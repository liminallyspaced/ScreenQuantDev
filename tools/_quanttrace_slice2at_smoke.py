# pack_scene 3-deep Math → world Strength → Session vs stock Cycles (Slice 2at).
from __future__ import annotations
import argparse, ctypes, os, sys, time
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def _color_close(got, expected, eps=1e-5):
    return all(abs(float(a) - float(b)) <= eps for a, b in zip(got, expected))


def _fclose(got, expected, eps=1e-5):
    return abs(float(got) - float(expected)) <= eps


def _compose_pair_png(stock_path, session_path, out_paths):
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
        print("QUANTTRACE_SLICE2AT_PAIR", path, "wh", w, h)


def _expected_for_mode(mode, strength):
    base = dict(
        world_color=(0.0, 0.0, 0.0),
        world_sky_type=0,
        world_color_image_path="",
        world_image_path_empty=True,
        world_gamma=1.0,
        world_hsv_hue=0.5,
        world_hsv_sat=1.0,
        world_hsv_val=1.0,
        world_hsv_fac=1.0,
        world_bright=0.0,
        world_contrast=0.0,
        world_mix_type=0,
        world_curves_n=0,
        world_tex_vector_mode=0,
        world_strength=float(strength),
    )
    if mode in ("math_nest3", "math_mul"):
        base["world_strength"] = 0.7
        base["world_image_path_empty"] = False
    elif mode == "unlinked":
        base["world_strength"] = 1.0
        base["world_image_path_empty"] = False
    elif mode == "rgb_curves":
        base["world_color"] = (1.0, 0.25, 0.1)
        base["world_curves_n"] = 257
        base["world_strength"] = 1.0
    elif mode == "rgb":
        base["world_color"] = (1.0, 0.25, 0.1)
        base["world_strength"] = 1.0
    elif mode == "rgb_mix":
        base["world_color"] = (1.0, 0.25, 0.1)
        base["world_mix_type"] = 1
        base["world_strength"] = 1.0
    elif mode == "hdr":
        base["world_image_path_empty"] = False
        base["world_strength"] = 1.0
    elif mode == "nishita":
        base["world_sky_type"] = 3
        base["world_strength"] = 1.0
    elif mode == "teximage":
        base["world_color_image_path"] = "nonempty"
        base["world_tex_vector_mode"] = 3
        base["world_strength"] = 1.0
    elif mode == "sky_map":
        base["world_sky_type"] = 1
        base["world_tex_vector_mode"] = 4
        base["world_strength"] = 1.0
    return base


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    p.add_argument("--out", default="/tmp/quanttrace_slice2at_session.exr")
    p.add_argument("--stock-out", default="/tmp/quanttrace_slice2at_stock.exr")
    p.add_argument("--compare", default="")
    p.add_argument("--render-stock", action="store_true", default=False)
    p.add_argument("--image", default="/tmp/qt_slice2at_env.exr")
    p.add_argument(
        "--mode",
        choices=(
            "math_nest3", "math_mul",
            "rgb", "rgb_mix", "hdr", "nishita", "teximage", "sky_map", "rgb_curves",
            "math_nest4", "env_math", "unlinked",
        ),
        default="math_nest3",
    )
    p.add_argument("--strength", type=float, default=0.7)
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
    import _quanttrace_slice2at_scene as sc2at
    qt_engine._reset_native_probe_for_tests()
    assert qt_engine.kernel_ready()

    scene, cube_obj, lamp, cam, img = sc2at.build_slice2at_scene(
        image_path=args.image,
        mode=args.mode,
        strength=args.strength,
        pull_camera=not args.no_pull_camera,
        env_path=args.image,
    )
    scene.render.resolution_x = scene.render.resolution_y = args.res
    scene.cycles.samples = args.samples
    if hasattr(scene.render, "use_persistent_data"):
        scene.render.use_persistent_data = False

    if args.mode in ("math_nest4", "env_math"):
        try:
            packed = qt_sync.pack_scene(
                scene, depsgraph=bpy.context.evaluated_depsgraph_get()
            )
        except qt_sync.QuantTraceSyncError as e:
            msg = str(e)
            print("QUANTTRACE_SLICE2AT_REFUSE", type(e).__name__, msg)
            if args.mode == "math_nest4":
                if "nest too deep" not in msg.lower() and "2at" not in msg:
                    raise RuntimeError(f"math_nest4 refused but message unexpected: {msg}")
            else:
                if "TEX_ENVIRONMENT" not in msg and "texture" not in msg.lower() and "refused" not in msg.lower():
                    raise RuntimeError(f"env_math refused but message unexpected: {msg}")
            print("QUANTTRACE_SLICE2AT_SMOKE OK refuse")
            return 0
        raise RuntimeError(
            f"{args.mode} packed unexpectedly world_strength={packed.get('world_strength')}"
        )

    expected = _expected_for_mode(args.mode, args.strength)

    if args.render_stock:
        if os.path.isfile(args.stock_out):
            os.unlink(args.stock_out)
        scene.render.filepath = args.stock_out
        t_s = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        print(
            "QUANTTRACE_SLICE2AT_STOCK wall", round(time.perf_counter() - t_s, 3),
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
    got_g = float(packed.get("world_gamma", 1.0))
    got_cn = int(packed.get("world_curves_n", 0) or 0)
    got_mt = int(packed.get("world_mix_type", 0) or 0)
    got_s = float(packed.get("world_strength", 0.0) or 0.0)
    print(
        "QUANTTRACE_SLICE2AT_SMOKE packed",
        "mode", args.mode,
        "world_image_path", packed.get("world_image_path"),
        "world_color_image_path", got_cip,
        "world_tex_vector_mode", got_mode,
        "world_strength", got_s,
        "world_color", got_c,
        "world_sky_type", got_sky,
        "world_gamma", got_g,
        "world_curves_n", got_cn,
        "world_mix_type", got_mt,
    )

    if args.mode in ("hdr", "math_nest3", "math_mul", "unlinked"):
        if not packed.get("world_image_path"):
            raise RuntimeError("packed world_image_path empty — env not packed")
    elif args.mode == "teximage":
        if not got_cip:
            raise RuntimeError("packed world_color_image_path empty")
    elif args.mode not in ("sky_map", "nishita"):
        if packed.get("world_image_path"):
            raise RuntimeError("packed world_image_path set — env should be empty")

    if not _fclose(got_s, expected["world_strength"]):
        raise RuntimeError(
            f"packed world_strength={got_s} expected {expected['world_strength']}"
        )
    if got_cn != expected["world_curves_n"]:
        raise RuntimeError(
            f"packed world_curves_n={got_cn} expected {expected['world_curves_n']}"
        )
    if not _color_close(got_c, expected["world_color"]):
        if args.mode not in ("hdr", "nishita", "teximage", "sky_map", "math_nest3", "math_mul", "unlinked"):
            raise RuntimeError(
                f"packed world_color={got_c} expected {expected['world_color']}"
            )
    if not _fclose(got_g, expected["world_gamma"]):
        raise RuntimeError(f"packed world_gamma={got_g} expected {expected['world_gamma']}")
    if got_mt != expected["world_mix_type"] and args.mode == "rgb_mix":
        raise RuntimeError(f"packed world_mix_type={got_mt} expected {expected['world_mix_type']}")

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
        "QUANTTRACE_SLICE2AT_CTYPES",
        "strength", float(desc.world_strength),
        "curves_n", int(desc.world_curves_n),
        "gamma", float(desc.world_gamma),
        "world_color", tuple(float(desc.world_color[i]) for i in range(3)),
        "ver", ver, "is_tracer", is_tr,
    )
    if abs(float(desc.world_strength) - expected["world_strength"]) > 1e-5:
        raise RuntimeError("ctypes world_strength mismatch")
    if int(desc.world_curves_n) != expected["world_curves_n"]:
        raise RuntimeError("ctypes world_curves_n mismatch")

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
    print(
        "QUANTTRACE_SLICE2AT_SMOKE rc", rc, "wall", round(time.perf_counter() - t0, 3),
        "ver", ver, "is_tracer", is_tr,
        "rgb_min", rgb_min, "rgb_max", rgb_max,
    )
    if rc != 0:
        raise RuntimeError(rc)
    if rgb_max == 0.0:
        raise RuntimeError("session Combined all-zero — world likely missing")

    if args.live_graph:
        unlinked_out = "/tmp/quanttrace_slice2at_stock_unlinked.exr"
        scene_b, *_r = sc2at.build_slice2at_scene(
            image_path=args.image,
            mode="unlinked",
            strength=1.0,
            pull_camera=not args.no_pull_camera,
            env_path=args.image,
        )
        scene_b.render.resolution_x = scene_b.render.resolution_y = args.res
        scene_b.cycles.samples = args.samples
        if hasattr(scene_b.render, "use_persistent_data"):
            scene_b.render.use_persistent_data = False
        scene_b.render.filepath = unlinked_out
        if os.path.isfile(unlinked_out):
            os.unlink(unlinked_out)
        bpy.ops.render.render(write_still=True)
        stock = args.compare or args.stock_out
        if not os.path.isfile(stock):
            raise RuntimeError("live-graph needs --render-stock / --compare stock")
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

        a = load(stock)
        b = load(unlinked_out)
        d = np.abs(a.astype(np.float64) - b.astype(np.float64))
        dmax = float(d.max())
        mae = float(d.mean())
        px = int((d.max(axis=2) >= 1e-3).sum())
        print(
            "QUANTTRACE_SLICE2AT_LIVE",
            "dmax", dmax, "mae", mae, "px_ge_1e-3", px,
        )
        if dmax < 1e-2:
            raise RuntimeError(f"live-graph Δmax={dmax} too small — nest3 no-op?")
        print("QUANTTRACE_SLICE2AT_SMOKE OK live-graph")
        return 0

    if args.compare:
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

        a = load(args.compare)
        b = load(args.out)
        d = np.abs(a.astype(np.float64) - b.astype(np.float64))
        dmax = float(d.max())
        mae = float(d.mean())
        px = int((d.max(axis=2) >= 1e-3).sum())
        gate = "PASS" if (dmax < 1e-3 and px == 0) else "FAIL"
        print(
            "QUANTTRACE_SLICE2AT_COMPARE",
            "res", args.res, "spp", args.samples,
            "dmax", dmax, "mae", mae, "px_ge_1e-3", px, gate,
        )
        if args.pair_png:
            paths = [p.strip() for p in args.pair_png.split(",") if p.strip()]
            _compose_pair_png(args.compare, args.out, paths)
        if gate != "PASS":
            print("QUANTTRACE_SLICE2AT_SMOKE DONE", gate)
            return 1
    print("QUANTTRACE_SLICE2AT_SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
