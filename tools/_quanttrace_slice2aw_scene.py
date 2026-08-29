# QuantTrace Slice 2aw: synthetic N>32 mesh grid for pack-cap gate.
#
#   blender --background --python tools/_quanttrace_slice2aw_scene.py -- --dry-run
#   blender --background --python tools/_quanttrace_slice2aw_scene.py -- \
#       --n-meshes 64 --dry-run
#
# CPU only. No user GPU. No Make it Fast.

from __future__ import annotations

import argparse
import math
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
    p = argparse.ArgumentParser(description="QuantTrace Slice 2aw many-mesh scene")
    p.add_argument("--dry-run", action="store_true", default=False)
    p.add_argument("--n-meshes", type=int, default=64,
                   help="Number of cubes (must be >32 to exercise 2aw caps)")
    p.add_argument("--n-lights", type=int, default=2)
    p.add_argument("--save", metavar="BLEND", default="")
    return p.parse_args(_argv_after_dashdash())


def _look_at(obj, target=(0.0, 0.0, 0.0), track="-Z", up="Y"):
    direction = Vector(target) - Vector(obj.location)
    if direction.length < 1e-8:
        return
    obj.rotation_euler = direction.to_track_quat(track, up).to_euler()


def _principled_mat(name, base_color, roughness=0.5, metallic=0.0):
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
    nt.links.new(prin.outputs["BSDF"], out.inputs["Surface"])
    return mat


def build_many_mesh_scene(n_meshes=64, n_lights=2):
    """Grid of constant-Principled cubes + AREA lights + one camera."""
    if n_meshes < 1:
        raise ValueError("n_meshes must be >= 1")
    if n_lights < 1:
        raise ValueError("n_lights must be >= 1")

    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_cube_scene as cube

    scene, cube0, lamp0, cam = cube.build_locked_scene()
    # Remove default cube; rebuild as grid.
    bpy.data.objects.remove(cube0, do_unlink=True)

    side = max(1, int(math.ceil(math.sqrt(n_meshes))))
    spacing = 1.4
    origin = (-(side - 1) * spacing * 0.5, -(side - 1) * spacing * 0.5, 0.0)
    meshes = []
    for i in range(n_meshes):
        gx = i % side
        gy = i // side
        loc = (
            origin[0] + gx * spacing,
            origin[1] + gy * spacing,
            0.0,
        )
        bpy.ops.mesh.primitive_cube_add(location=loc, scale=(0.35, 0.35, 0.35))
        obj = bpy.context.active_object
        obj.name = f"CubeGrid_{i:04d}"
        t = (i % 7) / 6.0
        color = (0.2 + 0.6 * t, 0.15 + 0.4 * (1.0 - t), 0.55, 1.0)
        obj.data.materials.append(
            _principled_mat(f"MatGrid_{i:04d}", color, roughness=0.4 + 0.1 * (i % 3))
        )
        meshes.append(obj)

    # Retarget default AREA; add extras if requested.
    lamps = []
    lamp0.name = "AreaKey"
    lamp0.location = (0.0, -side * spacing * 0.6, side * spacing * 0.8)
    lamp0.data.energy = 800.0
    _look_at(lamp0, (0.0, 0.0, 0.0), track="-Z", up="Y")
    lamps.append(lamp0)
    for li in range(1, n_lights):
        ang = (2.0 * math.pi * li) / max(n_lights, 1)
        loc = (
            math.cos(ang) * side * spacing * 0.7,
            math.sin(ang) * side * spacing * 0.7,
            side * spacing * 0.55,
        )
        bpy.ops.object.light_add(type="AREA", location=loc)
        fill = bpy.context.active_object
        fill.name = f"AreaFill_{li}"
        fill.data.energy = 350.0
        fill.data.color = (0.85, 0.9, 1.0)
        if hasattr(fill.data, "size"):
            fill.data.size = 0.8
        _look_at(fill, (0.0, 0.0, 0.0), track="-Z", up="Y")
        lamps.append(fill)

    # Pull camera back so the grid is in frame for optional Session smoke.
    extent = side * spacing * 0.7
    cam.location = (0.0, -extent * 2.2, extent * 1.4)
    _look_at(cam, (0.0, 0.0, 0.0), track="-Z", up="Y")

    bpy.context.view_layer.update()
    return scene, tuple(meshes), tuple(lamps), cam


def describe(scene, meshes, lamps, cam):
    print("QUANTTRACE_SLICE2AW dry-run")
    print("  blender", bpy.app.version_string)
    print("  engine", scene.render.engine, "device", scene.cycles.device)
    print("  n_meshes", len(meshes), "n_lights", len(lamps))
    print("  camera", cam.name, tuple(round(v, 4) for v in cam.location))
    print("  first3", [m.name for m in meshes[:3]],
          "last", meshes[-1].name if meshes else None)


def main():
    args = parse_args()
    if not args.save:
        args.dry_run = True
    scene, meshes, lamps, cam = build_many_mesh_scene(
        n_meshes=args.n_meshes, n_lights=args.n_lights
    )
    describe(scene, meshes, lamps, cam)
    if args.save:
        os.makedirs(os.path.dirname(os.path.abspath(args.save)) or ".", exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=args.save)
        print("QUANTTRACE_SLICE2AW saved", args.save)
    else:
        print("QUANTTRACE_SLICE2AW no F12 (dry-run)")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
