# QuantTrace Slice 2ab: locked cube + TEX_COORD Object-with-pointer → TEX_IMAGE.
# Empty (QT_TexEmpty) at a non-identity transform is the projector.
from __future__ import annotations
import argparse, os, sys
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def _make_tex_empty(scene, *, location=(0.5, 0.25, 0.0), rotation_z=0.4):
    """Empty is NOT a mesh — classify_scene must not export it."""
    empty = bpy.data.objects.new("QT_TexEmpty", None)
    empty.empty_display_type = "PLAIN_AXES"
    empty.location = (float(location[0]), float(location[1]), float(location[2]))
    empty.rotation_euler = (0.0, 0.0, float(rotation_z))
    scene.collection.objects.link(empty)
    return empty


def build_slice2ab_scene(
    image_path="/tmp/qt_checker_slice2ab.png",
    *,
    use_mapping=False,
    empty_ref=False,
    scale=(2.0, 2.0, 2.0),
    location=(0.1, 0.2, 0.0),
    rotation_z=0.15,
    empty_loc=(0.5, 0.25, 0.0),
    empty_rot_z=0.4,
):
    """TEX_COORD Object [→ Mapping VECTOR] → TEX_IMAGE Vector → Base Color.

    empty_ref=True: Slice 2l (tc.object=None, use_transform=0).
    empty_ref=False: tc.object = QT_TexEmpty at a non-identity transform.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_mapping_scene as mapsc

    empty = None
    scene, cube_obj, lamp, cam, img = mapsc.build_mapping_scene(
        image_path=image_path,
        use_mapping=use_mapping,
        use_texcoord=True,
        scale=scale,
        location=location,
        rotation_z=rotation_z,
        coord="Object",
        object_ref=None,
    )
    if not empty_ref:
        empty = _make_tex_empty(scene, location=empty_loc, rotation_z=empty_rot_z)
        mat = cube_obj.data.materials[0]
        tc = next(n for n in mat.node_tree.nodes if n.type == "TEX_COORD")
        tc.object = empty
        print(
            "QUANTTRACE_SLICE2AB empty", empty.name,
            "loc", tuple(empty.location),
            "rot_z", empty.rotation_euler[2],
            "type", empty.type,
        )
    else:
        print("QUANTTRACE_SLICE2AB empty-ref (2l) object=None")
    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img, empty


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2ab_stock.exr")
    p.add_argument("--image", default="/tmp/qt_checker_slice2ab.png")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--mode", choices=("texcoord", "mapping"), default="texcoord")
    p.add_argument("--empty-ref", action="store_true", default=False)
    p.add_argument("--scale", type=float, nargs=3, default=(2.0, 2.0, 2.0))
    p.add_argument("--location", type=float, nargs=3, default=(0.1, 0.2, 0.0))
    p.add_argument("--rotation-z", type=float, default=0.15)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img, empty = build_slice2ab_scene(
        image_path=args.image,
        use_mapping=(args.mode == "mapping"),
        empty_ref=args.empty_ref,
        scale=tuple(args.scale),
        location=tuple(args.location),
        rotation_z=args.rotation_z,
    )
    print(
        "QUANTTRACE_SLICE2AB", cube_obj.name, "mode", args.mode,
        "empty_ref", args.empty_ref,
        "empty", None if empty is None else empty.name,
        "image", img.filepath,
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2AB wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
