# QuantTrace Slice 2av: Mapping vector_type POINT on TEX_ENVIRONMENT Vector.
from __future__ import annotations
import argparse, os, sys
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def _pin_persistent_off(scene):
    if hasattr(scene.render, "use_persistent_data"):
        scene.render.use_persistent_data = False


def _wire_env_mapping(wnt, env, *, vector_type, location, rotation_z, scale):
    """TEX_COORD Generated → Mapping(vector_type) → Env Vector."""
    vec_in = env.inputs["Vector"]
    for link in list(vec_in.links):
        wnt.links.remove(link)
    tc = wnt.nodes.new("ShaderNodeTexCoord")
    tc.location = (-600, 200)
    mapping = wnt.nodes.new("ShaderNodeMapping")
    mapping.location = (-400, 200)
    # Set L/R/S while POINT so Location is addressable (VECTOR hides it in 5.2).
    mapping.vector_type = "POINT"
    mapping.inputs["Location"].default_value = (
        float(location[0]), float(location[1]), float(location[2]),
    )
    mapping.inputs["Rotation"].default_value = (0.0, 0.0, float(rotation_z))
    mapping.inputs["Scale"].default_value = (
        float(scale[0]), float(scale[1]), float(scale[2]),
    )
    mapping.vector_type = str(vector_type).upper()
    wnt.links.new(tc.outputs["Generated"], mapping.inputs["Vector"])
    wnt.links.new(mapping.outputs["Vector"], vec_in)
    print(
        "QUANTTRACE_SLICE2AV_WORLD mapping",
        "vector_type", mapping.vector_type,
        f"loc={tuple(location)} rot_z={rotation_z} scale={tuple(scale)}",
        "vec_linked", vec_in.is_linked,
    )
    return mapping


def build_slice2av_scene(
    image_path="/tmp/qt_slice2av_env.exr",
    *,
    mode="point",
    strength=1.0,
    scale=(1.0, 1.0, 1.0),
    location=(0.15, 0.0, 0.0),
    rotation_z=0.7,
    env_path="/tmp/qt_slice2av_env.exr",
):
    """Locked cube + AREA; Mapping POINT → Env Vector (+ regressions).

    mode:
      point          — TEX_COORD Generated → Mapping(POINT, loc, rot) → Env. CLAIM.
      point_identity — POINT loc=0 rot=0 scale=1 (loft EasyHDR Mapping ops).
      vector         — Slice 2ac Mapping(VECTOR) identity.
      texture        — Mapping TEXTURE (must refuse).
      env_mul0 / math_nest3 / hdr / rgb / rgb_mix / rgb_curves / nishita / teximage
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_slice2aa_scene as sc2aa
    import _quanttrace_slice2ac_scene as sc2ac
    import _quanttrace_slice2au_scene as sc2au

    mode_key = str(mode).strip().lower()
    allowed = (
        "point", "point_identity", "vector", "texture",
        "env_mul0", "math_nest3", "hdr", "rgb", "rgb_mix", "rgb_curves",
        "nishita", "teximage",
    )
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2av)")

    if mode_key == "env_mul0":
        return sc2au.build_slice2au_scene(
            image_path=env_path, mode="env_mul0", strength=0.0,
            pull_camera=True, env_path=env_path,
        )
    if mode_key == "math_nest3":
        return sc2au.build_slice2au_scene(
            image_path=env_path, mode="math_nest3", strength=0.7,
            pull_camera=True, env_path=env_path,
        )
    if mode_key == "hdr":
        return sc2au.build_slice2au_scene(
            image_path=env_path, mode="hdr", strength=1.0,
            pull_camera=True, env_path=env_path,
        )
    if mode_key == "rgb":
        return sc2au.build_slice2au_scene(
            image_path=env_path, mode="rgb", strength=1.0,
            pull_camera=True, env_path=env_path,
        )
    if mode_key == "rgb_mix":
        return sc2au.build_slice2au_scene(
            image_path=env_path, mode="rgb_mix", strength=1.0,
            pull_camera=True, env_path=env_path,
        )
    if mode_key == "rgb_curves":
        return sc2au.build_slice2au_scene(
            image_path=env_path, mode="rgb_curves", strength=1.0,
            pull_camera=True, env_path=env_path,
        )
    if mode_key == "nishita":
        return sc2au.build_slice2au_scene(
            image_path=env_path, mode="nishita", strength=1.0,
            pull_camera=True, env_path=env_path,
        )
    if mode_key == "teximage":
        return sc2au.build_slice2au_scene(
            image_path=env_path, mode="teximage", strength=1.0,
            pull_camera=True, env_path=env_path,
        )
    if mode_key == "vector":
        scene, cube_obj, lamp, cam, img = sc2ac.build_slice2ac_scene(
            image_path=image_path,
            mode="mapping",
            projection="EQUIRECTANGULAR",
            strength=strength,
            scale=scale,
            location=(0.0, 0.0, 0.0),
            rotation_z=rotation_z,
        )
        _pin_persistent_off(scene)
        return scene, cube_obj, lamp, cam, img

    scene, cube_obj, lamp, cam, img = sc2aa.build_slice2aa_scene(
        image_path=image_path,
        projection="EQUIRECTANGULAR",
        strength=strength,
        black_world=False,
    )
    _pin_persistent_off(scene)
    world = scene.world
    wnt = world.node_tree
    env = next(n for n in wnt.nodes if n.type == "TEX_ENVIRONMENT")

    if mode_key == "point_identity":
        _wire_env_mapping(
            wnt, env, vector_type="POINT",
            location=(0.0, 0.0, 0.0), rotation_z=0.0, scale=(1.0, 1.0, 1.0),
        )
    elif mode_key == "texture":
        _wire_env_mapping(
            wnt, env, vector_type="TEXTURE",
            location=location, rotation_z=rotation_z, scale=scale,
        )
    else:
        _wire_env_mapping(
            wnt, env, vector_type="POINT",
            location=location, rotation_z=rotation_z, scale=scale,
        )

    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="/tmp/quanttrace_slice2av_stock.exr")
    p.add_argument("--image", default="/tmp/qt_slice2av_env.exr")
    p.add_argument(
        "--mode",
        choices=(
            "point", "point_identity", "vector", "texture",
            "env_mul0", "math_nest3", "hdr", "rgb", "rgb_mix", "rgb_curves",
            "nishita", "teximage",
        ),
        default="point",
    )
    p.add_argument("--strength", type=float, default=1.0)
    p.add_argument("--scale", type=float, nargs=3, default=(1.0, 1.0, 1.0))
    p.add_argument("--location", type=float, nargs=3, default=(0.15, 0.0, 0.0))
    p.add_argument("--rotation-z", type=float, default=0.7)
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    args = p.parse_args(_argv())
    scene, *_rest = build_slice2av_scene(
        image_path=args.image,
        mode=args.mode,
        strength=args.strength,
        scale=tuple(args.scale),
        location=tuple(args.location),
        rotation_z=args.rotation_z,
        env_path=args.image,
    )
    scene.render.resolution_x = scene.render.resolution_y = args.res
    scene.cycles.samples = args.samples
    scene.render.filepath = args.out
    bpy.ops.render.render(write_still=True)
    print("QUANTTRACE_SLICE2AV_STOCK", args.out)


if __name__ == "__main__":
    main()
