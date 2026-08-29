# QuantTrace Slice 2aj: Background Strength linked from ShaderNodeMix.
from __future__ import annotations
import argparse, os, sys
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def _expected_mix(fac, a, b) -> float:
    return float(a) * (1.0 - float(fac)) + float(b) * float(fac)


def build_slice2aj_scene(
    image_path="/tmp/qt_slice2aj_env.exr",
    *,
    mode="mix_float",
    projection="EQUIRECTANGULAR",
    strength=0.7,
    mix_fac=0.5,
    mix_a=0.4,
    mix_b=1.0,
    mul_a=0.5,
    mul_b=1.4,
):
    """Locked cube + Environment Texture Color, Mix/Math/Value → Strength.

    mode:
      mix_float    — Strength ← Mix FLOAT MIX(Value fac, Value a, Value b)
                     (defaults 0.5, 0.4, 1.0 → 0.7); sock default stays 1.0
      mix_unlinked — same Mix FLOAT, Factor/A/B unlinked defaults (no Value)
      mix_rgb      — Strength ← MixRGB MIX(Fac, Color1 grey a, Color2 grey b)
      mix_tex      — Strength ← Mix FLOAT A ← TEX_IMAGE (must refuse pack)
      math_mul     — Slice 2ai regression (Math MULTIPLY)
      value        — Slice 2ah regression (Strength ← ShaderNodeValue)
      unlinked     — Slice 2aa regression (unlinked Strength default)
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_slice2aa_scene as sc2aa
    import _quanttrace_slice2ai_scene as sc2ai

    mode_key = str(mode).strip().lower()
    allowed = (
        "mix_float", "mix_unlinked", "mix_rgb", "mix_tex",
        "math_mul", "value", "unlinked",
    )
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2aj)")

    if mode_key == "math_mul":
        return sc2ai.build_slice2ai_scene(
            image_path=image_path,
            mode="math_mul",
            projection=projection,
            strength=strength,
            mul_a=mul_a,
            mul_b=mul_b,
        )
    if mode_key == "value":
        return sc2ai.build_slice2ai_scene(
            image_path=image_path,
            mode="value",
            projection=projection,
            strength=strength,
        )
    if mode_key == "unlinked":
        return sc2ai.build_slice2ai_scene(
            image_path=image_path,
            mode="unlinked",
            projection=projection,
            strength=strength,
        )

    aa_strength = 1.0
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
    for link in list(str_in.links):
        wnt.links.remove(link)
    str_in.default_value = 1.0

    fac_v, a_v, b_v = float(mix_fac), float(mix_a), float(mix_b)
    expected = _expected_mix(fac_v, a_v, b_v)

    if mode_key == "mix_tex":
        mix = wnt.nodes.new("ShaderNodeMix")
        mix.data_type = "FLOAT"
        mix.blend_type = "MIX"
        mix.clamp_factor = True
        mix.clamp_result = False
        mix.label = "WorldStrengthMixTex"
        mix.location = (bg.location[0] - 220, bg.location[1] - 80)
        mix.inputs["Factor"].default_value = fac_v
        mix.inputs["A"].default_value = a_v
        mix.inputs["B"].default_value = b_v
        tex = wnt.nodes.new("ShaderNodeTexImage")
        tex.label = "WorldStrengthMixATex"
        tex.location = (mix.location[0] - 220, mix.location[1] + 40)
        if img is not None:
            tex.image = img
        wnt.links.new(tex.outputs["Color"], mix.inputs["A"])
        wnt.links.new(mix.outputs["Result"], str_in)
        print(
            "QUANTTRACE_SLICE2AJ_WORLD mode mix_tex",
            "fac", fac_v, "a_tex", getattr(img, "filepath", None),
            "b", b_v, "sock_default", float(str_in.default_value),
            "str_linked", bool(str_in.is_linked),
            "from", mix.type, "data_type", mix.data_type,
        )
    elif mode_key == "mix_rgb":
        mix = wnt.nodes.new("ShaderNodeMixRGB")
        mix.blend_type = "MIX"
        mix.use_clamp = False
        mix.label = "WorldStrengthMixRGB"
        mix.location = (bg.location[0] - 220, bg.location[1] - 80)
        mix.inputs["Fac"].default_value = fac_v
        mix.inputs["Color1"].default_value = (a_v, a_v, a_v, 1.0)
        mix.inputs["Color2"].default_value = (b_v, b_v, b_v, 1.0)
        wnt.links.new(mix.outputs["Color"], str_in)
        print(
            "QUANTTRACE_SLICE2AJ_WORLD mode mix_rgb",
            "fac", fac_v, "a", a_v, "b", b_v, "expected", expected,
            "sock_default", float(str_in.default_value),
            "str_linked", bool(str_in.is_linked),
            "from", mix.type,
        )
    else:
        mix = wnt.nodes.new("ShaderNodeMix")
        mix.data_type = "FLOAT"
        mix.blend_type = "MIX"
        mix.clamp_factor = True
        mix.clamp_result = False
        mix.label = "WorldStrengthMix"
        mix.location = (bg.location[0] - 220, bg.location[1] - 80)
        fac_in = mix.inputs["Factor"]
        a_in = mix.inputs["A"]
        b_in = mix.inputs["B"]
        fac_in.default_value = fac_v
        a_in.default_value = a_v
        b_in.default_value = b_v
        if mode_key == "mix_float":
            vf = wnt.nodes.new("ShaderNodeValue")
            vf.label = "WorldStrengthFac"
            vf.outputs[0].default_value = fac_v
            vf.location = (mix.location[0] - 200, mix.location[1] + 80)
            va = wnt.nodes.new("ShaderNodeValue")
            va.label = "WorldStrengthA"
            va.outputs[0].default_value = a_v
            va.location = (mix.location[0] - 200, mix.location[1] + 20)
            vb = wnt.nodes.new("ShaderNodeValue")
            vb.label = "WorldStrengthB"
            vb.outputs[0].default_value = b_v
            vb.location = (mix.location[0] - 200, mix.location[1] - 40)
            # Leave socket defaults at Mix RNA (Fac=1, A=0, B=0) after linking
            # so ignoring Value links cannot accidentally pack 0.7.
            fac_in.default_value = 1.0
            a_in.default_value = 0.0
            b_in.default_value = 0.0
            wnt.links.new(vf.outputs[0], fac_in)
            wnt.links.new(va.outputs[0], a_in)
            wnt.links.new(vb.outputs[0], b_in)
        wnt.links.new(mix.outputs["Result"], str_in)
        print(
            "QUANTTRACE_SLICE2AJ_WORLD mode", mode_key,
            "op", mix.blend_type, "data_type", mix.data_type,
            "fac", fac_v, "a", a_v, "b", b_v, "expected", expected,
            "sock_default", float(str_in.default_value),
            "str_linked", bool(str_in.is_linked),
            "from", mix.type,
            "fac_linked", bool(fac_in.is_linked),
            "a_linked", bool(a_in.is_linked),
        )

    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2aj_stock.exr")
    p.add_argument("--image", default="/tmp/qt_slice2aj_env.exr")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument(
        "--mode",
        choices=(
            "mix_float", "mix_unlinked", "mix_rgb", "mix_tex",
            "math_mul", "value", "unlinked",
        ),
        default="mix_float",
    )
    p.add_argument(
        "--projection",
        choices=("EQUIRECTANGULAR", "MIRROR_BALL"),
        default="EQUIRECTANGULAR",
    )
    p.add_argument("--strength", type=float, default=0.7)
    p.add_argument("--mix-fac", type=float, default=0.5)
    p.add_argument("--mix-a", type=float, default=0.4)
    p.add_argument("--mix-b", type=float, default=1.0)
    p.add_argument("--mul-a", type=float, default=0.5)
    p.add_argument("--mul-b", type=float, default=1.4)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2aj_scene(
        image_path=args.image,
        mode=args.mode,
        projection=args.projection,
        strength=args.strength,
        mix_fac=args.mix_fac,
        mix_a=args.mix_a,
        mix_b=args.mix_b,
        mul_a=args.mul_a,
        mul_b=args.mul_b,
    )
    print(
        "QUANTTRACE_SLICE2AJ", cube_obj.name, "mode", args.mode,
        "strength", args.strength,
        "image", getattr(img, "filepath", None),
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2AJ wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
