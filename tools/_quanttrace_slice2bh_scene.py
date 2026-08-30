# QuantTrace Slice 2bh: RGB Curves ← TEX_IMAGE on Mix A/B → Principled Base Color.
from __future__ import annotations
import argparse, os, struct, sys, zlib
import bpy
from mathutils import Vector


CURVE_I_MID_Y = 0.35


def _argv():
    a = sys.argv
    return a[a.index("--") + 1 :] if "--" in a else []


def _pull_camera(cam, scale=1.8):
    loc = Vector(cam.location) * float(scale)
    cam.location = loc
    direction = Vector((0.0, 0.0, 0.0)) - loc
    if direction.length > 1e-8:
        cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def _make_checker_png(path, seed=0):
    w = h = 8
    rows = []
    for y in range(h):
        row = [0]
        for x in range(w):
            on = ((x + y + seed) % 2) == 0
            v = 220 if on else 40
            row.extend((v, v, v))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)
    return path


def _add_mix(nt, *, blend="MIX", fac=0.5, a=None, b=None, clamp_factor=False):
    node = nt.nodes.new("ShaderNodeMix")
    node.data_type = "RGBA"
    node.blend_type = blend
    node.clamp_factor = bool(clamp_factor)
    node.clamp_result = False
    fac_sock = node.inputs.get("Factor_Float") or node.inputs.get("Factor") or node.inputs.get("Fac")
    fac_sock.default_value = float(fac)
    a_sock = node.inputs.get("A_Color") or node.inputs.get("A")
    b_sock = node.inputs.get("B_Color") or node.inputs.get("B")
    if a is not None:
        a_sock.default_value = (float(a[0]), float(a[1]), float(a[2]), 1.0)
    if b is not None:
        b_sock.default_value = (float(b[0]), float(b[1]), float(b[2]), 1.0)
    return node


def _add_rgb_curves(nt, *, mid_y=CURVE_I_MID_Y):
    node = nt.nodes.new("ShaderNodeRGBCurve")
    node.label = "qt_mix_side_curves"
    fac = node.inputs.get("Fac") or node.inputs.get("Factor")
    fac.default_value = 1.0
    mapping = node.mapping
    cm_i = mapping.curves[3]
    while len(cm_i.points) > 2:
        cm_i.points.remove(cm_i.points[1])
    cm_i.points[0].location = (0.0, 0.0)
    cm_i.points[1].location = (1.0, 1.0)
    cm_i.points.new(0.5, float(mid_y))
    mapping.extend = "EXTRAPOLATED"
    mapping.update()
    return node


def build_slice2bh_scene(
    image_path="/tmp/qt_slice2bh_checker.png",
    *,
    mode="claim",
):
    """Locked cube; TEX_IMAGE → RGB Curves → Mix A, Mix B const, Fac unlinked 0.5.

    mode:
      claim        — CLAIM graph (Slice 2bh)
      bypass       — Mix A=TEX only (Curves bypassed; live partner)
      mix          — 2ay regression
      curves       — 2bd regression (Curves AFTER Mix)
      fresnel      — 2bf regression
      nested       — 2bg nested constant fold
      invert       — 2be regression
      point        — 2av regression
      hdr          — 2aa regression
      fac_noise    — Noise → Curves.Fac (named REFUSE Slice 2bh)
      color_noise  — Noise → Curves Color-in (named REFUSE Slice 2bh)
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)

    mode_key = str(mode).strip().lower()
    allowed = (
        "claim", "bypass", "mix", "curves", "fresnel", "nested",
        "invert", "point", "hdr", "fac_noise", "color_noise",
    )
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2bh)")

    if mode_key == "mix":
        import _quanttrace_slice2ay_scene as sc
        return sc.build_slice2ay_scene(mode="mix")
    if mode_key == "curves":
        import _quanttrace_slice2bd_scene as sc
        return sc.build_slice2bd_scene(mode="curves")
    if mode_key == "fresnel":
        import _quanttrace_slice2bf_scene as sc
        return sc.build_slice2bf_scene(mode="claim")
    if mode_key == "nested":
        import _quanttrace_slice2bg_scene as sc
        return sc.build_slice2bg_scene(mode="claim")
    if mode_key == "invert":
        import _quanttrace_slice2be_scene as sc
        return sc.build_slice2be_scene(mode="invert")
    if mode_key == "point":
        import _quanttrace_slice2av_scene as sc
        return sc.build_slice2av_scene(
            image_path="/tmp/qt_slice2av_env.exr", mode="point"
        )
    if mode_key == "hdr":
        import _quanttrace_slice2aa_scene as sc
        return sc.build_slice2aa_scene()

    import _quanttrace_tex_scene as texsc

    _make_checker_png(image_path, seed=0)
    scene, cube_obj, lamp, cam, img = texsc.build_tex_scene(image_path=image_path)
    _pull_camera(cam, 1.8)
    mat = cube_obj.data.materials[0]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex = next(n for n in nt.nodes if n.type == "TEX_IMAGE")
    for link in list(bsdf.inputs["Base Color"].links):
        nt.links.remove(link)

    mx = _add_mix(nt, blend="MIX", fac=0.5, b=(0.0, 0.0, 0.0), clamp_factor=False)
    mx.label = "qt_mix_side_curves_mix"
    a_sock = mx.inputs.get("A_Color") or mx.inputs.get("A")
    b_sock = mx.inputs.get("B_Color") or mx.inputs.get("B")
    fac_sock = mx.inputs.get("Factor_Float") or mx.inputs.get("Factor") or mx.inputs.get("Fac")
    fac_sock.default_value = 0.5

    if mode_key == "bypass":
        nt.links.new(tex.outputs["Color"], a_sock)
    else:
        curves = _add_rgb_curves(nt)
        color_in = curves.inputs.get("Color") or curves.inputs[1]
        if mode_key == "color_noise":
            noise = nt.nodes.new("ShaderNodeTexNoise")
            noise.label = "qt_curves_color_noise"
            nt.links.new(noise.outputs["Color"], color_in)
        else:
            nt.links.new(tex.outputs["Color"], color_in)
        if mode_key == "fac_noise":
            noise = nt.nodes.new("ShaderNodeTexNoise")
            noise.label = "qt_curves_fac_noise"
            fac_c = curves.inputs.get("Fac") or curves.inputs.get("Factor")
            nt.links.new(noise.outputs["Fac"], fac_c)
        nt.links.new(curves.outputs.get("Color") or curves.outputs[0], a_sock)

    out = mx.outputs.get("Result") or mx.outputs.get("Color") or mx.outputs[0]
    nt.links.new(out, bsdf.inputs["Base Color"])
    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--mode",
        default="claim",
        choices=(
            "claim", "bypass", "mix", "curves", "fresnel", "nested",
            "invert", "point", "hdr", "fac_noise", "color_noise",
        ),
    )
    p.add_argument("--image", default="/tmp/qt_slice2bh_checker.png")
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2bh_stock.exr")
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2bh_scene(
        image_path=args.image, mode=args.mode,
    )
    print("QUANTTRACE_SLICE2BH", cube_obj.name, "mode", args.mode)
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2BH wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
