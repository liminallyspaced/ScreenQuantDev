# Speed-plan execution. Parallel to plan_apply but a separate file so VRAM
# Fit-to-Budget handlers stay untouched. Every write is journal-tagged
# 'speed' (the wrapper forces the tag even when a callee passes 'trim').
# Background-safe: scene is passed in, no bpy.context UI assumptions.

from ..analysis import coverage as coverage_analysis
from ..planning import presets, speed_solver
from . import guards, objects_apply, settings_apply

SPEED_TAG = "speed"
DEFAULT_MIN_SAMPLES = 48

# Path-class slice of TIER_PERCEPTUAL: bounce/clamp/blur only.
_PATH_ENTRIES = tuple(
    entry for entry in presets.TIER_PERCEPTUAL
    if entry[1] in speed_solver.PATH_PROP_NAMES
)
_LOCK_ENTRIES = presets.TIER_LOSSLESS
_ADAPTIVE_ON = (("cycles", "use_adaptive_sampling", True, presets.MODE_SET),)
_THRESHOLD = ((
    "cycles", "adaptive_threshold", speed_solver.THRESHOLD_CAP, presets.MODE_MAX,
    {"skip_zero": True, "requires": "cycles.use_adaptive_sampling"},
),)
_SAMPLES_CAP = (("cycles", "samples", speed_solver.SAMPLES_CAP, presets.MODE_MIN),)
_DENOISE_ON = (("cycles", "use_denoising", True, presets.MODE_SET),)


class _SpeedJournal:
    """Force tag 'speed' on every write. Run-id stamping still happens if
    the inner journal is a RunScopedJournal."""

    def __init__(self, jrnl):
        self.journal = jrnl

    def set_prop(self, datablock, rna_path, value, tag=None, **kwargs):
        return self.journal.set_prop(datablock, rna_path, value, SPEED_TAG, **kwargs)

    def record_action(self, kind, payload, tag=None, **kwargs):
        return self.journal.record_action(kind, payload, SPEED_TAG, **kwargs)

    def __getattr__(self, name):
        return getattr(self.journal, name)


def apply_speed_plan(scene, settings, jrnl, plan, coverage_map=None,
                     progress=None, mem=None):
    """Execute plan actions (dict or SpeedPlan). Returns the same shape as
    plan_apply.apply_plan: {applied, outcomes, skipped}."""
    jrnl = _SpeedJournal(jrnl)
    cache = {"cov": coverage_map, "mem": mem}
    applied = 0
    outcomes = []
    skipped = []
    actions = _plan_actions(plan)
    for index, action in enumerate(actions):
        kind = action.get("kind") or "?"
        guards.notify_progress(progress, index, len(actions), kind)
        handler = _HANDLERS.get(kind)
        if handler is None:
            skipped.append(_skip(kind, "-", "unknown speed action: %s" % kind))
            continue
        outcome = handler(scene, settings, jrnl, action.get("payload") or {},
                          cache, skipped, progress)
        if outcome:
            outcomes.append(outcome)
        applied += 1
    return {"applied": applied, "outcomes": outcomes, "skipped": skipped}


def _plan_actions(plan):
    if isinstance(plan, dict):
        return plan.get("actions") or []
    return [__import__("dataclasses").asdict(a) for a in (plan.actions or [])]


def _skip(source, name, reason):
    return {"source": str(source), "name": str(name), "reason": str(reason)}


def _collect_skips(skipped, source, result):
    for name, reason in (result or {}).get("skipped", ()):
        skipped.append(_skip(source, name, reason))


def _vram_mb(settings):
    return float(getattr(settings, "vram_budget_gb", 0.0) or 0.0) * 1024.0


def _need_mem(cache, skipped, kind):
    mem = cache.get("mem")
    if mem is None:
        skipped.append(_skip(kind, "-", "no memory estimate; skipped headroom check"))
        return None
    return mem


def _need_coverage(scene, settings, cache, progress=None):
    if cache.get("cov") is None:
        if getattr(scene, "camera", None) is None:
            cache["cov"] = {}
        else:
            cache["cov"] = coverage_analysis.compute_coverage(
                scene, scene.objects,
                frame_samples=settings.coverage_frame_samples,
                quality_factor=settings.quality_factor,
                progress=progress,
            )
    return cache["cov"]


def _apply_entries(scene, jrnl, entries):
    return settings_apply._apply_entries(scene, jrnl, entries, SPEED_TAG)


# ---------------------------------------------------------------- handlers

