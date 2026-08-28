# pack_scene TEX_COORD Generated cube → Session vs stock Cycles (Slice 2k).
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
    p.add_argument("--out", default="/tmp/quanttrace_gen_session.exr")
    p.add_argument("--compare", default="")
    p.add_argument("--image", default="/tmp/qt_checker_gen.png")
    p.add_argument("--mode", choices=("texcoord", "mapping"), default="texcoord")
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
    import _quanttrace_generated_scene as gsc
    qt_engine._reset_native_probe_for_tests()
    assert qt_engine.kernel_ready()
    scene, cube_obj, lamp, cam, img = gsc.build_generated_scene(
        image_path=args.image,
        use_mapping=(args.mode == "mapping"),
        scale=tuple(args.scale),
        location=tuple(args.location),
        rotation_z=args.rotation_z,
    )
    scene.render.resolution_x = scene.render.resolution_y = args.res
    scene.cycles.samples = args.samples
    deps = bpy.context.evaluated_depsgraph_get()
    packed = qt_sync.pack_scene(scene, depsgraph=deps)
    m0 = packed["meshes"][0]
    print(
        "QUANTTRACE_GEN_SMOKE image", m0.get("image_path"),
        "mode", args.mode,
        "tex_vector_mode", m0.get("tex_vector_mode"),
        "map_loc", m0.get("map_location"),
        "map_rot", m0.get("map_rotation"),
        "map_scl", m0.get("map_scale"),
        "map_type", m0.get("map_type"),
        "nuv", len(m0.get("uvs") or []),
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
    n = args.res * args.res * 4
    buf = (ctypes.c_float * n)()
    ow = ctypes.c_int(0)
    oh = ctypes.c_int(0)
    if os.path.isfile(args.out):
        os.unlink(args.out)
    t0 = time.perf_counter()
    rc = lib.quanttrace_render_qt_scene_rgba(
        ctypes.byref(desc), buf, n, ctypes.byref(ow), ctypes.byref(oh))
    print(
        "QUANTTRACE_GEN_SMOKE rc", rc, "wall", round(time.perf_counter() - t0, 3),
        "ver", ver,
    )
    if rc != 0:
        raise RuntimeError(rc)
    if args.compare:
        r = subprocess.call([
            "blender", "--background", "--python",
            os.path.join(root, "tools", "_quanttrace_exr_delta.py"), "--",
            args.compare, args.out,
        ])
        print("QUANTTRACE_GEN_SMOKE compare rc", r)
        if r != 0:
            raise SystemExit(r)
    print("QUANTTRACE_GEN_SMOKE OK")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main() or 0)
    except Exception as e:
        print("QUANTTRACE_GEN_SMOKE FAIL", type(e).__name__, e)
        raise
