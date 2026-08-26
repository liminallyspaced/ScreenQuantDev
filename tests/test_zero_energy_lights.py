# ZERO_ENERGY_LIGHT classifier + journaled apply.
# Duck-typed lights; no .blend, no bpy.ops, no GPU.
#   python3 tests/test_zero_energy_lights.py

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


zel = _load("scenequant/analysis/zero_energy_lights.py")
speed_solver = _load("scenequant/planning/speed_solver.py")


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _Journal:
    """Duck journal: RNA set_prop + revert identity."""

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


def _light(name="Lamp", energy=0.0, light_type="POINT", hide_render=False,
           is_portal=False, library=None, data_library=None, engine_ok=True,
           animated=False, data_animated=False, override="AUTO"):
    data = Obj(
        energy=energy,
        type=light_type,
        cycles=Obj(is_portal=is_portal),
        library=data_library,
        animation_data=Obj(action=Obj(), nla_tracks=[], drivers=[]) if data_animated else None,
        use_nodes=False,
    )
    obj = Obj(
        name=name,
        type="LIGHT",
        hide_render=hide_render,
        data=data,
        library=library,
        animation_data=Obj(action=Obj(), nla_tracks=[], drivers=[]) if animated else None,
        scenequant=Obj(override=override),
    )
    return obj


def _mesh(name="Cube"):
    return Obj(
        name=name, type="MESH", hide_render=False, data=Obj(),
        library=None, animation_data=None,
        scenequant=Obj(override="AUTO"),
    )


def _scene(lights=None, engine="CYCLES"):
    objects = list(lights or [])
    return Obj(
        cycles=Obj(device="GPU"),
        render=Obj(engine=engine),
        objects=objects,
        world=None,
    )


def _speed_scene(lights=None):
    cycles = Obj(
        device="GPU", use_adaptive_sampling=True, adaptive_threshold=0.02,
        samples=256, use_denoising=True, adaptive_min_samples=48,
        max_bounces=8, diffuse_bounces=3, glossy_bounces=4,
        transmission_bounces=6, transparent_max_bounces=8,
        sample_clamp_indirect=10.0, sample_clamp_direct=0.0,
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
        camera=Obj(), objects=list(lights or []), world=None, view_layers=[],
        cycles_curves=Obj(shape="RIBBONS"), use_nodes=False, node_tree=None,
    )


def _settings():
    return Obj(vram_budget_gb=8.0, min_texture_size=256,
               coverage_frame_samples=5, quality_factor=2.0)


def _mem():
    return Obj(total_mb=400.0, caveats=[], per_object_geo_mb={},
               per_image_mb={})


def test_classify_energy_zero_only():
    section("classify: energy 0 fires; live lights / meshes / missing do not")
    recs = zel.classify_zero_energy_lights(_scene([_light("Dead", 0.0)]))
    check(len(recs) == 1 and recs[0]["class"] == "ZERO_ENERGY_LIGHT",
          "energy 0 → one ZERO_ENERGY_LIGHT record")
    check(recs[0]["object"] == "Dead" and recs[0]["to"] is True,
          "record names the light and hide_render True")
    check(recs[0]["energy"] == 0.0 and recs[0]["prop"] == "hide_render",
          "record is energy 0 → hide_render")

    for value in (0.01, 1.0, 10.0, 100.0):
        recs = zel.classify_zero_energy_lights(_scene([_light("Live", value)]))
        check(recs == [], "energy %s → no record" % value)

    recs = zel.classify_zero_energy_lights(_scene([_mesh()]))
    check(recs == [], "mesh is not a light → no record")

    recs = zel.classify_zero_energy_lights(_scene(
        [_light("Dead", 0.0)], engine="BLENDER_EEVEE"))
    check(recs == [], "EEVEE engine → no record")

    recs = zel.classify_zero_energy_lights(_scene(
        [_light("Dead", 0.0)], engine="CYCLES"))
    check(len(recs) == 1, "CYCLES engine + energy 0 still fires")

    already = _light("Hidden", 0.0, hide_render=True)
    recs = zel.classify_zero_energy_lights(_scene([already]))
    check(recs == [], "already hide_render → no record")


def test_skips_portal_linked_animated_hero():
    section("classify skips portal / linked / animated / HERO")
    recs = zel.classify_zero_energy_lights(_scene([
        _light("Portal", 0.0, is_portal=True)]))
    check(recs == [], "is_portal → skip (world MIS rectangle)")

    recs = zel.classify_zero_energy_lights(_scene([
        _light("Linked", 0.0, library=Obj())]))
    check(recs == [], "linked object → skip")

    recs = zel.classify_zero_energy_lights(_scene([
        _light("LinkedData", 0.0, data_library=Obj())]))
    check(recs == [], "linked light datablock → skip")

    recs = zel.classify_zero_energy_lights(_scene([
        _light("Keyed", 0.0, animated=True)]))
    check(recs == [], "object animation_data → skip")

    recs = zel.classify_zero_energy_lights(_scene([
        _light("KeyedData", 0.0, data_animated=True)]))
    check(recs == [], "light datablock animation_data → skip")

    recs = zel.classify_zero_energy_lights(_scene([
        _light("Hero", 0.0, override="HERO")]))
    check(recs == [], "HERO override → skip")

    recs = zel.classify_zero_energy_lights(_scene([
        _light("Keep", 0.0, override="KEEP")]))
    check(recs == [], "KEEP override → skip")


