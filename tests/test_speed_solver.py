# Speed-solver unit tests. No .blend required. Runs inside Blender or with
# plain Python (solver is importable without bpy; duck-typed scene/settings).
#   python tests/test_speed_solver.py
#   blender -b --factory-startup --python-exit-code 1 --python tests/test_speed_solver.py

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


speed_solver = _load("scenequant/planning/speed_solver.py")
SpeedAction = speed_solver.SpeedAction


class Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _scene(**cycles_kw):
    cycles_kw_full = dict(
        device="GPU",
        use_adaptive_sampling=True,
        adaptive_threshold=0.02,
        samples=256,
        use_denoising=True,
        adaptive_min_samples=48,
        max_bounces=8,
        diffuse_bounces=3,
        glossy_bounces=4,
        transmission_bounces=6,
        transparent_max_bounces=8,
        sample_clamp_indirect=5.0,
        blur_glossy=1.0,
        use_light_tree=True,
        caustics_reflective=False,
        caustics_refractive=False,
        use_guiding=False,
        use_animated_seed=True,
        use_camera_cull=False,
        denoising_use_gpu=True,
    )
    cycles_kw_full.update(cycles_kw)
    cycles = Obj(**cycles_kw_full)
    render = Obj(
        engine="CYCLES",
        use_lock_interface=True,
        use_persistent_data=True,
        use_motion_blur=False,
        compositor_device="GPU",
    )
    return Obj(
        cycles=cycles,
        render=render,
        frame_start=1,
        frame_end=1,
        camera=Obj(),
        objects=[],
        world=None,
        view_layers=[],
        cycles_curves=Obj(shape="RIBBONS"),
        use_nodes=False,
        node_tree=None,
    )


def _settings():
    return Obj(vram_budget_gb=8.0, min_texture_size=256,
               coverage_frame_samples=5, quality_factor=2.0)


def _mem(total=400.0):
    return Obj(total_mb=total, caveats=[], per_object_geo_mb={}, per_image_mb={})


def test_independence():
    section("one class one lever")
    actions = [
        SpeedAction("A", "a", "samples", 1, 0.50, 1, {}),
        SpeedAction("B", "b", "samples", 1, 0.80, 1, {}),
        SpeedAction("C", "c", "paths", 1, 0.90, 1, {}),
    ]
    kept = speed_solver.strongest_per_class(actions)
    check([a.kind for a in kept] == ["A", "C"],
          "strongest_per_class keeps one lever per waste_class")
    check(abs(speed_solver.multiply_factors(kept) - 0.45) < 1e-9,
          "factors multiply across classes (0.5 * 0.9)")


def test_default_plan_filters():
    section("default plan filters")
    scene = _scene(use_adaptive_sampling=False, samples=4096,
                   use_denoising=False, adaptive_threshold=0.01)
    scene.render.use_lock_interface = False
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    kinds = [a.kind for a in plan.actions]
    check(all(a.tier <= 1 for a in plan.actions),
          "tier 2/3 never in default plan")
    check(all(a.kind not in speed_solver.FORBIDDEN_KINDS for a in plan.actions),
          "no QUANTIZE/DRAFT/DEDUP in default plan")
    check("ADAPTIVE_ON" in kinds, "adaptive-off scene proposes ADAPTIVE_ON")
    check("SAMPLES_CAP" in kinds, "4096 samples proposes SAMPLES_CAP")
    check("LOCK_INTERFACE" in kinds, "unlocked interface proposes LOCK_INTERFACE")
    expected = speed_solver.multiply_factors(
        speed_solver.strongest_per_class(plan.actions))
    check(abs(plan.est_factor - expected) < 1e-9,
          "est_factor is the class-deduped product")


def test_never_raise_samples():
    section("samples are a ceiling")
    scene = _scene(samples=128, max_bounces=4)
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    kinds = [a.kind for a in plan.actions]
    check("SAMPLES_CAP" not in kinds,
          "samples 128 < 256: never propose lowering")
    # MODE_MIN bounce caps would not fire when already under the floor.
    path = [a for a in plan.actions if a.kind == "APPLY_PERCEPTUAL_PATHS"]
    check(not path, "bounces already at/under cap: no path write proposed")


def test_already_fast():
    section("honest empty plan")
    scene = _scene(use_light_tree=False)
    # Hide GPU-denoise (hasattr true on Obj) by using a cycles without the attr.
    del scene.cycles.denoising_use_gpu
    del scene.cycles.adaptive_min_samples
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(plan.est_factor == 1.0 or plan.actions,
          "empty or residual cheap levers only")
    if not plan.actions:
        check(any("low-double-digit" in c for c in plan.caveats),
              "no-action plan caveats low-double-digit gains")
        check(abs(plan.est_pct - 100.0) < 1e-9, "no-action est_pct is 100")


def test_light_tree_product_shot():
    section("light tree is not always-on")
    scene = _scene(use_light_tree=True)
    # Four simple lights, no mesh lights, no linking → propose OFF.
    scene.objects = [
        Obj(name="L%d" % i, type="LIGHT", hide_render=False,
            data=Obj(type="AREA"), light_linking=None, cycles=None,
            scenequant=Obj(override="AUTO"), material_slots=())
        for i in range(4)
    ]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    trees = [a for a in plan.actions if a.kind == "LIGHT_TREE"]
    check(len(trees) == 1 and trees[0].payload.get("enabled") is False,
          "≤4 simple lights → light tree off")


