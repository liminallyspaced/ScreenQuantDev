# QuantTrace Slice 2ah: Background Strength linked from ShaderNodeValue.
from __future__ import annotations
import argparse, os, sys
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def build_slice2ah_scene(
    image_path="/tmp/qt_slice2ah_env.exr",
    *,
    mode="value",
    projection="EQUIRECTANGULAR",
    strength=0.7,
):
    """Locked cube + Environment Texture Color, optional Value → Strength.

    mode:
      value    — Strength ← ShaderNodeValue (socket default left at 1.0)
      unlinked — Slice 2aa regression (unlinked Strength default)
    Strength default 0.7 so live stock Value-linked vs unlinked 1.0 differs.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_slice2aa_scene as sc2aa

    mode_key = str(mode).strip().lower()
    if mode_key not in ("value", "unlinked"):
        raise RuntimeError(f"mode={mode!r} refused (Slice 2ah)")

    # 2aa writes unlinked Strength. For value mode keep socket default 1.0
    # so a packer that ignores the Value node would pack 1.0 and fail the gate.
    aa_strength = 1.0 if mode_key == "value" else float(strength)
    scene, cube_obj, lamp, cam, img = sc2aa.build_slice2aa_scene(
        image_path=image_path,
        projection=projection,
        strength=aa_strength,
        black_world=False,
    )
    world = scene.world
    wnt = world.node_tree
    bg = next(n for n in wnt.nodes if n.type == "BACKGROUND")
    str_in = bg.inputs["Strength"]

    if mode_key == "value":
        vnode = wnt.nodes.new("ShaderNodeValue")
        vnode.label = "WorldStrength"
        vnode.outputs[0].default_value = float(strength)
        vnode.location = (bg.location[0] - 220, bg.location[1] - 80)
        for link in list(str_in.links):
            wnt.links.remove(link)
        wnt.links.new(vnode.outputs[0], str_in)
        print(
            "QUANTTRACE_SLICE2AH_WORLD mode value",
            "value", float(strength),
            "sock_default", float(str_in.default_value),
            "str_linked", bool(str_in.is_linked),
            "from", vnode.type,
        )
    else:
        print(
            "QUANTTRACE_SLICE2AH_WORLD mode unlinked",
            "strength", float(str_in.default_value),
            "str_linked", bool(str_in.is_linked),
        )

    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2ah_stock.exr")
    p.add_argument("--image", default="/tmp/qt_slice2ah_env.exr")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--mode", choices=("value", "unlinked"), default="value")
    p.add_argument(
        "--projection",
        choices=("EQUIRECTANGULAR", "MIRROR_BALL"),
        default="EQUIRECTANGULAR",
    )
    p.add_argument("--strength", type=float, default=0.7)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2ah_scene(
        image_path=args.image,
        mode=args.mode,
        projection=args.projection,
        strength=args.strength,
    )
    print(
        "QUANTTRACE_SLICE2AH", cube_obj.name, "mode", args.mode,
        "strength", args.strength,
        "image", getattr(img, "filepath", None),
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2AH wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
