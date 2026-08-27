# QuantTrace Slice 2f: locked cube + TEX_IMAGE on Principled Base Color.
from __future__ import annotations
import argparse, os, struct, sys, zlib
import bpy

def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def _write_checker_png(path, n=8):
    """8-bit sRGB checker written without bpy (avoids empty generated EXR)."""
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


def build_tex_scene(image_path="/tmp/qt_checker.png"):
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_cube_scene as cube
    scene, cube_obj, lamp, cam = cube.build_locked_scene()
    img = _write_checker_png(image_path)
    px = list(img.pixels)
    print("QUANTTRACE_TEX_IMG", image_path, "size", list(img.size),
          "cs", img.colorspace_settings.name,
          "px_min", min(px), "px_max", max(px))
    mat = cube_obj.data.materials[0]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = "Linear"
    tex.extension = "REPEAT"
    tex.projection = "FLAT"
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_tex_stock.exr")
    p.add_argument("--image", default="/tmp/qt_checker.png")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_tex_scene(image_path=args.image)
    cs = getattr(img, "colorspace_settings", None)
    print("QUANTTRACE_TEX", cube_obj.name, "image", img.filepath,
          "cs", getattr(cs, "name", None),
          "uvs", len(cube_obj.data.uv_layers))
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_TEX wrote", args.out)
    return 0

if __name__ == "__main__":
    raise SystemExit(main() or 0)
