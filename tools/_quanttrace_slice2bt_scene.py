# QuantTrace Slice 2bt: nested2 Mix <- Add+Glossy/SSS (loft Mix.004).
from __future__ import annotations
import argparse, os, sys
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1 :] if "--" in a else []


def build_slice2bt_scene(
    image_path="/tmp/qt_slice2bt_env.exr",
    *,
    mode="claim",
):
    """Locked cube + backplate; nested2 CLAIM + 2bp identity.

    mode:
      claim            — Outer MATH + Mix.005 Is Shadow + Mix.004 Fac←ColorRamp
                         (loft ColorRamp.002 stops, Fac←MATH) Shader=Add
                         (Glossy GGX unlinked + Transparent) Shader_001=Glass
      ramp             — 2br identity: ColorRamp Fac unlinked, Glass+Transparent
      nested2          — 2bq identity: Mix.004 Fac unlinked 0.35 Glass+Transparent
      nested_mix       — 2bp identity: Outer MATH + Inner Is Shadow Glass+Transparent
      glass_only       — 2bm identity
      mix / invert / bump_sep / hdr — prior regressions
      refuse_noise     — ColorRamp.Fac←Noise named REFUSE Slice 2bt
      refuse_add       — Mix.004 ← Add(Mix, Glossy) named REFUSE Slice 2bt
      refuse_third     — third Mix hop named REFUSE Slice 2bt
      refuse_linked    — Glass.Color linked REFUSE Slice 2bt
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)

    mode_key = str(mode).strip().lower()
    allowed = (
        "claim", "ramp", "nested2", "nested_mix", "glass_only",
        "mix", "invert", "bump_sep", "hdr",
        "refuse_noise", "refuse_add", "refuse_third", "refuse_linked",
    )
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2bt)")

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

    if mode_key == "nested_mix":
        # 2bp identity: Outer MATH + Inner Is Shadow Glass+Transparent (no Mix.004)
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

    def _loft_colorramp(*, math_fac=False):
        # Census loft ColorRamp.002: LINEAR RGB, 2 stops 0.387 black / 0.877 white.
        # math_fac: Fac <- MATH MULTIPLY(Backfacing, HueSat Color<-Ray Length).
        ramp = nt.nodes.new("ShaderNodeValToRGB")
        cr = ramp.color_ramp
        cr.interpolation = "LINEAR"
        els = cr.elements
        while len(els) > 2:
            els.remove(els[-1])
        while len(els) < 2:
            els.new(0.5)
        els[0].position = 0.3874170780181885
        els[0].color = (0.0, 0.0, 0.0, 1.0)
        els[1].position = 0.8774834871292114
        els[1].color = (1.0, 1.0, 1.0, 1.0)
        fac = ramp.inputs.get("Fac") or ramp.inputs.get("Factor")
        if fac is not None:
            fac.default_value = 0.5
        if math_fac:
            geom = nt.nodes.new("ShaderNodeNewGeometry")
            hsv = nt.nodes.new("ShaderNodeHueSaturation")
            hsv.inputs["Hue"].default_value = 0.5
            hsv.inputs["Saturation"].default_value = 1.0
            hsv.inputs["Value"].default_value = 2.0
            fac_h = hsv.inputs.get("Fac") or hsv.inputs.get("Factor")
            if fac_h is not None:
                fac_h.default_value = 1.0
            lp_rl = nt.nodes.new("ShaderNodeLightPath")
            nt.links.new(lp_rl.outputs["Ray Length"], hsv.inputs["Color"])
            mul = nt.nodes.new("ShaderNodeMath")
            mul.operation = "MULTIPLY"
            mul.use_clamp = False
            nt.links.new(geom.outputs["Backfacing"], mul.inputs[0])
            nt.links.new(hsv.outputs["Color"], mul.inputs[1])
            if fac is not None:
                nt.links.new(mul.outputs["Value"], fac)
        return ramp

    def _mk_glossy(rough=0.05, color=(1.0, 1.0, 1.0, 1.0), dist="GGX"):
        g = nt.nodes.new("ShaderNodeBsdfGlossy")
        g.distribution = dist
        g.inputs["Color"].default_value = color
        g.inputs["Roughness"].default_value = rough
        return g

    def _add_socks(add):
        s0 = add.inputs.get("Shader") or add.inputs[0]
        s1 = add.inputs.get("Shader_001") or add.inputs[1]
        return s0, s1

    if mode_key == "claim":
        # Outer MATH + Mix.005 Is Shadow + Mix.004 Fac<-ColorRamp (loft stops)
        # Shader=Add(Glossy GGX unlinked + Transparent) Shader_001=Glass.
        # ColorRamp.Fac <- MATH Backfacing x HueSat.
        lp = nt.nodes.new("ShaderNodeLightPath")
        deep = nt.nodes.new("ShaderNodeMixShader")
        ramp = _loft_colorramp(math_fac=True)
        nt.links.new(ramp.outputs["Color"], _fac_sock(deep))
        add = nt.nodes.new("ShaderNodeAddShader")
        a0, a1 = _add_socks(add)
        nt.links.new(_mk_glossy().outputs["BSDF"], a0)
        nt.links.new(_mk_trans().outputs["BSDF"], a1)
        nt.links.new(add.outputs["Shader"], _sh0(deep))
        nt.links.new(_mk_glass().outputs["BSDF"], _sh1(deep))
        inner = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(lp.outputs["Is Shadow Ray"], _fac_sock(inner))
        nt.links.new(deep.outputs["Shader"], _sh0(inner))
        nt.links.new(_mk_trans().outputs["BSDF"], _sh1(inner))
        outer = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(_loft_math_fac(), _fac_sock(outer))
        nt.links.new(inner.outputs["Shader"], _sh0(outer))
        nt.links.new(_mk_trans().outputs["BSDF"], _sh1(outer))
        nt.links.new(outer.outputs["Shader"], out.inputs["Surface"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key == "ramp":
        # 2br identity: ColorRamp Fac unlinked (no MATH) — bit-identical.
        lp = nt.nodes.new("ShaderNodeLightPath")
        deep = nt.nodes.new("ShaderNodeMixShader")
        ramp = _loft_colorramp(math_fac=False)
        nt.links.new(ramp.outputs["Color"], _fac_sock(deep))
        nt.links.new(_mk_glass().outputs["BSDF"], _sh0(deep))
        nt.links.new(_mk_trans().outputs["BSDF"], _sh1(deep))
        inner = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(lp.outputs["Is Shadow Ray"], _fac_sock(inner))
        nt.links.new(deep.outputs["Shader"], _sh0(inner))
        nt.links.new(_mk_trans().outputs["BSDF"], _sh1(inner))
        outer = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(_loft_math_fac(), _fac_sock(outer))
        nt.links.new(inner.outputs["Shader"], _sh0(outer))
        nt.links.new(_mk_trans().outputs["BSDF"], _sh1(outer))
        nt.links.new(outer.outputs["Shader"], out.inputs["Surface"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key == "nested2":
        # 2bq identity: Mix.004 Fac unlinked 0.35 (no ColorRamp) — bit-identical.
        lp = nt.nodes.new("ShaderNodeLightPath")
        deep = nt.nodes.new("ShaderNodeMixShader")
        _fac_sock(deep).default_value = 0.35
        nt.links.new(_mk_glass().outputs["BSDF"], _sh0(deep))
        nt.links.new(_mk_trans().outputs["BSDF"], _sh1(deep))
        inner = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(lp.outputs["Is Shadow Ray"], _fac_sock(inner))
        nt.links.new(deep.outputs["Shader"], _sh0(inner))
        nt.links.new(_mk_trans().outputs["BSDF"], _sh1(inner))
        outer = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(_loft_math_fac(), _fac_sock(outer))
        nt.links.new(inner.outputs["Shader"], _sh0(outer))
        nt.links.new(_mk_trans().outputs["BSDF"], _sh1(outer))
        nt.links.new(outer.outputs["Shader"], out.inputs["Surface"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key == "refuse_noise":
        ramp = _loft_colorramp()
        noise = nt.nodes.new("ShaderNodeTexNoise")
        fac = ramp.inputs.get("Fac") or ramp.inputs.get("Factor")
        nt.links.new(noise.outputs["Fac"], fac)
        deep = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(ramp.outputs["Color"], _fac_sock(deep))
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
        # Loft leftover: Add children Mix.002 / Mix.003 — Mix under Add.
        inner_mix = nt.nodes.new("ShaderNodeMixShader")
        _fac_sock(inner_mix).default_value = 0.5
        nt.links.new(_mk_glass().outputs["BSDF"], _sh0(inner_mix))
        nt.links.new(_mk_trans().outputs["BSDF"], _sh1(inner_mix))
        glossy = nt.nodes.new("ShaderNodeBsdfGlossy")
        add = nt.nodes.new("ShaderNodeAddShader")
        a0 = add.inputs.get("Shader") or add.inputs[0]
        a1 = add.inputs.get("Shader_001") or add.inputs[1]
        nt.links.new(inner_mix.outputs["Shader"], a0)
        nt.links.new(glossy.outputs["BSDF"], a1)
        deep = nt.nodes.new("ShaderNodeMixShader")
        _fac_sock(deep).default_value = 0.35
        nt.links.new(add.outputs["Shader"], _sh0(deep))
        nt.links.new(_mk_glass().outputs["BSDF"], _sh1(deep))
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

    if mode_key == "refuse_third":
        third = nt.nodes.new("ShaderNodeMixShader")
        _fac_sock(third).default_value = 0.5
        nt.links.new(_mk_glass().outputs["BSDF"], _sh0(third))
        nt.links.new(_mk_trans().outputs["BSDF"], _sh1(third))
        deep = nt.nodes.new("ShaderNodeMixShader")
        _fac_sock(deep).default_value = 0.35
        nt.links.new(third.outputs["Shader"], _sh0(deep))
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

    if mode_key == "refuse_linked":
        glass = _mk_glass()
        rgb = nt.nodes.new("ShaderNodeRGB")
        rgb.outputs[0].default_value = (1.0, 0.2, 0.1, 1.0)
        nt.links.new(rgb.outputs[0], glass.inputs["Color"])
        deep = nt.nodes.new("ShaderNodeMixShader")
        _fac_sock(deep).default_value = 0.35
        nt.links.new(glass.outputs["BSDF"], _sh0(deep))
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

    raise RuntimeError(f"unhandled mode={mode_key}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", default="claim")
    p.add_argument("--image", default="/tmp/qt_slice2bt_env.exr")
    args = p.parse_args(_argv())
    build_slice2bt_scene(image_path=args.image, mode=args.mode)
    print("QUANTTRACE_SLICE2BR_SCENE", args.mode)


if __name__ == "__main__":
    main()
