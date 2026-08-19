# Sample-knee and verify helpers. Pure numpy — no bpy, no writes.
# Knee = lowest N where mean abs linear RGB Δ(N, 2N) < eps.
# Operators that render a ladder call these; the helpers never render.

DEFAULT_EPS = 0.01          # ~1% mean abs linear RGB (full-res, raw)
AUTO_EPS = 0.015            # ~4/255; OIDN 25% interiors rarely hit 0.01
RGB_CHANNELS = 3
KNEE_FLOOR = 64


def _as_float_rgb(buffer):
    """(H, W, C) or flat array → float32 RGB (drop alpha)."""
    try:
        import numpy as np
    except ImportError:
        raise RuntimeError("numpy is required for sample-knee helpers")
    arr = np.asarray(buffer, dtype=np.float32)
    if arr.ndim == 1:
        # Packed RGBA/RGB from a render result.
        if arr.size % 4 == 0:
            arr = arr.reshape(-1, 4)
        elif arr.size % 3 == 0:
            arr = arr.reshape(-1, 3)
        else:
            raise ValueError("buffer length is not a multiple of 3 or 4")
    if arr.ndim == 3:
        arr = arr.reshape(-1, arr.shape[-1])
    if arr.ndim != 2 or arr.shape[-1] < RGB_CHANNELS:
        raise ValueError("buffer must be RGB or RGBA")
    return arr[:, :RGB_CHANNELS]


def mean_abs_linear_delta(buffer_a, buffer_b):
    """Mean absolute per-channel Δ between two linear RGB(A) buffers.

    Identical buffers → 0. Used by Verify Render and the sample-knee probe.
    """
    a = _as_float_rgb(buffer_a)
    b = _as_float_rgb(buffer_b)
    if a.shape != b.shape:
        raise ValueError("buffers must have the same RGB shape")
    # Mean over pixels AND channels so a 1% shift in one channel is 1/3%.
    return float(abs(a - b).mean())


def verify_delta(buffer_a, buffer_b):
    """(mean_abs, max_abs) linear RGB Δ. Identical → (0, 0)."""
    a = _as_float_rgb(buffer_a)
    b = _as_float_rgb(buffer_b)
    if a.shape != b.shape:
        raise ValueError("buffers must have the same RGB shape")
    diff = abs(a - b)
    return float(diff.mean()), float(diff.max())


def _ladder_pairs(ladder):
    """Sorted (N, buffer) pairs from a dict or a list of tuples."""
    if hasattr(ladder, "items"):
        items = list(ladder.items())
    else:
        items = list(ladder)
    items.sort(key=lambda item: item[0])
    return items


def find_sample_knee(ladder, eps=DEFAULT_EPS):
    """Lowest N where Δ(N, 2N) < eps. None if the ladder never converges.

    `ladder` is {samples: buffer} or [(samples, buffer), ...] — buffers are
    linear RGB(A) arrays. Consecutive rungs do not have to be exact doubles;
    the first pair whose sample counts satisfy n2 >= 2*n (or the next rung
    when the ladder is a strict doubling) is compared.
    """
    items = _ladder_pairs(ladder)
    if len(items) < 2:
        return None
    # Prefer exact doubles (64 vs 128, 128 vs 256, ...). Fall back to
    # consecutive rungs so a 64/128/256/512 ladder still works if one
    # render is missing.
    by_n = {n: buf for n, buf in items}
    for n, buf in items:
        doubled = by_n.get(2 * n)
        if doubled is None:
            continue
        if mean_abs_linear_delta(buf, doubled) < eps:
            return n
    # No exact double: consecutive rungs, still require n2 > n.
    for (n, a), (n2, b) in zip(items, items[1:]):
        if n2 <= n:
            continue
        if mean_abs_linear_delta(a, b) < eps:
            return n
    return None

DEFAULT_RUNGS = (64, 128, 256, 512)


def pad_cheap_probe_knee(knee, current, probe_scale, floor=KNEE_FLOOR):
    """One doubling of safety when the ladder was not full-res.

    A 25% OIDN postage stamp can look converged a rung early. Never raises
    the live sample count. Full-res probes (scale >= 100) keep the raw knee.
    """
    if knee is None:
        return None
    target = max(int(knee), int(floor))
    if not isinstance(current, (int, float)):
        return target
    current = int(current)
    if current <= 0:
        return target
    if probe_scale >= 100 or target >= current:
        return min(target, current)
    padded = min(current, max(target * 2, int(floor)))
    if padded < current:
        return padded
    return min(target, current)


def rungs_for_current(current, rungs=DEFAULT_RUNGS):
    """Ladder at or under current spp, plus the 2N partner of the top rung.

    300 spp must still render 512 so 256 can be compared. The extra rung is
    probe-only — apply_knee never raises the live count.
    """
    if not isinstance(current, (int, float)):
        return None
    under = [int(n) for n in rungs if n <= current]
    if not under:
        return None
    picked = list(under)
    partner = 2 * under[-1]
    if partner not in picked:
        picked.append(partner)
    if len(picked) < 2:
        return None
    return tuple(picked)


def run_knee_ladder(render_at, rungs=DEFAULT_RUNGS, eps=DEFAULT_EPS):
    """Call render_at(n) for each rung until a knee appears.

    render_at is injected so this stays pure (operators render; tests fake).
    Returns (knee_or_None, {n: buffer} for rungs actually rendered).
    Stops after the first pair that satisfies find_sample_knee so a
    converged scene does not pay for 512 spp.
    """
    ladder = {}
    for n in rungs:
        ladder[int(n)] = render_at(int(n))
        knee = find_sample_knee(ladder, eps)
        if knee is not None:
            return knee, ladder
    return None, ladder
