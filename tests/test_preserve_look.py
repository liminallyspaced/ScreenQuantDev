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
from scenequant import journal  # noqa: E402
from scenequant.analysis import visual_guard as guard_policy  # noqa: E402
from scenequant.apply import knee_apply  # noqa: E402
from scenequant.apply import visual_guard as apply_visual_guard  # noqa: E402


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
        # The operator contract is covered here; the guard itself has focused
        # real-render and forced-rejection checks below.
        settings.speed_visual_guard = False

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

        section("automatic visual guard accepts render-equivalent group")
        scene.render.resolution_x = 32
        scene.render.resolution_y = 32
        scene.render.resolution_percentage = 100
        scene.frame_start = 1
        scene.frame_end = 1
        scene.frame_set(1)
        cycles.samples = 8
        scene.render.use_lock_interface = False
        jrnl = journal.Journal()
        accepted = apply_visual_guard.run_guarded_speed_plan(
            scene, settings, jrnl,
            {"profile": "PRESERVE_LOOK", "intent": "STILL", "actions": [{
                "kind": "LOCK_INTERFACE", "payload": {},
            }]},
        )
        accepted_guard = accepted.get("visual_guard") or {}
        check(accepted_guard.get("accepted") == 1,
              "identical before/after render accepts the runtime group")
        check(scene.render.use_lock_interface is True,
              "accepted group remains applied")
        accepted_groups = accepted_guard.get("groups") or [{}]
        check(accepted_groups[0].get("quality", {}).get("passed") is True,
              "accepted group stores per-frame quality evidence")
        jrnl.revert_all()

        section("automatic visual guard immediately rolls back drift")
        import numpy as np
        cycles.use_light_tree = True

        def fake_renderer(target_scene, frame):
            value = 0.4 if target_scene.cycles.use_light_tree else 0.8
            return np.full((8, 8, 3), value, dtype=np.float32), 0.001

        jrnl = journal.Journal()
        rejected = apply_visual_guard.run_guarded_speed_plan(
            scene, settings, jrnl,
            {"profile": "PRESERVE_LOOK", "intent": "STILL", "actions": [{
                "kind": "LIGHT_TREE", "payload": {"enabled": False},
            }]},
            renderer=fake_renderer,
            prepare_probe=False,
        )
        rejected_guard = rejected.get("visual_guard") or {}
        check(rejected_guard.get("rejected") == 1,
              "image-changing group is rejected")
        check(cycles.use_light_tree is True,
              "rejected group is restored before the guard returns")
        check(rejected.get("applied") == 0,
              "rolled-back group is not reported as applied")
        check(jrnl.entry_count() == 0,
              "successful rollback consumes the rejected group's journal")

        section("empty plan has zero visual-probe overhead")
        probe_calls = []

        def should_not_render(target_scene, frame):
            probe_calls.append(frame)
            raise AssertionError("empty plan rendered")

        empty = apply_visual_guard.run_guarded_speed_plan(
            scene, settings, journal.Journal(),
            {"profile": "PRESERVE_LOOK", "intent": "VIDEO", "actions": []},
            renderer=should_not_render,
            prepare_probe=False,
        )
        check(probe_calls == [], "no action groups skip the baseline render")
        check(empty.get("visual_guard", {}).get("reason") ==
              "no action groups to verify",
              "empty guard records why it did no work")

        section("visual guard worst-region and temporal policy")
        truth = np.full((10, 10, 3), 0.4, dtype=np.float32)
        local = truth.copy()
        local.reshape(-1, 3)[:10] += 0.05
        verdict = guard_policy.evaluate_frame_set({1: truth}, {1: local})
        check(verdict.get("passed") is False,
              "p95 gate rejects a local change hidden by global mean")
        temporal = guard_policy.temporal_residual_metrics(
            truth, truth, truth, local)
        check(temporal["p95"] > 0.01,
              "temporal residual exposes frame-to-frame inconsistency")

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
