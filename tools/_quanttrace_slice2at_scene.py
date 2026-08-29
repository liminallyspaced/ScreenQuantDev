# QuantTrace Slice 2at: 3-deep constant Math nest → world Background Strength.
from __future__ import annotations
import argparse, os, sys
import bpy
from mathutils import Vector


def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def _pull_camera_for_world(cam, scale=1.8):
    loc = Vector(cam.location) * float(scale)
    cam.location = loc
    direction = Vector((0.0, 0.0, 0.0)) - loc
    if direction.length > 1e-8:
        cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def _pin_persistent_off(scene):
    if hasattr(scene.render, "use_persistent_data"):
        scene.render.use_persistent_data = False


def _math(wnt, op, loc, label):
    node = wnt.nodes.new("ShaderNodeMath")
    node.operation = op
    node.label = label
    node.location = loc
    return node


def _value(wnt, val, loc, label):
    node = wnt.nodes.new("ShaderNodeValue")
    node.label = label
    node.outputs[0].default_value = float(val)
    node.location = loc
    return node


def _wire_math_nest3(wnt, str_in, *, mul_a=0.5, mul_b=1.4, div_b=1.0, add_b=0.0):
    """Strength ← ADD( DIVIDE( MULTIPLY(mul_a, mul_b), div_b ), add_b ).

    Loft EasyHDR ops (MUL → DIV → ADD) with constant Values. Expected
    default 0.5*1.4/1.0+0.0 = 0.7. Socket default left 1.0.
    """
    for link in list(str_in.links):
        wnt.links.remove(link)
    str_in.default_value = 1.0
    mul = _math(wnt, "MULTIPLY", (-640, -80), "WorldStrengthMul")
    div = _math(wnt, "DIVIDE", (-420, -80), "WorldStrengthDiv")
    add = _math(wnt, "ADD", (-200, -80), "WorldStrengthAdd")
    va = _value(wnt, mul_a, (-860, -40), "MulA")
    vb = _value(wnt, mul_b, (-860, -120), "MulB")
    vd = _value(wnt, div_b, (-640, -180), "DivB")
    ve = _value(wnt, add_b, (-420, -180), "AddB")
    wnt.links.new(va.outputs[0], mul.inputs[0])
    wnt.links.new(vb.outputs[0], mul.inputs[1])
    wnt.links.new(mul.outputs[0], div.inputs[0])
    wnt.links.new(vd.outputs[0], div.inputs[1])
    wnt.links.new(div.outputs[0], add.inputs[0])
    wnt.links.new(ve.outputs[0], add.inputs[1])
    wnt.links.new(add.outputs[0], str_in)
    expected = (float(mul_a) * float(mul_b)) / float(div_b) + float(add_b)
    return expected


