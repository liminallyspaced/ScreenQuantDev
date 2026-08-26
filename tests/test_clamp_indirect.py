# CLAMP_INDIRECT classifier + journaled apply.
# Duck-typed integrator; no .blend, no bpy.ops, no GPU.
#   python3 tests/test_clamp_indirect.py

import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness  # noqa: E402
from _harness import PROJECT_ROOT, check, finish, section  # noqa: E402


def _load(rel):
    path = os.path.join(PROJECT_ROOT, *rel.split("/"))
    name = rel.replace("/", ".").removesuffix(".py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ci = _load("scenequant/analysis/clamp_indirect.py")
speed_solver = _load("scenequant/planning/speed_solver.py")


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Journal:
    """Duck journal: dotted RNA set_prop + revert identity."""

    def __init__(self):
        self.entries = []

    def set_prop(self, datablock, rna_path, value, tag=None, **kwargs):
        owner = datablock
        parts = rna_path.split(".")
        for part in parts[:-1]:
            owner = getattr(owner, part, None)
            if owner is None:
                return False
        attr = parts[-1]
        if not hasattr(owner, attr):
            return False
        old = getattr(owner, attr)
        setattr(owner, attr, value)
        self.entries.append({
            "t": "set",
            "path": rna_path,
            "old": old,
            "new": value,
            "tag": tag,
            "owner": datablock,
        })
        return True

    def revert(self):
        n = 0
        for entry in reversed(self.entries):
            owner = entry["owner"]
            parts = entry["path"].split(".")
            for part in parts[:-1]:
                owner = getattr(owner, part)
            setattr(owner, parts[-1], entry["old"])
            n += 1
        return n


def _scene(clamp=0.0, direct=0.0, engine="CYCLES", missing=False):
    cycles_kw = dict(
        device="GPU",
        sample_clamp_direct=direct,
    )
    if not missing:
        cycles_kw["sample_clamp_indirect"] = clamp
    return Obj(
        cycles=Obj(**cycles_kw),
        render=Obj(engine=engine),
        objects=[],
        world=None,
    )


def _speed_scene(clamp=0.0):
    cycles = Obj(
        device="GPU", use_adaptive_sampling=True, adaptive_threshold=0.02,
        samples=256, use_denoising=True, adaptive_min_samples=48,
        max_bounces=8, diffuse_bounces=3, glossy_bounces=4,
        transmission_bounces=6, transparent_max_bounces=8,
        sample_clamp_indirect=clamp, sample_clamp_direct=0.0,
        blur_glossy=1.0, use_light_tree=True,
        caustics_reflective=False, caustics_refractive=False,
        use_guiding=False, use_animated_seed=True, use_camera_cull=False,
        denoising_use_gpu=True,
    )
    render = Obj(
        engine="CYCLES", use_lock_interface=True, use_persistent_data=True,
        use_motion_blur=False, compositor_device="GPU",
    )
    return Obj(
        cycles=cycles, render=render, frame_start=1, frame_end=1,
        camera=Obj(), objects=[], world=None, view_layers=[],
        cycles_curves=Obj(shape="RIBBONS"), use_nodes=False, node_tree=None,
    )


def _settings():
    return Obj(vram_budget_gb=8.0, min_texture_size=256,
               coverage_frame_samples=5, quality_factor=2.0)


def _mem():
    return Obj(total_mb=400.0, caveats=[], per_object_geo_mb={},
               per_image_mb={})


def test_classify_disabled_only():
    section("classify: 0 fires; user values and missing attr do not")
    recs = ci.classify_clamp_indirect(_scene(0))
    check(len(recs) == 1 and recs[0]["class"] == "CLAMP_INDIRECT",
          "clamp 0 → one CLAMP_INDIRECT record")
    check(recs[0]["to"] == 10.0 and recs[0]["from"] == 0.0,
          "record is 0 → 10 (Cycles factory)")
    check(recs[0]["prop"] == "sample_clamp_indirect",
          "prop is sample_clamp_indirect")

    for value in (5.0, 10.0, 20.0, 0.01):
        recs = ci.classify_clamp_indirect(_scene(value))
        check(recs == [], "user clamp %s → no record" % value)

    recs = ci.classify_clamp_indirect(_scene(missing=True))
    check(recs == [], "missing attr → no record")

    recs = ci.classify_clamp_indirect(_scene(0, engine="BLENDER_EEVEE"))
    check(recs == [], "EEVEE engine → no record")

    recs = ci.classify_clamp_indirect(_scene(0, engine="CYCLES"))
    check(len(recs) == 1, "CYCLES engine + 0 still fires")


def test_never_writes_direct():
    section("apply never writes sample_clamp_direct")
    scene = _scene(0, direct=0.0)
    jrnl = _Journal()
    applied = ci.apply_clamp_indirect(scene, jrnl)
    check(len(applied) == 1, "apply writes the disabled clamp")
    check(scene.cycles.sample_clamp_indirect == 10.0,
          "indirect became Cycles factory 10")
    check(scene.cycles.sample_clamp_direct == 0.0,
          "direct clamp stayed 0")
    check(all(e["path"] != "cycles.sample_clamp_direct" for e in jrnl.entries),
          "journal has no sample_clamp_direct path")
    check(all(e["path"] == "cycles.sample_clamp_indirect" for e in jrnl.entries),
          "journal only recorded sample_clamp_indirect")


def test_apply_revert_identity():
    section("apply → revert restores integrator")
    scene = _scene(0, direct=0.0)
    before_indirect = scene.cycles.sample_clamp_indirect
    before_direct = scene.cycles.sample_clamp_direct
    jrnl = _Journal()
    ci.apply_clamp_indirect(scene, jrnl)
    check(scene.cycles.sample_clamp_indirect == 10.0, "applied 10")
    n = jrnl.revert()
    check(n == 1, "one journal entry reverted")
    check(scene.cycles.sample_clamp_indirect == before_indirect,
          "revert restored clamp-indirect 0")
    check(scene.cycles.sample_clamp_direct == before_direct,
          "revert left clamp-direct 0")


def test_apply_skips_user_value():
    section("apply re-proves current == 0")
    scene = _scene(10.0)
    jrnl = _Journal()
    applied = ci.apply_clamp_indirect(scene, jrnl)
    check(applied == [], "already 10 → apply no-op")
    check(scene.cycles.sample_clamp_indirect == 10.0, "user 10 unchanged")
    check(jrnl.entries == [], "no journal write when already enabled")

    scene = _scene(5.0)
    applied = ci.apply_clamp_indirect(scene, _Journal())
    check(applied == [], "user 5 → apply no-op (never raise or lower)")


def test_planner_hook_auto_off():
    section("planner hook exists; Auto plan does not call it")
    scene = _speed_scene(0.0)
    actions = speed_solver.clamp_indirect_actions(scene)
    check(len(actions) == 1 and actions[0].kind == "CLAMP_INDIRECT",
          "hook fires on clamp 0")
    check(actions[0].tier == 2, "tier 2 (Auto-off)")
    check(abs(actions[0].time_factor - 1.0) < 1e-9,
          "time_factor 1.0 (no claim)")
    check(actions[0].payload.get("value") == 10.0, "payload value 10")

    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    kinds = [a.kind for a in plan.actions]
    check("CLAMP_INDIRECT" not in kinds,
          "CLAMP_INDIRECT is not in the default Auto plan (clamp 0)")
    check(all(a.tier <= 1 for a in plan.actions),
          "default plan still tier 0+1 only")

    scene2 = _speed_scene(10.0)
    check(speed_solver.clamp_indirect_actions(scene2) == [],
          "hook silent when already 10")


def test_perceptual_paths_cannot_enable_zero():
    section("APPLY_PERCEPTUAL_PATHS MODE_MIN does not enable clamp 0")
    scene = _speed_scene(0.0)
    # PATH_ENTRIES MODE_MIN 5.0 fires only when current > 5.
    check(not speed_solver._entry_would_fire(
        scene, "cycles", "sample_clamp_indirect", 5.0, "min"),
          "MODE_MIN 5.0 does not fire on 0 (the gap this lever fills)")


def test_inventory_never_counts_direct():
    section("inventory counts")
    counts = ci.inventory_counts(ci.classify_clamp_indirect(_scene(0)))
    check(counts["CLAMP_INDIRECT"] == 1, "inventory counts the enable")
    check(counts["CLAMP_DIRECT_WRITES"] == 0, "inventory never counts direct")


def main():
    test_classify_disabled_only()
    test_never_writes_direct()
    test_apply_revert_identity()
    test_apply_skips_user_value()
    test_planner_hook_auto_off()
    test_perceptual_paths_cannot_enable_zero()
    test_inventory_never_counts_direct()
    finish()


if __name__ == "__main__":
    main()
