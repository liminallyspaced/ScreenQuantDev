# QuantTrace Slice 2ag: Mapping Location/Rotation/Scale linked from Combine XYZ (or Value).
from __future__ import annotations
import argparse, os, sys
import bpy


def _argv():
    a = sys.argv
    return a[a.index("--") + 1:] if "--" in a else []


def _link_combine_xyz(nt, mapping, sock_name, xyz, *, use_value_nodes=False):
    """Wire Combine XYZ (defaults or Value→X/Y/Z) into Mapping Location/Rotation/Scale.

    Location is is_unavailable under VECTOR in Blender 5.2 — set vector_type POINT
    before linking Location, then switch back to VECTOR (link persists).
    """
    comb = nt.nodes.new("ShaderNodeCombineXYZ")
    comb.location = (mapping.location[0] - 200, mapping.location[1] - {
        "Location": 0, "Rotation": 150, "Scale": 300
    }.get(sock_name, 0))
    x, y, z = float(xyz[0]), float(xyz[1]), float(xyz[2])
    if use_value_nodes:
        for axis, val, sock in (("X", x, comb.inputs["X"]),
                                ("Y", y, comb.inputs["Y"]),
                                ("Z", z, comb.inputs["Z"])):
            vnode = nt.nodes.new("ShaderNodeValue")
            vnode.label = f"{sock_name}.{axis}"
            vnode.outputs[0].default_value = val
            vnode.location = (comb.location[0] - 160, comb.location[1] - ord(axis) * 40)
            nt.links.new(vnode.outputs[0], sock)
    else:
        comb.inputs["X"].default_value = x
        comb.inputs["Y"].default_value = y
        comb.inputs["Z"].default_value = z

    # Location keyed lookup fails when VECTOR; iterate / use identifier while POINT.
    was = str(mapping.vector_type)
    if sock_name == "Location" and was == "VECTOR":
        mapping.vector_type = "POINT"
    target = None
    for s in mapping.inputs:
        if s.name == sock_name or s.identifier == sock_name:
            target = s
            break
    if target is None:
        raise RuntimeError(f"Mapping missing {sock_name}")
    # Drop existing links on target.
    for link in list(target.links):
        nt.links.remove(link)
    nt.links.new(comb.outputs["Vector"], target)
    if sock_name == "Location":
        mapping.vector_type = "VECTOR"
    elif was == "VECTOR":
        mapping.vector_type = "VECTOR"
    return comb


