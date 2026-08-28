# QuantTrace Slice 2i: locked cube + TEX_IMAGE on Principled Roughness / Metallic.
from __future__ import annotations
import argparse, os, struct, sys, zlib
import bpy

def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def _write_gray_checker_png(path, n=8, lo=40, hi=220):
    """8-bit grayscale checker (Non-Color data map) without bpy generate."""
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
    # Data map: Non-Color so values stay linear (match typical Roughness/Metallic).
    try:
        img.colorspace_settings.name = "Non-Color"
    except Exception:
        try:
            img.colorspace_settings.name = "Linear Rec.709"
        except Exception:
            pass
    return img


def build_rough_scene(
    image_path="/tmp/qt_rough_checker.png",
    *,
    socket="Roughness",
    base_color=(0.7, 0.7, 0.7),
    const_roughness=0.5,
    const_metallic=0.0,
    also_metallic=False,
):
    """Locked cube; TEX_IMAGE Color → Principled Roughness and/or Metallic.

    socket: 'Roughness' | 'Metallic' | 'Both'
    also_metallic: if True and socket==Roughness, wire same image to Metallic too.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_cube_scene as cube

    scene, cube_obj, lamp, cam = cube.build_locked_scene()
    img = _write_gray_checker_png(image_path)
    px = list(img.pixels)
    print(
        "QUANTTRACE_ROUGH_IMG", image_path, "size", list(img.size),
        "cs", img.colorspace_settings.name,
        "px_min", min(px), "px_max", max(px),
    )
    mat = cube_obj.data.materials[0]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    # Constant base color (no Base Color TEX_IMAGE unless regression tools add it).
    bsdf.inputs["Base Color"].default_value = (
        float(base_color[0]), float(base_color[1]), float(base_color[2]), 1.0,
    )
    bsdf.inputs["Roughness"].default_value = float(const_roughness)
    bsdf.inputs["Metallic"].default_value = float(const_metallic)

    sock = str(socket)
    targets = []
    if sock in ("Roughness", "Both") or also_metallic and sock == "Roughness":
        targets.append("Roughness")
    if sock in ("Metallic", "Both") or also_metallic:
        if "Metallic" not in targets:
            targets.append("Metallic")
    if sock == "Metallic":
        targets = ["Metallic"]
    if sock == "Both":
        targets = ["Roughness", "Metallic"]

    for tgt in targets:
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        tex.interpolation = "Linear"
        tex.extension = "REPEAT"
        tex.projection = "FLAT"
        tex.label = f"qt_{tgt.lower()}_tex"
        # Separate TEX_IMAGE node per socket (same disk filepath / Vector unlinked).
        nt.links.new(tex.outputs["Color"], bsdf.inputs[tgt])

    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_rough_stock.exr")
    p.add_argument("--image", default="/tmp/qt_rough_checker.png")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument(
        "--socket",
        choices=("Roughness", "Metallic", "Both"),
        default="Roughness",
    )
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_rough_scene(
        image_path=args.image, socket=args.socket,
    )
    cs = getattr(img, "colorspace_settings", None)
    print(
        "QUANTTRACE_ROUGH", cube_obj.name, "socket", args.socket,
        "image", img.filepath, "cs", getattr(cs, "name", None),
        "uvs", len(cube_obj.data.uv_layers),
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_ROUGH wrote", args.out)
    return 0

if __name__ == "__main__":
    raise SystemExit(main() or 0)
