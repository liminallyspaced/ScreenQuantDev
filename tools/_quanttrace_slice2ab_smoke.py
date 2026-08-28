# pack_scene TEX_COORD Object-with-pointer cube → Session vs stock Cycles (Slice 2ab).
from __future__ import annotations
import argparse, ctypes, os, sys, time, subprocess
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def _tfm_is_identity(tfm, eps=1e-6):
    ident = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0]
    if tfm is None or len(tfm) != 12:
        return False
    return all(abs(float(a) - float(b)) < eps for a, b in zip(tfm, ident))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    p.add_argument("--out", default="/tmp/quanttrace_slice2ab_session.exr")
    p.add_argument("--stock-out", default="/tmp/quanttrace_slice2ab_stock.exr")
    p.add_argument("--compare", default="")
    p.add_argument("--render-stock", action="store_true", default=False)
    p.add_argument("--image", default="/tmp/qt_checker_slice2ab.png")
    p.add_argument("--mode", choices=("texcoord", "mapping"), default="texcoord")
    p.add_argument("--empty-ref", action="store_true", default=False)
    p.add_argument("--scale", type=float, nargs=3, default=(2.0, 2.0, 2.0))
    p.add_argument("--location", type=float, nargs=3, default=(0.1, 0.2, 0.0))
    p.add_argument("--rotation-z", type=float, default=0.15)
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
    import _quanttrace_slice2ab_scene as sc2ab
    qt_engine._reset_native_probe_for_tests()
    assert qt_engine.kernel_ready()
    scene, cube_obj, lamp, cam, img, empty = sc2ab.build_slice2ab_scene(
        image_path=args.image,
        use_mapping=(args.mode == "mapping"),
        empty_ref=args.empty_ref,
        scale=tuple(args.scale),
        location=tuple(args.location),
        rotation_z=args.rotation_z,
    )
    scene.render.resolution_x = scene.render.resolution_y = args.res
    scene.cycles.samples = args.samples

    if args.render_stock:
        if os.path.isfile(args.stock_out):
            os.unlink(args.stock_out)
        scene.render.filepath = args.stock_out
        t_s = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        print(
            "QUANTTRACE_SLICE2AB_STOCK wall", round(time.perf_counter() - t_s, 3),
            "out", args.stock_out,
        )
        if not args.compare:
            args.compare = args.stock_out

    deps = bpy.context.evaluated_depsgraph_get()
    packed = qt_sync.pack_scene(scene, depsgraph=deps)
    m0 = packed["meshes"][0]
    use_tf = int(m0.get("tex_ob_use_transform", 0) or 0)
    tfm = list(m0.get("tex_ob_tfm") or [])
    print(
        "QUANTTRACE_SLICE2AB_SMOKE packed",
        "mode", args.mode,
        "empty_ref", args.empty_ref,
        "tex_vector_mode", m0.get("tex_vector_mode"),
        "tex_ob_use_transform", use_tf,
        "tex_ob_tfm", [round(float(v), 6) for v in tfm],
        "identity_tfm", _tfm_is_identity(tfm),
        "image", m0.get("image_path"),
        "nmeshes", len(packed["meshes"]),
    )
    if args.empty_ref:
        if use_tf != 0:
            raise RuntimeError(f"empty-ref packed use_transform={use_tf} expected 0")
    else:
        if use_tf != 1:
            raise RuntimeError(f"pointer packed use_transform={use_tf} expected 1")
        if _tfm_is_identity(tfm):
            raise RuntimeError("pointer packed tex_ob_tfm is identity — Empty must be transformed")
        if empty is not None and empty.type == "MESH":
            raise RuntimeError("Empty was exported as a mesh")

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
        "QUANTTRACE_SLICE2AB_CTYPES use_transform", desc.meshes[0].tex_ob_use_transform,
        "tfm", [round(desc.meshes[0].tex_ob_tfm[i], 6) for i in range(12)],
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
    r = [buf[i] for i in range(0, n, 4)]
    g = [buf[i + 1] for i in range(0, n, 4)]
    bch = [buf[i + 2] for i in range(0, n, 4)]
    rgb_min = min(min(r), min(g), min(bch))
    rgb_max = max(max(r), max(g), max(bch))
    constant = (rgb_max - rgb_min) < 1e-12
    print(
        "QUANTTRACE_SLICE2AB_SMOKE rc", rc, "wall", round(time.perf_counter() - t0, 3),
        "ver", ver, "is_tracer", is_tr,
        "rgb_min", rgb_min, "rgb_max", rgb_max, "constant", constant,
    )
    if rc != 0:
        raise RuntimeError(rc)
    if rgb_max == 0.0:
        raise RuntimeError("session Combined all-zero — Object graph likely missing")
    if constant:
        raise RuntimeError("session Combined constant — Object/pointer likely dead")
    if args.compare:
        blender = bpy.app.binary_path or "blender"
        rcode = subprocess.call([
            blender, "--background", "--python",
            os.path.join(root, "tools", "_quanttrace_exr_delta.py"), "--",
            args.compare, args.out,
        ])
        print("QUANTTRACE_SLICE2AB_SMOKE compare rc", rcode)
        if rcode != 0:
            raise SystemExit(rcode)
    print("QUANTTRACE_SLICE2AB_SMOKE OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main() or 0)
    except Exception as e:
        print("QUANTTRACE_SLICE2AB_SMOKE FAIL", type(e).__name__, e)
        raise
