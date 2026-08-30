"""Automatic before/after rendering and rollback for Preserve Look groups."""

import os
import shutil
import tempfile
import time
import uuid

from ..analysis import sample_probe
from ..analysis import visual_guard as guard_policy
from . import plan_apply, speed_apply


PROBE_TAG = "visual_guard_probe"
PROBE_SCALE = 16
PROBE_SAMPLES = 128


def prepare_probe_settings(scene, jrnl, scale=PROBE_SCALE,
                           samples=PROBE_SAMPLES):
    """Reduce only resolution and sample ceiling; preserve the image pipeline."""
    jrnl.set_prop(
        scene, "render.resolution_percentage", int(scale), PROBE_TAG)
    cycles = getattr(scene, "cycles", None)
    current = getattr(cycles, "samples", None)
    if isinstance(current, (int, float)) and current > samples:
        jrnl.set_prop(scene, "cycles.samples", int(samples), PROBE_TAG)
    image_settings = getattr(getattr(scene, "render", None), "image_settings", None)
    if image_settings is not None:
        jrnl.set_prop(
            scene, "render.image_settings.file_format", "OPEN_EXR", PROBE_TAG)
        if hasattr(image_settings, "color_depth"):
            jrnl.set_prop(
                scene, "render.image_settings.color_depth", "32", PROBE_TAG)
        if hasattr(image_settings, "color_mode"):
            jrnl.set_prop(
                scene, "render.image_settings.color_mode", "RGB", PROBE_TAG)