def test_persistent_session_bvh():
    section("persistent data keeps the next F12 BVH")
    still = _scene()
    still.render.use_persistent_data = False
    plan = speed_solver.build_speed_plan(still, {}, _mem(), _settings())
    hits = [a for a in plan.actions if a.kind == "PERSISTENT_DATA"]
    check(len(hits) == 1, "still frame proposes persistent data")
    check(abs(hits[0].time_factor - 1.0) < 1e-9,
          "still persistent factor is 1.0 (first F12 unpaid)")
    check(any("first F12" in c for c in plan.caveats),
          "still persistent caveats first F12")
    already = _scene()
    already.render.use_persistent_data = True
    plan = speed_solver.build_speed_plan(already, {}, _mem(), _settings())
    check(all(a.kind != "PERSISTENT_DATA" for a in plan.actions),
          "already-on persistent is not rewritten")
    anim = _scene()
    anim.render.use_persistent_data = False
    anim.frame_end = 48
    anim.camera.animation_data = Obj(action=Obj(name="CameraAction"), nla_tracks=())
    plan = speed_solver.build_speed_plan(anim, {}, _mem(), _settings())
    hits = [a for a in plan.actions if a.kind == "PERSISTENT_DATA"]
    check(len(hits) == 1, "animation with camera action proposes persistent data")
    check(abs(hits[0].time_factor - 0.55) < 1e-9,
          "animation persistent keeps 0.55 when budget is set")
    clock = _scene()
    clock.render.use_persistent_data = False
    clock.frame_end = 250
    clock.cycles.use_animated_seed = False
    clock.objects = [_mesh("Clock", animation_data=Obj(
        action=Obj(name="Tick"), nla_tracks=()))]
    plan = speed_solver.build_speed_plan(clock, {}, _mem(), _settings())
    check(any(a.kind == "PERSISTENT_DATA" for a in plan.actions),
          "object-only 1-250 still still gets session BVH")
    check(all(a.kind != "ANIMATED_SEED" for a in plan.actions),
          "object-only action does not propose animated seed")


class _GetMap:
    def __init__(self, mapping):
        self._mapping = mapping

    def get(self, key):
        return self._mapping.get(key)


def _mesh(name, **kw):
    defaults = dict(
        name=name, type="MESH", hide_render=False, data=None,
        light_linking=None, cycles=None, scenequant=Obj(override="AUTO"),
        material_slots=(), is_shadow_catcher=False, library=None,
        override_library=None, animation_data=None, modifiers=(),
    )
    defaults.update(kw)
    return Obj(**defaults)


def _empty(name, **kw):
    defaults = dict(
        name=name, type="EMPTY", instance_type="COLLECTION",
        instance_collection=Obj(), hide_render=False, data=None,
        light_linking=None, cycles=None, scenequant=Obj(override="AUTO"),
        material_slots=(), is_shadow_catcher=False, library=None,
        override_library=None, animation_data=None, modifiers=(),
    )
    defaults.update(kw)
    return Obj(**defaults)


def _off_cov(*names):
    return {n: {"near_frustum_ever": False, "in_frustum_ever": False,
                "max_coverage": 0.0} for n in names}


def _vol_mat(name, types, homogeneous=False, library=None):
    return Obj(
        name=name,
        library=library,
        cycles=Obj(homogeneous_volume=homogeneous),
        node_tree=Obj(nodes=[Obj(type=t) for t in types]),
        use_nodes=True,
    )


def _principled_mat(name, strength=0.5, linked=False):
    sock = Obj(default_value=strength, is_linked=linked)
    node = Obj(type="BSDF_PRINCIPLED",
               inputs=_GetMap({"Emission Strength": sock}),
               outputs=[], node_tree=None)
    return Obj(name=name, node_tree=Obj(nodes=[node]))


def _tiny_cov(*names):
    return {n: {"max_coverage": 0.002, "in_frustum_ever": True,
                "near_frustum_ever": True} for n in names}


def test_micro_emitters_strict():
    section("micro-emitters are strict")
    scene = _scene()
    nodeless = Obj(name="Flat", node_tree=None)
    scene.objects = [_mesh("Prop", material_slots=[Obj(material=nodeless)])]
    plan = speed_solver.build_speed_plan(
        scene, _tiny_cov("Prop"), _mem(), _settings())
    check(all(a.kind != "MICRO_EMITTERS" for a in plan.actions),
          "nodeless material does not produce MICRO_EMITTERS")

    neon = _principled_mat("Neon", strength=0.5)
    scene = _scene()
    scene.objects = [_mesh("Bulb", material_slots=[Obj(material=neon)])]
    plan = speed_solver.build_speed_plan(
        scene, _tiny_cov("Bulb"), _mem(), _settings())
    micros = [a for a in plan.actions if a.kind == "MICRO_EMITTERS"]
    check(len(micros) == 1 and "Bulb" in micros[0].payload.get("objects", []),
          "principled strength 0.5 on 0.2% coverage proposes MICRO_EMITTERS")

    shared = _principled_mat("Window_glass", strength=0.5)
    scene = _scene()
    scene.objects = [
        _mesh("PaneTiny", material_slots=[Obj(material=shared)]),
        _mesh("PaneBig", material_slots=[Obj(material=shared)]),
    ]
    cov = _tiny_cov("PaneTiny")
    cov["PaneBig"] = {"max_coverage": 0.20, "in_frustum_ever": True,
                      "near_frustum_ever": True}
    plan = speed_solver.build_speed_plan(scene, cov, _mem(), _settings())
    check(all(a.kind != "MICRO_EMITTERS" for a in plan.actions),
          "material also used by 20% coverage object is not a micro-emitter")

    scene = _scene()
    objs = []
    cov = {}
    for i in range(40):
        name = "Tiny%d" % i
        mat = _principled_mat("Emit%d" % i, strength=0.5)
        objs.append(_mesh(name, material_slots=[Obj(material=mat)]))
        cov[name] = {"max_coverage": 0.002, "in_frustum_ever": True,
                     "near_frustum_ever": True}
    scene.objects = objs
    plan = speed_solver.build_speed_plan(scene, cov, _mem(), _settings())
    check(all(a.kind != "MICRO_EMITTERS" for a in plan.actions),
          "40 tiny emitters skip the MICRO_EMITTERS lever")
    check(any("too many tiny-emitter candidates" in c for c in plan.caveats),
          "over-count micro-emitters caveats asset-pack leftover")


