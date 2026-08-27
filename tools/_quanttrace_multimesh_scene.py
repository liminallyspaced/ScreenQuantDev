# QuantTrace still-life (Slice 2c gate): two cubes, two AREA lights.
#
# Builds on the locked-cube camera/world pins, then adds a second
# Principled cube and a second AREA fill. Constant sockets only.
#
#   blender --background --python tools/_quanttrace_multimesh_scene.py -- --dry-run
#   blender --background --python tools/_quanttrace_multimesh_scene.py -- \
#       --render --res 32 --samples 4 --out /tmp/qt_still_stock.exr
#
# CPU only. No user GPU. No Make it Fast.

from __future__ import annotations

import argparse
import os
import sys

import bpy
from mathutils import Vector


def _argv_after_dashdash():
    argv = sys.argv
    if "--" in argv:
        return argv[argv.index("--") + 1 :]
    return []


def parse_args():
    p = argparse.ArgumentParser(description="QuantTrace still-life scene")
    p.add_argument("--dry-run", action="store_true", default=False)
    p.add_argument("--save", metavar="BLEND", default="")
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", metavar="EXR", default="/tmp/quanttrace_still_cycles_combined.exr")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=8)
    return p.parse_args(_argv_after_dashdash())


def _look_at(obj, target=(0.0, 0.0, 0.0), track="-Z", up="Y"):
    direction = Vector(target) - Vector(obj.location)
    if direction.length < 1e-8:
        return
    obj.rotation_euler = direction.to_track_quat(track, up).to_euler()


def _principled_mat(name, base_color, roughness=0.5, metallic=0.0, ior=1.45, alpha=1.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    for node in list(nt.nodes):
        nt.nodes.remove(node)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (300, 0)
    prin = nt.nodes.new("ShaderNodeBsdfPrincipled")
    prin.location = (0, 0)
    prin.inputs["Base Color"].default_value = base_color
    prin.inputs["Roughness"].default_value = roughness
    prin.inputs["Metallic"].default_value = metallic
    if "IOR" in prin.inputs:
        prin.inputs["IOR"].default_value = ior
    if "Alpha" in prin.inputs:
        prin.inputs["Alpha"].default_value = alpha
    nt.links.new(prin.outputs["BSDF"], out.inputs["Surface"])
    return mat


def build_still_life():
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_cube_scene as cube

    scene, cube_obj, lamp, cam = cube.build_locked_scene()

    # Two cubes, both in the locked camera frame, different Principled.
    cube_obj.name = "CubeGrey"
    cube_obj.location = (-1.15, 0.0, 0.0)
    cube_obj.scale = (0.7, 0.7, 0.7)
    if cube_obj.data.materials:
        cube_obj.data.materials[0] = _principled_mat(
            "GreyPrincipled", (0.8, 0.8, 0.8, 1.0)
        )
    else:
        cube_obj.data.materials.append(
            _principled_mat("GreyPrincipled", (0.8, 0.8, 0.8, 1.0))
        )

    bpy.ops.mesh.primitive_cube_add(location=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0))
    cube_red = bpy.context.active_object
    cube_red.name = "CubeRed"
    cube_red.location = (1.15, 0.0, 0.0)
    cube_red.scale = (0.7, 0.7, 0.7)
    cube_red.data.materials.append(
        _principled_mat("RedPrincipled", (0.75, 0.08, 0.08, 1.0), roughness=0.35)
    )

    lamp.name = "AreaKey"
    fill = None
    if os.environ.get("QUANTTRACE_STILL_LIGHTS", "2") != "1":
        bpy.ops.object.light_add(type="AREA", location=(-3.2, 2.8, 4.5))
        fill = bpy.context.active_object
        fill.name = "AreaFill"
        fill.data.energy = 400.0
        fill.data.color = (0.80, 0.90, 1.00)
        if hasattr(fill.data, "shape"):
            fill.data.shape = "SQUARE"
        if hasattr(fill.data, "size"):
            fill.data.size = 0.8
        _look_at(fill, (0.0, 0.0, 0.0), track="-Z", up="Y")

    # Bake loc/scale into mesh DNA so stock Cycles and the Session packer
    # share the same world-space verts (avoids 1-pixel silhouette ULP).
    bpy.ops.object.select_all(action="DESELECT")
    cube_obj.select_set(True)
    cube_red.select_set(True)
    bpy.context.view_layer.objects.active = cube_obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.update()
    return scene, (cube_obj, cube_red), tuple(x for x in (lamp, fill) if x is not None), cam


def describe(scene, cubes, lamps, cam):
    print("QUANTTRACE_STILL dry-run")
    print("  blender", bpy.app.version_string)
    print("  engine", scene.render.engine, "device", scene.cycles.device)
    print("  res", scene.render.resolution_x, "x", scene.render.resolution_y)
    print("  samples", scene.cycles.samples)
    print("  meshes", [c.name for c in cubes],
          "locs", [tuple(round(v, 4) for v in c.location) for c in cubes])
    print("  lights", [(L.name, L.data.type, L.data.energy) for L in lamps])
    print("  camera", cam.name, tuple(round(v, 4) for v in cam.location))
    print("  objects", [o.name for o in scene.objects])


def maybe_render(scene, args):
    scene.render.resolution_x = args.res
    scene.render.resolution_y = args.res
    scene.cycles.samples = args.samples
    scene.render.filepath = args.out
    print("QUANTTRACE_STILL render CPU", args.res, "spp", args.samples, "->", args.out)
    bpy.ops.render.render(write_still=True)
    print("QUANTTRACE_STILL wrote", args.out, "exists", os.path.isfile(args.out))


def main():
    args = parse_args()
    if not args.render and not args.save:
        args.dry_run = True
    scene, cubes, lamps, cam = build_still_life()
    describe(scene, cubes, lamps, cam)
    if args.save:
        os.makedirs(os.path.dirname(os.path.abspath(args.save)) or ".", exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=args.save)
        print("QUANTTRACE_STILL saved", args.save)
    if args.render:
        maybe_render(scene, args)
    else:
        print("QUANTTRACE_STILL no F12 (dry-run)")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
