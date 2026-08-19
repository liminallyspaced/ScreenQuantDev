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

    finish()


main()
