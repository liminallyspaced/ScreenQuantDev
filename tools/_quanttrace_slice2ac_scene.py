# QuantTrace Slice 2ac: locked cube + Environment Texture Vector (TEX_COORD / Mapping).
from __future__ import annotations
import argparse, os, sys
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def build_slice2ac_scene(
    image_path="/tmp/qt_slice2ac_env.exr",
    *,
    mode="generated",
    projection="EQUIRECTANGULAR",
    strength=1.0,
    scale=(1.0, 1.0, 1.0),
    location=(0.0, 0.0, 0.0),
    rotation_z=0.7,
):
    """Locked cube + world Environment Texture with linked Vector.

    mode:
      unlinked  — Slice 2aa regression (LINK_POSITION)
      generated — TEX_COORD Generated → Env Vector
      mapping   — TEX_COORD Generated → Mapping(VECTOR) → Env Vector
    Mapping uses non-identity rotation_z so Combined differs from unlinked.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_slice2aa_scene as sc2aa

    scene, cube_obj, lamp, cam, img = sc2aa.build_slice2aa_scene(
        image_path=image_path,
        projection=projection,
        strength=strength,
        black_world=False,
    )
    world = scene.world
    wnt = world.node_tree
    env = next(n for n in wnt.nodes if n.type == "TEX_ENVIRONMENT")
    vec_in = env.inputs["Vector"]
    for link in list(vec_in.links):
        wnt.links.remove(link)

    mode_key = str(mode).strip().lower()
    if mode_key == "unlinked":
        print(
            "QUANTTRACE_SLICE2AC_WORLD mode unlinked",
            "vec_linked", vec_in.is_linked,
        )
    elif mode_key in ("generated", "mapping"):
        tc = wnt.nodes.new("ShaderNodeTexCoord")
        tc.location = (-600, 200)
        coord_out = tc.outputs["Generated"]
        if mode_key == "mapping":
            mapping = wnt.nodes.new("ShaderNodeMapping")
            mapping.location = (-400, 200)
            mapping.inputs["Location"].default_value = (
                float(location[0]), float(location[1]), float(location[2]),
            )
            mapping.inputs["Rotation"].default_value = (0.0, 0.0, float(rotation_z))
            mapping.inputs["Scale"].default_value = (
                float(scale[0]), float(scale[1]), float(scale[2]),
            )
            mapping.vector_type = "VECTOR"
            wnt.links.new(coord_out, mapping.inputs["Vector"])
            wnt.links.new(mapping.outputs["Vector"], vec_in)
            print(
                "QUANTTRACE_SLICE2AC_WORLD mode mapping",
                f"loc={tuple(location)} rot_z={rotation_z} scale={tuple(scale)}",
                "vec_linked", vec_in.is_linked,
            )
        else:
            wnt.links.new(coord_out, vec_in)
            print(
                "QUANTTRACE_SLICE2AC_WORLD mode generated",
                "vec_linked", vec_in.is_linked,
            )
    else:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2ac)")

    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2ac_stock.exr")
    p.add_argument("--image", default="/tmp/qt_slice2ac_env.exr")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument(
        "--mode",
        choices=("generated", "mapping", "unlinked"),
        default="generated",
    )
    p.add_argument(
        "--projection",
        choices=("EQUIRECTANGULAR", "MIRROR_BALL"),
        default="EQUIRECTANGULAR",
    )
    p.add_argument("--strength", type=float, default=1.0)
    p.add_argument("--scale", type=float, nargs=3, default=(1.0, 1.0, 1.0))
    p.add_argument("--location", type=float, nargs=3, default=(0.0, 0.0, 0.0))
    p.add_argument("--rotation-z", type=float, default=0.7)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2ac_scene(
        image_path=args.image,
        mode=args.mode,
        projection=args.projection,
        strength=args.strength,
        scale=tuple(args.scale),
        location=tuple(args.location),
        rotation_z=args.rotation_z,
    )
    print(
        "QUANTTRACE_SLICE2AC", cube_obj.name,
        "mode", args.mode, "image", getattr(img, "filepath", None),
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2AC wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
