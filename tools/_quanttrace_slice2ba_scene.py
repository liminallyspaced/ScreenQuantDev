# QuantTrace Slice 2ba: ColorRamp -> Principled.Roughness.
from __future__ import annotations
import argparse, os, struct, sys, zlib
import bpy


# Loft Plane / mat '0' ColorRamp (LINEAR, Color out, 2 stops).
LOFT_STOP0 = (0.254546, (0.0, 0.0, 0.0, 1.0))
LOFT_STOP1 = (0.822727, (1.0, 1.0, 1.0, 1.0))


def _argv():
    a = sys.argv
    return a[a.index("--") + 1 :] if "--" in a else []


def _write_gray_checker_png(path, n=8, lo=40, hi=220):
    rgb = bytearray()
    for y in range(n):
        for x in range(n):
            v = lo if ((x // 2) + (y // 2)) % 2 == 0 else hi
            rgb.extend((v, v, v))

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


def _loft_colorramp(nt, interpolation="LINEAR"):
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.label = "qt_colorramp"
    cr = ramp.color_ramp
    cr.interpolation = interpolation
    # Default ColorRamp has 2 elements; set them to loft Plane stops.
    els = cr.elements
    while len(els) > 2:
        els.remove(els[-1])
    while len(els) < 2:
        els.new(0.5)
    els[0].position = LOFT_STOP0[0]
    els[0].color = LOFT_STOP0[1]
    els[1].position = LOFT_STOP1[0]
    els[1].color = LOFT_STOP1[1]
    return ramp


def build_slice2ba_scene(
    image_path="/tmp/qt_slice2ba_fac.png",
    *,
    mode="ramp",
):
    """Locked cube; ColorRamp -> Principled.Roughness.

    mode:
      ramp         — CLAIM: loft LINEAR ColorRamp, Fac <- Non-Color TEX_IMAGE
      fac_unlinked — ColorRamp Fac unlinked (default 0.5)
      ramp_const   — alias of fac_unlinked
      tex          — 2i regression: TEX_IMAGE -> Roughness, no ColorRamp
      bevel        — 2az regression
      mix          — 2ay regression
      point        — 2av regression
      hdr          — 2aa regression
      noise        — Noise -> ColorRamp Fac (named REFUSE)
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)

    mode_key = str(mode).strip().lower()
    if mode_key == "ramp_const":
        mode_key = "fac_unlinked"
    allowed = (
        "ramp", "fac_unlinked", "tex", "bevel", "mix", "point", "hdr", "noise",
    )
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2ba)")

    if mode_key == "tex":
        import _quanttrace_rough_scene as rsc
        return rsc.build_rough_scene(image_path=image_path, socket="Roughness")
    if mode_key == "bevel":
        import _quanttrace_slice2az_scene as sc
        return sc.build_slice2az_scene(mode="bevel")
    if mode_key == "mix":
        import _quanttrace_slice2ay_scene as sc
        return sc.build_slice2ay_scene(mode="mix")
    if mode_key == "point":
        import _quanttrace_slice2av_scene as sc
        return sc.build_slice2av_scene(
            image_path="/tmp/qt_slice2av_env.exr", mode="point"
        )
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

    ramp = _loft_colorramp(nt, interpolation="LINEAR")
    img = None

    if mode_key == "noise":
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.label = "qt_noise_fac"
        nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Roughness"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key == "ramp":
        img = _write_gray_checker_png(image_path)
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        tex.interpolation = "Linear"
        tex.extension = "REPEAT"
        tex.projection = "FLAT"
        tex.label = "qt_ramp_fac_tex"
        nt.links.new(tex.outputs["Color"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Roughness"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    # fac_unlinked
    ramp.inputs["Fac"].default_value = 0.5
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Roughness"])
    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--mode",
        default="ramp",
        choices=(
            "ramp", "fac_unlinked", "ramp_const", "tex", "bevel",
            "mix", "point", "hdr", "noise",
        ),
    )
    p.add_argument("--image", default="/tmp/qt_slice2ba_fac.png")
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2ba_stock.exr")
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2ba_scene(
        image_path=args.image, mode=args.mode,
    )
    print("QUANTTRACE_SLICE2BA", cube_obj.name, "mode", args.mode)
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2BA wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
