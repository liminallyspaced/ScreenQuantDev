# QuantTrace Slice 2af: locked cube + packed-only Image / Environment Texture.
# Modes materialize through sync._abspath_image → /tmp/quanttrace_packed/.
from __future__ import annotations
import argparse, os, sys
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def _pack_clear_and_unlink(img, disk_path: str):
    """Pack image into .blend, clear filepath, delete on-disk original."""
    if img is None:
        raise RuntimeError("no image to pack")
    disk_path = os.path.abspath(disk_path)
    img.pack()
    if img.packed_file is None:
        raise RuntimeError(f"pack failed for {img.name!r}")
    img.filepath = ""
    img.filepath_raw = ""
    if os.path.isfile(disk_path):
        os.unlink(disk_path)
    print(
        "QUANTTRACE_SLICE2AF_PACKED",
        img.name,
        "packed_size", img.packed_file.size,
        "filepath", repr(img.filepath),
        "from_user", repr(img.filepath_from_user()),
        "disk_gone", not os.path.isfile(disk_path),
        "cs", img.colorspace_settings.name,
    )
    return img


def build_slice2af_scene(
    image_path="/tmp/qt_slice2af_checker.png",
    *,
    mode="base_packed",
    projection="EQUIRECTANGULAR",
    strength=1.0,
):
    """Locked cube with packed-only or disk image paths.

    mode:
      base_packed — Principled Base Color ← TEX_IMAGE packed-only (no disk)
      hdr_packed  — world Environment Texture packed-only HDR (no disk)
      disk        — Principled Base Color ← TEX_IMAGE with normal disk filepath
                    (2f regression)
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    mode_key = str(mode).strip().lower()

    if mode_key == "hdr_packed":
        import _quanttrace_slice2aa_scene as sc2aa
        env_path = image_path if str(image_path).endswith(".exr") else "/tmp/qt_slice2af_env.exr"
        scene, cube_obj, lamp, cam, img = sc2aa.build_slice2aa_scene(
            image_path=env_path,
            projection=projection,
            strength=strength,
            black_world=False,
        )
        _pack_clear_and_unlink(img, env_path)
        bpy.context.view_layer.update()
        return scene, cube_obj, lamp, cam, img

    # base_packed or disk — mesh TEX_IMAGE
    import _quanttrace_tex_scene as texsc
    scene, cube_obj, lamp, cam, img = texsc.build_tex_scene(image_path=image_path)
    if mode_key == "base_packed":
        _pack_clear_and_unlink(img, image_path)
    elif mode_key == "disk":
        print(
            "QUANTTRACE_SLICE2AF_DISK",
            img.name,
            "filepath", img.filepath,
            "isfile", os.path.isfile(bpy.path.abspath(img.filepath)),
            "cs", img.colorspace_settings.name,
        )
    else:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2af)")
    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2af_stock.exr")
    p.add_argument("--image", default="/tmp/qt_slice2af_checker.png")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument(
        "--mode",
        choices=("base_packed", "hdr_packed", "disk"),
        default="base_packed",
    )
    p.add_argument(
        "--projection",
        choices=("EQUIRECTANGULAR", "MIRROR_BALL"),
        default="EQUIRECTANGULAR",
    )
    p.add_argument("--strength", type=float, default=1.0)
    args = p.parse_args(_argv())
    image = args.image
    if args.mode == "hdr_packed" and not str(image).endswith(".exr"):
        image = "/tmp/qt_slice2af_env.exr"
    scene, cube_obj, lamp, cam, img = build_slice2af_scene(
        image_path=image,
        mode=args.mode,
        projection=args.projection,
        strength=args.strength,
    )
    print(
        "QUANTTRACE_SLICE2AF", cube_obj.name,
        "mode", args.mode,
        "image", getattr(img, "filepath", None),
        "packed", img.packed_file is not None if img is not None else None,
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2AF wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
