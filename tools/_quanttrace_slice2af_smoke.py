# pack_scene packed-only Image / Env → Session vs stock Cycles (Slice 2af).
from __future__ import annotations
import argparse, ctypes, os, sys, time, subprocess
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    p.add_argument("--out", default="/tmp/quanttrace_slice2af_session.exr")
    p.add_argument("--stock-out", default="/tmp/quanttrace_slice2af_stock.exr")
    p.add_argument("--compare", default="")
    p.add_argument("--render-stock", action="store_true", default=False)
    p.add_argument("--image", default="/tmp/qt_slice2af_checker.png")
    p.add_argument(
        "--mode",
        choices=("base_packed", "hdr_packed", "disk"),
        default="base_packed",
    )
    p.add_argument(
        "--projection",
        choices=("EQUIRECTANGULAR", "MIRROR_BALL"),
        default="EQUIRECTANGULAR",
    )
    p.add_argument("--strength", type=float, default=1.0)
    args = p.parse_args(_argv())
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    import scenequant
    try:
        scenequant.register()
    except Exception:
        pass
    from scenequant.quanttrace import sync as qt_sync, engine as qt_engine
    sys.path.insert(0, os.path.join(root, "tools"))
    import _quanttrace_slice2af_scene as sc2af
    qt_engine._reset_native_probe_for_tests()
    assert qt_engine.kernel_ready()

    image = args.image
    if args.mode == "hdr_packed" and not str(image).endswith(".exr"):
        image = "/tmp/qt_slice2af_env.exr"

    scene, cube_obj, lamp, cam, img = sc2af.build_slice2af_scene(
        image_path=image,
        mode=args.mode,
        projection=args.projection,
        strength=args.strength,
    )
    scene.render.resolution_x = scene.render.resolution_y = args.res
    scene.cycles.samples = args.samples

    if args.render_stock:
        if os.path.isfile(args.stock_out):
            os.unlink(args.stock_out)
        scene.render.filepath = args.stock_out
        t_s = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        print(
            "QUANTTRACE_SLICE2AF_STOCK wall", round(time.perf_counter() - t_s, 3),
            "out", args.stock_out,
        )
        if not args.compare:
            args.compare = args.stock_out

    deps = bpy.context.evaluated_depsgraph_get()
    packed = qt_sync.pack_scene(scene, depsgraph=deps)
    m0 = packed["meshes"][0]
    if args.mode in ("base_packed", "disk"):
        path = m0.get("image_path") or ""
        print(
            "QUANTTRACE_SLICE2AF_SMOKE packed",
            "mode", args.mode,
            "image_path", path,
            "cs", m0.get("image_colorspace"),
            "under_cache", path.startswith("/tmp/quanttrace_packed/"),
            "isfile", os.path.isfile(path) if path else False,
        )
        if not path:
            raise RuntimeError("packed image_path empty — texture not packed")
        if args.mode == "base_packed" and not path.startswith("/tmp/quanttrace_packed/"):
            raise RuntimeError(
                f"base_packed expected /tmp/quanttrace_packed/ got {path!r}"
            )
        if args.mode == "disk" and path.startswith("/tmp/quanttrace_packed/"):
            raise RuntimeError(f"disk regression used packed cache: {path!r}")
    else:
        wpath = packed.get("world_image_path") or ""
        print(
            "QUANTTRACE_SLICE2AF_SMOKE packed",
            "mode", args.mode,
            "world_image_path", wpath,
            "cs", packed.get("world_image_colorspace"),
            "under_cache", wpath.startswith("/tmp/quanttrace_packed/"),
            "isfile", os.path.isfile(wpath) if wpath else False,
            "strength", packed.get("world_strength"),
        )
        if not wpath:
            raise RuntimeError("packed world_image_path empty — env not packed")
        if not wpath.startswith("/tmp/quanttrace_packed/"):
            raise RuntimeError(
                f"hdr_packed expected /tmp/quanttrace_packed/ got {wpath!r}"
            )

    QT_Mesh, QT_Light, QT_Scene = qt_sync.make_qt_scene_types()
    lib = qt_engine._native_lib
    ver = lib.quanttrace_version()
    if isinstance(ver, bytes):
        ver = ver.decode()
    is_tr = int(lib.quanttrace_is_tracer())
    lib.quanttrace_render_qt_scene_rgba.argtypes = [
        ctypes.POINTER(QT_Scene), ctypes.POINTER(ctypes.c_float), ctypes.c_int,
        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
    lib.quanttrace_render_qt_scene_rgba.restype = ctypes.c_int
    desc = qt_sync.to_ctypes_scene(packed, QT_Mesh, QT_Light, QT_Scene, exr_path=args.out)
    print(
        "QUANTTRACE_SLICE2AF_CTYPES ver", ver, "is_tracer", is_tr,
    )
    n = args.res * args.res * 4
    buf = (ctypes.c_float * n)()
    ow = ctypes.c_int(0)
    oh = ctypes.c_int(0)
    if os.path.isfile(args.out):
        os.unlink(args.out)
    t0 = time.perf_counter()
    rc = lib.quanttrace_render_qt_scene_rgba(
        ctypes.byref(desc), buf, n, ctypes.byref(ow), ctypes.byref(oh))
    r = [buf[i] for i in range(0, n, 4)]
    g = [buf[i + 1] for i in range(0, n, 4)]
    bch = [buf[i + 2] for i in range(0, n, 4)]
    rgb_min = min(min(r), min(g), min(bch))
    rgb_max = max(max(r), max(g), max(bch))
    constant = (rgb_max - rgb_min) < 1e-12
    print(
        "QUANTTRACE_SLICE2AF_SMOKE rc", rc, "wall", round(time.perf_counter() - t0, 3),
        "ver", ver, "is_tracer", is_tr,
        "rgb_min", rgb_min, "rgb_max", rgb_max, "constant", constant,
    )
    if rc != 0:
        raise RuntimeError(rc)
    if rgb_max == 0.0:
        raise RuntimeError("session Combined all-zero — packed image likely missing")
    if constant:
        raise RuntimeError("session Combined constant — packed texture likely dead")
    if args.compare:
        if os.path.isfile(args.compare):
            try:
                import OpenImageIO as oiio
                import numpy as np
                inp = oiio.ImageInput.open(args.compare)
                spec = inp.spec()
                pix = np.asarray(inp.read_image(oiio.FLOAT), dtype=np.float32).reshape(
                    spec.height, spec.width, spec.nchannels
                )
                inp.close()
                rgb = pix[:, :, :3]
                smin, smax = float(rgb.min()), float(rgb.max())
                print(
                    "QUANTTRACE_SLICE2AF_STOCK_VIS min", smin, "max", smax,
                    "constant", smax - smin < 1e-12,
                )
                if smax == 0.0:
                    raise RuntimeError("stock Combined all-zero — packed image not visible")
                if smax - smin < 1e-12:
                    raise RuntimeError("stock Combined constant — packed image not visible")
            except ImportError:
                print("QUANTTRACE_SLICE2AF_STOCK_VIS skip (no OIIO in this process)")
        blender = bpy.app.binary_path or "blender"
        rcode = subprocess.call([
            blender, "--background", "--python",
            os.path.join(root, "tools", "_quanttrace_exr_delta.py"), "--",
            args.compare, args.out,
        ])
        print("QUANTTRACE_SLICE2AF_SMOKE compare rc", rcode)
        if rcode != 0:
            raise SystemExit(rcode)
    print("QUANTTRACE_SLICE2AF_SMOKE OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main() or 0)
    except Exception as e:
        print("QUANTTRACE_SLICE2AF_SMOKE FAIL", type(e).__name__, e)
        raise