def test_never_writes_energy():
    section("apply never writes Light.energy")
    lamp = _light("Dead", 0.0)
    scene = _scene([lamp])
    jrnl = _Journal()
    applied = zel.apply_zero_energy_lights(scene, jrnl)
    check(len(applied) == 1, "apply hides the energy-0 light")
    check(lamp.hide_render is True, "hide_render became True")
    check(lamp.data.energy == 0.0, "energy stayed 0")
    check(all(e["path"] == "hide_render" for e in jrnl.entries),
          "journal only recorded hide_render")
    check(all(e["owner"] is lamp for e in jrnl.entries),
          "journal owner is the light object")


def test_apply_revert_identity():
    section("apply → revert restores hide_render")
    lamp = _light("Dead", 0.0)
    live = _light("Live", 12.0)
    scene = _scene([lamp, live])
    before_dead = lamp.hide_render
    before_live = live.hide_render
    before_energy = lamp.data.energy
    jrnl = _Journal()
    zel.apply_zero_energy_lights(scene, jrnl)
    check(lamp.hide_render is True, "applied hide_render")
    check(live.hide_render is False, "live light untouched")
    n = jrnl.revert()
    check(n == 1, "one journal entry reverted")
    check(lamp.hide_render is before_dead, "revert restored hide_render False")
    check(live.hide_render is before_live, "live light still visible")
    check(lamp.data.energy == before_energy, "energy still 0")


def test_apply_skips_live_and_portal():
    section("apply re-proves energy == 0 and not portal")
    live = _light("Live", 10.0)
    scene = _scene([live])
    jrnl = _Journal()
    applied = zel.apply_zero_energy_lights(scene, jrnl)
    check(applied == [], "energy 10 → apply no-op")
    check(live.hide_render is False, "live hide_render unchanged")
    check(jrnl.entries == [], "no journal write when energy != 0")

    portal = _light("Portal", 0.0, is_portal=True)
    applied = zel.apply_zero_energy_lights(_scene([portal]), _Journal())
    check(applied == [], "portal → apply no-op")
    check(portal.hide_render is False, "portal not hidden")


def test_planner_hook_auto_off():
    section("planner hook exists; Auto plan does not call it")
    dead = _light("Dead", 0.0)
    scene = _speed_scene([dead])
    actions = speed_solver.zero_energy_light_actions(scene)
    check(len(actions) == 1 and actions[0].kind == "ZERO_ENERGY_LIGHT",
          "hook fires on energy 0")
    check(actions[0].tier == 2, "tier 2 (Auto-off)")
    check(abs(actions[0].time_factor - 1.0) < 1e-9,
          "time_factor 1.0 (no claim)")
    check(len(actions[0].payload.get("records") or []) == 1,
          "payload carries the classify record")

    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    kinds = [a.kind for a in plan.actions]
    check("ZERO_ENERGY_LIGHT" not in kinds,
          "ZERO_ENERGY_LIGHT is not in the default Auto plan (energy 0)")
    check(all(a.tier <= 1 for a in plan.actions),
          "default plan still tier 0+1 only")

    scene2 = _speed_scene([_light("Live", 8.0)])
    check(speed_solver.zero_energy_light_actions(scene2) == [],
          "hook silent when every light has energy > 0")


def test_scene_agnostic_not_name_gated():
    section("classifier is DNA, never a scene/object name")
    # Names that would look "interior" / classroom must still classify from energy.
    recs = zel.classify_zero_energy_lights(_scene([
        _light("chair.001", 0.0),
        _light("ClassroomLamp", 4.0),
        _light("exterior_sun", 0.0),
    ]))
    names = sorted(r["object"] for r in recs)
    check(names == ["chair.001", "exterior_sun"],
          "two energy-0 lights fire regardless of name; live ClassroomLamp skipped")


def test_inventory_never_counts_energy_writes():
    section("inventory counts")
    counts = zel.inventory_counts(
        zel.classify_zero_energy_lights(_scene([_light("Dead", 0.0)])))
    check(counts["ZERO_ENERGY_LIGHT"] == 1, "inventory counts the hide")
    check(counts["ENERGY_WRITES"] == 0, "inventory never counts energy writes")


def main():
    test_classify_energy_zero_only()
    test_skips_portal_linked_animated_hero()
    test_never_writes_energy()
    test_apply_revert_identity()
    test_apply_skips_live_and_portal()
    test_planner_hook_auto_off()
    test_scene_agnostic_not_name_gated()
    test_inventory_never_counts_energy_writes()
    finish()


if __name__ == "__main__":
    main()
