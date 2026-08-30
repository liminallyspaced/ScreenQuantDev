# QuantTrace Slice 2bd: ShaderNodeRGBCurve → Principled Base Color (mesh analog of 2as).
from __future__ import annotations
import argparse, os, sys
import bpy
from mathutils import Vector


RGB = (1.0, 0.25, 0.1)
CURVE_I_MID_Y = 0.35
HSV_HUE = 0.6
HSV_SAT = 1.2
HSV_VAL = 0.85
HSV_FAC = 1.0


def _argv():
    a = sys.argv
    return a[a.index("--") + 1 :] if "--" in a else []


def _pull_camera(cam, scale=1.8):
    loc = Vector(cam.location) * float(scale)
    cam.location = loc
    direction = Vector((0.0, 0.0, 0.0)) - loc
    if direction.length > 1e-8:
        cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def _add_rgb_curves(nt, *, mid_y=CURVE_I_MID_Y):
    node = nt.nodes.new("ShaderNodeRGBCurve")
    node.label = "BaseColorRGBCurves"
    fac = node.inputs.get("Fac") or node.inputs.get("Factor")
    fac.default_value = 1.0
    mapping = node.mapping
    cm_i = mapping.curves[3]
    while len(cm_i.points) > 2:
        cm_i.points.remove(cm_i.points[1])
    cm_i.points[0].location = (0.0, 0.0)
    cm_i.points[1].location = (1.0, 1.0)
    cm_i.points.new(0.5, float(mid_y))
    mapping.update()
    return node


def _add_hsv(nt, *, hue, sat, val, fac):
    node = nt.nodes.new("ShaderNodeHueSaturation")
    node.label = "BaseColorHueSat"
    node.inputs["Hue"].default_value = float(hue)
    node.inputs["Saturation"].default_value = float(sat)
    node.inputs["Value"].default_value = float(val)
    fac_sock = node.inputs.get("Fac") or node.inputs.get("Factor")
    fac_sock.default_value = float(fac)
    return node


def _add_mix(nt, *, blend="MIX", fac=0.5, other=(0.0, 0.0, 0.0), clamp_factor=False):
    node = nt.nodes.new("ShaderNodeMix")
    node.data_type = "RGBA"
    node.blend_type = blend
    node.clamp_factor = bool(clamp_factor)
    node.clamp_result = False
    fac_sock = node.inputs.get("Factor_Float") or node.inputs.get("Factor") or node.inputs.get("Fac")
    fac_sock.default_value = float(fac)
    b_sock = node.inputs.get("B_Color") or node.inputs.get("B")
    b_sock.default_value = (float(other[0]), float(other[1]), float(other[2]), 1.0)
    return node


def _make_checker_png(path, seed=0):
    import struct, zlib
    w = h = 8
    rows = []
    for y in range(h):
        row = [0]
        for x in range(w):
            on = ((x + y + seed) % 2) == 0
            v = 220 if on else 40
            row.extend((v, v, v))
        rows.append(bytes(row))
    raw = b"".join(rows)
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(png)
    return path


def build_slice2bd_scene(
    image_path="/tmp/qt_slice2bd_checker.png",
    *,
    mode="curves",
    image_b_path="/tmp/qt_slice2bd_checker_b.png",
    pull_camera=True,
):
    """Locked cube; RGB Curves → Principled Base Color.

    mode:
      curves       — RGB(1,0.25,0.1) Color unlinked → Curves (I mid 0.35) → Base. CLAIM.
      curves_tex   — TEX_IMAGE → Curves → Base
      curves_mix   — TEX_IMAGE → Mix MIX fac=0.5 other=0 → Curves → Base (loft-ish)
      curves_hsv   — TEX_IMAGE → HueSat → Curves → Base
      unlinked_rgb — RGB(1,0.25,0.1) no Curves (live partner)
      fac_linked   — Noise → Curves.Fac (must REFUSE Slice 2bd)
      tex / hsv / mix — identity regressions (2f / 2ax / 2ay)
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)

    mode_key = str(mode).strip().lower()
    allowed = (
        "curves", "curves_tex", "curves_mix", "curves_hsv",
        "unlinked_rgb", "fac_linked",
        "tex", "hsv", "mix",
    )
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2bd)")

    if mode_key in ("tex", "hsv", "mix", "curves_tex", "curves_mix", "curves_hsv"):
        import _quanttrace_slice2ay_scene as sc2ay
        ay_mode = "tex" if mode_key in ("tex", "curves_tex") else (
            "hsv" if mode_key in ("hsv", "curves_hsv") else "mix"
        )
        scene, cube_obj, lamp, cam, img = sc2ay.build_slice2ay_scene(
            image_path=image_path, mode=ay_mode, image_b_path=image_b_path
        )
        if pull_camera:
            _pull_camera(cam, 1.8)
        if mode_key in ("tex", "hsv", "mix"):
            bpy.context.view_layer.update()
            return scene, cube_obj, lamp, cam, img
        mat = cube_obj.data.materials[0]
        nt = mat.node_tree
        bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        # Insert Curves between current Base Color source and Principled.
        src_links = list(bsdf.inputs["Base Color"].links)
        if not src_links:
            raise RuntimeError("Base Color unlinked after 2ay build")
        src = src_links[0].from_socket
        for link in src_links:
            nt.links.remove(link)
        curves = _add_rgb_curves(nt)
        nt.links.new(src, curves.inputs["Color"])
        nt.links.new(curves.outputs["Color"], bsdf.inputs["Base Color"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    import _quanttrace_cube_scene as cube
    scene, cube_obj, lamp, cam = cube.build_locked_scene()
    if pull_camera:
        _pull_camera(cam, 1.8)
    mat = cube_obj.data.materials[0]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Roughness"].default_value = 0.5
    bsdf.inputs["Metallic"].default_value = 0.0
    for link in list(bsdf.inputs["Base Color"].links):
        nt.links.remove(link)

    if mode_key == "unlinked_rgb":
        bsdf.inputs["Base Color"].default_value = (RGB[0], RGB[1], RGB[2], 1.0)
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, None

    curves = _add_rgb_curves(nt)
    color_in = curves.inputs["Color"]
    color_in.default_value = (RGB[0], RGB[1], RGB[2], 1.0)
    if mode_key == "fac_linked":
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.label = "qt_curves_fac_noise"
        fac = curves.inputs.get("Fac") or curves.inputs.get("Factor")
        out = noise.outputs.get("Fac") or noise.outputs.get("Factor") or noise.outputs[0]
        nt.links.new(out, fac)
    nt.links.new(curves.outputs["Color"], bsdf.inputs["Base Color"])
    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, None


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--mode",
        default="curves",
        choices=(
            "curves", "curves_tex", "curves_mix", "curves_hsv",
            "unlinked_rgb", "fac_linked",
            "tex", "hsv", "mix",
        ),
    )
    p.add_argument("--image", default="/tmp/qt_slice2bd_checker.png")
    p.add_argument("--image-b", default="/tmp/qt_slice2bd_checker_b.png")
    p.add_argument("--no-pull-camera", action="store_true", default=False)
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2bd_stock.exr")
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2bd_scene(
        image_path=args.image,
        mode=args.mode,
        image_b_path=args.image_b,
        pull_camera=not args.no_pull_camera,
    )
    print(
        "QUANTTRACE_SLICE2BD",
        cube_obj.name,
        "mode",
        args.mode,
        "image",
        getattr(img, "filepath", "") if img is not None else "",
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2BD wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
