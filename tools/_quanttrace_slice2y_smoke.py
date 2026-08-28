# pack_scene Thin Wall BOOLEAN cube → Session vs stock Cycles (Slice 2y).
from __future__ import annotations
import argparse, ctypes, os, sys, time, subprocess
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    p.add_argument("--out", default="/tmp/quanttrace_slice2y_session.exr")
    p.add_argument("--compare", default="")
    p.add_argument("--image", default="/tmp/qt_slice2x_height.png")
    p.add_argument(
        "--socket",
        choices=("ThinWall", "Bump"),
        default="ThinWall",
    )
    p.add_argument(
        "--thin-wall",
        dest="thin_wall",
        choices=("0", "1", "false", "true", "False", "True"),
        default="1",
    )
    p.add_argument("--transmission", type=float, default=1.0)
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
    import _quanttrace_slice2y_scene as sc2y
    qt_engine._reset_native_probe_for_tests()
    assert qt_engine.kernel_ready()
    tw = str(args.thin_wall).lower() in ("1", "true")
    scene, cube_obj, lamp, cam, img = sc2y.build_slice2y_scene(
        socket=args.socket,
        thin_wall=tw,
        transmission_weight=args.transmission,
        image_path=args.image,
    )
    scene.render.resolution_x = scene.render.resolution_y = args.res
    scene.cycles.samples = args.samples
    deps = bpy.context.evaluated_depsgraph_get()
    packed = qt_sync.pack_scene(scene, depsgraph=deps)
    m0 = packed["meshes"][0]
    print(
        "QUANTTRACE_SLICE2Y_SMOKE socket", args.socket,
        "thin_wall", m0.get("thin_wall"),
        "transmission_weight", m0.get("transmission_weight"),
        "trans_img", m0.get("trans_image_path"),
        "thin_wall_img", m0.get("thin_wall_image_path"),
        "bump", m0.get("bump_image_path"),
        "metal", m0.get("metallic"),
        "rough", m0.get("roughness"),
        "ior", m0.get("ior"),
    )
    QT_Mesh, QT_Light, QT_Scene = qt_sync.make_qt_scene_types()
    lib = qt_engine._native_lib
    ver = lib.quanttrace_version()
    if isinstance(ver, bytes):
        ver = ver.decode()
    lib.quanttrace_render_qt_scene_rgba.argtypes = [
        ctypes.POINTER(QT_Scene), ctypes.POINTER(ctypes.c_float), ctypes.c_int,
        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
    lib.quanttrace_render_qt_scene_rgba.restype = ctypes.c_int
    desc = qt_sync.to_ctypes_scene(packed, QT_Mesh, QT_Light, QT_Scene, exr_path=args.out)
    print(
        "QUANTTRACE_SLICE2Y_CTYPES thin_wall", desc.meshes[0].thin_wall,
        "transmission_weight", desc.meshes[0].transmission_weight,
        "ver", ver,
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
    print(
        "QUANTTRACE_SLICE2Y_SMOKE rc", rc, "wall", round(time.perf_counter() - t0, 3),
        "ver", ver, "rgb_min", rgb_min, "rgb_max", rgb_max,
        "constant", rgb_min == rgb_max,
    )
    if rc != 0:
        raise RuntimeError(rc)
    if rgb_max == 0.0:
        raise RuntimeError("session Combined all-zero — thin-wall graph likely missing")
    if args.compare:
        blender = bpy.app.binary_path or "blender"
        rcode = subprocess.call([
            blender, "--background", "--python",
            os.path.join(root, "tools", "_quanttrace_exr_delta.py"), "--",
            args.compare, args.out,
        ])
        print("QUANTTRACE_SLICE2Y_SMOKE compare rc", rcode)
        if rcode != 0:
            raise SystemExit(rcode)
    print("QUANTTRACE_SLICE2Y_SMOKE OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main() or 0)
    except Exception as e:
        print("QUANTTRACE_SLICE2Y_SMOKE FAIL", type(e).__name__, e)
        raise
