# QuantTrace Slice 2ao: Gamma + HueSat → world Background Color.
from __future__ import annotations
import argparse, os, sys
import bpy
from mathutils import Vector


RGB = (1.0, 0.25, 0.1)
GAMMA = 2.2
HDR_GAMMA = 0.8
HSV_HUE = 0.6
HSV_SAT = 1.2
HSV_VAL = 0.85
HSV_FAC = 1.0


def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


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


def _add_rgb(wnt, bg, rgb):
    rgb_node = wnt.nodes.new("ShaderNodeRGB")
    rgb_node.label = "WorldColorRGB"
    rgb_node.location = (bg.location[0] - 480, bg.location[1] + 40)
    rgb_node.outputs[0].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
    return rgb_node


def _add_gamma(wnt, bg, gamma):
    node = wnt.nodes.new("ShaderNodeGamma")
    node.label = "WorldColorGamma"
    node.location = (bg.location[0] - 280, bg.location[1] + 40)
    node.inputs["Gamma"].default_value = float(gamma)
    return node


def _add_hsv(wnt, bg, *, hue, sat, val, fac):
    node = wnt.nodes.new("ShaderNodeHueSaturation")
    node.label = "WorldColorHueSat"
    node.location = (bg.location[0] - 140, bg.location[1] + 40)
    node.inputs["Hue"].default_value = float(hue)
    node.inputs["Saturation"].default_value = float(sat)
    node.inputs["Value"].default_value = float(val)
    fac_sock = node.inputs.get("Fac") or node.inputs.get("Factor")
    fac_sock.default_value = float(fac)
    return node


