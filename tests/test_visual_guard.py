# Pure Preserve Look visual-guard policy tests. No .blend, no bpy.

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _harness import PROJECT_ROOT, check, finish, section  # noqa: E402

sys.path.insert(0, os.path.join(PROJECT_ROOT, "scenequant"))
from analysis import visual_guard  # noqa: E402


def main():
    import numpy as np

    section("stable logical action groups")
    actions = [
        {"kind": "ADAPTIVE_ON"},
        {"kind": "LOCK_INTERFACE"},
        {"kind": "MIN_SAMPLES"},
        {"kind": "FUTURE_UNKNOWN"},
    ]
    groups = visual_guard.group_speed_actions(actions)
    check([g["key"] for g in groups] == [
        "sampling", "runtime", "other:FUTURE_UNKNOWN"],
        "known actions coalesce and unknown actions stay isolated")
    check([a["kind"] for a in groups[0]["actions"]] == [
        "ADAPTIVE_ON", "MIN_SAMPLES"],
        "grouping keeps original action order")

    section("strict still and stricter video thresholds")
    still = visual_guard.thresholds("STILL")
    video = visual_guard.thresholds("VIDEO")
    check(video["mean"] < still["mean"] and video["p95"] < still["p95"],
          "video has tighter mean and worst-region limits")

    truth = np.full((20, 20, 3), 0.4, dtype=np.float32)
    identical = visual_guard.evaluate_frame_set({1: truth}, {1: truth.copy()})
    check(identical["passed"] is True, "identical frame passes")
    check(identical["frames"]["1"]["max"] == 0.0,
          "frame audit records exact max delta")

    local = truth.copy()
    local.reshape(-1, 3)[:40] += 0.05
    rejected = visual_guard.evaluate_frame_set({1: truth}, {1: local})
    check(rejected["passed"] is False,
          "p95 rejects a local change despite a small global mean")
    check(rejected["worst_frame"] == 1, "audit identifies the failing frame")

    missing = visual_guard.evaluate_frame_set(
        {1: truth, 2: truth}, {1: truth})
    check(missing["passed"] is False,
          "incomplete video evidence fails closed")

    section("temporal residual")
    temporal = visual_guard.temporal_residual_metrics(
        truth, truth, truth, local)
    check(temporal["p95"] > 0.01,
          "change-of-change catches frame-to-frame drift")
    finish()


if __name__ == "__main__":
    main()
