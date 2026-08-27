# QuantTrace Slice 2e: locked camera/cube + one SUN light aimed -Z at origin.
from __future__ import annotations
import argparse, os, sys
import bpy
from mathutils import Vector

def _argv():
    a = sys.argv
    return a[a.index("--")+1:] if "--" in a else []

def build_sun_scene(energy: float = 200.0, angle: float = 0.0091803):
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_cube_scene as cube
    scene, cube_obj, lamp, cam = cube.build_locked_scene()
    loc = tuple(lamp.location)
    bpy.data.objects.remove(lamp, do_unlink=True)
    bpy.ops.object.light_add(type="SUN", location=loc)
    sun = bpy.context.active_object
    sun.name = "SunKey"
    sun.data.energy = float(energy)
    sun.data.angle = float(angle)
    if hasattr(sun.data, "normalize"):
        sun.data.normalize = True
    # Aim emit -Z at world origin (same convention as AREA look-at).
    sun.rotation_euler = (Vector((0, 0, 0)) - Vector(sun.location)).to_track_quat("-Z", "Y").to_euler()
    bpy.context.view_layer.update()
    return scene, cube_obj, sun, cam

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_sun_stock.exr")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--energy", type=float, default=200.0)
    p.add_argument("--angle", type=float, default=0.0091803)
    args = p.parse_args(_argv())
    scene, cube_obj, sun, cam = build_sun_scene(energy=args.energy, angle=args.angle)
    print("QUANTTRACE_SUN", sun.name, sun.data.type, sun.data.energy,
          "angle", sun.data.angle, "normalize", getattr(sun.data, "normalize", None))
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SUN wrote", args.out)
    return 0

if __name__ == "__main__":
    raise SystemExit(main() or 0)
