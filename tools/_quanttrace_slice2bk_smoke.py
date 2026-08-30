# pack_scene Mix -> Principled.Specular Tint -> Session vs stock (Slice 2bk).
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
        print("QUANTTRACE_SLICE2BK_PAIR", path, "wh", w, h)


def _loft_pack_probe(qt_sync, qt_engine, loft_path):
    if not os.path.isfile(loft_path):
        print("QUANTTRACE_SLICE2BK_SMOKE loft MISSING", loft_path)
        print("PACK_FAIL loft file missing")
        return 1
    print("QUANTTRACE_SLICE2BK_SMOKE loft open", loft_path)
    bpy.ops.wm.open_mainfile(filepath=loft_path)
    scene = bpy.context.scene
    try:
        t0 = time.perf_counter()
        packed = qt_sync.pack_scene(
            scene, depsgraph=bpy.context.evaluated_depsgraph_get()
        )
        wall = time.perf_counter() - t0
        mix_n = sum(
            1 for m in packed["meshes"] if int(m.get("spec_tint_mix_type") or 0)
        )
        fold_n = sum(
            1
            for m in packed["meshes"]
            if (
                abs(float(m.get("specular_tint", (1, 1, 1))[0]) - 1.0) > 1e-6
                or abs(float(m.get("specular_tint", (1, 1, 1))[1]) - 1.0) > 1e-6
                or abs(float(m.get("specular_tint", (1, 1, 1))[2]) - 1.0) > 1e-6
            )
            and not (m.get("spec_tint_image_path") or "")
            and int(m.get("spec_tint_mix_type") or 0) == 0
        )
        print(
            "PACK_OK",
            "n_meshes", len(packed["meshes"]),
            "n_lights", len(packed["lights"]),
            "spec_tint_mix_meshes", mix_n,
            "spec_tint_fold_meshes", fold_n,
            "wall_s", round(wall, 3),
            "version", qt_engine.native_version(),
        )
        print("QUANTTRACE_SLICE2BK_SMOKE loft PACK_OK (no dmax claim)")
        return 0
    except qt_sync.QuantTraceSyncError as e:
        msg = str(e)
        print("PACK_FAIL", msg)
        print("QUANTTRACE_SLICE2BK_SMOKE loft PACK_FAIL", type(e).__name__, msg)
        return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    p.add_argument("--out", default="/tmp/quanttrace_slice2bk_session.exr")
    p.add_argument("--stock-out", default="/tmp/quanttrace_slice2bk_stock.exr")
    p.add_argument("--compare", default="")
    p.add_argument("--render-stock", action="store_true", default=False)
    p.add_argument("--image", default="/tmp/qt_slice2bk_checker.png")
    p.add_argument(
        "--mode",
        choices=(
            "claim", "fold", "mix", "mix_dual", "tex", "mix_base", "separate", "invert", "hdr",
            "fac_group", "fac_fresnel",
        ),
        default="claim",
    )
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

    import _quanttrace_slice2bk_scene as sc2bk
    built = sc2bk.build_slice2bk_scene(image_path=args.image, mode=args.mode)
    scene, cube_obj = built[0], built[1]

    scene.render.resolution_x = scene.render.resolution_y = args.res
    scene.cycles.samples = args.samples
    scene.render.use_persistent_data = False

    refuse = args.expect_refuse or args.mode in ("fac_group", "fac_fresnel")
    deps = bpy.context.evaluated_depsgraph_get()
    try:
        packed = qt_sync.pack_scene(scene, depsgraph=deps)
    except qt_sync.QuantTraceSyncError as e:
        msg = str(e)
        print("QUANTTRACE_SLICE2BK_PACK_REFUSE", msg)
        if refuse:
            if "Slice 2bk" in msg:
                print("QUANTTRACE_SLICE2BK_SMOKE REFUSE_OK", msg)
                return 0
            raise RuntimeError(f"refuse missing Slice 2bk tag: {msg}")
        raise

    if refuse:
        raise RuntimeError("expected Slice 2bk refuse but pack_scene succeeded")

    m0 = packed["meshes"][0]
    got_mix = int(m0.get("spec_tint_mix_type", 0) or 0)
    got_img = bool(m0.get("spec_tint_image_path") or "")
    got_tint = tuple(float(x) for x in (m0.get("specular_tint") or (1, 1, 1))[:3])
    print(
        "QUANTTRACE_SLICE2BK_PACKED",
        "mode", args.mode,
        "spec_tint_mix_type", got_mix,
        "spec_tint_image", got_img,
        "specular_tint", got_tint,
        "mix_fac", m0.get("spec_tint_mix_fac"),
        "version", qt_engine.native_version(),
    )
    if args.mode == "claim":
        if got_mix == 0:
            raise RuntimeError("claim expected mix_type!=0 (Sideboard Mix)")
        if not got_img:
            raise RuntimeError("claim expected spec_tint_image_path")
        gam = float(m0.get("spec_tint_gamma", 1.0) or 1.0)
        if abs(gam - 1.2) > 1e-5:
            raise RuntimeError(f"claim gamma={gam} expected 1.2")
    elif args.mode == "fold":
        if got_mix != 0:
            raise RuntimeError(f"fold should mix_type=0 got {got_mix}")
        if got_img:
            raise RuntimeError("fold should have no image")
        if not all(_fclose(got_tint[i], 0.0) for i in range(3)):
            raise RuntimeError(f"fold specular_tint={got_tint} expected (0,0,0)")
    elif args.mode == "mix":
        if got_mix == 0:
            raise RuntimeError("mix expected mix_type!=0")
        if not got_img:
            raise RuntimeError("mix expected spec_tint_image_path")
    elif args.mode == "mix_dual":
        if got_mix == 0:
            raise RuntimeError("mix_dual expected mix_type!=0")
        if not got_img or not (m0.get("spec_tint_mix_b_image_path") or ""):
            raise RuntimeError("mix_dual expected A+B images")
    elif args.mode == "tex":
        if got_mix != 0:
            raise RuntimeError(f"tex 2u identity mix_type={got_mix} expected 0")
        if not got_img:
            raise RuntimeError("tex 2u expected spec_tint_image_path")

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
        "QUANTTRACE_SLICE2BK_CTYPES",
        "mix_type", int(desc.meshes[0].spec_tint_mix_type),
        "specular_tint",
        float(desc.meshes[0].specular_tint[0]),
        float(desc.meshes[0].specular_tint[1]),
        float(desc.meshes[0].specular_tint[2]),
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
        "QUANTTRACE_SLICE2BK_SMOKE rc", rc, "wall", round(wall, 3),
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
        print("QUANTTRACE_SLICE2BK_STOCK wrote", args.stock_out)
        if not args.compare:
            args.compare = args.stock_out

    if args.compare:
        blender = bpy.app.binary_path or "blender"
        rcode = subprocess.call([
            blender, "--background", "--python",
            os.path.join(root, "tools", "_quanttrace_exr_delta.py"), "--",
            args.compare, args.out,
        ])
        print("QUANTTRACE_SLICE2BK_SMOKE compare rc", rcode)
        if args.pair_png and rcode == 0:
            pair = args.pair_png
            copies = [x.strip() for x in pair.split(",") if x.strip()] or [pair]
            proof = os.path.join(root, "docs", "proof", "quanttrace-spec-tint-mix-32-pair.png")
            ws = "/workspace/quanttrace-spec-tint-mix-32-pair.png"
            for extra in (proof, ws):
                if extra not in copies:
                    copies.append(extra)
            try:
                _compose_pair_png(args.compare, args.out, copies)
            except Exception as e:
                print("QUANTTRACE_SLICE2BK_PAIR FAIL", type(e).__name__, e)
                raise
        if rcode != 0:
            raise SystemExit(rcode)

    print("QUANTTRACE_SLICE2BK_SMOKE OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main() or 0)
    except Exception as e:
        print("QUANTTRACE_SLICE2BK_SMOKE FAIL", type(e).__name__, e)
        raise
