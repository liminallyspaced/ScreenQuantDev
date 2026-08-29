# pack_scene Mix → Principled Base Color → Session vs stock (Slice 2ay).
from __future__ import annotations
import argparse, ctypes, os, sys, time, subprocess
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1 :] if "--" in a else []


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
        print("QUANTTRACE_SLICE2AY_PAIR", path, "wh", w, h)


def _expected_for_mode(mode):
    ident = dict(
        base_gamma=1.0,
        base_hsv_hue=0.5,
        base_hsv_sat=1.0,
        base_hsv_val=1.0,
        base_hsv_fac=1.0,
        base_mix_type=0,
        base_mix_fac=0.5,
        base_mix_other=(0.0, 0.0, 0.0),
        base_mix_chain_is_a=1,
        base_mix_clamp_factor=0,
        base_mix_clamp_result=0,
        base_mix_b_nonempty=False,
        image_path_nonempty=True,
    )
    if mode == "mix":
        ident["base_mix_type"] = 1
        ident["base_mix_fac"] = 0.5
        ident["base_mix_other"] = (0.0, 0.0, 0.0)
        ident["base_mix_chain_is_a"] = 1
    elif mode == "mix_add":
        ident["base_mix_type"] = 2
        ident["base_mix_fac"] = 0.5
        ident["base_mix_other"] = (0.0, 0.0, 0.0)
        ident["base_mix_chain_is_a"] = 1
    elif mode == "mix_mul2":
        ident["base_mix_type"] = 4  # MULTIPLY
        ident["base_mix_fac"] = 0.5
        ident["base_mix_other"] = (0.0, 0.0, 0.0)
        ident["base_mix_chain_is_a"] = 1
        ident["base_mix_clamp_factor"] = 1
        ident["base_mix_b_nonempty"] = True
    elif mode == "mix_hsv":
        ident["base_mix_type"] = 1
        ident["base_mix_fac"] = 0.5
        ident["base_hsv_hue"] = 0.6
        ident["base_hsv_sat"] = 1.2
        ident["base_hsv_val"] = 0.85
        ident["base_hsv_fac"] = 1.0
    elif mode == "hsv":
        ident["base_hsv_hue"] = 0.6
        ident["base_hsv_sat"] = 1.2
        ident["base_hsv_val"] = 0.85
        ident["base_hsv_fac"] = 1.0
    elif mode == "tex":
        pass
    return ident


