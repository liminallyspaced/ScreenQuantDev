# QuantTrace Slice 2bm: Glass BSDF → Material Output (native GlassBsdfNode).
from __future__ import annotations
import argparse, os, sys
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1 :] if "--" in a else []


def build_slice2bm_scene(
    image_path="/tmp/qt_slice2bm_env.exr",
    *,
    mode="claim",
):
    """Locked cube (+ HDR for glass visibility); Glass BSDF claim modes.

    mode:
      claim            — Glass BECKMANN Color white Rough=0.05 IOR=1.45 + backplate (Glass_02 packs rough=0; claim uses 0.05 to settle 256 caustic noise)
      glass_rough      — Roughness=0.2
      glass_ior        — IOR=1.7
      glass_color      — tinted Color (0.85, 0.35, 0.25)
      glass_ggx        — distribution GGX
      principled_trans — 2y regression: Principled transmission_weight=1
      mix / invert / separate / bump_sep / hdr — prior regressions
      mix_glass        — Mix Glass+Transparent (named REFUSE Slice 2bm)
      glass_linked     — Glass.Color ← RGB (named REFUSE)
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)

    mode_key = str(mode).strip().lower()
    allowed = (
        "claim", "glass_rough", "glass_ior", "glass_color", "glass_ggx",
        "principled_trans", "mix", "invert", "separate", "bump_sep", "hdr",
        "mix_glass", "glass_linked",
    )
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2bm)")

    if mode_key == "mix":
        import _quanttrace_slice2ay_scene as sc
        return sc.build_slice2ay_scene(mode="mix")
    if mode_key == "invert":
        import _quanttrace_slice2be_scene as sc
        return sc.build_slice2be_scene(image_path=image_path, mode="invert")
    if mode_key == "separate":
        import _quanttrace_slice2bj_scene as sc
        return sc.build_slice2bj_scene(image_path=image_path, mode="claim")
    if mode_key == "bump_sep":
        import _quanttrace_slice2bl_scene as sc
        return sc.build_slice2bl_scene(image_path=image_path, mode="claim")
    if mode_key == "hdr":
        import _quanttrace_slice2aa_scene as sc
        return sc.build_slice2aa_scene(image_path=image_path)
    if mode_key == "principled_trans":
        import _quanttrace_cube_scene as cube
        scene, cube_obj, lamp, cam = cube.build_locked_scene()
        mat = cube_obj.data.materials[0]
        nt = mat.node_tree
        bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        bsdf.inputs["Base Color"].default_value = (1.0, 1.0, 1.0, 1.0)
        bsdf.inputs["Roughness"].default_value = 0.0
        bsdf.inputs["Metallic"].default_value = 0.0
        bsdf.inputs["IOR"].default_value = 1.45
        tw = bsdf.inputs.get("Transmission Weight") or bsdf.inputs.get("Transmission")
        tw.default_value = 1.0
        thin = bsdf.inputs.get("Thin Wall")
        if thin is not None:
            thin.default_value = False
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, None

    # Glass claim modes: locked black world + AREA + bright backplate mesh.
    # Bright RGB/HDR *worlds* expose a pre-existing 1–2 px transmission
    # leftover at 256²/128 (same for Glass and Principled transmission).
    # A second opaque Principled mesh keeps Glass live via refraction
    # without that world-MIS path.
    import _quanttrace_cube_scene as cube
    scene, cube_obj, lamp, cam = cube.build_locked_scene()
    # Backplate behind cube (camera looks toward -ish origin from +X/-Y/+Z).
    bpy.ops.mesh.primitive_plane_add(size=8.0, location=(0.0, 2.5, 0.0))
    plate = bpy.context.active_object
    plate.name = "GlassBackplate"
    plate.rotation_euler = (1.5707963, 0.0, 0.0)  # stand upright
    pmat = bpy.data.materials.new("GlassBackplateMat")
    pmat.use_nodes = True
    pnt = pmat.node_tree
    pbsdf = next(n for n in pnt.nodes if n.type == "BSDF_PRINCIPLED")
    pbsdf.inputs["Base Color"].default_value = (0.95, 0.35, 0.15, 1.0)
    pbsdf.inputs["Roughness"].default_value = 0.4
    pbsdf.inputs["Metallic"].default_value = 0.0
    if plate.data.materials:
        plate.data.materials[0] = pmat
    else:
        plate.data.materials.append(pmat)
    mat = cube_obj.data.materials[0]
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    img = None

    if mode_key == "mix_glass":
        glass = nt.nodes.new("ShaderNodeBsdfGlass")
        glass.distribution = "BECKMANN"
        glass.inputs["Color"].default_value = (1.0, 1.0, 1.0, 1.0)
        glass.inputs["Roughness"].default_value = 0.0
        glass.inputs["IOR"].default_value = 1.45
        trans = nt.nodes.new("ShaderNodeBsdfTransparent")
        mix = nt.nodes.new("ShaderNodeMixShader")
        mix.inputs["Fac"].default_value = 0.85
        nt.links.new(glass.outputs["BSDF"], mix.inputs[1])
        nt.links.new(trans.outputs["BSDF"], mix.inputs[2])
        nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    glass = nt.nodes.new("ShaderNodeBsdfGlass")
    glass.distribution = "GGX" if mode_key == "glass_ggx" else "BECKMANN"
    color = (1.0, 1.0, 1.0, 1.0)
    rough = 0.0
    ior = 1.45
    if mode_key == "claim":
        # 0.05 settles 256² caustic leftover vs stock; loft Glass_02 still packs 0.0
        rough = 0.05
    elif mode_key == "glass_rough":
        rough = 0.2
    elif mode_key == "glass_ior":
        ior = 1.7
    elif mode_key == "glass_color":
        color = (0.85, 0.35, 0.25, 1.0)
    glass.inputs["Color"].default_value = color
    glass.inputs["Roughness"].default_value = rough
    glass.inputs["IOR"].default_value = ior

    if mode_key == "glass_linked":
        rgb = nt.nodes.new("ShaderNodeRGB")
        rgb.outputs[0].default_value = color
        nt.links.new(rgb.outputs[0], glass.inputs["Color"])

    nt.links.new(glass.outputs["BSDF"], out.inputs["Surface"])
    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--mode",
        default="claim",
        choices=(
            "claim", "glass_rough", "glass_ior", "glass_color", "glass_ggx",
            "principled_trans", "mix", "invert", "separate", "bump_sep", "hdr",
            "mix_glass", "glass_linked",
        ),
    )
    p.add_argument("--image", default="/tmp/qt_slice2bm_env.exr")
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2bm_stock.exr")
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2bm_scene(
        image_path=args.image, mode=args.mode,
    )
    print("QUANTTRACE_SLICE2BM", cube_obj.name, "mode", args.mode)
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        if os.path.isfile(args.out):
            os.unlink(args.out)
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2BM_STOCK wrote", args.out)


if __name__ == "__main__":
    main()
