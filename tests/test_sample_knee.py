# Synthetic sample-knee / verify helpers. No .blend, no bpy.
#   python tests/test_sample_knee.py
#   blender -b --factory-startup --python-exit-code 1 --python tests/test_sample_knee.py

import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness  # noqa: E402
from _harness import PROJECT_ROOT, check, finish, section  # noqa: E402


def _load():
    path = os.path.join(PROJECT_ROOT, "scenequant", "analysis", "sample_probe.py")
    spec = importlib.util.spec_from_file_location("sample_probe", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod



def _load_report():
    path = os.path.join(PROJECT_ROOT, "scenequant", "ui", "report.py")
    spec = importlib.util.spec_from_file_location("sample_probe_report", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_reported_samples_uses_padded_target():
    section("operator reports padded spp not raw knee")
    probe = _load()
    check(probe.pad_cheap_probe_knee(64, 300, 25) == 128,
          "Classroom-shaped 300, raw 64 → padded 128")
    check(probe.pad_cheap_probe_knee(64, 512, 25, already_adaptive=True) == 256,
          "already-adaptive loft 512, raw 64 → padded 256")
    applied = {"applied": True, "knee": 64, "target": 128}
    check(probe.reported_samples(applied) == 128,
          "result.target is the padded floor")
    check(probe.reported_samples(applied, samples_after=128) == 128,
          "live cycles.samples after auto_knee is 128")
    check(probe.reported_samples(applied) != applied["knee"],
          "operator copy is not the raw probe knee")
    loft = {"applied": True, "knee": 64, "target": 256}
    check(probe.reported_samples(loft, samples_after=256) == 256,
          "already-adaptive extra pad reports 256")


def test_encode_last_report_keeps_grade():
    section("Analyze grade survives merge/truncate")
    import json
    report = _load_report()
    bulky = {
        "grade": "B",
        "memory": {"total_mb": 1200.0},
        "findings": [{"message": "x" * 80, "severity": "medium"}] * 40,
        "per_image_targets": [{"name": "Tex%d" % i, "px": 1024} for i in range(80)],
        "dedup": {"mesh_groups": [["A", "B"]] * 20},
    }
    dumped = json.dumps(bulky)
    check(len(dumped) > 1024,
          "classroom-sized Analyze JSON exceeds default StringProperty 1024")
    truncated = dumped[:1024]
    try:
        json.loads(truncated)
        parsed = True
    except ValueError:
        parsed = False
    check(parsed is False,
          "silently truncated last_report is invalid JSON (the grade wipe)")

    encoded = report.encode_last_report(bulky, maxlen=1024)
    check(len(encoded) <= 1024, "encode_last_report fits maxlen")
    data = json.loads(encoded)
    check(data.get("grade") == "B", "grade survives compact")
    check(data.get("memory", {}).get("total_mb") == 1200.0,
          "memory estimate survives compact")

    data["speed_plan"] = {"est_pct": 70.0, "actions": [
        {"kind": "CAMERA_CULL", "payload": {"objects": ["Chair.%03d" % i]}}
        for i in range(30)
    ], "profile": "PRESERVE_LOOK", "intent": "VIDEO",
        "withheld_kinds": ["CAMERA_CULL", "OPAQUE_CUTOUT_SHADOWS"],
        "visual_guard": {"accepted": 2, "rejected": 1, "groups": [
            {"quality": {"frames": {str(i): {"mean": i / 1000.0}}}}
            for i in range(40)
        ]}}
    merged = report.encode_last_report(data, maxlen=1024)
    check(len(merged) <= 1024, "merged speed plan still fits")
    out = report.decode_last_report(merged)
    check(out.get("grade") == "B",
          "grade kept after Make it Fast merge onto last_report")
    check("speed_plan" in out, "speed_plan kept after compact merge")
    check(out["speed_plan"].get("profile") == "PRESERVE_LOOK"
          and out["speed_plan"].get("intent") == "VIDEO",
          "quality contract and render intent survive compact merge")
    check(out["speed_plan"].get("visual_guard", {}).get("rejected") == 1,
          "visual-guard rollback summary survives compact merge")
    text_report = report.format_text(data)
    check("Visual guard:" in text_report and "rolled back" in text_report,
          "text report explains automatic visual rollback")
    html_report = report._render_html(data)
    check("Make it Fast" in html_report and "Worst p95" in html_report,
          "HTML report includes action-group quality evidence")



def main():
    probe = _load()
    try:
        import numpy as np
    except ImportError:
        print("numpy unavailable — skip")
        finish()
        return

    section("identical buffers")
    truth = np.full((16, 16, 3), 0.4, dtype=np.float32)
    mean = probe.mean_abs_linear_delta(truth, truth.copy())
    check(mean == 0.0, "identical buffers → mean Δ = 0")
    mean, peak = probe.verify_delta(truth, truth.copy())
    check(mean == 0.0 and peak == 0.0, "verify identical → (0, 0)")

    section("known shift")
    shifted = truth + 0.1
    mean, peak = probe.verify_delta(truth, shifted)
    check(abs(mean - 0.1) < 1e-5, "known +0.1 shift → mean Δ ≈ 0.1 (got %s)" % mean)
    check(abs(peak - 0.1) < 1e-5, "known +0.1 shift → max Δ ≈ 0.1 (got %s)" % peak)

    section("local-detail guard")
    local = truth.copy()
    local.reshape(-1, 3)[:32] += 0.1  # 12.5% of pixels, small global mean
    metrics = probe.delta_metrics(truth, local)
    check(metrics["mean"] < 0.02, "small region stays under a loose mean threshold")
    check(metrics["p95"] > 0.02, "p95 exposes the local change")
    loose = probe.find_sample_knee({64: truth, 128: local}, eps=0.02)
    guarded = probe.find_sample_knee(
        {64: truth, 128: local}, eps=0.02, p95_eps=0.02)
    check(loose == 64, "mean-only comparison accepts the small region")
    check(guarded is None, "p95 guard rejects the local-detail loss")

    section("representative video frames")
    check(probe.representative_frames(1, 101, 3) == (1, 51, 101),
          "three-frame probe includes start, middle and end")
    check(probe.representative_frames(5, 5, 3) == (5,),
          "single-frame range stays a still")
    check(probe.representative_frames(1, 3, 7) == (1, 2, 3),
          "short shots check every frame without duplicates")
    check(probe.VIDEO_EPS < probe.AUTO_EPS,
          "video convergence is stricter than the historical auto probe")
    check(probe.VIDEO_KNEE_FLOOR > probe.KNEE_FLOOR,
          "video keeps a higher minimum sample floor")

    section("monotonic noise knee")
    rng = np.random.RandomState(0)
    noise = rng.randn(16, 16, 3).astype(np.float32)
    ladder = {}
    for n in (64, 128, 256, 512, 1024):
        ladder[n] = np.clip(truth + noise / (n ** 0.5), 0, None)
    knee = probe.find_sample_knee(ladder, eps=0.02)
    check(knee is not None, "monotonic noise ladder detects a knee (got %s)" % knee)
    check(knee in (64, 128, 256, 512), "knee is a ladder rung (got %s)" % knee)
    tight = probe.find_sample_knee(ladder, eps=1e-6)
    check(tight is None or tight >= knee,
          "tighter eps does not invent an earlier knee")

    section("ladder early-stop")
    calls = []

    def identical(n):
        calls.append(n)
        return truth

    knee, ladder = probe.run_knee_ladder(
        identical, rungs=(64, 128, 256, 512), eps=0.01)
    check(knee == 64, "identical rungs knee at first double (64)")
    check(calls == [64, 128], "converged ladder does not render 256/512")

    section("auto rungs stay under current samples")
    check(probe.rungs_for_current(300) == (64, 128, 256, 512),
          "300 spp → 64/128/256 plus 512 partner")
    check(probe.rungs_for_current(512) == (64, 128, 256, 512, 1024),
          "512 spp → full ladder plus 1024 partner")
    check(probe.rungs_for_current(128) == (64, 128, 256),
          "128 spp → 64/128 plus 256 partner")
    check(probe.rungs_for_current(64) == (64, 128),
          "64 spp → 64 plus 128 partner")
    check(probe.rungs_for_current("x") is None,
          "non-numeric samples → no rungs")

    section("cheap-probe pad")
    check(probe.pad_cheap_probe_knee(64, 300, 25) == 128,
          "25% probe knee 64 on 300 → 128 (one doubling)")
    check(probe.pad_cheap_probe_knee(256, 300, 25) == 256,
          "25% probe knee 256 on 300 stays 256 (pad would raise)")
    check(probe.pad_cheap_probe_knee(64, 300, 100) == 64,
          "full-res probe keeps raw knee")
    check(probe.pad_cheap_probe_knee(None, 300, 25) is None,
          "no knee stays none")
    check(probe.pad_cheap_probe_knee(128, 128, 25) == 128,
          "already at knee is not raised")
    check(probe.pad_cheap_probe_knee(64, 512, 25, already_adaptive=True) == 256,
          "already-adaptive 512, probe knee 64 → 256 (extra doubling)")
    check(probe.pad_cheap_probe_knee(64, 512, 25, already_adaptive=False) == 128,
          "adaptive-off 512, probe knee 64 → 128 (one doubling)")
    check(probe.pad_cheap_probe_knee(64, 300, 25, already_adaptive=False) == 128,
          "Classroom-shaped 300 stays one doubling")
    check(probe.AUTO_EPS > probe.DEFAULT_EPS,
          "auto eps is looser than raw full-res eps")

    section("ladder never converges")
    rng2 = np.random.RandomState(1)

    def chaos(n):
        return rng2.randn(16, 16, 3).astype(np.float32)

    knee, ladder = probe.run_knee_ladder(
        chaos, rungs=(64, 128, 256), eps=1e-9)
    check(knee is None, "independent noise never finds a knee")
    check(sorted(ladder.keys()) == [64, 128, 256],
          "full ladder rendered when no knee")

    test_reported_samples_uses_padded_target()
    test_encode_last_report_keeps_grade()
    finish()


if __name__ == "__main__":
    main()
