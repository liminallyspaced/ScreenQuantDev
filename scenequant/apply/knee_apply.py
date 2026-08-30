# Live sample-knee probe. Temporary render-setting writes are journal-tagged
# 'probe' and must be reverted before any real samples cap (tag 'speed').
# bpy is imported lazily so unit tests never pull it in.

import os
import shutil
import tempfile

from ..analysis import sample_probe
from ..planning import presets
from . import settings_apply

PROBE_TAG = "probe"
SPEED_TAG = "speed"
PROBE_SCALE = 25
AUTO_PROBE_SCALE = 25
KNEE_FLOOR = 64


def apply_knee(scene, jrnl, knee, probe_scale=100, eps=None,
               already_adaptive=False, floor=KNEE_FLOOR):
    """MODE_MIN cycles.samples to the padded knee. Never raises. Returns dict."""
    current = getattr(getattr(scene, "cycles", None), "samples", 0)
    result = {
        "knee": knee,
        "applied": False,
        "reason": "",
        "target": None,
    }
    used_eps = sample_probe.AUTO_EPS if eps is None else eps
    if knee is None:
        result["reason"] = (
            "ladder never converged (eps=%.3f)" % used_eps)
        return result
    target = sample_probe.pad_cheap_probe_knee(
        knee, current, probe_scale, floor=floor,
        already_adaptive=already_adaptive)
    result["target"] = target
    if not isinstance(current, (int, float)) or current <= target:
        result["reason"] = "current samples %s already at/under knee %d" % (
            current, target)
        return result
    changes = settings_apply._apply_entries(
        scene, jrnl,
        (("cycles", "samples", target, presets.MODE_MIN),),
        SPEED_TAG)
    result["applied"] = bool(changes)
    result["reason"] = (
        "samples %s → %d" % (current, target) if changes else "no write")
    return result


def prepare_probe_settings(scene, jrnl, scale=PROBE_SCALE,
                           force_denoise=True):
    """Journal the still-image probe setup. Caller reverts the probe run.

    The probe always uses linear EXR with the compositor off. Historical
    Aggressive probing may force OIDN; Preserve Look and Video pass None so the
    artist's existing render-denoise choice is measured unchanged.
    """
    jrnl.set_prop(scene, "render.resolution_percentage", scale, PROBE_TAG)
    # Preserve Look and Video must measure the artist's actual denoise choice.
    # Forcing OIDN here can make a low-sample image appear converged, then leave
    # an originally raw/no-denoise final render undersampled and smeared.
    if force_denoise is not None:
        jrnl.set_prop(
            scene, "cycles.use_denoising", bool(force_denoise), PROBE_TAG)
    if hasattr(getattr(scene, "render", None), "use_compositing"):
        jrnl.set_prop(scene, "render.use_compositing", False, PROBE_TAG)
    jrnl.set_prop(scene, "render.use_lock_interface", True, PROBE_TAG)
    image_settings = getattr(getattr(scene, "render", None), "image_settings", None)
    if image_settings is not None:
        jrnl.set_prop(scene, "render.image_settings.file_format", "OPEN_EXR", PROBE_TAG)
        if hasattr(image_settings, "color_depth"):
            jrnl.set_prop(scene, "render.image_settings.color_depth", "32", PROBE_TAG)
        if hasattr(image_settings, "color_mode"):
            jrnl.set_prop(scene, "render.image_settings.color_mode", "RGB", PROBE_TAG)


