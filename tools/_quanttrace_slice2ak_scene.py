# QuantTrace Slice 2ak: Background Strength linked from Map Range / Clamp.
from __future__ import annotations
import argparse, os, sys
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def _expected_map_range(value, from_min, from_max, to_min, to_max, clamp=True) -> float:
    if abs(float(from_max) - float(from_min)) < 1e-12:
        result = 0.0
    else:
        factor = (float(value) - float(from_min)) / (float(from_max) - float(from_min))
        result = float(to_min) + factor * (float(to_max) - float(to_min))
    if clamp:
        lo, hi = (float(to_max), float(to_min)) if float(to_min) > float(to_max) else (
            float(to_min), float(to_max)
        )
        result = min(hi, max(lo, result))
    return float(result)


def _expected_clamp(value, mn, mx) -> float:
    return float(min(float(mx), max(float(mn), float(value))))


def build_slice2ak_scene(
    image_path="/tmp/qt_slice2ak_env.exr",
    *,
    mode="map_range",
    projection="EQUIRECTANGULAR",
    strength=0.7,
    mix_fac=0.5,
    mix_a=0.4,
    mix_b=1.0,
    mul_a=0.5,
    mul_b=1.4,
    mr_value=0.25,
    mr_from_min=0.0,
    mr_from_max=1.0,
    mr_to_min=0.4,
    mr_to_max=1.6,
    clamp_value=1.5,
    clamp_min=0.2,
    clamp_max=0.7,
):
    """Locked cube + Environment Texture Color, Map Range/Clamp → Strength.

    mode:
      map_range  — Strength ← Map Range FLOAT LINEAR
                   Value 0.25, From 0..1, To 0.4..1.6 → 0.7; sock default 1.0
      clamp      — Strength ← Clamp MINMAX Value 1.5 Min 0.2 Max 0.7 → 0.7
      map_tex    — Map Range Value ← TEX_IMAGE (must refuse pack)
      mix_float  — Slice 2aj regression
      math_mul   — Slice 2ai regression
      value      — Slice 2ah regression
      unlinked   — Slice 2aa regression
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_slice2aa_scene as sc2aa
    import _quanttrace_slice2aj_scene as sc2aj
    import _quanttrace_slice2ai_scene as sc2ai

    mode_key = str(mode).strip().lower()
    allowed = (
        "map_range", "clamp", "map_tex",
        "mix_float", "math_mul", "value", "unlinked",
    )
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2ak)")

    if mode_key == "mix_float":
        return sc2aj.build_slice2aj_scene(
            image_path=image_path,
            mode="mix_float",
            projection=projection,
            strength=strength,
            mix_fac=mix_fac,
            mix_a=mix_a,
            mix_b=mix_b,
        )
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

    scene, cube_obj, lamp, cam, img = sc2aa.build_slice2aa_scene(
        image_path=image_path,
        projection=projection,
        strength=1.0,
        black_world=False,
    )
    world = scene.world
    wnt = world.node_tree
    bg = next(n for n in wnt.nodes if n.type == "BACKGROUND")
    str_in = bg.inputs["Strength"]
    for link in list(str_in.links):
        wnt.links.remove(link)
    str_in.default_value = 1.0

    if mode_key == "map_tex":
        mr = wnt.nodes.new("ShaderNodeMapRange")
        mr.data_type = "FLOAT"
        mr.interpolation_type = "LINEAR"
        mr.clamp = True
        mr.label = "WorldStrengthMapRangeTex"
        mr.location = (bg.location[0] - 240, bg.location[1] - 80)
        mr.inputs["Value"].default_value = float(mr_value)
        mr.inputs["From Min"].default_value = float(mr_from_min)
        mr.inputs["From Max"].default_value = float(mr_from_max)
        mr.inputs["To Min"].default_value = float(mr_to_min)
        mr.inputs["To Max"].default_value = float(mr_to_max)
        tex = wnt.nodes.new("ShaderNodeTexImage")
        tex.label = "WorldStrengthMapRangeValueTex"
        tex.location = (mr.location[0] - 220, mr.location[1] + 40)
        if img is not None:
            tex.image = img
        wnt.links.new(tex.outputs["Color"], mr.inputs["Value"])
        wnt.links.new(mr.outputs["Result"], str_in)
        print(
            "QUANTTRACE_SLICE2AK_WORLD mode map_tex",
            "value_tex", getattr(img, "filepath", None),
            "from", float(mr_from_min), float(mr_from_max),
            "to", float(mr_to_min), float(mr_to_max),
            "sock_default", float(str_in.default_value),
            "str_linked", bool(str_in.is_linked),
            "from_type", mr.type,
        )
    elif mode_key == "clamp":
        cl = wnt.nodes.new("ShaderNodeClamp")
        cl.clamp_type = "MINMAX"
        cl.label = "WorldStrengthClamp"
        cl.location = (bg.location[0] - 240, bg.location[1] - 80)
        val_in = cl.inputs["Value"]
        min_in = cl.inputs["Min"]
        max_in = cl.inputs["Max"]
        min_in.default_value = float(clamp_min)
        max_in.default_value = float(clamp_max)
        vv = wnt.nodes.new("ShaderNodeValue")
        vv.label = "WorldStrengthClampValue"
        vv.outputs[0].default_value = float(clamp_value)
        vv.location = (cl.location[0] - 200, cl.location[1] + 20)
        # Leave Clamp.Value RNA default (1.0) after linking so ignoring the
        # Value node cannot accidentally pack clamp(1.0, 0.2, 0.7)=0.7.
        # Unlinked Value=1.0 would still clamp to 0.7 — set default 0.0 so
        # ignore-link packs clamp(0.0, 0.2, 0.7)=0.2.
        val_in.default_value = 0.0
        wnt.links.new(vv.outputs[0], val_in)
        wnt.links.new(cl.outputs["Result"], str_in)
        expected = _expected_clamp(clamp_value, clamp_min, clamp_max)
        print(
            "QUANTTRACE_SLICE2AK_WORLD mode clamp",
            "clamp_type", cl.clamp_type,
            "value", float(clamp_value), "min", float(clamp_min),
            "max", float(clamp_max), "expected", expected,
            "sock_default", float(str_in.default_value),
            "str_linked", bool(str_in.is_linked),
            "from_type", cl.type,
            "value_linked", bool(val_in.is_linked),
            "value_sock_default", float(val_in.default_value),
        )
    else:
        mr = wnt.nodes.new("ShaderNodeMapRange")
        mr.data_type = "FLOAT"
        mr.interpolation_type = "LINEAR"
        mr.clamp = True
        mr.label = "WorldStrengthMapRange"
        mr.location = (bg.location[0] - 240, bg.location[1] - 80)
        val_in = mr.inputs["Value"]
        mr.inputs["From Min"].default_value = float(mr_from_min)
        mr.inputs["From Max"].default_value = float(mr_from_max)
        mr.inputs["To Min"].default_value = float(mr_to_min)
        mr.inputs["To Max"].default_value = float(mr_to_max)
        vv = wnt.nodes.new("ShaderNodeValue")
        vv.label = "WorldStrengthMapRangeValue"
        vv.outputs[0].default_value = float(mr_value)
        vv.location = (mr.location[0] - 200, mr.location[1] + 40)
        # RNA Value default is 1.0: ignore-link maps to 1.6 not 0.7.
        val_in.default_value = 1.0
        wnt.links.new(vv.outputs[0], val_in)
        wnt.links.new(mr.outputs["Result"], str_in)
        expected = _expected_map_range(
            mr_value, mr_from_min, mr_from_max, mr_to_min, mr_to_max, clamp=True
        )
        print(
            "QUANTTRACE_SLICE2AK_WORLD mode map_range",
            "interp", mr.interpolation_type, "clamp", bool(mr.clamp),
            "value", float(mr_value),
            "from", float(mr_from_min), float(mr_from_max),
            "to", float(mr_to_min), float(mr_to_max),
            "expected", expected,
            "sock_default", float(str_in.default_value),
            "str_linked", bool(str_in.is_linked),
            "from_type", mr.type,
            "value_linked", bool(val_in.is_linked),
            "value_sock_default", float(val_in.default_value),
        )

    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2ak_stock.exr")
    p.add_argument("--image", default="/tmp/qt_slice2ak_env.exr")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument(
        "--mode",
        choices=(
            "map_range", "clamp", "map_tex",
            "mix_float", "math_mul", "value", "unlinked",
        ),
        default="map_range",
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
    p.add_argument("--mr-value", type=float, default=0.25)
    p.add_argument("--mr-from-min", type=float, default=0.0)
    p.add_argument("--mr-from-max", type=float, default=1.0)
    p.add_argument("--mr-to-min", type=float, default=0.4)
    p.add_argument("--mr-to-max", type=float, default=1.6)
    p.add_argument("--clamp-value", type=float, default=1.5)
    p.add_argument("--clamp-min", type=float, default=0.2)
    p.add_argument("--clamp-max", type=float, default=0.7)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2ak_scene(
        image_path=args.image,
        mode=args.mode,
        projection=args.projection,
        strength=args.strength,
        mix_fac=args.mix_fac,
        mix_a=args.mix_a,
        mix_b=args.mix_b,
        mul_a=args.mul_a,
        mul_b=args.mul_b,
        mr_value=args.mr_value,
        mr_from_min=args.mr_from_min,
        mr_from_max=args.mr_from_max,
        mr_to_min=args.mr_to_min,
        mr_to_max=args.mr_to_max,
        clamp_value=args.clamp_value,
        clamp_min=args.clamp_min,
        clamp_max=args.clamp_max,
    )
    print(
        "QUANTTRACE_SLICE2AK", cube_obj.name, "mode", args.mode,
        "strength", args.strength,
        "image", getattr(img, "filepath", None),
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2AK wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