def build_slice2ag_scene(
    image_path="/tmp/qt_slice2ag_checker.png",
    *,
    mode="combxyz",
    scale=(2.0, 2.0, 2.0),
    location=(0.1, 0.2, 0.0),
    rotation_z=0.15,
    link_location=True,
    link_rotation=True,
    link_scale=True,
):
    """Locked cube + TEX_COORD UV → Mapping(VECTOR) → TEX_IMAGE with linked L/R/S.

    mode:
      combxyz       — Combine XYZ with unlinked X/Y/Z defaults → L/R/S
      combxyz_value — Combine XYZ ← Value nodes → L/R/S
      value_rot     — single Value → Rotation only (broadcast); Scale/Location unlinked
      unlinked      — Slice 2h regression (unlinked L/R/S constants)
    """
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    import _quanttrace_mapping_scene as mapsc

    mode_key = str(mode).strip().lower()
    if mode_key == "unlinked":
        scene, cube_obj, lamp, cam, img = mapsc.build_mapping_scene(
            image_path=image_path,
            use_mapping=True,
            use_texcoord=True,
            scale=scale,
            location=location,
            rotation_z=rotation_z,
            coord="UV",
        )
        print(
            "QUANTTRACE_SLICE2AG_WORLD mode unlinked",
            f"loc={tuple(location)} rot_z={rotation_z} scale={tuple(scale)}",
        )
        return scene, cube_obj, lamp, cam, img

    # Build base Mapping with unlinked defaults first, then rewire L/R/S.
    scene, cube_obj, lamp, cam, img = mapsc.build_mapping_scene(
        image_path=image_path,
        use_mapping=True,
        use_texcoord=True,
        scale=scale,
        location=location,
        rotation_z=rotation_z,
        coord="UV",
    )
    mat = cube_obj.data.materials[0]
    nt = mat.node_tree
    mapping = next(n for n in nt.nodes if n.type == "MAPPING")
    use_vals = mode_key == "combxyz_value"

    if mode_key in ("combxyz", "combxyz_value"):
        if link_location:
            _link_combine_xyz(
                nt, mapping, "Location", location, use_value_nodes=use_vals
            )
        if link_rotation:
            _link_combine_xyz(
                nt, mapping, "Rotation", (0.0, 0.0, float(rotation_z)),
                use_value_nodes=use_vals,
            )
        if link_scale:
            _link_combine_xyz(
                nt, mapping, "Scale", scale, use_value_nodes=use_vals
            )
        # Ensure VECTOR after Location rewire.
        mapping.vector_type = "VECTOR"
        print(
            "QUANTTRACE_SLICE2AG_WORLD mode", mode_key,
            f"loc={tuple(location)} rot_z={rotation_z} scale={tuple(scale)}",
            "loc_linked", _sock_linked(mapping, "Location"),
            "rot_linked", _sock_linked(mapping, "Rotation"),
            "scl_linked", _sock_linked(mapping, "Scale"),
        )
    elif mode_key == "value_rot":
        # Single Value → Rotation (float→float3 broadcast). Leave L/S unlinked.
        vnode = nt.nodes.new("ShaderNodeValue")
        vnode.outputs[0].default_value = float(rotation_z)
        vnode.location = (mapping.location[0] - 200, mapping.location[1])
        rot = mapping.inputs["Rotation"]
        for link in list(rot.links):
            nt.links.remove(link)
        nt.links.new(vnode.outputs[0], rot)
        mapping.vector_type = "VECTOR"
        print(
            "QUANTTRACE_SLICE2AG_WORLD mode value_rot",
            f"rot_value={rotation_z}",
            "rot_linked", rot.is_linked,
            "NOTE value broadcasts to (v,v,v) — not (0,0,v)",
        )
    else:
        raise RuntimeError(f"mode={mode!r} refused (Slice 2ag)")

    bpy.context.view_layer.update()
    return scene, cube_obj, lamp, cam, img


def _sock_linked(mapping, name: str) -> bool:
    for s in mapping.inputs:
        if s.name == name or s.identifier == name:
            return bool(s.is_linked)
    return False


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--render", action="store_true", default=False)
    p.add_argument("--out", default="/tmp/quanttrace_slice2ag_stock.exr")
    p.add_argument("--image", default="/tmp/qt_slice2ag_checker.png")
    p.add_argument("--res", type=int, default=64)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument(
        "--mode",
        choices=("combxyz", "combxyz_value", "value_rot", "unlinked"),
        default="combxyz",
    )
    p.add_argument("--scale", type=float, nargs=3, default=(2.0, 2.0, 2.0))
    p.add_argument("--location", type=float, nargs=3, default=(0.1, 0.2, 0.0))
    p.add_argument("--rotation-z", type=float, default=0.15)
    args = p.parse_args(_argv())
    scene, cube_obj, lamp, cam, img = build_slice2ag_scene(
        image_path=args.image,
        mode=args.mode,
        scale=tuple(args.scale),
        location=tuple(args.location),
        rotation_z=args.rotation_z,
    )
    print(
        "QUANTTRACE_SLICE2AG", cube_obj.name, "mode", args.mode,
        "image", getattr(img, "filepath", None),
    )
    if args.render:
        scene.render.resolution_x = scene.render.resolution_y = args.res
        scene.cycles.samples = args.samples
        scene.render.filepath = args.out
        bpy.ops.render.render(write_still=True)
        print("QUANTTRACE_SLICE2AG wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main() or 0)