def make_blender_renderer(scene, jrnl, scale=PROBE_SCALE,
                          force_denoise=True):
    """render_at(n) → numpy RGB(A) buffer. Prepares probe settings once."""
    import bpy
    import numpy as np

    prepare_probe_settings(
        scene, jrnl, scale=scale, force_denoise=force_denoise)
    tmp = tempfile.mkdtemp(prefix="scenequant-knee-")

    def render_at(samples):
        jrnl.set_prop(scene, "cycles.samples", int(samples), PROBE_TAG)
        path = os.path.join(tmp, "knee_%d.exr" % int(samples))
        jrnl.set_prop(scene, "render.filepath", path, PROBE_TAG)
        bpy.ops.render.render(write_still=True)
        image = bpy.data.images.load(path)
        try:
            cs = getattr(image, "colorspace_settings", None)
            if cs is not None and hasattr(cs, "name"):
                try:
                    cs.name = "Non-Color"
                except TypeError:
                    pass
            pixels = np.array(image.pixels[:], dtype=np.float32)
            width, height = image.size
            channels = max(1, pixels.size // max(1, width * height))
            return pixels.reshape(height, width, channels)
        finally:
            bpy.data.images.remove(image)

    render_at.cleanup = lambda: shutil.rmtree(tmp, ignore_errors=True)
    return render_at


def auto_knee(scene, already_adaptive=False, profile="AGGRESSIVE",
              intent="STILL", video_frame_count=3):
    """Measured sample floor. Video fails closed across representative frames.

    Preserve Look never forces denoising during the probe.  Video checks several
    frames and applies only the highest knee, so an easy establishing frame
    cannot undersample a difficult close-up later in the shot.
    """
    import uuid

    from .. import journal
    from . import plan_apply

    result = {
        "knee": None,
        "applied": False,
        "reason": "",
        "rungs": [],
        "frames": [],
        "frame_knees": {},
    }
    if getattr(scene, "camera", None) is None:
        result["reason"] = "no scene camera"
        return result
    current = getattr(getattr(scene, "cycles", None), "samples", 0)
    rungs = sample_probe.rungs_for_current(current)
    if not rungs:
        result["reason"] = "samples %s too low to probe" % current
        return result
    preserve = profile == "PRESERVE_LOOK"
    video = intent == "VIDEO"
    if video:
        frames = sample_probe.representative_frames(
            getattr(scene, "frame_start", 1),
            getattr(scene, "frame_end", 1),
            count=video_frame_count,
        )
        eps = sample_probe.VIDEO_EPS
        p95_eps = sample_probe.VIDEO_P95_EPS
        floor = sample_probe.VIDEO_KNEE_FLOOR
    else:
        frames = (int(getattr(scene, "frame_current", 1) or 1),)
        eps = sample_probe.PRESERVE_EPS if preserve else sample_probe.AUTO_EPS
        p95_eps = sample_probe.VIDEO_P95_EPS if preserve else None
        floor = KNEE_FLOOR
    force_denoise = None if preserve or video else True
    result["frames"] = list(frames)

    jrnl = journal.Journal.load(scene)
    probe_id = uuid.uuid4().hex
    scoped = plan_apply.RunScopedJournal(jrnl, probe_id)
    original_frame = int(getattr(scene, "frame_current", frames[0]) or frames[0])
    frame_knees = []
    try:
        for frame in frames:
            frame_set = getattr(scene, "frame_set", None)
            if callable(frame_set):
                frame_set(int(frame))
            render_at = make_blender_renderer(
                scene, scoped, scale=AUTO_PROBE_SCALE,
                force_denoise=force_denoise)
            try:
                knee, ladder = sample_probe.run_knee_ladder(
                    render_at, rungs=rungs, eps=eps, p95_eps=p95_eps)
            finally:
                render_at.cleanup()
            result["rungs"] = sorted(set(result["rungs"]) | set(ladder.keys()))
            result["frame_knees"][str(frame)] = knee
            if knee is None:
                result["reason"] = (
                    "frame %d ladder did not converge; samples unchanged" % frame)
                break
            frame_knees.append(int(knee))
    except Exception as error:
        result["reason"] = "probe failed: %s" % error
    finally:
        try:
            frame_set = getattr(scene, "frame_set", None)
            if callable(frame_set):
                frame_set(original_frame)
        finally:
            jrnl.revert_run(probe_id)
            jrnl.save(scene)

    if result["reason"] or len(frame_knees) != len(frames):
        return result
    result["knee"] = max(frame_knees)

    apply_id = uuid.uuid4().hex
    apply_scoped = plan_apply.RunScopedJournal(jrnl, apply_id)
    try:
        applied = apply_knee(
            scene, apply_scoped, result["knee"],
            probe_scale=AUTO_PROBE_SCALE, eps=eps,
            already_adaptive=already_adaptive, floor=floor)
        result.update(applied)
        result["rungs"] = result.get("rungs") or sorted(
            sample_probe.rungs_for_current(current) or ())
    except Exception as error:
        jrnl.revert_run(apply_id)
        result["reason"] = "knee apply failed: %s" % error
    jrnl.save(scene)
    return result
