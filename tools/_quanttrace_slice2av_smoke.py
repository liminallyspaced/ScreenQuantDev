# pack_scene Mapping POINT → Env Vector → Session vs stock (Slice 2av).
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
        print("QUANTTRACE_SLICE2AV_PAIR", path, "wh", w, h)


def _expected_for_mode(mode, strength, location, rotation_z):
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
        world_map_type=2,
        world_map_location=(0.0, 0.0, 0.0),
        world_map_rotation=(0.0, 0.0, 0.0),
        world_strength=float(strength),
    )
    if mode == "point":
        base["world_image_path_empty"] = False
        base["world_tex_vector_mode"] = 4
        base["world_map_type"] = 0
        base["world_map_location"] = tuple(float(x) for x in location)
        base["world_map_rotation"] = (0.0, 0.0, float(rotation_z))
        base["world_strength"] = 1.0
    elif mode == "point_identity":
        base["world_image_path_empty"] = False
        base["world_tex_vector_mode"] = 4
        base["world_map_type"] = 0
        base["world_map_location"] = (0.0, 0.0, 0.0)
        base["world_map_rotation"] = (0.0, 0.0, 0.0)
        base["world_strength"] = 1.0
    elif mode == "vector":
        base["world_image_path_empty"] = False
        base["world_tex_vector_mode"] = 4
        base["world_map_type"] = 2
        base["world_map_location"] = (0.0, 0.0, 0.0)
        base["world_map_rotation"] = (0.0, 0.0, float(rotation_z))
        base["world_strength"] = 1.0
    elif mode == "env_mul0":
        base["world_strength"] = 0.0
        base["world_image_path_empty"] = False
    elif mode == "math_nest3":
        base["world_strength"] = 0.7
        base["world_image_path_empty"] = False
    elif mode == "hdr":
        base["world_image_path_empty"] = False
        base["world_strength"] = 1.0
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
    elif mode == "nishita":
        base["world_sky_type"] = 3
        base["world_strength"] = 1.0
    elif mode == "teximage":
        base["world_color_image_path"] = "nonempty"
        base["world_tex_vector_mode"] = 3
        base["world_strength"] = 1.0
    return base


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    p.add_argument("--out", default="/tmp/quanttrace_slice2av_session.exr")
    p.add_argument("--stock-out", default="/tmp/quanttrace_slice2av_stock.exr")
    p.add_argument("--compare", default="")
    p.add_argument("--render-stock", action="store_true", default=False)
    p.add_argument("--image", default="/tmp/qt_slice2av_env.exr")
    p.add_argument(
        "--mode",
        choices=(
            "point", "point_identity", "vector", "texture",
            "env_mul0", "math_nest3", "hdr", "rgb", "rgb_mix", "rgb_curves",
            "nishita", "teximage", "loft_probe",
        ),
        default="point",
    )
    p.add_argument("--strength", type=float, default=1.0)
    p.add_argument("--scale", type=float, nargs=3, default=(1.0, 1.0, 1.0))
    p.add_argument("--location", type=float, nargs=3, default=(0.15, 0.0, 0.0))
    p.add_argument("--rotation-z", type=float, default=0.7)
    p.add_argument("--live-graph", action="store_true", default=False)
    p.add_argument("--pair-png", default="")
    p.add_argument("--loft", default="/workspace/scenequant/work/bench/loft.blend")
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
    qt_engine._reset_native_probe_for_tests()
    assert qt_engine.kernel_ready()

    if args.mode == "loft_probe":
        loft = args.loft
        if not os.path.isfile(loft):
            raise RuntimeError(f"loft.blend missing: {loft}")
        bpy.ops.wm.open_mainfile(filepath=loft)
        scene = bpy.context.scene
        try:
            wi = qt_sync._world_info(scene)
            print(
                "QUANTTRACE_SLICE2AV_LOFT_PACKED",
                "world_strength", wi.get("world_strength"),
                "world_image_path", bool(wi.get("world_image_path")),
                "world_tex_vector_mode", wi.get("world_tex_vector_mode"),
                "world_map_type", wi.get("world_map_type"),
                "world_map_location", wi.get("world_map_location"),
                "world_map_rotation", wi.get("world_map_rotation"),
                "world_map_scale", wi.get("world_map_scale"),
                "world_gamma", wi.get("world_gamma"),
                "world_hsv_hue", wi.get("world_hsv_hue"),
                "world_hsv_sat", wi.get("world_hsv_sat"),
                "world_mix_type", wi.get("world_mix_type"),
                "world_mix_fac", wi.get("world_mix_fac"),
            )
        except qt_sync.QuantTraceSyncError as e:
            print("QUANTTRACE_SLICE2AV_LOFT_REFUSE", type(e).__name__, str(e))
            print("QUANTTRACE_SLICE2AV_SMOKE OK loft_probe")
            return 0
        try:
            packed = qt_sync.pack_scene(
                scene, depsgraph=bpy.context.evaluated_depsgraph_get()
            )
            print(
                "QUANTTRACE_SLICE2AV_LOFT_SCENE_PACKED",
                "n_meshes", packed.get("n_meshes"),
                "n_lights", packed.get("n_lights"),
            )
        except qt_sync.QuantTraceSyncError as e:
            print("QUANTTRACE_SLICE2AV_LOFT_SCENE_REFUSE", type(e).__name__, str(e))
        print("QUANTTRACE_SLICE2AV_SMOKE OK loft_probe")
        return 0

    sys.path.insert(0, os.path.join(root, "tools"))
    import _quanttrace_slice2av_scene as sc2av

    scene, cube_obj, lamp, cam, img = sc2av.build_slice2av_scene(
        image_path=args.image,
        mode=args.mode,
        strength=args.strength,
        scale=tuple(args.scale),
        location=tuple(args.location),
        rotation_z=args.rotation_z,
        env_path=args.image,
    )
    scene.render.resolution_x = scene.render.resolution_y = args.res
    scene.cycles.samples = args.samples
    if hasattr(scene.render, "use_persistent_data"):
        scene.render.use_persistent_data = False

    if args.mode == "texture":
        try:
            packed = qt_sync.pack_scene(
                scene, depsgraph=bpy.context.evaluated_depsgraph_get()
            )
        except qt_sync.QuantTraceSyncError as e:
            msg = str(e)
            print("QUANTTRACE_SLICE2AV_REFUSE", type(e).__name__, msg)
            if "TEXTURE" not in msg.upper() and "2av" not in msg:
                raise RuntimeError(f"texture refused but message unexpected: {msg}")
            print("QUANTTRACE_SLICE2AV_SMOKE OK refuse")
            return 0
        raise RuntimeError(
            f"texture packed unexpectedly map_type={packed.get('world_map_type')}"
        )

    expected = _expected_for_mode(
        args.mode, args.strength, args.location, args.rotation_z,
    )

    if args.render_stock:
        if os.path.isfile(args.stock_out):
            os.unlink(args.stock_out)
        scene.render.filepath = args.stock_out
        t_s = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        print(
            "QUANTTRACE_SLICE2AV_STOCK wall", round(time.perf_counter() - t_s, 3),
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
    got_mt = int(packed.get("world_map_type", 2) if packed.get("world_map_type") is not None else 2)
    got_loc = tuple(float(x) for x in (packed.get("world_map_location") or (0, 0, 0)))
    got_rot = tuple(float(x) for x in (packed.get("world_map_rotation") or (0, 0, 0)))
    got_g = float(packed.get("world_gamma", 1.0))
    got_cn = int(packed.get("world_curves_n", 0) or 0)
    got_mix = int(packed.get("world_mix_type", 0) or 0)
    got_s = float(packed.get("world_strength") if packed.get("world_strength") is not None else 0.0)
    print(
        "QUANTTRACE_SLICE2AV_SMOKE packed",
        "mode", args.mode,
        "world_image_path", packed.get("world_image_path"),
        "world_color_image_path", got_cip,
        "world_tex_vector_mode", got_mode,
        "world_map_type", got_mt,
        "world_map_location", got_loc,
        "world_map_rotation", got_rot,
        "world_strength", got_s,
        "world_color", got_c,
        "world_sky_type", got_sky,
        "world_gamma", got_g,
        "world_curves_n", got_cn,
        "world_mix_type", got_mix,
    )

    if args.mode in ("point", "point_identity", "vector", "hdr", "env_mul0", "math_nest3"):
        if not packed.get("world_image_path"):
            raise RuntimeError("packed world_image_path empty — env not packed")
    elif args.mode == "teximage":
        if not got_cip:
            raise RuntimeError("packed world_color_image_path empty")
    elif args.mode not in ("nishita",):
        if packed.get("world_image_path"):
            raise RuntimeError("packed world_image_path set — env should be empty")

    if not _fclose(got_s, expected["world_strength"]):
        raise RuntimeError(
            f"packed world_strength={got_s} expected {expected['world_strength']}"
        )
    if got_mode != expected["world_tex_vector_mode"] and args.mode in (
        "point", "point_identity", "vector", "teximage",
    ):
        raise RuntimeError(
            f"packed world_tex_vector_mode={got_mode} expected {expected['world_tex_vector_mode']}"
        )
    if got_mt != expected["world_map_type"] and args.mode in (
        "point", "point_identity", "vector",
    ):
        raise RuntimeError(
            f"packed world_map_type={got_mt} expected {expected['world_map_type']}"
        )
    if args.mode == "point":
        if not _color_close(got_loc, expected["world_map_location"]):
            raise RuntimeError(
                f"packed world_map_location={got_loc} expected {expected['world_map_location']}"
            )
        if not _fclose(got_rot[2], expected["world_map_rotation"][2]):
            raise RuntimeError(
                f"packed world_map_rotation={got_rot} expected {expected['world_map_rotation']}"
            )
    if got_cn != expected["world_curves_n"]:
        raise RuntimeError(
            f"packed world_curves_n={got_cn} expected {expected['world_curves_n']}"
        )
    if not _color_close(got_c, expected["world_color"]):
        if args.mode not in (
            "hdr", "nishita", "teximage",
            "point", "point_identity", "vector", "env_mul0", "math_nest3",
        ):
            raise RuntimeError(
                f"packed world_color={got_c} expected {expected['world_color']}"
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
        "QUANTTRACE_SLICE2AV_CTYPES",
        "strength", float(desc.world_strength),
        "map_type", int(desc.world_map_type),
        "map_loc", tuple(float(desc.world_map_location[i]) for i in range(3)),
        "map_rot", tuple(float(desc.world_map_rotation[i]) for i in range(3)),
        "tex_mode", int(desc.world_tex_vector_mode),
        "ver", ver, "is_tracer", is_tr,
    )
    if args.mode in ("point", "point_identity", "vector"):
        if int(desc.world_map_type) != expected["world_map_type"]:
            raise RuntimeError("ctypes world_map_type mismatch")
        if int(desc.world_tex_vector_mode) != expected["world_tex_vector_mode"]:
            raise RuntimeError("ctypes world_tex_vector_mode mismatch")

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
        "QUANTTRACE_SLICE2AV_SMOKE rc", rc, "wall", round(time.perf_counter() - t0, 3),
        "ver", ver, "is_tracer", is_tr,
        "rgb_min", rgb_min, "rgb_max", rgb_max,
    )
    if rc != 0:
        raise RuntimeError(rc)
    if rgb_max == 0.0 and args.mode != "env_mul0":
        raise RuntimeError("session Combined all-zero — world likely missing")

    if args.live_graph:
        vector_out = "/tmp/quanttrace_slice2av_stock_vector.exr"
        scene_b, *_r = sc2av.build_slice2av_scene(
            image_path=args.image,
            mode="vector",
            strength=1.0,
            scale=tuple(args.scale),
            location=(0.0, 0.0, 0.0),
            rotation_z=args.rotation_z,
            env_path=args.image,
        )
        scene_b.render.resolution_x = scene_b.render.resolution_y = args.res
        scene_b.cycles.samples = args.samples
        if hasattr(scene_b.render, "use_persistent_data"):
            scene_b.render.use_persistent_data = False
        scene_b.render.filepath = vector_out
        if os.path.isfile(vector_out):
            os.unlink(vector_out)
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
        b = load(vector_out)
        d = np.abs(a.astype(np.float64) - b.astype(np.float64))
        dmax = float(d.max())
        mae = float(d.mean())
        px = int((d.max(axis=2) >= 1e-3).sum())
        print(
            "QUANTTRACE_SLICE2AV_LIVE",
            "dmax", dmax, "mae", mae, "px_ge_1e-3", px,
        )
        if dmax < 1e-3:
            raise RuntimeError(
                f"live-graph Δmax={dmax} too small — POINT loc no-op vs VECTOR?"
            )
        print("QUANTTRACE_SLICE2AV_SMOKE OK live-graph")
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
            "QUANTTRACE_SLICE2AV_COMPARE",
            "res", args.res, "spp", args.samples,
            "dmax", dmax, "mae", mae, "px_ge_1e-3", px, gate,
        )
        if args.pair_png:
            paths = [p.strip() for p in args.pair_png.split(",") if p.strip()]
            _compose_pair_png(args.compare, args.out, paths)
        if gate != "PASS":
            print("QUANTTRACE_SLICE2AV_SMOKE DONE", gate)
            return 1
    print("QUANTTRACE_SLICE2AV_SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
