# Speed plan builder. Pure planning: reads the scene and datablocks, NEVER
# writes and never touches the journal. bpy is imported lazily so the
# independence / factor math is unit-testable with duck-typed fakes (and
# without Blender on sys.path).
#
# Independence: every qualifying tier-0/1 action is kept (apply them all),
# but est_factor multiplies only the strongest time_factor per waste_class
# so complementary writes are not double-counted.

from dataclasses import dataclass, field, asdict

WASTE_CLASSES = ("device", "rebuild", "samples", "paths", "dead", "variance")
DEFAULT_TIER_MAX = 1
# Never in the default Make it Fast plan (VRAM / draft / opt-in).
FORBIDDEN_KINDS = {
    "QUANTIZE", "TEX_LIMIT", "DEDUP", "HALF_FLOAT", "DRAFT",
    "PARANOID_CULL",
}
# TIER_PERCEPTUAL props that belong to the paths class. Adaptive / samples /
# light_tree / scrambling / filter-glossy are handled as their own levers
# (research: light tree is NOT always-on). FILTER_GLOSSY owns blur_glossy
# (analysis-gated). AUTO_SCRAMBLE owns auto_scrambling_distance (GPU).
PATH_PROP_NAMES = (
    "sample_clamp_indirect",
    "max_bounces", "diffuse_bounces", "glossy_bounces",
    "transmission_bounces", "transparent_max_bounces",
)
PATH_ENTRIES = (
    ("cycles", "sample_clamp_indirect", 5.0, "min"),
    ("cycles", "max_bounces", 8, "min"),
    ("cycles", "diffuse_bounces", 3, "min"),
    ("cycles", "glossy_bounces", 4, "min"),
    ("cycles", "transmission_bounces", 6, "min"),
    ("cycles", "transparent_max_bounces", 8, "min"),
)
FILTER_GLOSSY_VALUE = 1.0
SAMPLES_CAP = 1024
SAMPLES_FLOOR = 256          # never propose lowering below this
THRESHOLD_CAP = 0.015        # MODE_MAX cheap-floor; do not go to 0.03
LIGHT_SAMPLING_THRESHOLD = 0.01  # Cycles factory; 0 means disabled
OFFSCREEN_DICING_SCALE = 8.0     # coarsens adaptive dicing outside the camera
TINY_COVERAGE = 0.01         # micro-emitters / scatter cull
SUBDIV_COVERAGE = 0.05
NEAR_CURVES_COVERAGE = 0.15
SIMPLE_LIGHT_TYPES = {"POINT", "SUN", "SPOT", "AREA"}
DEFORM_MODS = {
    "ARMATURE", "LATTICE", "MESH_DEFORM", "SURFACE_DEFORM", "WARP", "CAST",
    "SIMPLE_DEFORM", "LAPLACIANDEFORM", "HOOK", "CORRECTIVE_SMOOTH",
}
CRYPTO_NODE_TYPES = {"CRYPTOMATTE", "CRYPTOMATTE_V2"}
CRYPTO_PASS_PROPS = (
    "use_pass_cryptomatte_object",
    "use_pass_cryptomatte_material",
    "use_pass_cryptomatte_asset",
)
# R_LAYERS socket name → ViewLayer RNA. Combined/Image/Alpha are never pruned.
PASS_SOCKET_TO_PROP = {
    "Depth": "use_pass_z",
    "Mist": "use_pass_mist",
    "Normal": "use_pass_normal",
    "UV": "use_pass_uv",
    "Vector": "use_pass_vector",
    "IndexOB": "use_pass_object_index",
    "IndexMA": "use_pass_material_index",
    "DiffDir": "use_pass_diffuse_direct",
    "DiffInd": "use_pass_diffuse_indirect",
    "DiffCol": "use_pass_diffuse_color",
    "GlossDir": "use_pass_glossy_direct",
    "GlossInd": "use_pass_glossy_indirect",
    "GlossCol": "use_pass_glossy_color",
    "TransDir": "use_pass_transmission_direct",
    "TransInd": "use_pass_transmission_indirect",
    "TransCol": "use_pass_transmission_color",
    "Emit": "use_pass_emit",
    "Env": "use_pass_environment",
    "Shadow": "use_pass_shadow",
    "AO": "use_pass_ambient_occlusion",
    "VolumeDir": "use_pass_volume_direct",
    "VolumeInd": "use_pass_volume_indirect",
    "Position": "use_pass_position",
}
WORLD_SOLID_BLOCKERS = {
    "TEX_ENVIRONMENT", "TEX_SKY", "TEX_IMAGE", "TEX_NOISE", "TEX_WAVE",
    "TEX_MUSGRAVE", "TEX_VORONOI", "TEX_MAGIC", "TEX_GRADIENT",
    "TEX_CHECKER", "TEX_BRICK", "TEX_WHITE_NOISE", "GROUP",
    "PRINCIPLED_VOLUME", "VOLUME_SCATTER", "VOLUME_ABSORPTION",
}
VOLUME_NODE_TYPES = {
    "PRINCIPLED_VOLUME", "VOLUME_SCATTER", "VOLUME_ABSORPTION", "GROUP",
}
VOLUME_PROVEN = {
    "PRINCIPLED_VOLUME", "VOLUME_SCATTER", "VOLUME_ABSORPTION",
}
VOLUME_VARYING_BLOCKERS = {
    "GROUP",
    "TEX_ENVIRONMENT", "TEX_SKY", "TEX_IMAGE", "TEX_NOISE", "TEX_WAVE",
    "TEX_MUSGRAVE", "TEX_VORONOI", "TEX_MAGIC", "TEX_GRADIENT",
    "TEX_CHECKER", "TEX_BRICK", "TEX_WHITE_NOISE",
    "TEX_COORD", "ATTRIBUTE",
}
ALREADY_FAST_CAVEAT = (
    "scene already at the sample knee / no dead work — low-double-digit gains only"
)
_MISSING = object()


@dataclass
class SpeedAction:
    kind: str
    label: str
    waste_class: str
    tier: int
    time_factor: float          # remaining-time multiplier in (0, 1]
    visual_cost: int = 0        # 0 free ... 3 noticeable
    payload: dict = field(default_factory=dict)


@dataclass
class SpeedPlan:
    actions: list
    est_factor: float
    est_pct: float              # remaining time as a percent (est_factor * 100)
    caveats: list = field(default_factory=list)
    applied_classes: list = field(default_factory=list)


def strongest_per_class(actions):
    """Keep the lowest time_factor (strongest lever) in each waste_class.

    First-seen order of classes is preserved so the estimate is stable.
    """
    winners = {}
    order = []
    for action in actions:
        key = action.waste_class
        prev = winners.get(key)
        if prev is None:
            winners[key] = action
            order.append(key)
        elif action.time_factor < prev.time_factor:
            winners[key] = action
    return [winners[key] for key in order]


def multiply_factors(actions):
    """Product of time_factors. Empty -> 1.0 (honest: nothing claimed)."""
    factor = 1.0
    for action in actions:
        value = float(action.time_factor)
        if value <= 0.0:
            continue
        factor *= min(value, 1.0)
    return factor


def plan_to_dict(plan):
    return {
        "actions": [asdict(action) for action in plan.actions],
        "est_factor": plan.est_factor,
        "est_pct": plan.est_pct,
        "caveats": list(plan.caveats),
        "applied_classes": list(plan.applied_classes),
    }


def build_speed_plan(scene, coverage, mem, settings, findings=None):
    """Default Make it Fast plan: tiers 0+1 only, class-deduped estimate."""
    caveats = []
    actions = []
    actions.extend(_device_actions(scene, caveats))
    actions.extend(_rebuild_actions(scene, mem, settings, caveats))
    actions.extend(_sample_actions(scene, caveats))
    actions.extend(_path_actions(scene, caveats))
    actions.extend(_dead_actions(scene, coverage or {}, caveats))
    actions.extend(_variance_actions(scene, settings, caveats))

    default = [a for a in actions
               if a.tier <= DEFAULT_TIER_MAX and a.kind not in FORBIDDEN_KINDS]
    if not default:
        caveats.append(ALREADY_FAST_CAVEAT)
        return SpeedPlan([], 1.0, 100.0, caveats, [])

    winners = strongest_per_class(default)
    factor = multiply_factors(winners)
    return SpeedPlan(
        actions=default,
        est_factor=factor,
        est_pct=factor * 100.0,
        caveats=caveats,
        applied_classes=[a.waste_class for a in winners],
    )


