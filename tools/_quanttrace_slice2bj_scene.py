# QuantTrace Slice 2bj: Separate Color → Principled.Roughness.
from __future__ import annotations
import argparse, os, struct, sys, zlib
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1 :] if "--" in a else []


def _write_rgb_channel_png(path, n=8):
    """Non-Color RGB where R/G/B differ so Separate.Green ≠ CF-gray(Color).

    Checker on Green (40/220); Red fixed 10; Blue fixed 200.
    """
    rgb = bytearray()
    for y in range(n):
        for x in range(n):
            g = 40 if ((x // 2) + (y // 2)) % 2 == 0 else 220
            rgb.extend((10, g, 200))

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
        img.colorspace_settings.name = "Non-Color"
    except Exception:
        try:
            img.colorspace_settings.name = "Linear Rec.709"
        except Exception:
            pass
    return img


def build_slice2bj_scene(
    image_path="/tmp/qt_slice2bj_rgb.png",
    *,
    mode="claim",
):
    """Locked cube; Separate Color channel → Principled.Roughness.

    mode:
      claim        — CLAIM: TEX_IMAGE Color → Separate RGB.Green → Roughness
      separate_r   — same TEX, Red channel
      separate_b   — same TEX, Blue channel
      separate_const — unlinked Color (0.2, 0.55, 0.8) Separate.Green fold
      tex          — 2i regression: TEX_IMAGE → Roughness (separate enable=0)
      invert       — 2be regression
      ramp         — 2ba regression
      noise        — 2bb regression
      mix          — 2ay regression
      curves       — 2bh regression
      hdr          — 2aa regression
      hsv          — Separate mode HSV (named REFUSE Slice 2bj)
      invert_sep   — Invert.Color ← Separate.Green (named REFUSE Slice 2bj)
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)

    mode_key = str(mode).strip().lower()
    allowed = (
        "claim", "separate_r", "separate_b", "separate_const",
        "tex", "invert", "ramp", "noise", "mix", "curves", "hdr",
        "hsv", "invert_sep",
    )
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2bj)")

    if mode_key == "tex":
        import _quanttrace_rough_scene as rsc
        return rsc.build_rough_scene(image_path=image_path, socket="Roughness")
    if mode_key == "invert":
        import _quanttrace_slice2be_scene as sc
        return sc.build_slice2be_scene(image_path=image_path, mode="invert")
    if mode_key == "ramp":
        import _quanttrace_slice2ba_scene as sc
        return sc.build_slice2ba_scene(image_path=image_path, mode="ramp")
    if mode_key == "noise":
        import _quanttrace_slice2bb_scene as sc
        return sc.build_slice2bb_scene(mode="noise")
    if mode_key == "mix":
        import _quanttrace_slice2ay_scene as sc
        return sc.build_slice2ay_scene(mode="mix")
    if mode_key == "curves":
        import _quanttrace_slice2bh_scene as sc
        return sc.build_slice2bh_scene(mode="claim")
    if mode_key == "hdr":
        import _quanttrace_slice2aa_scene as sc
        return sc.build_slice2aa_scene()

    import _quanttrace_cube_scene as cube

    scene, cube_obj, lamp, cam = cube.build_locked_scene()
    mat = cube_obj.data.materials[0]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.7, 0.7, 0.7, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.5
    bsdf.inputs["Metallic"].default_value = 0.0

    sep = nt.nodes.new("ShaderNodeSeparateColor")
    sep.mode = "RGB"
    sep.label = "qt_separate_rough"

    if mode_key == "hsv":
        sep.mode = "HSV"
        img = _write_rgb_channel_png(image_path)
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        tex.label = "qt_sep_tex"
        nt.links.new(tex.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key == "invert_sep":
        img = _write_rgb_channel_png(image_path)
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        tex.label = "qt_sep_tex"
        inv = nt.nodes.new("ShaderNodeInvert")
        inv.label = "qt_invert_over_sep"
        fac = inv.inputs.get("Fac") or inv.inputs.get("Factor")
        fac.default_value = 1.0
        nt.links.new(tex.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], inv.inputs["Color"])
        nt.links.new(inv.outputs["Color"], bsdf.inputs["Roughness"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key == "separate_const":
        col = sep.inputs.get("Color")
        col.default_value = (0.2, 0.55, 0.8, 1.0)
        nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, None

    img = _write_rgb_channel_png(image_path)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = "Linear"
    tex.extension = "REPEAT"
    tex.projection = "FLAT"
    tex.label = "qt_sep_tex"
    nt.links.new(tex.outputs["Color"], sep.inputs["Color"])
    chan = {
        "claim": "Green",
        "separate_r": "Red",
        "separate_b": "Blue",
    }[mode_key]
    nt.links.new(sep.outputs[chan], bsdf.inputs["Roughness"])
    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--mode",
        default="claim",
        choices=(
            "claim", "separate_r", "separate_b", "separate_const",
            "tex", "invert", "ramp", "noise", "mix", "curves", "hdr",
            "hsv", "invert_sep",
        ),
    )
    p.add_argument("--image", default="/tmp/qt_slice2bj_rgb.png")
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2bj_stock.exr")
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2bj_scene(
        image_path=args.image, mode=args.mode,
    )
    print("QUANTTRACE_SLICE2BJ", cube_obj.name, "mode", args.mode)
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2BJ wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
