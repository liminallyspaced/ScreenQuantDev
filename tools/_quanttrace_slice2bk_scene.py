# QuantTrace Slice 2bk: Mix → Principled.Specular Tint.
from __future__ import annotations
import argparse, os, struct, sys, zlib
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1 :] if "--" in a else []


def _write_checker_png(path, seed=0, n=8):
    rgb = bytearray()
    for y in range(n):
        for x in range(n):
            on = ((x + y + seed) % 2) == 0
            v = 220 if on else 40
            rgb.extend((v, v // 2, 255 - v))

    def chunk(tag, data):
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    raw = b""
    row = n * 3
    for y in range(n):
        raw += b"\x00" + bytes(rgb[y * row : (y + 1) * row])
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 2, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(bytes(raw), 9)))
        f.write(chunk(b"IEND", b""))
    img = bpy.data.images.load(path)
    try:
        img.colorspace_settings.name = "sRGB"
    except Exception:
        pass
    return img


def _add_mix(nt, *, blend="MIX", fac=0.25, a=(0.0, 0.0, 0.0), b=(0.0, 0.0, 0.0),
             clamp_factor=True):
    node = nt.nodes.new("ShaderNodeMix")
    node.data_type = "RGBA"
    node.blend_type = blend
    node.clamp_factor = bool(clamp_factor)
    node.clamp_result = False
    fac_sock = node.inputs.get("Factor_Float") or node.inputs.get("Factor") or node.inputs.get("Fac")
    fac_sock.default_value = float(fac)
    a_sock = node.inputs.get("A_Color") or node.inputs.get("A")
    b_sock = node.inputs.get("B_Color") or node.inputs.get("B")
    a_sock.default_value = (float(a[0]), float(a[1]), float(a[2]), 1.0)
    b_sock.default_value = (float(b[0]), float(b[1]), float(b[2]), 1.0)
    return node


