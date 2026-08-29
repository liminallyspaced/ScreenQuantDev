# QuantTrace Slice 2bb: Noise Texture -> ColorRamp.Fac -> Principled.Roughness.
from __future__ import annotations
import argparse, os, sys
import bpy


# Loft Plane / mat '0' ColorRamp (LINEAR, Color out, 2 stops).
LOFT_STOP0 = (0.254546, (0.0, 0.0, 0.0, 1.0))
LOFT_STOP1 = (0.822727, (1.0, 1.0, 1.0, 1.0))

# Loft Plane Noise Texture (census 2026-08-29): 3D FBM normalize,
# Vector unlinked Generated, Scale=150 Detail=16 Distortion=0.2 Fac out.
PLANE_NOISE = dict(
    noise_dimensions="3D",
    noise_type="FBM",
    normalize=True,
    scale=150.0,
    detail=16.0,
    roughness=0.5,
    lacunarity=2.0,
    distortion=0.2,
    w=0.0,
    offset=0.0,
    gain=1.0,
)


def _argv():
    a = sys.argv
    return a[a.index("--") + 1 :] if "--" in a else []


def _loft_colorramp(nt, interpolation="LINEAR"):
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.label = "qt_colorramp"
    cr = ramp.color_ramp
    cr.interpolation = interpolation
    els = cr.elements
    while len(els) > 2:
        els.remove(els[-1])
    while len(els) < 2:
        els.new(0.5)
    els[0].position = LOFT_STOP0[0]
    els[0].color = LOFT_STOP0[1]
    els[1].position = LOFT_STOP1[0]
    els[1].color = LOFT_STOP1[1]
    return ramp


def _set_noise_in(noise, ident, value):
    """Unavailable 3D-FBM sockets (W/Offset/Gain) miss keyed get."""
    inputs = noise.inputs
    sock = None
    getter = getattr(inputs, "get", None)
    if callable(getter):
        sock = getter(ident)
    if sock is None:
        for s in inputs:
            if getattr(s, "identifier", None) == ident or getattr(s, "name", None) == ident:
                sock = s
                break
    if sock is None:
        return
    try:
        sock.default_value = value
    except Exception:
        pass


def _apply_plane_noise(noise, *, params=None):
    p = dict(PLANE_NOISE)
    if params:
        p.update(params)
    noise.noise_dimensions = p["noise_dimensions"]
    noise.noise_type = p["noise_type"]
    noise.normalize = bool(p["normalize"])
    _set_noise_in(noise, "W", float(p["w"]))
    _set_noise_in(noise, "Scale", float(p["scale"]))
    _set_noise_in(noise, "Detail", float(p["detail"]))
    _set_noise_in(noise, "Roughness", float(p["roughness"]))
    _set_noise_in(noise, "Lacunarity", float(p["lacunarity"]))
    _set_noise_in(noise, "Offset", float(p["offset"]))
    _set_noise_in(noise, "Gain", float(p["gain"]))
    _set_noise_in(noise, "Distortion", float(p["distortion"]))
    return noise


def build_slice2bb_scene(
    image_path="/tmp/qt_slice2bb_fac.png",
    *,
    mode="noise",
):
    """Locked cube; Noise -> ColorRamp.Fac -> Principled.Roughness.

    mode:
      noise          — CLAIM: loft Plane Noise (Scale 150 / Detail 16 / Dist 0.2)
                       Factor -> ColorRamp.Fac -> Roughness
      noise_color    — same Noise Color (averaged) -> ColorRamp.Fac
      ramp           — 2ba regression: ColorRamp Fac <- Non-Color TEX_IMAGE
      fac_unlinked   — 2ba regression: ColorRamp Fac unlinked
      tex            — 2i regression: TEX_IMAGE -> Roughness, no ColorRamp
      fresnel        — Fresnel -> ColorRamp Fac (named REFUSE)
      mix            — Mix -> ColorRamp Fac (named REFUSE)
      vector_linked  — TEX_COORD -> Noise Vector (named REFUSE)
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)

    mode_key = str(mode).strip().lower()
    allowed = (
        "noise", "noise_color", "ramp", "fac_unlinked", "tex",
        "fresnel", "mix", "vector_linked",
    )
    if mode_key not in allowed:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2bb)")

    if mode_key in ("ramp", "fac_unlinked", "tex"):
        import _quanttrace_slice2ba_scene as sc
        ba = "ramp" if mode_key == "ramp" else mode_key
        return sc.build_slice2ba_scene(image_path=image_path, mode=ba)

    import _quanttrace_cube_scene as cube

    scene, cube_obj, lamp, cam = cube.build_locked_scene()
    mat = cube_obj.data.materials[0]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.7, 0.7, 0.7, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.5
    bsdf.inputs["Metallic"].default_value = 0.0

    ramp = _loft_colorramp(nt, interpolation="LINEAR")
    img = None

    if mode_key == "fresnel":
        fr = nt.nodes.new("ShaderNodeFresnel")
        fr.label = "qt_fresnel_fac"
        nt.links.new(fr.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Roughness"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    if mode_key == "mix":
        mx = nt.nodes.new("ShaderNodeMix")
        mx.data_type = "FLOAT"
        mx.label = "qt_mix_fac"
        nt.links.new(mx.outputs["Result"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Roughness"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.label = "qt_noise_fac"
    _apply_plane_noise(noise)

    if mode_key == "vector_linked":
        tc = nt.nodes.new("ShaderNodeTexCoord")
        tc.label = "qt_noise_vec"
        nt.links.new(tc.outputs["Generated"], noise.inputs["Vector"])
        nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        nt.links.new(ramp.outputs["Color"], bsdf.inputs["Roughness"])
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    out_name = "Color" if mode_key == "noise_color" else "Fac"
    if out_name not in noise.outputs:
        out_name = "Factor" if mode_key != "noise_color" else "Color"
    nt.links.new(noise.outputs[out_name], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Roughness"])
    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--mode",
        default="noise",
        choices=(
            "noise", "noise_color", "ramp", "fac_unlinked", "tex",
            "fresnel", "mix", "vector_linked",
        ),
    )
    p.add_argument("--image", default="/tmp/qt_slice2bb_fac.png")
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2bb_stock.exr")
    p.add_argument("--res", type=int, default=32)
    p.add_argument("--samples", type=int, default=4)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2bb_scene(
        image_path=args.image, mode=args.mode,
    )
    print("QUANTTRACE_SLICE2BB", cube_obj.name, "mode", args.mode)
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2BB wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
