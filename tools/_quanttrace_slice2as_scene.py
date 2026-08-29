# QuantTrace Slice 2as: ShaderNodeRGBCurve → world Background Color (packed LUT).
from __future__ import annotations
import argparse, os, sys
import bpy
from mathutils import Vector


RGB = (1.0, 0.25, 0.1)
GAMMA = 2.2
# Non-identity master (I = DNA cm[3] = curves[3]): mid pull so lever is live.
CURVE_I_MID_Y = 0.35


def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def _pull_camera_for_world(cam, scale=1.8):
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


def _add_rgb(wnt, bg, rgb):
    rgb_node = wnt.nodes.new("ShaderNodeRGB")
    rgb_node.label = "WorldColorRGB"
    rgb_node.location = (bg.location[0] - 560, bg.location[1] + 40)
    rgb_node.outputs[0].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
    return rgb_node


def _add_rgb_curves(wnt, bg, *, mid_y=CURVE_I_MID_Y):
    """RGB Curves with non-identity master (I=curves[3]) mid point."""
    node = wnt.nodes.new("ShaderNodeRGBCurve")
    node.label = "WorldColorRGBCurves"
    node.location = (bg.location[0] - 360, bg.location[1] + 40)
    # Fac default 1.0 unlinked
    fac = node.inputs.get("Fac") or node.inputs.get("Factor")
    fac.default_value = 1.0
    mapping = node.mapping
    # DNA order used by Cycles: cm[0]=R, cm[1]=G, cm[2]=B, cm[3]=I
    # Pull master I mid so all channels move (clearly live vs unlinked RGB).
    cm_i = mapping.curves[3]
    while len(cm_i.points) > 2:
        cm_i.points.remove(cm_i.points[1])
    cm_i.points[0].location = (0.0, 0.0)
    cm_i.points[1].location = (1.0, 1.0)
    cm_i.points.new(0.5, float(mid_y))
    mapping.update()
    return node


def _add_gamma(wnt, bg, gamma):
    node = wnt.nodes.new("ShaderNodeGamma")
    node.label = "WorldColorGamma"
    node.location = (bg.location[0] - 180, bg.location[1] + 40)
    node.inputs["Gamma"].default_value = float(gamma)
    return node


def build_slice2as_scene(
    image_path="/tmp/qt_slice2as_env.exr",
    *,
    mode="rgb_curves",
    strength=1.0,
    pull_camera=True,
    env_path="/tmp/qt_slice2as_env.exr",
):
    """Locked cube + AREA; RGB Curves → world Color (+ regressions).

    mode:
      rgb_curves       — RGB → RGB Curves (non-id I mid) → BG. CLAIM.
      rgb_curves_gamma — RGB → Curves → Gamma 2.2 → BG.
      rgb / rgb_mix / hdr / nishita / teximage / sky_map — identity regressions.
      noise            — Noise → Color (must refuse).
      unlinked_rgb     — live-graph partner (no Curves).
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_cube_scene as cube
    import _quanttrace_slice2al_scene as sc2al
    import _quanttrace_slice2aa_scene as sc2aa
    import _quanttrace_slice2am_scene as sc2am
    import _quanttrace_slice2an_scene as sc2an
    import _quanttrace_slice2aq_scene as sc2aq
    import _quanttrace_slice2ar_scene as sc2ar

    mode_key = str(mode).strip().lower()
    allowed = (
        "rgb_curves", "rgb_curves_gamma",
        "rgb", "rgb_mix", "hdr", "nishita", "teximage", "sky_map",
        "noise", "unlinked_rgb",
    )
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2as)")

    if mode_key == "hdr":
        return sc2aa.build_slice2aa_scene(
            image_path=env_path,
            projection="EQUIRECTANGULAR",
            strength=float(strength),
            black_world=False,
        )
    if mode_key == "rgb":
        return sc2al.build_slice2al_scene(
            image_path=env_path,
            mode="rgb",
            projection="EQUIRECTANGULAR",
            strength=float(strength),
            pull_camera=pull_camera,
        )
    if mode_key == "nishita":
        return sc2am.build_slice2am_scene(
            image_path=env_path,
            mode="nishita",
            strength=float(strength),
            pull_camera=pull_camera,
        )
    if mode_key == "teximage":
        return sc2an.build_slice2an_scene(
            image_path="/tmp/qt_slice2an_checker.png",
            mode="teximage",
            projection="FLAT",
            strength=float(strength),
            pull_camera=pull_camera,
        )
    if mode_key == "rgb_mix":
        return sc2aq.build_slice2aq_scene(
            image_path=env_path,
            mode="rgb_mix",
            strength=float(strength),
            pull_camera=pull_camera,
            env_path=env_path,
        )
    if mode_key == "sky_map":
        return sc2ar.build_slice2ar_scene(
            image_path=env_path,
            mode="sky_map",
            strength=float(strength),
            pull_camera=pull_camera,
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
    rgb = RGB

    if mode_key == "unlinked_rgb":
        color_in.default_value = (rgb[0], rgb[1], rgb[2], 1.0)
        print(
            "QUANTTRACE_SLICE2AS_WORLD mode unlinked_rgb",
            "color", rgb, "strength", float(str_in.default_value),
        )
    elif mode_key == "noise":
        noise = wnt.nodes.new("ShaderNodeTexNoise")
        noise.label = "WorldColorNoiseRefuse"
        noise.location = (bg.location[0] - 240, bg.location[1] + 40)
        wnt.links.new(noise.outputs["Color"], color_in)
        print("QUANTTRACE_SLICE2AS_WORLD mode noise")
    else:
        rgb_node = _add_rgb(wnt, bg, rgb)
        curves = _add_rgb_curves(wnt, bg)
        wnt.links.new(rgb_node.outputs[0], curves.inputs["Color"])
        if mode_key == "rgb_curves_gamma":
            gamma = _add_gamma(wnt, bg, GAMMA)
            wnt.links.new(curves.outputs["Color"], gamma.inputs["Color"])
            wnt.links.new(gamma.outputs["Color"], color_in)
            print(
                "QUANTTRACE_SLICE2AS_WORLD mode rgb_curves_gamma",
                "rgb", rgb, "I_mid_y", CURVE_I_MID_Y, "gamma", GAMMA,
            )
        else:
            wnt.links.new(curves.outputs["Color"], color_in)
            print(
                "QUANTTRACE_SLICE2AS_WORLD mode rgb_curves",
                "rgb", rgb, "I_mid_y", CURVE_I_MID_Y,
                "fac", float(curves.inputs["Fac"].default_value),
                "extend", curves.mapping.extend,
            )

    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="/tmp/quanttrace_slice2as_stock.exr")
    p.add_argument("--image", default="/tmp/qt_slice2as_env.exr")
    p.add_argument(
        "--mode",
        choices=(
            "rgb_curves", "rgb_curves_gamma",
            "rgb", "rgb_mix", "hdr", "nishita", "teximage", "sky_map",
            "noise", "unlinked_rgb",
        ),
        default="rgb_curves",
    )
    p.add_argument("--strength", type=float, default=1.0)
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    args = p.parse_args(_argv())
    scene, *_rest = build_slice2as_scene(
        image_path=args.image,
        mode=args.mode,
        strength=args.strength,
        env_path=args.image,
    )
    scene.render.resolution_x = scene.render.resolution_y = args.res
    scene.cycles.samples = args.samples
    scene.render.filepath = args.out
    bpy.ops.render.render(write_still=True)
    print("QUANTTRACE_SLICE2AS_STOCK", args.out)


if __name__ == "__main__":
    main()
