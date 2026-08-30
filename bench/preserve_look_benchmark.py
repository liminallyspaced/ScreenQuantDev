"""Full-resolution Preserve Look benchmark for an already-open .blend.

Run through ``bench/run_preserve_look.ps1``.  The script never saves the blend;
all SceneQuant writes exist only in this background Blender process.
"""

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import bpy
import numpy as np


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import scenequant  # noqa: E402
from scenequant.analysis import sample_probe  # noqa: E402
from scenequant.analysis import visual_guard  # noqa: E402


def parse_args():
    raw = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--label", default="problem-scene")
    parser.add_argument("--frames", default="")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--no-auto-knee", action="store_true")
    return parser.parse_args(raw)


def file_sha256(path):
    if not path or not os.path.isfile(path):
        return None
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def git_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT),
            text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return None


def selected_frames(scene, text):
    if text:
        frames = []
        for value in text.split(","):
            frame = int(value.strip())
            if frame not in frames:
                frames.append(frame)
        return tuple(frames)
    return sample_probe.representative_frames(
        scene.frame_start, scene.frame_end, count=3)


def render_buffer(scene, frame, path):
    scene.frame_set(int(frame))
    scene.render.filepath = path
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


def render_pass(scene, frames, repeats, directory, prefix):
    timings = {}
    paths = {}
    for frame in frames:
        samples = []
        buffer = None
        for repeat in range(max(1, repeats)):
            exr = os.path.join(
                directory, "%s-%d-%d.exr" % (prefix, frame, repeat))
            buffer, elapsed = render_buffer(scene, frame, exr)
            samples.append(elapsed)
        path = os.path.join(directory, "%s-%d.npy" % (prefix, frame))
        np.save(path, buffer)
        paths[int(frame)] = path
        timings[str(frame)] = {
            "seconds": samples,
            "median_seconds": float(statistics.median(samples)),
        }
    return paths, timings


def timing_total(timings):
    return float(sum(item["median_seconds"] for item in timings.values()))


def cycles_devices():
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.get_devices()
        return [{"name": d.name, "type": d.type, "use": bool(d.use)}
                for d in prefs.devices]
    except Exception:
        return []