def test_honest_estimate_gated_noops():
    section("honest estimate ignores unpaid VRAM levers")
    scene = _scene()
    scene.render.use_persistent_data = False
    scene.frame_end = 48
    scene.camera.animation_data = Obj(action=Obj(name="Cam"), nla_tracks=())
    scene.cycles.use_denoising = False
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.samples = 512
    zero = Obj(vram_budget_gb=0.0, min_texture_size=256,
               coverage_frame_samples=5, quality_factor=2.0)
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), zero)
    kinds = {a.kind: a.time_factor for a in plan.actions}
    check("PERSISTENT_DATA" in kinds, "still proposes persistent data")
    check(abs(kinds["PERSISTENT_DATA"] - 1.0) < 1e-9,
          "VRAM 0 → persistent factor 1.0")
    check("GPU_DENOISE" in kinds, "still proposes GPU denoise")
    check(abs(kinds["GPU_DENOISE"] - 1.0) < 1e-9,
          "VRAM 0 → GPU denoise factor 1.0")
    check(abs(kinds.get("DENOISE_ON", 1.0) - 1.0) < 1e-9,
          "OIDN without sample drop is factor 1.0")
    winners = speed_solver.strongest_per_class(plan.actions)
    rebuild = [a for a in winners if a.waste_class == "rebuild"][0]
    check(rebuild.kind != "PERSISTENT_DATA" or rebuild.time_factor >= 1.0,
          "rebuild winner is not a fake 0.55")
    check(any("budget unset" in c for c in plan.caveats),
          "caveat names unset VRAM budget")

    rich = _settings()
    plan2 = speed_solver.build_speed_plan(scene, {}, _mem(), rich)
    kinds2 = {a.kind: a.time_factor for a in plan2.actions}
    check(abs(kinds2["PERSISTENT_DATA"] - 0.55) < 1e-9,
          "budget set → persistent keeps 0.55")
    check(abs(kinds2["GPU_DENOISE"] - 0.85) < 1e-9,
          "budget set → GPU denoise keeps 0.85")

    drop = _scene(samples=4096, use_denoising=False, use_adaptive_sampling=True)
    plan3 = speed_solver.build_speed_plan(drop, {}, _mem(), _settings())
    den = [a for a in plan3.actions if a.kind == "DENOISE_ON"]
    check(den and abs(den[0].time_factor - 0.80) < 1e-9,
          "OIDN + sample ceiling keeps 0.80")




def test_linked_offscreen_is_loud():
    section("linked off-screen trim is not silent")
    scene = _scene()
    chair = _mesh("Chair.001", library="assets/chairs.blend")
    local = _mesh("WasteBin")
    scene.objects = [chair, local]
    cov = {
        "Chair.001": {"near_frustum_ever": False, "in_frustum_ever": False,
                      "max_coverage": 0.0},
        "WasteBin": {"near_frustum_ever": False, "in_frustum_ever": False,
                     "max_coverage": 0.0},
    }
    plan = speed_solver.build_speed_plan(scene, cov, _mem(), _settings())
    trims = [a for a in plan.actions if a.kind == "TRIM_OFFSCREEN"]
    check(len(trims) == 1 and trims[0].payload.get("objects") == ["WasteBin"],
          "local off-screen object is trimmed")
    check(all("Chair.001" not in (a.payload.get("objects") or [])
              for a in trims),
          "linked off-screen object is not trimmed")
    check(any("not trimmed (linked" in c for c in plan.caveats),
          "linked skip is a caveat, not silent")


def test_linked_cull_is_loud():
    section("linked scatter is camera-culled")
    scene = _scene()
    scene.objects = [_mesh("Chair.001", library="assets/chairs.blend")]
    plan = speed_solver.build_speed_plan(
        scene, _tiny_cov("Chair.001"), _mem(), _settings())
    culls = [a for a in plan.actions if a.kind == "CAMERA_CULL"]
    check(len(culls) == 1 and "Chair.001" in (culls[0].payload.get("objects") or []),
          "linked scatter object is camera-culled")
    check(all("not camera-culled (linked" not in c for c in plan.caveats),
          "linked cull is not caveated as skipped")


def test_hero_tiny_not_camera_culled():
    section("HERO tiny is not camera-culled")
    scene = _scene()
    scene.objects = [_mesh("HeroTiny", scenequant=Obj(override="HERO"))]
    plan = speed_solver.build_speed_plan(
        scene, _tiny_cov("HeroTiny"), _mem(), _settings())
    culled = []
    for a in plan.actions:
        if a.kind == "CAMERA_CULL":
            culled.extend(a.payload.get("objects") or [])
    check("HeroTiny" not in culled, "HERO tiny object is not camera-culled")


def test_denoise_prefilter_accurate_only():
    section("OIDN prefilter FAST only from Accurate")
    scene = _scene()
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "DENOISE_PREFILTER" for a in plan.actions),
          "no denoising_prefilter attr → no DENOISE_PREFILTER")

    scene = _scene(denoising_prefilter="ACCURATE", use_denoising=True)
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    hits = [a for a in plan.actions if a.kind == "DENOISE_PREFILTER"]
    check(len(hits) == 1, "ACCURATE + denoise on → DENOISE_PREFILTER")
    check(abs(hits[0].time_factor - 0.95) < 1e-9, "time_factor 0.95")
    check(hits[0].payload.get("value") == "FAST", "payload value FAST")

    scene = _scene(denoising_prefilter="FAST")
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "DENOISE_PREFILTER" for a in plan.actions),
          "FAST → no DENOISE_PREFILTER")

    scene = _scene(denoising_prefilter="NONE")
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "DENOISE_PREFILTER" for a in plan.actions),
          "NONE → no DENOISE_PREFILTER")

    scene = _scene(denoising_prefilter="ACCURATE", use_denoising=False)
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(any(a.kind == "DENOISE_PREFILTER" for a in plan.actions),
          "ACCURATE + denoise off → still DENOISE_PREFILTER (OIDN turning on)")

