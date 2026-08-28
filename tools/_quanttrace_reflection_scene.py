# QuantTrace Slice 2n: locked cube + TEX_COORD Reflection [→ Mapping] → TEX_IMAGE.
from __future__ import annotations
import argparse, os, sys
import bpy

def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def build_reflection_scene(
    image_path="/tmp/qt_checker_refl.png",
    *,
    use_mapping=False,
    scale=(2.0, 2.0, 2.0),
    location=(0.1, 0.2, 0.0),
    rotation_z=0.15,
):
    """TEX_COORD Reflection [→ Mapping VECTOR] → TEX_IMAGE Vector → Base Color."""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_mapping_scene as mapsc
    return mapsc.build_mapping_scene(
        image_path=image_path,
        use_mapping=use_mapping,
        use_texcoord=True,
        scale=scale,
        location=location,
        rotation_z=rotation_z,
        coord="Reflection",
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_refl_stock.exr")
    p.add_argument("--image", default="/tmp/qt_checker_refl.png")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--mode", choices=("texcoord", "mapping"), default="texcoord")
    p.add_argument("--scale", type=float, nargs=3, default=(2.0, 2.0, 2.0))
    p.add_argument("--location", type=float, nargs=3, default=(0.1, 0.2, 0.0))
    p.add_argument("--rotation-z", type=float, default=0.15)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_reflection_scene(
        image_path=args.image,
        use_mapping=(args.mode == "mapping"),
        scale=tuple(args.scale),
        location=tuple(args.location),
        rotation_z=args.rotation_z,
    )
    print(
        "QUANTTRACE_REFL", cube_obj.name, "mode", args.mode,
        "image", img.filepath, "uvs", len(cube_obj.data.uv_layers),
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_REFL wrote", args.out)
    return 0

if __name__ == "__main__":
    raise SystemExit(main() or 0)