# ------------------------------------------------------------------ device

def _device_actions(scene, caveats):
    cycles = _cycles(scene)
    if cycles is None:
        return []
    device = getattr(cycles, "device", "GPU")
    if device not in ("CPU", "NONE", None):
        return []
    device_type, backends = _gpu_backends()
    # Potential only when we cannot prove a GPU exists: empty payload so
    # apply will not invent a prefs write, factor is conservative.
    payload = {}
    if backends and device_type not in (None, "NONE"):
        payload = {"set_device": True}
        label = "Switch this scene to GPU Compute"
    else:
        caveats.append(
            "switch Cycles to GPU in Preferences > System > Cycles Render "
            "Devices, then set Render Properties > Device to GPU Compute")
        label = "Cycles is on CPU — GPU would be much faster (Preferences)"
    return [SpeedAction(
        "DEVICE_GPU", label, "device", 0, 0.4, 0, payload)]


def _gpu_backends():
    try:
        from ..analysis import audit
        return audit._cycles_gpu_backends()
    except Exception:
        return None, ()


# ----------------------------------------------------------------- rebuild

def _rebuild_actions(scene, mem, settings, caveats):
    actions = []
    rend = getattr(scene, "render", None)
    if rend is not None and not getattr(rend, "use_persistent_data", False):
        # First F12 still pays the BVH. The next F12 on a weak GPU does not.
        # Apply stays VRAM-headroom gated so an 8 GB box cannot OOM.
        anim = _is_anim(scene)
        if anim:
            factor = 0.55 if _budget_known(settings) else 1.0
            label = "Persistent Data (animation; VRAM-headroom gated)"
        else:
            factor = 1.0
            label = "Persistent Data (next F12 keeps the BVH; VRAM-headroom gated)"
            caveats.append(
                "persistent data does not speed the first F12")
        actions.append(SpeedAction(
            "PERSISTENT_DATA", label, "rebuild", 0, factor, 0, {}))
        if anim and factor >= 1.0:
            caveats.append(
                "estimate ignores VRAM-gated levers (budget unset)")
    if rend is not None and not getattr(rend, "use_lock_interface", False):
        actions.append(SpeedAction(
            "LOCK_INTERFACE", "Lock interface during render",
            "rebuild", 0, 0.97, 0, {}))
    if _is_anim(scene):
        cycles = _cycles(scene)
        if cycles is not None and not getattr(cycles, "use_animated_seed", False):
            if _has_attr(cycles, "use_animated_seed"):
                actions.append(SpeedAction(
                    "ANIMATED_SEED", "Animated seed (animation flicker)",
                    "rebuild", 0, 1.0, 0, {}))
    actions.extend(_deform_mblur_actions(scene))
    return actions


def _deform_mblur_actions(scene):
    rend = getattr(scene, "render", None)
    if rend is None or not getattr(rend, "use_motion_blur", False):
        return []
    names = []
    for obj in _iter_objects(scene):
        if getattr(obj, "hide_render", False) or _protected(obj):
            continue
        oc = getattr(obj, "cycles", None)
        if oc is None or not getattr(oc, "use_deform_motion", False):
            continue
        if _has_deform(obj):
            continue
        names.append(getattr(obj, "name", ""))
    names = [n for n in names if n]
    if not names:
        return []
    factor = 0.88 if _is_anim(scene) else 0.95
    return [SpeedAction(
        "DEFORM_MBLUR_OFF",
        "%d static mesh(es) → deform motion blur off" % len(names),
        "rebuild", 0, factor, 0, {"objects": names})]


# ----------------------------------------------------------------- samples

def _sample_actions(scene, caveats):
    cycles = _cycles(scene)
    if cycles is None:
        return []
    actions = []
    if not getattr(cycles, "use_adaptive_sampling", True):
        actions.append(SpeedAction(
            "ADAPTIVE_ON", "Adaptive sampling on",
            "samples", 1, 0.55, 0, {}))
    threshold = getattr(cycles, "adaptive_threshold", 0.0)
    if isinstance(threshold, (int, float)) and 0.0 < threshold < THRESHOLD_CAP:
        actions.append(SpeedAction(
            "THRESHOLD_CAP",
            "Adaptive threshold floor 0.015 (never loosens a cheaper value)",
            "samples", 1, 0.85, 1,
            {"value": THRESHOLD_CAP}))
    samples = getattr(cycles, "samples", 0)
    # Ceiling for adaptive, not a target. Never lower a budget under 256;
    # MODE_MIN 1024 only fires when current is above the cap.
    if isinstance(samples, (int, float)) and samples > SAMPLES_CAP and samples >= SAMPLES_FLOOR:
        factor = 0.70 if samples > 2048 else 0.85
        actions.append(SpeedAction(
            "SAMPLES_CAP",
            "Sample ceiling %d (currently %d)" % (SAMPLES_CAP, int(samples)),
            "samples", 1, factor, 1,
            {"value": SAMPLES_CAP}))
    if not getattr(cycles, "use_denoising", False):
        # OIDN at the same spp is quality, often a time tax. Credit 0.80
        # only when a sample-count write is also in this plan.
        samples_drop = (
            isinstance(samples, (int, float))
            and samples > SAMPLES_CAP
            and samples >= SAMPLES_FLOOR
        )
        actions.append(SpeedAction(
            "DENOISE_ON", "OIDN denoising on",
            "samples", 1, 0.80 if samples_drop else 1.0, 1, {}))
    target = _min_samples_target(scene)
    current_min = getattr(cycles, "adaptive_min_samples", 0)
    if _has_attr(cycles, "adaptive_min_samples"):
        if not isinstance(current_min, (int, float)) or current_min < target:
            actions.append(SpeedAction(
                "MIN_SAMPLES",
                "Adaptive min samples %d (stops blotching in dark areas)" % target,
                "samples", 1, 1.0, 0,
                {"value": target}))
    actions.extend(_auto_scramble_actions(scene))
    caveats.append(
        "Sample knee: Make it Fast probes a cheap ladder and caps "
        "samples at the proven floor — it does not guess a count")
    return actions


def _min_samples_target(scene):
    """32 outdoor / 48 typical / 96 interiors+metals. Leaving 0 blotches."""
    cycles = _cycles(scene)
    bounces = getattr(cycles, "max_bounces", 8) if cycles is not None else 8
    if isinstance(bounces, (int, float)) and bounces > 8:
        return 96
    sun = 0
    other = 0
    for obj in _iter_objects(scene):
        if getattr(obj, "type", "") != "LIGHT" or getattr(obj, "hide_render", False):
            continue
        ltype = getattr(getattr(obj, "data", None), "type", "")
        if ltype == "SUN":
            sun += 1
        else:
            other += 1
    if sun and other == 0:
        return 32
    return 48


# ------------------------------------------------------------------- paths

def _path_actions(scene, caveats):
    cycles = _cycles(scene)
    if cycles is None:
        return []
    actions = []
    if any(_entry_would_fire(scene, *entry) for entry in PATH_ENTRIES):
        overworked = _paths_overworked(scene)
        actions.append(SpeedAction(
            "APPLY_PERCEPTUAL_PATHS",
            "Bounce / clamp (perceptual, never raises user caps)",
            "paths", 1, 0.75 if overworked else 0.90, 1, {}))
    actions.extend(_light_tree_actions(scene))
    actions.extend(_caustics_actions(scene))
    if getattr(cycles, "use_guiding", False) and getattr(cycles, "device", "GPU") != "CPU":
        # Path guiding is CPU-only; leaving it on with GPU is wasted work.
        actions.append(SpeedAction(
            "PATH_GUIDING_OFF", "Path guiding off (CPU-only; no-op on GPU)",
            "paths", 0, 1.0, 0, {}))
    actions.extend(_world_mis_actions(scene, caveats))
    actions.extend(_volume_bounces_actions(scene, caveats))
    actions.extend(_homogeneous_volume_actions(scene, caveats))
    actions.extend(_light_sampling_actions(scene))
    actions.extend(_transparent_shadow_actions(scene, caveats))
    actions.extend(_filter_glossy_actions(scene, caveats))
    return actions