def _apply_lock(scene, settings, jrnl, payload, cache, skipped, progress):
    changes = _apply_entries(scene, jrnl, _LOCK_ENTRIES)
    return "lock interface" if changes else None


def _apply_paths(scene, settings, jrnl, payload, cache, skipped, progress):
    changes = _apply_entries(scene, jrnl, _PATH_ENTRIES)
    return "perceptual path settings (%d)" % len(changes) if changes else None


def _apply_adaptive_on(scene, settings, jrnl, payload, cache, skipped, progress):
    changes = _apply_entries(scene, jrnl, _ADAPTIVE_ON)
    return "adaptive sampling on" if changes else None


def _apply_threshold(scene, settings, jrnl, payload, cache, skipped, progress):
    changes = _apply_entries(scene, jrnl, _THRESHOLD)
    return "adaptive threshold floor 0.015" if changes else None


def _apply_samples_cap(scene, settings, jrnl, payload, cache, skipped, progress):
    current = getattr(getattr(scene, "cycles", None), "samples", 0)
    if isinstance(current, (int, float)) and current < speed_solver.SAMPLES_FLOOR:
        skipped.append(_skip("SAMPLES_CAP", "-",
                             "samples %s < %d; not lowering" % (
                                 current, speed_solver.SAMPLES_FLOOR)))
        return None
    changes = _apply_entries(scene, jrnl, _SAMPLES_CAP)
    return "sample ceiling 1024" if changes else None


def _apply_denoise_on(scene, settings, jrnl, payload, cache, skipped, progress):
    changes = _apply_entries(scene, jrnl, _DENOISE_ON)
    # Prefer OIDN when the enum exists; invalid items raise TypeError, which
    # set_prop catches, so this degrades to a safe skip.
    jrnl.set_prop(scene, "cycles.denoiser", "OPENIMAGEDENOISE", SPEED_TAG)
    return "OIDN denoising on" if changes else None


def _apply_min_samples(scene, settings, jrnl, payload, cache, skipped, progress):
    target = int(payload.get("value") or DEFAULT_MIN_SAMPLES)
    entry = (("cycles", "adaptive_min_samples", target, presets.MODE_MAX,
              {"skip_zero": False}),)
    changes = _apply_entries(scene, jrnl, entry)
    return "adaptive min samples %d" % target if changes else None


def _apply_persistent(scene, settings, jrnl, payload, cache, skipped, progress):
    mem = _need_mem(cache, skipped, "PERSISTENT_DATA")
    if mem is None:
        return None
    enabled = settings_apply.maybe_enable_persistent_data(
        scene, jrnl, mem, _vram_mb(settings), tag=SPEED_TAG)
    if not enabled:
        skipped.append(_skip(
            "PERSISTENT_DATA", "-",
            "VRAM headroom missing or budget unknown — persistent data left off"))
        return None
    return "persistent data enabled"


def _apply_gpu_denoise(scene, settings, jrnl, payload, cache, skipped, progress):
    mem = _need_mem(cache, skipped, "GPU_DENOISE")
    if mem is None:
        return None
    settings_apply.gpu_denoise_policy(
        scene, jrnl, mem, _vram_mb(settings), tag=SPEED_TAG)
    return "GPU denoise policy applied"


def _apply_denoise_prefilter(scene, settings, jrnl, payload, cache, skipped, progress):
    value = payload.get("value") or "FAST"
    cycles = getattr(scene, "cycles", None)
    if cycles is None or not hasattr(cycles, "denoising_prefilter"):
        skipped.append(_skip("DENOISE_PREFILTER", "-", "denoising_prefilter missing"))
        return None
    current = getattr(cycles, "denoising_prefilter", None)
    if current in ("FAST", "NONE"):
        return None
    if value != "FAST":
        return None
    if jrnl.set_prop(scene, "cycles.denoising_prefilter", "FAST"):
        return "OIDN prefilter FAST"
    return None


def _apply_trim(scene, settings, jrnl, payload, cache, skipped, progress):
    if getattr(scene, "camera", None) is None:
        skipped.append(_skip("TRIM_OFFSCREEN", "-", "no scene camera"))
        return None
    cov = _need_coverage(scene, settings, cache, progress)
    result = objects_apply.trim_offscreen(
        scene, cov, jrnl,
        keep_reflections=settings.trim_keep_reflections, progress=progress)
    _collect_skips(skipped, "trim", result)
    return "ray visibility trimmed on %d objects" % result.get("trimmed", 0)


