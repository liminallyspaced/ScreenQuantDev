# QuantTrace Slice 2bg: nested constant Mix fold on Mix A/B → Principled Base Color.
from __future__ import annotations
import argparse, os, struct, sys, zlib
import bpy
from mathutils import Vector


LOFT_FRESNEL_IOR = 1.45
LOFT_MIX_A = (0.08200758695602417, 0.08200758695602417, 0.08200758695602417)
LOFT_MIX_B = (0.2355731576681137, 0.2355731576681137, 0.2355731576681137)
LOFT_CURVE_I_MID = (0.313637, 0.7125)


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


def _add_mix(nt, *, blend="MIX", fac=0.5, a=None, b=None, clamp_factor=True):
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


def _add_fresnel(nt, *, ior):
    node = nt.nodes.new("ShaderNodeFresnel")
    node.label = "qt_mix_fresnel_fac"
    ior_sock = node.inputs.get("IOR")
    ior_sock.default_value = float(ior)
    return node


def _add_rgb_curves_loft(nt):
    node = nt.nodes.new("ShaderNodeRGBCurve")
    node.label = "qt_base_curves_loft"
    fac = node.inputs.get("Fac") or node.inputs.get("Factor")
    fac.default_value = 1.0
    mapping = node.mapping
    cm_i = mapping.curves[3]
    while len(cm_i.points) > 2:
        cm_i.points.remove(cm_i.points[1])
    cm_i.points[0].location = (0.0, 0.0)
    cm_i.points[1].location = (1.0, 1.0)
    cm_i.points.new(float(LOFT_CURVE_I_MID[0]), float(LOFT_CURVE_I_MID[1]))
    mapping.extend = "EXTRAPOLATED"
    mapping.update()
    return node


def build_slice2bg_scene(
    image_path="/tmp/qt_slice2bg_checker.png",
    *,
    mode="claim",
):
    """Locked cube; loft Material.003-shaped Mix → Base Color.

    mode:
      claim          — CLAIM: A←nested constant Mix, B←Curves←nested Mix, Fac←Fresnel
      mix            — 2ay regression
      fresnel        — 2bf regression (TEX A vs const B, Fac←Fresnel)
      curves         — 2bd regression
      invert         — 2be regression
      point          — 2av regression
      hdr            — 2aa regression
      nested_tex     — nested Mix with TEX_IMAGE on A (named REFUSE Slice 2bg)
      fac_noise      — Noise → Mix.Fac (named REFUSE Slice 2bf)
      unlinked_fac   — same graph as claim but Fac unlinked 0.5 (live partner)
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)

    mode_key = str(mode).strip().lower()
    allowed = (
        "claim", "mix", "fresnel", "curves", "invert", "point", "hdr",
        "nested_tex", "fac_noise", "unlinked_fac",
    )
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2bg)")

    if mode_key == "mix":
        import _quanttrace_slice2ay_scene as sc
        return sc.build_slice2ay_scene(mode="mix")
    if mode_key == "fresnel":
        import _quanttrace_slice2bf_scene as sc
        return sc.build_slice2bf_scene(mode="claim")
    if mode_key == "curves":
        import _quanttrace_slice2bd_scene as sc
        return sc.build_slice2bd_scene(mode="curves")
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

    inner = _add_mix(
        nt, blend="MIX", fac=0.5, a=LOFT_MIX_A, b=LOFT_MIX_B, clamp_factor=True
    )
    inner.label = "qt_nested_const_mix"
    inner_out = inner.outputs.get("Result") or inner.outputs.get("Color") or inner.outputs[0]

    if mode_key == "nested_tex":
        # Nested Mix with linked TEX on A — not constant-foldable → REFUSE 2bg.
        nested = _add_mix(nt, blend="MIX", fac=0.5, a=(0.1, 0.1, 0.1), b=(0.9, 0.9, 0.9), clamp_factor=True)
        nested.label = "qt_nested_tex_mix"
        a_n = nested.inputs.get("A_Color") or nested.inputs.get("A")
        nt.links.new(tex.outputs["Color"], a_n)
        outer = _add_mix(nt, blend="MIX", fac=0.5, a=(0.0, 0.0, 0.0), b=(0.0, 0.0, 0.0), clamp_factor=True)
        a_o = outer.inputs.get("A_Color") or outer.inputs.get("A")
        b_o = outer.inputs.get("B_Color") or outer.inputs.get("B")
        nested_out = nested.outputs.get("Result") or nested.outputs.get("Color") or nested.outputs[0]
        nt.links.new(nested_out, a_o)
        # B = constant RGB via Curves identity so both sides linked without dual-TEX escape.
        curves = _add_rgb_curves_loft(nt)
        # Feed Curves from inner constant Mix so Color-in is valid.
        nt.links.new(inner_out, curves.inputs.get("Color") or curves.inputs[1])
        nt.links.new(curves.outputs.get("Color") or curves.outputs[0], b_o)
        fac_sock = outer.inputs.get("Factor_Float") or outer.inputs.get("Factor") or outer.inputs.get("Fac")
        fr = _add_fresnel(nt, ior=LOFT_FRESNEL_IOR)
        fr_out = fr.outputs.get("Fac") or fr.outputs.get("Factor") or fr.outputs[0]
        nt.links.new(fr_out, fac_sock)
        out = outer.outputs.get("Result") or outer.outputs.get("Color") or outer.outputs[0]
        nt.links.new(out, bsdf.inputs["Base Color"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    # CLAIM / unlinked_fac / fac_noise: loft graph shape.
    curves = _add_rgb_curves_loft(nt)
    nt.links.new(inner_out, curves.inputs.get("Color") or curves.inputs[1])
    outer = _add_mix(nt, blend="MIX", fac=0.5, a=(0.5, 0.5, 0.5), b=(0.5, 0.5, 0.5), clamp_factor=True)
    outer.label = "qt_outer_mix"
    a_o = outer.inputs.get("A_Color") or outer.inputs.get("A")
    b_o = outer.inputs.get("B_Color") or outer.inputs.get("B")
    nt.links.new(inner_out, a_o)
    nt.links.new(curves.outputs.get("Color") or curves.outputs[0], b_o)
    fac_sock = outer.inputs.get("Factor_Float") or outer.inputs.get("Factor") or outer.inputs.get("Fac")
    if mode_key == "fac_noise":
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.label = "qt_mix_fac_noise"
        nt.links.new(noise.outputs["Fac"], fac_sock)
    elif mode_key == "unlinked_fac":
        fac_sock.default_value = 0.5
    else:
        fr = _add_fresnel(nt, ior=LOFT_FRESNEL_IOR)
        fr_out = fr.outputs.get("Fac") or fr.outputs.get("Factor") or fr.outputs[0]
        nt.links.new(fr_out, fac_sock)
    out = outer.outputs.get("Result") or outer.outputs.get("Color") or outer.outputs[0]
    nt.links.new(out, bsdf.inputs["Base Color"])
    # Detach unused tex from Base Color path (still in tree for live partner builds).
    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--mode",
        default="claim",
        choices=(
            "claim", "mix", "fresnel", "curves", "invert", "point", "hdr",
            "nested_tex", "fac_noise", "unlinked_fac",
        ),
    )
    p.add_argument("--image", default="/tmp/qt_slice2bg_checker.png")
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2bg_stock.exr")
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2bg_scene(
        image_path=args.image, mode=args.mode,
    )
    print("QUANTTRACE_SLICE2BG", cube_obj.name, "mode", args.mode)
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2BG wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