def _paths_overworked(scene):
    cycles = _cycles(scene)
    if cycles is None:
        return False
    if getattr(cycles, "max_bounces", 0) > 8:
        return True
    if getattr(cycles, "samples", 0) > SAMPLES_CAP:
        return True
    return False


def _light_sampling_actions(scene):
    """Enable factory 0.01 only when the threshold is left disabled (0)."""
    cycles = _cycles(scene)
    if cycles is None or not _has_attr(cycles, "light_sampling_threshold"):
        return []
    current = getattr(cycles, "light_sampling_threshold", None)
    if not isinstance(current, (int, float)) or current != 0:
        return []
    return [SpeedAction(
        "LIGHT_SAMPLING_THRESHOLD",
        "Light sampling threshold 0.01 (was disabled)",
        "paths", 1, 0.94, 1,
        {"value": LIGHT_SAMPLING_THRESHOLD})]


def _world_mis_actions(scene, caveats):
    world = getattr(scene, "world", None)
    if world is None:
        return []
    wcycles = getattr(world, "cycles", None)
    if wcycles is None or not _has_attr(wcycles, "sampling_method"):
        return []
    current = getattr(wcycles, "sampling_method", None)
    if current == "NONE":
        return []
    if _is_linked(world):
        caveats.append("world MIS not changed (linked world)")
        return []
    if not _world_is_solid(world):
        return []
    return [SpeedAction(
        "WORLD_MIS_NONE",
        "World MIS off (solid background — skip env sampling)",
        "paths", 0, 0.95, 0, {})]


def _world_is_solid(world):
    if not getattr(world, "use_nodes", False):
        return True
    tree = getattr(world, "node_tree", None)
    if tree is None:
        return True
    return not _tree_has_types(tree, WORLD_SOLID_BLOCKERS)


def _volume_bounces_actions(scene, caveats):
    cycles = _cycles(scene)
    if cycles is None or not _has_attr(cycles, "volume_bounces"):
        return []
    current = getattr(cycles, "volume_bounces", 0)
    if not isinstance(current, (int, float)) or current <= 0:
        return []
    if _scene_has_volume(scene):
        return []
    factor = 0.97 if current <= 4 else 0.90
    return [SpeedAction(
        "VOLUME_BOUNCES_ZERO",
        "Volume bounces 0 (no volumes in scene)",
        "paths", 1, factor, 0, {"value": 0})]


def _scene_has_volume(scene):
    for obj in _iter_objects(scene):
        if getattr(obj, "hide_render", False):
            continue
        if getattr(obj, "type", "") == "VOLUME":
            return True
        for slot in getattr(obj, "material_slots", ()) or ():
            mat = getattr(slot, "material", None)
            if mat is None:
                continue
            tree = getattr(mat, "node_tree", None)
            if _tree_has_types(tree, VOLUME_NODE_TYPES):
                return True
    world = getattr(scene, "world", None)
    if world is not None:
        tree = getattr(world, "node_tree", None)
        if _tree_has_types(tree, VOLUME_NODE_TYPES):
            return True
    return False


def _tree_has_types(tree, types):
    if tree is None:
        return False
    for node in getattr(tree, "nodes", ()) or ():
        if getattr(node, "type", "") in types:
            return True
    return False




def _volume_tree_is_homogeneous(tree):
    if tree is None:
        return False
    if not _tree_has_types(tree, VOLUME_PROVEN):
        return False
    if _tree_has_types(tree, VOLUME_VARYING_BLOCKERS):
        return False
    return True


def _homogeneous_volume_actions(scene, caveats):
    materials = []
    linked_skipped = 0
    for obj in _iter_objects(scene):
        if getattr(obj, "hide_render", False) or _protected(obj):
            continue
        for slot in getattr(obj, "material_slots", ()) or ():
            mat = getattr(slot, "material", None)
            if mat is None:
                continue
            mat_name = getattr(mat, "name", None)
            if mat_name and mat_name in materials:
                continue
            if _is_linked(mat):
                linked_skipped += 1
                continue
            mcycles = getattr(mat, "cycles", None)
            if not _has_attr(mcycles, "homogeneous_volume"):
                continue
            if getattr(mcycles, "homogeneous_volume", False):
                continue
            if not _volume_tree_is_homogeneous(getattr(mat, "node_tree", None)):
                continue
            if mat_name:
                materials.append(mat_name)
    world_flag = False
    world = getattr(scene, "world", None)
    if world is not None and not _is_linked(world):
        wcycles = getattr(world, "cycles", None)
        if (_has_attr(wcycles, "homogeneous_volume")
                and not getattr(wcycles, "homogeneous_volume", False)
                and _volume_tree_is_homogeneous(
                    getattr(world, "node_tree", None))):
            world_flag = True
    if linked_skipped:
        caveats.append(
            "%d volume material(s) not marked homogeneous (linked)"
            % linked_skipped)
    if not materials and not world_flag:
        return []
    count = len(materials) + (1 if world_flag else 0)
    return [SpeedAction(
        "HOMOGENEOUS_VOLUME",
        "%d volume material(s) → homogeneous (no textures)" % count,
        "paths", 1, 0.92, 0,
        {"materials": materials, "world": world_flag})]


def _light_tree_actions(scene):
    cycles = _cycles(scene)
    if cycles is None or not _has_attr(cycles, "use_light_tree"):
        return []
    n_simple, n_mesh, linking = _light_stats(scene)
    current = getattr(cycles, "use_light_tree", True)
    # ≤4 simple lights, no mesh lights, no linking: tree overhead loses.
    if n_simple <= 4 and n_mesh == 0 and not linking:
        if current:
            return [SpeedAction(
                "LIGHT_TREE",
                "Light tree off (%d simple lights, no mesh lights)" % n_simple,
                "paths", 1, 0.90, 0, {"enabled": False})]
        return []
    # ≥16 lights or any linking / mesh lights: force the tree on.
    if n_simple + n_mesh >= 16 or linking or n_mesh:
        if not current:
            return [SpeedAction(
                "LIGHT_TREE",
                "Light tree on (%d lights%s)" % (
                    n_simple + n_mesh, ", linking" if linking else ""),
                "paths", 0, 0.92, 0, {"enabled": True})]
        return []
    return []


def _light_stats(scene):
    n_simple = 0
    n_mesh = 0
    linking = False
    for obj in _iter_objects(scene):
        if getattr(obj, "hide_render", False):
            continue
        linking = linking or _has_light_linking(obj)
        if getattr(obj, "type", "") == "LIGHT":
            ltype = getattr(getattr(obj, "data", None), "type", "POINT")
            if ltype in SIMPLE_LIGHT_TYPES:
                n_simple += 1
            continue
        if _is_emissive(obj):
            n_mesh += 1
    return n_simple, n_mesh, linking


def _has_light_linking(obj):
    ll = getattr(obj, "light_linking", None)
    if ll is None:
        return False
    return bool(getattr(ll, "receiver_collection", None)
                or getattr(ll, "blocker_collection", None))


def _caustics_actions(scene):
    cycles = _cycles(scene)
    if cycles is None:
        return []
    refl = getattr(cycles, "caustics_reflective", False)
    refr = getattr(cycles, "caustics_refractive", False)
    if not refl and not refr:
        return []
    if _needs_caustics(scene):
        return []
    return [SpeedAction(
        "CAUSTICS_OFF",
        "Caustics off (no MNEE caster/receiver, no hero glass)",
        "paths", 1, 0.92, 1, {})]


