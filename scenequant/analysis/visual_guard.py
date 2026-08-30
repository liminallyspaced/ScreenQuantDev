"""Pure image-quality policy for Preserve Look action-group probes.

The Blender-facing renderer and journal transactions live in
``apply.visual_guard``.  Keeping grouping and acceptance here makes the
quality contract unit-testable without importing bpy.
"""

from . import sample_probe


PRESERVE_MEAN_EPS = 0.003
PRESERVE_P95_EPS = 0.012
VIDEO_MEAN_EPS = 0.002
VIDEO_P95_EPS = 0.008


_GROUPS = {
    "DEVICE_GPU": ("backend", "Render backend"),
    "GPU_DENOISE": ("backend", "Render backend"),
    "ADAPTIVE_ON": ("sampling", "Sampling controls"),
    "MIN_SAMPLES": ("sampling", "Sampling controls"),
    "PERSISTENT_DATA": ("runtime", "Render reuse and runtime"),
    "LOCK_INTERFACE": ("runtime", "Render reuse and runtime"),
    "COMPOSITOR_GPU": ("runtime", "Render reuse and runtime"),
    "DEFORM_MBLUR_OFF": ("proven_noop", "Proven dead render work"),
    "PATH_GUIDING_OFF": ("proven_noop", "Proven dead render work"),
    "WORLD_MIS_NONE": ("proven_noop", "Proven dead render work"),
    "VOLUME_BOUNCES_ZERO": ("proven_noop", "Proven dead render work"),
    "HOMOGENEOUS_VOLUME": ("proven_noop", "Proven dead render work"),
}


def group_speed_actions(actions):
    """Stable logical groups, with unknown kinds isolated fail-safe.

    Unknown actions never get bundled with a known-safe group.  If a future
    Preserve Look action is added without a policy entry, its probe and
    rollback affect only that action.
    """
    groups = []
    by_key = {}
    for action in actions or ():
        kind = action.get("kind") if isinstance(action, dict) else None
        key, label = _GROUPS.get(
            kind, ("other:%s" % (kind or "?"), kind or "Unknown action"))
        group = by_key.get(key)
        if group is None:
            group = {"key": key, "label": label, "actions": []}
            by_key[key] = group
            groups.append(group)
        group["actions"].append(action)
    return groups


def thresholds(intent="STILL"):
    if intent == "VIDEO":
        return {"mean": VIDEO_MEAN_EPS, "p95": VIDEO_P95_EPS}
    return {"mean": PRESERVE_MEAN_EPS, "p95": PRESERVE_P95_EPS}


def evaluate_frame_set(baselines, candidates, intent="STILL"):
    """Compare matching ``{frame: buffer}`` maps and return an audit record."""
    expected = set(baselines or {})
    actual = set(candidates or {})
    if not expected or expected != actual:
        return {
            "passed": False,
            "reason": "probe frame set incomplete",
            "thresholds": thresholds(intent),
            "frames": {},
        }
    limits = thresholds(intent)
    records = {}
    passed = True
    worst_frame = None
    worst_ratio = -1.0
    for frame in sorted(expected):
        metrics = sample_probe.delta_metrics(
            baselines[frame], candidates[frame])
        frame_passed = (
            metrics["mean"] <= limits["mean"]
            and metrics["p95"] <= limits["p95"]
        )
        metrics["passed"] = frame_passed
        records[str(frame)] = metrics
        passed = passed and frame_passed
        ratio = max(
            metrics["mean"] / max(limits["mean"], 1e-12),
            metrics["p95"] / max(limits["p95"], 1e-12),
        )
        if ratio > worst_ratio:
            worst_ratio = ratio
            worst_frame = int(frame)
    return {
        "passed": passed,
        "reason": "within Preserve Look limits" if passed else (
            "frame %s exceeded Preserve Look limits" % worst_frame),
        "thresholds": limits,
        "worst_frame": worst_frame,
        "frames": records,
    }


def temporal_residual_metrics(baseline_a, baseline_b,
                              candidate_a, candidate_b):
    """Delta between baseline motion/change and optimized motion/change.

    This catches temporal smearing or crawling that can be small in each still
    yet inconsistent between adjacent representative frames.
    """
    a0 = sample_probe._as_float_rgb(baseline_a)
    a1 = sample_probe._as_float_rgb(baseline_b)
    b0 = sample_probe._as_float_rgb(candidate_a)
    b1 = sample_probe._as_float_rgb(candidate_b)
    if a0.shape != a1.shape or a0.shape != b0.shape or a0.shape != b1.shape:
        raise ValueError("temporal buffers must have the same RGB shape")
    return sample_probe.delta_metrics(a1 - a0, b1 - b0)