def _apply_hide_instances(scene, settings, jrnl, payload, cache, skipped, progress):
    if getattr(scene, "camera", None) is None:
        skipped.append(_skip("HIDE_OFFSCREEN_INSTANCES", "-", "no scene camera"))
        return None
    guard_cache = {}
    hid = 0
    for name in payload.get("objects") or ():
        obj = scene.objects.get(name)
        if obj is None:
            skipped.append(_skip("HIDE_OFFSCREEN_INSTANCES", name, "object missing"))
            continue
        reason = _object_write_skip(obj, scene, guard_cache)
        if reason:
            skipped.append(_skip("HIDE_OFFSCREEN_INSTANCES", name, reason))
            continue
        if not speed_solver._is_collection_instance(obj):
            skipped.append(_skip(
                "HIDE_OFFSCREEN_INSTANCES", name, "not a collection instance"))
            continue
        if getattr(obj, "type", "") in ("LIGHT", "CAMERA", "VOLUME"):
            skipped.append(_skip(
                "HIDE_OFFSCREEN_INSTANCES", name, "light/camera/volume"))
            continue
        if speed_solver._instance_carries_light(obj):
            skipped.append(_skip(
                "HIDE_OFFSCREEN_INSTANCES", name, "instance carries lights"))
            continue
        if jrnl.set_prop(obj, "hide_render", True):
            hid += 1
    return "hid %d off-screen collection instances" % hid


def _apply_subdiv(scene, settings, jrnl, payload, cache, skipped, progress):
    if getattr(scene, "camera", None) is None:
        skipped.append(_skip("SUBDIV_TRIM", "-", "no scene camera"))
        return None
    cov = _need_coverage(scene, settings, cache, progress)
    result = objects_apply.trim_subdiv(scene, cov, jrnl, progress=progress)
    _collect_skips(skipped, "subdiv trim", result)
    return "render subdivision capped on %d objects" % result.get("capped", 0)


def _apply_micro_emitters(scene, settings, jrnl, payload, cache, skipped, progress):
    changed = 0
    guard_cache = {}
    for name in payload.get("materials") or ():
        try:
            import bpy
            mat = bpy.data.materials.get(name)
        except Exception:
            mat = None
        if mat is None:
            skipped.append(_skip("MICRO_EMITTERS", name, "material missing"))
            continue
        from .. import compat
        if compat.is_linked(mat):
            skipped.append(_skip("MICRO_EMITTERS", name, "linked material"))
            continue
        if jrnl.set_prop(mat, "cycles.emission_sampling", "NONE", SPEED_TAG):
            changed += 1
        else:
            skipped.append(_skip("MICRO_EMITTERS", name,
                                 "emission_sampling unavailable or already off"))
    for name in payload.get("objects") or ():
        obj = scene.objects.get(name)
        if obj is None:
            skipped.append(_skip("MICRO_EMITTERS", name, "object missing"))
            continue
        reason = _object_write_skip(obj, scene, guard_cache)
        if reason:
            skipped.append(_skip("MICRO_EMITTERS", name, reason))
            continue
        if jrnl.set_prop(obj, "cycles.use_multiple_importance_sampling",
                         False, SPEED_TAG):
            changed += 1
    return "micro-emitters demoted (%d writes)" % changed if changed else None


def _apply_light_tree(scene, settings, jrnl, payload, cache, skipped, progress):
    enabled = bool(payload.get("enabled"))
    if jrnl.set_prop(scene, "cycles.use_light_tree", enabled, SPEED_TAG):
        return "light tree %s" % ("on" if enabled else "off")
    return None


def _apply_caustics_off(scene, settings, jrnl, payload, cache, skipped, progress):
    changed = jrnl.set_prop(scene, "cycles.caustics_reflective", False, SPEED_TAG)
    changed = jrnl.set_prop(scene, "cycles.caustics_refractive", False, SPEED_TAG) or changed
    return "caustics off" if changed else None


def _apply_path_guiding_off(scene, settings, jrnl, payload, cache, skipped, progress):
    if jrnl.set_prop(scene, "cycles.use_guiding", False, SPEED_TAG):
        return "path guiding off (GPU)"
    return None


