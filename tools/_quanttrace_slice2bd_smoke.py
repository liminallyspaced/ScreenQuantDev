# pack_scene RGB Curves → Principled Base Color → Session vs stock (Slice 2bd).
from __future__ import annotations
import argparse, ctypes, os, sys, time, subprocess
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1 :] if "--" in a else []


def _fclose(got, expected, eps=1e-5):
    return abs(float(got) - float(expected)) <= eps


def _compose_pair_png(stock_path, session_path, out_paths):
    import OpenImageIO as oiio
    import numpy as np

    def load(path):
        inp = oiio.ImageInput.open(path)
        spec = inp.spec()
        pix = np.asarray(inp.read_image(oiio.FLOAT), dtype="float32").reshape(
            spec.height, spec.width, spec.nchannels
        )
        inp.close()
        return pix[:, :, :3]

    a = load(stock_path)
    b = load(session_path)
    diff = np.abs(a.astype("float64") - b.astype("float64"))
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
        print("QUANTTRACE_SLICE2BD_PAIR", path, "wh", w, h)


def _loft_pack_probe(qt_sync, qt_engine, loft_path):
    if not os.path.isfile(loft_path):
        print("QUANTTRACE_SLICE2BD_SMOKE loft MISSING", loft_path)
        print("PACK_FAIL loft file missing")
        return 1
    print("QUANTTRACE_SLICE2BD_SMOKE loft open", loft_path)
    bpy.ops.wm.open_mainfile(filepath=loft_path)
    scene = bpy.context.scene
    try:
        t0 = time.perf_counter()
        packed = qt_sync.pack_scene(
            scene, depsgraph=bpy.context.evaluated_depsgraph_get()
        )
        wall = time.perf_counter() - t0
        curves_n = sum(
            1 for m in packed["meshes"] if int(m.get("base_curves_n") or 0) > 0
        )
        print(
            "PACK_OK",
            "n_meshes", len(packed["meshes"]),
            "n_lights", len(packed["lights"]),
            "base_curves_meshes", curves_n,
            "wall_s", round(wall, 3),
            "version", qt_engine.native_version(),
        )
        print("QUANTTRACE_SLICE2BD_SMOKE loft PACK_OK (no dmax claim)")
        return 0
    except qt_sync.QuantTraceSyncError as e:
        msg = str(e)
        print("PACK_FAIL", msg)
        print("QUANTTRACE_SLICE2BD_SMOKE loft PACK_FAIL", type(e).__name__, msg)
        return 0


