# QuantTrace Slice 2d: locked camera/cube + one POINT light (vs AREA).
from __future__ import annotations
import argparse, os, sys
import bpy
from mathutils import Vector

def _argv():
    a = sys.argv
    return a[a.index("--")+1:] if "--" in a else []

def build_point_scene():
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_cube_scene as cube
    scene, cube_obj, lamp, cam = cube.build_locked_scene()
    # Convert Area → Point at same location; look-at unused for point.
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
        point.data.shadow_soft_size = 0.0
    bpy.context.view_layer.update()
    return scene, cube_obj, point, cam

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_point_stock.exr")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    args = p.parse_args(_argv())
    scene, cube_obj, point, cam = build_point_scene()
    print("QUANTTRACE_POINT", point.name, point.data.type, point.data.energy,
          "soft", getattr(point.data, "shadow_soft_size", None))
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_POINT wrote", args.out)
    return 0

if __name__ == "__main__":
    raise SystemExit(main() or 0)
