#!/usr/bin/env python3
# Compare two linear Combined OpenEXR files (stock Cycles vs QuantTrace Session).
# Primary: Δmax = max |a-b| over RGB. Secondary: mean abs (MAE). Ignore A.
# Fail clearly on missing files or dim mismatch. Does not flip is_tracer.
#
# Prefer Blender's OpenImageIO (system Python OIIO from cycles-src is a
# broken namespace package without the extension module on PATH):
#   blender --background --python tools/_quanttrace_exr_delta.py -- a.exr b.exr
# Or if bpy OpenImageIO is importable in plain python3, same argv works.

from __future__ import annotations

import os
import sys


def _argv_paths():
    argv = sys.argv
    if "--" in argv:
        rest = argv[argv.index("--") + 1 :]
    else:
        rest = argv[1:]
    if len(rest) != 2:
        print(
            "usage: blender --background --python tools/_quanttrace_exr_delta.py -- a.exr b.exr",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return rest[0], rest[1]


def load_rgba(oiio, path: str):
    if not os.path.isfile(path):
        raise SystemExit(f"FAIL missing EXR: {path}")
    inp = oiio.ImageInput.open(path)
    if inp is None:
        raise SystemExit(f"FAIL cannot open EXR: {path}: {oiio.geterror()}")
    spec = inp.spec()
    w, h, nch = spec.width, spec.height, spec.nchannels
    pixels = inp.read_image(oiio.FLOAT)
    inp.close()
    if pixels is None:
        raise SystemExit(f"FAIL read_image failed: {path}: {oiio.geterror()}")
    import numpy as np

    arr = np.asarray(pixels, dtype=np.float32)
    if arr.ndim == 1:
        arr = arr.reshape(h, w, nch)
    elif arr.ndim == 2:
        # (h, w*nch) unlikely; try reshape
        arr = arr.reshape(h, w, nch)
    elif arr.shape != (h, w, nch):
        arr = arr.reshape(h, w, nch)
    return w, h, nch, arr


def main() -> int:
    a_path, b_path = _argv_paths()
    try:
        import OpenImageIO as oiio
        if not hasattr(oiio, "ImageInput"):
            raise ImportError("OpenImageIO namespace without ImageInput")
    except ImportError as e:
        print(f"FAIL OpenImageIO: {e}", file=sys.stderr)
        print(
            "Run under Blender: blender --background --python tools/_quanttrace_exr_delta.py -- a.exr b.exr",
            file=sys.stderr,
        )
        return 2

    import numpy as np

    wa, ha, ncha, a = load_rgba(oiio, a_path)
    wb, hb, nchb, b = load_rgba(oiio, b_path)
    print(f"stock   {a_path}  {wa}x{ha} ch={ncha}")
    print(f"session {b_path}  {wb}x{hb} ch={nchb}")
    if wa != wb or ha != hb:
        print(f"FAIL dims differ: {wa}x{ha} vs {wb}x{hb}")
        return 1
    nrgb = min(3, ncha, nchb)
    if nrgb < 3:
        print(f"FAIL need >=3 channels, got {ncha} and {nchb}")
        return 1
    da = a[:, :, :3].astype(np.float64)
    db = b[:, :, :3].astype(np.float64)
    diff = np.abs(da - db)
    dmax = float(diff.max())
    mae = float(diff.mean())
    print(
        f"stock   RGB min={da.min(axis=(0, 1))} max={da.max(axis=(0, 1))} "
        f"mean={da.mean(axis=(0, 1))}"
    )
    print(
        f"session RGB min={db.min(axis=(0, 1))} max={db.max(axis=(0, 1))} "
        f"mean={db.mean(axis=(0, 1))}"
    )
    print(f"dmax={dmax:.6g}")
    print(f"mae={mae:.6g}")
    gate = 1e-3
    print(f"gate={gate} pass={dmax < gate}")
    if ncha >= 4:
        print(f"alpha_mean stock={float(a[:, :, 3].mean()):.6g}")
    if nchb >= 4:
        print(f"alpha_mean session={float(b[:, :, 3].mean()):.6g}")
    return 0 if dmax < gate else 3


if __name__ == "__main__":
    raise SystemExit(main())
