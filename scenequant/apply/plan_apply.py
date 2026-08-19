# Plan execution: the one place that turns solver plan dicts into journaled
# apply calls, shared by Fit-to-Budget and the standalone lever operators
# (which run single-action plans). No UI here: progress is an optional
# callback, the scene is passed in, and every write goes through the journal
# handed in (invariant #1).

import bpy

from ..analysis import coverage as coverage_analysis
from ..analysis import dedup_scan, memory_model
from . import guards, objects_apply, textures_apply

DEFAULT_TEX_LIMIT = "2048"


class RunScopedJournal:
    """Journal facade stamping one operator invocation's run id onto every
    write, so a mid-apply exception rolls back all-or-nothing via
    journal.revert_run(run_id). Everything else passes through."""

    def __init__(self, jrnl, run_id):
        self.journal = jrnl
        self.run_id = run_id

    def set_prop(self, datablock, rna_path, value, tag, **kwargs):
        # Forwarded so this facade stays substitutable for the journal, but the
        # run being applied always owns the stamp: a caller's run_id cannot
        # smuggle a write out of this run's rollback set.
        kwargs["run_id"] = self.run_id
        return self.journal.set_prop(datablock, rna_path, value, tag, **kwargs)

    def record_action(self, kind, payload, tag):
        self.journal.record_action(kind, payload, tag, run_id=self.run_id)

    def __getattr__(self, name):
        return getattr(self.journal, name)


def apply_plan(scene, settings, jrnl, plan, coverage_map=None, progress=None):
    """Execute plan["actions"] in order.

    coverage_map: precomputed {name: CoverageInfo} (e.g. from an operator's
    invoke pass) — computed once on demand when None. progress: optional
    (index, total, label) callable, forwarded into per-item apply loops.
    Returns {"applied": int, "outcomes": [str],
             "skipped": [{"source", "name", "reason"}]}.
    """
    cache = {"cov": coverage_map}
    applied = 0
    outcomes = []
    skipped = []
    actions = plan.get("actions") or []
    for index, action in enumerate(actions):
        kind = action.get("kind") or "?"
        guards.notify_progress(progress, index, len(actions), kind)
        handler = _HANDLERS.get(kind)
        if handler is None:
            skipped.append(_skip(kind, "-", f"unknown plan action: {kind}"))
            continue
        outcome = handler(scene, settings, jrnl, action.get("payload") or {},
                          cache, skipped, progress)
        if outcome:
            outcomes.append(outcome)
        applied += 1
    return {"applied": applied, "outcomes": outcomes, "skipped": skipped}


def _skip(source, name, reason):
    return {"source": str(source), "name": str(name), "reason": str(reason)}


def _collect_skips(skipped, source, result):
    for name, reason in (result or {}).get("skipped", ()):
        skipped.append(_skip(source, name, reason))


def _plan_coverage(scene, settings, cache, progress=None):
    if cache.get("cov") is None:
        cache["cov"] = coverage_analysis.compute_coverage(
            scene, scene.objects,
            frame_samples=settings.coverage_frame_samples,
            quality_factor=settings.quality_factor,
            progress=progress,
        )
    return cache["cov"]


def _apply_dedup(scene, settings, jrnl, payload, cache, skipped, progress):
    # Groups recomputed fresh: correct regardless of solver payload shape, and
    # the detailed scan surfaces its skip reasons instead of discarding them.
    mesh_scan = dedup_scan.scan_meshes(scene)
    image_scan = dedup_scan.scan_images()
    for entry in mesh_scan["skipped"]:
        skipped.append(_skip("mesh scan", entry.get("name"), entry.get("reason")))
    for entry in image_scan["skipped"]:
        skipped.append(_skip("image scan", entry.get("name"), entry.get("reason")))
    mesh_result = objects_apply.relink_duplicate_meshes(
        mesh_scan["groups"], jrnl, scene=scene)
    image_result = objects_apply.relink_duplicate_images(
        image_scan["groups"], jrnl, memory_model.images_used_by_render(scene))
    _collect_skips(skipped, "dedup", mesh_result)
    _collect_skips(skipped, "dedup", image_result)
    saved = mesh_result.get("saved_mb", 0.0) + image_result.get("saved_mb", 0.0)
    return (f"dedup merged {mesh_result.get('merged', 0)} meshes + "
            f"{image_result.get('merged', 0)} images (~{saved:.0f} MB)")


