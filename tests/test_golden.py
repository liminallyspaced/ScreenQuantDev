# Golden-diff render test — MANUAL / CI ONLY. Excluded from tests/run_all.ps1
# defaults because it RENDERS (run_all only includes it with -IncludeGolden;
# never run it while a benchmark is using the GPU/CPU).
#   blender -b --factory-startup bench/bad_scene.blend \
#       --python-exit-code 1 --python tests/test_golden.py
# Self-relative goldens (review P5.3): renders its own baseline at
# 480x270/16spp/fixed-seed/CPU, applies one lever at a time, re-renders and
# numpy-diffs via bench/diff_images.py. Encodes the measured 0.078% production
# diff as an automated bound:
#   - dedup must be pixel-identical (it only relinks byte-identical data)
#   - quantize must stay under a small perceptual tolerance
#   - revert must restore the baseline pixels exactly (the product promise)

import os
import sys
import tempfile

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness  # noqa: E402  (side effect: repo root on sys.path)
from _harness import PROJECT_ROOT, check, finish, section  # noqa: E402

sys.path.insert(0, os.path.join(PROJECT_ROOT, "bench"))
from diff_images import diff_stats  # noqa: E402

QUANTIZE_MEAN_TOLERANCE = 0.002  # ~2.5x the measured 0.078% production diff
QUANTIZE_P99_TOLERANCE = 0.10


def configure_render(scene):
    """Small, deterministic and GPU-free so diffs measure the levers only."""
    render = scene.render
    render.resolution_x, render.resolution_y = 480, 270
    render.resolution_percentage = 100
    render.image_settings.file_format = "PNG"
    cycles = scene.cycles
    cycles.device = 'CPU'
    cycles.samples = 16
    cycles.use_adaptive_sampling = False
    cycles.seed = 0
    cycles.use_denoising = False


def render_to(scene, out_dir, name):
    path = os.path.join(out_dir, name + ".png")
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


def main():
    import scenequant
    scenequant.register()
    scene = bpy.context.scene
    configure_render(scene)
    out_dir = tempfile.mkdtemp(prefix="sq_golden_")
    print(f"golden renders in: {out_dir}")

    section("baseline")
    baseline = render_to(scene, out_dir, "baseline")
    check(os.path.exists(baseline), "baseline rendered")

    section("dedup is pixel-identical")
    result = bpy.ops.scenequant.dedup()
    check(result == {"FINISHED"}, "dedup returns FINISHED")
    stats = diff_stats(baseline, render_to(scene, out_dir, "dedup"))
    print(f"  dedup diff: {stats}")
    check(stats["max"] == 0.0, f"dedup changed no pixel (max {stats['max']:.6f})")

    section("quantize stays under tolerance")
    result = bpy.ops.scenequant.quantize_textures()
    check(result == {"FINISHED"}, "quantize returns FINISHED")
    stats = diff_stats(baseline, render_to(scene, out_dir, "quantize"))
    print(f"  quantize diff: {stats}")
    check(stats["mean"] <= QUANTIZE_MEAN_TOLERANCE,
          f"quantize mean diff {stats['mean']:.5f} <= {QUANTIZE_MEAN_TOLERANCE}")
    check(stats["p99"] <= QUANTIZE_P99_TOLERANCE,
          f"quantize p99 diff {stats['p99']:.5f} <= {QUANTIZE_P99_TOLERANCE}")

    section("revert restores the baseline exactly")
    result = bpy.ops.scenequant.revert_all()
    check(result == {"FINISHED"}, "revert returns FINISHED")
    stats = diff_stats(baseline, render_to(scene, out_dir, "reverted"))
    print(f"  revert diff: {stats}")
    check(stats["max"] == 0.0,
          f"revert restored every pixel (max {stats['max']:.6f})")
    finish()


main()
