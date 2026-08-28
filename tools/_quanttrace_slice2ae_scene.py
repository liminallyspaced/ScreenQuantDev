# QuantTrace Slice 2ae: locked cube + Env TEX_COORD Object-with-pointer.
# Empty (QT_WorldEmpty) at a non-identity rotation is the projector.
# Default loc=(0,0,0): world/background Object+translate trips 1px HDR-MIS
# residue at 4spp on the sharp gradient (same MAE class); rot_z=0.4 is enough
# for live stock pointer vs empty_ref Δmax and use_transform=1.
from __future__ import annotations
import argparse, os, sys
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def _make_world_empty(scene, *, location=(0.5, 0.25, 0.0), rotation_z=0.4):
    """Empty is NOT a mesh — classify_scene must not export it."""
    empty = bpy.data.objects.new("QT_WorldEmpty", None)
    empty.empty_display_type = "PLAIN_AXES"
    empty.location = (float(location[0]), float(location[1]), float(location[2]))
    empty.rotation_euler = (0.0, 0.0, float(rotation_z))
    scene.collection.objects.link(empty)
    return empty


def build_slice2ae_scene(
    image_path="/tmp/qt_slice2ae_env.exr",
    *,
    mode="pointer",
    projection="EQUIRECTANGULAR",
    strength=1.0,
    scale=(1.0, 1.0, 1.0),
    location=(0.0, 0.0, 0.0),
    rotation_z=0.7,
    empty_loc=(0.0, 0.0, 0.0),
    empty_rot_z=0.4,
):
    """Locked cube + world Environment Texture with Object Vector.

    mode:
      pointer         — TEX_COORD Object (QT_WorldEmpty pointer) → Env Vector
      pointer_mapping — TEX_COORD Object → Mapping(VECTOR) → Env Vector
      empty_ref       — TEX_COORD Object with object=None (2ac regression)
      generated       — TEX_COORD Generated (cheap 2ac regression)
      unlinked        — Slice 2aa LINK_POSITION regression
    Mapping uses non-identity rotation_z so Combined can differ from empty_ref.
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

    empty = None
    mode_key = str(mode).strip().lower()
    if mode_key == "unlinked":
        print(
            "QUANTTRACE_SLICE2AE_WORLD mode unlinked",
            "vec_linked", vec_in.is_linked,
        )
    elif mode_key == "generated":
        tc = wnt.nodes.new("ShaderNodeTexCoord")
        tc.location = (-600, 200)
        wnt.links.new(tc.outputs["Generated"], vec_in)
        print(
            "QUANTTRACE_SLICE2AE_WORLD mode generated",
            "vec_linked", vec_in.is_linked,
        )
    elif mode_key in ("pointer", "pointer_mapping", "empty_ref"):
        tc = wnt.nodes.new("ShaderNodeTexCoord")
        tc.location = (-600, 200)
        if mode_key != "empty_ref":
            empty = _make_world_empty(
                scene, location=empty_loc, rotation_z=empty_rot_z,
            )
            tc.object = empty
            print(
                "QUANTTRACE_SLICE2AE empty", empty.name,
                "loc", tuple(empty.location),
                "rot_z", empty.rotation_euler[2],
                "type", empty.type,
            )
        else:
            tc.object = None
            print("QUANTTRACE_SLICE2AE empty-ref (2ac) object=None")
        coord_out = tc.outputs["Object"]
        if mode_key == "pointer_mapping":
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
                "QUANTTRACE_SLICE2AE_WORLD mode pointer_mapping",
                f"loc={tuple(location)} rot_z={rotation_z} scale={tuple(scale)}",
                "vec_linked", vec_in.is_linked,
            )
        else:
            wnt.links.new(coord_out, vec_in)
            print(
                "QUANTTRACE_SLICE2AE_WORLD mode", mode_key,
                "vec_linked", vec_in.is_linked,
            )
    else:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2ae)")

    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img, empty


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2ae_stock.exr")
    p.add_argument("--image", default="/tmp/qt_slice2ae_env.exr")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument(
        "--mode",
        choices=("pointer", "pointer_mapping", "empty_ref", "generated", "unlinked"),
        default="pointer",
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
    scene, cube_obj, lamp, cam, img, empty = build_slice2ae_scene(
        image_path=args.image,
        mode=args.mode,
        projection=args.projection,
        strength=args.strength,
        scale=tuple(args.scale),
        location=tuple(args.location),
        rotation_z=args.rotation_z,
    )
    print(
        "QUANTTRACE_SLICE2AE", cube_obj.name,
        "mode", args.mode,
        "empty", None if empty is None else empty.name,
        "image", getattr(img, "filepath", None),
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2AE wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