def test_world_mis_solid_only():
    section("world MIS none is solid-only")
    scene = _scene()
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "WORLD_MIS_NONE" for a in plan.actions),
          "default scene world=None → no WORLD_MIS_NONE")

    scene = _scene()
    scene.world = Obj(
        use_nodes=False, node_tree=None, library=None,
        cycles=Obj(sampling_method="AUTOMATIC"))
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    hits = [a for a in plan.actions if a.kind == "WORLD_MIS_NONE"]
    check(len(hits) == 1, "nodeless AUTOMATIC world → WORLD_MIS_NONE")
    check(abs(hits[0].time_factor - 0.95) < 1e-9, "WORLD_MIS_NONE factor 0.95")

    scene = _scene()
    scene.world = Obj(
        use_nodes=True,
        node_tree=Obj(nodes=[Obj(type="TEX_ENVIRONMENT")]),
        library=None,
        cycles=Obj(sampling_method="AUTOMATIC"))
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "WORLD_MIS_NONE" for a in plan.actions),
          "TEX_ENVIRONMENT world → no WORLD_MIS_NONE")

    scene = _scene()
    scene.world = Obj(
        use_nodes=True,
        node_tree=Obj(nodes=[Obj(type="GROUP")]),
        library=None,
        cycles=Obj(sampling_method="AUTOMATIC"))
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "WORLD_MIS_NONE" for a in plan.actions),
          "GROUP world → no WORLD_MIS_NONE (not proven)")

    scene = _scene()
    scene.world = Obj(
        use_nodes=False, node_tree=None, library=None,
        cycles=Obj(sampling_method="NONE"))
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "WORLD_MIS_NONE" for a in plan.actions),
          "sampling already NONE → no WORLD_MIS_NONE")

    scene = _scene()
    scene.world = Obj(
        use_nodes=False, node_tree=None, library="lib.blend",
        cycles=Obj(sampling_method="AUTOMATIC"))
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "WORLD_MIS_NONE" for a in plan.actions),
          "linked nodeless world → no WORLD_MIS_NONE")
    check(any("linked world" in c for c in plan.caveats),
          "linked world skip is a caveat, not silent")


def test_volume_bounces_zero():
    section("volume bounces zero when no volumes")
    scene = _scene()
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "VOLUME_BOUNCES_ZERO" for a in plan.actions),
          "default scene has no volume_bounces attr → no VOLUME_BOUNCES_ZERO")

    scene = _scene(volume_bounces=12)
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    hits = [a for a in plan.actions if a.kind == "VOLUME_BOUNCES_ZERO"]
    check(len(hits) == 1, "volume_bounces=12, no volumes → VOLUME_BOUNCES_ZERO")
    check(abs(hits[0].time_factor - 0.90) < 1e-9, "factor 0.90 when current > 4")
    check(hits[0].payload.get("value") == 0, "payload value 0")

    scene = _scene(volume_bounces=2)
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    hits = [a for a in plan.actions if a.kind == "VOLUME_BOUNCES_ZERO"]
    check(len(hits) == 1, "volume_bounces=2, no volumes → VOLUME_BOUNCES_ZERO")
    check(abs(hits[0].time_factor - 0.97) < 1e-9, "factor 0.97 when current <= 4")

    scene = _scene(volume_bounces=12)
    scene.objects = [_mesh("VolObj", type="VOLUME")]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "VOLUME_BOUNCES_ZERO" for a in plan.actions),
          "VOLUME-type object → no VOLUME_BOUNCES_ZERO")

    vol_node = Obj(type="PRINCIPLED_VOLUME")
    vol_mat = Obj(name="VolMat", node_tree=Obj(nodes=[vol_node]))
    scene = _scene(volume_bounces=12)
    scene.objects = [_mesh("FogMesh", material_slots=[Obj(material=vol_mat)])]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "VOLUME_BOUNCES_ZERO" for a in plan.actions),
          "PRINCIPLED_VOLUME material → no VOLUME_BOUNCES_ZERO")

    grp_node = Obj(type="GROUP")
    grp_mat = Obj(name="GrpMat", node_tree=Obj(nodes=[grp_node]))
    scene = _scene(volume_bounces=12)
    scene.objects = [_mesh("Mystery", material_slots=[Obj(material=grp_mat)])]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "VOLUME_BOUNCES_ZERO" for a in plan.actions),
          "material GROUP node → no VOLUME_BOUNCES_ZERO (not proven)")


def test_hide_offscreen_instances():
    section("off-screen local collection instances")
    scene = _scene()
    scene.objects = [_empty("ChairInst")]
    plan = speed_solver.build_speed_plan(
        scene, _off_cov("ChairInst"), _mem(), _settings())
    hides = [a for a in plan.actions if a.kind == "HIDE_OFFSCREEN_INSTANCES"]
    check(len(hides) == 1,
          "off-screen local collection instance → HIDE_OFFSCREEN_INSTANCES")
    check("ChairInst" in (hides[0].payload.get("objects") or []),
          "payload has the instance name")

    scene = _scene()
    scene.objects = [_mesh("WasteBin")]
    plan = speed_solver.build_speed_plan(
        scene, _off_cov("WasteBin"), _mem(), _settings())
    check(all(a.kind != "HIDE_OFFSCREEN_INSTANCES" for a in plan.actions),
          "off-screen MESH is not HIDE_OFFSCREEN_INSTANCES")

    scene = _scene()
    scene.objects = [_empty("LinkedChair", library="assets/chairs.blend")]
    plan = speed_solver.build_speed_plan(
        scene, _off_cov("LinkedChair"), _mem(), _settings())
    check(all(a.kind != "HIDE_OFFSCREEN_INSTANCES" for a in plan.actions),
          "linked off-screen collection instance is not hidden")
    check(any("linked" in c or "collection instance" in c for c in plan.caveats),
          "linked instance skip is a caveat, not silent")

    scene = _scene()
    scene.objects = [_empty("OnScreenChair")]
    cov = {"OnScreenChair": {"near_frustum_ever": True, "in_frustum_ever": True,
                             "max_coverage": 0.2}}
    plan = speed_solver.build_speed_plan(scene, cov, _mem(), _settings())
    check(all(a.kind != "HIDE_OFFSCREEN_INSTANCES" for a in plan.actions),
          "in-frustum collection instance is not hidden")

    scene = _scene()
    scene.objects = [_empty("HeroChair", scenequant=Obj(override="HERO"))]
    plan = speed_solver.build_speed_plan(
        scene, _off_cov("HeroChair"), _mem(), _settings())
    check(all(a.kind != "HIDE_OFFSCREEN_INSTANCES" for a in plan.actions),
          "HERO collection instance is not hidden")

    lamp_coll = Obj(objects=[Obj(
        name="Spot", type="LIGHT", hide_render=False,
        material_slots=(), instance_collection=None)])
    scene = _scene()
    scene.objects = [_empty("ceilingLamp", instance_collection=lamp_coll)]
    plan = speed_solver.build_speed_plan(
        scene, _off_cov("ceilingLamp"), _mem(), _settings())
    check(all(a.kind != "HIDE_OFFSCREEN_INSTANCES" for a in plan.actions),
          "off-screen lamp instance is not hidden")
    check(any("light" in c.lower() for c in plan.caveats),
          "light instance skip is a caveat, not silent")

    emit_coll = Obj(objects=[_mesh("Fixture", material_slots=[
        Obj(material=_principled_mat("Emit", strength=5.0))])])
    scene = _scene()
    scene.objects = [_empty("MeshLightInst", instance_collection=emit_coll)]
    plan = speed_solver.build_speed_plan(
        scene, _off_cov("MeshLightInst"), _mem(), _settings())
    check(all(a.kind != "HIDE_OFFSCREEN_INSTANCES" for a in plan.actions),
          "off-screen mesh-light instance is not hidden")

    scene = _scene()
    scene.objects = [_empty("ceilingLamp", instance_collection=lamp_coll)]
    plan = speed_solver.build_speed_plan(
        scene, _tiny_cov("ceilingLamp"), _mem(), _settings())
    culls = [a for a in plan.actions if a.kind == "CAMERA_CULL"]
    culled = []
    for a in culls:
        culled.extend(a.payload.get("objects") or [])
    check("ceilingLamp" not in culled,
          "tiny lamp instance is not camera-culled")