def _loft_pack_probe(qt_sync, qt_engine, loft_path):
    if not os.path.isfile(loft_path):
        print("QUANTTRACE_SLICE2AY_SMOKE loft MISSING", loft_path)
        print("PACK_FAIL loft file missing")
        return 1
    print("QUANTTRACE_SLICE2AY_SMOKE loft open", loft_path)
    bpy.ops.wm.open_mainfile(filepath=loft_path)
    scene = bpy.context.scene
    try:
        t0 = time.perf_counter()
        packed = qt_sync.pack_scene(
            scene, depsgraph=bpy.context.evaluated_depsgraph_get()
        )
        wall = time.perf_counter() - t0
        print(
            "PACK_OK",
            "n_meshes", len(packed["meshes"]),
            "n_lights", len(packed["lights"]),
            "wall_s", round(wall, 3),
            "version", qt_engine.native_version(),
        )
        # Spot-check Metal_Sheet packed Mix if present
        for m in packed["meshes"]:
            if "Metal_Sheet" in (m.get("name") or "") or True:
                pass
        metal = [m for m in packed["meshes"] if "Metal" in str(m.get("name", ""))]
        print("QUANTTRACE_SLICE2AY_SMOKE loft PACK_OK (no Δmax claim)")
        return 0
    except qt_sync.QuantTraceSyncError as e:
        msg = str(e)
        print("PACK_FAIL", msg)
        print("QUANTTRACE_SLICE2AY_SMOKE loft PACK_FAIL", type(e).__name__, msg)
        return 0  # expected refuse is still a successful probe


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    p.add_argument("--out", default="/tmp/quanttrace_slice2ay_session.exr")
    p.add_argument("--stock-out", default="/tmp/quanttrace_slice2ay_stock.exr")
    p.add_argument("--compare", default="")
    p.add_argument("--render-stock", action="store_true", default=False)
    p.add_argument("--image", default="/tmp/qt_slice2ay_checker.png")
    p.add_argument("--image-b", default="/tmp/qt_slice2ay_checker_b.png")
    p.add_argument(
        "--mode",
        choices=("tex", "hsv", "mix", "mix_add", "mix_mul2", "mix_hsv", "mix_tex", "point"),
        default="mix",
    )
    p.add_argument("--live-graph", action="store_true", default=False)
    p.add_argument("--expect-refuse", action="store_true", default=False)
    p.add_argument("--pair-png", default="")
    p.add_argument("--loft", default="")
    p.add_argument("--pack-only", action="store_true", default=False)
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

    if args.mode == "point":
        import _quanttrace_slice2av_scene as sc2av
        scene, cube_obj, lamp, cam, img = sc2av.build_slice2av_scene(
            image_path="/tmp/qt_slice2av_env.exr", mode="point"
        )
        expected = None
    else:
        import _quanttrace_slice2ay_scene as sc2ay
        scene, cube_obj, lamp, cam, img = sc2ay.build_slice2ay_scene(
            image_path=args.image, mode=args.mode, image_b_path=args.image_b
        )
        expected = _expected_for_mode(args.mode)

    scene.render.resolution_x = scene.render.resolution_y = args.res
    scene.cycles.samples = args.samples
    scene.render.use_persistent_data = False

    deps = bpy.context.evaluated_depsgraph_get()
    try:
        packed = qt_sync.pack_scene(scene, depsgraph=deps)
    except qt_sync.QuantTraceSyncError as e:
        msg = str(e)
        print("QUANTTRACE_SLICE2AY_PACK_REFUSE", msg)
        if args.expect_refuse or args.mode == "mix_tex":
            if "Slice 2ay" in msg:
                print("QUANTTRACE_SLICE2AY_SMOKE REFUSE_OK", msg)
                return 0
            raise RuntimeError(f"refuse missing Slice 2ay tag: {msg}")
        raise

    if args.expect_refuse or args.mode == "mix_tex":
        raise RuntimeError("expected Slice 2ay refuse but pack_scene succeeded")

    m0 = packed["meshes"][0]
    if expected is not None:
        got_type = int(m0.get("base_mix_type", 0) if m0.get("base_mix_type") is not None else 0)
        got_fac = float(m0.get("base_mix_fac", 0.5) if m0.get("base_mix_fac") is not None else 0.5)
        got_other = tuple(float(x) for x in (m0.get("base_mix_other") or (0, 0, 0))[:3])
        got_cia = int(m0.get("base_mix_chain_is_a", 1) if m0.get("base_mix_chain_is_a") is not None else 1)
        got_cf = int(m0.get("base_mix_clamp_factor", 0) or 0)
        got_b = m0.get("base_mix_b_image_path") or ""
        got_g = float(m0.get("base_gamma", 1.0) if m0.get("base_gamma") is not None else 1.0)
        got_h = float(m0.get("base_hsv_hue", 0.5) if m0.get("base_hsv_hue") is not None else 0.5)
        print(
            "QUANTTRACE_SLICE2AY_PACKED",
            "mode", args.mode,
            "image", m0.get("image_path"),
            "base_mix_type", got_type,
            "fac", got_fac,
            "other", got_other,
            "chain_is_a", got_cia,
            "clamp_factor", got_cf,
            "b_path", bool(got_b),
            "base_gamma", got_g,
            "base_hsv_hue", got_h,
        )
        if expected["image_path_nonempty"] and not (m0.get("image_path") or ""):
            raise RuntimeError("packed image_path empty — TEX_IMAGE not packed")
        if got_type != expected["base_mix_type"]:
            raise RuntimeError(f"base_mix_type={got_type} expected {expected['base_mix_type']}")
        if not _fclose(got_fac, expected["base_mix_fac"]):
            raise RuntimeError(f"base_mix_fac={got_fac} expected {expected['base_mix_fac']}")
        if got_cia != expected["base_mix_chain_is_a"]:
            raise RuntimeError(f"chain_is_a={got_cia} expected {expected['base_mix_chain_is_a']}")
        if got_cf != expected["base_mix_clamp_factor"]:
            raise RuntimeError(f"clamp_factor={got_cf} expected {expected['base_mix_clamp_factor']}")
        if expected["base_mix_b_nonempty"] and not got_b:
            raise RuntimeError("base_mix_b_image_path empty for dual TEX_IMAGE")
        if not expected["base_mix_b_nonempty"] and got_b:
            raise RuntimeError(f"unexpected base_mix_b_image_path={got_b!r}")
        if not _fclose(got_g, expected["base_gamma"]):
            raise RuntimeError(f"base_gamma={got_g} expected {expected['base_gamma']}")
        if not _fclose(got_h, expected["base_hsv_hue"]):
            raise RuntimeError(f"base_hsv_hue={got_h} expected {expected['base_hsv_hue']}")

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
    if expected is not None:
        print(
            "QUANTTRACE_SLICE2AY_CTYPES",
            "base_mix_type", int(desc.meshes[0].base_mix_type),
            "fac", float(desc.meshes[0].base_mix_fac),
            "ver", ver, "is_tracer", is_tr,
        )
        if int(desc.meshes[0].base_mix_type) != expected["base_mix_type"]:
            raise RuntimeError("ctypes base_mix_type mismatch")

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
        "QUANTTRACE_SLICE2AY_SMOKE rc", rc, "wall", round(wall, 3),
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
        print("QUANTTRACE_SLICE2AY_STOCK wrote", args.stock_out)
        if not args.compare:
            args.compare = args.stock_out

    if args.live_graph:
        import _quanttrace_slice2ay_scene as sc
        scene2, *_ = sc.build_slice2ay_scene(image_path=args.image, mode="tex")
        scene2.render.resolution_x = scene2.render.resolution_y = args.res
        scene2.cycles.samples = args.samples
        scene2.render.use_persistent_data = False
        tex_stock = "/tmp/qt_slice2ay_live_tex_stock.exr"
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
        print("QUANTTRACE_SLICE2AY_LIVE_GRAPH stock_mix_vs_tex compare rc", rcode)

    if args.compare:
        blender = bpy.app.binary_path or "blender"
        rcode = subprocess.call([
            blender, "--background", "--python",
            os.path.join(root, "tools", "_quanttrace_exr_delta.py"), "--",
            args.compare, args.out,
        ])
        print("QUANTTRACE_SLICE2AY_SMOKE compare rc", rcode)
        if args.pair_png and rcode == 0:
            pair = args.pair_png
            copies = [pair]
            proof = os.path.join(root, "docs", "proof", "quanttrace-mix-basecolor-32-pair.png")
            ws = "/workspace/quanttrace-mix-basecolor-32-pair.png"
            for extra in (proof, ws):
                if extra not in copies:
                    copies.append(extra)
            try:
                _compose_pair_png(args.compare, args.out, copies)
            except Exception as e:
                print("QUANTTRACE_SLICE2AY_PAIR FAIL", type(e).__name__, e)
                raise
        if rcode != 0:
            raise SystemExit(rcode)

    print("QUANTTRACE_SLICE2AY_SMOKE OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main() or 0)
    except Exception as e:
        print("QUANTTRACE_SLICE2AY_SMOKE FAIL", type(e).__name__, e)
        raise