def build_slice2bk_scene(
    image_path="/tmp/qt_slice2bk_checker.png",
    *,
    mode="claim",
    image_b_path="/tmp/qt_slice2bk_checker_b.png",
):
    """Locked cube; Mix → Principled.Specular Tint (loft Sideboard shape).

    mode:
      claim     — CLAIM: Mix RGBA MIX Fac=0.25 clamp_factor A=B=(0,0,0) → Specular Tint
      mix       — TEX_IMAGE → Mix A, B const (0.1,0.8,0.4) Fac=0.5 → Specular Tint
      mix_dual  — dual TEX_IMAGE Mix MULTIPLY Fac=0.5 clamp_factor
      tex       — 2u regression: TEX_IMAGE → Specular Tint (mix_type=0)
      mix_base  — 2ay regression
      separate  — 2bj regression
      invert    — 2be regression
      hdr       — 2aa regression
      fac_group — Fac ← Value group-like (VALUE node) REFUSE Slice 2bk
      fac_fresnel — Fac ← Fresnel REFUSE Slice 2bk
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)

    mode_key = str(mode).strip().lower()
    allowed = (
        "claim", "fold", "mix", "mix_dual", "tex", "mix_base", "separate", "invert", "hdr",
        "fac_group", "fac_fresnel",
    )
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2bk)")

    if mode_key == "mix_base":
        import _quanttrace_slice2ay_scene as sc
        return sc.build_slice2ay_scene(mode="mix")
    if mode_key == "separate":
        import _quanttrace_slice2bj_scene as sc
        return sc.build_slice2bj_scene(mode="claim")
    if mode_key == "invert":
        import _quanttrace_slice2be_scene as sc
        return sc.build_slice2be_scene(image_path=image_path, mode="invert")
    if mode_key == "hdr":
        import _quanttrace_slice2aa_scene as sc
        return sc.build_slice2aa_scene()
    if mode_key == "tex":
        import _quanttrace_slice2u_scene as sc
        return sc.build_slice2u_scene(socket="SpecTint")

    import _quanttrace_cube_scene as cube

    scene, cube_obj, lamp, cam = cube.build_locked_scene()
    mat = cube_obj.data.materials[0]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.85, 0.85, 0.85, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.25
    bsdf.inputs["Metallic"].default_value = 1.0  # Specular Tint highly visible
    st = bsdf.inputs.get("Specular Tint")

    if mode_key == "claim":
        # Loft Sideboard: TEX → Gamma(1.2) → HueSat(H=0.51,S=0.9,V=0.8,Fac=1)
        # → Mix.B; Mix.A = white; Fac=0.25 clamp_factor.
        img = _write_checker_png(image_path, seed=0)
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        tex.interpolation = "Linear"
        tex.extension = "REPEAT"
        tex.projection = "FLAT"
        tex.label = "qt_spec_tint_sideboard_tex"
        gam = nt.nodes.new("ShaderNodeGamma")
        gam.inputs["Gamma"].default_value = 1.2
        gam.label = "qt_spec_tint_gamma"
        hs = nt.nodes.new("ShaderNodeHueSaturation")
        hs.inputs["Hue"].default_value = 0.51
        hs.inputs["Saturation"].default_value = 0.9
        hs.inputs["Value"].default_value = 0.8
        fac_hs = hs.inputs.get("Fac") or hs.inputs.get("Factor")
        fac_hs.default_value = 1.0
        hs.label = "qt_spec_tint_hsv"
        mx = _add_mix(nt, fac=0.25, a=(1.0, 1.0, 1.0), b=(0.0, 0.0, 0.0), clamp_factor=True)
        mx.label = "qt_spec_tint_mix_sideboard"
        b_sock = mx.inputs.get("B_Color") or mx.inputs.get("B")
        nt.links.new(tex.outputs["Color"], gam.inputs["Color"])
        nt.links.new(gam.outputs["Color"], hs.inputs["Color"])
        nt.links.new(hs.outputs["Color"], b_sock)
        nt.links.new(mx.outputs.get("Result") or mx.outputs[0], st)
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key == "fold":
        # Constant-only Mix fold A=B=black Fac=0.25 (Python-only specular_tint).
        mx = _add_mix(nt, fac=0.25, a=(0.0, 0.0, 0.0), b=(0.0, 0.0, 0.0), clamp_factor=True)
        mx.label = "qt_spec_tint_mix_fold"
        nt.links.new(mx.outputs.get("Result") or mx.outputs[0], st)
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, None

    if mode_key in ("fac_group", "fac_fresnel"):
        mx = _add_mix(nt, fac=0.25, a=(1.0, 0.0, 0.0), b=(0.0, 0.0, 1.0), clamp_factor=True)
        fac_sock = mx.inputs.get("Factor_Float") or mx.inputs.get("Factor") or mx.inputs.get("Fac")
        if mode_key == "fac_fresnel":
            fr = nt.nodes.new("ShaderNodeFresnel")
            fr.inputs["IOR"].default_value = 1.45
            nt.links.new(fr.outputs["Fac"], fac_sock)
        else:
            val = nt.nodes.new("ShaderNodeValue")
            val.outputs[0].default_value = 0.3
            nt.links.new(val.outputs[0], fac_sock)
        nt.links.new(mx.outputs.get("Result") or mx.outputs[0], st)
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, None

    img = _write_checker_png(image_path, seed=0)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = "Linear"
    tex.extension = "REPEAT"
    tex.projection = "FLAT"
    tex.label = "qt_spec_tint_tex"

    if mode_key == "mix":
        mx = _add_mix(nt, fac=0.5, a=(0.0, 0.0, 0.0), b=(0.1, 0.8, 0.4), clamp_factor=False)
        a_sock = mx.inputs.get("A_Color") or mx.inputs.get("A")
        nt.links.new(tex.outputs["Color"], a_sock)
        nt.links.new(mx.outputs.get("Result") or mx.outputs[0], st)
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key == "mix_dual":
        img_b = _write_checker_png(image_b_path, seed=1)
        tex_b = nt.nodes.new("ShaderNodeTexImage")
        tex_b.image = img_b
        tex_b.interpolation = "Linear"
        tex_b.extension = "REPEAT"
        tex_b.projection = "FLAT"
        mx = _add_mix(nt, blend="MULTIPLY", fac=0.5, clamp_factor=True)
        a_sock = mx.inputs.get("A_Color") or mx.inputs.get("A")
        b_sock = mx.inputs.get("B_Color") or mx.inputs.get("B")
        nt.links.new(tex.outputs["Color"], a_sock)
        nt.links.new(tex_b.outputs["Color"], b_sock)
        nt.links.new(mx.outputs.get("Result") or mx.outputs[0], st)
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    raise RuntimeError(f"unhandled mode {mode_key}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--mode", default="claim",
        choices=(
            "claim", "mix", "mix_dual", "tex", "mix_base", "separate", "invert", "hdr",
            "fac_group", "fac_fresnel",
        ),
    )
    p.add_argument("--image", default="/tmp/qt_slice2bk_checker.png")
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2bk_stock.exr")
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2bk_scene(
        image_path=args.image, mode=args.mode,
    )
    print("QUANTTRACE_SLICE2BK", cube_obj.name, "mode", args.mode)
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2BK wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
