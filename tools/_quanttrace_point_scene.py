# QuantTrace Slice 2e: locked camera/cube + one POINT light (hard or soft).
from __future__ import annotations
import argparse, os, sys
import bpy

def _argv():
    a = sys.argv
    return a[a.index("--")+1:] if "--" in a else []

def build_point_scene(soft_size: float = 0.0, soft_falloff: bool = True):
    """POINT at locked AreaKey location. soft_size maps to shadow_soft_size.

    Blender Cycles sync: is_sphere = !use_soft_falloff. Default soft_falloff
    True → disk soft point (matches new Blender POINT defaults).
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_cube_scene as cube
    scene, cube_obj, lamp, cam = cube.build_locked_scene()
    loc = tuple(lamp.location)
    energy = float(lamp.data.energy)
    color = tuple(lamp.data.color)
    bpy.data.objects.remove(lamp, do_unlink=True)
    bpy.ops.object.light_add(type="POINT", location=loc)
    point = bpy.context.active_object
    point.name = "PointKey"
    point.data.energy = energy
    point.data.color = color
    if hasattr(point.data, "shadow_soft_size"):
        point.data.shadow_soft_size = float(soft_size)
    if hasattr(point.data, "use_soft_falloff"):
        point.data.use_soft_falloff = bool(soft_falloff)
    if hasattr(point.data, "normalize"):
        point.data.normalize = True
    bpy.context.view_layer.update()
    return scene, cube_obj, point, cam

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_point_stock.exr")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--soft-size", type=float, default=0.0,
                   help="shadow_soft_size metres (0=hard POINT)")
    p.add_argument("--no-soft-falloff", action="store_true", default=False,
                   help="use_soft_falloff=False → sphere (is_sphere=1)")
    args = p.parse_args(_argv())
    soft_fo = not args.no_soft_falloff
    scene, cube_obj, point, cam = build_point_scene(
        soft_size=args.soft_size, soft_falloff=soft_fo)
    print("QUANTTRACE_POINT", point.name, point.data.type, point.data.energy,
          "soft", getattr(point.data, "shadow_soft_size", None),
          "soft_falloff", getattr(point.data, "use_soft_falloff", None),
          "normalize", getattr(point.data, "normalize", None))
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_POINT wrote", args.out)
    return 0

if __name__ == "__main__":
    raise SystemExit(main() or 0)
