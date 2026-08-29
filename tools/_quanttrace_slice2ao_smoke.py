# pack_scene Gamma/HueSat → world Color → Session vs stock Cycles (Slice 2ao).
from __future__ import annotations
import argparse, ctypes, os, sys, time, subprocess
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def _color_close(got, expected, eps=1e-5):
    return all(abs(float(a) - float(b)) <= eps for a, b in zip(got, expected))


def _fclose(got, expected, eps=1e-5):
    return abs(float(got) - float(expected)) <= eps


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
        print("QUANTTRACE_SLICE2AO_PAIR", path, "wh", w, h)


def _expected_for_mode(mode, strength):
    ident_g, ident_h, ident_s, ident_v, ident_f = 1.0, 0.5, 1.0, 1.0, 1.0
    base = dict(
        world_color=(0.0, 0.0, 0.0),
        world_sky_type=0,
        world_color_image_path="",
        world_image_path_empty=True,
        world_gamma=ident_g,
        world_hsv_hue=ident_h,
        world_hsv_sat=ident_s,
        world_hsv_val=ident_v,
        world_hsv_fac=ident_f,
        world_tex_vector_mode=0,
        world_strength=float(strength),
    )
    if mode == "rgb_gamma":
        base["world_color"] = (1.0, 0.25, 0.1)
        base["world_gamma"] = 2.2
    elif mode == "rgb_hsv":
        base["world_color"] = (1.0, 0.25, 0.1)
        base["world_hsv_hue"] = 0.6
        base["world_hsv_sat"] = 1.2
        base["world_hsv_val"] = 0.85
        base["world_hsv_fac"] = 1.0
    elif mode == "rgb_gamma_hsv":
        base["world_color"] = (1.0, 0.25, 0.1)
        base["world_gamma"] = 2.2
        base["world_hsv_hue"] = 0.6
        base["world_hsv_sat"] = 1.2
        base["world_hsv_val"] = 0.85
        base["world_hsv_fac"] = 1.0
    elif mode == "hdr_gamma":
        base["world_image_path_empty"] = False
        base["world_gamma"] = 0.8
    elif mode == "rgb":
        base["world_color"] = (1.0, 0.25, 0.1)
    elif mode == "hdr":
        base["world_image_path_empty"] = False
    elif mode == "nishita":
        base["world_sky_type"] = 3
    elif mode == "teximage":
        base["world_color_image_path"] = "nonempty"
        base["world_tex_vector_mode"] = 3
    elif mode == "unlinked_rgb":
        base["world_color"] = (1.0, 0.25, 0.1)
    return base


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    p.add_argument("--out", default="/tmp/quanttrace_slice2ao_session.exr")
    p.add_argument("--stock-out", default="/tmp/quanttrace_slice2ao_stock.exr")
    p.add_argument("--compare", default="")
    p.add_argument("--render-stock", action="store_true", default=False)
    p.add_argument("--image", default="/tmp/qt_slice2ao_env.exr")
    p.add_argument(
        "--mode",
        choices=(
            "rgb_gamma", "rgb_hsv", "rgb_gamma_hsv", "hdr_gamma",
            "rgb", "hdr", "nishita", "teximage", "noise", "unlinked_rgb",
        ),
        default="rgb_gamma",
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
    import _quanttrace_slice2ao_scene as sc2ao
    qt_engine._reset_native_probe_for_tests()
    assert qt_engine.kernel_ready()

    scene, cube_obj, lamp, cam, img = sc2ao.build_slice2ao_scene(
        image_path=args.image,
        mode=args.mode,
        strength=args.strength,
        pull_camera=not args.no_pull_camera,
        env_path=args.image,
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
            print("QUANTTRACE_SLICE2AO_REFUSE", type(e).__name__, msg)
            if "Slice 2ao" not in msg and "Noise" not in msg and "TEX_NOISE" not in msg and "noise" not in msg.lower():
                if "refused" not in msg.lower():
                    raise RuntimeError(f"noise refused but message unexpected: {msg}")
            print("QUANTTRACE_SLICE2AO_SMOKE OK refuse")
            return 0
        raise RuntimeError(
            f"noise packed unexpectedly world_color={packed.get('world_color')}"
        )

    expected = _expected_for_mode(args.mode, args.strength)

    if args.render_stock:
        if os.path.isfile(args.stock_out):
            os.unlink(args.stock_out)
        scene.render.filepath = args.stock_out
        t_s = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        print(
            "QUANTTRACE_SLICE2AO_STOCK wall", round(time.perf_counter() - t_s, 3),
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
    got_h = float(packed.get("world_hsv_hue", 0.5))
    got_sat = float(packed.get("world_hsv_sat", 1.0))
    got_v = float(packed.get("world_hsv_val", 1.0))
    got_f = float(packed.get("world_hsv_fac", 1.0))
    print(
        "QUANTTRACE_SLICE2AO_SMOKE packed",
        "mode", args.mode,
        "world_image_path", packed.get("world_image_path"),
        "world_color_image_path", got_cip,
        "world_tex_vector_mode", got_mode,
        "world_strength", packed.get("world_strength"),
        "world_color", got_c,
        "world_sky_type", got_sky,
        "world_gamma", got_g,
        "world_hsv", (got_h, got_sat, got_v, got_f),
        "expected_color", expected["world_color"],
        "expected_gamma", expected["world_gamma"],
        "expected_hsv", (
            expected["world_hsv_hue"], expected["world_hsv_sat"],
            expected["world_hsv_val"], expected["world_hsv_fac"],
        ),
        "expected_sky", expected["world_sky_type"],
    )
    if args.mode in ("hdr", "hdr_gamma"):
        if not packed.get("world_image_path"):
            raise RuntimeError("packed world_image_path empty — env not packed")
        if got_cip:
            raise RuntimeError("packed world_color_image_path set on hdr mode")
    elif args.mode == "teximage":
        if not got_cip:
            raise RuntimeError("packed world_color_image_path empty — TEX_IMAGE not packed")
        if packed.get("world_image_path"):
            raise RuntimeError("packed world_image_path set — env should be empty")
        if got_mode != expected["world_tex_vector_mode"]:
            raise RuntimeError(
                f"packed world_tex_vector_mode={got_mode} expected {expected['world_tex_vector_mode']}"
            )
    else:
        if got_cip:
            raise RuntimeError("packed world_color_image_path set unexpectedly")
        if packed.get("world_image_path"):
            raise RuntimeError("packed world_image_path set — env should be empty")

    got_s = float(packed.get("world_strength", 0.0))
    if abs(got_s - expected["world_strength"]) > 1e-6:
        raise RuntimeError(
            f"packed world_strength={got_s} expected {expected['world_strength']}"
        )
    if not _color_close(got_c, expected["world_color"]):
        raise RuntimeError(
            f"packed world_color={got_c} expected {expected['world_color']}"
        )
    if got_sky != expected["world_sky_type"]:
        raise RuntimeError(
            f"packed world_sky_type={got_sky} expected {expected['world_sky_type']}"
        )
    if not _fclose(got_g, expected["world_gamma"]):
        raise RuntimeError(
            f"packed world_gamma={got_g} expected {expected['world_gamma']}"
        )
    if not _fclose(got_h, expected["world_hsv_hue"]):
        raise RuntimeError(
            f"packed world_hsv_hue={got_h} expected {expected['world_hsv_hue']}"
        )
    if not _fclose(got_sat, expected["world_hsv_sat"]):
        raise RuntimeError(
            f"packed world_hsv_sat={got_sat} expected {expected['world_hsv_sat']}"
        )
    if not _fclose(got_v, expected["world_hsv_val"]):
        raise RuntimeError(
            f"packed world_hsv_val={got_v} expected {expected['world_hsv_val']}"
        )
    if not _fclose(got_f, expected["world_hsv_fac"]):
        raise RuntimeError(
            f"packed world_hsv_fac={got_f} expected {expected['world_hsv_fac']}"
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
        "QUANTTRACE_SLICE2AO_CTYPES env_path", desc.world_image_path,
        "color_image_path", desc.world_color_image_path,
        "strength", desc.world_strength,
        "world_color", ctypes_c,
        "world_sky_type", int(desc.world_sky_type),
        "world_gamma", float(desc.world_gamma),
        "world_hsv", (
            float(desc.world_hsv_hue), float(desc.world_hsv_sat),
            float(desc.world_hsv_val), float(desc.world_hsv_fac),
        ),
        "ver", ver, "is_tracer", is_tr,
    )
    if abs(float(desc.world_strength) - expected["world_strength"]) > 1e-6:
        raise RuntimeError(
            f"ctypes world_strength={desc.world_strength} expected {expected['world_strength']}"
        )
    if not _color_close(ctypes_c, expected["world_color"]):
        raise RuntimeError(
            f"ctypes world_color={ctypes_c} expected {expected['world_color']}"
        )
    if int(desc.world_sky_type) != expected["world_sky_type"]:
        raise RuntimeError(
            f"ctypes world_sky_type={desc.world_sky_type} expected {expected['world_sky_type']}"
        )
    if not _fclose(desc.world_gamma, expected["world_gamma"]):
        raise RuntimeError(
            f"ctypes world_gamma={desc.world_gamma} expected {expected['world_gamma']}"
        )
    if not _fclose(desc.world_hsv_hue, expected["world_hsv_hue"]):
        raise RuntimeError("ctypes world_hsv_hue mismatch")
    if not _fclose(desc.world_hsv_sat, expected["world_hsv_sat"]):
        raise RuntimeError("ctypes world_hsv_sat mismatch")
    if not _fclose(desc.world_hsv_val, expected["world_hsv_val"]):
        raise RuntimeError("ctypes world_hsv_val mismatch")
    if not _fclose(desc.world_hsv_fac, expected["world_hsv_fac"]):
        raise RuntimeError("ctypes world_hsv_fac mismatch")
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
        "QUANTTRACE_SLICE2AO_SMOKE rc", rc, "wall", round(time.perf_counter() - t0, 3),
        "ver", ver, "is_tracer", is_tr,
        "rgb_min", rgb_min, "rgb_max", rgb_max, "constant", constant,
    )
    if rc != 0:
        raise RuntimeError(rc)
    if rgb_max == 0.0:
        raise RuntimeError("session Combined all-zero — world likely missing")
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
                    "QUANTTRACE_SLICE2AO_STOCK_VIS min", smin, "max", smax,
                    "constant", smax - smin < 1e-12,
                )
                if smax == 0.0:
                    raise RuntimeError("stock Combined all-zero — world not visible")
            except ImportError:
                print("QUANTTRACE_SLICE2AO_STOCK_VIS skip (no OIIO in this process)")
        blender = bpy.app.binary_path or "blender"
        rcode = subprocess.call([
            blender, "--background", "--python",
            os.path.join(root, "tools", "_quanttrace_exr_delta.py"), "--",
            args.compare, args.out,
        ])
        print("QUANTTRACE_SLICE2AO_SMOKE compare rc", rcode)
        if args.pair_png and rcode == 0:
            pair = args.pair_png
            copies = [pair]
            proof = os.path.join(root, "docs", "proof", "quanttrace-gamma-hsv-32-pair.png")
            ws = "/workspace/quanttrace-gamma-hsv-32-pair.png"
            for extra in (proof, ws):
                if extra not in copies:
                    copies.append(extra)
            try:
                _compose_pair_png(args.compare, args.out, copies)
            except Exception as e:
                print("QUANTTRACE_SLICE2AO_PAIR FAIL", type(e).__name__, e)
                raise
        if rcode != 0:
            raise SystemExit(rcode)

    if args.live_graph:
        if args.mode != "rgb_gamma":
            raise RuntimeError("--live-graph requires --mode rgb_gamma")
        unlinked_out = "/tmp/quanttrace_slice2ao_stock_unlinked_rgb.exr"
        scene_b, *_rest = sc2ao.build_slice2ao_scene(
            image_path=args.image,
            mode="unlinked_rgb",
            strength=args.strength,
            pull_camera=not args.no_pull_camera,
        )
        scene_b.render.resolution_x = scene_b.render.resolution_y = args.res
        scene_b.cycles.samples = args.samples
        if os.path.isfile(unlinked_out):
            os.unlink(unlinked_out)
        scene_b.render.filepath = unlinked_out
        t_b = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        print(
            "QUANTTRACE_SLICE2AO_STOCK_UNLINKED wall",
            round(time.perf_counter() - t_b, 3), "out", unlinked_out,
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
        db = _load(unlinked_out)
        diff = np.abs(da - db)
        dmax = float(diff.max())
        mae = float(diff.mean())
        n_gt = int((diff.max(axis=2) >= 1e-3).sum())
        print(
            "QUANTTRACE_SLICE2AO_LIVE rgb_gamma_vs_unlinked_rgb",
            "dmax", dmax, "mae", mae, "px>=1e-3", n_gt,
            "of", da.shape[0] * da.shape[1],
        )
        if dmax <= 1e-3:
            raise RuntimeError(
                f"live-graph rgb_gamma vs unlinked RGB Δmax={dmax} not > 1e-3 "
                "(gamma not visible — camera/GI)"
            )

    print("QUANTTRACE_SLICE2AO_SMOKE OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main() or 0)
    except Exception as e:
        print("QUANTTRACE_SLICE2AO_SMOKE FAIL", type(e).__name__, e)
        raise
