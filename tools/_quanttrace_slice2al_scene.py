# QuantTrace Slice 2al: Background Color constant RGB / Mix / unlinked.
from __future__ import annotations
import argparse, os, sys
import bpy
from mathutils import Vector


def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


RGB = (1.0, 0.25, 0.1)
MIX_A = (1.0, 0.0, 0.0)
MIX_B = (1.0, 0.5, 0.2)
MIX_FAC = 0.5


def _expected_mix_rgb(fac=MIX_FAC, a=MIX_A, b=MIX_B):
    f = float(fac)
    return (
        float(a[0]) * (1.0 - f) + float(b[0]) * f,
        float(a[1]) * (1.0 - f) + float(b[1]) * f,
        float(a[2]) * (1.0 - f) + float(b[2]) * f,
    )


def _pull_camera_for_world(cam, scale=1.8):
    """Pull camera back so Combined shows world pixels; keep cube in frame."""
    loc = Vector(cam.location) * float(scale)
    cam.location = loc
    direction = Vector((0.0, 0.0, 0.0)) - loc
    if direction.length > 1e-8:
        cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def _reset_world_nodes(scene, *, strength=1.0):
    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        scene.world = world
    world.use_nodes = True
    wnt = world.node_tree
    wnt.nodes.clear()
    out = wnt.nodes.new("ShaderNodeOutputWorld")
    bg = wnt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = float(strength)
    bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    wnt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    return world, wnt, bg


