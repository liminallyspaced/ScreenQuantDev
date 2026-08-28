# QuantTrace Slice 2aa: locked cube + Environment Texture world (HDR equirect).
from __future__ import annotations
import argparse, os, sys
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def _write_gradient_exr(path: str, w: int = 32, h: int = 16) -> str:
    """Tiny linear float EXR: left red → right cyan (visible non-constant env).

    Writes via OpenImageIO (Blender Image.save was writing all-zero EXRs).
    """
    path = os.path.abspath(path)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    import numpy as np
    import OpenImageIO as oiio
    arr = np.zeros((h, w, 3), dtype=np.float32)
    for y in range(h):
        for x in range(w):
            t = x / max(1, w - 1)
            v = 0.55 + 0.45 * (y / max(1, h - 1))
            arr[y, x, 0] = (1.0 - t) * v
            arr[y, x, 1] = t * v
            arr[y, x, 2] = t * v
    spec = oiio.ImageSpec(w, h, 3, oiio.FLOAT)
    spec.attribute("compression", "zip")
    out = oiio.ImageOutput.create(path)
    if out is None:
        raise RuntimeError(f"OIIO create failed: {oiio.geterror()}")
    if not out.open(path, spec):
        raise RuntimeError(f"OIIO open failed: {oiio.geterror()}")
    if not out.write_image(arr):
        raise RuntimeError(f"OIIO write failed: {oiio.geterror()}")
    out.close()
    print(
        "QUANTTRACE_SLICE2AA_EXR", path, "size", [w, h],
        "left", arr[h // 2, 0].tolist(),
        "right", arr[h // 2, -1].tolist(),
        "max", arr.max(axis=(0, 1)).tolist(),
    )
    return path


def build_slice2aa_scene(
    image_path="/tmp/qt_slice2aa_env.exr",
    *,
    projection="EQUIRECTANGULAR",
    strength=1.0,
    black_world=False,
):
    """Locked cube + world Environment Texture → Background Color.

    Vector unlinked (Cycles LINK_POSITION). Strength unlinked.
    projection: EQUIRECTANGULAR | MIRROR_BALL
    black_world=True: skip env (Slice 2b regression).
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_cube_scene as cube

    scene, cube_obj, lamp, cam = cube.build_locked_scene()
    # Principled grey (locked cube defaults already).
    mat = cube_obj.data.materials[0]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    bsdf.inputs["Base Color"].default_value = (0.7, 0.7, 0.7, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.5
    bsdf.inputs["Metallic"].default_value = 0.0

    world = scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        scene.world = world
    world.use_nodes = True
    wnt = world.node_tree
    wnt.nodes.clear()
    out = wnt.nodes.new("ShaderNodeOutputWorld")
    bg = wnt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = float(strength)
    bg.inputs["Color"].default_value = (0.0, 0.0, 0.0, 1.0)
    wnt.links.new(bg.outputs["Background"], out.inputs["Surface"])

    img = None
    env = None
    if not black_world:
        exr_path = _write_gradient_exr(image_path)
        # Drop any stale same-name image so load gets fresh pixels.
        for im in list(bpy.data.images):
            fp = os.path.abspath(bpy.path.abspath(im.filepath or "")) if im.filepath else ""
            if fp == os.path.abspath(exr_path) or im.name.startswith("qt_slice2aa"):
                bpy.data.images.remove(im)
        img = bpy.data.images.load(exr_path)
        # HDR / linear float EXR — prefer Linear Rec.709.
        for cs_name in ("Linear Rec.709", "Linear", "Non-Color"):
            try:
                img.colorspace_settings.name = cs_name
                break
            except Exception:
                continue
        env = wnt.nodes.new("ShaderNodeTexEnvironment")
        env.image = img
        proj = str(projection).upper()
        if proj not in ("EQUIRECTANGULAR", "MIRROR_BALL"):
            raise RuntimeError(f"projection={projection!r} refused")
        env.projection = proj
        # Vector left unlinked → LINK_POSITION.
        wnt.links.new(env.outputs["Color"], bg.inputs["Color"])
        print(
            "QUANTTRACE_SLICE2AA_WORLD path", exr_path,
            "proj", env.projection, "strength", bg.inputs["Strength"].default_value,
            "vec_linked", env.inputs["Vector"].is_linked,
            "cs", img.colorspace_settings.name,
        )
    else:
        print("QUANTTRACE_SLICE2AA_WORLD black strength", strength)

    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2aa_stock.exr")
    p.add_argument("--image", default="/tmp/qt_slice2aa_env.exr")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument(
        "--projection",
        choices=("EQUIRECTANGULAR", "MIRROR_BALL"),
        default="EQUIRECTANGULAR",
    )
    p.add_argument("--strength", type=float, default=1.0)
    p.add_argument("--black-world", action="store_true", default=False)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2aa_scene(
        image_path=args.image,
        projection=args.projection,
        strength=args.strength,
        black_world=args.black_world,
    )
    print(
        "QUANTTRACE_SLICE2AA", cube_obj.name,
        "proj", args.projection, "black", args.black_world,
        "image", getattr(img, "filepath", None) if img is not None else None,
        "strength", args.strength,
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2AA wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