def _needs_caustics(scene):
    for obj in _iter_objects(scene):
        if getattr(obj, "hide_render", False):
            continue
        oc = getattr(obj, "cycles", None)
        if oc is not None:
            if getattr(oc, "is_caustics_caster", False):
                return True
            if getattr(oc, "is_caustics_receiver", False):
                return True
            if getattr(oc, "is_caustics_light", False):
                return True
        data_c = getattr(getattr(obj, "data", None), "cycles", None)
        if data_c is not None and getattr(data_c, "is_caustics_light", False):
            return True
        if _protected(obj) and _looks_glass(obj):
            return True
    return False


# -------------------------------------------------------------------- dead

def _dead_actions(scene, coverage, caveats):
    actions = []
    actions.extend(_trim_actions(scene, coverage, caveats))
    actions.extend(_instance_hide_actions(scene, coverage, caveats))
    actions.extend(_subdiv_actions(scene, coverage, caveats))
    actions.extend(_adaptive_subdiv_actions(scene))
    actions.extend(_offscreen_dicing_actions(scene))
    actions.extend(_micro_emitter_actions(scene, coverage, caveats))
    actions.extend(_camera_cull_actions(scene, coverage, caveats))
    actions.extend(_hair_ribbon_actions(scene, coverage))
    actions.extend(_crypto_actions(scene))
    actions.extend(_pass_prune_actions(scene))
    actions.extend(_opaque_cutout_shadow_actions(scene, caveats))
    # DEAD_CLOSURE_PRUNE lives in dead_closure_prune_actions (manual-later).
    # Not in the default Auto plan until official Classroom/loft inventory
    # proves PRUNE_ALPHA + PRUNE_VOLUME >= 1. No time claim.
    # UNUSED_SLOTS lives in unused_slots_actions (manual-later).
    # Not in the default Auto plan until a measured loft pair exists.
    # No time claim. Not a Cycles RNA knob.
    return actions


def _trim_actions(scene, coverage, caveats):
    if not coverage:
        return []
    names = []
    linked_skipped = 0
    for name, info in _sorted_coverage(coverage):
        if _cov_attr(info, "near_frustum_ever",
                     _cov_attr(info, "in_frustum_ever", True)):
            continue
        obj = _get_object(scene, name)
        if obj is None or getattr(obj, "hide_render", False):
            continue
        if getattr(obj, "type", "") != "MESH" or _protected(obj):
            continue
        if _is_linked(obj) or _used_outside(obj, scene):
            linked_skipped += 1
            continue
        names.append(name)
    if linked_skipped:
        caveats.append(
            "%d off-screen object(s) not trimmed (linked or used outside this scene)"
            % linked_skipped)
    if not names:
        return []
    return [SpeedAction(
        "TRIM_OFFSCREEN",
        "%d off-screen object(s) → ray visibility off (shadows kept)" % len(names),
        "dead", 0, 0.85, 0, {"objects": names})]


def _is_collection_instance(obj):
    return (getattr(obj, "instance_type", None) == "COLLECTION"
            or getattr(obj, "instance_collection", None) is not None)


def _instance_carries_light(obj, _seen=None):
    """True if hiding/culling this object would also drop lights or emitters."""
    if obj is None:
        return False
    if getattr(obj, "type", "") == "LIGHT":
        return True
    if _is_emissive_strict(obj) or _is_emissive(obj):
        return True
    coll = getattr(obj, "instance_collection", None)
    if coll is None:
        return False
    if _seen is None:
        _seen = set()
    ident = id(coll)
    if ident in _seen:
        return False
    _seen.add(ident)
    members = getattr(coll, "all_objects", None)
    if members is None:
        members = getattr(coll, "objects", None) or ()
    for member in members:
        if _instance_carries_light(member, _seen):
            return True
    return False


def _instance_hide_actions(scene, coverage, caveats):
    """hide_render on local off-screen collection instances (not linked)."""
    if not coverage:
        return []
    names = []
    linked_skipped = 0
    light_skipped = 0
    for name, info in _sorted_coverage(coverage):
        if _cov_attr(info, "near_frustum_ever",
                     _cov_attr(info, "in_frustum_ever", True)):
            continue
        obj = _get_object(scene, name)
        if obj is None or getattr(obj, "hide_render", False):
            continue
        if _protected(obj):
            continue
        if not _is_collection_instance(obj):
            continue
        if getattr(obj, "type", "") in ("LIGHT", "CAMERA", "VOLUME"):
            continue
        if _instance_carries_light(obj):
            light_skipped += 1
            continue
        if _is_linked(obj) or _used_outside(obj, scene):
            linked_skipped += 1
            continue
        names.append(name)
    if linked_skipped:
        caveats.append(
            "%d off-screen collection instance(s) not hidden (linked or used outside this scene)"
            % linked_skipped)
    if light_skipped:
        caveats.append(
            "%d off-screen light instance(s) not hidden (would turn off lights)"
            % light_skipped)
    if not names:
        return []
    return [SpeedAction(
        "HIDE_OFFSCREEN_INSTANCES",
        "%d off-screen collection instance(s) → hide_render" % len(names),
        "dead", 0, 0.88, 0, {"objects": names})]


def _subdiv_actions(scene, coverage, caveats):
    if not coverage:
        return []
    names = []
    linked_skipped = 0
    for name, info in _sorted_coverage(coverage):
        if _cov_attr(info, "max_coverage", 1.0) >= SUBDIV_COVERAGE:
            continue
        obj = _get_object(scene, name)
        if obj is None or getattr(obj, "hide_render", False):
            continue
        if getattr(obj, "type", "") != "MESH" or _protected(obj):
            continue
        if _is_linked(obj) or _used_outside(obj, scene):
            linked_skipped += 1
            continue
        if _uses_adaptive_subdiv(scene, obj):
            continue
        if _extra_subdiv(obj) <= 0:
            continue
        names.append(name)
    if linked_skipped:
        caveats.append(
            "%d low-coverage object(s) not subdiv-capped (linked or used outside this scene)"
            % linked_skipped)
    if not names:
        return []
    return [SpeedAction(
        "SUBDIV_TRIM",
        "%d low-coverage object(s) → render subdiv capped" % len(names),
        "dead", 0, 0.70, 0, {"objects": names})]


def _adaptive_subdiv_actions(scene):
    names = []
    for obj in _iter_objects(scene):
        if getattr(obj, "hide_render", False) or _protected(obj):
            continue
        if not _uses_adaptive_subdiv(scene, obj):
            continue
        if _is_linked(obj) or _used_outside(obj, scene):
            continue
        # Adaptive dicing ignores render_levels; leaving them high still
        # tessellates the *base* mesh before dicing. Zero is the same look.
        if not _adaptive_subdiv_has_levels(obj):
            continue
        names.append(getattr(obj, "name", ""))
    names = [n for n in names if n]
    if not names:
        return []
    return [SpeedAction(
        "ADAPTIVE_SUBDIV_CAP",
        "%d adaptive-subdiv object(s) → render_levels 0 (dicing unchanged)" % len(names),
        "dead", 0, 0.75, 0, {"objects": names})]


def _scene_has_adaptive_subdiv(scene):
    for obj in _iter_objects(scene):
        if getattr(obj, "hide_render", False):
            continue
        if _uses_adaptive_subdiv(scene, obj):
            return True
    return False


def _offscreen_dicing_actions(scene):
    """Raise offscreen dicing only when adaptive subdiv is actually in use."""
    cycles = _cycles(scene)
    if cycles is None or not _has_attr(cycles, "offscreen_dicing_scale"):
        return []
    current = getattr(cycles, "offscreen_dicing_scale", None)
    if not isinstance(current, (int, float)) or current >= OFFSCREEN_DICING_SCALE:
        return []
    if not _scene_has_adaptive_subdiv(scene):
        return []
    return [SpeedAction(
        "OFFSCREEN_DICING",
        "Offscreen dicing scale %.0f (adaptive subdiv, outside camera only)"
        % OFFSCREEN_DICING_SCALE,
        "dead", 1, 0.92, 1,
        {"value": OFFSCREEN_DICING_SCALE})]


