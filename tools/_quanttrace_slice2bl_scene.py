# QuantTrace Slice 2bl: Separate Color → Bump.Height → Principled.Normal.
from __future__ import annotations
import argparse, os, struct, sys, zlib
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1 :] if "--" in a else []


def _write_rgb_blue_height_png(path, n=16, lo=0.15, hi=0.9):
    """Non-Color RGB: Blue = height hill; Red=10; Green=40.

    Proves Separate.Blue ≠ CF-gray(Color) and ≠ Red/Green.
    """
    rgb = bytearray()
    for y in range(n):
        for x in range(n):
            u = (x + 0.5) / n * 2.0 - 1.0
            v = (y + 0.5) / n * 2.0 - 1.0
            r2 = u * u + v * v
            t = max(0.0, 1.0 - r2 / 0.55)
            h = lo + (hi - lo) * (t * t)
            b8 = max(0, min(255, int(round(h * 255.0))))
            rgb.extend((10, 40, b8))

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


def build_slice2bl_scene(
    image_path="/tmp/qt_slice2bl_blue_height.png",
    *,
    mode="claim",
):
    """Locked cube; Separate Color channel → Bump.Height → Principled.Normal.

    mode:
      claim          — CLAIM: TEX_IMAGE Color → Separate RGB.Blue → Bump.Height
      separate_r     — same TEX, Red channel
      separate_g     — same TEX, Green channel
      separate_const — unlinked Color (0.2, 0.55, 0.8) Separate.Blue fold
      bump           — 2x regression: Bump Height ← TEX_IMAGE (separate enable=0)
      noise          — 2bc regression
      separate_rough — 2bj regression
      mix            — 2ay regression
      invert         — 2be regression
      hdr            — 2aa regression
      hsv            — Separate mode HSV (named REFUSE Slice 2bl)
      invert_sep     — Invert.Color ← Separate.Blue → Height (named REFUSE)
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)

    mode_key = str(mode).strip().lower()
    allowed = (
        "claim", "separate_r", "separate_g", "separate_const",
        "bump", "noise", "separate_rough", "mix", "invert", "hdr",
        "hsv", "invert_sep",
    )
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2bl)")

    if mode_key == "bump":
        import _quanttrace_slice2x_scene as sc2x
        return sc2x.build_slice2x_scene(image_path=image_path, socket="Bump")
    if mode_key == "noise":
        import _quanttrace_slice2bc_scene as sc
        return sc.build_slice2bc_scene(mode="noise")
    if mode_key == "separate_rough":
        import _quanttrace_slice2bj_scene as sc
        return sc.build_slice2bj_scene(image_path=image_path, mode="claim")
    if mode_key == "mix":
        import _quanttrace_slice2ay_scene as sc
        return sc.build_slice2ay_scene(mode="mix")
    if mode_key == "invert":
        import _quanttrace_slice2be_scene as sc
        return sc.build_slice2be_scene(image_path=image_path, mode="invert")
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
    sep.label = "qt_separate_bump"

    bump = nt.nodes.new("ShaderNodeBump")
    bump.label = "qt_bump"
    bump.invert = False
    # loft-ish strength; Distance stays RNA default 0.001
    if "Strength" in bump.inputs:
        bump.inputs["Strength"].default_value = 1.0

    if mode_key == "hsv":
        sep.mode = "HSV"
        img = _write_rgb_blue_height_png(image_path)
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        tex.label = "qt_sep_tex"
        nt.links.new(tex.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Blue"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key == "invert_sep":
        img = _write_rgb_blue_height_png(image_path)
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        tex.label = "qt_sep_tex"
        inv = nt.nodes.new("ShaderNodeInvert")
        inv.label = "qt_invert_over_sep"
        fac = inv.inputs.get("Fac") or inv.inputs.get("Factor")
        fac.default_value = 1.0
        nt.links.new(tex.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Blue"], inv.inputs["Color"])
        nt.links.new(inv.outputs["Color"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key == "separate_const":
        col = sep.inputs.get("Color")
        col.default_value = (0.2, 0.55, 0.8, 1.0)
        nt.links.new(sep.outputs["Blue"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, None

    img = _write_rgb_blue_height_png(image_path)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = "Linear"
    tex.extension = "REPEAT"
    tex.projection = "FLAT"
    tex.label = "qt_sep_tex"
    nt.links.new(tex.outputs["Color"], sep.inputs["Color"])
    chan = {
        "claim": "Blue",
        "separate_r": "Red",
        "separate_g": "Green",
    }[mode_key]
    nt.links.new(sep.outputs[chan], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--mode",
        default="claim",
        choices=(
            "claim", "separate_r", "separate_g", "separate_const",
            "bump", "noise", "separate_rough", "mix", "invert", "hdr",
            "hsv", "invert_sep",
        ),
    )
    p.add_argument("--image", default="/tmp/qt_slice2bl_blue_height.png")
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2bl_stock.exr")
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2bl_scene(
        image_path=args.image, mode=args.mode,
    )
    print("QUANTTRACE_SLICE2BL", cube_obj.name, "mode", args.mode)
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2BL wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
