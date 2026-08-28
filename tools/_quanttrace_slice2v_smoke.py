# pack_scene Subsurface IOR / Anisotropy / Diffuse Roughness TEX_IMAGE cube → Session vs stock (Slice 2v).
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
    p.add_argument("--out", default="/tmp/quanttrace_slice2v_session.exr")
    p.add_argument("--compare", default="")
    p.add_argument("--image", default="/tmp/qt_slice2v_gray.png")
    p.add_argument("--tint-image", default="/tmp/qt_slice2v_tint.png")
    p.add_argument(
        "--socket",
        choices=("SSSIOR", "SSSAniso", "DiffuseRough", "Combo", "CoatWeight", "SpecTint"),
        default="SSSIOR",
    )
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
    import _quanttrace_slice2v_scene as sc2v
    qt_engine._reset_native_probe_for_tests()
    assert qt_engine.kernel_ready()
    scene, cube_obj, lamp, cam, gray, tint = sc2v.build_slice2v_scene(
        image_path=args.image, socket=args.socket, tint_image_path=args.tint_image,
    )
    scene.render.resolution_x = scene.render.resolution_y = args.res
    scene.cycles.samples = args.samples
    deps = bpy.context.evaluated_depsgraph_get()
    packed = qt_sync.pack_scene(scene, depsgraph=deps)
    m0 = packed["meshes"][0]
    print(
        "QUANTTRACE_SLICE2V_SMOKE socket", args.socket,
        "sss_ior", m0.get("sss_ior_image_path"),
        "sss_aniso", m0.get("sss_aniso_image_path"),
        "diffuse_rough", m0.get("diffuse_rough_image_path"),
        "thin_wall", m0.get("thin_wall_image_path"),
        "coat", m0.get("coat_image_path"),
        "spec_tint", m0.get("spec_tint_image_path"),
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
        "QUANTTRACE_SLICE2V_SMOKE rc", rc, "wall", round(time.perf_counter() - t0, 3),
        "ver", ver,
    )
    if rc != 0:
        raise RuntimeError(rc)
    if args.compare:
        blender = bpy.app.binary_path or "blender"
        r = subprocess.call([
            blender, "--background", "--python",
            os.path.join(root, "tools", "_quanttrace_exr_delta.py"), "--",
            args.compare, args.out,
        ])
        print("QUANTTRACE_SLICE2V_SMOKE compare rc", r)
        if r != 0:
            raise SystemExit(r)
    print("QUANTTRACE_SLICE2V_SMOKE OK")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main() or 0)
    except Exception as e:
        print("QUANTTRACE_SLICE2V_SMOKE FAIL", type(e).__name__, e)
        raise