def _adaptive_subdiv_has_levels(obj):
    for mod in getattr(obj, "modifiers", ()):
        if getattr(mod, "type", "") != "SUBSURF":
            continue
        if getattr(mod, "show_render", True) and getattr(mod, "render_levels", 0) > 0:
            return True
    return False


MICRO_EMITTER_MAX = 32
STRICT_GROUP_DEPTH = 4
STRICT_EMISSION_STRENGTH = 0.1


def _micro_emitter_actions(scene, coverage, caveats):
    if not coverage:
        return []
    objects = []
    materials = []
    seen_mats = set()
    for name, info in _sorted_coverage(coverage):
        if _cov_attr(info, "max_coverage", 1.0) >= TINY_COVERAGE:
            continue
        if not _cov_attr(info, "in_frustum_ever", True):
            continue  # off-screen emitters may be hidden lights
        obj = _get_object(scene, name)
        if obj is None or getattr(obj, "hide_render", False) or _protected(obj):
            continue
        if _is_linked(obj) or _used_outside(obj, scene):
            continue
        if not _is_emissive_strict(obj):
            continue
        objects.append(name)
        for slot in getattr(obj, "material_slots", ()):
            mat = getattr(slot, "material", None)
            mat_name = getattr(mat, "name", None) if mat is not None else None
            if not mat_name or mat_name in seen_mats:
                continue
            seen_mats.add(mat_name)
            materials.append(mat_name)
    if not objects:
        return []
    blocked = _materials_used_by_large_objects(scene, coverage)
    if blocked:
        materials = [m for m in materials if m not in blocked]
        objects = [name for name in objects
                   if not _object_uses_material_names(
                       _get_object(scene, name), blocked)]
    if not objects:
        return []
    if len(objects) > MICRO_EMITTER_MAX:
        caveats.append(
            "too many tiny-emitter candidates; not auto-applying "
            "(likely asset-pack leftover emission)")
        return []
    return [SpeedAction(
        "MICRO_EMITTERS",
        "%d tiny emitter(s) → emission sampling off" % len(objects),
        "dead", 1, 0.90, 1,
        {"objects": objects, "materials": materials})]


def _materials_used_by_large_objects(scene, coverage):
    names = set()
    for name, info in _sorted_coverage(coverage):
        if _cov_attr(info, "max_coverage", 0.0) < TINY_COVERAGE:
            continue
        obj = _get_object(scene, name)
        if obj is None:
            continue
        for slot in getattr(obj, "material_slots", ()):
            mat = getattr(slot, "material", None)
            mat_name = getattr(mat, "name", None) if mat is not None else None
            if mat_name:
                names.add(mat_name)
    return names


def _object_uses_material_names(obj, names):
    if obj is None:
        return False
    for slot in getattr(obj, "material_slots", ()):
        mat = getattr(slot, "material", None)
        mat_name = getattr(mat, "name", None) if mat is not None else None
        if mat_name in names:
            return True
    return False


def _is_emissive_strict(obj):
    """Proven emitter only. objects_apply.is_emissive errs toward True
    (nodeless, deep groups) — correct for TRIM, wrong for sampling-off.
    A linked Emission Strength socket is unknown: not a proven emitter.
    """
    for slot in getattr(obj, "material_slots", ()):
        mat = getattr(slot, "material", None)
        if mat is None:
            continue
        tree = getattr(mat, "node_tree", None)
        if tree is None:
            continue
        if _tree_emits_strict(tree, 0):
            return True
    return False


def _tree_emits_strict(tree, depth):
    if tree is None or depth > STRICT_GROUP_DEPTH:
        return False
    for node in getattr(tree, "nodes", ()) or ():
        ntype = getattr(node, "type", "")
        if ntype == "EMISSION":
            outputs = getattr(node, "outputs", ()) or ()
            if any(getattr(out, "is_linked", False) for out in outputs):
                return True
            continue
        if ntype == "BSDF_PRINCIPLED":
            sock = _emission_strength_socket(node)
            if sock is None or getattr(sock, "is_linked", False):
                continue
            if getattr(sock, "default_value", 0.0) > STRICT_EMISSION_STRENGTH:
                return True
            continue
        if ntype == "GROUP" and getattr(node, "node_tree", None) is not None:
            if _tree_emits_strict(node.node_tree, depth + 1):
                return True
    return False


def _emission_strength_socket(node):
    inputs = getattr(node, "inputs", None)
    if inputs is None:
        return None
    getter = getattr(inputs, "get", None)
    if getter is not None:
        return getter("Emission Strength")
    return None


def _camera_cull_actions(scene, coverage, caveats):
    """Scatter/tiny only. Scene flag alone does nothing — objects listed too.

    Never lights, heroes, volumes, shadow catchers. Linked scatter/tiny ARE
    listed (Cycles per-object flag, not hide_render). Shared across local
    helper scenes is fine: the flag is evaluated against the rendering camera.
    Distance cull is AND with camera cull; we do not enable both.
    """
    if not coverage:
        return []
    cycles = _cycles(scene)
    if cycles is None or not _has_attr(cycles, "use_camera_cull"):
        return []
    names = []
    for name, info in _sorted_coverage(coverage):
        if _cov_attr(info, "max_coverage", 1.0) >= TINY_COVERAGE:
            continue
        obj = _get_object(scene, name)
        if obj is None or getattr(obj, "hide_render", False) or _protected(obj):
            continue
        if getattr(obj, "type", "") in ("LIGHT", "VOLUME", "CAMERA"):
            continue
        if _is_emissive(obj) or _instance_carries_light(obj):
            continue
        if getattr(obj, "is_shadow_catcher", False):
            continue
        oc = getattr(obj, "cycles", None)
        if oc is not None and getattr(oc, "is_shadow_catcher", False):
            continue
        # use_camera_cull is evaluated against the rendering camera, so a
        # chair also linked into a helper scene (Classroom dustParticules)
        # is still safe to tag. hide_render / trim keep used-outside.
        if getattr(oc, "use_camera_cull", False):
            continue
        names.append(name)
    if not names and getattr(cycles, "use_camera_cull", False):
        return []
    if not names:
        return []
    return [SpeedAction(
        "CAMERA_CULL",
        "%d scatter/tiny object(s) → camera cull, including linked" % len(names),
        "dead", 1, 0.88, 1, {"objects": names})]


def _hair_ribbon_actions(scene, coverage):
    curves = getattr(scene, "cycles_curves", None)
    if curves is None:
        return []
    shape = getattr(curves, "shape", None)
    if shape is None or "RIBBON" in str(shape):
        return []
    has_curves = any(getattr(obj, "type", "") == "CURVES"
                     and not getattr(obj, "hide_render", False)
                     for obj in _iter_objects(scene))
    if not has_curves:
        return []
    if _camera_near_curves(scene, coverage):
        return []
    return [SpeedAction(
        "HAIR_RIBBONS",
        "Hair/curves → rounded ribbons (none are camera-near)",
        "dead", 1, 0.90, 1, {})]


def _camera_near_curves(scene, coverage):
    for obj in _iter_objects(scene):
        if getattr(obj, "type", "") != "CURVES" or getattr(obj, "hide_render", False):
            continue
        info = coverage.get(getattr(obj, "name", "")) if coverage else None
        if _cov_attr(info, "max_coverage", 0.0) >= NEAR_CURVES_COVERAGE:
            return True
    return False


def _iter_comp_trees(scene):
    """Scene compositor tree, Blender 5 compositing_node_group, nested GROUPs."""
    pending = []
    if getattr(scene, "use_nodes", False):
        pending.append(getattr(scene, "node_tree", None))
    pending.append(getattr(scene, "compositing_node_group", None))
    seen = set()
    while pending:
        tree = pending.pop()
        if tree is None:
            continue
        ident = id(tree)
        if ident in seen:
            continue
        seen.add(ident)
        yield tree
        for node in getattr(tree, "nodes", ()) or ():
            if getattr(node, "type", "") != "GROUP":
                continue
            nested = getattr(node, "node_tree", None)
            if nested is not None:
                pending.append(nested)


