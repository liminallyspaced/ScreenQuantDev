# QuantTrace Slice 2au: TEX_ENVIRONMENT×0 MULTIPLY → world Background Strength.
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


def _wire_env_mul0_add20(wnt, str_in, env, *, mul_b=0.0, div_b=100.0, add_b=20.0):
    """Strength ← ADD(DIVIDE(MULTIPLY(env.Color, mul_b), div_b), add_b).

    Loft EasyHDR ops (MUL → DIV → ADD). Socket default left 1.0.
    mul_b=0, div_b=100, add_b=20 → Strength 20.
    """
    for link in list(str_in.links):
        wnt.links.remove(link)
    str_in.default_value = 1.0
    mul = _math(wnt, "MULTIPLY", (-640, -80), "WorldStrengthMul")
    div = _math(wnt, "DIVIDE", (-420, -80), "WorldStrengthDiv")
    add = _math(wnt, "ADD", (-200, -80), "WorldStrengthAdd")
    mul.inputs[1].default_value = float(mul_b)
    div.inputs[1].default_value = float(div_b)
    add.inputs[1].default_value = float(add_b)
    wnt.links.new(env.outputs["Color"], mul.inputs[0])
    wnt.links.new(mul.outputs[0], div.inputs[0])
    wnt.links.new(div.outputs[0], add.inputs[0])
    wnt.links.new(add.outputs[0], str_in)
    expected = (0.0 / float(div_b)) + float(add_b) if abs(mul_b) < 1e-12 else None
    return expected


