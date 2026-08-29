# pack_scene TEX_IMAGE → world Color → Session vs stock Cycles (Slice 2an).
from __future__ import annotations
import argparse, ctypes, os, sys, time, subprocess
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def _color_close(got, expected, eps=1e-5):
    return all(abs(float(a) - float(b)) <= eps for a, b in zip(got, expected))


def _compose_pair_png(stock_path, session_path, out_paths):
    """stock | session | 10×abs-diff → 8-bit PNG."""
    import OpenImageIO as oiio
    import numpy as np

    def load(path):
        inp = oiio.ImageInput.open(path)
        spec = inp.spec()
        pix = np.asarray(inp.read_image(oiio.FLOAT), dtype=np.float32).reshape(
            spec.height, spec.width, spec.nchannels
        )
        inp.close()
        return pix[:, :, :3]

    a = load(stock_path)
    b = load(session_path)
    diff = np.abs(a.astype(np.float64) - b.astype(np.float64))
    vis = np.clip(diff * 10.0, 0.0, 1.0)
    plate = np.concatenate(
        [np.clip(a, 0.0, 1.0), np.clip(b, 0.0, 1.0), vis.astype(np.float32)],
        axis=1,
    )
    u8 = np.clip(plate * 255.0 + 0.5, 0, 255).astype(np.uint8)
    h, w, _ = u8.shape
    spec = oiio.ImageSpec(w, h, 3, oiio.UINT8)
    for path in out_paths:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        out = oiio.ImageOutput.create(path)
        if out is None:
            raise RuntimeError(f"OIIO create failed for {path}: {oiio.geterror()}")
        if not out.open(path, spec):
            raise RuntimeError(f"OIIO open failed for {path}: {oiio.geterror()}")
        if not out.write_image(u8):
            raise RuntimeError(f"OIIO write failed for {path}: {oiio.geterror()}")
        out.close()
        print("QUANTTRACE_SLICE2AN_PAIR", path, "wh", w, h)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    p.add_argument("--out", default="/tmp/quanttrace_slice2an_session.exr")
    p.add_argument("--stock-out", default="/tmp/quanttrace_slice2an_stock.exr")
    p.add_argument("--compare", default="")
    p.add_argument("--render-stock", action="store_true", default=False)
    p.add_argument("--image", default="/tmp/qt_slice2an_checker.png")
    p.add_argument(
        "--mode",
        choices=(
            "teximage", "teximage_mapping", "teximage_unlinked",
            "rgb", "hdr", "nishita", "noise", "black",
        ),
        default="teximage",
    )
    p.add_argument(
        "--projection",
        choices=("FLAT", "BOX", "SPHERE", "TUBE"),
        default="FLAT",
    )
    p.add_argument("--strength", type=float, default=1.0)
    p.add_argument("--live-graph", action="store_true", default=False)
    p.add_argument("--no-pull-camera", action="store_true", default=False)
    p.add_argument("--pair-png", default="")
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
    import _quanttrace_slice2an_scene as sc2an
    qt_engine._reset_native_probe_for_tests()
    assert qt_engine.kernel_ready()

    scene, cube_obj, lamp, cam, img = sc2an.build_slice2an_scene(
        image_path=args.image,
        mode=args.mode,
        projection=args.projection,
        strength=args.strength,
        pull_camera=not args.no_pull_camera,
    )
    scene.render.resolution_x = scene.render.resolution_y = args.res
    scene.cycles.samples = args.samples

    if args.mode == "noise":
        try:
            packed = qt_sync.pack_scene(
                scene, depsgraph=bpy.context.evaluated_depsgraph_get()
            )
        except qt_sync.QuantTraceSyncError as e:
            msg = str(e)
            print("QUANTTRACE_SLICE2AN_REFUSE", type(e).__name__, msg)
            if "Slice 2an" not in msg and "TEX_IMAGE" not in msg and "Noise" not in msg and "TEX_NOISE" not in msg and "noise" not in msg.lower():
                # Noise comes through _world_color_from_linked as type TEX_NOISE
                if "refused" not in msg.lower():
                    raise RuntimeError(f"noise refused but message unexpected: {msg}")
            print("QUANTTRACE_SLICE2AN_SMOKE OK refuse")
            return 0
        raise RuntimeError(
            f"noise packed unexpectedly world_color_image_path={packed.get('world_color_image_path')}"
        )

    if args.mode == "rgb":
        expected_c = (1.0, 0.25, 0.1)
        expected_sky = 0
        expected_cip = ""
        expected_mode = 0
    elif args.mode in ("hdr", "black"):
        expected_c = (0.0, 0.0, 0.0)
        expected_sky = 0
        expected_cip = ""
        expected_mode = 0
    elif args.mode == "nishita":
        expected_c = (0.0, 0.0, 0.0)
        expected_sky = 3
        expected_cip = ""
        expected_mode = 0
    else:
        expected_c = (0.0, 0.0, 0.0)
        expected_sky = 0
        expected_cip = "nonempty"
        if args.mode == "teximage":
            expected_mode = 3  # TEXCOORD_GENERATED
        elif args.mode == "teximage_mapping":
            expected_mode = 4  # MAPPING_GENERATED
        else:
            expected_mode = 0  # unlinked
    expected_s = float(args.strength)

    if args.render_stock:
        if os.path.isfile(args.stock_out):
            os.unlink(args.stock_out)
        scene.render.filepath = args.stock_out
        t_s = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        print(
            "QUANTTRACE_SLICE2AN_STOCK wall", round(time.perf_counter() - t_s, 3),
            "out", args.stock_out,
        )
        if not args.compare:
            args.compare = args.stock_out

    deps = bpy.context.evaluated_depsgraph_get()
    packed = qt_sync.pack_scene(scene, depsgraph=deps)
    got_c = tuple(float(v) for v in (packed.get("world_color") or (0.0, 0.0, 0.0)))
    got_sky = int(packed.get("world_sky_type", 0) or 0)
    got_cip = str(packed.get("world_color_image_path") or "")
    got_mode = int(packed.get("world_tex_vector_mode", 0) or 0)
    print(
        "QUANTTRACE_SLICE2AN_SMOKE packed",
        "mode", args.mode,
        "world_image_path", packed.get("world_image_path"),
        "world_color_image_path", got_cip,
        "world_color_image_projection", packed.get("world_color_image_projection"),
        "world_color_image_colorspace", packed.get("world_color_image_colorspace"),
        "world_tex_vector_mode", got_mode,
        "world_strength", packed.get("world_strength"),
        "world_color", got_c,
        "world_sky_type", got_sky,
        "expected_color", expected_c,
        "expected_sky", expected_sky,
        "expected_cip", expected_cip,
        "expected_mode", expected_mode,
        "expected_strength", expected_s,
    )
    if args.mode == "hdr":
        if not packed.get("world_image_path"):
            raise RuntimeError("packed world_image_path empty — env not packed")
        if got_cip:
            raise RuntimeError("packed world_color_image_path set on hdr mode")
    elif args.mode in ("teximage", "teximage_mapping", "teximage_unlinked"):
        if not got_cip:
            raise RuntimeError("packed world_color_image_path empty — TEX_IMAGE not packed")
        if packed.get("world_image_path"):
            raise RuntimeError("packed world_image_path set — env should be empty")
        if got_mode != expected_mode:
            raise RuntimeError(
                f"packed world_tex_vector_mode={got_mode} expected {expected_mode}"
            )
        if int(packed.get("world_color_image_projection", -1) or 0) != 0:
            raise RuntimeError(
                f"packed projection={packed.get('world_color_image_projection')} expected 0 FLAT"
            )
    else:
        if got_cip:
            raise RuntimeError("packed world_color_image_path set unexpectedly")
        if args.mode != "hdr" and packed.get("world_image_path"):
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
    if got_sky != expected_sky:
        raise RuntimeError(
            f"packed world_sky_type={got_sky} expected {expected_sky} (mode={args.mode})"
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
    ctypes_cip = desc.world_color_image_path
    if isinstance(ctypes_cip, bytes):
        ctypes_cip = ctypes_cip.decode()
    print(
        "QUANTTRACE_SLICE2AN_CTYPES env_path", desc.world_image_path,
        "color_image_path", ctypes_cip,
        "proj", int(desc.world_color_image_projection),
        "tex_mode", int(desc.world_tex_vector_mode),
        "strength", desc.world_strength,
        "world_color", ctypes_c,
        "world_sky_type", int(desc.world_sky_type),
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
    if int(desc.world_sky_type) != expected_sky:
        raise RuntimeError(
            f"ctypes world_sky_type={desc.world_sky_type} expected {expected_sky}"
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
        "QUANTTRACE_SLICE2AN_SMOKE rc", rc, "wall", round(time.perf_counter() - t0, 3),
        "ver", ver, "is_tracer", is_tr,
        "rgb_min", rgb_min, "rgb_max", rgb_max, "constant", constant,
    )
    if rc != 0:
        raise RuntimeError(rc)
    if args.mode not in ("black",) and rgb_max == 0.0:
        raise RuntimeError("session Combined all-zero — world likely missing")
    if args.mode == "teximage" and constant:
        print("QUANTTRACE_SLICE2AN_WARN session Combined is constant — Generated may be flat")
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
                    "QUANTTRACE_SLICE2AN_STOCK_VIS min", smin, "max", smax,
                    "constant", smax - smin < 1e-12,
                )
                if args.mode not in ("black",) and smax == 0.0:
                    raise RuntimeError("stock Combined all-zero — world not visible")
            except ImportError:
                print("QUANTTRACE_SLICE2AN_STOCK_VIS skip (no OIIO in this process)")
        blender = bpy.app.binary_path or "blender"
        rcode = subprocess.call([
            blender, "--background", "--python",
            os.path.join(root, "tools", "_quanttrace_exr_delta.py"), "--",
            args.compare, args.out,
        ])
        print("QUANTTRACE_SLICE2AN_SMOKE compare rc", rcode)
        if args.pair_png and rcode == 0:
            pair = args.pair_png
            copies = [pair]
            proof = os.path.join(root, "docs", "proof", "quanttrace-teximage-color-32-pair.png")
            ws = "/workspace/quanttrace-teximage-color-32-pair.png"
            for extra in (proof, ws):
                if extra not in copies:
                    copies.append(extra)
            try:
                _compose_pair_png(args.compare, args.out, copies)
            except Exception as e:
                print("QUANTTRACE_SLICE2AN_PAIR FAIL", type(e).__name__, e)
                raise
        if rcode != 0:
            raise SystemExit(rcode)

    if args.live_graph:
        if args.mode != "teximage":
            raise RuntimeError("--live-graph requires --mode teximage")
        black_out = "/tmp/quanttrace_slice2an_stock_black.exr"
        scene_b, *_rest = sc2an.build_slice2an_scene(
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
            "QUANTTRACE_SLICE2AN_STOCK_BLACK wall",
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
            "QUANTTRACE_SLICE2AN_LIVE teximage_vs_black",
            "dmax", dmax, "mae", mae, "px>=1e-3", n_gt,
            "of", da.shape[0] * da.shape[1],
        )
        if dmax <= 1e-3:
            raise RuntimeError(
                f"live-graph teximage vs black Δmax={dmax} not > 1e-3 "
                "(image not visible — camera/GI)"
            )

    print("QUANTTRACE_SLICE2AN_SMOKE OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main() or 0)
    except Exception as e:
        print("QUANTTRACE_SLICE2AN_SMOKE FAIL", type(e).__name__, e)
        raise
