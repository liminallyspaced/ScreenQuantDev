# pack_scene world Color RGB/Mix → Session vs stock Cycles (Slice 2al).
from __future__ import annotations
import argparse, ctypes, os, sys, time, subprocess
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


RGB = (1.0, 0.25, 0.1)
MIX_A = (1.0, 0.0, 0.0)
MIX_B = (1.0, 0.5, 0.2)
MIX_FAC = 0.5


def _expected_color(args):
    mode = args.mode
    if mode == "mix_rgb":
        f = float(MIX_FAC)
        return (
            MIX_A[0] * (1.0 - f) + MIX_B[0] * f,
            MIX_A[1] * (1.0 - f) + MIX_B[1] * f,
            MIX_A[2] * (1.0 - f) + MIX_B[2] * f,
        )
    if mode == "black":
        return (0.0, 0.0, 0.0)
    if mode in ("hdr", "map_range"):
        return (0.0, 0.0, 0.0)
    return tuple(float(c) for c in RGB)


def _expected_strength(args):
    if args.mode == "map_range":
        # Value 0.25 From 0..1 To 0.4..1.6 LINEAR clamp → 0.7
        return 0.7
    return float(args.strength)


def _color_close(got, expected, eps=1e-5):
    return all(abs(float(a) - float(b)) <= eps for a, b in zip(got, expected))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    p.add_argument("--out", default="/tmp/quanttrace_slice2al_session.exr")
    p.add_argument("--stock-out", default="/tmp/quanttrace_slice2al_stock.exr")
    p.add_argument("--compare", default="")
    p.add_argument("--render-stock", action="store_true", default=False)
    p.add_argument("--image", default="/tmp/qt_slice2al_env.exr")
    p.add_argument(
        "--mode",
        choices=("rgb", "unlinked", "mix_rgb", "black", "hdr", "map_range", "sky"),
        default="rgb",
    )
    p.add_argument(
        "--projection",
        choices=("EQUIRECTANGULAR", "MIRROR_BALL"),
        default="EQUIRECTANGULAR",
    )
    p.add_argument("--strength", type=float, default=1.0)
    p.add_argument("--live-graph", action="store_true", default=False)
    p.add_argument("--no-pull-camera", action="store_true", default=False)
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
    import _quanttrace_slice2al_scene as sc2al
    qt_engine._reset_native_probe_for_tests()
    assert qt_engine.kernel_ready()

    scene, cube_obj, lamp, cam, img = sc2al.build_slice2al_scene(
        image_path=args.image,
        mode=args.mode,
        projection=args.projection,
        strength=args.strength,
        pull_camera=not args.no_pull_camera,
    )
    scene.render.resolution_x = scene.render.resolution_y = args.res
    scene.cycles.samples = args.samples

    if args.mode == "sky":
        try:
            packed = qt_sync.pack_scene(
                scene, depsgraph=bpy.context.evaluated_depsgraph_get()
            )
        except qt_sync.QuantTraceSyncError as e:
            msg = str(e)
            print("QUANTTRACE_SLICE2AL_REFUSE", type(e).__name__, msg)
            if "Slice 2al" not in msg and "TEX_SKY" not in msg and "Sky" not in msg:
                raise RuntimeError(f"sky refused but message unexpected: {msg}")
            print("QUANTTRACE_SLICE2AL_SMOKE OK refuse")
            return 0
        raise RuntimeError(
            f"sky packed unexpectedly world_color={packed.get('world_color')}"
        )

    expected_c = _expected_color(args)
    expected_s = _expected_strength(args)

    if args.render_stock:
        if os.path.isfile(args.stock_out):
            os.unlink(args.stock_out)
        scene.render.filepath = args.stock_out
        t_s = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        print(
            "QUANTTRACE_SLICE2AL_STOCK wall", round(time.perf_counter() - t_s, 3),
            "out", args.stock_out,
        )
        if not args.compare:
            args.compare = args.stock_out

    deps = bpy.context.evaluated_depsgraph_get()
    packed = qt_sync.pack_scene(scene, depsgraph=deps)
    got_c = tuple(float(v) for v in (packed.get("world_color") or (0.0, 0.0, 0.0)))
    print(
        "QUANTTRACE_SLICE2AL_SMOKE packed",
        "mode", args.mode,
        "world_image_path", packed.get("world_image_path"),
        "world_projection", packed.get("world_projection"),
        "world_strength", packed.get("world_strength"),
        "world_color", got_c,
        "expected_color", expected_c,
        "expected_strength", expected_s,
    )
    if args.mode in ("hdr", "map_range"):
        if not packed.get("world_image_path"):
            raise RuntimeError("packed world_image_path empty — env not packed")
    else:
        if packed.get("world_image_path"):
            raise RuntimeError("packed world_image_path set — env should be empty")
    got_s = float(packed.get("world_strength", 0.0))
    if abs(got_s - expected_s) > 1e-6:
        raise RuntimeError(
            f"packed world_strength={got_s} expected {expected_s} (mode={args.mode})"
        )
    if not _color_close(got_c, expected_c):
        raise RuntimeError(
            f"packed world_color={got_c} expected {expected_c} (mode={args.mode})"
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
    ctypes_c = tuple(float(desc.world_color[i]) for i in range(3))
    print(
        "QUANTTRACE_SLICE2AL_CTYPES path", desc.world_image_path,
        "proj", desc.world_projection, "strength", desc.world_strength,
        "world_color", ctypes_c,
        "ver", ver, "is_tracer", is_tr,
    )
    if abs(float(desc.world_strength) - expected_s) > 1e-6:
        raise RuntimeError(
            f"ctypes world_strength={desc.world_strength} expected {expected_s}"
        )
    if not _color_close(ctypes_c, expected_c):
        raise RuntimeError(
            f"ctypes world_color={ctypes_c} expected {expected_c}"
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
        "QUANTTRACE_SLICE2AL_SMOKE rc", rc, "wall", round(time.perf_counter() - t0, 3),
        "ver", ver, "is_tracer", is_tr,
        "rgb_min", rgb_min, "rgb_max", rgb_max, "constant", constant,
    )
    if rc != 0:
        raise RuntimeError(rc)
    if args.mode != "black" and rgb_max == 0.0:
        raise RuntimeError("session Combined all-zero — world color likely missing")
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
                    "QUANTTRACE_SLICE2AL_STOCK_VIS min", smin, "max", smax,
                    "constant", smax - smin < 1e-12,
                )
                if args.mode != "black" and smax == 0.0:
                    raise RuntimeError("stock Combined all-zero — world not visible")
            except ImportError:
                print("QUANTTRACE_SLICE2AL_STOCK_VIS skip (no OIIO in this process)")
        blender = bpy.app.binary_path or "blender"
        rcode = subprocess.call([
            blender, "--background", "--python",
            os.path.join(root, "tools", "_quanttrace_exr_delta.py"), "--",
            args.compare, args.out,
        ])
        print("QUANTTRACE_SLICE2AL_SMOKE compare rc", rcode)
        if rcode != 0:
            raise SystemExit(rcode)

    if args.live_graph:
        if args.mode != "rgb":
            raise RuntimeError("--live-graph requires --mode rgb")
        black_out = "/tmp/quanttrace_slice2al_stock_black.exr"
        scene_b, *_rest = sc2al.build_slice2al_scene(
            image_path=args.image,
            mode="black",
            projection=args.projection,
            strength=args.strength,
            pull_camera=not args.no_pull_camera,
        )
        scene_b.render.resolution_x = scene_b.render.resolution_y = args.res
        scene_b.cycles.samples = args.samples
        if os.path.isfile(black_out):
            os.unlink(black_out)
        scene_b.render.filepath = black_out
        t_b = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        print(
            "QUANTTRACE_SLICE2AL_STOCK_BLACK wall",
            round(time.perf_counter() - t_b, 3), "out", black_out,
        )
        import OpenImageIO as oiio
        import numpy as np
        def _load(path):
            inp = oiio.ImageInput.open(path)
            spec = inp.spec()
            pix = np.asarray(inp.read_image(oiio.FLOAT), dtype=np.float32).reshape(
                spec.height, spec.width, spec.nchannels
            )
            inp.close()
            return pix[:, :, :3].astype(np.float64)
        da = _load(args.stock_out if args.render_stock else args.compare)
        db = _load(black_out)
        diff = np.abs(da - db)
        dmax = float(diff.max())
        mae = float(diff.mean())
        n_gt = int((diff.max(axis=2) >= 1e-3).sum())
        print(
            "QUANTTRACE_SLICE2AL_LIVE rgb_vs_black",
            "dmax", dmax, "mae", mae, "px>=1e-3", n_gt,
            "of", da.shape[0] * da.shape[1],
        )
        if dmax <= 1e-3:
            raise RuntimeError(
                f"live-graph rgb vs black Δmax={dmax} not > 1e-3 "
                "(world color not visible — camera/GI)"
            )

    print("QUANTTRACE_SLICE2AL_SMOKE OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main() or 0)
    except Exception as e:
        print("QUANTTRACE_SLICE2AL_SMOKE FAIL", type(e).__name__, e)
        raise
