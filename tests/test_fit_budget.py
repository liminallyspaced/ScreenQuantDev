# Flagship-path test: the fit-to-VRAM-budget solver end to end.
#   blender --background --factory-startup --python-exit-code 1 --python tests/test_fit_budget.py
# Loads the bench scene itself, so no CLI blend argument is needed.

import json
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness  # noqa: E402  (side effect: repo root on sys.path)
from _harness import PROJECT_ROOT, check, finish, section  # noqa: E402

BAD_SCENE = os.path.join(PROJECT_ROOT, "bench", "bad_scene.blend")
# vram_budget_gb is PHYSICAL VRAM: the usable threshold is derived from it once,
# by memory_model.effective_budget_threshold_mb. 0.9 GB -> 0.85 * 921.6 =
# 783 MB usable, the threshold this suite's ladder-depth assertions were tuned
# against (dedup alone is not enough; subdiv trim must fire).
BUDGET_GB = 0.9


def estimate_now(scene):
    from scenequant.analysis import memory_model
    depsgraph = bpy.context.evaluated_depsgraph_get()
    return memory_model.estimate_scene_memory(scene, depsgraph)


def main():
    import scenequant
    from scenequant import journal as sq_journal
    from scenequant.analysis import memory_model
    scenequant.register()
    # The threshold's measured branch depends on live GPU load. Pin it to the
    # flat-reserve branch (what CI without nvidia-smi gets) so the suite
    # asserts the same numbers on every machine.
    memory_model.vram_sample_mb = lambda: None
    threshold = memory_model.effective_budget_threshold_mb(BUDGET_GB * 1024)
    bpy.ops.wm.open_mainfile(filepath=BAD_SCENE)
    scene = bpy.context.scene

    section("fit to budget")
    before = estimate_now(scene)
    print(f"estimate before: {before.total_mb:.0f} MB "
          f"(tex {before.texture_mb:.0f} + geo {before.geometry_mb:.0f})")
    check(before.total_mb > threshold,
          f"bad scene starts over the {threshold:.0f} MB usable threshold")

    scene.scenequant.vram_budget_gb = BUDGET_GB
    result = bpy.ops.scenequant.fit_budget()
    check(result == {"FINISHED"}, "fit_budget returns FINISHED")

    after = estimate_now(scene)
    print(f"estimate after: {after.total_mb:.0f} MB "
          f"(tex {after.texture_mb:.0f} + geo {after.geometry_mb:.0f})")
    check(after.total_mb < before.total_mb - 400,
          f"solver freed at least 400 MB (got {before.total_mb - after.total_mb:.0f})")
    check(after.total_mb <= threshold * 1.05,
          f"estimate within the {threshold:.0f} MB threshold "
          f"(got {after.total_mb:.0f} MB)")

    far_mod = bpy.data.objects["Far_1"].modifiers["Subsurf"]
    check(far_mod.render_levels == far_mod.levels, "solver applied subdiv trim")
    journal_entries = sq_journal.Journal.load(scene).entry_count()
    check(journal_entries > 0, f"journal recorded plan actions ({journal_entries})")

    section("stored report honesty")
    stored = json.loads(scene.scenequant.last_report or "{}")
    plan = stored.get("plan") or {}
    check(plan.get("fits") is True, f"stored plan reports fits (got {plan.get('fits')})")
    check("shortfall_mb" in plan, "stored plan carries shortfall_mb")
    check(isinstance(plan.get("actions"), list) and plan["actions"],
          "stored plan carries the applied actions")
    check(isinstance(stored.get("est_after_measured_mb"), (int, float)),
          "post-apply re-estimate stored (planned vs measured)")

    section("revert")
    result = bpy.ops.scenequant.revert_all()
    check(result == {"FINISHED"}, "revert returns FINISHED")
    far_mod = bpy.data.objects["Far_1"].modifiers["Subsurf"]
    check(far_mod.render_levels == 2, "revert restores subdiv levels")
    restored = estimate_now(scene)
    check(abs(restored.total_mb - before.total_mb) < before.total_mb * 0.02,
          f"revert restores estimate ({restored.total_mb:.0f} vs {before.total_mb:.0f} MB)")
    finish()


main()
