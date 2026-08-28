# QuantTrace Slice 2y: locked cube + Principled Thin Wall BOOLEAN.
from __future__ import annotations
import argparse, os, sys
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def build_slice2y_scene(
    *,
    socket="ThinWall",
    thin_wall=True,
    transmission_weight=1.0,
    image_path="/tmp/qt_slice2x_height.png",
):
    """Locked cube; unlinked Thin Wall BOOLEAN, or 2x Bump regression.

    socket: ThinWall | Bump
    ThinWall pins Roughness=0.05 Metallic=0 IOR=1.45 Base ~0.8 gray.
    Transmission Weight unlinked (default 1.0). No textures.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)

    sock = str(socket)
    if sock == "Bump":
        import _quanttrace_slice2x_scene as sc2x
        return sc2x.build_slice2x_scene(image_path=image_path, socket="Bump")

    import _quanttrace_cube_scene as cube
    scene, cube_obj, lamp, cam = cube.build_locked_scene()
    mat = cube_obj.data.materials[0]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.8, 0.8, 0.8, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.05
    bsdf.inputs["Metallic"].default_value = 0.0
    bsdf.inputs["IOR"].default_value = 1.45
    tw = bsdf.inputs.get("Thin Wall")
    if tw is None:
        raise RuntimeError("Principled has no Thin Wall socket")
    if getattr(tw, "is_linked", False):
        raise RuntimeError("Thin Wall must stay unlinked")
    tw.default_value = bool(thin_wall)
    tr = bsdf.inputs.get("Transmission Weight")
    if tr is None:
        tr = bsdf.inputs.get("Transmission")
    if tr is None:
        raise RuntimeError("Principled has no Transmission Weight socket")
    if getattr(tr, "is_linked", False):
        raise RuntimeError("Transmission Weight must stay unlinked")
    tr.default_value = float(transmission_weight)
    bpy.context.view_layer.update()
    print(
        "QUANTTRACE_SLICE2Y_BSDF thin_wall", tw.default_value,
        "tw_linked", tw.is_linked,
        "trans", tr.default_value,
        "tr_linked", tr.is_linked,
        "rough", bsdf.inputs["Roughness"].default_value,
        "metal", bsdf.inputs["Metallic"].default_value,
        "ior", bsdf.inputs["IOR"].default_value,
    )
    return scene, cube_obj, lamp, cam, None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2y_stock.exr")
    p.add_argument("--image", default="/tmp/qt_slice2x_height.png")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument(
        "--socket",
        choices=("ThinWall", "Bump"),
        default="ThinWall",
    )
    p.add_argument(
        "--thin-wall",
        dest="thin_wall",
        choices=("0", "1", "false", "true", "False", "True"),
        default="1",
        help="Unlinked Thin Wall BOOLEAN (ThinWall socket only).",
    )
    p.add_argument("--transmission", type=float, default=1.0)
    args = p.parse_args(_argv())
    tw = str(args.thin_wall).lower() in ("1", "true")
    scene, cube_obj, lamp, cam, img = build_slice2y_scene(
        socket=args.socket,
        thin_wall=tw,
        transmission_weight=args.transmission,
        image_path=args.image,
    )
    print(
        "QUANTTRACE_SLICE2Y", cube_obj.name, "socket", args.socket,
        "thin_wall", tw, "transmission", args.transmission,
        "img", getattr(img, "filepath", None) if img is not None else None,
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2Y wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