def _apply_half_float(scene, settings, jrnl, payload, cache, skipped, progress):
    changed = textures_apply.set_half_precision(
        _half_float_images(scene, payload), jrnl, scene=scene)
    return f"half precision on {changed} float images"


def _apply_trim(scene, settings, jrnl, payload, cache, skipped, progress):
    cov = _plan_coverage(scene, settings, cache, progress)
    result = objects_apply.trim_offscreen(
        scene, cov, jrnl,
        keep_reflections=settings.trim_keep_reflections, progress=progress)
    _collect_skips(skipped, "trim", result)
    return f"ray visibility trimmed on {result.get('trimmed', 0)} objects"


def _apply_subdiv_trim(scene, settings, jrnl, payload, cache, skipped, progress):
    cov = _plan_coverage(scene, settings, cache, progress)
    result = objects_apply.trim_subdiv(scene, cov, jrnl, progress=progress)
    _collect_skips(skipped, "subdiv trim", result)
    return f"render subdivision capped on {result.get('capped', 0)} objects"


def _apply_quantize(scene, settings, jrnl, payload, cache, skipped, progress):
    targets = _quantize_targets(payload)
    if not targets:
        # No explicit targets (standalone operator direct-execute): size every
        # render-used image from coverage, exactly like the preview would.
        cov = _plan_coverage(scene, settings, cache, progress)
        result = textures_apply.quantize_by_coverage(
            scene, cov, jrnl, settings, progress=progress)
        _collect_skips(skipped, "quantize", result)
        return (f"quantized {result.get('changed', 0)} textures "
                f"(~{result.get('saved_mb', 0.0):.0f} MB)")
    users_map = memory_model.images_used_by_render(scene)
    changed = 0
    items = sorted(targets.items())
    for index, (name, target_px) in enumerate(items):
        guards.notify_progress(progress, index, len(items), name)
        image = bpy.data.images.get(name)
        if image is None:
            skipped.append(_skip("quantize", name, "image missing"))
            continue
        users = users_map.get(name)
        if not users:
            skipped.append(_skip("quantize", name, "no render users found"))
            continue
        reason = textures_apply.quantize_image(
            image, int(target_px), jrnl, users, scene=scene)
        if reason is not None:
            skipped.append(_skip("quantize", name, reason))
            continue
        changed += 1
    return f"quantized {changed} textures"


def _apply_tex_limit(scene, settings, jrnl, payload, cache, skipped, progress):
    size = _tex_limit_size(payload)
    textures_apply.apply_texture_limit(scene, jrnl, size)
    return f"global texture clamp {size}px"


_HANDLERS = {
    "DEDUP": _apply_dedup,
    "HALF_FLOAT": _apply_half_float,
    "TRIM_OFFSCREEN": _apply_trim,
    "SUBDIV_TRIM": _apply_subdiv_trim,
    "QUANTIZE": _apply_quantize,
    "TEX_LIMIT": _apply_tex_limit,
}


def _half_float_images(scene, payload):
    names = payload.get("images") or payload.get("image_names")
    if not names or not isinstance(names, (list, tuple)):
        names = list(memory_model.images_used_by_render(scene))
    found = (bpy.data.images.get(str(name)) for name in names)
    return [image for image in found if image is not None and image.is_float]


def _quantize_targets(payload):
    for key in ("targets", "images", "per_image_targets"):
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    # tolerate a flat {image_name: px} payload shape
    return {k: v for k, v in payload.items() if isinstance(v, (int, float))}


def _tex_limit_size(payload):
    value = payload.get("size") or payload.get("limit") or payload.get("texture_limit")
    return str(value) if value else DEFAULT_TEX_LIMIT
