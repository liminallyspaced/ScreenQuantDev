# QuantTrace Slice 2ai: Background Strength linked from ShaderNodeMath.
from __future__ import annotations
import argparse, os, sys
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def build_slice2ai_scene(
    image_path="/tmp/qt_slice2ai_env.exr",
    *,
    mode="math_mul",
    projection="EQUIRECTANGULAR",
    strength=0.7,
    mul_a=0.5,
    mul_b=1.4,
    add_a=0.3,
    add_b=0.4,
):
    """Locked cube + Environment Texture Color, Math/Value → Strength.

    mode:
      math_mul — Strength ← Math MULTIPLY(Value mul_a, Value mul_b)
                 (defaults 0.5 * 1.4 = 0.7); Strength sock default stays 1.0
      math_add — Strength ← Math ADD(Value add_a, Value add_b)
                 (defaults 0.3 + 0.4 = 0.7); sock default stays 1.0
      value    — Slice 2ah regression (Strength ← ShaderNodeValue)
      unlinked — Slice 2aa regression (unlinked Strength default)
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_slice2aa_scene as sc2aa

    mode_key = str(mode).strip().lower()
    if mode_key not in ("math_mul", "math_add", "value", "unlinked"):
        raise RuntimeError(f"mode={mode!r} refused (Slice 2ai)")

    # Linked modes keep socket default 1.0 so ignoring the link fails the gate.
    aa_strength = 1.0 if mode_key != "unlinked" else float(strength)
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

    if mode_key in ("math_mul", "math_add"):
        for link in list(str_in.links):
            wnt.links.remove(link)
        str_in.default_value = 1.0
        math = wnt.nodes.new("ShaderNodeMath")
        math.label = "WorldStrengthMath"
        math.location = (bg.location[0] - 220, bg.location[1] - 80)
        if mode_key == "math_mul":
            math.operation = "MULTIPLY"
            a_val, b_val = float(mul_a), float(mul_b)
            expected = a_val * b_val
        else:
            math.operation = "ADD"
            a_val, b_val = float(add_a), float(add_b)
            expected = a_val + b_val
        va = wnt.nodes.new("ShaderNodeValue")
        va.label = "WorldStrengthA"
        va.outputs[0].default_value = a_val
        va.location = (math.location[0] - 200, math.location[1] + 40)
        vb = wnt.nodes.new("ShaderNodeValue")
        vb.label = "WorldStrengthB"
        vb.outputs[0].default_value = b_val
        vb.location = (math.location[0] - 200, math.location[1] - 40)
        # Blender 5.2 identifiers: Value / Value_001
        wnt.links.new(va.outputs[0], math.inputs[0])
        wnt.links.new(vb.outputs[0], math.inputs[1])
        wnt.links.new(math.outputs[0], str_in)
        print(
            "QUANTTRACE_SLICE2AI_WORLD mode", mode_key,
            "op", math.operation,
            "a", a_val, "b", b_val, "expected", expected,
            "sock_default", float(str_in.default_value),
            "str_linked", bool(str_in.is_linked),
            "from", math.type,
        )
    elif mode_key == "value":
        vnode = wnt.nodes.new("ShaderNodeValue")
        vnode.label = "WorldStrength"
        vnode.outputs[0].default_value = float(strength)
        vnode.location = (bg.location[0] - 220, bg.location[1] - 80)
        for link in list(str_in.links):
            wnt.links.remove(link)
        str_in.default_value = 1.0
        wnt.links.new(vnode.outputs[0], str_in)
        print(
            "QUANTTRACE_SLICE2AI_WORLD mode value",
            "value", float(strength),
            "sock_default", float(str_in.default_value),
            "str_linked", bool(str_in.is_linked),
            "from", vnode.type,
        )
    else:
        print(
            "QUANTTRACE_SLICE2AI_WORLD mode unlinked",
            "strength", float(str_in.default_value),
            "str_linked", bool(str_in.is_linked),
        )

    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2ai_stock.exr")
    p.add_argument("--image", default="/tmp/qt_slice2ai_env.exr")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument(
        "--mode",
        choices=("math_mul", "math_add", "value", "unlinked"),
        default="math_mul",
    )
    p.add_argument(
        "--projection",
        choices=("EQUIRECTANGULAR", "MIRROR_BALL"),
        default="EQUIRECTANGULAR",
    )
    p.add_argument("--strength", type=float, default=0.7)
    p.add_argument("--mul-a", type=float, default=0.5)
    p.add_argument("--mul-b", type=float, default=1.4)
    p.add_argument("--add-a", type=float, default=0.3)
    p.add_argument("--add-b", type=float, default=0.4)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2ai_scene(
        image_path=args.image,
        mode=args.mode,
        projection=args.projection,
        strength=args.strength,
        mul_a=args.mul_a,
        mul_b=args.mul_b,
        add_a=args.add_a,
        add_b=args.add_b,
    )
    print(
        "QUANTTRACE_SLICE2AI", cube_obj.name, "mode", args.mode,
        "strength", args.strength,
        "image", getattr(img, "filepath", None),
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2AI wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
