# QuantTrace depsgraph sync smoke — pack_simple_scene → Session Combined.
#
# Headless Blender: build locked cube, pack via depsgraph sync (no hardcoded
# Session path), render through quanttrace_render_scene_rgba, optional
# compare vs stock Cycles EXR.
#
#   blender --background --python tools/_quanttrace_depsgraph_smoke.py -- \
#       --res 32 --samples 4 --out /tmp/qt_deps.exr
#   blender ... -- --res 256 --samples 128 --compare /tmp/stock.exr
#
# CPU only. No user GPU. No Make it Fast.

from __future__ import annotations

import argparse
import ctypes
import os
import sys
import time

import bpy


def _argv_after_dashdash():
    argv = sys.argv
    if "--" in argv:
        return argv[argv.index("--") + 1 :]
    return []


def parse_args():
    p = argparse.ArgumentParser(description="QuantTrace depsgraph sync smoke")
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    p.add_argument("--out", default="/tmp/quanttrace_depsgraph_combined.exr")
    p.add_argument("--compare", default="", help="Stock Cycles EXR to delta vs")
    p.add_argument("--addon-root", default="")
    return p.parse_args(_argv_after_dashdash())


def main():
    args = parse_args()
    here = os.path.dirname(os.path.abspath(__file__))
    root = args.addon_root or os.path.dirname(here)
    if root not in sys.path:
        sys.path.insert(0, root)

    import scenequant
    try:
        scenequant.unregister()
    except Exception:
        pass
    scenequant.register()

    from scenequant.quanttrace import engine as qt_engine
    from scenequant.quanttrace import sync as qt_sync

    qt_engine._reset_native_probe_for_tests()
    if not qt_engine.kernel_ready():
        raise RuntimeError(
            f"kernel_ready False path={qt_engine.native_lib_path()!r} "
            f"ver={qt_engine.native_version()!r}"
        )
    print("QUANTTRACE_DEPS version", qt_engine.native_version(),
          "path", qt_engine.native_lib_path())

    sys.path.insert(0, here)
    import _quanttrace_cube_scene as cube

    scene, _c, _l, _cam = cube.build_locked_scene()
    scene.render.resolution_x = args.res
    scene.render.resolution_y = args.res
    scene.cycles.samples = args.samples

    depsgraph = bpy.context.evaluated_depsgraph_get()
    packed = qt_sync.pack_simple_scene(scene, depsgraph=depsgraph)
    print("QUANTTRACE_DEPS packed",
          "res", packed["width"], "x", packed["height"],
          "spp", packed["samples"],
          "verts", len(packed["verts"]) // 3,
          "tris", len(packed["tris"]) // 3,
          "cam_fov", round(packed["cam_fov"], 6),
          "light_strength", packed["light_strength"],
          "world_strength", packed["world_strength"])

    lib = qt_engine._native_lib
    QT_SimpleScene = qt_sync.make_qt_simple_scene_type()
    lib.quanttrace_render_scene_rgba.argtypes = [
        ctypes.POINTER(QT_SimpleScene),
        ctypes.POINTER(ctypes.c_float),
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int),
    ]
    lib.quanttrace_render_scene_rgba.restype = ctypes.c_int

    desc = qt_sync.to_ctypes(packed, QT_SimpleScene, exr_path=args.out)
    nfloat = packed["width"] * packed["height"] * 4
    buf = (ctypes.c_float * nfloat)()
    out_w = ctypes.c_int(0)
    out_h = ctypes.c_int(0)

    if os.path.isfile(args.out):
        os.unlink(args.out)
    t0 = time.perf_counter()
    rc = lib.quanttrace_render_scene_rgba(
        ctypes.byref(desc), buf, nfloat, ctypes.byref(out_w), ctypes.byref(out_h)
    )
    wall = time.perf_counter() - t0
    print("QUANTTRACE_DEPS rc", rc, "wall_s", round(wall, 3),
          "size", out_w.value, "x", out_h.value)
    if rc != 0:
        raise RuntimeError(f"render_scene_rgba rc={rc}")
    if not os.path.isfile(args.out):
        raise RuntimeError("EXR not written")
    print("QUANTTRACE_DEPS wrote", args.out, "bytes", os.path.getsize(args.out))

    if args.compare:
        import subprocess
        delta = os.path.join(root, "tools", "_quanttrace_exr_delta.py")
        cmd = [
            "blender", "--background", "--python", delta, "--",
            args.compare, args.out,
        ]
        print("QUANTTRACE_DEPS compare", " ".join(cmd))
        rc2 = subprocess.call(cmd)
        print("QUANTTRACE_DEPS compare rc", rc2)
        if rc2 != 0:
            raise SystemExit(rc2)

    print("QUANTTRACE_DEPS OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main() or 0)
    except Exception as exc:
        print("QUANTTRACE_DEPS FAIL", type(exc).__name__, exc)
        raise
