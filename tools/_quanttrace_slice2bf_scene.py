# QuantTrace Slice 2bf: Fresnel Fac -> Mix -> Principled Base Color.
from __future__ import annotations
import argparse, os, struct, sys, zlib
import bpy


LOFT_FRESNEL_IOR = 1.45  # Object003.002 Material.003 ShaderNodeFresnel


def _argv():
    a = sys.argv
    return a[a.index("--") + 1 :] if "--" in a else []


def _make_checker_png(path, seed=0):
    """8x8 sRGB checker; seed flips which cells are light for second image."""
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


def _add_mix(nt, *, blend="MIX", fac=0.5, other=(0.0, 0.0, 0.0), clamp_factor=True):
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


def _add_fresnel(nt, *, ior):
    node = nt.nodes.new("ShaderNodeFresnel")
    node.label = "qt_mix_fresnel_fac"
    ior_sock = node.inputs.get("IOR")
    ior_sock.default_value = float(ior)
    return node


def build_slice2bf_scene(
    image_path="/tmp/qt_slice2bf_checker.png",
    *,
    mode="claim",
):
    """Locked cube; Mix -> Base Color with linked Fac matching loft census.

    mode:
      claim        — CLAIM: TEX_IMAGE A vs constant B, Fac <- Fresnel IOR=1.45
      mix          — 2ay regression: same Mix, Fac unlinked 0.5
      curves       — 2bd regression
      invert       — 2be regression
      point        — 2av regression
      hdr          — 2aa regression
      fac_noise    — Noise -> Mix.Fac (named REFUSE Slice 2bf)
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)

    mode_key = str(mode).strip().lower()
    allowed = ("claim", "mix", "curves", "invert", "point", "hdr", "fac_noise")
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2bf)")

    if mode_key == "mix":
        import _quanttrace_slice2ay_scene as sc
        return sc.build_slice2ay_scene(mode="mix")
    if mode_key == "curves":
        import _quanttrace_slice2bd_scene as sc
        return sc.build_slice2bd_scene(mode="curves")
    if mode_key == "invert":
        import _quanttrace_slice2be_scene as sc
        return sc.build_slice2be_scene(mode="invert")
    if mode_key == "point":
        import _quanttrace_slice2av_scene as sc
        return sc.build_slice2av_scene(
            image_path="/tmp/qt_slice2av_env.exr", mode="point"
        )
    if mode_key == "hdr":
        import _quanttrace_slice2aa_scene as sc
        return sc.build_slice2aa_scene()

    import _quanttrace_tex_scene as texsc

    _make_checker_png(image_path, seed=0)
    scene, cube_obj, lamp, cam, img = texsc.build_tex_scene(image_path=image_path)
    mat = cube_obj.data.materials[0]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex = next(n for n in nt.nodes if n.type == "TEX_IMAGE")
    for link in list(bsdf.inputs["Base Color"].links):
        nt.links.remove(link)

    mx = _add_mix(nt, blend="MIX", fac=0.5, other=(0.0, 0.0, 0.0), clamp_factor=True)
    a_sock = mx.inputs.get("A_Color") or mx.inputs.get("A")
    nt.links.new(tex.outputs["Color"], a_sock)
    fac_sock = mx.inputs.get("Factor_Float") or mx.inputs.get("Factor") or mx.inputs.get("Fac")
    if mode_key == "fac_noise":
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.label = "qt_mix_fac_noise"
        nt.links.new(noise.outputs["Fac"], fac_sock)
    else:
        fr = _add_fresnel(nt, ior=LOFT_FRESNEL_IOR)
        fr_out = fr.outputs.get("Fac") or fr.outputs.get("Factor") or fr.outputs[0]
        nt.links.new(fr_out, fac_sock)
    out = mx.outputs.get("Result") or mx.outputs.get("Color") or mx.outputs[0]
    nt.links.new(out, bsdf.inputs["Base Color"])
    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--mode",
        default="claim",
        choices=("claim", "mix", "curves", "invert", "point", "hdr", "fac_noise"),
    )
    p.add_argument("--image", default="/tmp/qt_slice2bf_checker.png")
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2bf_stock.exr")
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2bf_scene(
        image_path=args.image, mode=args.mode,
    )
    print("QUANTTRACE_SLICE2BF", cube_obj.name, "mode", args.mode)
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2BF wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
