# QuantTrace Slice 2r: locked cube + TEX_IMAGE on Principled Emission Color.
from __future__ import annotations
import argparse, os, struct, sys, zlib
import bpy

def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def _write_srgb_checker_png(path, n=8):
    """8-bit sRGB checker (chromatic, like Slice 2f Base Color)."""
    rgb = bytearray()
    for y in range(n):
        for x in range(n):
            if ((x // 2) + (y // 2)) % 2 == 0:
                rgb.extend((220, 30, 20))
            else:
                rgb.extend((20, 40, 210))
    def chunk(tag, data):
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)
    raw = b""
    row = n * 3
    for y in range(n):
        raw += b"\x00" + bytes(rgb[y * row:(y + 1) * row])
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n")
        f.write(chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 2, 0, 0, 0)))
        f.write(chunk(b"IDAT", zlib.compress(bytes(raw), 9)))
        f.write(chunk(b"IEND", b""))
    img = bpy.data.images.load(path)
    return img


def _write_gray_checker_png(path, n=8, lo=40, hi=220):
    """8-bit grayscale checker (Non-Color) for Emission Strength."""
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
        raw += b"\x00" + bytes(rgb[y * row:(y + 1) * row])
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


def _bsdf_input(bsdf, *names):
    for n in names:
        sock = bsdf.inputs.get(n)
        if sock is not None:
            return n, sock
    raise KeyError(names)


def build_emitcolor_scene(
    image_path="/tmp/qt_emitcolor_checker.png",
    *,
    socket="Color",
    strength_image_path="/tmp/qt_emitcolor_str_checker.png",
    base_color=(0.7, 0.7, 0.7),
    const_roughness=0.5,
    const_metallic=0.0,
    const_ior=1.45,
    const_alpha=1.0,
    const_emit=1.0,
):
    """Locked cube; TEX_IMAGE Color → Principled Emission Color.

    socket: 'Color' | 'Color+Strength'
    Color: sRGB checker → Emission Color; Strength unlinked constant 1.0.
    Color+Strength: same Color map + Non-Color gray checker → Emission Strength.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_cube_scene as cube

    scene, cube_obj, lamp, cam = cube.build_locked_scene()
    img = _write_srgb_checker_png(image_path)
    px = list(img.pixels)
    print(
        "QUANTTRACE_EMITCOLOR_IMG", image_path, "size", list(img.size),
        "cs", img.colorspace_settings.name,
        "px_min", min(px), "px_max", max(px),
    )
    mat = cube_obj.data.materials[0]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (
        float(base_color[0]), float(base_color[1]), float(base_color[2]), 1.0,
    )
    bsdf.inputs["Roughness"].default_value = float(const_roughness)
    bsdf.inputs["Metallic"].default_value = float(const_metallic)
    bsdf.inputs["IOR"].default_value = float(const_ior)
    bsdf.inputs["Alpha"].default_value = float(const_alpha)

    color_name, color_sock = _bsdf_input(bsdf, "Emission Color", "Emission")
    str_name, str_sock = _bsdf_input(bsdf, "Emission Strength")
    sock = str(socket)
    str_sock.default_value = float(const_emit)

    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = "Linear"
    tex.extension = "REPEAT"
    tex.projection = "FLAT"
    tex.label = "qt_emit_color_tex"
    nt.links.new(tex.outputs["Color"], color_sock)

    str_img = None
    if sock == "Color":
        pass
    elif sock == "Color+Strength":
        str_img = _write_gray_checker_png(strength_image_path)
        texs = nt.nodes.new("ShaderNodeTexImage")
        texs.image = str_img
        texs.interpolation = "Linear"
        texs.extension = "REPEAT"
        texs.projection = "FLAT"
        texs.label = "qt_emit_str_tex"
        nt.links.new(texs.outputs["Color"], str_sock)
    else:
        raise ValueError(f"unknown socket {sock!r}")

    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img, str_img


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_emitcolor_stock.exr")
    p.add_argument("--image", default="/tmp/qt_emitcolor_checker.png")
    p.add_argument("--str-image", default="/tmp/qt_emitcolor_str_checker.png")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument(
        "--socket",
        choices=("Color", "Color+Strength"),
        default="Color",
    )
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img, str_img = build_emitcolor_scene(
        image_path=args.image, socket=args.socket,
        strength_image_path=args.str_image,
    )
    cs = getattr(img, "colorspace_settings", None)
    print(
        "QUANTTRACE_EMITCOLOR", cube_obj.name, "socket", args.socket,
        "image", img.filepath, "cs", getattr(cs, "name", None),
        "uvs", len(cube_obj.data.uv_layers),
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_EMITCOLOR wrote", args.out)
    return 0

if __name__ == "__main__":
    raise SystemExit(main() or 0)