def test_homogeneous_volume_proven_only():
    section("homogeneous volume is proven-untextured only")
    scene = _scene()
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "HOMOGENEOUS_VOLUME" for a in plan.actions),
          "default scene → no HOMOGENEOUS_VOLUME")

    fog = _vol_mat("Fog", ["PRINCIPLED_VOLUME"])
    scene = _scene()
    scene.objects = [_mesh("FogMesh", material_slots=[Obj(material=fog)])]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    hits = [a for a in plan.actions if a.kind == "HOMOGENEOUS_VOLUME"]
    check(len(hits) == 1, "PRINCIPLED_VOLUME only → HOMOGENEOUS_VOLUME")
    check(abs(hits[0].time_factor - 0.92) < 1e-9,
          "HOMOGENEOUS_VOLUME factor 0.92")
    check("Fog" in (hits[0].payload.get("materials") or []),
          "payload materials contains Fog")
    check(hits[0].payload.get("world") is False, "payload world False")

    noisy = _vol_mat("NoisyFog", ["PRINCIPLED_VOLUME", "TEX_NOISE"])
    scene = _scene()
    scene.objects = [_mesh("Noisy", material_slots=[Obj(material=noisy)])]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "HOMOGENEOUS_VOLUME" for a in plan.actions),
          "PRINCIPLED_VOLUME + TEX_NOISE → no HOMOGENEOUS_VOLUME")

    grouped = _vol_mat("GrpFog", ["PRINCIPLED_VOLUME", "GROUP"])
    scene = _scene()
    scene.objects = [_mesh("Grp", material_slots=[Obj(material=grouped)])]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "HOMOGENEOUS_VOLUME" for a in plan.actions),
          "PRINCIPLED_VOLUME + GROUP → no HOMOGENEOUS_VOLUME")

    attr = _vol_mat("AttrFog", ["PRINCIPLED_VOLUME", "ATTRIBUTE"])
    scene = _scene()
    scene.objects = [_mesh("Attr", material_slots=[Obj(material=attr)])]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "HOMOGENEOUS_VOLUME" for a in plan.actions),
          "PRINCIPLED_VOLUME + ATTRIBUTE → no HOMOGENEOUS_VOLUME")

    already = _vol_mat("Already", ["PRINCIPLED_VOLUME"], homogeneous=True)
    scene = _scene()
    scene.objects = [_mesh("Done", material_slots=[Obj(material=already)])]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "HOMOGENEOUS_VOLUME" for a in plan.actions),
          "already homogeneous True → no HOMOGENEOUS_VOLUME")

    linked = _vol_mat("LinkedFog", ["PRINCIPLED_VOLUME"], library="lib.blend")
    scene = _scene()
    scene.objects = [_mesh("Linked", material_slots=[Obj(material=linked)])]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "HOMOGENEOUS_VOLUME" for a in plan.actions),
          "linked volume material → no HOMOGENEOUS_VOLUME")
    check(any("linked" in c for c in plan.caveats),
          "linked volume skip is a caveat, not silent")

    scene = _scene()
    scene.world = Obj(
        library=None,
        cycles=Obj(homogeneous_volume=False),
        node_tree=Obj(nodes=[Obj(type="VOLUME_SCATTER")]),
        use_nodes=True)
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    hits = [a for a in plan.actions if a.kind == "HOMOGENEOUS_VOLUME"]
    check(len(hits) == 1, "world VOLUME_SCATTER → HOMOGENEOUS_VOLUME")
    check(hits[0].payload.get("world") is True, "payload world True")

    hero_mat = _vol_mat("HeroFog", ["PRINCIPLED_VOLUME"])
    auto_mat = _vol_mat("AutoFog", ["PRINCIPLED_VOLUME"])
    excl_mat = _vol_mat("ExclFog", ["PRINCIPLED_VOLUME"])
    scene = _scene()
    scene.objects = [
        _mesh("HeroVol", material_slots=[Obj(material=hero_mat)],
              scenequant=Obj(override="HERO")),
        _mesh("AutoVol", material_slots=[Obj(material=auto_mat)]),
        _mesh("ExclVol", material_slots=[Obj(material=excl_mat)],
              scenequant=Obj(override="EXCLUDE")),
    ]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    hits = [a for a in plan.actions if a.kind == "HOMOGENEOUS_VOLUME"]
    mats = (hits[0].payload.get("materials") or []) if hits else []
    check("HeroFog" not in mats, "HERO object volume material is not included")
    check("ExclFog" not in mats, "EXCLUDE object volume material is not included")
    check("AutoFog" in mats, "AUTO object volume material is included")


