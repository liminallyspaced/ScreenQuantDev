# QuantTrace Slice 2z: locked cube + Normal Map Object/World space.
from __future__ import annotations
import argparse, os, sys
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def build_slice2z_scene(
    image_path="/tmp/qt_slice2z_normal.png",
    *,
    socket="Normal",
    space="OBJECT",
    strength=1.0,
    base_color=(0.7, 0.7, 0.7),
):
    """Locked cube; TEX_IMAGE Color -> Normal Map (space) -> Principled.

    socket: Normal | Bump | Tangent | CoatNormal
    space: TANGENT | OBJECT | WORLD  (Normal / CoatNormal only)
    Visibility: Roughness=0.5 Metallic=0 Strength=1.0 unlinked.
    Reuses the 16x16 Non-Color tangent-hill PNG from Slice 2j.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)

    sock = str(socket)
    if sock == "Bump":
        import _quanttrace_slice2x_scene as sc2x
        return sc2x.build_slice2x_scene(image_path=image_path, socket="Bump")
    if sock == "Tangent":
        import _quanttrace_normal_scene as nsc
        return nsc.build_normal_scene(image_path=image_path, strength=strength, base_color=base_color)

    import _quanttrace_cube_scene as cube
    import _quanttrace_normal_scene as nsc

    scene, cube_obj, lamp, cam = cube.build_locked_scene()
    img = nsc._write_tangent_normal_png(image_path)
    px = list(img.pixels)
    print(
        "QUANTTRACE_SLICE2Z_IMG", image_path, "size", list(img.size),
        "cs", img.colorspace_settings.name,
        "px_min", min(px), "px_max", max(px),
    )
    mat = cube_obj.data.materials[0]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (
        float(base_color[0]), float(base_color[1]), float(base_color[2]), 1.0,
    )
    bsdf.inputs["Roughness"].default_value = 0.5
    bsdf.inputs["Metallic"].default_value = 0.0
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = "Linear"
    tex.extension = "REPEAT"
    tex.projection = "FLAT"
    tex.label = "qt_slice2z_tex"
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    sp = str(space).upper()
    if sp not in ("TANGENT", "OBJECT", "WORLD"):
        raise RuntimeError(
            f"space={space!r} refused (Slice 2z: TANGENT/OBJECT/WORLD; "
            "BLENDER_OBJECT/BLENDER_WORLD not this hour)"
        )
    nmap.space = sp
    nmap.inputs["Strength"].default_value = float(strength)
    nmap.label = "qt_slice2z_nmap"
    nt.links.new(tex.outputs["Color"], nmap.inputs["Color"])
    if sock == "CoatNormal":
        nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Coat Normal"])
        cw = bsdf.inputs.get("Coat Weight")
        if cw is None:
            cw = bsdf.inputs.get("Coat")
        if cw is not None and not getattr(cw, "is_linked", False):
            cw.default_value = 1.0
    else:
        nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    bpy.context.view_layer.update()
    print(
        "QUANTTRACE_SLICE2Z_BSDF socket", sock, "space", nmap.space,
        "strength", nmap.inputs["Strength"].default_value,
        "str_linked", nmap.inputs["Strength"].is_linked,
        "rough", bsdf.inputs["Roughness"].default_value,
        "metal", bsdf.inputs["Metallic"].default_value,
    )
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2z_stock.exr")
    p.add_argument("--image", default="/tmp/qt_slice2z_normal.png")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument(
        "--socket",
        choices=("Normal", "Bump", "Tangent", "CoatNormal"),
        default="Normal",
    )
    p.add_argument(
        "--space",
        choices=("TANGENT", "OBJECT", "WORLD"),
        default="OBJECT",
    )
    p.add_argument("--strength", type=float, default=1.0)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2z_scene(
        image_path=args.image,
        socket=args.socket,
        space=args.space,
        strength=args.strength,
    )
    print(
        "QUANTTRACE_SLICE2Z", cube_obj.name,
        "socket", args.socket, "space", args.space,
        "image", getattr(img, "filepath", None) if img is not None else None,
        "strength", args.strength,
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2Z wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
