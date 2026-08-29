# pack_scene Mapping L/R/S linked Combine XYZ → Session vs stock Cycles (Slice 2ag).
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
    p.add_argument("--out", default="/tmp/quanttrace_slice2ag_session.exr")
    p.add_argument("--stock-out", default="/tmp/quanttrace_slice2ag_stock.exr")
    p.add_argument("--compare", default="")
    p.add_argument("--render-stock", action="store_true", default=False)
    p.add_argument("--image", default="/tmp/qt_slice2ag_checker.png")
    p.add_argument(
        "--mode",
        choices=("combxyz", "combxyz_value", "value_rot", "unlinked"),
        default="combxyz",
    )
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
    import _quanttrace_slice2ag_scene as sc2ag
    qt_engine._reset_native_probe_for_tests()
    assert qt_engine.kernel_ready()

    scene, cube_obj, lamp, cam, img = sc2ag.build_slice2ag_scene(
        image_path=args.image,
        mode=args.mode,
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
            "QUANTTRACE_SLICE2AG_STOCK wall", round(time.perf_counter() - t_s, 3),
            "out", args.stock_out,
        )
        if not args.compare:
            args.compare = args.stock_out

    deps = bpy.context.evaluated_depsgraph_get()
    packed = qt_sync.pack_scene(scene, depsgraph=deps)
    m0 = packed["meshes"][0]
    print(
        "QUANTTRACE_SLICE2AG_SMOKE packed",
        "mode", args.mode,
        "tex_vector_mode", m0.get("tex_vector_mode"),
        "map_loc", m0.get("map_location"),
        "map_rot", m0.get("map_rotation"),
        "map_scl", m0.get("map_scale"),
        "map_type", m0.get("map_type"),
        "image", m0.get("image_path"),
    )
    expected_mode = 2  # QT_TEX_VECTOR_MAPPING (UV)
    if int(m0.get("tex_vector_mode") or 0) != expected_mode:
        raise RuntimeError(
            f"expected tex_vector_mode={expected_mode} got {m0.get('tex_vector_mode')}"
        )
    # Sanity: packed constants match scene intent (Location packed even if SVM ignores).
    loc = tuple(float(x) for x in m0.get("map_location"))
    rot = tuple(float(x) for x in m0.get("map_rotation"))
    scl = tuple(float(x) for x in m0.get("map_scale"))
    if args.mode in ("combxyz", "combxyz_value", "unlinked"):
        exp_loc = tuple(float(x) for x in args.location)
        exp_rot = (0.0, 0.0, float(args.rotation_z))
        exp_scl = tuple(float(x) for x in args.scale)
        if args.mode != "value_rot":
            if any(abs(a - b) > 1e-6 for a, b in zip(loc, exp_loc)):
                raise RuntimeError(f"map_location packed {loc} != {exp_loc}")
            if any(abs(a - b) > 1e-6 for a, b in zip(rot, exp_rot)):
                raise RuntimeError(f"map_rotation packed {rot} != {exp_rot}")
            if any(abs(a - b) > 1e-6 for a, b in zip(scl, exp_scl)):
                raise RuntimeError(f"map_scale packed {scl} != {exp_scl}")
    elif args.mode == "value_rot":
        v = float(args.rotation_z)
        if any(abs(a - b) > 1e-6 for a, b in zip(rot, (v, v, v))):
            raise RuntimeError(f"value_rot map_rotation packed {rot} != {(v, v, v)}")

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
    print("QUANTTRACE_SLICE2AG_CTYPES ver", ver, "is_tracer", is_tr)
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
        "QUANTTRACE_SLICE2AG_SMOKE rc", rc, "wall", round(time.perf_counter() - t0, 3),
        "ver", ver, "is_tracer", is_tr,
        "rgb_min", rgb_min, "rgb_max", rgb_max, "constant", constant,
    )
    if rc != 0:
        raise RuntimeError(rc)
    if rgb_max == 0.0:
        raise RuntimeError("session Combined all-zero")
    if constant:
        raise RuntimeError("session Combined constant — mapping likely dead")
    if args.compare:
        blender = bpy.app.binary_path or "blender"
        rcode = subprocess.call([
            blender, "--background", "--python",
            os.path.join(root, "tools", "_quanttrace_exr_delta.py"), "--",
            args.compare, args.out,
        ])
        print("QUANTTRACE_SLICE2AG_SMOKE compare rc", rcode)
        if rcode != 0:
            raise SystemExit(rcode)
    print("QUANTTRACE_SLICE2AG_SMOKE OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main() or 0)
    except Exception as e:
        print("QUANTTRACE_SLICE2AG_SMOKE FAIL", type(e).__name__, e)
        raise