def main():
    args = parse_args()
    output = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    scene = bpy.context.scene
    if scene.render.engine != "CYCLES":
        raise RuntimeError("benchmark scene must use Cycles")
    if scene.camera is None:
        raise RuntimeError("benchmark scene needs an active camera")
    frames = selected_frames(scene, args.frames)
    original_frame = int(scene.frame_current)
    temp = tempfile.mkdtemp(prefix="scenequant-preserve-bench-")
    registered_here = not hasattr(bpy.types.Scene, "scenequant")
    if registered_here:
        scenequant.register()
    try:
        settings = scene.scenequant
        settings.speed_profile = "PRESERVE_LOOK"
        settings.speed_render_intent = "VIDEO" if len(frames) > 1 else "STILL"
        settings.video_probe_frames = min(7, max(2, len(frames)))
        settings.speed_visual_guard = True
        settings.speed_probe_knee = not args.no_auto_knee
        scene.render.image_settings.file_format = "OPEN_EXR"
        scene.render.image_settings.color_depth = "32"
        scene.render.image_settings.color_mode = "RGB"
        render_settings_before = {
            "cycles_device": getattr(scene.cycles, "device", None),
            "samples": getattr(scene.cycles, "samples", None),
            "adaptive_sampling": getattr(
                scene.cycles, "use_adaptive_sampling", None),
            "denoising": getattr(scene.cycles, "use_denoising", None),
        }

        baseline_paths, baseline_timings = render_pass(
            scene, frames, args.repeats, temp, "baseline")
        optimize_started = time.perf_counter()
        operator_result = sorted(bpy.ops.scenequant.make_it_fast('EXEC_DEFAULT'))
        optimize_seconds = time.perf_counter() - optimize_started
        optimized_paths, optimized_timings = render_pass(
            scene, frames, args.repeats, temp, "optimized")

        intent = "VIDEO" if len(frames) > 1 else "STILL"
        limits = visual_guard.thresholds(intent)
        frame_quality = {}
        frame_pass = True
        for frame in frames:
            baseline = np.load(baseline_paths[int(frame)], mmap_mode="r")
            optimized = np.load(optimized_paths[int(frame)], mmap_mode="r")
            metrics = sample_probe.delta_metrics(baseline, optimized)
            metrics["passed"] = (
                metrics["mean"] <= limits["mean"]
                and metrics["p95"] <= limits["p95"])
            frame_pass = frame_pass and metrics["passed"]
            frame_quality[str(frame)] = metrics

        temporal_quality = []
        temporal_pass = True
        for frame_a, frame_b in zip(frames, frames[1:]):
            baseline_a = np.load(baseline_paths[int(frame_a)], mmap_mode="r")
            baseline_b = np.load(baseline_paths[int(frame_b)], mmap_mode="r")
            optimized_a = np.load(optimized_paths[int(frame_a)], mmap_mode="r")
            optimized_b = np.load(optimized_paths[int(frame_b)], mmap_mode="r")
            metrics = visual_guard.temporal_residual_metrics(
                baseline_a, baseline_b, optimized_a, optimized_b)
            metrics["passed"] = (
                metrics["mean"] <= visual_guard.VIDEO_MEAN_EPS
                and metrics["p95"] <= visual_guard.VIDEO_P95_EPS)
            temporal_pass = temporal_pass and metrics["passed"]
            temporal_quality.append({
                "frames": [int(frame_a), int(frame_b)], **metrics,
            })

        baseline_total = timing_total(baseline_timings)
        optimized_total = timing_total(optimized_timings)
        saved_per_sequence = baseline_total - optimized_total
        speedup_pct = (
            (saved_per_sequence / baseline_total) * 100.0
            if baseline_total > 0 else None)
        break_even_sequences = (
            optimize_seconds / saved_per_sequence
            if saved_per_sequence > 0 else None)
        report_data = json.loads(settings.last_report or "{}")
        plan = report_data.get("speed_plan") or {}
        guard_data = plan.get("visual_guard") or {}
        render_settings_after = {
            "cycles_device": getattr(scene.cycles, "device", None),
            "samples": getattr(scene.cycles, "samples", None),
            "adaptive_sampling": getattr(
                scene.cycles, "use_adaptive_sampling", None),
            "denoising": getattr(scene.cycles, "use_denoising", None),
        }
        operator_ok = "FINISHED" in operator_result
        timing_pass = saved_per_sequence > 0
        guard_ok = not bool(guard_data.get("error"))
        passed = operator_ok and timing_pass and guard_ok and frame_pass and temporal_pass
        payload = {
            "schema": 1,
            "status": "PASS" if passed else "FAIL",
            "label": args.label,
            "scene": {
                "path": bpy.data.filepath or None,
                "sha256": file_sha256(bpy.data.filepath),
                "frame_start": int(scene.frame_start),
                "frame_end": int(scene.frame_end),
                "bench_frames": [int(frame) for frame in frames],
                "resolution": [int(scene.render.resolution_x),
                               int(scene.render.resolution_y),
                               int(scene.render.resolution_percentage)],
            },
            "machine": {
                "platform": platform.platform(),
                "processor": platform.processor(),
                "logical_cpu_count": os.cpu_count(),
                "blender": bpy.app.version_string,
                "cycles_devices": cycles_devices(),
            },
            "scenequant_commit": git_commit(),
            "settings": {
                "profile": "PRESERVE_LOOK",
                "intent": intent,
                "repeats": max(1, args.repeats),
                "auto_knee": not args.no_auto_knee,
                "visual_guard": True,
                "before": render_settings_before,
                "after": render_settings_after,
            },
            "operator_result": operator_result,
            "timing": {
                "baseline": baseline_timings,
                "optimized": optimized_timings,
                "baseline_sequence_median_seconds": baseline_total,
                "optimized_sequence_median_seconds": optimized_total,
                "speedup_percent": speedup_pct,
                "optimization_overhead_seconds": optimize_seconds,
                "break_even_sequences": break_even_sequences,
                "timing_gate_passed": timing_pass,
            },
            "quality": {
                "thresholds": limits,
                "frames": frame_quality,
                "temporal_residuals": temporal_quality,
                "frame_gate_passed": frame_pass,
                "temporal_gate_passed": temporal_pass,
            },
            "operational_gate_passed": operator_ok and guard_ok,
            "visual_guard": guard_data,
            "plan": {
                "est_pct": plan.get("est_pct"),
                "actions": [a.get("kind") for a in plan.get("actions", [])],
                "withheld_kinds": plan.get("withheld_kinds", []),
            },
        }
        with open(output, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        print("SCENEQUANT_PRESERVE_BENCH: %s" % payload["status"])
        print("SCENEQUANT_PRESERVE_BENCH_REPORT: %s" % output)
    finally:
        scene.frame_set(original_frame)
        if registered_here:
            scenequant.unregister()
        import shutil
        shutil.rmtree(temp, ignore_errors=True)


if __name__ == "__main__":
    main()