def _apply_world_mis_none(scene, settings, jrnl, payload, cache, skipped, progress):
    world = getattr(scene, "world", None)
    if world is None:
        skipped.append(_skip("WORLD_MIS_NONE", "-", "no world"))
        return None
    from .. import compat
    if compat.is_linked(world):
        skipped.append(_skip("WORLD_MIS_NONE", "-", "linked world"))
        return None
    wcycles = getattr(world, "cycles", None)
    if wcycles is None or not hasattr(wcycles, "sampling_method"):
        skipped.append(_skip("WORLD_MIS_NONE", "-", "sampling_method missing"))
        return None
    if getattr(wcycles, "sampling_method", None) == "NONE":
        return None
    if not speed_solver._world_is_solid(world):
        skipped.append(_skip(
            "WORLD_MIS_NONE", "-",
            "world is not a proven solid background"))
        return None
    if jrnl.set_prop(world, "cycles.sampling_method", "NONE"):
        return "world MIS off (solid background)"
    return None


def _apply_light_sampling_threshold(scene, settings, jrnl, payload, cache, skipped, progress):
    cycles = getattr(scene, "cycles", None)
    if cycles is None or not hasattr(cycles, "light_sampling_threshold"):
        skipped.append(_skip("LIGHT_SAMPLING_THRESHOLD", "-", "no threshold attr"))
        return None
    current = getattr(cycles, "light_sampling_threshold", None)
    if current != 0:
        skipped.append(_skip(
            "LIGHT_SAMPLING_THRESHOLD", "-", "already enabled or missing"))
        return None
    target = payload.get("value", speed_solver.LIGHT_SAMPLING_THRESHOLD)
    if jrnl.set_prop(scene, "cycles.light_sampling_threshold", target):
        return "light sampling threshold %s" % target
    return None


def _apply_volume_bounces_zero(scene, settings, jrnl, payload, cache, skipped, progress):
    if speed_solver._scene_has_volume(scene):
        skipped.append(_skip("VOLUME_BOUNCES_ZERO", "-", "scene has volumes"))
        return None
    entry = (("cycles", "volume_bounces", 0, presets.MODE_MIN),)
    changes = _apply_entries(scene, jrnl, entry)
    return "volume bounces 0" if changes else None




def _apply_homogeneous_volume(scene, settings, jrnl, payload, cache, skipped, progress):
    changed = 0
    from .. import compat
    for name in payload.get("materials") or ():
        try:
            import bpy
            mat = bpy.data.materials.get(name)
        except Exception:
            mat = None
        if mat is None:
            skipped.append(_skip("HOMOGENEOUS_VOLUME", name, "material missing"))
            continue
        if compat.is_linked(mat):
            skipped.append(_skip("HOMOGENEOUS_VOLUME", name, "linked material"))
            continue
        if not speed_solver._volume_tree_is_homogeneous(
                getattr(mat, "node_tree", None)):
            skipped.append(_skip(
                "HOMOGENEOUS_VOLUME", name, "volume not proven homogeneous"))
            continue
        if jrnl.set_prop(mat, "cycles.homogeneous_volume", True):
            changed += 1
    if payload.get("world"):
        world = getattr(scene, "world", None)
        if world is None:
            skipped.append(_skip("HOMOGENEOUS_VOLUME", "-", "no world"))
        elif compat.is_linked(world):
            skipped.append(_skip("HOMOGENEOUS_VOLUME", "-", "linked world"))
        elif not speed_solver._volume_tree_is_homogeneous(
                getattr(world, "node_tree", None)):
            skipped.append(_skip(
                "HOMOGENEOUS_VOLUME", "-", "volume not proven homogeneous"))
        elif jrnl.set_prop(world, "cycles.homogeneous_volume", True):
            changed += 1
    return "homogeneous volume (%d writes)" % changed if changed else None


def _apply_camera_cull(scene, settings, jrnl, payload, cache, skipped, progress):
    jrnl.set_prop(scene, "cycles.use_camera_cull", True, SPEED_TAG)
    # Distance cull is AND with camera cull — do not enable it here.
    guard_cache = {}
    tagged = 0
    for name in payload.get("objects") or ():
        obj = scene.objects.get(name)
        if obj is None:
            skipped.append(_skip("CAMERA_CULL", name, "object missing"))
            continue
        reason = _object_write_skip(obj, scene, guard_cache)
        if reason:
            skipped.append(_skip("CAMERA_CULL", name, reason))
            continue
        if getattr(obj, "type", "") in ("LIGHT", "VOLUME", "CAMERA"):
            skipped.append(_skip("CAMERA_CULL", name, "lights/volumes never culled"))
            continue
        if getattr(obj, "is_shadow_catcher", False):
            skipped.append(_skip("CAMERA_CULL", name, "shadow catcher"))
            continue
        if jrnl.set_prop(obj, "cycles.use_camera_cull", True, SPEED_TAG):
            tagged += 1
    return "camera cull on %d objects" % tagged


