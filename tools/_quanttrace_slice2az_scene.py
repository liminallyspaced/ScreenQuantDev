# QuantTrace Slice 2az: Bevel → Principled.Normal (+ loft nest Bump←NormalMap).
from __future__ import annotations
import argparse, os, struct, sys, zlib
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1 :] if "--" in a else []


def _write_gray_png(path, n=16, *, hill=True, seed=0):
    """Non-Color gray PNG. hill=True → center hill; else checker for normal-ish."""
    rgb = bytearray()
    for y in range(n):
        for x in range(n):
            if hill:
                u = (x + 0.5) / n * 2.0 - 1.0
                v = (y + 0.5) / n * 2.0 - 1.0
                r2 = u * u + v * v
                t = max(0.0, 1.0 - r2 / 0.55)
                h = 0.15 + 0.75 * (t * t)
                v8 = max(0, min(255, int(round(h * 255.0))))
                rgb.extend((v8, v8, v8))
            else:
                on = ((x + y + seed) % 2) == 0
                # Fake tangent normal map-ish: mostly pointing up (0.5,0.5,1)
                if on:
                    rgb.extend((180, 180, 255))
                else:
                    rgb.extend((80, 80, 255))

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
        pass
    return img


def build_slice2az_scene(
    image_path="/tmp/qt_slice2az_height.png",
    *,
    mode="bevel",
    normal_path="/tmp/qt_slice2az_normal.png",
    radius=0.12,
    samples=4,
):
    """Locked cube; Bevel → Principled.Normal.

    mode:
      bevel       — Bevel only (CLAIM; radius non-default so graph is live)
      bevel_nmap  — NormalMap → Bevel.Normal → Principled
      bevel_bump  — Bump(Height TEX) → Bevel → Principled
      loft        — loft shape: NormalMap → Bump.Normal; Height TEX → Bump;
                    Bump → Bevel → Principled (Metal_Sheet-like)
      bump        — 2x regression (no Bevel)
      normalmap   — 2j regression
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)

    mode_key = str(mode).strip().lower()
    allowed = ("bevel", "bevel_nmap", "bevel_bump", "loft", "bump", "normalmap")
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2az)")

    if mode_key == "bump":
        import _quanttrace_slice2x_scene as sc2x
        return sc2x.build_slice2x_scene(image_path=image_path, socket="Bump")
    if mode_key == "normalmap":
        import _quanttrace_normal_scene as nsc
        return nsc.build_normal_scene(image_path=normal_path)

    import _quanttrace_cube_scene as cube

    scene, cube_obj, lamp, cam = cube.build_locked_scene()
    mat = cube_obj.data.materials[0]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.7, 0.7, 0.7, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.35
    bsdf.inputs["Metallic"].default_value = 0.0

    bevel = nt.nodes.new("ShaderNodeBevel")
    bevel.samples = int(samples)
    bevel.inputs["Radius"].default_value = float(radius)
    bevel.label = "qt_bevel"

    img = None
    if mode_key == "bevel":
        nt.links.new(bevel.outputs["Normal"], bsdf.inputs["Normal"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key == "bevel_nmap":
        img = _write_gray_png(normal_path, hill=False)
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = img
        tex.label = "qt_bevel_nmap_tex"
        nmap = nt.nodes.new("ShaderNodeNormalMap")
        nmap.space = "TANGENT"
        nmap.inputs["Strength"].default_value = 1.0
        nt.links.new(tex.outputs["Color"], nmap.inputs["Color"])
        nt.links.new(nmap.outputs["Normal"], bevel.inputs["Normal"])
        nt.links.new(bevel.outputs["Normal"], bsdf.inputs["Normal"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    # bump height image
    img = _write_gray_png(image_path, hill=True)
    tex_h = nt.nodes.new("ShaderNodeTexImage")
    tex_h.image = img
    tex_h.label = "qt_bevel_bump_height"
    bump = nt.nodes.new("ShaderNodeBump")
    bump.invert = False
    # loft-ish strength/distance
    if mode_key == "loft":
        bump.inputs["Strength"].default_value = 0.1
        bump.inputs["Distance"].default_value = 1.0
        bevel.inputs["Radius"].default_value = 0.02
    else:
        bump.inputs["Strength"].default_value = 1.0
        bump.inputs["Distance"].default_value = 0.001
    nt.links.new(tex_h.outputs["Color"], bump.inputs["Height"])

    if mode_key == "loft":
        img_n = _write_gray_png(normal_path, hill=False, seed=1)
        tex_n = nt.nodes.new("ShaderNodeTexImage")
        tex_n.image = img_n
        tex_n.label = "qt_bevel_nmap_tex"
        nmap = nt.nodes.new("ShaderNodeNormalMap")
        nmap.space = "TANGENT"
        nmap.inputs["Strength"].default_value = 1.0
        nt.links.new(tex_n.outputs["Color"], nmap.inputs["Color"])
        nt.links.new(nmap.outputs["Normal"], bump.inputs["Normal"])

    nt.links.new(bump.outputs["Normal"], bevel.inputs["Normal"])
    nt.links.new(bevel.outputs["Normal"], bsdf.inputs["Normal"])
    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--mode",
        default="bevel",
        choices=("bevel", "bevel_nmap", "bevel_bump", "loft", "bump", "normalmap"),
    )
    p.add_argument("--image", default="/tmp/qt_slice2az_height.png")
    p.add_argument("--normal", default="/tmp/qt_slice2az_normal.png")
    p.add_argument("--radius", type=float, default=0.12)
    p.add_argument("--bevel-samples", type=int, default=4)
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2az_stock.exr")
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2az_scene(
        image_path=args.image,
        mode=args.mode,
        normal_path=args.normal,
        radius=args.radius,
        samples=args.bevel_samples,
    )
    print(
        "QUANTTRACE_SLICE2AZ",
        cube_obj.name,
        "mode",
        args.mode,
        "radius",
        args.radius,
        "bevel_samples",
        args.bevel_samples,
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2AZ wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
