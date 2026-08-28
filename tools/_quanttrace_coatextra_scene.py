# QuantTrace Slice 2s: locked cube + TEX_IMAGE on Coat Rough/IOR/Tint + Sheen Rough/Tint.
from __future__ import annotations
import argparse, os, struct, sys, zlib
import bpy

def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


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


def _write_srgb_checker_png(path, n=8):
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
    return bpy.data.images.load(path)


def _bsdf_input(bsdf, *names):
    for n in names:
        sock = bsdf.inputs.get(n)
        if sock is not None:
            return n, sock
    raise KeyError(names)


def _link_tex(nt, img, tgt_sock, label):
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = "Linear"
    tex.extension = "REPEAT"
    tex.projection = "FLAT"
    tex.label = label
    nt.links.new(tex.outputs["Color"], tgt_sock)


def build_coatextra_scene(
    image_path="/tmp/qt_coatextra_gray.png",
    *,
    socket="CoatRough",
    tint_image_path="/tmp/qt_coatextra_tint.png",
    base_color=(0.7, 0.7, 0.7),
    const_roughness=0.2,
    const_metallic=0.0,
    const_ior=1.45,
    const_alpha=1.0,
    const_coat=1.0,
    const_sheen=1.0,
):
    """Locked cube; TEX_IMAGE on Coat Roughness/IOR/Tint and Sheen Roughness/Tint.

    socket: CoatRough | CoatIOR | CoatTint | SheenRough | SheenTint | Combo
    Coat* pins Coat Weight=1 (unlinked). Sheen* pins Sheen Weight=1.
    Combo maps Coat Roughness + Sheen Roughness with both weights 1.
    Tint sockets use an sRGB checker; float sockets use Non-Color gray.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_cube_scene as cube

    scene, cube_obj, lamp, cam = cube.build_locked_scene()
    gray = _write_gray_checker_png(image_path)
    tint = None
    px = list(gray.pixels)
    print(
        "QUANTTRACE_COATEXTRA_IMG", image_path, "size", list(gray.size),
        "cs", gray.colorspace_settings.name,
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

    coat_w_name, coat_w = _bsdf_input(bsdf, "Coat Weight", "Coat", "Clearcoat")
    sheen_w_name, sheen_w = _bsdf_input(bsdf, "Sheen Weight", "Sheen")
    coat_r_name, coat_r = _bsdf_input(bsdf, "Coat Roughness")
    coat_i_name, coat_i = _bsdf_input(bsdf, "Coat IOR")
    coat_t_name, coat_t = _bsdf_input(bsdf, "Coat Tint")
    sheen_r_name, sheen_r = _bsdf_input(bsdf, "Sheen Roughness")
    sheen_t_name, sheen_t = _bsdf_input(bsdf, "Sheen Tint")

    sock = str(socket)
    coat_w.default_value = 0.0
    sheen_w.default_value = 0.0

    if sock == "CoatRough":
        coat_w.default_value = float(const_coat)
        _link_tex(nt, gray, coat_r, "qt_coat_rough_tex")
    elif sock == "CoatIOR":
        coat_w.default_value = float(const_coat)
        _link_tex(nt, gray, coat_i, "qt_coat_ior_tex")
    elif sock == "CoatTint":
        coat_w.default_value = float(const_coat)
        tint = _write_srgb_checker_png(tint_image_path)
        _link_tex(nt, tint, coat_t, "qt_coat_tint_tex")
    elif sock == "SheenRough":
        sheen_w.default_value = float(const_sheen)
        _link_tex(nt, gray, sheen_r, "qt_sheen_rough_tex")
    elif sock == "SheenTint":
        sheen_w.default_value = float(const_sheen)
        tint = _write_srgb_checker_png(tint_image_path)
        _link_tex(nt, tint, sheen_t, "qt_sheen_tint_tex")
    elif sock == "Combo":
        coat_w.default_value = float(const_coat)
        sheen_w.default_value = float(const_sheen)
        _link_tex(nt, gray, coat_r, "qt_coat_rough_tex")
        _link_tex(nt, gray, sheen_r, "qt_sheen_rough_tex")
    else:
        raise ValueError(f"unknown socket {sock!r}")

    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, gray, tint


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_coatextra_stock.exr")
    p.add_argument("--image", default="/tmp/qt_coatextra_gray.png")
    p.add_argument("--tint-image", default="/tmp/qt_coatextra_tint.png")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument(
        "--socket",
        choices=("CoatRough", "CoatIOR", "CoatTint", "SheenRough", "SheenTint", "Combo"),
        default="CoatRough",
    )
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, gray, tint = build_coatextra_scene(
        image_path=args.image, socket=args.socket,
        tint_image_path=args.tint_image,
    )
    print(
        "QUANTTRACE_COATEXTRA", cube_obj.name, "socket", args.socket,
        "gray", gray.filepath, "uvs", len(cube_obj.data.uv_layers),
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_COATEXTRA wrote", args.out)
    return 0

if __name__ == "__main__":
    raise SystemExit(main() or 0)