def make_blender_renderer(scene, jrnl):
    """Return an EXR-backed renderer that also works in background Blender."""
    import bpy
    import numpy as np

    directory = tempfile.mkdtemp(prefix="scenequant-visual-guard-")
    counter = [0]

    def render_frame(target_scene, frame):
        frame_set = getattr(target_scene, "frame_set", None)
        if callable(frame_set):
            frame_set(int(frame))
        counter[0] += 1
        path = os.path.join(
            directory, "frame_%d_%d.exr" % (int(frame), counter[0]))
        jrnl.set_prop(target_scene, "render.filepath", path, PROBE_TAG)
        started = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        elapsed = time.perf_counter() - started
        image = bpy.data.images.load(path)
        try:
            colorspace = getattr(image, "colorspace_settings", None)
            if colorspace is not None and hasattr(colorspace, "name"):
                try:
                    colorspace.name = "Non-Color"
                except TypeError:
                    pass
            pixels = np.array(image.pixels[:], dtype=np.float32)
            width, height = image.size
            channels = max(1, pixels.size // max(1, width * height))
            return pixels.reshape(height, width, channels), float(elapsed)
        finally:
            bpy.data.images.remove(image)

    render_frame.cleanup = lambda: shutil.rmtree(directory, ignore_errors=True)
    return render_frame


def _frames(scene, intent, frame_count):
    if intent == "VIDEO":
        return sample_probe.representative_frames(
            getattr(scene, "frame_start", 1),
            getattr(scene, "frame_end", 1),
            count=frame_count,
        )
    return (int(getattr(scene, "frame_current", 1) or 1),)


def _capture(scene, frames, renderer):
    buffers = {}
    seconds = {}
    for frame in frames:
        buffer, elapsed = renderer(scene, int(frame))
        buffers[int(frame)] = buffer
        seconds[str(int(frame))] = float(elapsed)
    return buffers, seconds


def _rollback_runs(jrnl, run_ids):
    reverted = 0
    skipped = 0
    for run_id in reversed(run_ids):
        reverted += int(jrnl.revert_run(run_id) or 0)
        skipped += int(getattr(jrnl, "skipped_on_revert", 0) or 0)
    return reverted, skipped


def run_guarded_speed_plan(scene, settings, jrnl, plan, coverage_map=None,
                           progress=None, mem=None, frame_count=3,
                           renderer=None, prepare_probe=True):
    """Apply each logical group, render, and immediately reject visual drift.

    ``jrnl`` is the base Journal, not an already run-scoped facade: each group
    needs its own run id so one failed group can be reverted without touching
    previously accepted groups.  Any infrastructure exception rolls back every
    group accepted by this invocation.
    """
    owns_renderer = renderer is None
    actions = speed_apply._plan_actions(plan)
    intent = (plan.get("intent", "STILL") if isinstance(plan, dict)
              else getattr(plan, "intent", "STILL"))
    frames = _frames(scene, intent, frame_count)
    original_frame = int(getattr(scene, "frame_current", frames[0]) or frames[0])
    probe_id = uuid.uuid4().hex
    accepted_ids = []
    guard = {
        "enabled": True,
        "profile": "PRESERVE_LOOK",
        "intent": intent,
        "scale_pct": PROBE_SCALE if prepare_probe else None,
        "sample_ceiling": PROBE_SAMPLES if prepare_probe else None,
        "frames": list(frames),
        "baseline_seconds": {},
        "groups": [],
        "accepted": 0,
        "rejected": 0,
        "error": "",
    }
    result = {"applied": 0, "applied_kinds": [],
              "outcomes": [], "skipped": [],
              "visual_guard": guard}
    if not actions:
        guard["reason"] = "no action groups to verify"
        return result
    probe_scoped = plan_apply.RunScopedJournal(jrnl, probe_id)
    pending_id = None
    try:
        if prepare_probe:
            prepare_probe_settings(scene, probe_scoped)
        if renderer is None:
            renderer = make_blender_renderer(scene, probe_scoped)
        baselines, baseline_seconds = _capture(scene, frames, renderer)
        guard["baseline_seconds"] = baseline_seconds
        groups = guard_policy.group_speed_actions(actions)
        for index, group in enumerate(groups):
            group_id = uuid.uuid4().hex
            pending_id = group_id
            scoped = plan_apply.RunScopedJournal(jrnl, group_id)
            group_result = speed_apply.apply_speed_plan(
                scene, settings, scoped, {"actions": group["actions"]},
                coverage_map=coverage_map, progress=progress, mem=mem)
            journaled = sum(
                1 for entry in getattr(jrnl, "entries", ())
                if entry.get("run") == group_id)
            record = {
                "key": group["key"],
                "label": group["label"],
                "actions": [a.get("kind", "?") for a in group["actions"]],
                "status": "no-op",
                "applied": int(group_result.get("applied", 0) or 0),
                "applied_kinds": list(group_result.get("applied_kinds") or ()),
                "journal_entries": journaled,
                "render_seconds": {},
            }
            result["skipped"].extend(group_result.get("skipped") or ())
            if not group_result.get("applied"):
                if journaled:
                    reverted, revert_skipped = _rollback_runs(jrnl, [group_id])
                    record["status"] = "inconsistent-rolled-back"
                    record["reverted"] = reverted
                    record["rollback_skipped"] = revert_skipped
                    guard["rejected"] += 1
                    result["skipped"].append({
                        "source": "visual_guard", "name": group["label"],
                        "reason": (
                            "journaled writes had no applied outcome; group rolled back"),
                    })
                    if revert_skipped:
                        guard["groups"].append(record)
                        raise RuntimeError(
                            "%s inconsistent rollback left %d journal entry(ies) pending" % (
                                group["label"], revert_skipped))
                pending_id = None
                guard["groups"].append(record)
                continue
            guards_total = max(1, len(groups))
            if progress is not None:
                progress(index, guards_total, "verify %s" % group["label"])
            candidates, render_seconds = _capture(scene, frames, renderer)
            verdict = guard_policy.evaluate_frame_set(
                baselines, candidates, intent=intent)
            record["render_seconds"] = render_seconds
            record["quality"] = verdict
            if verdict["passed"]:
                record["status"] = "accepted"
                accepted_ids.append(group_id)
                pending_id = None
                guard["accepted"] += 1
                result["applied"] += int(group_result["applied"])
                result["applied_kinds"].extend(
                    group_result.get("applied_kinds") or ())
                result["outcomes"].extend(group_result.get("outcomes") or ())
            else:
                reverted, revert_skipped = _rollback_runs(jrnl, [group_id])
                record["status"] = "rejected-rolled-back"
                record["reverted"] = reverted
                record["rollback_skipped"] = revert_skipped
                guard["rejected"] += 1
                reason = verdict.get("reason") or "visual delta exceeded"
                for kind in record["actions"]:
                    result["skipped"].append({
                        "source": "visual_guard", "name": kind,
                        "reason": "%s; group rolled back" % reason,
                    })
                if revert_skipped:
                    guard["groups"].append(record)
                    raise RuntimeError(
                        "%s rollback left %d journal entry(ies) pending" % (
                            group["label"], revert_skipped))
                pending_id = None
            guard["groups"].append(record)
    except Exception as error:
        rollback_ids = list(accepted_ids)
        if pending_id is not None and pending_id not in rollback_ids:
            rollback_ids.append(pending_id)
        reverted, revert_skipped = _rollback_runs(jrnl, rollback_ids)
        guard["error"] = str(error)
        guard["accepted"] = 0
        guard["rolled_back_on_error"] = reverted
        guard["rollback_skipped"] = revert_skipped
        result["applied"] = 0
        result["applied_kinds"] = []
        result["outcomes"] = []
        for record in guard["groups"]:
            if record.get("status") == "accepted":
                record["status"] = "rolled-back-on-error"
        result["skipped"].append({
            "source": "visual_guard", "name": "PRESERVE_LOOK",
            "reason": "visual guard failed closed: %s" % error,
        })
    finally:
        try:
            frame_set = getattr(scene, "frame_set", None)
            if callable(frame_set):
                frame_set(original_frame)
        finally:
            try:
                if owns_renderer and renderer is not None:
                    renderer.cleanup()
            finally:
                _rollback_runs(jrnl, [probe_id])
    return result