def build_slice2ao_scene(
    image_path="/tmp/qt_slice2ao_env.exr",
    *,
    mode="rgb_gamma",
    strength=1.0,
    pull_camera=True,
    env_path="/tmp/qt_slice2ao_env.exr",
):
    """Locked cube + AREA; Gamma / HueSat on world Color.

    mode:
      rgb_gamma      — RGB (1.0, 0.25, 0.1) → Gamma 2.2 → Background.
                       Color sock default left black. CLAIM plate.
      rgb_hsv        — RGB → HueSat hue=0.6 sat=1.2 val=0.85 fac=1.0
      rgb_gamma_hsv  — RGB → Gamma 2.2 → HueSat (loft order)
      hdr_gamma      — 2aa HDR equirect + Gamma 0.8 (EasyHDR-like)
      rgb            — Slice 2al regression
      hdr            — Slice 2aa regression
      nishita        — Slice 2am regression
      teximage       — Slice 2an Generated FLAT regression
      noise          — Noise → Color (must refuse pack)
      unlinked_rgb   — unlinked Color (1.0, 0.25, 0.1) live-graph partner
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_cube_scene as cube
    import _quanttrace_slice2al_scene as sc2al
    import _quanttrace_slice2aa_scene as sc2aa
    import _quanttrace_slice2am_scene as sc2am
    import _quanttrace_slice2an_scene as sc2an

    mode_key = str(mode).strip().lower()
    allowed = (
        "rgb_gamma", "rgb_hsv", "rgb_gamma_hsv", "hdr_gamma",
        "rgb", "hdr", "nishita", "teximage", "noise", "unlinked_rgb",
    )
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2ao)")

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
    if mode_key == "hdr_gamma":
        scene, cube_obj, lamp, cam, img = sc2aa.build_slice2aa_scene(
            image_path=env_path,
            projection="EQUIRECTANGULAR",
            strength=float(strength),
            black_world=False,
        )
        world = scene.world
        wnt = world.node_tree
        bg = next(n for n in wnt.nodes if n.type == "BACKGROUND")
        env = next(n for n in wnt.nodes if n.type == "TEX_ENVIRONMENT")
        # Insert Gamma 0.8 between Env Color and Background Color.
        for link in list(bg.inputs["Color"].links):
            wnt.links.remove(link)
        gamma = _add_gamma(wnt, bg, HDR_GAMMA)
        wnt.links.new(env.outputs["Color"], gamma.inputs["Color"])
        wnt.links.new(gamma.outputs["Color"], bg.inputs["Color"])
        bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
        print(
            "QUANTTRACE_SLICE2AO_WORLD mode hdr_gamma",
            "gamma", float(HDR_GAMMA),
            "env_path", getattr(img, "filepath", None),
            "sock_default", tuple(float(v) for v in bg.inputs["Color"].default_value[:3]),
            "strength", float(bg.inputs["Strength"].default_value),
        )
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

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
            "QUANTTRACE_SLICE2AO_WORLD mode unlinked_rgb",
            "color", rgb, "strength", float(str_in.default_value),
            "color_linked", bool(color_in.is_linked),
        )
    elif mode_key == "noise":
        noise = wnt.nodes.new("ShaderNodeTexNoise")
        noise.label = "WorldColorNoise"
        noise.location = (bg.location[0] - 240, bg.location[1] + 40)
        wnt.links.new(noise.outputs["Color"], color_in)
        print(
            "QUANTTRACE_SLICE2AO_WORLD mode noise",
            "from_type", noise.type,
            "color_linked", bool(color_in.is_linked),
        )
    else:
        rgb_node = _add_rgb(wnt, bg, rgb)
        if mode_key == "rgb_gamma":
            gamma = _add_gamma(wnt, bg, GAMMA)
            wnt.links.new(rgb_node.outputs[0], gamma.inputs["Color"])
            wnt.links.new(gamma.outputs["Color"], color_in)
            print(
                "QUANTTRACE_SLICE2AO_WORLD mode rgb_gamma",
                "rgb", rgb, "gamma", float(GAMMA),
                "sock_default", tuple(float(v) for v in color_in.default_value[:3]),
                "strength", float(str_in.default_value),
            )
        elif mode_key == "rgb_hsv":
            hsv = _add_hsv(
                wnt, bg, hue=HSV_HUE, sat=HSV_SAT, val=HSV_VAL, fac=HSV_FAC
            )
            wnt.links.new(rgb_node.outputs[0], hsv.inputs["Color"])
            wnt.links.new(hsv.outputs["Color"], color_in)
            print(
                "QUANTTRACE_SLICE2AO_WORLD mode rgb_hsv",
                "rgb", rgb,
                "hue", HSV_HUE, "sat", HSV_SAT, "val", HSV_VAL, "fac", HSV_FAC,
                "sock_default", tuple(float(v) for v in color_in.default_value[:3]),
                "strength", float(str_in.default_value),
            )
        elif mode_key == "rgb_gamma_hsv":
            # Loft order: Color source → Gamma → HSV → Background.
            gamma = _add_gamma(wnt, bg, GAMMA)
            hsv = _add_hsv(
                wnt, bg, hue=HSV_HUE, sat=HSV_SAT, val=HSV_VAL, fac=HSV_FAC
            )
            wnt.links.new(rgb_node.outputs[0], gamma.inputs["Color"])
            wnt.links.new(gamma.outputs["Color"], hsv.inputs["Color"])
            wnt.links.new(hsv.outputs["Color"], color_in)
            print(
                "QUANTTRACE_SLICE2AO_WORLD mode rgb_gamma_hsv",
                "rgb", rgb, "gamma", float(GAMMA),
                "hue", HSV_HUE, "sat", HSV_SAT, "val", HSV_VAL, "fac", HSV_FAC,
                "sock_default", tuple(float(v) for v in color_in.default_value[:3]),
                "strength", float(str_in.default_value),
            )
        else:
            raise RuntimeError(f"mode={mode_key!r} unhandled (Slice 2ao)")

    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2ao_stock.exr")
    p.add_argument("--image", default="/tmp/qt_slice2ao_env.exr")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument(
        "--mode",
        choices=(
            "rgb_gamma", "rgb_hsv", "rgb_gamma_hsv", "hdr_gamma",
            "rgb", "hdr", "nishita", "teximage", "noise", "unlinked_rgb",
        ),
        default="rgb_gamma",
    )
    p.add_argument("--strength", type=float, default=1.0)
    p.add_argument("--no-pull-camera", action="store_true", default=False)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2ao_scene(
        image_path=args.image,
        mode=args.mode,
        strength=args.strength,
        pull_camera=not args.no_pull_camera,
        env_path=args.image,
    )
    print(
        "QUANTTRACE_SLICE2AO", cube_obj.name, "mode", args.mode,
        "strength", args.strength,
        "image", getattr(img, "filepath", None) if img is not None else None,
        "cam", tuple(round(v, 4) for v in cam.location),
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2AO wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