def _used_pass_props(scene):
    """(used{(layer, prop)}, found_rlayers, unknown_group)."""
    used = set()
    found_rlayers = False
    unknown = False
    for tree in _iter_comp_trees(scene):
        for node in getattr(tree, "nodes", ()) or ():
            ntype = getattr(node, "type", "")
            if ntype == "GROUP" and getattr(node, "node_tree", None) is None:
                unknown = True
                continue
            if ntype != "R_LAYERS":
                continue
            found_rlayers = True
            layer = getattr(node, "layer", "") or ""
            for out in getattr(node, "outputs", ()) or ():
                if not getattr(out, "is_linked", False):
                    continue
                prop = PASS_SOCKET_TO_PROP.get(getattr(out, "name", ""))
                if prop:
                    used.add((layer, prop))
    return used, found_rlayers, unknown


def _pass_prune_actions(scene):
    """Turn off view-layer passes the compositor never reads. Combined stays."""
    used, _found, unknown = _used_pass_props(scene)
    if unknown:
        return []
    props = []
    for layer in getattr(scene, "view_layers", ()) or ():
        lname = getattr(layer, "name", "")
        for prop in PASS_SOCKET_TO_PROP.values():
            if not getattr(layer, prop, False):
                continue
            if (lname, prop) in used:
                continue
            props.append((lname, prop))
    if not props:
        return []
    factor = 0.93 if len(props) >= 6 else 0.97
    return [SpeedAction(
        "PASS_PRUNE",
        "%d unused view-layer pass(es) off" % len(props),
        "dead", 0, factor, 0, {"passes": props})]


def _crypto_actions(scene):
    if _compositor_has_crypto(scene):
        return []
    props = []
    for layer in getattr(scene, "view_layers", ()) or ():
        for prop in CRYPTO_PASS_PROPS:
            if getattr(layer, prop, False):
                props.append((getattr(layer, "name", ""), prop))
    if not props:
        return []
    return [SpeedAction(
        "CRYPTO_PRUNE",
        "Cryptomatte passes off (no Cryptomatte compositor node)",
        "dead", 0, 0.97, 0, {"passes": props})]


def _compositor_has_crypto(scene):
    trees = []
    if getattr(scene, "use_nodes", False):
        trees.append(getattr(scene, "node_tree", None))
    trees.append(getattr(scene, "compositing_node_group", None))
    for tree in trees:
        if tree is None:
            continue
        for node in getattr(tree, "nodes", ()) or ():
            if getattr(node, "type", "") in CRYPTO_NODE_TYPES:
                return True
    return False


# ---------------------------------------------------------------- variance

def _variance_actions(scene, settings, caveats):
    actions = []
    cycles = _cycles(scene)
    if cycles is not None and _has_attr(cycles, "denoising_use_gpu"):
        # Policy decides enable vs disable from VRAM headroom at apply time.
        factor = 0.85 if _budget_known(settings) else 1.0
        actions.append(SpeedAction(
            "GPU_DENOISE",
            "GPU denoiser placement (VRAM-headroom gated)",
            "variance", 1, factor, 0, {}))
    if cycles is not None and _has_attr(cycles, "denoising_prefilter"):
        current = getattr(cycles, "denoising_prefilter", None)
        denoise_on = getattr(cycles, "use_denoising", False)
        # Fire when denoise is already on OR will be turned on
        # (use_denoising False — DENOISE_ON is also in the plan).
        # Skip NONE (already fastest; quality risk). Skip FAST (already there).
        # Skip missing/unknown. Never propose NONE. Do not touch denoising_quality.
        if current == "ACCURATE":
            # Fire whether denoise_on or DENOISE_ON will enable OIDN.
            actions.append(SpeedAction(
                "DENOISE_PREFILTER",
                "OIDN prefilter FAST (Accurate is extra denoise time)",
                "variance", 1, 0.95, 1,
                {"value": "FAST"}))
    rend = getattr(scene, "render", None)
    device = getattr(rend, "compositor_device", None) if rend is not None else None
    if device is not None and device != "GPU":
        actions.append(SpeedAction(
            "COMPOSITOR_GPU", "Compositor on GPU",
            "variance", 0, 0.97, 0, {}))
    return actions


# ----------------------------------------------------------------- helpers


def _budget_known(settings):
    return float(getattr(settings, "vram_budget_gb", 0.0) or 0.0) > 0.0


def _cycles(scene):
    if getattr(getattr(scene, "render", None), "engine", "CYCLES") != "CYCLES":
        return None
    return getattr(scene, "cycles", None)


def _is_anim(scene):
    if getattr(scene, "frame_end", 1) <= getattr(scene, "frame_start", 1):
        return False
    rend = getattr(scene, "render", None)
    if rend is not None and getattr(rend, "use_motion_blur", False):
        return True
    return _has_animation_data(scene)


def _has_animation_data(scene):
    # Shot-level only. Persistent Data / animated seed are for a moving
    # camera or a scene action, not a ticking clock or animated blinds.
    owners = [scene, getattr(scene, "camera", None)]
    for owner in owners:
        if owner is None:
            continue
        ad = getattr(owner, "animation_data", None)
        if ad is None:
            continue
        if getattr(ad, "action", None) is not None:
            return True
        tracks = getattr(ad, "nla_tracks", None) or ()
        if any(getattr(track, "strips", None) for track in tracks):
            return True
    return False


def _protected(obj):
    return getattr(getattr(obj, "scenequant", None), "override", "AUTO") != "AUTO"


def _has_attr(owner, name):
    if owner is None:
        return False
    try:
        return hasattr(owner, name)
    except Exception:
        return False


def _read_owner(scene, owner_key):
    if owner_key == "scene":
        return scene
    return getattr(scene, owner_key, None)


def _read_current(scene, owner_key, prop_name):
    owner = _read_owner(scene, owner_key)
    if owner is None:
        return _MISSING
    return getattr(owner, prop_name, _MISSING)


def _entry_would_fire(scene, owner_key, prop_name, value, mode, options=None):
    """Same MODE_MIN / MODE_MAX rules as settings_apply._apply_entries."""
    options = options or {}
    requires = options.get("requires")
    if requires:
        gate = scene
        for part in requires.split("."):
            gate = getattr(gate, part, _MISSING)
            if gate is _MISSING:
                return False
        if not gate:
            return False
    current = _read_current(scene, owner_key, prop_name)
    if current is _MISSING:
        return False
    if mode == "min":
        return isinstance(current, (int, float)) and current > value
    if mode == "max":
        if not isinstance(current, (int, float)) or current >= value:
            return False
        if options.get("skip_zero") and current == 0:
            return False
        return True
    return current != value


def _iter_objects(scene):
    return getattr(scene, "objects", ()) or ()


def _get_object(scene, name):
    objects = getattr(scene, "objects", None)
    getter = getattr(objects, "get", None)
    if getter is not None:
        try:
            return getter(name)
        except Exception:
            pass
    for obj in objects or ():
        if getattr(obj, "name", None) == name:
            return obj
    return None


def _sorted_coverage(coverage):
    return sorted((coverage or {}).items(), key=lambda item: item[0])


def _cov_attr(info, name, default=None):
    if info is None:
        return default
    if isinstance(info, dict):
        return info.get(name, default)
    return getattr(info, name, default)


def _is_linked(obj):
    try:
        from .. import compat
        return compat.is_linked(obj)
    except Exception:
        return getattr(obj, "library", None) is not None


def _used_outside(obj, scene):
    try:
        from ..apply import guards
        return guards.used_outside_scene(obj, scene)
    except Exception:
        return False


def _is_emissive(obj):
    try:
        from ..apply.objects_apply import is_emissive
        return is_emissive(obj)
    except Exception:
        return False


def _extra_subdiv(obj):
    try:
        from ..analysis import memory_model
        return memory_model.extra_render_subdiv_levels(obj)
    except Exception:
        return 0


def _uses_adaptive_subdiv(scene, obj):
    try:
        from ..analysis import memory_model
        return memory_model.uses_adaptive_subdivision(scene, obj)
    except Exception:
        return False


