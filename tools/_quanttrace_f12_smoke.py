# QuantTrace F12 smoke — SQ_QUANTTRACE.render lands Combined for locked cube.
#
# Headless Blender: register addon, build QUANTTRACE-CUBE scene, switch
# engine to SQ_QUANTTRACE, F12, write linear OpenEXR from the render result.
# CPU only. No user GPU. No Make it Fast.
#
#   blender --background --python tools/_quanttrace_f12_smoke.py -- \
#       --res 32 --samples 4 --out /tmp/qt_f12.exr
#
# Optional --compare STOCK_EXR runs tools/_quanttrace_exr_delta.py gate.

from __future__ import annotations

import argparse
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
    p = argparse.ArgumentParser(description="QuantTrace F12 locked-cube smoke")
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    p.add_argument("--out", default="/tmp/quanttrace_f12_combined.exr")
    p.add_argument("--compare", default="", help="Stock Cycles EXR to delta vs")
    p.add_argument("--addon-root", default="",
                   help="Repo root containing scenequant/ (default: parent of tools/)")
    return p.parse_args(_argv_after_dashdash())


def _ensure_addon(root: str):
    if root not in sys.path:
        sys.path.insert(0, root)
    import scenequant
    # Fresh register; ignore unregister noise when nothing was registered yet.
    try:
        scenequant.unregister()
    except Exception as exc:
        print("QUANTTRACE_F12 unregister_skip", type(exc).__name__, exc)
    scenequant.register()
    from scenequant.quanttrace import engine as qt_engine
    qt_engine._reset_native_probe_for_tests()
    loaded = qt_engine.native_lib_loaded()
    ready = qt_engine.kernel_ready()
    print("QUANTTRACE_F12 addon_root", root)
    print("QUANTTRACE_F12 native_loaded", loaded,
          "version", qt_engine.native_version(),
          "path", qt_engine.native_lib_path())
    print("QUANTTRACE_F12 kernel_ready", ready,
          "is_tracer", qt_engine.native_is_tracer())
    if not ready:
        raise RuntimeError(
            "kernel_ready False — need QT_WITH_CYCLES libquanttrace.so "
            f"(tried {qt_engine.native_lib_path()!r})"
        )
    return qt_engine


def main():
    args = parse_args()
    here = os.path.dirname(os.path.abspath(__file__))
    root = args.addon_root or os.path.dirname(here)
    qt_engine = _ensure_addon(root)

    # Build locked cube via the shared script helpers.
    sys.path.insert(0, here)
    import _quanttrace_cube_scene as cube  # noqa: E402

    scene, _c, _l, _cam = cube.build_locked_scene()
    scene.render.resolution_x = args.res
    scene.render.resolution_y = args.res
    scene.render.resolution_percentage = 100
    scene.cycles.samples = args.samples
    scene.render.engine = "SQ_QUANTTRACE"
    scene.render.filepath = args.out
    scene.render.image_settings.file_format = "OPEN_EXR"
    scene.render.image_settings.color_depth = "32"
    scene.render.image_settings.exr_codec = "ZIP"
    scene.render.image_settings.color_mode = "RGBA"
    scene.view_settings.view_transform = "Raw"

    print("QUANTTRACE_F12 engine", scene.render.engine,
          "res", args.res, "spp", args.samples, "->", args.out)
    # Clear any stale output so a failed render cannot look like success.
    if os.path.isfile(args.out):
        os.unlink(args.out)
    t0 = time.perf_counter()
    result = bpy.ops.render.render(write_still=True)
    wall = time.perf_counter() - t0
    print("QUANTTRACE_F12 ops_result", result, "wall_s", round(wall, 3))
    if result != {"FINISHED"} and "FINISHED" not in str(result):
        raise RuntimeError(f"render ops did not finish: {result}")
    if not os.path.isfile(args.out):
        img = bpy.data.images.get("Render Result")
        if img is None:
            raise RuntimeError("no EXR and no Render Result image")
        img.filepath_raw = args.out
        img.file_format = "OPEN_EXR"
        img.save_render(args.out) if hasattr(img, "save_render") else img.save()
    size = os.path.getsize(args.out) if os.path.isfile(args.out) else 0
    print("QUANTTRACE_F12 wrote", args.out, "bytes", size)
    if size <= 0:
        raise RuntimeError("F12 output missing or empty")
    # Sanity on the written EXR (Render Result.pixels can stay empty in
    # background for custom engines even when write_still succeeded).
    try:
        import OpenImageIO as oiio
        import numpy as np
        inp = oiio.ImageInput.open(args.out)
        spec = inp.spec()
        pix = inp.read_image(oiio.FLOAT)
        inp.close()
        arr = np.asarray(pix, dtype=np.float32).reshape(spec.height, spec.width, spec.nchannels)
        mx = float(arr[:, :, 0].max()) if arr.size else 0.0
        print("QUANTTRACE_F12 exr_max_R", mx, "size", spec.width, "x", spec.height)
        if mx < 1e-4:
            raise RuntimeError("F12 EXR looks black (max R < 1e-4)")
    except ImportError:
        print("QUANTTRACE_F12 skip OIIO max check")

    if args.compare:
        import subprocess
        delta = os.path.join(root, "tools", "_quanttrace_exr_delta.py")
        cmd = [
            "blender", "--background", "--python", delta, "--",
            args.compare, args.out,
        ]
        print("QUANTTRACE_F12 compare", " ".join(cmd))
        rc = subprocess.call(cmd)
        print("QUANTTRACE_F12 compare rc", rc)
        if rc != 0:
            raise SystemExit(rc)

    print("QUANTTRACE_F12 OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main() or 0)
    except Exception as exc:
        print("QUANTTRACE_F12 FAIL", type(exc).__name__, exc)
        raise
