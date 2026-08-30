# QuantTrace Slice 2bp: nested Mix Shader hop (loft Realistic_Glass_01 shape).
from __future__ import annotations
import argparse, os, sys
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1 :] if "--" in a else []


def build_slice2bp_scene(
    image_path="/tmp/qt_slice2bp_env.exr",
    *,
    mode="claim",
):
    """Locked cube + backplate; nested Mix CLAIM + 2bo/2bn identity.

    mode:
      claim            — loft nested shape: Outer Mix Fac=MATH MAXIMUM(...)
                         Shader=Inner Mix Fac←Is Shadow (Glass+Transparent)
                         Shader_001=Transparent
      flat_math        — 2bo identity: flat Mix Fac MATH Glass+Transparent
      lightpath_shadow — 2bn identity: Fac←Is Shadow, no nest
      unlinked_fac     — 2bn identity: Fac=0.85 unlinked
      glass_only       — 2bm identity
      mix / invert / bump_sep / hdr — prior regressions
      refuse_deeper    — Outer→Inner→Mix again named REFUSE Slice 2bp
      refuse_add       — nested Mix ← Add Shader REFUSE
      refuse_tex_fac   — nested Mix Fac←TEX REFUSE
      refuse_linked    — Glass.Color linked REFUSE
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)

    mode_key = str(mode).strip().lower()
    allowed = (
        "claim", "flat_math", "lightpath_shadow", "unlinked_fac", "glass_only",
        "mix", "invert", "bump_sep", "hdr",
        "refuse_deeper", "refuse_add", "refuse_tex_fac", "refuse_linked",
    )
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2bp)")

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

    def _fac_sock(mix):
        return mix.inputs.get("Fac") or mix.inputs.get("Factor")

    def _sh0(mix):
        return mix.inputs.get("Shader") or mix.inputs[1]

    def _sh1(mix):
        return mix.inputs.get("Shader_001") or mix.inputs[2]

    def _loft_math_fac():
        lp = nt.nodes.new("ShaderNodeLightPath")
        inner = nt.nodes.new("ShaderNodeMath")
        inner.operation = "MAXIMUM"
        inner.use_clamp = False
        nt.links.new(lp.outputs["Is Shadow Ray"], inner.inputs[0])
        nt.links.new(lp.outputs["Is Reflection Ray"], inner.inputs[1])
        gt = nt.nodes.new("ShaderNodeMath")
        gt.operation = "GREATER_THAN"
        gt.use_clamp = False
        val = nt.nodes.new("ShaderNodeValue")
        val.outputs[0].default_value = 6.0
        nt.links.new(lp.outputs["Ray Depth"], gt.inputs[0])
        nt.links.new(val.outputs[0], gt.inputs[1])
        rootm = nt.nodes.new("ShaderNodeMath")
        rootm.operation = "MAXIMUM"
        rootm.use_clamp = False
        nt.links.new(inner.outputs["Value"], rootm.inputs[0])
        nt.links.new(gt.outputs["Value"], rootm.inputs[1])
        return rootm.outputs["Value"]

    if mode_key == "glass_only":
        glass = _mk_glass()
        nt.links.new(glass.outputs["BSDF"], out.inputs["Surface"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key == "unlinked_fac":
        mix = nt.nodes.new("ShaderNodeMixShader")
        _fac_sock(mix).default_value = 0.85
        nt.links.new(_mk_glass().outputs["BSDF"], _sh0(mix))
        nt.links.new(_mk_trans().outputs["BSDF"], _sh1(mix))
        nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key == "lightpath_shadow":
        lp = nt.nodes.new("ShaderNodeLightPath")
        mix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(lp.outputs["Is Shadow Ray"], _fac_sock(mix))
        nt.links.new(_mk_glass().outputs["BSDF"], _sh0(mix))
        nt.links.new(_mk_trans().outputs["BSDF"], _sh1(mix))
        nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key == "flat_math":
        mix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(_loft_math_fac(), _fac_sock(mix))
        nt.links.new(_mk_glass().outputs["BSDF"], _sh0(mix))
        nt.links.new(_mk_trans().outputs["BSDF"], _sh1(mix))
        nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key == "claim":
        # Loft Realistic_Glass_01 packable nested shape (census 2026-08-30 8am):
        # Outer Mix.006 Fac=MATH MAXIMUM(...); Shader=Inner Mix.005
        #   Fac←Is Shadow; Shader=Glass; Shader_001=Transparent
        # Shader_001=Transparent white.
        # (Loft Inner.Shader is Mix.004 ColorRamp — refuse_deeper / next slice.)
        lp = nt.nodes.new("ShaderNodeLightPath")
        inner = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(lp.outputs["Is Shadow Ray"], _fac_sock(inner))
        nt.links.new(_mk_glass().outputs["BSDF"], _sh0(inner))
        nt.links.new(_mk_trans().outputs["BSDF"], _sh1(inner))
        outer = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(_loft_math_fac(), _fac_sock(outer))
        nt.links.new(inner.outputs["Shader"], _sh0(outer))
        nt.links.new(_mk_trans().outputs["BSDF"], _sh1(outer))
        nt.links.new(outer.outputs["Shader"], out.inputs["Surface"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key == "refuse_deeper":
        # Outer → Inner → deeper Mix (loft Mix.004 shape stub)
        deep = nt.nodes.new("ShaderNodeMixShader")
        _fac_sock(deep).default_value = 0.5
        nt.links.new(_mk_glass().outputs["BSDF"], _sh0(deep))
        nt.links.new(_mk_trans().outputs["BSDF"], _sh1(deep))
        inner = nt.nodes.new("ShaderNodeMixShader")
        lp = nt.nodes.new("ShaderNodeLightPath")
        nt.links.new(lp.outputs["Is Shadow Ray"], _fac_sock(inner))
        nt.links.new(deep.outputs["Shader"], _sh0(inner))
        nt.links.new(_mk_trans().outputs["BSDF"], _sh1(inner))
        outer = nt.nodes.new("ShaderNodeMixShader")
        _fac_sock(outer).default_value = 0.5
        nt.links.new(inner.outputs["Shader"], _sh0(outer))
        nt.links.new(_mk_trans().outputs["BSDF"], _sh1(outer))
        nt.links.new(outer.outputs["Shader"], out.inputs["Surface"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key == "refuse_add":
        glossy = nt.nodes.new("ShaderNodeBsdfGlossy")
        add = nt.nodes.new("ShaderNodeAddShader")
        nt.links.new(_mk_glass().outputs["BSDF"], add.inputs[0])
        nt.links.new(glossy.outputs["BSDF"], add.inputs[1])
        inner = nt.nodes.new("ShaderNodeMixShader")
        lp = nt.nodes.new("ShaderNodeLightPath")
        nt.links.new(lp.outputs["Is Shadow Ray"], _fac_sock(inner))
        nt.links.new(add.outputs["Shader"], _sh0(inner))
        nt.links.new(_mk_trans().outputs["BSDF"], _sh1(inner))
        outer = nt.nodes.new("ShaderNodeMixShader")
        _fac_sock(outer).default_value = 0.5
        nt.links.new(inner.outputs["Shader"], _sh0(outer))
        nt.links.new(_mk_trans().outputs["BSDF"], _sh1(outer))
        nt.links.new(outer.outputs["Shader"], out.inputs["Surface"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key == "refuse_tex_fac":
        tex = nt.nodes.new("ShaderNodeTexImage")
        inner = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(tex.outputs.get("Color") or tex.outputs[0], _fac_sock(inner))
        nt.links.new(_mk_glass().outputs["BSDF"], _sh0(inner))
        nt.links.new(_mk_trans().outputs["BSDF"], _sh1(inner))
        outer = nt.nodes.new("ShaderNodeMixShader")
        _fac_sock(outer).default_value = 0.5
        nt.links.new(inner.outputs["Shader"], _sh0(outer))
        nt.links.new(_mk_trans().outputs["BSDF"], _sh1(outer))
        nt.links.new(outer.outputs["Shader"], out.inputs["Surface"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key == "refuse_linked":
        glass = _mk_glass()
        rgb = nt.nodes.new("ShaderNodeRGB")
        rgb.outputs[0].default_value = (1.0, 0.2, 0.1, 1.0)
        nt.links.new(rgb.outputs[0], glass.inputs["Color"])
        inner = nt.nodes.new("ShaderNodeMixShader")
        lp = nt.nodes.new("ShaderNodeLightPath")
        nt.links.new(lp.outputs["Is Shadow Ray"], _fac_sock(inner))
        nt.links.new(glass.outputs["BSDF"], _sh0(inner))
        nt.links.new(_mk_trans().outputs["BSDF"], _sh1(inner))
        outer = nt.nodes.new("ShaderNodeMixShader")
        _fac_sock(outer).default_value = 0.5
        nt.links.new(inner.outputs["Shader"], _sh0(outer))
        nt.links.new(_mk_trans().outputs["BSDF"], _sh1(outer))
        nt.links.new(outer.outputs["Shader"], out.inputs["Surface"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    raise RuntimeError(f"unhandled mode={mode_key}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", default="claim")
    p.add_argument("--image", default="/tmp/qt_slice2bp_env.exr")
    args = p.parse_args(_argv())
    build_slice2bp_scene(image_path=args.image, mode=args.mode)
    print("QUANTTRACE_SLICE2BP_SCENE", args.mode)


if __name__ == "__main__":
    main()
