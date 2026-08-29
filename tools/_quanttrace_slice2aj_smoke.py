# pack_scene Mix → world Strength → Session vs stock Cycles (Slice 2aj).
from __future__ import annotations
import argparse, ctypes, os, sys, time, subprocess
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def _expected_strength(mode, strength, mix_fac, mix_a, mix_b, mul_a, mul_b) -> float:
    if mode in ("mix_float", "mix_unlinked", "mix_rgb"):
        return float(mix_a) * (1.0 - float(mix_fac)) + float(mix_b) * float(mix_fac)
    if mode == "math_mul":
        return float(mul_a) * float(mul_b)
    return float(strength)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    p.add_argument("--out", default="/tmp/quanttrace_slice2aj_session.exr")
    p.add_argument("--stock-out", default="/tmp/quanttrace_slice2aj_stock.exr")
    p.add_argument("--compare", default="")
    p.add_argument("--render-stock", action="store_true", default=False)
    p.add_argument("--image", default="/tmp/qt_slice2aj_env.exr")
    p.add_argument(
        "--mode",
        choices=(
            "mix_float", "mix_unlinked", "mix_rgb", "mix_tex",
            "math_mul", "value", "unlinked",
        ),
        default="mix_float",
    )
    p.add_argument(
        "--projection",
        choices=("EQUIRECTANGULAR", "MIRROR_BALL"),
        default="EQUIRECTANGULAR",
    )
    p.add_argument("--strength", type=float, default=0.7)
    p.add_argument("--mix-fac", type=float, default=0.5)
    p.add_argument("--mix-a", type=float, default=0.4)
    p.add_argument("--mix-b", type=float, default=1.0)
    p.add_argument("--mul-a", type=float, default=0.5)
    p.add_argument("--mul-b", type=float, default=1.4)
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
    import _quanttrace_slice2aj_scene as sc2aj
    qt_engine._reset_native_probe_for_tests()
    assert qt_engine.kernel_ready()

    scene, cube_obj, lamp, cam, img = sc2aj.build_slice2aj_scene(
        image_path=args.image,
        mode=args.mode,
        projection=args.projection,
        strength=args.strength,
        mix_fac=args.mix_fac,
        mix_a=args.mix_a,
        mix_b=args.mix_b,
        mul_a=args.mul_a,
        mul_b=args.mul_b,
    )
    scene.render.resolution_x = scene.render.resolution_y = args.res
    scene.cycles.samples = args.samples

    if args.mode == "mix_tex":
        try:
            packed = qt_sync.pack_scene(
                scene, depsgraph=bpy.context.evaluated_depsgraph_get()
            )
        except qt_sync.QuantTraceSyncError as e:
            msg = str(e)
            print("QUANTTRACE_SLICE2AJ_REFUSE", type(e).__name__, msg)
            if "TEX_IMAGE" not in msg and "tex" not in msg.lower() and "refused" not in msg.lower():
                raise RuntimeError(f"mix_tex refused but message unexpected: {msg}")
            print("QUANTTRACE_SLICE2AJ_SMOKE OK refuse")
            return 0
        raise RuntimeError(
            f"mix_tex packed unexpectedly world_strength={packed.get('world_strength')}"
        )

    expected = _expected_strength(
        args.mode, args.strength, args.mix_fac, args.mix_a, args.mix_b,
        args.mul_a, args.mul_b,
    )

    if args.render_stock:
        if os.path.isfile(args.stock_out):
            os.unlink(args.stock_out)
        scene.render.filepath = args.stock_out
        t_s = time.perf_counter()
        bpy.ops.render.render(write_still=True)
        print(
            "QUANTTRACE_SLICE2AJ_STOCK wall", round(time.perf_counter() - t_s, 3),
            "out", args.stock_out,
        )
        if not args.compare:
            args.compare = args.stock_out

    deps = bpy.context.evaluated_depsgraph_get()
    packed = qt_sync.pack_scene(scene, depsgraph=deps)
    print(
        "QUANTTRACE_SLICE2AJ_SMOKE packed",
        "mode", args.mode,
        "world_image_path", packed.get("world_image_path"),
        "world_projection", packed.get("world_projection"),
        "world_strength", packed.get("world_strength"),
        "world_cs", packed.get("world_image_colorspace"),
        "expected_strength", expected,
    )
    if not packed.get("world_image_path"):
        raise RuntimeError("packed world_image_path empty — env not packed")
    got = float(packed.get("world_strength", 0.0))
    if abs(got - expected) > 1e-6:
        raise RuntimeError(
            f"packed world_strength={got} expected {expected} (mode={args.mode})"
        )

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
        "QUANTTRACE_SLICE2AJ_CTYPES path", desc.world_image_path,
        "proj", desc.world_projection, "strength", desc.world_strength,
        "ver", ver, "is_tracer", is_tr,
    )
    if abs(float(desc.world_strength) - expected) > 1e-6:
        raise RuntimeError(
            f"ctypes world_strength={desc.world_strength} expected {expected}"
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
        "QUANTTRACE_SLICE2AJ_SMOKE rc", rc, "wall", round(time.perf_counter() - t0, 3),
        "ver", ver, "is_tracer", is_tr,
        "rgb_min", rgb_min, "rgb_max", rgb_max, "constant", constant,
    )
    if rc != 0:
        raise RuntimeError(rc)
    if rgb_max == 0.0:
        raise RuntimeError("session Combined all-zero — env graph likely missing")
    if constant:
        raise RuntimeError("session Combined constant — env likely dead")
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
                    "QUANTTRACE_SLICE2AJ_STOCK_VIS min", smin, "max", smax,
                    "constant", smax - smin < 1e-12,
                )
                if smax == 0.0:
                    raise RuntimeError("stock Combined all-zero — env not visible")
                if smax - smin < 1e-12:
                    raise RuntimeError("stock Combined constant — env not visible")
            except ImportError:
                print("QUANTTRACE_SLICE2AJ_STOCK_VIS skip (no OIIO in this process)")
        blender = bpy.app.binary_path or "blender"
        rcode = subprocess.call([
            blender, "--background", "--python",
            os.path.join(root, "tools", "_quanttrace_exr_delta.py"), "--",
            args.compare, args.out,
        ])
        print("QUANTTRACE_SLICE2AJ_SMOKE compare rc", rcode)
        if rcode != 0:
            raise SystemExit(rcode)
    print("QUANTTRACE_SLICE2AJ_SMOKE OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main() or 0)
    except Exception as e:
        print("QUANTTRACE_SLICE2AJ_SMOKE FAIL", type(e).__name__, e)
        raise