def _expected_for_mode(mode):
    ident = dict(
        base_gamma=1.0,
        base_hsv_hue=0.5,
        base_hsv_sat=1.0,
        base_hsv_val=1.0,
        base_hsv_fac=1.0,
        base_mix_type=0,
        base_curves_n_nonzero=False,
        image_path_nonempty=False,
        base_color=(0.8, 0.8, 0.8),
    )
    if mode == "curves":
        ident["base_curves_n_nonzero"] = True
        ident["base_color"] = (1.0, 0.25, 0.1)
    elif mode == "unlinked_rgb":
        ident["base_color"] = (1.0, 0.25, 0.1)
    elif mode == "curves_tex":
        ident["base_curves_n_nonzero"] = True
        ident["image_path_nonempty"] = True
    elif mode == "curves_mix":
        ident["base_curves_n_nonzero"] = True
        ident["image_path_nonempty"] = True
        ident["base_mix_type"] = 1
    elif mode == "curves_hsv":
        ident["base_curves_n_nonzero"] = True
        ident["image_path_nonempty"] = True
        ident["base_hsv_hue"] = 0.6
        ident["base_hsv_sat"] = 1.2
        ident["base_hsv_val"] = 0.85
        ident["base_hsv_fac"] = 1.0
    elif mode == "mix":
        ident["image_path_nonempty"] = True
        ident["base_mix_type"] = 1
    elif mode == "hsv":
        ident["image_path_nonempty"] = True
        ident["base_hsv_hue"] = 0.6
        ident["base_hsv_sat"] = 1.2
        ident["base_hsv_val"] = 0.85
        ident["base_hsv_fac"] = 1.0
    elif mode == "tex":
        ident["image_path_nonempty"] = True
    return ident


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    p.add_argument("--out", default="/tmp/quanttrace_slice2bd_session.exr")
    p.add_argument("--stock-out", default="/tmp/quanttrace_slice2bd_stock.exr")
    p.add_argument("--compare", default="")
    p.add_argument("--render-stock", action="store_true", default=False)
    p.add_argument("--image", default="/tmp/qt_slice2bd_checker.png")
    p.add_argument("--image-b", default="/tmp/qt_slice2bd_checker_b.png")
    p.add_argument(
        "--mode",
        choices=(
            "curves", "curves_tex", "curves_mix", "curves_hsv",
            "unlinked_rgb", "fac_linked",
            "tex", "hsv", "mix",
            "point", "hdr", "noise", "bevel",
        ),
        default="curves",
    )
    p.add_argument("--live-graph", action="store_true", default=False)
    p.add_argument("--expect-refuse", action="store_true", default=False)
    p.add_argument("--pair-png", default="")
    p.add_argument("--loft", default="")
    p.add_argument("--pack-only", action="store_true", default=False)
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
    qt_engine._reset_native_probe_for_tests()
    assert qt_engine.kernel_ready()

    if args.loft and args.pack_only:
        return _loft_pack_probe(qt_sync, qt_engine, args.loft)

    expected = None
    if args.mode == "point":
        import _quanttrace_slice2av_scene as sc2av
        scene, cube_obj, lamp, cam, img = sc2av.build_slice2av_scene(
            image_path="/tmp/qt_slice2av_env.exr", mode="point"
        )
    elif args.mode == "hdr":
        import _quanttrace_slice2aa_scene as sc2aa
        scene, cube_obj, lamp, cam, img = sc2aa.build_slice2aa_scene(
            image_path="/tmp/qt_slice2aa_env.exr",
            projection="EQUIRECTANGULAR",
            strength=1.0,
            black_world=False,
        )
    elif args.mode == "noise":
        import _quanttrace_slice2bc_scene as sc2bc
        scene, cube_obj, lamp, cam, img = sc2bc.build_slice2bc_scene(mode="noise")
    elif args.mode == "bevel":
        import _quanttrace_slice2az_scene as sc2az
        scene, cube_obj, lamp, cam, img = sc2az.build_slice2az_scene(mode="bevel")
    else:
        import _quanttrace_slice2bd_scene as sc2bd
        scene, cube_obj, lamp, cam, img = sc2bd.build_slice2bd_scene(
            image_path=args.image,
            mode=args.mode,
            image_b_path=args.image_b,
            pull_camera=not args.no_pull_camera,
        )
        expected = _expected_for_mode(args.mode)

    scene.render.resolution_x = scene.render.resolution_y = args.res
    scene.cycles.samples = args.samples
    scene.render.use_persistent_data = False

    refuse = args.expect_refuse or args.mode == "fac_linked"
    deps = bpy.context.evaluated_depsgraph_get()
    try:
        packed = qt_sync.pack_scene(scene, depsgraph=deps)
    except qt_sync.QuantTraceSyncError as e:
        msg = str(e)
        print("QUANTTRACE_SLICE2BD_PACK_REFUSE", msg)
        if refuse:
            if "Slice 2bd" in msg:
                print("QUANTTRACE_SLICE2BD_SMOKE REFUSE_OK", msg)
                return 0
            raise RuntimeError(f"refuse missing Slice 2bd tag: {msg}")
        raise

    if refuse:
        raise RuntimeError("expected Slice 2bd refuse but pack_scene succeeded")

    m0 = packed["meshes"][0]
    got_n = int(m0.get("base_curves_n", 0) or 0)
    got_fac = float(m0.get("base_curves_fac", 1.0) if m0.get("base_curves_fac") is not None else 1.0)
    got_mix = int(m0.get("base_mix_type", 0) if m0.get("base_mix_type") is not None else 0)
    got_h = float(m0.get("base_hsv_hue", 0.5) if m0.get("base_hsv_hue") is not None else 0.5)
    got_c = tuple(float(x) for x in (m0.get("base_color") or (0, 0, 0))[:3])
    print(
        "QUANTTRACE_SLICE2BD_PACKED",
        "mode", args.mode,
        "image", bool(m0.get("image_path")),
        "base_curves_n", got_n,
        "base_curves_fac", got_fac,
        "base_mix_type", got_mix,
        "base_hsv_hue", got_h,
        "base_color", got_c,
        "version", qt_engine.native_version(),
    )
    if expected is not None:
        if expected["base_curves_n_nonzero"]:
            if got_n != 257:
                raise RuntimeError(f"base_curves_n={got_n} expected 257")
            if abs(got_fac - 1.0) > 1e-6:
                raise RuntimeError(f"base_curves_fac={got_fac} expected 1.0")
        else:
            if got_n != 0:
                raise RuntimeError(f"identity skip expected base_curves_n=0 got {got_n}")
        if expected["image_path_nonempty"] and not (m0.get("image_path") or ""):
            raise RuntimeError("packed image_path empty — TEX_IMAGE not packed")
        if got_mix != expected["base_mix_type"]:
            raise RuntimeError(f"base_mix_type={got_mix} expected {expected['base_mix_type']}")
        if not _fclose(got_h, expected["base_hsv_hue"]):
            raise RuntimeError(f"base_hsv_hue={got_h} expected {expected['base_hsv_hue']}")
        if expected["base_color"] != (0.8, 0.8, 0.8):
            if any(abs(a - b) > 1e-4 for a, b in zip(got_c, expected["base_color"])):
                raise RuntimeError(f"base_color={got_c} expected {expected['base_color']}")

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
        "QUANTTRACE_SLICE2BD_CTYPES",
        "curves_n", int(desc.meshes[0].base_curves_n),
        "fac", float(desc.meshes[0].base_curves_fac),
        "mix", int(desc.meshes[0].base_mix_type),
        "ver", ver, "is_tracer", is_tr,
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
    wall = time.perf_counter() - t0
    print(
        "QUANTTRACE_SLICE2BD_SMOKE rc", rc, "wall", round(wall, 3),
        "ver", ver, "is_tracer", is_tr,
        "mode", args.mode, "res", args.res, "spp", args.samples,
    )
    if rc != 0:
        raise RuntimeError(rc)

    if args.render_stock:
        scene.render.filepath = args.stock_out
        if os.path.isfile(args.stock_out):
            os.unlink(args.stock_out)
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2BD_STOCK wrote", args.stock_out)
        if not args.compare:
            args.compare = args.stock_out

    if args.live_graph:
        import _quanttrace_slice2bd_scene as sc
        scene2, *_ = sc.build_slice2bd_scene(
            image_path=args.image, mode="unlinked_rgb",
            pull_camera=not args.no_pull_camera,
        )
        scene2.render.resolution_x = scene2.render.resolution_y = args.res
        scene2.cycles.samples = args.samples
        scene2.render.use_persistent_data = False
        tex_stock = "/tmp/qt_slice2bd_live_unlinked_stock.exr"
        scene2.render.filepath = tex_stock
        bpy.ops.render.render(write_still=True)
        if not args.compare or not os.path.isfile(args.compare):
            scene.render.filepath = args.stock_out
            bpy.ops.render.render(write_still=True)
            args.compare = args.stock_out
        blender = bpy.app.binary_path or "blender"
        rcode = subprocess.call([
            blender, "--background", "--python",
            os.path.join(root, "tools", "_quanttrace_exr_delta.py"), "--",
            args.compare, tex_stock,
        ])
        print("QUANTTRACE_SLICE2BD_LIVE_GRAPH stock_curves_vs_unlinked compare rc", rcode)

    if args.compare:
        blender = bpy.app.binary_path or "blender"
        rcode = subprocess.call([
            blender, "--background", "--python",
            os.path.join(root, "tools", "_quanttrace_exr_delta.py"), "--",
            args.compare, args.out,
        ])
        print("QUANTTRACE_SLICE2BD_SMOKE compare rc", rcode)
        if args.pair_png and rcode == 0:
            pair = args.pair_png
            copies = [pair]
            proof = os.path.join(root, "docs", "proof", "quanttrace-base-curves-32-pair.png")
            ws = "/workspace/quanttrace-base-curves-32-pair.png"
            for extra in (proof, ws):
                if extra not in copies:
                    copies.append(extra)
            try:
                _compose_pair_png(args.compare, args.out, copies)
            except Exception as e:
                print("QUANTTRACE_SLICE2BD_PAIR FAIL", type(e).__name__, e)
                raise
        if rcode != 0:
            raise SystemExit(rcode)

    print("QUANTTRACE_SLICE2BD_SMOKE OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main() or 0)
    except Exception as e:
        print("QUANTTRACE_SLICE2BD_SMOKE FAIL", type(e).__name__, e)
        raise
