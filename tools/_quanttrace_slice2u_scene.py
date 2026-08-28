# QuantTrace Slice 2u: locked cube + TEX_IMAGE on Specular Tint / Thin Film / Subsurface.
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


def _write_float_checker_exr(path, n=8, lo=200.0, hi=800.0):
    """Non-Color float checker (nm for Thin Film Thickness). bpy save, not stdlib EXR."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    img = bpy.data.images.new(
        "qt_film_thick", width=n, height=n, alpha=True, float_buffer=True, is_data=True,
    )
    px = [0.0] * (n * n * 4)
    for y in range(n):
        for x in range(n):
            v = lo if ((x // 2) + (y // 2)) % 2 == 0 else hi
            i = (y * n + x) * 4
            px[i:i + 4] = [v, v, v, 1.0]
    img.pixels = px
    try:
        img.colorspace_settings.name = "Non-Color"
    except Exception:
        try:
            img.colorspace_settings.name = "Linear Rec.709"
        except Exception:
            pass
    img.filepath_raw = path
    img.file_format = "OPEN_EXR"
    img.save()
    print("QUANTTRACE_SLICE2U_THICK_EXR", path, "lo", lo, "hi", hi, "n", n)
    return img


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


def build_slice2u_scene(
    image_path="/tmp/qt_slice2u_gray.png",
    *,
    socket="SpecTint",
    tint_image_path="/tmp/qt_slice2u_tint.png",
    thick_image_path="/tmp/qt_slice2u_thick.exr",
    base_color=(0.7, 0.7, 0.7),
    const_roughness=0.2,
    const_metallic=0.0,
    const_ior=1.45,
    const_alpha=1.0,
    const_sss=1.0,
    const_film_thick=400.0,
):
    """Locked cube; TEX_IMAGE on Specular Tint / Thin Film / Subsurface sockets.

    socket: SpecTint | FilmThick | FilmIOR | SSSWeight | SSSRadius | SSSScale | Combo
    FilmIOR pins Thickness=400 nm (unlinked). SSS extras pin Weight=1.
    Combo maps Specular Tint + Thin Film Thickness.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_cube_scene as cube

    scene, cube_obj, lamp, cam = cube.build_locked_scene()
    gray = _write_gray_checker_png(image_path)
    tint = None
    thick = None
    px = list(gray.pixels)
    print(
        "QUANTTRACE_SLICE2U_IMG", image_path, "size", list(gray.size),
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

    spec_t_name, spec_t = _bsdf_input(bsdf, "Specular Tint")
    film_th_name, film_th = _bsdf_input(bsdf, "Thin Film Thickness")
    film_i_name, film_i = _bsdf_input(bsdf, "Thin Film IOR")
    sss_w_name, sss_w = _bsdf_input(bsdf, "Subsurface Weight", "Subsurface")
    sss_r_name, sss_r = _bsdf_input(bsdf, "Subsurface Radius")
    sss_s_name, sss_s = _bsdf_input(bsdf, "Subsurface Scale")

    sock = str(socket)
    sss_w.default_value = 0.0
    film_th.default_value = 0.0

    if sock == "SpecTint":
        tint = _write_srgb_checker_png(tint_image_path)
        _link_tex(nt, tint, spec_t, "qt_spec_tint_tex")
    elif sock == "FilmThick":
        thick = _write_float_checker_exr(thick_image_path)
        _link_tex(nt, thick, film_th, "qt_film_thick_tex")
    elif sock == "FilmIOR":
        film_th.default_value = float(const_film_thick)
        _link_tex(nt, gray, film_i, "qt_film_ior_tex")
    elif sock == "SSSWeight":
        _link_tex(nt, gray, sss_w, "qt_sss_weight_tex")
    elif sock == "SSSRadius":
        sss_w.default_value = float(const_sss)
        tint = _write_srgb_checker_png(tint_image_path)
        _link_tex(nt, tint, sss_r, "qt_sss_radius_tex")
    elif sock == "SSSScale":
        sss_w.default_value = float(const_sss)
        _link_tex(nt, gray, sss_s, "qt_sss_scale_tex")
    elif sock == "Combo":
        tint = _write_srgb_checker_png(tint_image_path)
        thick = _write_float_checker_exr(thick_image_path)
        _link_tex(nt, tint, spec_t, "qt_spec_tint_tex")
        _link_tex(nt, thick, film_th, "qt_film_thick_tex")
    else:
        raise ValueError(f"unknown socket {sock!r}")

    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, gray, tint, thick


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2u_stock.exr")
    p.add_argument("--image", default="/tmp/qt_slice2u_gray.png")
    p.add_argument("--tint-image", default="/tmp/qt_slice2u_tint.png")
    p.add_argument("--thick-image", default="/tmp/qt_slice2u_thick.exr")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument(
        "--socket",
        choices=("SpecTint", "FilmThick", "FilmIOR", "SSSWeight", "SSSRadius", "SSSScale", "Combo"),
        default="SpecTint",
    )
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, gray, tint, thick = build_slice2u_scene(
        image_path=args.image, socket=args.socket,
        tint_image_path=args.tint_image, thick_image_path=args.thick_image,
    )
    print(
        "QUANTTRACE_SLICE2U", cube_obj.name, "socket", args.socket,
        "gray", gray.filepath, "uvs", len(cube_obj.data.uv_layers),
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2U wrote", args.out)
    return 0

if __name__ == "__main__":
    raise SystemExit(main() or 0)
