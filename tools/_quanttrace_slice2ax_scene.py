# QuantTrace Slice 2ax: Gamma + HueSat → Principled Base Color (mesh).
from __future__ import annotations
import argparse, os, sys
import bpy


HSV_HUE = 0.6
HSV_SAT = 1.2
HSV_VAL = 0.85
HSV_FAC = 1.0
GAMMA = 2.2


def _argv():
    a = sys.argv
    return a[a.index("--") + 1 :] if "--" in a else []


def _add_gamma(nt, gamma):
    node = nt.nodes.new("ShaderNodeGamma")
    node.label = "BaseColorGamma"
    node.inputs["Gamma"].default_value = float(gamma)
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


def build_slice2ax_scene(
    image_path="/tmp/qt_slice2ax_checker.png",
    *,
    mode="hsv",
):
    """Locked cube + 8×8 sRGB checker TEX_IMAGE → Base Color (+ Gamma/HueSat).

    mode:
      tex         — identity (2f regression; no HSV/Gamma nodes)
      hsv         — Hue=0.6 Sat=1.2 Val=0.85 Fac=1.0 (CLAIM)
      gamma       — Gamma=2.2
      gamma_hsv   — loft-ish Gamma 2.2 then HueSat (CLAIM plate)
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_tex_scene as texsc

    mode_key = str(mode).strip().lower()
    allowed = ("tex", "hsv", "gamma", "gamma_hsv")
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2ax)")

    scene, cube_obj, lamp, cam, img = texsc.build_tex_scene(image_path=image_path)
    if mode_key == "tex":
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    mat = cube_obj.data.materials[0]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex = next(n for n in nt.nodes if n.type == "TEX_IMAGE")

    # Drop direct TEX_IMAGE → Base Color; rebuild loft-ish chain.
    for link in list(bsdf.inputs["Base Color"].links):
        nt.links.remove(link)

    cur_out = tex.outputs["Color"]
    if mode_key in ("gamma", "gamma_hsv"):
        g = _add_gamma(nt, GAMMA)
        nt.links.new(cur_out, g.inputs["Color"])
        cur_out = g.outputs["Color"]
    if mode_key in ("hsv", "gamma_hsv"):
        h = _add_hsv(nt, hue=HSV_HUE, sat=HSV_SAT, val=HSV_VAL, fac=HSV_FAC)
        nt.links.new(cur_out, h.inputs["Color"])
        cur_out = h.outputs["Color"]
    nt.links.new(cur_out, bsdf.inputs["Base Color"])
    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", default="hsv", choices=("tex", "hsv", "gamma", "gamma_hsv"))
    p.add_argument("--image", default="/tmp/qt_slice2ax_checker.png")
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2ax_stock.exr")
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2ax_scene(
        image_path=args.image, mode=args.mode
    )
    print(
        "QUANTTRACE_SLICE2AX",
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
        print("QUANTTRACE_SLICE2AX wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