def test_offscreen_dicing_adaptive_only():
    section("offscreen dicing is adaptive-subdiv only")
    orig = speed_solver._uses_adaptive_subdiv
    try:
        scene = _scene()
        plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
        check(all(a.kind != "OFFSCREEN_DICING" for a in plan.actions),
              "no scale attr → no OFFSCREEN_DICING")

        scene = _scene(offscreen_dicing_scale=1.0)
        scene.objects = [_mesh("Ground")]
        plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
        check(all(a.kind != "OFFSCREEN_DICING" for a in plan.actions),
              "no adaptive subdiv → no OFFSCREEN_DICING")

        speed_solver._uses_adaptive_subdiv = lambda scene, obj: True
        scene = _scene(offscreen_dicing_scale=1.0)
        scene.objects = [_mesh("Ground")]
        plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
        hits = [a for a in plan.actions if a.kind == "OFFSCREEN_DICING"]
        check(len(hits) == 1, "adaptive subdiv + scale 1 → OFFSCREEN_DICING")
        check(hits[0].payload.get("value") == 8.0, "payload value 8.0")
        check(abs(hits[0].time_factor - 0.92) < 1e-9, "factor 0.92")

        scene = _scene(offscreen_dicing_scale=8.0)
        scene.objects = [_mesh("Ground")]
        plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
        check(all(a.kind != "OFFSCREEN_DICING" for a in plan.actions),
              "already 8 → no write")

        scene = _scene(offscreen_dicing_scale=16.0)
        scene.objects = [_mesh("Ground")]
        plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
        check(all(a.kind != "OFFSCREEN_DICING" for a in plan.actions),
              "user 16 is not lowered")
    finally:
        speed_solver._uses_adaptive_subdiv = orig


def test_light_sampling_threshold_disabled_only():
    section("light sampling threshold is factory-default only")
    scene = _scene()
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "LIGHT_SAMPLING_THRESHOLD" for a in plan.actions),
          "no threshold attr → no LIGHT_SAMPLING_THRESHOLD")

    scene = _scene(light_sampling_threshold=0)
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    hits = [a for a in plan.actions if a.kind == "LIGHT_SAMPLING_THRESHOLD"]
    check(len(hits) == 1, "threshold 0 (disabled) → LIGHT_SAMPLING_THRESHOLD")
    check(abs(hits[0].time_factor - 0.94) < 1e-9, "factor 0.94")
    check(hits[0].payload.get("value") == 0.01, "payload value 0.01")

    scene = _scene(light_sampling_threshold=0.01)
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "LIGHT_SAMPLING_THRESHOLD" for a in plan.actions),
          "already 0.01 → no write")

    scene = _scene(light_sampling_threshold=0.02)
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "LIGHT_SAMPLING_THRESHOLD" for a in plan.actions),
          "user already cheaper (0.02) → no write")

    scene = _scene(light_sampling_threshold=0.005)
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "LIGHT_SAMPLING_THRESHOLD" for a in plan.actions),
          "user stricter 0.005 → not raised")


def test_pass_prune_unused_only():
    section("unused view-layer passes")
    scene = _scene()
    scene.view_layers = [Obj(
        name="ViewLayer", use_pass_z=True, use_pass_normal=True,
        use_pass_object_index=False, use_pass_combined=True,
        use_pass_mist=False, use_pass_uv=False, use_pass_vector=False,
        use_pass_material_index=False, use_pass_diffuse_direct=False,
        use_pass_diffuse_indirect=False, use_pass_diffuse_color=False,
        use_pass_glossy_direct=False, use_pass_glossy_indirect=False,
        use_pass_glossy_color=False, use_pass_transmission_direct=False,
        use_pass_transmission_indirect=False, use_pass_transmission_color=False,
        use_pass_emit=False, use_pass_environment=False, use_pass_shadow=False,
        use_pass_ambient_occlusion=False, use_pass_volume_direct=False,
        use_pass_volume_indirect=False, use_pass_position=False)]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    hits = [a for a in plan.actions if a.kind == "PASS_PRUNE"]
    check(len(hits) == 1, "no compositor + leftover Z/Normal → PASS_PRUNE")
    pruned = hits[0].payload.get("passes") or []
    check(("ViewLayer", "use_pass_z") in pruned, "payload includes use_pass_z")
    check(("ViewLayer", "use_pass_normal") in pruned, "payload includes use_pass_normal")
    check(all(prop != "use_pass_combined" for _n, prop in pruned),
          "Combined is never pruned")

    rlayer = Obj(
        type="R_LAYERS", layer="ViewLayer", inputs=(),
        outputs=[Obj(name="Depth", is_linked=True),
                 Obj(name="Image", is_linked=True),
                 Obj(name="Normal", is_linked=False)])
    scene = _scene()
    scene.use_nodes = True
    scene.node_tree = Obj(nodes=[rlayer])
    scene.view_layers = [Obj(
        name="ViewLayer", use_pass_z=True, use_pass_normal=True,
        use_pass_object_index=False, use_pass_combined=True,
        use_pass_mist=False, use_pass_uv=False, use_pass_vector=False,
        use_pass_material_index=False, use_pass_diffuse_direct=False,
        use_pass_diffuse_indirect=False, use_pass_diffuse_color=False,
        use_pass_glossy_direct=False, use_pass_glossy_indirect=False,
        use_pass_glossy_color=False, use_pass_transmission_direct=False,
        use_pass_transmission_indirect=False, use_pass_transmission_color=False,
        use_pass_emit=False, use_pass_environment=False, use_pass_shadow=False,
        use_pass_ambient_occlusion=False, use_pass_volume_direct=False,
        use_pass_volume_indirect=False, use_pass_position=False)]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    hits = [a for a in plan.actions if a.kind == "PASS_PRUNE"]
    check(len(hits) == 1, "unlinked Normal is pruned when Depth is used")
    pruned = hits[0].payload.get("passes") or []
    check(("ViewLayer", "use_pass_z") not in pruned, "linked Depth is kept")
    check(("ViewLayer", "use_pass_normal") in pruned, "unlinked Normal is pruned")

    scene = _scene()
    scene.use_nodes = True
    scene.node_tree = Obj(nodes=[Obj(type="GROUP", node_tree=None, outputs=(), inputs=())])
    scene.view_layers = [Obj(
        name="ViewLayer", use_pass_z=True, use_pass_normal=False,
        use_pass_object_index=False, use_pass_combined=True,
        use_pass_mist=False, use_pass_uv=False, use_pass_vector=False,
        use_pass_material_index=False, use_pass_diffuse_direct=False,
        use_pass_diffuse_indirect=False, use_pass_diffuse_color=False,
        use_pass_glossy_direct=False, use_pass_glossy_indirect=False,
        use_pass_glossy_color=False, use_pass_transmission_direct=False,
        use_pass_transmission_indirect=False, use_pass_transmission_color=False,
        use_pass_emit=False, use_pass_environment=False, use_pass_shadow=False,
        use_pass_ambient_occlusion=False, use_pass_volume_direct=False,
        use_pass_volume_indirect=False, use_pass_position=False)]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "PASS_PRUNE" for a in plan.actions),
          "unwalkable GROUP → no PASS_PRUNE (not proven)")


