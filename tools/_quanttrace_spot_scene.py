# QuantTrace Slice 2g: locked camera/cube + one SPOT aimed -Z at origin.
from __future__ import annotations
import argparse, math, os, sys
import bpy
from mathutils import Vector

def _argv():
    a = sys.argv
    return a[a.index("--")+1:] if "--" in a else []

def build_spot_scene(
    energy: float = 1000.0,
    spot_size: float = math.pi / 4.0,
    spot_blend: float = 0.15,
    soft_size: float = 0.0,
    soft_falloff: bool = True,
):
    """SPOT at locked AreaKey location, emit -Z toward origin.

    Blender Cycles sync: spot_size→angle, spot_blend→smooth,
    shadow_soft_size→radius, is_sphere=!use_soft_falloff.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_cube_scene as cube
    scene, cube_obj, lamp, cam = cube.build_locked_scene()
    loc = tuple(lamp.location)
    bpy.data.objects.remove(lamp, do_unlink=True)
    bpy.ops.object.light_add(type="SPOT", location=loc)
    spot = bpy.context.active_object
    spot.name = "SpotKey"
    spot.data.energy = float(energy)
    spot.data.color = (1.0, 1.0, 1.0)
    spot.data.spot_size = float(spot_size)
    spot.data.spot_blend = float(spot_blend)
    if hasattr(spot.data, "shadow_soft_size"):
        spot.data.shadow_soft_size = float(soft_size)
    if hasattr(spot.data, "use_soft_falloff"):
        spot.data.use_soft_falloff = bool(soft_falloff)
    if hasattr(spot.data, "normalize"):
        spot.data.normalize = True
    # Aim emit -Z at world origin (same convention as AREA/SUN).
    spot.rotation_euler = (
        Vector((0, 0, 0)) - Vector(spot.location)
    ).to_track_quat("-Z", "Y").to_euler()
    bpy.context.view_layer.update()
    return scene, cube_obj, spot, cam

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_spot_stock.exr")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--energy", type=float, default=1000.0)
    p.add_argument("--spot-size", type=float, default=math.pi / 4.0)
    p.add_argument("--spot-blend", type=float, default=0.15)
    p.add_argument("--soft-size", type=float, default=0.0)
    p.add_argument("--no-soft-falloff", action="store_true", default=False)
    args = p.parse_args(_argv())
    soft_fo = not args.no_soft_falloff
    scene, cube_obj, spot, cam = build_spot_scene(
        energy=args.energy,
        spot_size=args.spot_size,
        spot_blend=args.spot_blend,
        soft_size=args.soft_size,
        soft_falloff=soft_fo,
    )
    print(
        "QUANTTRACE_SPOT", spot.name, spot.data.type, spot.data.energy,
        "spot_size", spot.data.spot_size,
        "spot_blend", spot.data.spot_blend,
        "soft", getattr(spot.data, "shadow_soft_size", None),
        "soft_falloff", getattr(spot.data, "use_soft_falloff", None),
        "normalize", getattr(spot.data, "normalize", None),
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SPOT wrote", args.out)
    return 0

if __name__ == "__main__":
    raise SystemExit(main() or 0)
