# pack_scene Gamma/HueSat → Principled Base Color → Session vs stock (Slice 2ax).
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
        print("QUANTTRACE_SLICE2AX_PAIR", path, "wh", w, h)


def _expected_for_mode(mode):
    ident_g, ident_h, ident_s, ident_v, ident_f = 1.0, 0.5, 1.0, 1.0, 1.0
    base = dict(
        base_gamma=ident_g,
        base_hsv_hue=ident_h,
        base_hsv_sat=ident_s,
        base_hsv_val=ident_v,
        base_hsv_fac=ident_f,
        image_path_nonempty=True,
    )
    if mode == "hsv":
        base["base_hsv_hue"] = 0.6
        base["base_hsv_sat"] = 1.2
        base["base_hsv_val"] = 0.85
        base["base_hsv_fac"] = 1.0
    elif mode == "gamma":
        base["base_gamma"] = 2.2
    elif mode == "gamma_hsv":
        base["base_gamma"] = 2.2
        base["base_hsv_hue"] = 0.6
        base["base_hsv_sat"] = 1.2
        base["base_hsv_val"] = 0.85
        base["base_hsv_fac"] = 1.0
    elif mode == "tex":
        pass
    return base


def _loft_pack_probe(qt_sync, qt_engine, loft_path):
    if not os.path.isfile(loft_path):
        print("QUANTTRACE_SLICE2AX_SMOKE loft MISSING", loft_path)
        print("PACK_FAIL loft file missing")
        return 1
    print("QUANTTRACE_SLICE2AX_SMOKE loft open", loft_path)
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
        print("QUANTTRACE_SLICE2AX_SMOKE loft PACK_OK (no Δmax claim)")
        return 0
    except qt_sync.QuantTraceSyncError as e:
        msg = str(e)
        print("PACK_FAIL", msg)
        print("QUANTTRACE_SLICE2AX_SMOKE loft PACK_FAIL", type(e).__name__, msg)
        return 0  # expected refuse is still a successful probe


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    p.add_argument("--out", default="/tmp/quanttrace_slice2ax_session.exr")
    p.add_argument("--stock-out", default="/tmp/quanttrace_slice2ax_stock.exr")
    p.add_argument("--compare", default="")
    p.add_argument("--render-stock", action="store_true", default=False)
    p.add_argument("--image", default="/tmp/qt_slice2ax_checker.png")
    p.add_argument(
        "--mode",
        choices=("tex", "hsv", "gamma", "gamma_hsv"),
        default="hsv",
    )
    p.add_argument("--live-graph", action="store_true", default=False)
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

    import _quanttrace_slice2ax_scene as sc2ax

    scene, cube_obj, lamp, cam, img = sc2ax.build_slice2ax_scene(
        image_path=args.image, mode=args.mode
    )
    scene.render.resolution_x = scene.render.resolution_y = args.res
    scene.cycles.samples = args.samples

    expected = _expected_for_mode(args.mode)
    deps = bpy.context.evaluated_depsgraph_get()
    packed = qt_sync.pack_scene(scene, depsgraph=deps)
    m0 = packed["meshes"][0]
    got_g = float(m0.get("base_gamma", 1.0))
    got_h = float(m0.get("base_hsv_hue", 0.5))
    got_s = float(m0.get("base_hsv_sat", 1.0))
    got_v = float(m0.get("base_hsv_val", 1.0))
    got_f = float(m0.get("base_hsv_fac", 1.0))
    print(
        "QUANTTRACE_SLICE2AX_PACKED",
        "mode", args.mode,
        "image", m0.get("image_path"),
        "base_gamma", got_g,
        "base_hsv", (got_h, got_s, got_v, got_f),
        "expected_gamma", expected["base_gamma"],
        "expected_hsv", (
            expected["base_hsv_hue"], expected["base_hsv_sat"],
            expected["base_hsv_val"], expected["base_hsv_fac"],
        ),
    )
    if expected["image_path_nonempty"] and not (m0.get("image_path") or ""):
        raise RuntimeError("packed image_path empty — TEX_IMAGE not packed")
    if not _fclose(got_g, expected["base_gamma"]):
        raise RuntimeError(f"packed base_gamma={got_g} expected {expected['base_gamma']}")
    if not _fclose(got_h, expected["base_hsv_hue"]):
        raise RuntimeError(f"packed base_hsv_hue={got_h} expected {expected['base_hsv_hue']}")
    if not _fclose(got_s, expected["base_hsv_sat"]):
        raise RuntimeError(f"packed base_hsv_sat={got_s} expected {expected['base_hsv_sat']}")
    if not _fclose(got_v, expected["base_hsv_val"]):
        raise RuntimeError(f"packed base_hsv_val={got_v} expected {expected['base_hsv_val']}")
    if not _fclose(got_f, expected["base_hsv_fac"]):
        raise RuntimeError(f"packed base_hsv_fac={got_f} expected {expected['base_hsv_fac']}")

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
        "QUANTTRACE_SLICE2AX_CTYPES",
        "base_gamma", float(desc.meshes[0].base_gamma),
        "base_hsv", (
            float(desc.meshes[0].base_hsv_hue),
            float(desc.meshes[0].base_hsv_sat),
            float(desc.meshes[0].base_hsv_val),
            float(desc.meshes[0].base_hsv_fac),
        ),
        "ver", ver, "is_tracer", is_tr,
    )
    if not _fclose(desc.meshes[0].base_gamma, expected["base_gamma"]):
        raise RuntimeError("ctypes base_gamma mismatch")
    if not _fclose(desc.meshes[0].base_hsv_hue, expected["base_hsv_hue"]):
        raise RuntimeError("ctypes base_hsv_hue mismatch")

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
        "QUANTTRACE_SLICE2AX_SMOKE rc", rc, "wall", round(wall, 3),
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
        print("QUANTTRACE_SLICE2AX_STOCK wrote", args.stock_out)
        if not args.compare:
            args.compare = args.stock_out

    if args.live_graph:
        # Stock hsv vs tex-only must be clearly live (Δmax ≫ 1e-3).
        import _quanttrace_slice2ax_scene as sc
        scene2, *_ = sc.build_slice2ax_scene(image_path=args.image, mode="tex")
        scene2.render.resolution_x = scene2.render.resolution_y = args.res
        scene2.cycles.samples = args.samples
        tex_stock = "/tmp/qt_slice2ax_live_tex_stock.exr"
        scene2.render.filepath = tex_stock
        bpy.ops.render.render(write_still=True)
        # Re-render current mode stock if needed
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
        print("QUANTTRACE_SLICE2AX_LIVE_GRAPH stock_hsv_vs_tex compare rc", rcode)

    if args.compare:
        blender = bpy.app.binary_path or "blender"
        rcode = subprocess.call([
            blender, "--background", "--python",
            os.path.join(root, "tools", "_quanttrace_exr_delta.py"), "--",
            args.compare, args.out,
        ])
        print("QUANTTRACE_SLICE2AX_SMOKE compare rc", rcode)
        if args.pair_png and rcode == 0:
            pair = args.pair_png
            copies = [pair]
            proof = os.path.join(root, "docs", "proof", "quanttrace-base-hsv-32-pair.png")
            ws = "/workspace/quanttrace-base-hsv-32-pair.png"
            for extra in (proof, ws):
                if extra not in copies:
                    copies.append(extra)
            try:
                _compose_pair_png(args.compare, args.out, copies)
            except Exception as e:
                print("QUANTTRACE_SLICE2AX_PAIR FAIL", type(e).__name__, e)
                raise
        if rcode != 0:
            raise SystemExit(rcode)

    print("QUANTTRACE_SLICE2AX_SMOKE OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main() or 0)
    except Exception as e:
        print("QUANTTRACE_SLICE2AX_SMOKE FAIL", type(e).__name__, e)
        raise