def _glass_mat(name, types, library=None, blend="OPAQUE"):
    return Obj(
        name=name,
        library=library,
        blend_method=blend,
        node_tree=Obj(nodes=[Obj(type=t, inputs=Obj(get=lambda *_: None)) for t in types]),
    )


def test_transparent_shadow_cap_proven_only():
    section("transparent shadow cap is proven alpha/glass only")
    scene = _scene()
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "TRANSPARENT_SHADOW_CAP" for a in plan.actions),
          "default scene → no TRANSPARENT_SHADOW_CAP")
    scene = _scene()
    scene.objects = [_mesh("Blind", material_slots=[
        Obj(material=_glass_mat("Leaf", ["BSDF_TRANSPARENT"]))])]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    hits = [a for a in plan.actions if a.kind == "TRANSPARENT_SHADOW_CAP"]
    check(len(hits) == 1, "BSDF_TRANSPARENT + 8 bounces → TRANSPARENT_SHADOW_CAP")
    check(hits[0].payload.get("value") == 4, "payload value 4")
    check(abs(hits[0].time_factor - 0.92) < 1e-9, "factor 0.92")
    scene = _scene(transparent_max_bounces=4)
    scene.objects = [_mesh("Blind", material_slots=[
        Obj(material=_glass_mat("Leaf", ["BSDF_TRANSPARENT"]))])]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "TRANSPARENT_SHADOW_CAP" for a in plan.actions),
          "already 4 → no write")
    scene = _scene(transparent_max_bounces=2)
    scene.objects = [_mesh("Blind", material_slots=[
        Obj(material=_glass_mat("Leaf", ["BSDF_TRANSPARENT"]))])]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "TRANSPARENT_SHADOW_CAP" for a in plan.actions),
          "user 2 is not raised")
    scene = _scene()
    scene.objects = [_mesh("Pane", material_slots=[
        Obj(material=_glass_mat("Glass", ["BSDF_GLASS"]))])]
    pane = scene.objects[0]
    pane.scenequant = Obj(override="HERO")
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "TRANSPARENT_SHADOW_CAP" for a in plan.actions),
          "HERO glass → no TRANSPARENT_SHADOW_CAP")
    scene = _scene()
    scene.objects = [_mesh("GroupGlass", material_slots=[
        Obj(material=_glass_mat("G", ["GROUP"]))])]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "TRANSPARENT_SHADOW_CAP" for a in plan.actions),
          "GROUP tree → no TRANSPARENT_SHADOW_CAP (not proven)")
    scene = _scene()
    scene.objects = [_mesh("Card", material_slots=[
        Obj(material=_glass_mat("AlphaCard", [], blend="HASHED"))])]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(any(a.kind == "TRANSPARENT_SHADOW_CAP" for a in plan.actions),
          "HASHED blend_method → TRANSPARENT_SHADOW_CAP")
    scene = _scene()
    scene.objects = [_mesh("Pane",
        cycles=Obj(is_caustics_caster=True),
        material_slots=[Obj(material=_glass_mat("Glass", ["BSDF_GLASS"]))])]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "TRANSPARENT_SHADOW_CAP" for a in plan.actions),
          "MNEE caster → no TRANSPARENT_SHADOW_CAP")


def _alpha_cutout_mat(name, blend="HASHED", library=None, already=False):
    alpha = Obj(default_value=1.0, is_linked=True)
    trans = Obj(default_value=0.0, is_linked=False)
    node = Obj(
        type="BSDF_PRINCIPLED",
        inputs=_GetMap({
            "Alpha": alpha,
            "Transmission Weight": trans,
            "Transmission": trans,
        }),
    )
    return Obj(
        name=name, library=library, blend_method=blend,
        use_transparent_shadow=(not already),
        node_tree=Obj(nodes=[node]),
    )


def _mix_cutout_mat(name, fac_linked=True, blend="HASHED", library=None):
    mix = Obj(type="MIX_SHADER", inputs=_GetMap({
        "Fac": Obj(default_value=0.5, is_linked=fac_linked),
    }))
    return Obj(
        name=name, library=library, blend_method=blend,
        use_transparent_shadow=True,
        node_tree=Obj(nodes=[
            Obj(type="BSDF_DIFFUSE"),
            Obj(type="BSDF_TRANSPARENT"),
            mix,
            Obj(type="TEX_IMAGE"),
            Obj(type="OUTPUT_MATERIAL"),
        ]),
    )


