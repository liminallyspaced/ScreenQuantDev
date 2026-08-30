# pack_scene nested constant Mix fold → Mix → Principled Base Color vs stock (Slice 2bg).
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
        print("QUANTTRACE_SLICE2BG_PAIR", path, "wh", w, h)


def _loft_pack_probe(qt_sync, qt_engine, loft_path):
    if not os.path.isfile(loft_path):
        print("QUANTTRACE_SLICE2BG_SMOKE loft MISSING", loft_path)
        print("PACK_FAIL loft file missing")
        return 1
    print("QUANTTRACE_SLICE2BG_SMOKE loft open", loft_path)
    bpy.ops.wm.open_mainfile(filepath=loft_path)
    scene = bpy.context.scene
    try:
        t0 = time.perf_counter()
        packed = qt_sync.pack_scene(
            scene, depsgraph=bpy.context.evaluated_depsgraph_get()
        )
        wall = time.perf_counter() - t0
        fr_n = sum(
            1 for m in packed["meshes"] if int(m.get("base_mix_fresnel_enable") or 0)
        )
        curves_n = sum(
            1 for m in packed["meshes"] if int(m.get("base_curves_n") or 0) > 0
        )
        print(
            "PACK_OK",
            "n_meshes", len(packed["meshes"]),
            "n_lights", len(packed["lights"]),
            "fresnel_mix_meshes", fr_n,
            "curves_meshes", curves_n,
            "wall_s", round(wall, 3),
            "version", qt_engine.native_version(),
        )
        print("QUANTTRACE_SLICE2BG_SMOKE loft PACK_OK (no dmax claim)")
        return 0
    except qt_sync.QuantTraceSyncError as e:
        msg = str(e)
        print("PACK_FAIL", msg)
        print("QUANTTRACE_SLICE2BG_SMOKE loft PACK_FAIL", type(e).__name__, msg)
        return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    p.add_argument("--out", default="/tmp/quanttrace_slice2bg_session.exr")
    p.add_argument("--stock-out", default="/tmp/quanttrace_slice2bg_stock.exr")
    p.add_argument("--compare", default="")
    p.add_argument("--render-stock", action="store_true", default=False)
    p.add_argument("--image", default="/tmp/qt_slice2bg_checker.png")
    p.add_argument(
        "--mode",
        choices=(
            "claim", "mix", "fresnel", "curves", "invert", "point", "hdr",
            "nested_tex", "fac_noise", "unlinked_fac",
        ),
        default="claim",
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

    import _quanttrace_slice2bg_scene as sc2bg
    scene, cube_obj, lamp, cam, img = sc2bg.build_slice2bg_scene(
        image_path=args.image, mode=args.mode,
    )

    scene.render.resolution_x = scene.render.resolution_y = args.res
    scene.cycles.samples = args.samples
    scene.render.use_persistent_data = False

    refuse = args.expect_refuse or args.mode in ("fac_noise", "nested_tex")
    deps = bpy.context.evaluated_depsgraph_get()
    try:
        packed = qt_sync.pack_scene(scene, depsgraph=deps)
    except qt_sync.QuantTraceSyncError as e:
        msg = str(e)
        print("QUANTTRACE_SLICE2BG_PACK_REFUSE", msg)
        if refuse:
            tag = "Slice 2bg" if args.mode == "nested_tex" else "Slice 2bf"
            if tag in msg or (args.mode == "fac_noise" and "Slice 2bf" in msg):
                print("QUANTTRACE_SLICE2BG_SMOKE REFUSE_OK", msg)
                return 0
            raise RuntimeError(f"refuse missing expected tag: {msg}")
        raise

    if refuse:
        raise RuntimeError("expected Slice 2bg/2bf refuse but pack_scene succeeded")

    m0 = packed["meshes"][0]
    got_en = int(
        m0.get("base_mix_fresnel_enable", 0)
        if m0.get("base_mix_fresnel_enable") is not None
        else 0
    )
    got_ior = float(
        m0.get("base_mix_fresnel_ior", 1.45)
        if m0.get("base_mix_fresnel_ior") is not None
        else 1.45
    )
    got_type = int(
        m0.get("base_mix_type", 0) if m0.get("base_mix_type") is not None else 0
    )
    got_curves = int(
        m0.get("base_curves_n", 0) if m0.get("base_curves_n") is not None else 0
    )
    got_chain = int(
        m0.get("base_mix_chain_is_a", 1) if m0.get("base_mix_chain_is_a") is not None else 1
    )
    other = tuple(float(x) for x in (m0.get("base_mix_other") or (0, 0, 0))[:3])
    print(
        "QUANTTRACE_SLICE2BG_PACKED",
        "mode", args.mode,
        "base_mix_type", got_type,
        "fresnel_enable", got_en,
        "fresnel_ior", got_ior,
        "curves_n", got_curves,
        "chain_is_a", got_chain,
        "other", other,
        "base_color", tuple(float(x) for x in (m0.get("base_color") or (0,0,0))[:3]),
        "image", bool(m0.get("image_path") or ""),
        "version", qt_engine.native_version(),
    )
    if args.mode == "claim":
        if got_en != 1:
            raise RuntimeError(f"claim fresnel_enable={got_en} expected 1")
        if got_type != 1:
            raise RuntimeError(f"claim mix_type={got_type} expected 1")
        # Curves folded into Mix B constant — native Curves ABI stays n==0.
        if got_curves != 0:
            raise RuntimeError(f"claim curves_n={got_curves} expected 0 (folded into other)")
        if got_chain != 1:
            raise RuntimeError(f"claim chain_is_a={got_chain} expected 1 (A=const chain)")
        if not _fclose(got_ior, 1.45, 1e-5):
            raise RuntimeError(f"claim fresnel_ior={got_ior} expected 1.45")
        # A = folded Mix.001 ≈ 0.15879; B = Curves(A) ≈ 0.5168 (loft I mid).
        base = tuple(float(x) for x in (m0.get("base_color") or (0, 0, 0))[:3])
        if abs(base[0] - 0.15879037231206894) > 1e-5:
            raise RuntimeError(f"claim base_color={base} expected folded Mix.001")
        if abs(other[0] - 0.5168152451515198) > 1e-4:
            raise RuntimeError(f"claim other={other} expected Curves(folded Mix.001)")
    elif args.mode == "mix":
        if got_en != 0:
            raise RuntimeError(f"mix 2ay identity enable={got_en} expected 0")
        if got_type != 1:
            raise RuntimeError(f"mix 2ay mix_type={got_type} expected 1")
    elif args.mode == "fresnel":
        if got_en != 1:
            raise RuntimeError(f"fresnel 2bf enable={got_en} expected 1")
    elif args.mode == "curves":
        if got_en != 0:
            raise RuntimeError(f"curves 2bd identity enable={got_en} expected 0")
        if got_curves == 0:
            raise RuntimeError("curves 2bd expected curves_n>0")
    elif args.mode == "unlinked_fac":
        if got_en != 0:
            raise RuntimeError(f"unlinked_fac enable={got_en} expected 0")
        if got_type != 1:
            raise RuntimeError(f"unlinked_fac mix_type={got_type} expected 1")
        if got_curves == 0:
            raise RuntimeError("unlinked_fac expected curves_n>0")

    if args.live_graph:
        scene.render.filepath = args.stock_out
        if os.path.isfile(args.stock_out):
            os.unlink(args.stock_out)
        bpy.ops.render.render(write_still=True)
        scene_z, *_ = sc2bg.build_slice2bg_scene(
            image_path=args.image, mode="unlinked_fac"
        )
        scene_z.render.resolution_x = scene_z.render.resolution_y = args.res
        scene_z.cycles.samples = args.samples
        scene_z.render.filepath = "/tmp/qt_slice2bg_live_unlinked.exr"
        if os.path.isfile(scene_z.render.filepath):
            os.unlink(scene_z.render.filepath)
        bpy.ops.render.render(write_still=True)
        blender = bpy.app.binary_path or "blender"
        rcode = subprocess.call([
            blender, "--background", "--python",
            os.path.join(root, "tools", "_quanttrace_exr_delta.py"), "--",
            args.stock_out, "/tmp/qt_slice2bg_live_unlinked.exr",
        ])
        print("QUANTTRACE_SLICE2BG_LIVE compare rc", rcode)
        return 0

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
        "QUANTTRACE_SLICE2BG_CTYPES",
        "fresnel_enable", int(desc.meshes[0].base_mix_fresnel_enable),
        "ior", float(desc.meshes[0].base_mix_fresnel_ior),
        "mix_type", int(desc.meshes[0].base_mix_type),
        "curves_n", int(desc.meshes[0].base_curves_n),
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
        "QUANTTRACE_SLICE2BG_SMOKE rc", rc, "wall", round(wall, 3),
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
        print("QUANTTRACE_SLICE2BG_STOCK wrote", args.stock_out)
        if not args.compare:
            args.compare = args.stock_out

    if args.compare:
        blender = bpy.app.binary_path or "blender"
        rcode = subprocess.call([
            blender, "--background", "--python",
            os.path.join(root, "tools", "_quanttrace_exr_delta.py"), "--",
            args.compare, args.out,
        ])
        print("QUANTTRACE_SLICE2BG_SMOKE compare rc", rcode)
        if args.pair_png and rcode == 0:
            pair = args.pair_png
            copies = [x.strip() for x in pair.split(",") if x.strip()] or [pair]
            proof = os.path.join(root, "docs", "proof", "quanttrace-nested-mix-fold-32-pair.png")
            ws = "/workspace/quanttrace-nested-mix-fold-32-pair.png"
            for extra in (proof, ws):
                if extra not in copies:
                    copies.append(extra)
            try:
                _compose_pair_png(args.compare, args.out, copies)
            except Exception as e:
                print("QUANTTRACE_SLICE2BG_PAIR FAIL", type(e).__name__, e)
                raise
        if rcode != 0:
            raise SystemExit(rcode)

    print("QUANTTRACE_SLICE2BG_SMOKE OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main() or 0)
    except Exception as e:
        print("QUANTTRACE_SLICE2BG_SMOKE FAIL", type(e).__name__, e)
        raise
