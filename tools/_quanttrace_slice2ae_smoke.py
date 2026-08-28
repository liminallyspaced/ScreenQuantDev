# pack_scene Env Object-with-pointer → Session vs stock Cycles (Slice 2ae).
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
    p.add_argument("--out", default="/tmp/quanttrace_slice2ae_session.exr")
    p.add_argument("--stock-out", default="/tmp/quanttrace_slice2ae_stock.exr")
    p.add_argument("--compare", default="")
    p.add_argument("--render-stock", action="store_true", default=False)
    p.add_argument("--image", default="/tmp/qt_slice2ae_env.exr")
    p.add_argument(
        "--mode",
        choices=("pointer", "pointer_mapping", "empty_ref", "generated", "unlinked"),
        default="pointer",
    )
    p.add_argument(
        "--projection",
        choices=("EQUIRECTANGULAR", "MIRROR_BALL"),
        default="EQUIRECTANGULAR",
    )
    p.add_argument("--strength", type=float, default=1.0)
    p.add_argument("--scale", type=float, nargs=3, default=(1.0, 1.0, 1.0))
    p.add_argument("--location", type=float, nargs=3, default=(0.0, 0.0, 0.0))
    p.add_argument("--rotation-z", type=float, default=0.7)
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
    import _quanttrace_slice2ae_scene as sc2ae
    qt_engine._reset_native_probe_for_tests()
    assert qt_engine.kernel_ready()
    scene, cube_obj, lamp, cam, img, empty = sc2ae.build_slice2ae_scene(
        image_path=args.image,
        mode=args.mode,
        projection=args.projection,
        strength=args.strength,
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
            "QUANTTRACE_SLICE2AE_STOCK wall", round(time.perf_counter() - t_s, 3),
            "out", args.stock_out,
        )
        if not args.compare:
            args.compare = args.stock_out

    deps = bpy.context.evaluated_depsgraph_get()
    packed = qt_sync.pack_scene(scene, depsgraph=deps)
    expect_mode = {
        "unlinked": 0,
        "generated": 3,
        "pointer": 5,
        "empty_ref": 5,
        "pointer_mapping": 6,
    }[args.mode]
    use_tf = int(packed.get("world_ob_use_transform", 0) or 0)
    tfm = list(packed.get("world_ob_tfm") or [])
    print(
        "QUANTTRACE_SLICE2AE_SMOKE packed",
        "mode", args.mode,
        "world_image_path", packed.get("world_image_path"),
        "world_tex_vector_mode", packed.get("world_tex_vector_mode"),
        "world_ob_use_transform", use_tf,
        "world_ob_tfm", [round(float(v), 6) for v in tfm],
        "identity_tfm", _tfm_is_identity(tfm),
        "world_map_rotation", packed.get("world_map_rotation"),
        "nmeshes", len(packed["meshes"]),
    )
    if not packed.get("world_image_path"):
        raise RuntimeError("packed world_image_path empty — env not packed")
    if int(packed.get("world_tex_vector_mode", -1)) != expect_mode:
        raise RuntimeError(
            f"packed world_tex_vector_mode={packed.get('world_tex_vector_mode')} "
            f"expected {expect_mode}"
        )
    if args.mode in ("empty_ref", "generated", "unlinked"):
        if use_tf != 0:
            raise RuntimeError(f"{args.mode} packed use_transform={use_tf} expected 0")
    else:
        if use_tf != 1:
            raise RuntimeError(f"pointer packed use_transform={use_tf} expected 1")
        if _tfm_is_identity(tfm):
            raise RuntimeError(
                "pointer packed world_ob_tfm is identity — Empty must be transformed"
            )
        if empty is not None and empty.type == "MESH":
            raise RuntimeError("Empty was exported as a mesh")
        # Empty must not appear as a mesh in packed scene
        for m in packed["meshes"]:
            if "Empty" in (m.get("name") or ""):
                raise RuntimeError(f"Empty classified as mesh: {m.get('name')}")
    if args.mode == "pointer_mapping":
        rot = packed.get("world_map_rotation") or (0, 0, 0)
        if abs(float(rot[2]) - float(args.rotation_z)) > 1e-5:
            raise RuntimeError(f"packed map_rotation z={rot} expected {args.rotation_z}")

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
        "QUANTTRACE_SLICE2AE_CTYPES use_transform", desc.world_ob_use_transform,
        "mode", desc.world_tex_vector_mode,
        "tfm", [round(desc.world_ob_tfm[i], 6) for i in range(12)],
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
        "QUANTTRACE_SLICE2AE_SMOKE rc", rc, "wall", round(time.perf_counter() - t0, 3),
        "ver", ver, "is_tracer", is_tr,
        "rgb_min", rgb_min, "rgb_max", rgb_max, "constant", constant,
    )
    if rc != 0:
        raise RuntimeError(rc)
    if rgb_max == 0.0:
        raise RuntimeError("session Combined all-zero — env Object graph likely missing")
    if constant:
        raise RuntimeError("session Combined constant — env Object/pointer likely dead")
    if args.compare:
        if os.path.isfile(args.compare):
            try:
                import OpenImageIO as oiio
                import numpy as np
                inp = oiio.ImageInput.open(args.compare)
                spec = inp.spec()
                pix = np.asarray(inp.read_image(oiio.FLOAT), dtype=np.float32).reshape(
                    spec.height, spec.width, spec.nchannels
                )
                inp.close()
                rgb = pix[:, :, :3]
                smin, smax = float(rgb.min()), float(rgb.max())
                print(
                    "QUANTTRACE_SLICE2AE_STOCK_VIS min", smin, "max", smax,
                    "constant", smax - smin < 1e-12,
                )
                if smax == 0.0:
                    raise RuntimeError("stock Combined all-zero — env not visible")
                if smax - smin < 1e-12:
                    raise RuntimeError("stock Combined constant — env not visible")
            except ImportError:
                print("QUANTTRACE_SLICE2AE_STOCK_VIS skip (no OIIO in this process)")
        blender = bpy.app.binary_path or "blender"
        rcode = subprocess.call([
            blender, "--background", "--python",
            os.path.join(root, "tools", "_quanttrace_exr_delta.py"), "--",
            args.compare, args.out,
        ])
        print("QUANTTRACE_SLICE2AE_SMOKE compare rc", rcode)
        if rcode != 0:
            raise SystemExit(rcode)
    print("QUANTTRACE_SLICE2AE_SMOKE OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main() or 0)
    except Exception as e:
        print("QUANTTRACE_SLICE2AE_SMOKE FAIL", type(e).__name__, e)
        raise
