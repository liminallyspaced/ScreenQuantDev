# QuantTrace Slice 2x: locked cube + Bump ← TEX_IMAGE Height on Principled Normal.
from __future__ import annotations
import argparse, os, struct, sys, zlib
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def _write_height_hill_png(path, n=16, lo=0.15, hi=0.9):
    """16x16 Non-Color gray height: 0.15 outside, 0.9 center hill.

    Combined must NOT be constant / all-zero if Bump graph is live.
    """
    rgb = bytearray()
    for y in range(n):
        for x in range(n):
            u = (x + 0.5) / n * 2.0 - 1.0
            v = (y + 0.5) / n * 2.0 - 1.0
            r2 = u * u + v * v
            t = max(0.0, 1.0 - r2 / 0.55)
            h = lo + (hi - lo) * (t * t)
            v8 = max(0, min(255, int(round(h * 255.0))))
            rgb.extend((v8, v8, v8))

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


def build_slice2x_scene(
    image_path="/tmp/qt_slice2x_height.png",
    *,
    socket="Bump",
    base_color=(0.7, 0.7, 0.7),
    invert=False,
):
    """Locked cube; Bump Height TEX_IMAGE, or 2j/2w regression sockets.

    socket: Bump | NormalMap | Aniso
    Bump pins Roughness=0.5 Metallic=0 (visibility). Strength/Distance RNA defaults.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)

    sock = str(socket)
    if sock == "NormalMap":
        import _quanttrace_normal_scene as nsc
        return nsc.build_normal_scene(image_path=image_path, base_color=base_color)
    if sock == "Aniso":
        import _quanttrace_slice2w_scene as sc2w
        return sc2w.build_slice2w_scene(image_path=image_path, socket="Aniso")

    import _quanttrace_cube_scene as cube
    scene, cube_obj, lamp, cam = cube.build_locked_scene()
    img = _write_height_hill_png(image_path)
    px = list(img.pixels)
    print(
        "QUANTTRACE_SLICE2X_IMG", image_path, "size", list(img.size),
        "cs", img.colorspace_settings.name,
        "px_min", min(px), "px_max", max(px),
    )
    mat = cube_obj.data.materials[0]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (
        float(base_color[0]), float(base_color[1]), float(base_color[2]), 1.0,
    )
    bsdf.inputs["Roughness"].default_value = 0.5
    bsdf.inputs["Metallic"].default_value = 0.0

    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = "Linear"
    tex.extension = "REPEAT"
    tex.projection = "FLAT"
    tex.label = "qt_bump_height"
    bump = nt.nodes.new("ShaderNodeBump")
    bump.invert = bool(invert)
    bump.label = "qt_bump"
    print(
        "QUANTTRACE_SLICE2X_BUMP invert", bump.invert,
        "strength", bump.inputs["Strength"].default_value,
        "distance", bump.inputs["Distance"].default_value,
        "height", bump.inputs["Height"].default_value,
        "str_linked", bump.inputs["Strength"].is_linked,
        "dist_linked", bump.inputs["Distance"].is_linked,
        "n_linked", bump.inputs["Normal"].is_linked,
    )
    nt.links.new(tex.outputs["Color"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2x_stock.exr")
    p.add_argument("--image", default="/tmp/qt_slice2x_height.png")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument(
        "--socket",
        choices=("Bump", "NormalMap", "Aniso"),
        default="Bump",
    )
    p.add_argument("--invert", action="store_true", default=False)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2x_scene(
        image_path=args.image, socket=args.socket, invert=args.invert,
    )
    print(
        "QUANTTRACE_SLICE2X", cube_obj.name, "socket", args.socket,
        "img", getattr(img, "filepath", None),
        "uvs", len(cube_obj.data.uv_layers),
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2X wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
