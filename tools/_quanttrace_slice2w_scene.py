# QuantTrace Slice 2w: locked cube + TEX_IMAGE on Anisotropic / Rotation / Tangent.
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


def _bsdf_input(bsdf, *names):
    for n in names:
        sock = bsdf.inputs.get(n)
        if sock is not None:
            return n, sock
        for s in bsdf.inputs:
            if getattr(s, "name", None) == n or getattr(s, "identifier", None) == n:
                return n, s
    raise KeyError(names)


def _link_tex(nt, img, tgt_sock, label):
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = "Linear"
    tex.extension = "REPEAT"
    tex.projection = "FLAT"
    tex.label = label
    nt.links.new(tex.outputs["Color"], tgt_sock)


def build_slice2w_scene(
    image_path="/tmp/qt_slice2w_gray.png",
    *,
    socket="Aniso",
    base_color=(0.7, 0.7, 0.7),
    const_roughness=0.2,
    const_metallic=1.0,
    const_ior=1.45,
    const_alpha=1.0,
):
    """Locked cube; TEX_IMAGE on Anisotropic / Anisotropic Rotation / Tangent.

    socket: Aniso | AnisoRot | Tangent | Combo | DiffuseRough
    Aniso/AnisoRot/Tangent/Combo pin Metallic=1 Roughness=0.2 (GGX highlight visibility).
    DiffuseRough is 2v regression (metallic default 0).
    Combo = Anisotropic + Anisotropic Rotation TEX_IMAGE.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_cube_scene as cube

    scene, cube_obj, lamp, cam = cube.build_locked_scene()
    gray = _write_gray_checker_png(image_path)
    px = list(gray.pixels)
    print(
        "QUANTTRACE_SLICE2W_IMG", image_path, "size", list(gray.size),
        "cs", gray.colorspace_settings.name,
        "px_min", min(px), "px_max", max(px),
    )
    mat = cube_obj.data.materials[0]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (
        float(base_color[0]), float(base_color[1]), float(base_color[2]), 1.0,
    )
    sock = str(socket)
    # DiffuseRough regression keeps metallic=0 (2v defaults); aniso sockets need metal.
    if sock == "DiffuseRough":
        metal = 0.0
        rough = float(const_roughness)
    else:
        metal = float(const_metallic)
        rough = float(const_roughness)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    bsdf.inputs["IOR"].default_value = float(const_ior)
    bsdf.inputs["Alpha"].default_value = float(const_alpha)

    aniso_name, aniso = _bsdf_input(bsdf, "Anisotropic")
    aniso_rot_name, aniso_rot = _bsdf_input(bsdf, "Anisotropic Rotation")
    tangent_name, tangent = _bsdf_input(bsdf, "Tangent")
    diff_r_name, diff_r = _bsdf_input(bsdf, "Diffuse Roughness")

    if sock == "Aniso":
        _link_tex(nt, gray, aniso, "qt_aniso_tex")
    elif sock == "AnisoRot":
        # Pin Anisotropic=1 so Rotation is visible (Cycles disconnects when 0).
        aniso.default_value = 1.0
        _link_tex(nt, gray, aniso_rot, "qt_aniso_rot_tex")
    elif sock == "Tangent":
        aniso.default_value = 1.0
        _link_tex(nt, gray, tangent, "qt_tangent_tex")
    elif sock == "Combo":
        _link_tex(nt, gray, aniso, "qt_aniso_tex")
        _link_tex(nt, gray, aniso_rot, "qt_aniso_rot_tex")
    elif sock == "DiffuseRough":
        _link_tex(nt, gray, diff_r, "qt_diffuse_rough_tex")
    else:
        raise ValueError(f"unknown socket {sock!r}")

    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, gray


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2w_stock.exr")
    p.add_argument("--image", default="/tmp/qt_slice2w_gray.png")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument(
        "--socket",
        choices=("Aniso", "AnisoRot", "Tangent", "Combo", "DiffuseRough"),
        default="Aniso",
    )
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, gray = build_slice2w_scene(
        image_path=args.image, socket=args.socket,
    )
    print(
        "QUANTTRACE_SLICE2W", cube_obj.name, "socket", args.socket,
        "gray", gray.filepath, "uvs", len(cube_obj.data.uv_layers),
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2W wrote", args.out)
    return 0

if __name__ == "__main__":
    raise SystemExit(main() or 0)
