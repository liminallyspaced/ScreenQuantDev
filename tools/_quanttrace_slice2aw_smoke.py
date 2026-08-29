# QuantTrace Slice 2aw smoke — pack_scene with N>32 meshes (cap raise).
#
#   blender --background --python tools/_quanttrace_slice2aw_smoke.py -- \
#       --n-meshes 64 --res 32 --samples 4 --session
#
# Optional loft pack probe (no Δmax claim):
#   blender ... -- --loft /path/to/loft.blend --pack-only
#
# CPU only. No user GPU. No Make it Fast. No loft Session match claim.

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
    p = argparse.ArgumentParser(description="QuantTrace Slice 2aw pack-cap smoke")
    p.add_argument("--n-meshes", type=int, default=64)
    p.add_argument("--n-lights", type=int, default=2)
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    p.add_argument("--out", default="/tmp/quanttrace_slice2aw_session.exr")
    p.add_argument("--session", action="store_true", default=False,
                   help="Also run tiny Session render after pack")
    p.add_argument("--pack-only", action="store_true", default=False,
                   help="Stop after successful pack_scene")
    p.add_argument("--loft", default="",
                   help="Optional loft.blend path — pack probe only, no Δmax")
    p.add_argument("--addon-root", default="")
    return p.parse_args(_argv_after_dashdash())


def _setup_addon(root):
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
    return qt_engine, qt_sync


def _pack_and_report(qt_engine, qt_sync, scene, label):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    t0 = time.perf_counter()
    packed = qt_sync.pack_scene(scene, depsgraph=depsgraph)
    wall = time.perf_counter() - t0
    n_m = len(packed["meshes"])
    n_l = len(packed["lights"])
    print(
        f"QUANTTRACE_SLICE2AW_SMOKE {label} PACK_OK",
        "n_meshes", n_m,
        "n_lights", n_l,
        "caps", qt_sync.QT_MAX_MESHES, qt_sync.QT_MAX_LIGHTS,
        "wall_s", round(wall, 3),
        "world_strength", packed.get("world_strength"),
        "version", qt_engine.native_version(),
    )
    if n_m > 32:
        print("QUANTTRACE_SLICE2AW_SMOKE cap_raise confirmed n_meshes>32")
    return packed, wall


def _session_render(qt_engine, qt_sync, packed, out_path):
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
        packed, QT_Mesh, QT_Light, QT_Scene, exr_path=out_path
    )
    nfloat = packed["width"] * packed["height"] * 4
    buf = (ctypes.c_float * nfloat)()
    out_w = ctypes.c_int(0)
    out_h = ctypes.c_int(0)
    if os.path.isfile(out_path):
        os.unlink(out_path)
    t0 = time.perf_counter()
    rc = lib.quanttrace_render_qt_scene_rgba(
        ctypes.byref(desc), buf, nfloat, ctypes.byref(out_w), ctypes.byref(out_h)
    )
    wall = time.perf_counter() - t0
    print(
        "QUANTTRACE_SLICE2AW_SMOKE session rc", rc,
        "wall_s", round(wall, 3),
        "size", out_w.value, "x", out_h.value,
    )
    if rc != 0:
        raise RuntimeError(f"render_qt_scene_rgba rc={rc}")
    if not os.path.isfile(out_path):
        raise RuntimeError("EXR not written")
    print(
        "QUANTTRACE_SLICE2AW_SMOKE wrote", out_path,
        "bytes", os.path.getsize(out_path),
    )
    print("QUANTTRACE_SLICE2AW_SMOKE pack-only Session OK; no Δmax claim")
    return wall


def main():
    args = parse_args()
    here = os.path.dirname(os.path.abspath(__file__))
    root = args.addon_root or os.path.dirname(here)
    qt_engine, qt_sync = _setup_addon(root)
    print(
        "QUANTTRACE_SLICE2AW_SMOKE version", qt_engine.native_version(),
        "path", qt_engine.native_lib_path(),
        "QT_MAX_MESHES", qt_sync.QT_MAX_MESHES,
        "QT_MAX_LIGHTS", qt_sync.QT_MAX_LIGHTS,
    )
    if qt_sync.QT_MAX_MESHES < 1200 or qt_sync.QT_MAX_LIGHTS < 64:
        raise RuntimeError(
            f"caps too low for 2aw: meshes={qt_sync.QT_MAX_MESHES} "
            f"lights={qt_sync.QT_MAX_LIGHTS}"
        )

    if args.loft:
        loft = args.loft
        if not os.path.isfile(loft):
            print("QUANTTRACE_SLICE2AW_SMOKE loft MISSING", loft)
            print("QUANTTRACE_SLICE2AW_SMOKE note loft file missing; synthetic gate only")
        else:
            print("QUANTTRACE_SLICE2AW_SMOKE loft open", loft)
            bpy.ops.wm.open_mainfile(filepath=loft)
            scene = bpy.context.scene
            try:
                packed, wall = _pack_and_report(qt_engine, qt_sync, scene, "loft")
                print(
                    "QUANTTRACE_SLICE2AW_SMOKE loft pack success;",
                    "no Session Δmax claim",
                )
            except Exception as exc:
                print(
                    "QUANTTRACE_SLICE2AW_SMOKE loft PACK_FAIL",
                    type(exc).__name__, exc,
                )
                print(
                    "QUANTTRACE_SLICE2AW_SMOKE note loft may still refuse on "
                    "shader/graph reasons beyond mesh count"
                )
            # Fall through to synthetic gate either way.

    sys.path.insert(0, here)
    import _quanttrace_slice2aw_scene as sc2aw

    if args.n_meshes <= 32:
        raise RuntimeError(
            f"--n-meshes must be >32 to exercise 2aw (got {args.n_meshes})"
        )

    scene, meshes, lamps, cam = sc2aw.build_many_mesh_scene(
        n_meshes=args.n_meshes, n_lights=args.n_lights
    )
    scene.render.resolution_x = args.res
    scene.render.resolution_y = args.res
    scene.cycles.samples = args.samples
    print(
        "QUANTTRACE_SLICE2AW_SMOKE synthetic",
        "built", len(meshes), "meshes", len(lamps), "lights",
        "cam", cam.name,
    )
    packed, pack_wall = _pack_and_report(qt_engine, qt_sync, scene, "synthetic")
    if len(packed["meshes"]) != args.n_meshes:
        raise RuntimeError(
            f"expected {args.n_meshes} packed meshes, got {len(packed['meshes'])}"
        )

    if args.pack_only or not args.session:
        if not args.session:
            print("QUANTTRACE_SLICE2AW_SMOKE pack-only (pass --session for tiny render)")
        print("QUANTTRACE_SLICE2AW_SMOKE OK pack_wall_s", round(pack_wall, 3))
        return 0

    _session_render(qt_engine, qt_sync, packed, args.out)
    print("QUANTTRACE_SLICE2AW_SMOKE OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main() or 0)
    except Exception as exc:
        print("QUANTTRACE_SLICE2AW_SMOKE FAIL", type(exc).__name__, exc)
        raise
