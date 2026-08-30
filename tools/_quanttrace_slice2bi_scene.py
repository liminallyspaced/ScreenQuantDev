# QuantTrace Slice 2bi: Normal Map Color ← Combine+InvertG Separate←TEX_IMAGE.
from __future__ import annotations
import argparse, os, sys
import bpy
from mathutils import Vector


def _argv():
    a = sys.argv
    return a[a.index("--") + 1 :] if "--" in a else []


def _pull_camera(cam, scale=1.8):
    loc = Vector(cam.location) * float(scale)
    cam.location = loc
    direction = Vector((0.0, 0.0, 0.0)) - loc
    if direction.length > 1e-8:
        cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def _wire_invert_g(nt, tex):
    """TEX → Separate×3 + Invert(G) → Combine → return Color output (loft Rope)."""
    sep_r = nt.nodes.new("ShaderNodeSeparateColor")
    sep_r.mode = "RGB"
    sep_r.label = "qt_sep_r"
    sep_g = nt.nodes.new("ShaderNodeSeparateColor")
    sep_g.mode = "RGB"
    sep_g.label = "qt_sep_g"
    sep_b = nt.nodes.new("ShaderNodeSeparateColor")
    sep_b.mode = "RGB"
    sep_b.label = "qt_sep_b"
    inv = nt.nodes.new("ShaderNodeInvert")
    inv.label = "qt_invert_g"
    fac = inv.inputs.get("Fac") or inv.inputs.get("Factor")
    fac.default_value = 1.0
    comb = nt.nodes.new("ShaderNodeCombineColor")
    comb.mode = "RGB"
    comb.label = "qt_combine_inv_g"
    nt.links.new(tex.outputs["Color"], sep_r.inputs["Color"])
    nt.links.new(tex.outputs["Color"], sep_g.inputs["Color"])
    nt.links.new(tex.outputs["Color"], sep_b.inputs["Color"])
    nt.links.new(sep_g.outputs["Green"], inv.inputs["Color"])
    nt.links.new(sep_r.outputs["Red"], comb.inputs["Red"])
    nt.links.new(inv.outputs["Color"], comb.inputs["Green"])
    nt.links.new(sep_b.outputs["Blue"], comb.inputs["Blue"])
    return comb.outputs["Color"]


