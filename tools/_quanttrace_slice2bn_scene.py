# QuantTrace Slice 2bn: Mix Shader Glass+Transparent (+ Light Path Fac).
from __future__ import annotations
import argparse, os, sys
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1 :] if "--" in a else []


def build_slice2bn_scene(
    image_path="/tmp/qt_slice2bn_env.exr",
    *,
    mode="claim",
):
    """Locked cube + backplate; Mix Glass+Transparent claim modes.

    mode:
      claim            — Mix Fac=0.85 Glass+Transparent (loft lente shape)
      lightpath_shadow — Fac←Light Path Is Shadow Ray, Glass+Transparent
      glass_only       — pure Glass identity skip (2bm)
      mix / invert / bump_sep / hdr — prior regressions
      refuse_nested    — Mix(Glass, Mix(...)) named REFUSE
      refuse_math_fac  — Mix Fac←Math named REFUSE
      refuse_linked    — Glass.Color linked named REFUSE
      refuse_add       — Mix Glass+Add named REFUSE
      live_bypass_hint — same as claim (smoke compares vs pure-Glass Session)
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)

    mode_key = str(mode).strip().lower()
    allowed = (
        "claim", "lightpath_shadow", "glass_only",
        "mix", "invert", "bump_sep", "hdr",
        "refuse_nested", "refuse_math_fac", "refuse_linked", "refuse_add",
        "live_bypass_hint",
    )
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2bn)")

    if mode_key == "mix":
        import _quanttrace_slice2ay_scene as sc
        return sc.build_slice2ay_scene(mode="mix")
    if mode_key == "invert":
        import _quanttrace_slice2be_scene as sc
        return sc.build_slice2be_scene(image_path=image_path, mode="invert")
    if mode_key == "bump_sep":
        import _quanttrace_slice2bl_scene as sc
        return sc.build_slice2bl_scene(image_path=image_path, mode="claim")
    if mode_key == "hdr":
        import _quanttrace_slice2aa_scene as sc
        return sc.build_slice2aa_scene(image_path=image_path)

    import _quanttrace_cube_scene as cube
    scene, cube_obj, lamp, cam = cube.build_locked_scene()
    bpy.ops.mesh.primitive_plane_add(size=8.0, location=(0.0, 2.5, 0.0))
    plate = bpy.context.active_object
    plate.name = "GlassBackplate"
    plate.rotation_euler = (1.5707963, 0.0, 0.0)
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

    def _mk_glass(rough=0.05, ior=1.45, color=(1.0, 1.0, 1.0, 1.0), dist="BECKMANN"):
        g = nt.nodes.new("ShaderNodeBsdfGlass")
        g.distribution = dist
        g.inputs["Color"].default_value = color
        g.inputs["Roughness"].default_value = rough
        g.inputs["IOR"].default_value = ior
        return g

    def _mk_trans(color=(1.0, 1.0, 1.0, 1.0)):
        t = nt.nodes.new("ShaderNodeBsdfTransparent")
        t.inputs["Color"].default_value = color
        return t

    def _link_mix(glass, trans, fac=0.85, fac_from=None):
        mix = nt.nodes.new("ShaderNodeMixShader")
        # Blender 5: Factor; older: Fac
        fac_sock = mix.inputs.get("Fac") or mix.inputs.get("Factor")
        if fac_from is not None:
            nt.links.new(fac_from, fac_sock)
        else:
            fac_sock.default_value = fac
        nt.links.new(glass.outputs["BSDF"], mix.inputs.get("Shader") or mix.inputs[1])
        nt.links.new(trans.outputs["BSDF"], mix.inputs.get("Shader_001") or mix.inputs[2])
        nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
        return mix

    if mode_key == "glass_only":
        glass = _mk_glass()
        nt.links.new(glass.outputs["BSDF"], out.inputs["Surface"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key in ("claim", "live_bypass_hint"):
        _link_mix(_mk_glass(), _mk_trans(), fac=0.85)
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key == "lightpath_shadow":
        lp = nt.nodes.new("ShaderNodeLightPath")
        _link_mix(_mk_glass(), _mk_trans(), fac_from=lp.outputs["Is Shadow Ray"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key == "refuse_nested":
        glass = _mk_glass()
        trans = _mk_trans()
        inner = nt.nodes.new("ShaderNodeMixShader")
        fac_i = inner.inputs.get("Fac") or inner.inputs.get("Factor")
        fac_i.default_value = 0.5
        nt.links.new(glass.outputs["BSDF"], inner.inputs.get("Shader") or inner.inputs[1])
        nt.links.new(trans.outputs["BSDF"], inner.inputs.get("Shader_001") or inner.inputs[2])
        outer = nt.nodes.new("ShaderNodeMixShader")
        fac_o = outer.inputs.get("Fac") or outer.inputs.get("Factor")
        fac_o.default_value = 0.5
        trans2 = _mk_trans()
        nt.links.new(inner.outputs["Shader"], outer.inputs.get("Shader") or outer.inputs[1])
        nt.links.new(trans2.outputs["BSDF"], outer.inputs.get("Shader_001") or outer.inputs[2])
        nt.links.new(outer.outputs["Shader"], out.inputs["Surface"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key == "refuse_math_fac":
        glass = _mk_glass()
        trans = _mk_trans()
        lp = nt.nodes.new("ShaderNodeLightPath")
        math = nt.nodes.new("ShaderNodeMath")
        math.operation = "ADD"
        nt.links.new(lp.outputs["Is Shadow Ray"], math.inputs[0])
        nt.links.new(lp.outputs["Is Reflection Ray"], math.inputs[1])
        _link_mix(glass, trans, fac_from=math.outputs["Value"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key == "refuse_linked":
        glass = _mk_glass()
        rgb = nt.nodes.new("ShaderNodeRGB")
        rgb.outputs[0].default_value = (1.0, 0.2, 0.1, 1.0)
        nt.links.new(rgb.outputs[0], glass.inputs["Color"])
        _link_mix(glass, _mk_trans(), fac=0.85)
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key == "refuse_add":
        glass = _mk_glass()
        glossy = nt.nodes.new("ShaderNodeBsdfGlossy")
        add = nt.nodes.new("ShaderNodeAddShader")
        nt.links.new(glass.outputs["BSDF"], add.inputs[0])
        nt.links.new(glossy.outputs["BSDF"], add.inputs[1])
        mix = nt.nodes.new("ShaderNodeMixShader")
        fac_sock = mix.inputs.get("Fac") or mix.inputs.get("Factor")
        fac_sock.default_value = 0.5
        trans = _mk_trans()
        nt.links.new(add.outputs["Shader"], mix.inputs.get("Shader") or mix.inputs[1])
        nt.links.new(trans.outputs["BSDF"], mix.inputs.get("Shader_001") or mix.inputs[2])
        nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    raise RuntimeError(f"unhandled mode {mode_key}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="claim")
    ap.add_argument("--image", default="/tmp/qt_slice2bn_env.exr")
    args = ap.parse_args(_argv())
    build_slice2bn_scene(image_path=args.image, mode=args.mode)
    print("SLICE2BN_SCENE_OK", args.mode)
