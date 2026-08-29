# QuantTrace Slice 2ar: linked Sky Vector (TEX_COORD / Mapping) → Background Color.
# RGB Curves deferred (curve LUT/SVM); Mix landed as 2aq.
from __future__ import annotations
import argparse, os, sys
import bpy
from mathutils import Vector


MAP_ROT_Z = 0.7  # radians; non-identity so Mapping lever is live vs unlinked


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


def _set_sky_type(sky, preferred=("MULTIPLE_SCATTERING", "NISHITA")):
    """Set sky_type from preferred list; return RNA string actually set."""
    if not hasattr(sky, "sky_type"):
        return getattr(sky, "sky_type", None)
    for ident in preferred:
        try:
            sky.sky_type = ident
            return getattr(sky, "sky_type", None)
        except Exception:
            continue
    return getattr(sky, "sky_type", None)


def _sky_vector_input(sky):
    for inp in list(sky.inputs):
        if getattr(inp, "identifier", "") == "Vector" or getattr(inp, "name", "") == "Vector":
            return inp
    getter = getattr(sky.inputs, "get", None)
    return getter("Vector") if callable(getter) else None


def build_slice2ar_scene(
    image_path="/tmp/qt_slice2ar_env.exr",
    *,
    mode="sky_map",
    projection="EQUIRECTANGULAR",
    strength=1.0,
    rotation_z=MAP_ROT_Z,
    scale=(1.0, 1.0, 1.0),
    location=(0.0, 0.0, 0.0),
    pull_camera=True,
):
    """Locked cube + AREA; Sky Vector linked (Slice 2ar) + regressions.

    mode:
      sky_map      — PREETHAM + TEX_COORD Generated → Mapping(VECTOR, rot_z) → Sky Vector. CLAIM.
                      (Nishita/MULTIPLE hides Vector; Blender ignores the link — use PREETHAM.)
      sky_gen      — PREETHAM + TEX_COORD Generated → Sky Vector (no Mapping).
      preetham     — PREETHAM unlinked Vector (live-graph partner / identity).
      nishita      — Slice 2am unlinked MULTIPLE Vector (mode 0 identity).
      rgb_mix      — Slice 2aq Mix regression.
      rgb / hdr / teximage — prior identity regressions.
      rgb_curves   — RGB Curves → Color (must refuse pack).
      noise        — Noise → Color (must refuse pack).
      unlinked_sky — alias of nishita for live-graph partner.
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

    mode_key = str(mode).strip().lower()
    allowed = (
        "sky_map", "sky_gen", "preetham", "nishita", "unlinked_sky",
        "rgb_mix", "rgb", "hdr", "teximage", "rgb_curves", "noise",
    )
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2ar)")

    if mode_key == "hdr":
        return sc2aa.build_slice2aa_scene(
            image_path=image_path,
            projection=projection,
            strength=float(strength),
            black_world=False,
        )
    if mode_key == "rgb":
        return sc2al.build_slice2al_scene(
            image_path=image_path,
            mode="rgb",
            projection=projection,
            strength=float(strength),
            pull_camera=pull_camera,
        )
    if mode_key in ("nishita", "unlinked_sky"):
        return sc2am.build_slice2am_scene(
            image_path=image_path,
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
            image_path=image_path,
            mode="rgb_mix",
            strength=float(strength),
            pull_camera=pull_camera,
            env_path=image_path,
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
    color_in.default_value = (0.0, 0.0, 0.0, 1.0)
    img = None

    if mode_key == "preetham":
        sky = wnt.nodes.new("ShaderNodeTexSky")
        sky.label = "WorldColorSky"
        sky.location = (bg.location[0] - 240, bg.location[1] + 40)
        sky_type = _set_sky_type(sky, ("PREETHAM",))
        wnt.links.new(sky.outputs["Color"], color_in)
        vec_in = _sky_vector_input(sky)
        print(
            "QUANTTRACE_SLICE2AR_WORLD mode preetham",
            "sky_type", sky_type,
            "vector_linked", bool(vec_in.is_linked) if vec_in is not None else None,
        )
    elif mode_key == "noise":
        noise = wnt.nodes.new("ShaderNodeTexNoise")
        noise.label = "WorldColorNoiseRefuse"
        noise.location = (bg.location[0] - 240, bg.location[1] + 40)
        wnt.links.new(noise.outputs["Color"], color_in)
        print("QUANTTRACE_SLICE2AR_WORLD mode noise")
    elif mode_key == "rgb_curves":
        curves = wnt.nodes.new("ShaderNodeRGBCurve")
        curves.label = "WorldColorRGBCurvesRefuse"
        curves.location = (bg.location[0] - 240, bg.location[1] + 40)
        rgb = wnt.nodes.new("ShaderNodeRGB")
        rgb.outputs[0].default_value = (1.0, 0.25, 0.1, 1.0)
        rgb.location = (curves.location[0] - 200, curves.location[1])
        wnt.links.new(rgb.outputs[0], curves.inputs["Color"])
        wnt.links.new(curves.outputs["Color"], color_in)
        print("QUANTTRACE_SLICE2AR_WORLD mode rgb_curves")
    else:
        sky = wnt.nodes.new("ShaderNodeTexSky")
        sky.label = "WorldColorSky"
        sky.location = (bg.location[0] - 240, bg.location[1] + 40)
        # PREETHAM: Vector socket available (is_unavailable=False). Nishita hides it
        # and Blender stock ignores linked Vector (map vs unlinked Δmax=0).
        sky_type = _set_sky_type(sky, ("PREETHAM",))
        wnt.links.new(sky.outputs["Color"], color_in)
        vec_in = _sky_vector_input(sky)
        if vec_in is None:
            raise RuntimeError("TEX_SKY has no Vector input")
        texc = wnt.nodes.new("ShaderNodeTexCoord")
        texc.label = "SkyVectorTexCoord"
        texc.location = (sky.location[0] - 400, sky.location[1])
        # Nishita/MULTIPLE hides Vector (is_unavailable); link still packs.
        if mode_key == "sky_map":
            mapping = wnt.nodes.new("ShaderNodeMapping")
            mapping.label = "SkyVectorMapping"
            mapping.location = (sky.location[0] - 200, sky.location[1])
            # Set L/R/S before VECTOR — Blender 5.2 hides Location under VECTOR
            # (is_unavailable / KeyError). Same order as Slice 2ac.
            mapping.inputs["Location"].default_value = (
                float(location[0]), float(location[1]), float(location[2]),
            )
            mapping.inputs["Rotation"].default_value = (0.0, 0.0, float(rotation_z))
            mapping.inputs["Scale"].default_value = (
                float(scale[0]), float(scale[1]), float(scale[2]),
            )
            mapping.vector_type = "VECTOR"
            wnt.links.new(texc.outputs["Generated"], mapping.inputs["Vector"])
            wnt.links.new(mapping.outputs["Vector"], vec_in)
            print(
                "QUANTTRACE_SLICE2AR_WORLD mode sky_map",
                "sky_type", sky_type,
                "rot_z", float(rotation_z),
                "scale", tuple(float(v) for v in scale),
                "vector_linked", bool(vec_in.is_linked),
            )
        else:  # sky_gen
            wnt.links.new(texc.outputs["Generated"], vec_in)
            print(
                "QUANTTRACE_SLICE2AR_WORLD mode sky_gen",
                "sky_type", sky_type,
                "vector_linked", bool(vec_in.is_linked),
                "from", "TEX_COORD.Generated",
            )

    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2ar_stock.exr")
    p.add_argument("--image", default="/tmp/qt_slice2ar_env.exr")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument(
        "--mode",
        choices=(
            "sky_map", "sky_gen", "preetham", "nishita", "unlinked_sky",
            "rgb_mix", "rgb", "hdr", "teximage", "rgb_curves", "noise",
        ),
        default="sky_map",
    )
    p.add_argument("--projection", choices=("EQUIRECTANGULAR", "MIRROR_BALL"),
                   default="EQUIRECTANGULAR")
    p.add_argument("--strength", type=float, default=1.0)
    p.add_argument("--rotation-z", type=float, default=MAP_ROT_Z)
    p.add_argument("--no-pull-camera", action="store_true", default=False)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2ar_scene(
        image_path=args.image,
        mode=args.mode,
        projection=args.projection,
        strength=args.strength,
        rotation_z=args.rotation_z,
        pull_camera=not args.no_pull_camera,
    )
    print(
        "QUANTTRACE_SLICE2AR", cube_obj.name, "mode", args.mode,
        "strength", args.strength,
        "cam", tuple(round(v, 4) for v in cam.location),
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2AR wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