def _has_deform(obj):
    if getattr(getattr(obj, "data", None), "shape_keys", None) is not None:
        return True
    for mod in getattr(obj, "modifiers", ()):
        if getattr(mod, "type", "") in DEFORM_MODS:
            return True
    return False


OPAQUE_CUTOUT_SHADOW_MAX = 64


def _opaque_cutout_shadow_actions(scene, caveats):
    """Opaque shadows on CLIP/HASHED cutouts. Glass and transmission stay.

    Cycles docs: disabling use_transparent_shadow is faster, shadows are not
    accurate. Cutout cards (leaves, decals) are the safe case. Windows and
    hero glass are not. A material shared with any HERO/EXCLUDE object is
    skipped — writing it would change the protected user too.
    """
    protected_mats = set()
    for obj in _iter_objects(scene):
        if not _protected(obj):
            continue
        for slot in getattr(obj, "material_slots", ()) or ():
            mat = getattr(slot, "material", None)
            name = getattr(mat, "name", None) if mat is not None else None
            if name:
                protected_mats.add(name)

    names = []
    seen = set()
    linked_seen = set()
    for obj in _iter_objects(scene):
        if getattr(obj, "hide_render", False) or _protected(obj):
            continue
        for slot in getattr(obj, "material_slots", ()) or ():
            mat = getattr(slot, "material", None)
            if mat is None:
                continue
            if not _is_cutout_for_opaque_shadow(mat):
                continue
            name = getattr(mat, "name", "")
            if not name:
                continue
            if _is_linked(mat):
                linked_seen.add(name)
                continue
            if name in protected_mats:
                continue
            if getattr(mat, "use_transparent_shadow", True) is False:
                continue
            if name in seen:
                continue
            seen.add(name)
            names.append(name)
    if linked_seen:
        caveats.append(
            "%d linked cutout material(s) not changed (opaque shadows)"
            % len(linked_seen))
    if len(names) > OPAQUE_CUTOUT_SHADOW_MAX:
        caveats.append(
            "too many cutout materials for opaque-shadow lever")
        return []
    if not names:
        return []
    return [SpeedAction(
        "OPAQUE_CUTOUT_SHADOWS",
        "%d cutout material(s) → opaque shadows" % len(names),
        "dead", 1, 0.90, 1, {"materials": names})]