def build_slice2at_scene(
    image_path="/tmp/qt_slice2at_env.exr",
    *,
    mode="math_nest3",
    strength=0.7,
    pull_camera=True,
    env_path="/tmp/qt_slice2at_env.exr",
):
    """Locked cube + AREA; 3-deep Math → Strength (+ regressions).

    mode:
      math_nest3  — HDR + MUL→DIV→ADD constants = 0.7. CLAIM.
      math_mul    — 2ai 2-deep identity skip.
      rgb / rgb_mix / hdr / nishita / teximage / sky_map / rgb_curves
      math_nest4  — 4-deep Math (must refuse).
      env_math    — TEX_ENVIRONMENT.Color → Math (must refuse; loft leftover).
      unlinked    — live-graph partner (unlinked Strength 1.0).
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_slice2aa_scene as sc2aa
    import _quanttrace_slice2ai_scene as sc2ai
    import _quanttrace_slice2al_scene as sc2al
    import _quanttrace_slice2am_scene as sc2am
    import _quanttrace_slice2an_scene as sc2an
    import _quanttrace_slice2aq_scene as sc2aq
    import _quanttrace_slice2ar_scene as sc2ar
    import _quanttrace_slice2as_scene as sc2as

    mode_key = str(mode).strip().lower()
    allowed = (
        "math_nest3", "math_mul",
        "rgb", "rgb_mix", "hdr", "nishita", "teximage", "sky_map", "rgb_curves",
        "math_nest4", "env_math", "unlinked",
    )
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2at)")

    if mode_key == "hdr":
        scene, cube_obj, lamp, cam, img = sc2aa.build_slice2aa_scene(
            image_path=env_path,
            projection="EQUIRECTANGULAR",
            strength=1.0,
            black_world=False,
        )
        _pin_persistent_off(scene)
        return scene, cube_obj, lamp, cam, img
    if mode_key == "rgb":
        return sc2al.build_slice2al_scene(
            image_path=env_path,
            mode="rgb",
            projection="EQUIRECTANGULAR",
            strength=1.0,
            pull_camera=pull_camera,
        )
    if mode_key == "nishita":
        return sc2am.build_slice2am_scene(
            image_path=env_path,
            mode="nishita",
            strength=1.0,
            pull_camera=pull_camera,
        )
    if mode_key == "teximage":
        return sc2an.build_slice2an_scene(
            image_path="/tmp/qt_slice2an_checker.png",
            mode="teximage",
            projection="FLAT",
            strength=1.0,
            pull_camera=pull_camera,
        )
    if mode_key == "rgb_mix":
        return sc2aq.build_slice2aq_scene(
            image_path=env_path,
            mode="rgb_mix",
            strength=1.0,
            pull_camera=pull_camera,
            env_path=env_path,
        )
    if mode_key == "sky_map":
        return sc2ar.build_slice2ar_scene(
            image_path=env_path,
            mode="sky_map",
            strength=1.0,
            pull_camera=pull_camera,
        )
    if mode_key == "rgb_curves":
        return sc2as.build_slice2as_scene(
            image_path=env_path,
            mode="rgb_curves",
            strength=1.0,
            pull_camera=pull_camera,
            env_path=env_path,
        )
    if mode_key == "math_mul":
        scene, cube_obj, lamp, cam, img = sc2ai.build_slice2ai_scene(
            image_path=env_path,
            mode="math_mul",
            projection="EQUIRECTANGULAR",
            strength=0.7,
            mul_a=0.5,
            mul_b=1.4,
        )
        _pin_persistent_off(scene)
        return scene, cube_obj, lamp, cam, img

    # HDR env base (Color ← TEX_ENVIRONMENT). Strength sock default 1.0.
    scene, cube_obj, lamp, cam, img = sc2aa.build_slice2aa_scene(
        image_path=image_path,
        projection="EQUIRECTANGULAR",
        strength=1.0,
        black_world=False,
    )
    _pin_persistent_off(scene)
    if pull_camera:
        _pull_camera_for_world(cam, 1.8)

    world = scene.world
    wnt = world.node_tree
    bg = next(n for n in wnt.nodes if n.type == "BACKGROUND")
    str_in = bg.inputs["Strength"]
    env = next(n for n in wnt.nodes if n.type == "TEX_ENVIRONMENT")

    if mode_key == "unlinked":
        print(
            "QUANTTRACE_SLICE2AT_WORLD mode unlinked",
            "strength", float(str_in.default_value),
            "str_linked", bool(str_in.is_linked),
        )
    elif mode_key == "env_math":
        for link in list(str_in.links):
            wnt.links.remove(link)
        str_in.default_value = 1.0
        math = _math(wnt, "MULTIPLY", (bg.location[0] - 220, bg.location[1] - 80),
                     "WorldStrengthEnvMathRefuse")
        math.inputs[1].default_value = 0.0
        wnt.links.new(env.outputs["Color"], math.inputs[0])
        wnt.links.new(math.outputs[0], str_in)
        print("QUANTTRACE_SLICE2AT_WORLD mode env_math")
    elif mode_key == "math_nest4":
        expected = _wire_math_nest3(wnt, str_in)
        add = next(n for n in wnt.nodes if n.label == "WorldStrengthAdd")
        extra = _math(wnt, "ADD", (bg.location[0] - 80, bg.location[1] - 80),
                      "WorldStrengthNest4")
        extra.inputs[1].default_value = 0.0
        for link in list(str_in.links):
            wnt.links.remove(link)
        wnt.links.new(add.outputs[0], extra.inputs[0])
        wnt.links.new(extra.outputs[0], str_in)
        print("QUANTTRACE_SLICE2AT_WORLD mode math_nest4 expected", expected)
    else:
        expected = _wire_math_nest3(wnt, str_in)
        print(
            "QUANTTRACE_SLICE2AT_WORLD mode math_nest3",
            "expected", expected,
            "sock_default", float(str_in.default_value),
            "str_linked", bool(str_in.is_linked),
        )

    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="/tmp/quanttrace_slice2at_stock.exr")
    p.add_argument("--image", default="/tmp/qt_slice2at_env.exr")
    p.add_argument(
        "--mode",
        choices=(
            "math_nest3", "math_mul",
            "rgb", "rgb_mix", "hdr", "nishita", "teximage", "sky_map", "rgb_curves",
            "math_nest4", "env_math", "unlinked",
        ),
        default="math_nest3",
    )
    p.add_argument("--strength", type=float, default=0.7)
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    args = p.parse_args(_argv())
    scene, *_rest = build_slice2at_scene(
        image_path=args.image,
        mode=args.mode,
        strength=args.strength,
        env_path=args.image,
    )
    scene.render.resolution_x = scene.render.resolution_y = args.res
    scene.cycles.samples = args.samples
    scene.render.filepath = args.out
    bpy.ops.render.render(write_still=True)
    print("QUANTTRACE_SLICE2AT_STOCK", args.out)


if __name__ == "__main__":
    main()
