# QuantTrace Slice 2am: Sky Texture → world Background Color (Nishita/MULTIPLE).
from __future__ import annotations
import argparse, os, sys
import bpy
from mathutils import Vector


def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


ELEV_LIVE = 0.6  # radians; non-default so the sky graph is live


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


def _set_sky_nishita(sky):
    """Blender 5.2 identifier is MULTIPLE_SCATTERING; NISHITA is the legacy name."""
    if not hasattr(sky, "sky_type"):
        return getattr(sky, "sky_type", None)
    for ident in ("MULTIPLE_SCATTERING", "NISHITA"):
        try:
            sky.sky_type = ident
            break
        except Exception:
            continue
    return getattr(sky, "sky_type", None)


def build_slice2am_scene(
    image_path="/tmp/qt_slice2am_env.exr",
    *,
    mode="nishita",
    projection="EQUIRECTANGULAR",
    strength=1.0,
    sun_elevation=None,
    pull_camera=True,
):
    """Locked cube + AREA; world Color Sky / RGB / HDR.

    mode:
      nishita           — ShaderNodeTexSky MULTIPLE_SCATTERING/NISHITA, default RNA,
                          Strength 1.0, Color socket default left black.
      nishita_elev      — same + sun_elevation=0.6 rad (live graph).
      rgb               — Slice 2al regression (world_color, no sky).
      hdr               — Slice 2aa regression (env path, sky_type=0).
      sky_vector_linked — TEX_COORD → Sky Vector (must refuse pack).
      black             — unlinked Color black (live-graph partner).
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_cube_scene as cube
    import _quanttrace_slice2al_scene as sc2al
    import _quanttrace_slice2aa_scene as sc2aa

    mode_key = str(mode).strip().lower()
    allowed = ("nishita", "nishita_elev", "rgb", "hdr", "sky_vector_linked", "black")
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2am)")

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
        color_in.default_value = (0.0, 0.0, 0.0, 1.0)
        print(
            "QUANTTRACE_SLICE2AM_WORLD mode black",
            "color", (0.0, 0.0, 0.0), "strength", float(str_in.default_value),
        )
    else:
        sky = wnt.nodes.new("ShaderNodeTexSky")
        sky.label = "WorldColorSky"
        sky.location = (bg.location[0] - 240, bg.location[1] + 40)
        sky_type = _set_sky_nishita(sky)
        if mode_key == "nishita_elev":
            elev = float(sun_elevation) if sun_elevation is not None else ELEV_LIVE
            sky.sun_elevation = elev
        color_in.default_value = (0.0, 0.0, 0.0, 1.0)
        wnt.links.new(sky.outputs["Color"], color_in)
        if mode_key == "sky_vector_linked":
            texc = wnt.nodes.new("ShaderNodeTexCoord")
            texc.label = "SkyVectorTexCoord"
            texc.location = (sky.location[0] - 240, sky.location[1])
            vec_in = None
            for inp in list(sky.inputs):
                if getattr(inp, "identifier", "") == "Vector" or getattr(inp, "name", "") == "Vector":
                    vec_in = inp
                    break
            if vec_in is None:
                raise RuntimeError("TEX_SKY has no Vector input")
            # Nishita/MULTIPLE hides Vector (is_unavailable); still link so packer refuses.
            wnt.links.new(texc.outputs["Generated"], vec_in)
            print(
                "QUANTTRACE_SLICE2AM_WORLD mode sky_vector_linked",
                "sky_type", sky_type,
                "vector_linked", bool(vec_in.is_linked),
                "from_type", texc.type,
            )
        else:
            vec_in = sky.inputs.get("Vector")
            print(
                "QUANTTRACE_SLICE2AM_WORLD mode", mode_key,
                "sky_type", sky_type,
                "sun_elevation", float(getattr(sky, "sun_elevation", 0.0)),
                "sun_rotation", float(getattr(sky, "sun_rotation", 0.0)),
                "sun_disc", bool(getattr(sky, "sun_disc", False)),
                "sun_size", float(getattr(sky, "sun_size", 0.0)),
                "sun_intensity", float(getattr(sky, "sun_intensity", 0.0)),
                "altitude", float(getattr(sky, "altitude", 0.0)),
                "air_density", float(getattr(sky, "air_density", 0.0)),
                "aerosol_density", float(
                    getattr(sky, "aerosol_density", getattr(sky, "dust_density", 0.0))
                ),
                "ozone_density", float(getattr(sky, "ozone_density", 0.0)),
                "vector_linked", bool(vec_in.is_linked) if vec_in is not None else None,
                "sock_default", tuple(float(v) for v in color_in.default_value[:3]),
                "color_linked", bool(color_in.is_linked),
                "from_type", sky.type,
                "strength", float(str_in.default_value),
            )

    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2am_stock.exr")
    p.add_argument("--image", default="/tmp/qt_slice2am_env.exr")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument(
        "--mode",
        choices=("nishita", "nishita_elev", "rgb", "hdr", "sky_vector_linked", "black"),
        default="nishita",
    )
    p.add_argument(
        "--projection",
        choices=("EQUIRECTANGULAR", "MIRROR_BALL"),
        default="EQUIRECTANGULAR",
    )
    p.add_argument("--strength", type=float, default=1.0)
    p.add_argument("--no-pull-camera", action="store_true", default=False)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2am_scene(
        image_path=args.image,
        mode=args.mode,
        projection=args.projection,
        strength=args.strength,
        pull_camera=not args.no_pull_camera,
    )
    print(
        "QUANTTRACE_SLICE2AM", cube_obj.name, "mode", args.mode,
        "strength", args.strength,
        "image", getattr(img, "filepath", None) if img is not None else None,
        "cam", tuple(round(v, 4) for v in cam.location),
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2AM wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