def build_slice2bi_scene(
    image_path="/tmp/qt_slice2bi_normal.png",
    *,
    mode="claim",
    strength=1.0,
):
    """Locked cube; loft Rope Normal Map Color graph (Combine+InvertG).

    mode:
      claim       — CLAIM Invert-G Y-flip (Slice 2bi)
      bypass      — TEX_IMAGE Color → Normal Map directly (live partner)
      normal      — 2j regression (TEX → Normal Map, invert_g enable=0)
      mix         — 2ay regression
      curves      — 2bh regression
      hdr         — 2aa regression
      fac_linked  — Invert.Fac linked (named REFUSE Slice 2bi)
      invert_r    — Invert on Red (named REFUSE Slice 2bi)
      hsv         — Combine mode HSV (named REFUSE Slice 2bi)
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)

    mode_key = str(mode).strip().lower()
    allowed = (
        "claim", "bypass", "normal", "mix", "curves", "hdr",
        "fac_linked", "invert_r", "hsv",
    )
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2bi)")

    if mode_key == "mix":
        import _quanttrace_slice2ay_scene as sc
        return sc.build_slice2ay_scene(mode="mix")
    if mode_key == "curves":
        import _quanttrace_slice2bh_scene as sc
        return sc.build_slice2bh_scene(mode="claim")
    if mode_key == "hdr":
        import _quanttrace_slice2aa_scene as sc
        return sc.build_slice2aa_scene()
    if mode_key == "normal":
        import _quanttrace_normal_scene as sc
        return sc.build_normal_scene(image_path=image_path, strength=strength)

    import _quanttrace_normal_scene as nsc

    scene, cube_obj, lamp, cam, img = nsc.build_normal_scene(
        image_path=image_path, strength=strength,
    )
    _pull_camera(cam, 1.8)
    mat = cube_obj.data.materials[0]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    nmap = next(n for n in nt.nodes if n.type == "NORMAL_MAP")
    tex = next(n for n in nt.nodes if n.type == "TEX_IMAGE")
    # Drop direct TEX → Normal Map Color
    for link in list(nmap.inputs["Color"].links):
        nt.links.remove(link)

    if mode_key == "bypass":
        nt.links.new(tex.outputs["Color"], nmap.inputs["Color"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key == "hsv":
        sep = nt.nodes.new("ShaderNodeSeparateColor")
        sep.mode = "RGB"
        comb = nt.nodes.new("ShaderNodeCombineColor")
        comb.mode = "HSV"
        inv = nt.nodes.new("ShaderNodeInvert")
        fac = inv.inputs.get("Fac") or inv.inputs.get("Factor")
        fac.default_value = 1.0
        nt.links.new(tex.outputs["Color"], sep.inputs["Color"])
        nt.links.new(sep.outputs["Green"], inv.inputs["Color"])
        nt.links.new(sep.outputs["Red"], comb.inputs["Red"])
        nt.links.new(inv.outputs["Color"], comb.inputs["Green"])
        nt.links.new(sep.outputs["Blue"], comb.inputs["Blue"])
        nt.links.new(comb.outputs["Color"], nmap.inputs["Color"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key == "invert_r":
        sep_r = nt.nodes.new("ShaderNodeSeparateColor")
        sep_r.mode = "RGB"
        sep_g = nt.nodes.new("ShaderNodeSeparateColor")
        sep_g.mode = "RGB"
        sep_b = nt.nodes.new("ShaderNodeSeparateColor")
        sep_b.mode = "RGB"
        inv = nt.nodes.new("ShaderNodeInvert")
        fac = inv.inputs.get("Fac") or inv.inputs.get("Factor")
        fac.default_value = 1.0
        comb = nt.nodes.new("ShaderNodeCombineColor")
        comb.mode = "RGB"
        nt.links.new(tex.outputs["Color"], sep_r.inputs["Color"])
        nt.links.new(tex.outputs["Color"], sep_g.inputs["Color"])
        nt.links.new(tex.outputs["Color"], sep_b.inputs["Color"])
        nt.links.new(sep_r.outputs["Red"], inv.inputs["Color"])
        nt.links.new(inv.outputs["Color"], comb.inputs["Red"])
        nt.links.new(sep_g.outputs["Green"], comb.inputs["Green"])
        nt.links.new(sep_b.outputs["Blue"], comb.inputs["Blue"])
        nt.links.new(comb.outputs["Color"], nmap.inputs["Color"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    # claim / fac_linked
    color_out = _wire_invert_g(nt, tex)
    if mode_key == "fac_linked":
        inv = next(n for n in nt.nodes if n.label == "qt_invert_g")
        fac = inv.inputs.get("Fac") or inv.inputs.get("Factor")
        for link in list(fac.links):
            nt.links.remove(link)
        val = nt.nodes.new("ShaderNodeValue")
        val.outputs[0].default_value = 1.0
        nt.links.new(val.outputs[0], fac)
    nt.links.new(color_out, nmap.inputs["Color"])
    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--mode",
        default="claim",
        choices=(
            "claim", "bypass", "normal", "mix", "curves", "hdr",
            "fac_linked", "invert_r", "hsv",
        ),
    )
    p.add_argument("--image", default="/tmp/qt_slice2bi_normal.png")
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2bi_stock.exr")
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2bi_scene(
        image_path=args.image, mode=args.mode,
    )
    print("QUANTTRACE_SLICE2BI", cube_obj.name, "mode", args.mode)
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2BI wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
