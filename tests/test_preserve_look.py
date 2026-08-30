# End-to-end Preserve Look smoke on Blender's factory scene. No external .blend.
#   blender -b --factory-startup --python-exit-code 1 --python tests/test_preserve_look.py

import json
import glob
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import PROJECT_ROOT, check, finish, section  # noqa: E402

sys.path.insert(0, PROJECT_ROOT)
import bpy  # noqa: E402
import scenequant  # noqa: E402
from scenequant.apply import knee_apply  # noqa: E402


def main():
    section("Preserve Look operator smoke")
    scenequant.register()
    try:
        scene = bpy.context.scene
        scene.render.engine = "CYCLES"
        scene.frame_start = 1
        scene.frame_end = 12
        settings = scene.scenequant
        settings.speed_profile = "PRESERVE_LOOK"
        settings.speed_render_intent = "AUTO"
        settings.speed_probe_knee = False

        cycles = scene.cycles
        cycles.max_bounces = 24
        cycles.transparent_max_bounces = 16
        cycles.use_denoising = False
        cycles.use_light_tree = True
        cycles.caustics_reflective = True
        cycles.caustics_refractive = True
        if hasattr(cycles, "blur_glossy"):
            cycles.blur_glossy = 0.0
        if hasattr(cycles, "use_animated_seed"):
            cycles.use_animated_seed = False

        before = {
            "max_bounces": cycles.max_bounces,
            "transparent_max_bounces": cycles.transparent_max_bounces,
            "use_denoising": cycles.use_denoising,
            "use_light_tree": cycles.use_light_tree,
            "caustics_reflective": cycles.caustics_reflective,
            "caustics_refractive": cycles.caustics_refractive,
            "blur_glossy": getattr(cycles, "blur_glossy", None),
            "use_animated_seed": getattr(cycles, "use_animated_seed", None),
        }

        result = bpy.ops.scenequant.make_it_fast('EXEC_DEFAULT')
        check(result == {"FINISHED"}, "Preserve Look operator finishes")
        after = {
            "max_bounces": cycles.max_bounces,
            "transparent_max_bounces": cycles.transparent_max_bounces,
            "use_denoising": cycles.use_denoising,
            "use_light_tree": cycles.use_light_tree,
            "caustics_reflective": cycles.caustics_reflective,
            "caustics_refractive": cycles.caustics_refractive,
            "blur_glossy": getattr(cycles, "blur_glossy", None),
            "use_animated_seed": getattr(cycles, "use_animated_seed", None),
        }
        check(after == before,
              "operator preserves bounce, shadow, caustic, denoise, glossy and seed settings")

        report = json.loads(settings.last_report or "{}")
        plan = report.get("speed_plan") or {}
        check(plan.get("profile") == "PRESERVE_LOOK",
              "stored plan names the Preserve Look contract")
        check(plan.get("intent") == "VIDEO",
              "multi-frame range stores Video intent")
        risky = {
            "APPLY_PERCEPTUAL_PATHS", "LIGHT_TREE", "CAUSTICS_OFF",
            "MICRO_EMITTERS", "CAMERA_CULL", "OPAQUE_CUTOUT_SHADOWS",
            "TRANSPARENT_SHADOW_CAP", "FILTER_GLOSSY", "DENOISE_ON",
            "DENOISE_PREFILTER", "ANIMATED_SEED",
        }
        kinds = {a.get("kind") for a in (plan.get("actions") or [])}
        check(not (kinds & risky), "stored plan contains no appearance-risk action")

        section("video knee integration")
        scene.render.resolution_x = 64
        scene.render.resolution_y = 64
        scene.render.resolution_percentage = 100
        scene.frame_start = 1
        scene.frame_end = 3
        scene.frame_set(2)
        cycles.samples = 128
        cycles.use_denoising = False
        temp_before = set(glob.glob(os.path.join(
            tempfile.gettempdir(), "scenequant-knee-*")))
        knee = knee_apply.auto_knee(
            scene,
            already_adaptive=cycles.use_adaptive_sampling,
            profile="PRESERVE_LOOK",
            intent="VIDEO",
            video_frame_count=3,
        )
        check(knee.get("frames") == [1, 2, 3],
              "video probe checks every frame in a three-frame shot")
        check(scene.frame_current == 2, "video probe restores the artist's frame")
        check(cycles.use_denoising is False,
              "video probe does not force denoising")
        check(cycles.samples == 128,
              "video probe never lowers below the 128 spp floor")
        check(bool(knee.get("frame_knees")),
              "video probe records per-frame convergence evidence")
        temp_after = set(glob.glob(os.path.join(
            tempfile.gettempdir(), "scenequant-knee-*")))
        check(temp_after <= temp_before,
              "video probe removes its temporary EXR directories")
    finally:
        scenequant.unregister()
    finish()


main()