def _load_unused_slots():
    try:
        from ..analysis import unused_slots
        return unused_slots
    except Exception:
        pass
    try:
        import importlib.util
        import os
        path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), "..", "analysis", "unused_slots.py"))
        spec = importlib.util.spec_from_file_location(
            "scenequant.analysis.unused_slots", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None


def unused_slots_actions(scene, caveats=None):
    """Manual-later planner hook for L3 UNUSED_SLOTS.

    NOT called from build_speed_plan / _dead_actions. Auto stays off until
    a measured loft pair exists. time_factor is 1.0 (no claim). Graph /
    datablock lever — not a Cycles RNA knob.
    """
    unused_slots = _load_unused_slots()
    if unused_slots is None:
        return []
    records = unused_slots.classify_unused_slots(scene)
    n = len(records)
    if n < 1:
        return []
    meshes = {r.get("mesh") for r in records if r.get("mesh")}
    return [SpeedAction(
        "UNUSED_SLOTS",
        "%d unused material slot(s) on %d unique mesh(es) → prune (manual)"
        % (n, len(meshes)),
        "dead", 2, 1.0, 1,
        {"records": records})]


def dead_closure_prune_actions(scene, caveats=None):
    """Manual-later planner hook for L1 DEAD_CLOSURE_PRUNE.

    NOT called from build_speed_plan / _dead_actions. Auto stays off until
    official-file inventory proves candidates. time_factor is 1.0 (no claim).
    """
    try:
        from ..analysis import dead_closures
    except Exception:
        return []
    records = dead_closures.classify_dead_closures(scene)
    prunes = [r for r in records if r.get("class") in dead_closures.PRUNE_CLASSES]
    n_alpha = sum(1 for r in prunes if r.get("class") == dead_closures.PRUNE_ALPHA)
    n_vol = sum(1 for r in prunes if r.get("class") == dead_closures.PRUNE_VOLUME)
    if n_alpha + n_vol < 1:
        return []
    return [SpeedAction(
        "DEAD_CLOSURE_PRUNE",
        "%d false-transparent / empty-volume socket(s) → unlink (manual)"
        % (n_alpha + n_vol),
        "dead", 2, 1.0, 1,
        {"records": prunes})]


_CUTOUT_SURFACE = {
    "BSDF_DIFFUSE", "BSDF_GLOSSY", "BSDF_PRINCIPLED",
    "BSDF_TRANSLUCENT", "BSDF_VELVET", "BSDF_TOON",
}


def _is_cutout_for_opaque_shadow(mat):
    """CLIP/HASHED is not enough. Official files often store HASHED on
    every material (Classroom walls, floor, paint). Require proven alpha
    and skip glass / portals / leftover Transparent-only windows.
    """
    if mat is None:
        return False
    blend = getattr(mat, "blend_method", "OPAQUE")
    if blend not in ("CLIP", "HASHED"):
        return False
    tree = getattr(mat, "node_tree", None)
    if tree is None:
        return False
    if _tree_has_types(tree, {"GROUP"}):
        return False
    if _tree_has_types(tree, {"BSDF_GLASS", "BSDF_REFRACTION"}):
        return False
    nodes = list(getattr(tree, "nodes", ()) or ())
    types = {getattr(n, "type", "") for n in nodes}
    for node in nodes:
        if getattr(node, "type", "") == "BSDF_PRINCIPLED" and _principled_transmits(node):
            return False
    # Light portal: Transparent mixed with Emission, no surface BSDF.
    if "BSDF_TRANSPARENT" in types and "EMISSION" in types and not (types & _CUTOUT_SURFACE):
        return False
    for node in nodes:
        if getattr(node, "type", "") == "BSDF_PRINCIPLED" and _principled_alpha_open(node):
            return True
    return _mix_transparent_cutout(tree)


def _mix_transparent_cutout(tree):
    """Image-driven leaf/wire: Mix Shader of Transparent + surface, Fac linked."""
    nodes = list(getattr(tree, "nodes", ()) or ())
    types = {getattr(n, "type", "") for n in nodes}
    if "BSDF_TRANSPARENT" not in types:
        return False
    if not (types & _CUTOUT_SURFACE):
        return False
    for node in nodes:
        if getattr(node, "type", "") != "MIX_SHADER":
            continue
        inputs = getattr(node, "inputs", None)
        if inputs is None:
            continue
        getter = getattr(inputs, "get", None)
        sock = getter("Fac") if getter is not None else None
        if sock is None:
            try:
                sock = inputs[0]
            except Exception:
                sock = None
        if sock is not None and getattr(sock, "is_linked", False):
            return True
    return False



GLOSSY_BSDF_TYPES = {"BSDF_GLOSSY", "BSDF_GLASS", "BSDF_ANISOTROPIC"}


def _filter_glossy_prop(cycles):
    """Cycles 4.5.5 / 5.1.2 RNA is blur_glossy (UI: Filter Glossy).

    filter_glossy is not present on supported versions; hasattr-guard both.
    """
    if _has_attr(cycles, "blur_glossy"):
        return "blur_glossy"
    if _has_attr(cycles, "filter_glossy"):
        return "filter_glossy"
    return None


def _filter_glossy_disabled(cycles, prop):
    """True when Filter Glossy is 0 / unset / disabled. User values > 0 stay."""
    current = getattr(cycles, prop, None)
    if current is None:
        return True
    if isinstance(current, bool):
        return current is False
    if isinstance(current, (int, float)):
        return current == 0
    return False


def _filter_glossy_actions(scene, caveats):
    """Enable Filter Glossy at 1.0 only when it is off and glossy is proven.

    Write is 0 -> 1.0, never a raise of a user value already > 0. MODE_MIN
    against 1.0 would skip 0 and would drag a deliberate 3.0 down (slower);
    we do neither. GROUP trees are unproven. HERO/EXCLUDE objects do not
    count as proof.
    """
    cycles = _cycles(scene)
    if cycles is None:
        return []
    prop = _filter_glossy_prop(cycles)
    if prop is None:
        return []
    if not _filter_glossy_disabled(cycles, prop):
        return []
    proven, saw_group = _scene_glossy_state(scene)
    if not proven:
        if saw_group:
            caveats.append(
                "filter glossy not changed (glossy unproven — GROUP node trees)")
        return []
    return [SpeedAction(
        "FILTER_GLOSSY",
        "Filter glossy 1.0 (proven glossy/glass; was disabled)",
        "paths", 1, 0.96, 1,
        {"value": FILTER_GLOSSY_VALUE, "prop": prop})]


def _scene_glossy_state(scene):
    """(proven, saw_unwalkable_group). Protected objects are not proof."""
    proven = False
    saw_group = False
    for obj in _iter_objects(scene):
        if getattr(obj, "hide_render", False) or _protected(obj):
            continue
        for slot in getattr(obj, "material_slots", ()) or ():
            mat = getattr(slot, "material", None)
            if mat is None:
                continue
            tree = getattr(mat, "node_tree", None)
            if tree is None:
                continue
            if _tree_has_types(tree, {"GROUP"}):
                saw_group = True
                continue
            if _tree_has_glossy(tree):
                proven = True
    return proven, saw_group


def _tree_has_glossy(tree):
    for node in getattr(tree, "nodes", ()) or ():
        ntype = getattr(node, "type", "")
        if ntype in GLOSSY_BSDF_TYPES:
            return True
        if ntype == "BSDF_PRINCIPLED" and _principled_is_glossy(node):
            return True
    return False


def _sock(node, *names):
    inputs = getattr(node, "inputs", None)
    if inputs is None:
        return None
    getter = getattr(inputs, "get", None)
    if getter is None:
        return None
    for name in names:
        sock = getter(name)
        if sock is not None:
            return sock
    return None


def _sock_unlinked_float(node, names, default=0.0):
    sock = _sock(node, *names)
    if sock is None or getattr(sock, "is_linked", False):
        return None
    value = getattr(sock, "default_value", default)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _principled_is_glossy(node):
    """Clearcoat, or roughness < 1 with specular / metal / anisotropy."""
    coat = _sock_unlinked_float(node, ("Coat Weight", "Coat", "Clearcoat"))
    if coat is not None and coat > 0.0:
        return True
    rough = _sock_unlinked_float(node, ("Roughness",), 1.0)
    if rough is None or rough >= 1.0:
        return False
    spec = _sock_unlinked_float(node, ("Specular IOR Level", "Specular"))
    if spec is not None and spec > 0.0:
        return True
    metal = _sock_unlinked_float(node, ("Metallic",))
    if metal is not None and metal > 0.0:
        return True
    aniso = _sock_unlinked_float(node, ("Anisotropic", "Anisotropy"))
    if aniso is not None and aniso > 0.0:
        return True
    return False


def _auto_scramble_prop(cycles):
    """Cycles 4.5.5 / 5.1.2 RNA is auto_scrambling_distance (bool).

    use_auto_scrambling_distance exists on no supported version. use_auto_scrambling
    is a defensive alias. scrambling_distance is the manual multiplier
    (factory 1.0) — never force a huge value.
    """
    if _has_attr(cycles, "auto_scrambling_distance"):
        return "auto_scrambling_distance"
    if _has_attr(cycles, "use_auto_scrambling"):
        return "use_auto_scrambling"
    return None


def _auto_scramble_actions(scene):
    """Turn auto scrambling on for the GPU path. Skip if the attr is missing.

    Inert under Blue-Noise / 4.5 AUTOMATIC unless sampling_pattern is
    TABULATED_SOBOL (same pairing as TIER_PERCEPTUAL). Never writes
    scrambling_distance.
    """
    cycles = _cycles(scene)
    if cycles is None:
        return []
    prop = _auto_scramble_prop(cycles)
    if prop is None:
        return []
    if getattr(cycles, "device", "GPU") == "CPU":
        return []
    if getattr(cycles, prop, False):
        return []
    payload = {"prop": prop, "enabled": True}
    if _has_attr(cycles, "sampling_pattern"):
        payload["sampling_pattern"] = "TABULATED_SOBOL"
    return [SpeedAction(
        "AUTO_SCRAMBLE",
        "Auto scrambling distance on (GPU)",
        "samples", 1, 0.97, 1,
        payload)]


TRANSPARENT_SHADOW_CAP = 4
TRANSPARENT_NODE_TYPES = {"BSDF_TRANSPARENT", "BSDF_GLASS", "BSDF_REFRACTION"}


def _transparent_shadow_actions(scene, caveats):
    """MODE_MIN transparent_max_bounces to 4 when the scene proves alpha/glass.

    Shadow rays retrace every transparent hit. A default of 8 is leftover
    budget on blinds, leaves, and window stacks. Hero glass / MNEE stay.
    GROUP trees are not proven.
    """
    cycles = _cycles(scene)
    if cycles is None or not _has_attr(cycles, "transparent_max_bounces"):
        return []
    current = getattr(cycles, "transparent_max_bounces", None)
    if not isinstance(current, (int, float)) or current <= TRANSPARENT_SHADOW_CAP:
        return []
    if _needs_caustics(scene):
        return []
    if not _scene_has_transparency(scene):
        return []
    return [SpeedAction(
        "TRANSPARENT_SHADOW_CAP",
        "Transparent shadows cap %d (stacked alpha/glass; not hero)" % (
            TRANSPARENT_SHADOW_CAP),
        "paths", 1, 0.92, 1,
        {"value": TRANSPARENT_SHADOW_CAP})]


def _scene_has_transparency(scene):
    for obj in _iter_objects(scene):
        if getattr(obj, "hide_render", False) or _protected(obj):
            continue
        for slot in getattr(obj, "material_slots", ()) or ():
            mat = getattr(slot, "material", None)
            proven = _material_is_transparent(mat)
            if proven is True:
                return True
    return False


def _material_is_transparent(mat):
    """True / False. GROUP in the tree → not proven (False)."""
    if mat is None:
        return False
    blend = getattr(mat, "blend_method", "OPAQUE")
    if blend in ("CLIP", "HASHED", "BLEND"):
        return True
    tree = getattr(mat, "node_tree", None)
    if tree is None:
        return False
    if _tree_has_types(tree, {"GROUP"}):
        return False
    if _tree_has_types(tree, TRANSPARENT_NODE_TYPES):
        return True
    for node in getattr(tree, "nodes", ()) or ():
        if getattr(node, "type", "") != "BSDF_PRINCIPLED":
            continue
        if _principled_transmits(node) or _principled_alpha_open(node):
            return True
    return False


def _principled_alpha_open(node):
    inputs = getattr(node, "inputs", None)
    if inputs is None:
        return False
    getter = getattr(inputs, "get", None)
    if getter is None:
        return False
    sock = getter("Alpha")
    if sock is None:
        return False
    if getattr(sock, "is_linked", False):
        return True
    value = getattr(sock, "default_value", 1.0)
    return isinstance(value, (int, float)) and value < 0.999


def _looks_glass(obj):
    for slot in getattr(obj, "material_slots", ()):
        mat = getattr(slot, "material", None)
        tree = getattr(mat, "node_tree", None) if mat is not None else None
        if tree is None:
            continue
        for node in getattr(tree, "nodes", ()) or ():
            ntype = getattr(node, "type", "")
            if ntype in ("BSDF_GLASS", "BSDF_REFRACTION"):
                return True
            if ntype == "BSDF_PRINCIPLED" and _principled_transmits(node):
                return True
    return False


def _principled_transmits(node):
    sock = None
    inputs = getattr(node, "inputs", None)
    if inputs is None:
        return False
    getter = getattr(inputs, "get", None)
    if getter is not None:
        sock = getter("Transmission Weight") or getter("Transmission")
    if sock is None:
        return False
    if getattr(sock, "is_linked", False):
        return True
    return getattr(sock, "default_value", 0.0) > 0.2
