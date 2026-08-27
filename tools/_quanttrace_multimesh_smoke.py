# QuantTrace Slice 2c smoke — pack_scene → Session Combined vs stock Cycles.
#
#   blender --background --python tools/_quanttrace_multimesh_smoke.py -- \
#       --res 32 --samples 4 --out /tmp/qt_still_session.exr
#   blender ... -- --res 256 --samples 128 --compare /tmp/qt_still_stock.exr
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
    p = argparse.ArgumentParser(description="QuantTrace still-life Session smoke")
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    p.add_argument("--out", default="/tmp/quanttrace_still_session.exr")
    p.add_argument("--compare", default="", help="Stock Cycles EXR to delta vs")
    p.add_argument("--addon-root", default="")
    p.add_argument("--f12", action="store_true", default=False,
                   help="Also F12 via SQ_QUANTTRACE after Session write")
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
    print("QUANTTRACE_STILL_SMOKE version", qt_engine.native_version(),
          "path", qt_engine.native_lib_path())

    sys.path.insert(0, here)
    import _quanttrace_multimesh_scene as still

    scene, cubes, lamps, cam = still.build_still_life()
    scene.render.resolution_x = args.res
    scene.render.resolution_y = args.res
    scene.cycles.samples = args.samples

    depsgraph = bpy.context.evaluated_depsgraph_get()
    packed = qt_sync.pack_scene(scene, depsgraph=depsgraph)
    print("QUANTTRACE_STILL_SMOKE packed",
          "res", packed["width"], "x", packed["height"],
          "spp", packed["samples"],
          "meshes", len(packed["meshes"]),
          "lights", len(packed["lights"]),
          "verts", [len(m["verts"]) // 3 for m in packed["meshes"]],
          "base", [m["base_color"] for m in packed["meshes"]],
          "strength", [L["strength"] for L in packed["lights"]],
          "world", packed["world_strength"])

    lib = qt_engine._native_lib
    QT_Mesh, QT_Light, QT_Scene = qt_sync.make_qt_scene_types()
    lib.quanttrace_render_qt_scene_rgba.argtypes = [
        ctypes.POINTER(QT_Scene),
        ctypes.POINTER(ctypes.c_float),
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int),
    ]
    lib.quanttrace_render_qt_scene_rgba.restype = ctypes.c_int

    desc = qt_sync.to_ctypes_scene(
        packed, QT_Mesh, QT_Light, QT_Scene, exr_path=args.out
    )
    nfloat = packed["width"] * packed["height"] * 4
    buf = (ctypes.c_float * nfloat)()
    out_w = ctypes.c_int(0)
    out_h = ctypes.c_int(0)

    if os.path.isfile(args.out):
        os.unlink(args.out)
    t0 = time.perf_counter()
    rc = lib.quanttrace_render_qt_scene_rgba(
        ctypes.byref(desc), buf, nfloat, ctypes.byref(out_w), ctypes.byref(out_h)
    )
    wall = time.perf_counter() - t0
    print("QUANTTRACE_STILL_SMOKE rc", rc, "wall_s", round(wall, 3),
          "size", out_w.value, "x", out_h.value)
    if rc != 0:
        raise RuntimeError(f"render_qt_scene_rgba rc={rc}")
    if not os.path.isfile(args.out):
        raise RuntimeError("EXR not written")
    print("QUANTTRACE_STILL_SMOKE wrote", args.out, "bytes", os.path.getsize(args.out))

    if args.compare:
        import subprocess
        delta = os.path.join(root, "tools", "_quanttrace_exr_delta.py")
        cmd = [
            "blender", "--background", "--python", delta, "--",
            args.compare, args.out,
        ]
        print("QUANTTRACE_STILL_SMOKE compare", " ".join(cmd))
        rc2 = subprocess.call(cmd)
        print("QUANTTRACE_STILL_SMOKE compare rc", rc2)
        if rc2 != 0:
            raise SystemExit(rc2)

    if args.f12:
        f12_out = args.out.replace(".exr", "_f12.exr")
        scene.render.engine = "SQ_QUANTTRACE"
        scene.render.filepath = f12_out
        scene.render.image_settings.file_format = "OPEN_EXR"
        scene.render.image_settings.color_depth = "32"
        scene.render.image_settings.exr_codec = "ZIP"
        scene.render.image_settings.color_mode = "RGBA"
        if os.path.isfile(f12_out):
            os.unlink(f12_out)
        t1 = time.perf_counter()
        result = bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_STILL_SMOKE f12", result,
              "wall_s", round(time.perf_counter() - t1, 3),
              "bytes", os.path.getsize(f12_out) if os.path.isfile(f12_out) else 0)
        if args.compare and os.path.isfile(f12_out):
            import subprocess
            delta = os.path.join(root, "tools", "_quanttrace_exr_delta.py")
            rc3 = subprocess.call([
                "blender", "--background", "--python", delta, "--",
                args.compare, f12_out,
            ])
            print("QUANTTRACE_STILL_SMOKE f12 compare rc", rc3)
            if rc3 != 0:
                raise SystemExit(rc3)

    print("QUANTTRACE_STILL_SMOKE OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main() or 0)
    except Exception as exc:
        print("QUANTTRACE_STILL_SMOKE FAIL", type(exc).__name__, exc)
        raise
