# QuantTrace Slice 2h: locked cube + TEX_COORD UV (+ optional Mapping) → TEX_IMAGE.
from __future__ import annotations
import argparse, math, os, sys
import bpy

def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def build_mapping_scene(
    image_path="/tmp/qt_checker_map.png",
    *,
    use_mapping=True,
    use_texcoord=True,
    scale=(2.0, 2.0, 2.0),
    location=(0.1, 0.2, 0.0),
    rotation_z=0.15,
    coord="UV",
):
    """Build tex scene; optionally wire TEX_COORD UV/Generated/Object/Camera [→ Mapping] → TEX_IMAGE.

    use_texcoord=False + use_mapping=False → Slice 2f unlinked Vector regression.
    use_texcoord=True + use_mapping=False → TEX_COORD only.
    use_texcoord=True + use_mapping=True → TEX_COORD → Mapping (VECTOR) → TEX_IMAGE.
    coord: "UV" (2h), "Generated" (2k), "Object" (2l), or "Camera" (2m).
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_tex_scene as texsc

    scene, cube_obj, lamp, cam, img = texsc.build_tex_scene(image_path=image_path)
    mat = cube_obj.data.materials[0]
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    tex = next(n for n in nt.nodes if n.type == "TEX_IMAGE")

    # Drop any existing Vector links on the image (build_tex_scene leaves unlinked).
    vec_in = tex.inputs["Vector"]
    for link in list(vec_in.links):
        nt.links.remove(link)

    if use_texcoord:
        tc = nt.nodes.new("ShaderNodeTexCoord")
        tc.location = (-600, 200)
        key = str(coord).strip().lower()
        if key == "generated":
            coord_name = "Generated"
        elif key == "object":
            coord_name = "Object"
        elif key == "camera":
            coord_name = "Camera"
        else:
            coord_name = "UV"
        coord_out = tc.outputs[coord_name]
        # Slice 2l: empty Object reference only (no object_itfm).
        if coord_name == "Object" and getattr(tc, "object", None) is not None:
            tc.object = None
        if use_mapping:
            mapping = nt.nodes.new("ShaderNodeMapping")
            mapping.location = (-400, 200)
            # Set L/R/S while type is POINT so Location is addressable; VECTOR
            # hides Location in Blender 5.2 (SVM VECTOR also ignores it).
            mapping.inputs["Location"].default_value = (
                float(location[0]), float(location[1]), float(location[2]),
            )
            mapping.inputs["Rotation"].default_value = (0.0, 0.0, float(rotation_z))
            mapping.inputs["Scale"].default_value = (
                float(scale[0]), float(scale[1]), float(scale[2]),
            )
            mapping.vector_type = "VECTOR"
            nt.links.new(coord_out, mapping.inputs["Vector"])
            nt.links.new(mapping.outputs["Vector"], vec_in)
            print(
                f"QUANTTRACE_MAP graph TEX_COORD {coord_name} → Mapping VECTOR "
                f"loc={tuple(location)} rot_z={rotation_z} scale={tuple(scale)}"
            )
        else:
            nt.links.new(coord_out, vec_in)
            print(f"QUANTTRACE_MAP graph TEX_COORD {coord_name} → TEX_IMAGE Vector")
    else:
        print("QUANTTRACE_MAP graph TEX_IMAGE Vector unlinked (2f regression)")

    # Ensure Color still feeds Base Color.
    if not bsdf.inputs["Base Color"].is_linked:
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])

    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_map_stock.exr")
    p.add_argument("--image", default="/tmp/qt_checker_map.png")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--mode", choices=("mapping", "texcoord", "unlinked"), default="mapping")
    p.add_argument("--coord", choices=("UV", "Generated", "Object", "Camera"), default="UV")
    p.add_argument("--scale", type=float, nargs=3, default=(2.0, 2.0, 2.0))
    p.add_argument("--location", type=float, nargs=3, default=(0.1, 0.2, 0.0))
    p.add_argument("--rotation-z", type=float, default=0.15)
    args = p.parse_args(_argv())
    use_tc = args.mode != "unlinked"
    use_map = args.mode == "mapping"
    scene, cube_obj, lamp, cam, img = build_mapping_scene(
        image_path=args.image,
        use_mapping=use_map,
        use_texcoord=use_tc,
        scale=tuple(args.scale),
        location=tuple(args.location),
        rotation_z=args.rotation_z,
        coord=args.coord,
    )
    print(
        "QUANTTRACE_MAP", cube_obj.name, "mode", args.mode,
        "image", img.filepath, "uvs", len(cube_obj.data.uv_layers),
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_MAP wrote", args.out)
    return 0

if __name__ == "__main__":
    raise SystemExit(main() or 0)
