# QuantTrace Slice 2an: TEX_IMAGE → world Background Color.
from __future__ import annotations
import argparse, os, sys
import bpy
from mathutils import Vector


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


def build_slice2an_scene(
    image_path="/tmp/qt_slice2an_checker.png",
    *,
    mode="teximage",
    projection="FLAT",
    strength=1.0,
    pull_camera=True,
    map_rot_z=0.15,
    env_path="/tmp/qt_slice2am_env.exr",
):
    """Locked cube + AREA; world Color TEX_IMAGE / RGB / HDR / Sky / Noise.

    mode:
      teximage           — TEX_IMAGE → Color, Vector ← TEX_COORD Generated, FLAT.
                           CLAIM plate. Color sock default left black.
      teximage_mapping   — same + Mapping VECTOR rot_z (unlinked L/R/S)
      teximage_unlinked  — TEX_IMAGE Vector unlinked (honesty; may be flat)
      rgb                — Slice 2al regression
      hdr                — Slice 2aa equirect regression
      nishita            — Slice 2am regression
      noise              — Noise → Color (must refuse pack)
      black              — unlinked Color black (live-graph partner)
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_cube_scene as cube
    import _quanttrace_tex_scene as texsc
    import _quanttrace_slice2al_scene as sc2al
    import _quanttrace_slice2aa_scene as sc2aa
    import _quanttrace_slice2am_scene as sc2am

    mode_key = str(mode).strip().lower()
    allowed = (
        "teximage", "teximage_mapping", "teximage_unlinked",
        "rgb", "hdr", "nishita", "noise", "black",
    )
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2an)")

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

    if mode_key == "black":
        print(
            "QUANTTRACE_SLICE2AN_WORLD mode black",
            "color", (0.0, 0.0, 0.0), "strength", float(str_in.default_value),
        )
    elif mode_key == "noise":
        noise = wnt.nodes.new("ShaderNodeTexNoise")
        noise.label = "WorldColorNoise"
        noise.location = (bg.location[0] - 240, bg.location[1] + 40)
        wnt.links.new(noise.outputs["Color"], color_in)
        print(
            "QUANTTRACE_SLICE2AN_WORLD mode noise",
            "from_type", noise.type,
            "color_linked", bool(color_in.is_linked),
        )
    else:
        img = texsc._write_checker_png(image_path, n=8)
        tex = wnt.nodes.new("ShaderNodeTexImage")
        tex.label = "WorldColorTexImage"
        tex.location = (bg.location[0] - 280, bg.location[1] + 40)
        tex.image = img
        tex.interpolation = "Linear"
        tex.extension = "REPEAT"
        tex.projection = str(projection).upper()
        color_in.default_value = (0.0, 0.0, 0.0, 1.0)
        wnt.links.new(tex.outputs["Color"], color_in)

        if mode_key == "teximage_unlinked":
            print(
                "QUANTTRACE_SLICE2AN_WORLD mode teximage_unlinked",
                "projection", tex.projection,
                "vector_linked", bool(tex.inputs["Vector"].is_linked),
                "path", getattr(img, "filepath", None),
                "cs", getattr(img.colorspace_settings, "name", None),
                "sock_default", tuple(float(v) for v in color_in.default_value[:3]),
                "strength", float(str_in.default_value),
            )
        else:
            texc = wnt.nodes.new("ShaderNodeTexCoord")
            texc.label = "WorldColorTexCoord"
            texc.location = (tex.location[0] - 280, tex.location[1])
            if mode_key == "teximage_mapping":
                mapping = wnt.nodes.new("ShaderNodeMapping")
                mapping.label = "WorldColorMapping"
                mapping.location = (tex.location[0] - 140, tex.location[1])
                mapping.vector_type = "VECTOR"
                mapping.inputs["Rotation"].default_value[2] = float(map_rot_z)
                wnt.links.new(texc.outputs["Generated"], mapping.inputs["Vector"])
                wnt.links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
                print(
                    "QUANTTRACE_SLICE2AN_WORLD mode teximage_mapping",
                    "projection", tex.projection,
                    "map_rot_z", float(map_rot_z),
                    "vector_type", mapping.vector_type,
                    "path", getattr(img, "filepath", None),
                    "cs", getattr(img.colorspace_settings, "name", None),
                    "sock_default", tuple(float(v) for v in color_in.default_value[:3]),
                    "strength", float(str_in.default_value),
                )
            else:
                wnt.links.new(texc.outputs["Generated"], tex.inputs["Vector"])
                print(
                    "QUANTTRACE_SLICE2AN_WORLD mode teximage",
                    "projection", tex.projection,
                    "vector_from", "Generated",
                    "path", getattr(img, "filepath", None),
                    "cs", getattr(img.colorspace_settings, "name", None),
                    "sock_default", tuple(float(v) for v in color_in.default_value[:3]),
                    "strength", float(str_in.default_value),
                )

    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2an_stock.exr")
    p.add_argument("--image", default="/tmp/qt_slice2an_checker.png")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument(
        "--mode",
        choices=(
            "teximage", "teximage_mapping", "teximage_unlinked",
            "rgb", "hdr", "nishita", "noise", "black",
        ),
        default="teximage",
    )
    p.add_argument(
        "--projection",
        choices=("FLAT", "BOX", "SPHERE", "TUBE"),
        default="FLAT",
    )
    p.add_argument("--strength", type=float, default=1.0)
    p.add_argument("--no-pull-camera", action="store_true", default=False)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2an_scene(
        image_path=args.image,
        mode=args.mode,
        projection=args.projection,
        strength=args.strength,
        pull_camera=not args.no_pull_camera,
    )
    print(
        "QUANTTRACE_SLICE2AN", cube_obj.name, "mode", args.mode,
        "strength", args.strength,
        "image", getattr(img, "filepath", None) if img is not None else None,
        "cam", tuple(round(v, 4) for v in cam.location),
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2AN wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
