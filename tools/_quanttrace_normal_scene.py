# QuantTrace Slice 2j: locked cube + Normal Map ← TEX_IMAGE on Principled Normal.
from __future__ import annotations
import argparse, math, os, struct, sys, zlib
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def _write_tangent_normal_png(path, n=16):
    """Tiny tangent-space normal map: mostly (0.5, 0.5, 1.0) + a center bump.

    Encoded 8-bit RGB, Non-Color. Flat = (128, 128, 255). Center pixels
    tilt so Combined differs from a geometric-normal cube.
    """
    rgb = bytearray()
    for y in range(n):
        for x in range(n):
            u = (x + 0.5) / n * 2.0 - 1.0
            v = (y + 0.5) / n * 2.0 - 1.0
            r2 = u * u + v * v
            if r2 < 0.55:
                nx = u * 0.65
                ny = v * 0.65
                nz2 = max(1e-6, 1.0 - nx * nx - ny * ny)
                nz = math.sqrt(nz2)
                length = math.sqrt(nx * nx + ny * ny + nz * nz)
                nx, ny, nz = nx / length, ny / length, nz / length
            else:
                nx, ny, nz = 0.0, 0.0, 1.0
            r = max(0, min(255, int(round((nx * 0.5 + 0.5) * 255.0))))
            g = max(0, min(255, int(round((ny * 0.5 + 0.5) * 255.0))))
            b = max(0, min(255, int(round((nz * 0.5 + 0.5) * 255.0))))
            rgb.extend((r, g, b))

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


def build_normal_scene(
    image_path="/tmp/qt_normal_map.png",
    *,
    strength=1.0,
    base_color=(0.7, 0.7, 0.7),
):
    """Locked cube; TEX_IMAGE Color → Normal Map (Tangent) → Principled Normal."""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_cube_scene as cube

    scene, cube_obj, lamp, cam = cube.build_locked_scene()
    img = _write_tangent_normal_png(image_path)
    px = list(img.pixels)
    print(
        "QUANTTRACE_NORMAL_IMG", image_path, "size", list(img.size),
        "cs", img.colorspace_settings.name,
        "px_min", min(px), "px_max", max(px),
    )
    mat = cube_obj.data.materials[0]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (
        float(base_color[0]), float(base_color[1]), float(base_color[2]), 1.0,
    )
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = "Linear"
    tex.extension = "REPEAT"
    tex.projection = "FLAT"
    tex.label = "qt_normal_tex"
    nmap = nt.nodes.new("ShaderNodeNormalMap")
    nmap.space = "TANGENT"
    nmap.inputs["Strength"].default_value = float(strength)
    nmap.label = "qt_normal_map"
    nt.links.new(tex.outputs["Color"], nmap.inputs["Color"])
    nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_normal_stock.exr")
    p.add_argument("--image", default="/tmp/qt_normal_map.png")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--strength", type=float, default=1.0)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_normal_scene(
        image_path=args.image, strength=args.strength,
    )
    cs = getattr(img, "colorspace_settings", None)
    print(
        "QUANTTRACE_NORMAL", cube_obj.name,
        "image", img.filepath, "cs", getattr(cs, "name", None),
        "uvs", len(cube_obj.data.uv_layers),
        "strength", args.strength,
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_NORMAL wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