def build_slice2au_scene(
    image_path="/tmp/qt_slice2au_env.exr",
    *,
    mode="env_mul0_add20",
    strength=20.0,
    pull_camera=True,
    env_path="/tmp/qt_slice2au_env.exr",
):
    """Locked cube + AREA; TEX_ENVIRONMENT×0 MULTIPLY → Strength (+ regressions).

    mode:
      env_mul0_add20 — HDR + MUL(env.Color,0)→DIV/100→ADD+20 = 20. CLAIM.
      env_mul0       — MULTIPLY(env.Color, 0) only (strength 0).
      env_mul_nonzero — MULTIPLY(env, 0.5) must refuse.
      env_add        — ADD(env.Color, 20) must refuse.
      math_nest4     — 4-deep Math (must refuse).
      math_nest3 / math_mul / hdr / rgb / rgb_mix / rgb_curves / nishita / teximage
      unlinked       — live-graph partner (unlinked Strength 1.0).
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_slice2aa_scene as sc2aa
    import _quanttrace_slice2at_scene as sc2at
    import _quanttrace_slice2al_scene as sc2al
    import _quanttrace_slice2am_scene as sc2am
    import _quanttrace_slice2an_scene as sc2an
    import _quanttrace_slice2aq_scene as sc2aq
    import _quanttrace_slice2as_scene as sc2as

    mode_key = str(mode).strip().lower()
    allowed = (
        "env_mul0_add20", "env_mul0", "env_mul_nonzero", "env_add",
        "math_nest4", "math_nest3", "math_mul",
        "hdr", "rgb", "rgb_mix", "rgb_curves", "nishita", "teximage",
        "unlinked",
    )
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2au)")

    if mode_key == "math_nest3":
        return sc2at.build_slice2at_scene(
            image_path=env_path, mode="math_nest3", strength=0.7,
            pull_camera=pull_camera, env_path=env_path,
        )
    if mode_key == "math_mul":
        return sc2at.build_slice2at_scene(
            image_path=env_path, mode="math_mul", strength=0.7,
            pull_camera=pull_camera, env_path=env_path,
        )
    if mode_key == "math_nest4":
        return sc2at.build_slice2at_scene(
            image_path=env_path, mode="math_nest4", strength=0.7,
            pull_camera=pull_camera, env_path=env_path,
        )
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
            image_path=env_path, mode="rgb",
            projection="EQUIRECTANGULAR", strength=1.0,
            pull_camera=pull_camera,
        )
    if mode_key == "nishita":
        return sc2am.build_slice2am_scene(
            image_path=env_path, mode="nishita", strength=1.0,
            pull_camera=pull_camera,
        )
    if mode_key == "teximage":
        return sc2an.build_slice2an_scene(
            image_path="/tmp/qt_slice2an_checker.png",
            mode="teximage", projection="FLAT", strength=1.0,
            pull_camera=pull_camera,
        )
    if mode_key == "rgb_mix":
        return sc2aq.build_slice2aq_scene(
            image_path=env_path, mode="rgb_mix", strength=1.0,
            pull_camera=pull_camera, env_path=env_path,
        )
    if mode_key == "rgb_curves":
        return sc2as.build_slice2as_scene(
            image_path=env_path, mode="rgb_curves", strength=1.0,
            pull_camera=pull_camera, env_path=env_path,
        )

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
            "QUANTTRACE_SLICE2AU_WORLD mode unlinked",
            "strength", float(str_in.default_value),
            "str_linked", bool(str_in.is_linked),
        )
    elif mode_key == "env_mul0":
        for link in list(str_in.links):
            wnt.links.remove(link)
        str_in.default_value = 1.0
        mul = _math(wnt, "MULTIPLY", (bg.location[0] - 220, bg.location[1] - 80),
                    "WorldStrengthMul0")
        mul.inputs[1].default_value = 0.0
        wnt.links.new(env.outputs["Color"], mul.inputs[0])
        wnt.links.new(mul.outputs[0], str_in)
        print("QUANTTRACE_SLICE2AU_WORLD mode env_mul0 expected 0.0")
    elif mode_key == "env_mul_nonzero":
        for link in list(str_in.links):
            wnt.links.remove(link)
        str_in.default_value = 1.0
        mul = _math(wnt, "MULTIPLY", (bg.location[0] - 220, bg.location[1] - 80),
                    "WorldStrengthMulNonzero")
        mul.inputs[1].default_value = 0.5
        wnt.links.new(env.outputs["Color"], mul.inputs[0])
        wnt.links.new(mul.outputs[0], str_in)
        print("QUANTTRACE_SLICE2AU_WORLD mode env_mul_nonzero")
    elif mode_key == "env_add":
        for link in list(str_in.links):
            wnt.links.remove(link)
        str_in.default_value = 1.0
        add = _math(wnt, "ADD", (bg.location[0] - 220, bg.location[1] - 80),
                    "WorldStrengthEnvAddRefuse")
        add.inputs[1].default_value = 20.0
        wnt.links.new(env.outputs["Color"], add.inputs[0])
        wnt.links.new(add.outputs[0], str_in)
        print("QUANTTRACE_SLICE2AU_WORLD mode env_add")
    else:
        expected = _wire_env_mul0_add20(wnt, str_in, env)
        print(
            "QUANTTRACE_SLICE2AU_WORLD mode env_mul0_add20",
            "expected", expected,
            "sock_default", float(str_in.default_value),
            "str_linked", bool(str_in.is_linked),
        )

    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", default="/tmp/quanttrace_slice2au_stock.exr")
    p.add_argument("--image", default="/tmp/qt_slice2au_env.exr")
    p.add_argument(
        "--mode",
        choices=(
            "env_mul0_add20", "env_mul0", "env_mul_nonzero", "env_add",
            "math_nest4", "math_nest3", "math_mul",
            "hdr", "rgb", "rgb_mix", "rgb_curves", "nishita", "teximage",
            "unlinked",
        ),
        default="env_mul0_add20",
    )
    p.add_argument("--strength", type=float, default=20.0)
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    args = p.parse_args(_argv())
    scene, *_rest = build_slice2au_scene(
        image_path=args.image,
        mode=args.mode,
        strength=args.strength,
        env_path=args.image,
    )
    scene.render.resolution_x = scene.render.resolution_y = args.res
    scene.cycles.samples = args.samples
    scene.render.filepath = args.out
    bpy.ops.render.render(write_still=True)
    print("QUANTTRACE_SLICE2AU_STOCK", args.out)


if __name__ == "__main__":
    main()