def build_slice2al_scene(
    image_path="/tmp/qt_slice2al_env.exr",
    *,
    mode="rgb",
    projection="EQUIRECTANGULAR",
    strength=1.0,
    color=RGB,
    mix_fac=MIX_FAC,
    mix_a=MIX_A,
    mix_b=MIX_B,
    pull_camera=True,
):
    """Locked cube + AREA; world Color RGB / Mix / unlinked / HDR / Sky.

    mode:
      rgb       — ShaderNodeRGB (1.0, 0.25, 0.1) → Color; Strength 1.0; no env.
                  Color socket default left black so ignore-link fails the gate.
      unlinked  — unlinked Color default (1.0, 0.25, 0.1), Strength 1.0, no env.
      mix_rgb   — MixRGB Fac=0.5 A=(1,0,0) B=(1,0.5,0.2) → Color; sock default black.
      black     — unlinked Color black, Strength 1.0, no env (live-graph partner).
      hdr       — Slice 2aa regression (HDR equirect, Strength 1.0).
      map_range — Slice 2ak regression (HDR + Map Range → Strength 0.7).
      sky       — Sky/Nishita → Color (must refuse pack).
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_cube_scene as cube
    import _quanttrace_slice2aa_scene as sc2aa
    import _quanttrace_slice2ak_scene as sc2ak

    mode_key = str(mode).strip().lower()
    allowed = ("rgb", "unlinked", "mix_rgb", "black", "hdr", "map_range", "sky")
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2al)")

    if mode_key == "hdr":
        return sc2aa.build_slice2aa_scene(
            image_path=image_path,
            projection=projection,
            strength=float(strength),
            black_world=False,
        )
    if mode_key == "map_range":
        return sc2ak.build_slice2ak_scene(
            image_path=image_path,
            mode="map_range",
            projection=projection,
            strength=0.7,
        )

    scene, cube_obj, lamp, cam = cube.build_locked_scene()
    mat = cube_obj.data.materials[0]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.7, 0.7, 0.7, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.5
    bsdf.inputs["Metallic"].default_value = 0.0

    if pull_camera:
        _pull_camera_for_world(cam, 1.8)

    world, wnt, bg = _reset_world_nodes(scene, strength=float(strength))
    color_in = bg.inputs["Color"]
    str_in = bg.inputs["Strength"]
    color_in.default_value = (0.0, 0.0, 0.0, 1.0)
    img = None
    rgb = tuple(float(c) for c in color)

    if mode_key == "unlinked":
        color_in.default_value = (rgb[0], rgb[1], rgb[2], 1.0)
        print(
            "QUANTTRACE_SLICE2AL_WORLD mode unlinked",
            "color", rgb, "strength", float(str_in.default_value),
            "color_linked", bool(color_in.is_linked),
        )
    elif mode_key == "black":
        color_in.default_value = (0.0, 0.0, 0.0, 1.0)
        print(
            "QUANTTRACE_SLICE2AL_WORLD mode black",
            "color", (0.0, 0.0, 0.0), "strength", float(str_in.default_value),
        )
    elif mode_key == "mix_rgb":
        mix = wnt.nodes.new("ShaderNodeMixRGB")
        mix.blend_type = "MIX"
        mix.use_clamp = False
        mix.label = "WorldColorMixRGB"
        mix.location = (bg.location[0] - 240, bg.location[1] + 40)
        mix.inputs["Fac"].default_value = float(mix_fac)
        mix.inputs["Color1"].default_value = (
            float(mix_a[0]), float(mix_a[1]), float(mix_a[2]), 1.0
        )
        mix.inputs["Color2"].default_value = (
            float(mix_b[0]), float(mix_b[1]), float(mix_b[2]), 1.0
        )
        color_in.default_value = (0.0, 0.0, 0.0, 1.0)
        wnt.links.new(mix.outputs["Color"], color_in)
        expected = _expected_mix_rgb(mix_fac, mix_a, mix_b)
        print(
            "QUANTTRACE_SLICE2AL_WORLD mode mix_rgb",
            "fac", float(mix_fac), "a", tuple(mix_a), "b", tuple(mix_b),
            "expected", expected,
            "sock_default", tuple(float(v) for v in color_in.default_value[:3]),
            "color_linked", bool(color_in.is_linked),
            "from_type", mix.type,
        )
    elif mode_key == "sky":
        sky = wnt.nodes.new("ShaderNodeTexSky")
        sky.label = "WorldColorSky"
        sky.location = (bg.location[0] - 240, bg.location[1] + 40)
        if hasattr(sky, "sky_type"):
            try:
                sky.sky_type = "NISHITA"
            except Exception:
                pass
        color_in.default_value = (0.0, 0.0, 0.0, 1.0)
        wnt.links.new(sky.outputs["Color"], color_in)
        print(
            "QUANTTRACE_SLICE2AL_WORLD mode sky",
            "sky_type", getattr(sky, "sky_type", None),
            "from_type", sky.type,
            "color_linked", bool(color_in.is_linked),
        )
    else:
        rgb_node = wnt.nodes.new("ShaderNodeRGB")
        rgb_node.label = "WorldColorRGB"
        rgb_node.location = (bg.location[0] - 240, bg.location[1] + 40)
        rgb_node.outputs[0].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
        color_in.default_value = (0.0, 0.0, 0.0, 1.0)
        wnt.links.new(rgb_node.outputs[0], color_in)
        print(
            "QUANTTRACE_SLICE2AL_WORLD mode rgb",
            "color", rgb,
            "sock_default", tuple(float(v) for v in color_in.default_value[:3]),
            "color_linked", bool(color_in.is_linked),
            "from_type", rgb_node.type,
            "strength", float(str_in.default_value),
        )

    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2al_stock.exr")
    p.add_argument("--image", default="/tmp/qt_slice2al_env.exr")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument(
        "--mode",
        choices=("rgb", "unlinked", "mix_rgb", "black", "hdr", "map_range", "sky"),
        default="rgb",
    )
    p.add_argument(
        "--projection",
        choices=("EQUIRECTANGULAR", "MIRROR_BALL"),
        default="EQUIRECTANGULAR",
    )
    p.add_argument("--strength", type=float, default=1.0)
    p.add_argument("--no-pull-camera", action="store_true", default=False)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2al_scene(
        image_path=args.image,
        mode=args.mode,
        projection=args.projection,
        strength=args.strength,
        pull_camera=not args.no_pull_camera,
    )
    print(
        "QUANTTRACE_SLICE2AL", cube_obj.name, "mode", args.mode,
        "strength", args.strength,
        "image", getattr(img, "filepath", None) if img is not None else None,
        "cam", tuple(round(v, 4) for v in cam.location),
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2AL wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