def test_opaque_cutout_shadows_proven_only():
    section("opaque cutout shadows need proven alpha, not HASHED-only")
    scene = _scene()
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "OPAQUE_CUTOUT_SHADOWS" for a in plan.actions),
          "default scene → no OPAQUE_CUTOUT_SHADOWS")

    scene = _scene()
    scene.objects = [_mesh("Card", material_slots=[
        Obj(material=_alpha_cutout_mat("Leaf"))])]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    hits = [a for a in plan.actions if a.kind == "OPAQUE_CUTOUT_SHADOWS"]
    check(len(hits) == 1, "HASHED + principled Alpha linked → OPAQUE_CUTOUT_SHADOWS")
    check("Leaf" in (hits[0].payload.get("materials") or []),
          "payload materials includes Leaf")
    check(abs(hits[0].time_factor - 0.90) < 1e-9, "time_factor 0.90")

    scene = _scene()
    scene.objects = [_mesh("Card", material_slots=[
        Obj(material=_mix_cutout_mat("Wire"))])]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    hits = [a for a in plan.actions if a.kind == "OPAQUE_CUTOUT_SHADOWS"]
    check(len(hits) == 1, "HASHED Mix(Diffuse, Transparent) + linked Fac → lever")
    check("Wire" in (hits[0].payload.get("materials") or []),
          "payload materials includes Wire")

    scene = _scene()
    scene.objects = [_mesh("Card", material_slots=[
        Obj(material=_mix_cutout_mat("UnlinkedMix", fac_linked=False))])]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "OPAQUE_CUTOUT_SHADOWS" for a in plan.actions),
          "Mix Fac unlinked → not a proven cutout")

    scene = _scene()
    scene.objects = [_mesh("Wall", material_slots=[
        Obj(material=_glass_mat("BeigeWall", ["BSDF_DIFFUSE"], blend="HASHED"))])]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "OPAQUE_CUTOUT_SHADOWS" for a in plan.actions),
          "HASHED opaque paint (Classroom leftover) → no lever")

    scene = _scene()
    scene.objects = [_mesh("Card", material_slots=[
        Obj(material=_glass_mat("EmptyCard", [], blend="HASHED"))])]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "OPAQUE_CUTOUT_SHADOWS" for a in plan.actions),
          "HASHED empty tree → no lever")

    scene = _scene()
    scene.objects = [_mesh("Pane", material_slots=[
        Obj(material=_glass_mat("Window", ["BSDF_TRANSPARENT"], blend="HASHED"))])]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "OPAQUE_CUTOUT_SHADOWS" for a in plan.actions),
          "Transparent-only window → no opaque-shadow lever")

    scene = _scene()
    scene.objects = [_mesh("Portal", material_slots=[
        Obj(material=Obj(
            name="dayLight_portal", library=None, blend_method="HASHED",
            use_transparent_shadow=True,
            node_tree=Obj(nodes=[
                Obj(type="BSDF_TRANSPARENT"),
                Obj(type="EMISSION"),
                Obj(type="MIX_SHADER", inputs=_GetMap({
                    "Fac": Obj(is_linked=True)})),
                Obj(type="TEX_SKY"),
            ])))])]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "OPAQUE_CUTOUT_SHADOWS" for a in plan.actions),
          "emission+transparent portal → no lever")

    scene = _scene()
    scene.objects = [_mesh("Solid", material_slots=[
        Obj(material=_alpha_cutout_mat("Paint", blend="OPAQUE"))])]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "OPAQUE_CUTOUT_SHADOWS" for a in plan.actions),
          "OPAQUE blend → no OPAQUE_CUTOUT_SHADOWS")

    scene = _scene()
    scene.objects = [_mesh("Pane", material_slots=[
        Obj(material=_glass_mat("GlassHash", ["BSDF_GLASS"], blend="HASHED"))])]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "OPAQUE_CUTOUT_SHADOWS" for a in plan.actions),
          "HASHED + BSDF_GLASS → no OPAQUE_CUTOUT_SHADOWS")

    already = _alpha_cutout_mat("DoneCard", already=True)
    scene = _scene()
    scene.objects = [_mesh("Card", material_slots=[Obj(material=already)])]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "OPAQUE_CUTOUT_SHADOWS" for a in plan.actions),
          "already use_transparent_shadow False → no")

    scene = _scene()
    scene.objects = [_mesh("Card", material_slots=[
        Obj(material=_alpha_cutout_mat("LibLeaf", library="Lib"))])]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "OPAQUE_CUTOUT_SHADOWS" for a in plan.actions),
          "linked proven cutout → no OPAQUE_CUTOUT_SHADOWS")
    check(any("linked" in c for c in plan.caveats),
          "linked cutout skip is a caveat, not silent")

    scene = _scene()
    scene.objects = [_mesh("HeroCard",
        scenequant=Obj(override="HERO"),
        material_slots=[Obj(material=_alpha_cutout_mat("HeroLeaf"))])]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "OPAQUE_CUTOUT_SHADOWS" for a in plan.actions),
          "HERO proven cutout → no OPAQUE_CUTOUT_SHADOWS")

    shared = _alpha_cutout_mat("SharedLeaf")
    scene = _scene()
    scene.objects = [
        _mesh("HeroCard", scenequant=Obj(override="HERO"),
              material_slots=[Obj(material=shared)]),
        _mesh("ExtraCard", material_slots=[Obj(material=shared)]),
    ]
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "OPAQUE_CUTOUT_SHADOWS" for a in plan.actions),
          "proven cutout shared with HERO → no OPAQUE_CUTOUT_SHADOWS")

    scene = _scene()
    objs = []
    for i in range(65):
        mat = _alpha_cutout_mat("Cut%d" % i)
        objs.append(_mesh("Card%d" % i, material_slots=[Obj(material=mat)]))
    scene.objects = objs
    plan = speed_solver.build_speed_plan(scene, {}, _mem(), _settings())
    check(all(a.kind != "OPAQUE_CUTOUT_SHADOWS" for a in plan.actions),
          "65 unique proven cutouts → no OPAQUE_CUTOUT_SHADOWS")
    check(any("too many cutout materials" in c for c in plan.caveats),
          "over-count cutouts caveats too many")


def main():
    test_independence()
    test_default_plan_filters()
    test_never_raise_samples()
    test_already_fast()
    test_light_tree_product_shot()
    test_persistent_session_bvh()
    test_transparent_shadow_cap_proven_only()
    test_honest_estimate_gated_noops()
    test_micro_emitters_strict()
    test_linked_offscreen_is_loud()
    test_linked_cull_is_loud()
    test_hero_tiny_not_camera_culled()
    test_denoise_prefilter_accurate_only()
    test_world_mis_solid_only()
    test_volume_bounces_zero()
    test_homogeneous_volume_proven_only()
    test_hide_offscreen_instances()
    test_pass_prune_unused_only()
    test_light_sampling_threshold_disabled_only()
    test_offscreen_dicing_adaptive_only()
    test_opaque_cutout_shadows_proven_only()
    finish()


main()
