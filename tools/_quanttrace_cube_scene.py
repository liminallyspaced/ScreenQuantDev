# Locked QuantTrace cube scene (acceptance gate).
#
# Builds the QUANTTRACE-CUBE.md toy: one cube, Principled, one area light,
# one camera, black world. Default is a dry-run that constructs the scene
# and exits (no F12). Optional --render does a tiny CPU Cycles EXR (64x64)
# for a smoke test — not the 256x256/128 spp gate.
#
# Usage (from repo root):
#   blender --background --python tools/_quanttrace_cube_scene.py -- --dry-run
#   blender --background --python tools/_quanttrace_cube_scene.py -- --save /tmp/quanttrace_cube.blend
#   blender --background --python tools/_quanttrace_cube_scene.py -- --render --samples 8 --res 64
#
# CPU only. No user GPU. No Make it Fast. No QuantTrace F12 (is_tracer=0).

from __future__ import annotations

import argparse
import os
import sys

import bpy
from mathutils import Vector


# QUANTTRACE-CUBE.md locked values.
CUBE_SCALE = 1.0
PRINCIPLED = dict(
    base_color=(0.8, 0.8, 0.8, 1.0),
    roughness=0.5,
    metallic=0.0,
    ior=1.45,
    alpha=1.0,
)
AREA_LOC = (4.07625, 1.00545, 5.90386)
AREA_SIZE = 1.0
AREA_ENERGY = 1000.0
AREA_COLOR = (1.0, 1.0, 1.0)
CAM_LOC = (7.358891, -6.925791, 4.958309)
CAM_LENS = 50.0
CAM_SENSOR = 36.0
GATE_RES = 256
GATE_SAMPLES = 128
GATE_SEED = 0
GATE_CLAMP_INDIRECT = 10.0
GATE_FILTER_WIDTH = 1.5


def _argv_after_dashdash():
    argv = sys.argv
    if "--" in argv:
        return argv[argv.index("--") + 1 :]
    return []


def parse_args():
    p = argparse.ArgumentParser(description="QuantTrace locked cube scene")
    p.add_argument("--dry-run", action="store_true", default=False,
                   help="Build scene, print, exit. Default if neither --render nor --save.")
    p.add_argument("--save", metavar="BLEND", default="",
                   help="Write .blend (gitignored). Path outside addon zip.")
    p.add_argument("--render", action="store_true", default=False,
                   help="F12 stock Cycles CPU to EXR (tiny res unless overridden).")
    p.add_argument("--out", metavar="EXR", default="/tmp/quanttrace_cube_cycles_combined.exr")
    p.add_argument("--res", type=int, default=64,
                   help="Render resolution (default 64; gate is 256, do not use unless ready).")
    p.add_argument("--samples", type=int, default=8,
                   help="Fixed samples (default 8 for smoke; gate is 128).")
    return p.parse_args(_argv_after_dashdash())


def _look_at(obj, target=(0.0, 0.0, 0.0), track="-Z", up="Y"):
    direction = Vector(target) - Vector(obj.location)
    if direction.length < 1e-8:
        return
    obj.rotation_euler = direction.to_track_quat(track, up).to_euler()


