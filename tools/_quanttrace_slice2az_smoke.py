# pack_scene Bevel → Principled.Normal → Session vs stock (Slice 2az).
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
        pix = __import__("numpy").asarray(inp.read_image(oiio.FLOAT), dtype="float32").reshape(
            spec.height, spec.width, spec.nchannels
        )
        inp.close()
        return pix[:, :, :3]

    a = load(stock_path)
    b = load(session_path)
    diff = __import__("numpy").abs(a.astype("float64") - b.astype("float64"))
    np = __import__("numpy")
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
        print("QUANTTRACE_SLICE2AZ_PAIR", path, "wh", w, h)


def _loft_pack_probe(qt_sync, qt_engine, loft_path):
    if not os.path.isfile(loft_path):
        print("QUANTTRACE_SLICE2AZ_SMOKE loft MISSING", loft_path)
        print("PACK_FAIL loft file missing")
        return 1
    print("QUANTTRACE_SLICE2AZ_SMOKE loft open", loft_path)
    bpy.ops.wm.open_mainfile(filepath=loft_path)
    scene = bpy.context.scene
    try:
        t0 = time.perf_counter()
        packed = qt_sync.pack_scene(
            scene, depsgraph=bpy.context.evaluated_depsgraph_get()
        )
        wall = time.perf_counter() - t0
        # Spot-check bevel on Metal_Sheet-ish
        bevel_n = sum(1 for m in packed["meshes"] if int(m.get("bevel_enable") or 0))
        print(
            "PACK_OK",
            "n_meshes", len(packed["meshes"]),
            "n_lights", len(packed["lights"]),
            "bevel_meshes", bevel_n,
            "wall_s", round(wall, 3),
            "version", qt_engine.native_version(),
        )
        print("QUANTTRACE_SLICE2AZ_SMOKE loft PACK_OK (no Δmax claim)")
        return 0
    except qt_sync.QuantTraceSyncError as e:
        msg = str(e)
        print("PACK_FAIL", msg)
        print("QUANTTRACE_SLICE2AZ_SMOKE loft PACK_FAIL", type(e).__name__, msg)
        return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    p.add_argument("--out", default="/tmp/quanttrace_slice2az_session.exr")
    p.add_argument("--stock-out", default="/tmp/quanttrace_slice2az_stock.exr")
    p.add_argument("--compare", default="")
    p.add_argument("--render-stock", action="store_true", default=False)
    p.add_argument("--image", default="/tmp/qt_slice2az_height.png")
    p.add_argument("--normal", default="/tmp/qt_slice2az_normal.png")
    p.add_argument(
        "--mode",
        choices=("bevel", "bevel_nmap", "bevel_bump", "loft", "bump", "normalmap",
                 "mix", "hsv", "point", "hdr"),
        default="bevel",
    )
    p.add_argument("--radius", type=float, default=0.12)
    p.add_argument("--bevel-samples", type=int, default=4)
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

    # Regression modes reuse prior scene builders
    if args.mode == "mix":
        import _quanttrace_slice2ay_scene as sc
        scene, cube_obj, lamp, cam, img = sc.build_slice2ay_scene(mode="mix")
    elif args.mode == "hsv":
        import _quanttrace_slice2ay_scene as sc
        scene, cube_obj, lamp, cam, img = sc.build_slice2ay_scene(mode="hsv")
    elif args.mode == "point":
        import _quanttrace_slice2av_scene as sc
        scene, cube_obj, lamp, cam, img = sc.build_slice2av_scene(
            image_path="/tmp/qt_slice2av_env.exr", mode="point"
        )
    elif args.mode == "hdr":
        import _quanttrace_slice2aa_scene as sc
        scene, cube_obj, lamp, cam, img = sc.build_slice2aa_scene()
    else:
        import _quanttrace_slice2az_scene as sc2az
        scene, cube_obj, lamp, cam, img = sc2az.build_slice2az_scene(
            image_path=args.image,
            mode=args.mode,
            normal_path=args.normal,
            radius=args.radius,
            samples=args.bevel_samples,
        )

    scene.render.resolution_x = scene.render.resolution_y = args.res
    scene.cycles.samples = args.samples
    scene.render.use_persistent_data = False

    deps = bpy.context.evaluated_depsgraph_get()
    packed = qt_sync.pack_scene(scene, depsgraph=deps)
    m0 = packed["meshes"][0]
    print(
        "QUANTTRACE_SLICE2AZ_PACKED",
        "bevel_enable", m0.get("bevel_enable"),
        "bevel_samples", m0.get("bevel_samples"),
        "bevel_radius", m0.get("bevel_radius"),
        "bump", bool(m0.get("bump_image_path")),
        "nmap", bool(m0.get("normal_image_path")),
        "version", qt_engine.native_version(),
    )
    if args.mode == "bevel":
        assert int(m0.get("bevel_enable") or 0) == 1
        assert int(m0.get("bevel_samples") or 0) == int(args.bevel_samples)
        assert _fclose(m0.get("bevel_radius"), args.radius)
        assert not (m0.get("bump_image_path") or "")
        assert not (m0.get("normal_image_path") or "")
    elif args.mode == "loft":
        assert int(m0.get("bevel_enable") or 0) == 1
        assert m0.get("bump_image_path")
        assert m0.get("normal_image_path")
    elif args.mode == "bevel_bump":
        assert int(m0.get("bevel_enable") or 0) == 1
        assert m0.get("bump_image_path")
    elif args.mode == "bevel_nmap":
        assert int(m0.get("bevel_enable") or 0) == 1
        assert m0.get("normal_image_path")

    if args.live_graph:
        # Render current scene (nonzero radius) then rebuild radius=0 in a fresh scene.
        import _quanttrace_slice2az_scene as sc2az
        scene.render.filepath = args.stock_out
        if os.path.isfile(args.stock_out):
            os.unlink(args.stock_out)
        bpy.ops.render.render(write_still=True)
        scene_z, *_ = sc2az.build_slice2az_scene(
            image_path=args.image, mode="bevel", radius=0.0, samples=args.bevel_samples
        )
        scene_z.render.resolution_x = scene_z.render.resolution_y = args.res
        scene_z.cycles.samples = args.samples
        scene_z.render.filepath = "/tmp/qt_slice2az_live_zero.exr"
        if os.path.isfile(scene_z.render.filepath):
            os.unlink(scene_z.render.filepath)
        bpy.ops.render.render(write_still=True)
        blender = bpy.app.binary_path or "blender"
        rcode = subprocess.call([
            blender, "--background", "--python",
            os.path.join(root, "tools", "_quanttrace_exr_delta.py"), "--",
            args.stock_out, "/tmp/qt_slice2az_live_zero.exr",
        ])
        print("QUANTTRACE_SLICE2AZ_LIVE compare rc", rcode)
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
        "QUANTTRACE_SLICE2AZ_CTYPES",
        "bevel_enable", int(desc.meshes[0].bevel_enable),
        "samples", int(desc.meshes[0].bevel_samples),
        "radius", float(desc.meshes[0].bevel_radius),
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
        "QUANTTRACE_SLICE2AZ_SMOKE rc", rc, "wall", round(wall, 3),
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
        print("QUANTTRACE_SLICE2AZ_STOCK wrote", args.stock_out)
        if not args.compare:
            args.compare = args.stock_out

    cmp_path = args.compare or ""
    if cmp_path and os.path.isfile(cmp_path):
        blender = bpy.app.binary_path or "blender"
        rcode = subprocess.call([
            blender, "--background", "--python",
            os.path.join(root, "tools", "_quanttrace_exr_delta.py"), "--",
            cmp_path, args.out,
        ])
        print("QUANTTRACE_SLICE2AZ_SMOKE compare rc", rcode)
        if args.pair_png:
            paths = [x.strip() for x in args.pair_png.split(",") if x.strip()]
            proof = os.path.join(root, "docs", "proof", "quanttrace-bevel-32-pair.png")
            if proof not in paths:
                paths.append(proof)
            try:
                _compose_pair_png(cmp_path, args.out, paths)
            except Exception as e:
                print("QUANTTRACE_SLICE2AZ_PAIR FAIL", type(e).__name__, e)
    return 0




if __name__ == "__main__":
    raise SystemExit(main() or 0)
