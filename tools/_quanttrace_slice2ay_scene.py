# QuantTrace Slice 2ay: Mix → Principled Base Color (mesh).
from __future__ import annotations
import argparse, os, sys
import bpy


HSV_HUE = 0.6
HSV_SAT = 1.2
HSV_VAL = 0.85
HSV_FAC = 1.0


def _argv():
    a = sys.argv
    return a[a.index("--") + 1 :] if "--" in a else []


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
    """8×8 sRGB checker; seed flips which cells are light for second image."""
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


def build_slice2ay_scene(
    image_path="/tmp/qt_slice2ay_checker.png",
    *,
    mode="mix",
    image_b_path="/tmp/qt_slice2ay_checker_b.png",
):
    """Locked cube + 8×8 sRGB checker TEX_IMAGE → Mix → Base Color.

    mode:
      mix       — TEX_IMAGE → Mix MIX fac=0.5 other=(0,0,0) chain A → Base (CLAIM)
      mix_add   — same with blend ADD
      mix_mul2  — TEX_IMAGE × TEX_IMAGE_B MULTIPLY fac=0.5 clamp_factor (loft-ish)
      mix_hsv   — TEX → HueSat → Mix MIX → Base (native Color→HSV→Mix)
      mix_tex   — TEX_IMAGE on Fac (must REFUSE Slice 2ay)
      tex       — identity (2ax/2f regression; no Mix)
      hsv       — 2ax regression HueSat only
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_tex_scene as texsc

    mode_key = str(mode).strip().lower()
    allowed = ("tex", "hsv", "mix", "mix_add", "mix_mul2", "mix_hsv", "mix_tex")
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2ay)")

    _make_checker_png(image_path, seed=0)
    scene, cube_obj, lamp, cam, img = texsc.build_tex_scene(image_path=image_path)
    if mode_key == "tex":
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    mat = cube_obj.data.materials[0]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex = next(n for n in nt.nodes if n.type == "TEX_IMAGE")

    for link in list(bsdf.inputs["Base Color"].links):
        nt.links.remove(link)

    if mode_key == "hsv":
        h = _add_hsv(nt, hue=HSV_HUE, sat=HSV_SAT, val=HSV_VAL, fac=HSV_FAC)
        nt.links.new(tex.outputs["Color"], h.inputs["Color"])
        nt.links.new(h.outputs["Color"], bsdf.inputs["Base Color"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key == "mix_tex":
        mx = _add_mix(nt, blend="MIX", fac=0.5, other=(0, 0, 0))
        nt.links.new(tex.outputs["Color"], mx.inputs.get("A_Color") or mx.inputs.get("A"))
        # Link Fac from a second image (refuse).
        _make_checker_png(image_b_path, seed=1)
        img_b = bpy.data.images.load(image_b_path)
        tex_f = nt.nodes.new("ShaderNodeTexImage")
        tex_f.image = img_b
        fac_sock = mx.inputs.get("Factor_Float") or mx.inputs.get("Factor") or mx.inputs.get("Fac")
        # Color→Fac needs convert; Blender allows linking Color to Factor.
        nt.links.new(tex_f.outputs["Color"], fac_sock)
        nt.links.new(mx.outputs.get("Result") or mx.outputs.get("Color") or mx.outputs[0],
                     bsdf.inputs["Base Color"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    cur_out = tex.outputs["Color"]
    if mode_key == "mix_hsv":
        h = _add_hsv(nt, hue=HSV_HUE, sat=HSV_SAT, val=HSV_VAL, fac=HSV_FAC)
        nt.links.new(cur_out, h.inputs["Color"])
        cur_out = h.outputs["Color"]

    if mode_key == "mix_mul2":
        _make_checker_png(image_b_path, seed=1)
        img_b = bpy.data.images.load(image_b_path)
        tex_b = nt.nodes.new("ShaderNodeTexImage")
        tex_b.image = img_b
        # Share Vector if tex has Mapping/TEXCOORD; else both unlinked UV.
        vec = tex.inputs.get("Vector")
        if vec is not None and vec.is_linked:
            nt.links.new(vec.links[0].from_socket, tex_b.inputs["Vector"])
        mx = _add_mix(nt, blend="MULTIPLY", fac=0.5, other=(0, 0, 0), clamp_factor=True)
        a_sock = mx.inputs.get("A_Color") or mx.inputs.get("A")
        b_sock = mx.inputs.get("B_Color") or mx.inputs.get("B")
        nt.links.new(tex.outputs["Color"], a_sock)
        nt.links.new(tex_b.outputs["Color"], b_sock)
        out = mx.outputs.get("Result") or mx.outputs.get("Color") or mx.outputs[0]
        nt.links.new(out, bsdf.inputs["Base Color"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    blend = "ADD" if mode_key == "mix_add" else "MIX"
    mx = _add_mix(nt, blend=blend, fac=0.5, other=(0.0, 0.0, 0.0), clamp_factor=False)
    a_sock = mx.inputs.get("A_Color") or mx.inputs.get("A")
    nt.links.new(cur_out, a_sock)
    out = mx.outputs.get("Result") or mx.outputs.get("Color") or mx.outputs[0]
    nt.links.new(out, bsdf.inputs["Base Color"])
    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--mode",
        default="mix",
        choices=("tex", "hsv", "mix", "mix_add", "mix_mul2", "mix_hsv", "mix_tex"),
    )
    p.add_argument("--image", default="/tmp/qt_slice2ay_checker.png")
    p.add_argument("--image-b", default="/tmp/qt_slice2ay_checker_b.png")
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2ay_stock.exr")
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2ay_scene(
        image_path=args.image, mode=args.mode, image_b_path=args.image_b
    )
    print(
        "QUANTTRACE_SLICE2AY",
        cube_obj.name,
        "mode",
        args.mode,
        "image",
        getattr(img, "filepath", ""),
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2AY wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