def build_locked_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)

    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.render.engine = "CYCLES"
    scene.render.resolution_x = GATE_RES
    scene.render.resolution_y = GATE_RES
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "OPEN_EXR"
    scene.render.image_settings.color_depth = "32"
    scene.render.image_settings.exr_codec = "ZIP"
    scene.render.image_settings.color_mode = "RGB"
    # Linear Combined: do not bake a view transform into the EXR.
    scene.view_settings.view_transform = "Raw"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0

    cycles = scene.cycles
    cycles.device = "CPU"
    cycles.samples = GATE_SAMPLES
    cycles.use_adaptive_sampling = False
    cycles.use_denoising = False
    cycles.seed = GATE_SEED
    if hasattr(cycles, "sample_clamp_direct"):
        cycles.sample_clamp_direct = 0.0
    if hasattr(cycles, "sample_clamp_indirect"):
        cycles.sample_clamp_indirect = GATE_CLAMP_INDIRECT
    if hasattr(cycles, "pixel_filter_type"):
        cycles.pixel_filter_type = "GAUSSIAN"
    if hasattr(scene.cycles, "filter_width"):
        scene.cycles.filter_width = GATE_FILTER_WIDTH
    elif hasattr(scene.render, "filter_size"):
        scene.render.filter_size = GATE_FILTER_WIDTH

    # Cube
    bpy.ops.mesh.primitive_cube_add(location=(0.0, 0.0, 0.0), scale=(CUBE_SCALE, CUBE_SCALE, CUBE_SCALE))
    cube = bpy.context.active_object
    cube.name = "Cube"

    mat = bpy.data.materials.new("CubePrincipled")
    mat.use_nodes = True
    nt = mat.node_tree
    for node in list(nt.nodes):
        nt.nodes.remove(node)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    out.location = (300, 0)
    prin = nt.nodes.new("ShaderNodeBsdfPrincipled")
    prin.location = (0, 0)
    prin.inputs["Base Color"].default_value = PRINCIPLED["base_color"]
    prin.inputs["Roughness"].default_value = PRINCIPLED["roughness"]
    prin.inputs["Metallic"].default_value = PRINCIPLED["metallic"]
    if "IOR" in prin.inputs:
        prin.inputs["IOR"].default_value = PRINCIPLED["ior"]
    if "Alpha" in prin.inputs:
        prin.inputs["Alpha"].default_value = PRINCIPLED["alpha"]
    nt.links.new(prin.outputs["BSDF"], out.inputs["Surface"])
    cube.data.materials.append(mat)

    # Area light
    bpy.ops.object.light_add(type="AREA", location=AREA_LOC)
    lamp = bpy.context.active_object
    lamp.name = "Area"
    lamp.data.energy = AREA_ENERGY
    lamp.data.color = AREA_COLOR
    if hasattr(lamp.data, "shape"):
        lamp.data.shape = "SQUARE"
    if hasattr(lamp.data, "size"):
        lamp.data.size = AREA_SIZE
    _look_at(lamp, (0.0, 0.0, 0.0), track="-Z", up="Y")

    # Camera
    bpy.ops.object.camera_add(location=CAM_LOC)
    cam = bpy.context.active_object
    cam.name = "Camera"
    cam.data.lens = CAM_LENS
    cam.data.sensor_width = CAM_SENSOR
    cam.data.type = "PERSP"
    _look_at(cam, (0.0, 0.0, 0.0), track="-Z", up="Y")
    scene.camera = cam

    # World: black, strength 0
    world = bpy.data.worlds.new("World")
    scene.world = world
    world.use_nodes = True
    wnt = world.node_tree
    bg = None
    for n in wnt.nodes:
        if n.type == "BACKGROUND":
            bg = n
            break
    if bg is None:
        bg = wnt.nodes.new("ShaderNodeBackground")
        outw = None
        for n in wnt.nodes:
            if n.type == "OUTPUT_WORLD":
                outw = n
                break
        if outw is None:
            outw = wnt.nodes.new("ShaderNodeOutputWorld")
        wnt.links.new(bg.outputs["Background"], outw.inputs["Surface"])
    bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    bg.inputs["Strength"].default_value = 0.0

    return scene, cube, lamp, cam


def describe(scene, cube, lamp, cam):
    mats = [s.material.name if s.material else None for s in cube.material_slots]
    print("QUANTTRACE_CUBE dry-run")
    print("  blender", bpy.app.version_string)
    print("  engine", scene.render.engine, "device", scene.cycles.device)
    print("  res", scene.render.resolution_x, "x", scene.render.resolution_y)
    print("  samples", scene.cycles.samples, "adaptive", scene.cycles.use_adaptive_sampling,
          "seed", scene.cycles.seed, "denoise", scene.cycles.use_denoising)
    print("  cube", cube.name, "loc", tuple(round(v, 5) for v in cube.location), "mats", mats)
    print("  light", lamp.type, lamp.data.type, "energy", lamp.data.energy,
          "size", getattr(lamp.data, "size", None), "loc", tuple(round(v, 5) for v in lamp.location))
    print("  camera lens", cam.data.lens, "sensor", cam.data.sensor_width,
          "loc", tuple(round(v, 5) for v in cam.location))
    print("  world strength", scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value
          if "Background" in scene.world.node_tree.nodes else "?")
    print("  view_transform", scene.view_settings.view_transform)
    print("  objects", [o.name for o in scene.objects])
    print("  is_tracer=0 — this script only builds stock Cycles reference")


def maybe_render(scene, args):
    scene.render.resolution_x = args.res
    scene.render.resolution_y = args.res
    scene.cycles.samples = args.samples
    scene.render.filepath = args.out
    print("QUANTTRACE_CUBE render CPU", args.res, "spp", args.samples, "->", args.out)
    bpy.ops.render.render(write_still=True)
    print("QUANTTRACE_CUBE wrote", args.out, "exists", os.path.isfile(args.out))


def main():
    args = parse_args()
    if not args.render and not args.save:
        args.dry_run = True
    scene, cube, lamp, cam = build_locked_scene()
    describe(scene, cube, lamp, cam)
    if args.save:
        os.makedirs(os.path.dirname(os.path.abspath(args.save)) or ".", exist_ok=True)
        bpy.ops.wm.save_as_mainfile(filepath=args.save)
        print("QUANTTRACE_CUBE saved", args.save)
    if args.render:
        maybe_render(scene, args)
    else:
        print("QUANTTRACE_CUBE no F12 (dry-run)")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
