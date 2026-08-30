# pack_scene Separate Color -> Principled.Roughness -> Session vs stock (Slice 2bj).
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
        print("QUANTTRACE_SLICE2BJ_PAIR", path, "wh", w, h)


def _loft_pack_probe(qt_sync, qt_engine, loft_path):
    if not os.path.isfile(loft_path):
        print("QUANTTRACE_SLICE2BJ_SMOKE loft MISSING", loft_path)
        print("PACK_FAIL loft file missing")
        return 1
    print("QUANTTRACE_SLICE2BJ_SMOKE loft open", loft_path)
    bpy.ops.wm.open_mainfile(filepath=loft_path)
    scene = bpy.context.scene
    try:
        t0 = time.perf_counter()
        packed = qt_sync.pack_scene(
            scene, depsgraph=bpy.context.evaluated_depsgraph_get()
        )
        wall = time.perf_counter() - t0
        inv_n = sum(
            1 for m in packed["meshes"] if int(m.get("rough_separate_enable") or 0)
        )
        print(
            "PACK_OK",
            "n_meshes", len(packed["meshes"]),
            "n_lights", len(packed["lights"]),
            "separate_meshes", inv_n,
            "wall_s", round(wall, 3),
            "version", qt_engine.native_version(),
        )
        print("QUANTTRACE_SLICE2BJ_SMOKE loft PACK_OK (no dmax claim)")
        return 0
    except qt_sync.QuantTraceSyncError as e:
        msg = str(e)
        print("PACK_FAIL", msg)
        print("QUANTTRACE_SLICE2BJ_SMOKE loft PACK_FAIL", type(e).__name__, msg)
        return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    p.add_argument("--out", default="/tmp/quanttrace_slice2bj_session.exr")
    p.add_argument("--stock-out", default="/tmp/quanttrace_slice2bj_stock.exr")
    p.add_argument("--compare", default="")
    p.add_argument("--render-stock", action="store_true", default=False)
    p.add_argument("--image", default="/tmp/qt_slice2bj_rgb.png")
    p.add_argument(
        "--mode",
        choices=(
            "claim", "separate_r", "separate_b", "separate_const",
            "tex", "invert", "ramp", "noise", "mix", "curves", "hdr",
            "hsv", "invert_sep",
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

    import _quanttrace_slice2bj_scene as sc2bj
    scene, cube_obj, lamp, cam, img = sc2bj.build_slice2bj_scene(
        image_path=args.image, mode=args.mode,
    )

    scene.render.resolution_x = scene.render.resolution_y = args.res
    scene.cycles.samples = args.samples
    scene.render.use_persistent_data = False

    refuse = args.expect_refuse or args.mode in ("hsv", "invert_sep")
    deps = bpy.context.evaluated_depsgraph_get()
    try:
        packed = qt_sync.pack_scene(scene, depsgraph=deps)
    except qt_sync.QuantTraceSyncError as e:
        msg = str(e)
        print("QUANTTRACE_SLICE2BJ_PACK_REFUSE", msg)
        if refuse:
            if "Slice 2bj" in msg:
                print("QUANTTRACE_SLICE2BJ_SMOKE REFUSE_OK", msg)
                return 0
            raise RuntimeError(f"refuse missing Slice 2bj tag: {msg}")
        raise

    if refuse:
        raise RuntimeError("expected Slice 2bj refuse but pack_scene succeeded")

    m0 = packed["meshes"][0]
    got_en = int(m0.get("rough_separate_enable", 0) or 0)
    got_ch = int(
        m0.get("rough_separate_channel", 1)
        if m0.get("rough_separate_channel") is not None
        else 1
    )
    got_inv = int(m0.get("rough_invert_enable", 0) or 0)
    got_ramp = int(m0.get("rough_ramp_n", 0) or 0)
    got_img = bool(m0.get("rough_image_path") or "")
    print(
        "QUANTTRACE_SLICE2BJ_PACKED",
        "mode", args.mode,
        "rough_separate_enable", got_en,
        "rough_separate_channel", got_ch,
        "rough_invert_enable", got_inv,
        "rough_ramp_n", got_ramp,
        "rough_image", got_img,
        "roughness", m0.get("roughness"),
        "version", qt_engine.native_version(),
    )
    if args.mode == "claim":
        if got_en != 1:
            raise RuntimeError(f"claim separate_enable={got_en} expected 1")
        if got_ch != 1:
            raise RuntimeError(f"claim channel={got_ch} expected 1 (Green)")
        if not got_img:
            raise RuntimeError("claim expected rough_image_path")
        if got_inv != 0:
            raise RuntimeError(f"claim invert_enable={got_inv} expected 0")
    elif args.mode == "separate_r":
        if got_en != 1 or got_ch != 0:
            raise RuntimeError(f"separate_r enable={got_en} ch={got_ch} expected 1/0")
        if not got_img:
            raise RuntimeError("separate_r expected rough_image_path")
    elif args.mode == "separate_b":
        if got_en != 1 or got_ch != 2:
            raise RuntimeError(f"separate_b enable={got_en} ch={got_ch} expected 1/2")
    elif args.mode == "separate_const":
        if got_en != 0:
            raise RuntimeError(f"separate_const should fold enable=0 got {got_en}")
        if not _fclose(m0.get("roughness", -1), 0.55, 1e-5):
            raise RuntimeError(
                f"separate_const roughness={m0.get('roughness')} expected 0.55"
            )
    elif args.mode == "tex":
        if got_en != 0:
            raise RuntimeError(f"tex 2i identity separate_enable={got_en} expected 0")
        if not got_img:
            raise RuntimeError("tex 2i expected rough_image_path")
    elif args.mode == "invert":
        if got_en != 0:
            raise RuntimeError(f"invert 2be identity separate_enable={got_en} expected 0")
        if got_inv != 1:
            raise RuntimeError(f"invert 2be invert_enable={got_inv} expected 1")
    elif args.mode == "ramp":
        if got_en != 0:
            raise RuntimeError(f"ramp 2ba identity separate_enable={got_en} expected 0")
        if got_ramp == 0:
            raise RuntimeError("ramp 2ba expected ramp_n>0")

    if args.live_graph:
        scene.render.filepath = args.stock_out
        if os.path.isfile(args.stock_out):
            os.unlink(args.stock_out)
        bpy.ops.render.render(write_still=True)
        scene_z, *_ = sc2bj.build_slice2bj_scene(
            image_path=args.image, mode="tex"
        )
        scene_z.render.resolution_x = scene_z.render.resolution_y = args.res
        scene_z.cycles.samples = args.samples
        scene_z.render.filepath = "/tmp/qt_slice2bj_live_tex.exr"
        if os.path.isfile(scene_z.render.filepath):
            os.unlink(scene_z.render.filepath)
        bpy.ops.render.render(write_still=True)
        blender = bpy.app.binary_path or "blender"
        rcode = subprocess.call([
            blender, "--background", "--python",
            os.path.join(root, "tools", "_quanttrace_exr_delta.py"), "--",
            args.stock_out, "/tmp/qt_slice2bj_live_tex.exr",
        ])
        print("QUANTTRACE_SLICE2BJ_LIVE compare rc", rcode)
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
        "QUANTTRACE_SLICE2BJ_CTYPES",
        "separate_enable", int(desc.meshes[0].rough_separate_enable),
        "channel", int(desc.meshes[0].rough_separate_channel),
        "invert_enable", int(desc.meshes[0].rough_invert_enable),
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
        "QUANTTRACE_SLICE2BJ_SMOKE rc", rc, "wall", round(wall, 3),
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
        print("QUANTTRACE_SLICE2BJ_STOCK wrote", args.stock_out)
        if not args.compare:
            args.compare = args.stock_out

    if args.compare:
        blender = bpy.app.binary_path or "blender"
        rcode = subprocess.call([
            blender, "--background", "--python",
            os.path.join(root, "tools", "_quanttrace_exr_delta.py"), "--",
            args.compare, args.out,
        ])
        print("QUANTTRACE_SLICE2BJ_SMOKE compare rc", rcode)
        if args.pair_png and rcode == 0:
            pair = args.pair_png
            copies = [x.strip() for x in pair.split(",") if x.strip()] or [pair]
            proof = os.path.join(root, "docs", "proof", "quanttrace-separate-rough-32-pair.png")
            ws = "/workspace/quanttrace-separate-rough-32-pair.png"
            for extra in (proof, ws):
                if extra not in copies:
                    copies.append(extra)
            try:
                _compose_pair_png(args.compare, args.out, copies)
            except Exception as e:
                print("QUANTTRACE_SLICE2BJ_PAIR FAIL", type(e).__name__, e)
                raise
        if rcode != 0:
            raise SystemExit(rcode)

    print("QUANTTRACE_SLICE2BJ_SMOKE OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main() or 0)
    except Exception as e:
        print("QUANTTRACE_SLICE2BJ_SMOKE FAIL", type(e).__name__, e)
        raise