def _apply_offscreen_dicing(scene, settings, jrnl, payload, cache, skipped, progress):
    if not speed_solver._scene_has_adaptive_subdiv(scene):
        skipped.append(_skip("OFFSCREEN_DICING", "-", "no adaptive subdivision"))
        return None
    cycles = getattr(scene, "cycles", None)
    if cycles is None or not hasattr(cycles, "offscreen_dicing_scale"):
        skipped.append(_skip("OFFSCREEN_DICING", "-", "no offscreen_dicing_scale"))
        return None
    current = getattr(cycles, "offscreen_dicing_scale", None)
    target = payload.get("value", speed_solver.OFFSCREEN_DICING_SCALE)
    if not isinstance(current, (int, float)) or current >= target:
        skipped.append(_skip("OFFSCREEN_DICING", "-", "already at/above target"))
        return None
    if jrnl.set_prop(scene, "cycles.offscreen_dicing_scale", target):
        return "offscreen dicing scale %s" % target
    return None


def _apply_adaptive_subdiv(scene, settings, jrnl, payload, cache, skipped, progress):
    guard_cache = {}
    capped = 0
    for name in payload.get("objects") or ():
        obj = scene.objects.get(name)
        if obj is None:
            skipped.append(_skip("ADAPTIVE_SUBDIV_CAP", name, "object missing"))
            continue
        reason = _object_write_skip(obj, scene, guard_cache)
        if reason:
            skipped.append(_skip("ADAPTIVE_SUBDIV_CAP", name, reason))
            continue
        for mod in getattr(obj, "modifiers", ()):
            if getattr(mod, "type", "") != "SUBSURF":
                continue
            if '"' in getattr(mod, "name", ""):
                skipped.append(_skip("ADAPTIVE_SUBDIV_CAP", name,
                                     "modifier name contains '\"'"))
                continue
            path = 'modifiers["%s"].render_levels' % mod.name
            if jrnl.set_prop(obj, path, 0, SPEED_TAG):
                capped += 1
    return "adaptive-subdiv render_levels 0 on %d modifiers" % capped if capped else None


def _apply_animated_seed(scene, settings, jrnl, payload, cache, skipped, progress):
    if jrnl.set_prop(scene, "cycles.use_animated_seed", True, SPEED_TAG):
        return "animated seed on"
    return None


def _apply_compositor_gpu(scene, settings, jrnl, payload, cache, skipped, progress):
    if jrnl.set_prop(scene, "render.compositor_device", "GPU", SPEED_TAG):
        return "compositor on GPU"
    skipped.append(_skip("COMPOSITOR_GPU", "-",
                         "compositor_device unavailable or already GPU"))
    return None


def _apply_deform_mblur(scene, settings, jrnl, payload, cache, skipped, progress):
    guard_cache = {}
    changed = 0
    for name in payload.get("objects") or ():
        obj = scene.objects.get(name)
        if obj is None:
            skipped.append(_skip("DEFORM_MBLUR_OFF", name, "object missing"))
            continue
        reason = _object_write_skip(obj, scene, guard_cache)
        if reason:
            skipped.append(_skip("DEFORM_MBLUR_OFF", name, reason))
            continue
        if jrnl.set_prop(obj, "cycles.use_deform_motion", False, SPEED_TAG):
            changed += 1
    return "deform motion blur off on %d objects" % changed if changed else None


def _apply_hair_ribbons(scene, settings, jrnl, payload, cache, skipped, progress):
    if jrnl.set_prop(scene, "cycles_curves.shape", "RIBBONS", SPEED_TAG):
        return "hair/curves shape → ribbons"
    skipped.append(_skip("HAIR_RIBBONS", "-", "cycles_curves.shape unavailable"))
    return None


def _apply_pass_prune(scene, settings, jrnl, payload, cache, skipped, progress):
    used, _found, unknown = speed_solver._used_pass_props(scene)
    if unknown:
        skipped.append(_skip("PASS_PRUNE", "-", "compositor group not proven"))
        return None
    changed = 0
    for layer_name, prop in payload.get("passes") or ():
        if not isinstance(layer_name, str) or '"' in layer_name:
            skipped.append(_skip("PASS_PRUNE", str(layer_name),
                                 "view layer name unsafe for RNA path"))
            continue
        if (layer_name, prop) in used:
            skipped.append(_skip("PASS_PRUNE", layer_name,
                                 "compositor now reads %s" % prop))
            continue
        if prop == "use_pass_combined":
            skipped.append(_skip("PASS_PRUNE", layer_name, "never disable Combined"))
            continue
        path = 'view_layers["%s"].%s' % (layer_name, prop)
        if jrnl.set_prop(scene, path, False, SPEED_TAG):
            changed += 1
        else:
            skipped.append(_skip("PASS_PRUNE", layer_name,
                                 "pass %s unavailable or already off" % prop))
    return "unused passes off (%d)" % changed if changed else None


