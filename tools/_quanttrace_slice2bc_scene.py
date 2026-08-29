# QuantTrace Slice 2bc: Noise Texture -> Bump.Height -> Principled.Normal.
from __future__ import annotations
import argparse, os, sys
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1 :] if "--" in a else []


def build_slice2bc_scene(
    image_path="/tmp/qt_slice2bc_height.png",
    *,
    mode="noise",
):
    """Locked cube; Noise -> Bump.Height -> Principled.Normal.

    mode:
      noise          — CLAIM: loft Plane Noise (Scale 150 / Detail 16 / Dist 0.2)
                       Color -> Bump.Height -> Principled.Normal
      noise_fac      — same Noise Factor -> Bump.Height
      bump           — 2x regression: Bump Height <- TEX_IMAGE
      vector_linked  — TEX_COORD -> Noise Vector (named REFUSE)
      mapping        — non-identity texture_mapping scale (named REFUSE)
      scale_linked   — Value -> Noise Scale (named REFUSE)
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)

    mode_key = str(mode).strip().lower()
    allowed = (
        "noise", "noise_fac", "bump",
        "vector_linked", "mapping", "scale_linked",
    )
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2bc)")

    if mode_key == "bump":
        import _quanttrace_slice2x_scene as sc2x
        return sc2x.build_slice2x_scene(image_path=image_path, socket="Bump")

    import _quanttrace_cube_scene as cube
    import _quanttrace_slice2bb_scene as sc2bb

    scene, cube_obj, lamp, cam = cube.build_locked_scene()
    mat = cube_obj.data.materials[0]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.7, 0.7, 0.7, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.5
    bsdf.inputs["Metallic"].default_value = 0.0

    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.label = "qt_noise_bump"
    sc2bb._apply_plane_noise(noise)

    bump = nt.nodes.new("ShaderNodeBump")
    bump.label = "qt_bump"
    bump.invert = False

    if mode_key == "vector_linked":
        tc = nt.nodes.new("ShaderNodeTexCoord")
        tc.label = "qt_noise_vec"
        nt.links.new(tc.outputs["Generated"], noise.inputs["Vector"])
        out_name = "Color" if "Color" in noise.outputs else "Fac"
        nt.links.new(noise.outputs[out_name], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, None

    if mode_key == "mapping":
        tm = getattr(noise, "texture_mapping", None)
        if tm is not None:
            tm.scale = (2.0, 2.0, 2.0)
        out_name = "Color" if "Color" in noise.outputs else "Fac"
        nt.links.new(noise.outputs[out_name], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, None

    if mode_key == "scale_linked":
        val = nt.nodes.new("ShaderNodeValue")
        val.label = "qt_noise_scale"
        val.outputs[0].default_value = 150.0
        scale_in = None
        getter = getattr(noise.inputs, "get", None)
        if callable(getter):
            scale_in = getter("Scale")
        if scale_in is None:
            for s in noise.inputs:
                if getattr(s, "name", None) == "Scale" or getattr(s, "identifier", None) == "Scale":
                    scale_in = s
                    break
        if scale_in is None:
            raise RuntimeError("Noise Scale input missing")
        nt.links.new(val.outputs[0], scale_in)
        out_name = "Color" if "Color" in noise.outputs else "Fac"
        nt.links.new(noise.outputs[out_name], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, None

    out_name = "Fac" if mode_key == "noise_fac" else "Color"
    if out_name not in noise.outputs:
        out_name = "Factor" if mode_key == "noise_fac" else "Color"
    nt.links.new(noise.outputs[out_name], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, None


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--mode",
        default="noise",
        choices=(
            "noise", "noise_fac", "bump",
            "vector_linked", "mapping", "scale_linked",
        ),
    )
    p.add_argument("--image", default="/tmp/qt_slice2bc_height.png")
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2bc_stock.exr")
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2bc_scene(
        image_path=args.image, mode=args.mode,
    )
    print("QUANTTRACE_SLICE2BC", cube_obj.name, "mode", args.mode)
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2BC wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