def _apply_crypto_prune(scene, settings, jrnl, payload, cache, skipped, progress):
    # ViewLayer is not a journal ID kind — write through the Scene so revert
    # can resolve the RNA path.
    changed = 0
    for layer_name, prop in payload.get("passes") or ():
        if not isinstance(layer_name, str) or '"' in layer_name:
            skipped.append(_skip("CRYPTO_PRUNE", str(layer_name),
                                 "view layer name unsafe for RNA path"))
            continue
        path = 'view_layers["%s"].%s' % (layer_name, prop)
        if jrnl.set_prop(scene, path, False, SPEED_TAG):
            changed += 1
        else:
            skipped.append(_skip("CRYPTO_PRUNE", layer_name,
                                 "pass %s unavailable or already off" % prop))
    return "cryptomatte passes off (%d)" % changed if changed else None


def _apply_device_gpu(scene, settings, jrnl, payload, cache, skipped, progress):
    if not payload.get("set_device"):
        skipped.append(_skip(
            "DEVICE_GPU", "-",
            "switch Cycles to GPU in Preferences > System > Cycles Render Devices"))
        return None
    if jrnl.set_prop(scene, "cycles.device", "GPU", SPEED_TAG):
        return "scene device → GPU Compute"
    skipped.append(_skip("DEVICE_GPU", "-", "cycles.device write did not stick"))
    return None


def _object_write_skip(obj, scene, guard_cache):
    from .. import compat
    override = getattr(getattr(obj, "scenequant", None), "override", "AUTO")
    if override != "AUTO":
        return "override %s" % override
    if compat.is_linked(obj):
        return "linked object"
    if not guards.in_object_mode(obj):
        return "object in %s mode" % getattr(obj, "mode", "?")
    if guards.used_outside_scene(obj, scene, guard_cache):
        return "used by other scenes"
    return None


_HANDLERS = {
    "LOCK_INTERFACE": _apply_lock,
    "APPLY_PERCEPTUAL_PATHS": _apply_paths,
    "ADAPTIVE_ON": _apply_adaptive_on,
    "THRESHOLD_CAP": _apply_threshold,
    "SAMPLES_CAP": _apply_samples_cap,
    "DENOISE_ON": _apply_denoise_on,
    "MIN_SAMPLES": _apply_min_samples,
    "PERSISTENT_DATA": _apply_persistent,
    "GPU_DENOISE": _apply_gpu_denoise,
    "DENOISE_PREFILTER": _apply_denoise_prefilter,
    "TRIM_OFFSCREEN": _apply_trim,
    "HIDE_OFFSCREEN_INSTANCES": _apply_hide_instances,
    "SUBDIV_TRIM": _apply_subdiv,
    "MICRO_EMITTERS": _apply_micro_emitters,
    "LIGHT_TREE": _apply_light_tree,
    "CAUSTICS_OFF": _apply_caustics_off,
    "PATH_GUIDING_OFF": _apply_path_guiding_off,
    "WORLD_MIS_NONE": _apply_world_mis_none,
    "LIGHT_SAMPLING_THRESHOLD": _apply_light_sampling_threshold,
    "VOLUME_BOUNCES_ZERO": _apply_volume_bounces_zero,
    "HOMOGENEOUS_VOLUME": _apply_homogeneous_volume,
    "CAMERA_CULL": _apply_camera_cull,
    "OFFSCREEN_DICING": _apply_offscreen_dicing,
    "ADAPTIVE_SUBDIV_CAP": _apply_adaptive_subdiv,
    "ANIMATED_SEED": _apply_animated_seed,
    "COMPOSITOR_GPU": _apply_compositor_gpu,
    "DEFORM_MBLUR_OFF": _apply_deform_mblur,
    "HAIR_RIBBONS": _apply_hair_ribbons,
    "PASS_PRUNE": _apply_pass_prune,
    "CRYPTO_PRUNE": _apply_crypto_prune,
    "DEVICE_GPU": _apply_device_gpu,
}
