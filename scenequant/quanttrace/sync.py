# QuantTrace depsgraph → QT_SimpleScene packer (Slice 2b).
#
# Walks a Blender depsgraph and packs camera / meshes / Principled /
# AREA lights / world into ctypes QT_SimpleScene (1+1) or QT_Scene (N+N)
# for quanttrace_render_scene_rgba / quanttrace_render_qt_scene_rgba.
# Slice 2c/2d: up to 32 meshes + 16 AREA/POINT/SUN/SPOT lights, constant Principled.
# Slice 2f: TEX_IMAGE → Principled Base Color (default UV, disk filepath).
# Slice 2h: TEX_COORD UV (+ optional Mapping Vector-type constants) → TEX_IMAGE Vector.
# Slice 2i: TEX_IMAGE → Principled Roughness / Metallic (same Vector rules as Base Color).
# Slice 2j: Principled.Normal ← Normal Map (Tangent) ← TEX_IMAGE Color (same Vector rules).
# Slice 2k: TEX_COORD Generated (+ optional Mapping Vector-type) → TEX_IMAGE Vector.
# Slice 2l: TEX_COORD Object (+ optional Mapping Vector-type) → TEX_IMAGE Vector.
# Slice 2m: TEX_COORD Camera (+ optional Mapping Vector-type) → TEX_IMAGE Vector.
# Slice 2o: TEX_IMAGE → Principled IOR / Alpha (same Vector rules).
# Slice 2p: TEX_IMAGE → Principled Transmission Weight / Specular IOR Level
#   (Blender 5.x names; legacy Transmission / Specular accepted).
# Slice 2q: TEX_IMAGE → Principled Coat Weight / Sheen Weight / Emission Strength
#   (legacy Coat/Clearcoat, Sheen; Strength-only Emission). Coat Roughness/IOR/Tint,
#   Sheen Roughness/Tint, Emission Color still refuse. Other linked sockets / HDR worlds refuse.
# Slice 2e: soft POINT radius + is_sphere=!use_soft_falloff; SUN angle.
# Slice 2g: SPOT spot_size/spot_blend (+ soft radius / is_sphere).
# Make it Fast stays on stock Cycles.

from __future__ import annotations

import ctypes
import os
import math
from typing import Any, List, Optional, Sequence, Tuple


class QuantTraceSyncError(RuntimeError):
    """Depsgraph shape QuantTrace cannot export yet."""


def _matrix_3x4(m) -> List[float]:
    """First three rows of a Blender 4x4 matrix_world (row-major)."""
    return [
        float(m[0][0]), float(m[0][1]), float(m[0][2]), float(m[0][3]),
        float(m[1][0]), float(m[1][1]), float(m[1][2]), float(m[1][3]),
        float(m[2][0]), float(m[2][1]), float(m[2][2]), float(m[2][3]),
    ]


def _identity_3x4() -> List[float]:
    return [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0]



def _mul_tfm_point(tfm, x, y, z):
    """Apply Blender 3x4 row-major matrix_world to a point (double math)."""
    return (
        tfm[0] * x + tfm[1] * y + tfm[2] * z + tfm[3],
        tfm[4] * x + tfm[5] * y + tfm[6] * z + tfm[7],
        tfm[8] * x + tfm[9] * y + tfm[10] * z + tfm[11],
    )


def _world_verts(verts, tfm):
    """Bake object transform into vertex positions; caller uses identity tfm."""
    out = []
    for i in range(0, len(verts), 3):
        wx, wy, wz = _mul_tfm_point(tfm, verts[i], verts[i + 1], verts[i + 2])
        out.extend((float(wx), float(wy), float(wz)))
    return out


def _abspath_image(img) -> str:
    """Disk filepath for a Blender Image, or empty if packed/missing."""
    if img is None:
        return ""
    getter = getattr(img, "filepath_from_user", None)
    if callable(getter):
        try:
            raw = getter() or ""
        except Exception:
            raw = ""
    else:
        raw = getattr(img, "filepath", "") or ""
    raw = str(raw).strip()
    if not raw:
        return ""
    # bpy.path.abspath when available (// relative).
    try:
        import bpy  # type: ignore
        abspath = getattr(getattr(bpy, "path", None), "abspath", None)
        if callable(abspath):
            raw = abspath(raw)
    except Exception:
        pass
    raw = os.path.abspath(os.path.expanduser(raw))
    return raw if os.path.isfile(raw) else ""


def _sock_default_float3(sock) -> Tuple[float, float, float]:
    """Unlinked Vector/Location/Rotation/Scale default as float3."""
    dv = getattr(sock, "default_value", (0.0, 0.0, 0.0))
    return (float(dv[0]), float(dv[1]), float(dv[2]))


def _tex_coord_space_from_vector_link(vec_sock) -> str:
    """Return 'UV', 'Generated', 'Object', 'Camera', 'Window', or 'Reflection'.

    Object requires empty Object reference (no Blender object pointer /
    use_transform / object_itfm) — Cycles NODE_TEXCO_OBJECT only.
    Camera uses scene Camera::worldtocamera (NODE_TEXCO_CAMERA); no extra
    inverse-matrix ABI. from_instancer/from_dupli unused on Camera.
    Window uses camera_world_to_ndc (NODE_TEXCO_WINDOW); Reflection uses
    svm_texco_reflection (NODE_TEXCO_REFLECTION) — both from existing
    Camera::update data. Mesh objects only for Reflection tests (bg uses
    NODE_GEOM_I).
    """
    links = list(getattr(vec_sock, "links", None) or [])
    if len(links) != 1:
        raise QuantTraceSyncError(
            "Image/Mapping Vector must have exactly one link (Slice 2h/2k/2l/2m/2n)"
        )
    src = links[0]
    from_node = getattr(src, "from_node", None)
    from_sock = getattr(src, "from_socket", None)
    if from_node is None or getattr(from_node, "type", None) != "TEX_COORD":
        raise QuantTraceSyncError(
            "TEX_IMAGE/Mapping Vector must come from TEX_COORD (Slice 2h/2k/2l/2m/2n)"
        )
    sock_name = getattr(from_sock, "name", "") if from_sock is not None else ""
    key = str(sock_name).strip().lower()
    if key == "uv":
        return "UV"
    if key == "generated":
        return "Generated"
    if key == "object":
        # Empty Object only: ShaderNodeTexCoord.object set → use_transform.
        obj_ref = getattr(from_node, "object", None)
        if obj_ref is not None:
            raise QuantTraceSyncError(
                "TEX_COORD Object with Object reference refused "
                "(Slice 2l: empty Object / no object_itfm only)"
            )
        return "Object"
    if key == "camera":
        # Camera output; from_instancer is unused on NODE_TEXCO_CAMERA.
        return "Camera"
    if key == "window":
        return "Window"
    if key == "reflection":
        return "Reflection"
    raise QuantTraceSyncError(
        f"TEX_COORD output {sock_name!r} refused "
        "(Slice 2n accepts UV, Generated, Object, Camera, Window, or Reflection)"
    )


def _tex_coord_uv_from_vector_link(vec_sock) -> None:
    """Require Vector linked from TEX_COORD UV (compat wrapper)."""
    space = _tex_coord_space_from_vector_link(vec_sock)
    if space != "UV":
        raise QuantTraceSyncError(
            f"TEX_COORD output {space!r} refused (expected UV)"
        )


def _mapping_input_by_name(map_node, name: str):
    """Find Mapping input by name, including VECTOR-hidden Location."""
    inputs = getattr(map_node, "inputs", None)
    if inputs is None:
        return None
    # Keyed lookup fails for is_unavailable sockets (Blender 5.2 VECTOR Location).
    for sock in inputs:
        if getattr(sock, "name", None) == name or getattr(sock, "identifier", None) == name:
            return sock
    getter = getattr(inputs, "get", None)
    if callable(getter):
        return getter(name)
    return None


def _mapping_constants(map_node) -> Tuple[Tuple[float, float, float],
                                            Tuple[float, float, float],
                                            Tuple[float, float, float],
                                            int,
                                            str]:
    """Validate MAPPING: Vector-type, Vector←TEX_COORD UV/Generated/Object/Camera/Window/Reflection, unlinked L/R/S."""
    vtype = str(getattr(map_node, "vector_type", "POINT") or "POINT").upper()
    if vtype != "VECTOR":
        raise QuantTraceSyncError(
            f"Mapping vector_type={vtype!r} refused (Slice 2h needs VECTOR)"
        )
    vec_in = _mapping_input_by_name(map_node, "Vector")
    if vec_in is None or not getattr(vec_in, "is_linked", False):
        raise QuantTraceSyncError(
            "Mapping.Vector must be linked from TEX_COORD UV/Generated/Object/Camera/Window/Reflection (Slice 2h/2k/2l/2m/2n)"
        )
    space = _tex_coord_space_from_vector_link(vec_in)
    loc_s = _mapping_input_by_name(map_node, "Location")
    rot_s = _mapping_input_by_name(map_node, "Rotation")
    scl_s = _mapping_input_by_name(map_node, "Scale")
    for name, sock in (("Location", loc_s), ("Rotation", rot_s), ("Scale", scl_s)):
        if sock is None:
            raise QuantTraceSyncError(f"Mapping missing {name}")
        if getattr(sock, "is_linked", False):
            raise QuantTraceSyncError(
                f"Mapping.{name} is linked (Slice 2h needs unlinked constants)"
            )
    # NODE_MAPPING_TYPE_VECTOR == 2 (POINT=0, TEXTURE=1, VECTOR=2, NORMAL=3)
    # VECTOR SVM ignores Location; still pack DNA default for ABI honesty.
    return (
        _sock_default_float3(loc_s),
        _sock_default_float3(rot_s),
        _sock_default_float3(scl_s),
        2,
        space,
    )


def _empty_tex_info() -> dict:
    return {
        "image_path": "",
        "image_colorspace": "",
        "tex_vector_mode": 0,
        "map_location": (0.0, 0.0, 0.0),
        "map_rotation": (0.0, 0.0, 0.0),
        "map_scale": (1.0, 1.0, 1.0),
        "map_type": 2,
    }


def _tex_image_from_sock(sock, sock_label: str) -> dict:
    """If socket is TEX_IMAGE Color, return path/cs + Vector graph (2f/2h/2i)."""
    empty = _empty_tex_info()
    links = list(getattr(sock, "links", None) or [])
    if not links:
        return empty
    if len(links) != 1:
        raise QuantTraceSyncError(f"Principled.{sock_label} has multiple links")
    src = links[0]
    from_node = getattr(src, "from_node", None)
    from_sock = getattr(src, "from_socket", None)
    if from_node is None or getattr(from_node, "type", None) != "TEX_IMAGE":
        raise QuantTraceSyncError(
            f"Principled.{sock_label} link is not TEX_IMAGE (Slice 2f/2h/2i)"
        )
    sock_name = getattr(from_sock, "name", "Color") if from_sock is not None else "Color"
    if sock_name not in ("Color", "color"):
        raise QuantTraceSyncError(
            f"{sock_label} must come from Image Texture Color (Slice 2f/2h/2i)"
        )
    vec = None
    inputs = getattr(from_node, "inputs", None)
    if inputs is not None:
        getter = getattr(inputs, "get", None)
        vec = getter("Vector") if callable(getter) else None

    tex_vector_mode = 0  # QT_TEX_VECTOR_UNLINKED
    map_location = (0.0, 0.0, 0.0)
    map_rotation = (0.0, 0.0, 0.0)
    map_scale = (1.0, 1.0, 1.0)
    map_type = 2

    if vec is not None and getattr(vec, "is_linked", False):
        vlinks = list(getattr(vec, "links", None) or [])
        if len(vlinks) != 1:
            raise QuantTraceSyncError(
                "Image Texture Vector has multiple links (Slice 2h)"
            )
        vsrc = vlinks[0]
        vnode = getattr(vsrc, "from_node", None)
        vsock = getattr(vsrc, "from_socket", None)
        vtype = getattr(vnode, "type", None) if vnode is not None else None
        vname = getattr(vsock, "name", "") if vsock is not None else ""
        if vtype == "TEX_COORD":
            key = str(vname).strip().lower()
            if key == "uv":
                tex_vector_mode = 1  # QT_TEX_VECTOR_TEXCOORD
            elif key == "generated":
                tex_vector_mode = 3  # QT_TEX_VECTOR_TEXCOORD_GENERATED
            elif key == "object":
                obj_ref = getattr(vnode, "object", None)
                if obj_ref is not None:
                    raise QuantTraceSyncError(
                        "TEX_COORD Object with Object reference refused "
                        "(Slice 2l: empty Object / no object_itfm only)"
                    )
                tex_vector_mode = 5  # QT_TEX_VECTOR_TEXCOORD_OBJECT
            elif key == "camera":
                tex_vector_mode = 7  # QT_TEX_VECTOR_TEXCOORD_CAMERA
            elif key == "window":
                tex_vector_mode = 9  # QT_TEX_VECTOR_TEXCOORD_WINDOW
            elif key == "reflection":
                tex_vector_mode = 11  # QT_TEX_VECTOR_TEXCOORD_REFLECTION
            else:
                raise QuantTraceSyncError(
                    f"TEX_COORD output {vname!r} refused "
                    "(Slice 2n accepts UV, Generated, Object, Camera, Window, or Reflection)"
                )
        elif vtype == "MAPPING":
            if vname not in ("Vector", "vector"):
                raise QuantTraceSyncError(
                    "Image Texture Vector must come from Mapping Vector"
                )
            map_location, map_rotation, map_scale, map_type, space = _mapping_constants(
                vnode
            )
            if space == "Generated":
                tex_vector_mode = 4  # QT_TEX_VECTOR_MAPPING_GENERATED
            elif space == "Object":
                tex_vector_mode = 6  # QT_TEX_VECTOR_MAPPING_OBJECT
            elif space == "Camera":
                tex_vector_mode = 8  # QT_TEX_VECTOR_MAPPING_CAMERA
            elif space == "Window":
                tex_vector_mode = 10  # QT_TEX_VECTOR_MAPPING_WINDOW
            elif space == "Reflection":
                tex_vector_mode = 12  # QT_TEX_VECTOR_MAPPING_REFLECTION
            else:
                tex_vector_mode = 2  # QT_TEX_VECTOR_MAPPING (UV)
        else:
            raise QuantTraceSyncError(
                f"Image Texture Vector from {vtype!r} refused "
                "(Slice 2h/2k/2l/2m/2n: TEX_COORD UV/Generated/Object/Camera/Window/Reflection or Mapping only)"
            )

    img = getattr(from_node, "image", None)
    if img is None:
        raise QuantTraceSyncError("Image Texture has no image")
    path = _abspath_image(img)
    if not path:
        raise QuantTraceSyncError(
            "Image Texture filepath missing on disk (Slice 2f/2h/2i; packed-only refused)"
        )
    cs = ""
    settings = getattr(img, "colorspace_settings", None)
    if settings is not None:
        cs = str(getattr(settings, "name", "") or "")
    return {
        "image_path": path,
        "image_colorspace": cs,
        "tex_vector_mode": tex_vector_mode,
        "map_location": map_location,
        "map_rotation": map_rotation,
        "map_scale": map_scale,
        "map_type": map_type,
    }


def _tex_image_from_base_color(sock) -> dict:
    """Compat wrapper: Base Color TEX_IMAGE (Slice 2f/2h)."""
    return _tex_image_from_sock(sock, "Base Color")



def _prefix_tex(info: dict, prefix: str) -> dict:
    """Remap image_path/… keys to rough_/metal_/normal_/ior_/alpha_/trans_/spec_/coat_/sheen_/emit_str_ (or keep for base)."""
    if not prefix:
        return dict(info)
    return {
        f"{prefix}image_path": info.get("image_path") or "",
        f"{prefix}image_colorspace": info.get("image_colorspace") or "",
        f"{prefix}tex_vector_mode": int(info.get("tex_vector_mode", 0) or 0),
        f"{prefix}map_location": info.get("map_location") or (0.0, 0.0, 0.0),
        f"{prefix}map_rotation": info.get("map_rotation") or (0.0, 0.0, 0.0),
        f"{prefix}map_scale": info.get("map_scale") or (1.0, 1.0, 1.0),
        f"{prefix}map_type": int(info.get("map_type", 2) if info.get("map_type") is not None else 2),
    }



def _empty_normal_info() -> dict:
    out = _prefix_tex(_empty_tex_info(), "normal_")
    out["normal_strength"] = 1.0
    return out


def _normal_map_from_sock(sock) -> dict:
    """Principled.Normal ← Normal Map.Normal; Color ← TEX_IMAGE; Strength unlinked.

    Space must be Tangent (default). Object/World, Bump, linked Strength,
    packed-only images, and custom uv_map names refuse.
    """
    empty = _empty_normal_info()
    if sock is None:
        return empty
    links = list(getattr(sock, "links", None) or [])
    if not links:
        return empty
    if len(links) != 1:
        raise QuantTraceSyncError("Principled.Normal has multiple links")
    src = links[0]
    from_node = getattr(src, "from_node", None)
    from_sock = getattr(src, "from_socket", None)
    ntype = getattr(from_node, "type", None) if from_node is not None else None
    if ntype != "NORMAL_MAP":
        raise QuantTraceSyncError(
            f"Principled.Normal from {ntype!r} refused "
            "(Slice 2j: Normal Map only; Bump/etc refuse)"
        )
    sock_name = getattr(from_sock, "name", "") if from_sock is not None else ""
    if sock_name not in ("Normal", "normal"):
        raise QuantTraceSyncError(
            "Principled.Normal must come from Normal Map Normal (Slice 2j)"
        )
    space = str(getattr(from_node, "space", "TANGENT") or "TANGENT").upper()
    if space not in ("TANGENT",):
        raise QuantTraceSyncError(
            f"Normal Map space={space!r} refused (Slice 2j: Tangent only)"
        )
    uv_map = str(getattr(from_node, "uv_map", "") or "").strip()
    if uv_map:
        raise QuantTraceSyncError(
            f"Normal Map uv_map={uv_map!r} refused (Slice 2j: default UV only)"
        )
    inputs = getattr(from_node, "inputs", None)
    getter = getattr(inputs, "get", None) if inputs is not None else None
    strength_sock = getter("Strength") if callable(getter) else None
    color_sock = getter("Color") if callable(getter) else None
    if strength_sock is not None and getattr(strength_sock, "is_linked", False):
        raise QuantTraceSyncError(
            "Normal Map Strength is linked (Slice 2j: unlinked float only)"
        )
    strength = 1.0
    if strength_sock is not None:
        strength = float(getattr(strength_sock, "default_value", 1.0))
    if color_sock is None or not getattr(color_sock, "is_linked", False):
        raise QuantTraceSyncError(
            "Normal Map Color must be TEX_IMAGE (Slice 2j)"
        )
    tex = _tex_image_from_sock(color_sock, "Normal Map Color")
    out = _prefix_tex(tex, "normal_")
    out["normal_strength"] = strength
    return out


def _input_by_names(bsdf, *names):
    """First matching Principled input (Blender 5.x name, then legacy)."""
    inputs = getattr(bsdf, "inputs", None)
    if inputs is None:
        return None, None
    getter = getattr(inputs, "get", None)
    for name in names:
        sock = getter(name) if callable(getter) else None
        if sock is not None:
            return name, sock
    return None, None


def _principled_from_material(mat) -> dict:
    """Return principled dict (constants + optional TEX_IMAGE on Base/Rough/Metal/IOR/Alpha/Trans/Spec/Coat/Sheen/EmitStr)."""
    empty = {
        "base_color": (0.8, 0.8, 0.8),
        "roughness": 0.5,
        "metallic": 0.0,
        "ior": 1.45,
        "alpha": 1.0,
        **_empty_tex_info(),
        **_prefix_tex(_empty_tex_info(), "rough_"),
        **_prefix_tex(_empty_tex_info(), "metal_"),
        **_empty_normal_info(),
        **_prefix_tex(_empty_tex_info(), "ior_"),
        **_prefix_tex(_empty_tex_info(), "alpha_"),
        **_prefix_tex(_empty_tex_info(), "trans_"),
        **_prefix_tex(_empty_tex_info(), "spec_"),
        **_prefix_tex(_empty_tex_info(), "coat_"),
        **_prefix_tex(_empty_tex_info(), "sheen_"),
        **_prefix_tex(_empty_tex_info(), "emit_str_"),
    }
    if mat is None:
        raise QuantTraceSyncError("mesh has no material")
    if not getattr(mat, "use_nodes", False) or mat.node_tree is None:
        diff = getattr(mat, "diffuse_color", (0.8, 0.8, 0.8, 1.0))
        empty["base_color"] = (float(diff[0]), float(diff[1]), float(diff[2]))
        return empty
    bsdf = None
    for node in mat.node_tree.nodes:
        if getattr(node, "type", None) == "BSDF_PRINCIPLED":
            bsdf = node
            break
    if bsdf is None:
        raise QuantTraceSyncError("material has no Principled BSDF (Slice 2b)")
    base_tex = _empty_tex_info()
    rough_tex = _empty_tex_info()
    metal_tex = _empty_tex_info()
    ior_tex = _empty_tex_info()
    alpha_tex = _empty_tex_info()
    trans_tex = _empty_tex_info()
    spec_tex = _empty_tex_info()
    coat_tex = _empty_tex_info()
    sheen_tex = _empty_tex_info()
    emit_str_tex = _empty_tex_info()
    # 5.x names first; legacy Transmission / Specular / Coat / Sheen accepted.
    allowed = (
        ("Base Color", ("Base Color",), "base"),
        ("Roughness", ("Roughness",), "rough"),
        ("Metallic", ("Metallic",), "metal"),
        ("IOR", ("IOR",), "ior"),
        ("Alpha", ("Alpha",), "alpha"),
        ("Transmission Weight", ("Transmission Weight", "Transmission"), "trans"),
        ("Specular IOR Level", ("Specular IOR Level", "Specular"), "spec"),
        ("Coat Weight", ("Coat Weight", "Coat", "Clearcoat"), "coat"),
        ("Sheen Weight", ("Sheen Weight", "Sheen"), "sheen"),
        ("Emission Strength", ("Emission Strength",), "emit_str"),
    )
    for label, names, kind in allowed:
        _name, sock = _input_by_names(bsdf, *names)
        if sock is None or not getattr(sock, "is_linked", False):
            continue
        tex = _tex_image_from_sock(sock, label)
        if kind == "base":
            base_tex = tex
        elif kind == "rough":
            rough_tex = tex
        elif kind == "metal":
            metal_tex = tex
        elif kind == "ior":
            ior_tex = tex
        elif kind == "alpha":
            alpha_tex = tex
        elif kind == "trans":
            trans_tex = tex
        elif kind == "spec":
            spec_tex = tex
        elif kind == "coat":
            coat_tex = tex
        elif kind == "sheen":
            sheen_tex = tex
        elif kind == "emit_str":
            emit_str_tex = tex
    for rname in (
        "Coat Roughness", "Coat IOR", "Coat Tint",
        "Sheen Roughness", "Sheen Tint",
        "Emission Color", "Emission",
    ):
        _n, sock = _input_by_names(bsdf, rname)
        if sock is not None and getattr(sock, "is_linked", False):
            raise QuantTraceSyncError(
                f"Principled.{rname} is linked "
                "(Slice 2q: Coat Roughness/IOR/Tint, Sheen Roughness/Tint, "
                "Emission Color refuse; Coat/Sheen Weight + Emission Strength may be TEX_IMAGE)"
            )
    normal_info = _normal_map_from_sock(bsdf.inputs.get("Normal"))
    base = bsdf.inputs["Base Color"].default_value
    return {
        "base_color": (float(base[0]), float(base[1]), float(base[2])),
        "roughness": float(bsdf.inputs["Roughness"].default_value),
        "metallic": float(bsdf.inputs["Metallic"].default_value),
        "ior": float(bsdf.inputs["IOR"].default_value),
        "alpha": float(bsdf.inputs["Alpha"].default_value),
        **base_tex,
        **_prefix_tex(rough_tex, "rough_"),
        **_prefix_tex(metal_tex, "metal_"),
        **normal_info,
        **_prefix_tex(ior_tex, "ior_"),
        **_prefix_tex(alpha_tex, "alpha_"),
        **_prefix_tex(trans_tex, "trans_"),
        **_prefix_tex(spec_tex, "spec_"),
        **_prefix_tex(coat_tex, "coat_"),
        **_prefix_tex(sheen_tex, "sheen_"),
        **_prefix_tex(emit_str_tex, "emit_str_"),
    }



def _mesh_corner_uvs(obj, ntris: int) -> List[float]:
    """loop_triangle corner UVs (ntris * 3 * 2) from the active UV map."""
    mesh = obj.data
    layers = getattr(mesh, "uv_layers", None)
    uv_layer = None
    if layers:
        uv_layer = getattr(layers, "active", None)
        if uv_layer is None and len(layers) > 0:
            uv_layer = layers[0]
    if uv_layer is None:
        raise QuantTraceSyncError("textured Principled needs a UV map")
    loops = getattr(mesh, "loop_triangles", None)
    if loops is None or len(loops) == 0:
        raise QuantTraceSyncError("mesh has no loop_triangles for UVs")
    uvs: List[float] = []
    for tri in loops:
        for loop_i in tri.loops:
            uv = uv_layer.data[loop_i].uv
            uvs.extend((float(uv[0]), float(uv[1])))
    if len(uvs) != ntris * 6:
        raise QuantTraceSyncError(
            f"UV count {len(uvs)} != ntris*6 ({ntris * 6})"
        )
    return uvs


def _mesh_arrays(obj) -> Tuple[List[float], List[int]]:
    """Object-local verts + loop_triangles (CCW)."""
    mesh = obj.data
    # Ensure loop triangles exist (depsgraph-evaluated meshes usually do).
    calc = getattr(mesh, "calc_loop_triangles", None)
    if callable(calc):
        try:
            calc()
        except Exception:
            pass
    verts: List[float] = []
    for v in mesh.vertices:
        co = v.co
        verts.extend((float(co[0]), float(co[1]), float(co[2])))
    tris: List[int] = []
    loops = getattr(mesh, "loop_triangles", None)
    if loops is None or len(loops) == 0:
        raise QuantTraceSyncError("mesh has no loop_triangles")
    for tri in loops:
        idx = tri.vertices
        tris.extend((int(idx[0]), int(idx[1]), int(idx[2])))
    if len(verts) < 9 or len(tris) < 3:
        raise QuantTraceSyncError("mesh too small")
    return verts, tris


def _world_strength(scene) -> float:
    world = getattr(scene, "world", None)
    if world is None:
        return 0.0
    if not getattr(world, "use_nodes", False) or world.node_tree is None:
        # Nodeless world color — treat as strength 1 with that color; Slice 2b
        # only supports black+strength, so refuse non-black.
        col = getattr(world, "color", (0.0, 0.0, 0.0))
        if abs(float(col[0])) + abs(float(col[1])) + abs(float(col[2])) > 1e-6:
            raise QuantTraceSyncError("nodeless world color not black (Slice 2b)")
        return 0.0
    bg = None
    for node in world.node_tree.nodes:
        if getattr(node, "type", None) == "BACKGROUND":
            bg = node
            break
    if bg is None:
        return 0.0
    color_sock = bg.inputs.get("Color")
    if color_sock is not None and getattr(color_sock, "is_linked", False):
        raise QuantTraceSyncError("world Background Color linked (Slice 2b)")
    if color_sock is not None:
        col = color_sock.default_value
        if abs(float(col[0])) + abs(float(col[1])) + abs(float(col[2])) > 1e-6:
            raise QuantTraceSyncError("world Background Color not black (Slice 2b)")
    strength_sock = bg.inputs.get("Strength")
    if strength_sock is not None and getattr(strength_sock, "is_linked", False):
        raise QuantTraceSyncError("world Background Strength linked (Slice 2b)")
    return float(strength_sock.default_value) if strength_sock is not None else 0.0


def _light_strength(lamp_obj, scene) -> Tuple[float, float, float]:
    """Official Blender sync: color * energy * exp2(exposure)."""
    data = lamp_obj.data
    color = getattr(data, "color", (1.0, 1.0, 1.0))
    energy = float(getattr(data, "energy", 1.0))
    exposure = 0.0
    view = getattr(scene, "view_settings", None)
    if view is not None:
        exposure = float(getattr(view, "exposure", 0.0) or 0.0)
    scale = energy * (2.0 ** exposure)
    return (float(color[0]) * scale, float(color[1]) * scale, float(color[2]) * scale)


def _render_size(scene) -> Tuple[int, int, int]:
    scale = float(scene.render.resolution_percentage) / 100.0
    width = max(1, int(scene.render.resolution_x * scale))
    height = max(1, int(scene.render.resolution_y * scale))
    cycles = getattr(scene, "cycles", None)
    samples = int(getattr(cycles, "samples", 128) or 128)
    samples = max(1, min(samples, 8192))
    width = min(width, 8192)
    height = min(height, 8192)
    return width, height, samples


def can_sync_simple(scene) -> bool:
    """True when depsgraph shape is Slice 2b simple (no raise)."""
    try:
        classify_simple(scene)
        return True
    except QuantTraceSyncError:
        return False


def classify_simple(scene) -> dict:
    """Validate + return object handles for a simple scene. Raises otherwise."""
    if scene is None:
        raise QuantTraceSyncError("no scene")
    objs = [o for o in (getattr(scene, "objects", []) or [])
            if not getattr(o, "hide_render", False)]
    meshes = [o for o in objs if getattr(o, "type", None) == "MESH"]
    lights = [o for o in objs if getattr(o, "type", None) == "LIGHT"]
    cams = [o for o in objs if getattr(o, "type", None) == "CAMERA"]
    if len(meshes) != 1:
        raise QuantTraceSyncError(f"need exactly 1 mesh, got {len(meshes)}")
    if len(lights) != 1:
        raise QuantTraceSyncError(f"need exactly 1 light, got {len(lights)}")
    if len(cams) != 1:
        raise QuantTraceSyncError(f"need exactly 1 camera, got {len(cams)}")
    lamp = lights[0]
    data = getattr(lamp, "data", None)
    if data is None or getattr(data, "type", None) != "AREA":
        raise QuantTraceSyncError("light must be AREA")
    # use_nodes is fine: Blender 5.x default AREA tree is Emission Strength 1.
    # We still take strength from RNA color*energy*exp2(exposure) and build
    # Emission×1 on the native side (matches locked-cube Session path).
    mesh_obj = meshes[0]
    mats = list(getattr(mesh_obj.data, "materials", []) or [])
    mat = mats[0] if mats else None
    # Probe principled + world early.
    _principled_from_material(mat)
    _world_strength(scene)
    return {
        "mesh": mesh_obj,
        "light": lamp,
        "camera": cams[0],
        "material": mat,
    }



def _pack_tex_fields(pr: dict) -> dict:
    """Flatten base/rough/metal/normal/ior/alpha/trans/spec/coat/sheen/emit_str TEX_IMAGE fields."""
    def loc(key, default):
        return list(pr.get(key) or default)
    out = {
        "image_path": pr.get("image_path") or "",
        "image_colorspace": pr.get("image_colorspace") or "",
        "tex_vector_mode": int(pr.get("tex_vector_mode", 0) or 0),
        "map_location": loc("map_location", (0.0, 0.0, 0.0)),
        "map_rotation": loc("map_rotation", (0.0, 0.0, 0.0)),
        "map_scale": loc("map_scale", (1.0, 1.0, 1.0)),
        "map_type": int(pr.get("map_type", 2) if pr.get("map_type") is not None else 2),
        "rough_image_path": pr.get("rough_image_path") or "",
        "rough_image_colorspace": pr.get("rough_image_colorspace") or "",
        "rough_tex_vector_mode": int(pr.get("rough_tex_vector_mode", 0) or 0),
        "rough_map_location": loc("rough_map_location", (0.0, 0.0, 0.0)),
        "rough_map_rotation": loc("rough_map_rotation", (0.0, 0.0, 0.0)),
        "rough_map_scale": loc("rough_map_scale", (1.0, 1.0, 1.0)),
        "rough_map_type": int(pr.get("rough_map_type", 2) if pr.get("rough_map_type") is not None else 2),
        "metal_image_path": pr.get("metal_image_path") or "",
        "metal_image_colorspace": pr.get("metal_image_colorspace") or "",
        "metal_tex_vector_mode": int(pr.get("metal_tex_vector_mode", 0) or 0),
        "metal_map_location": loc("metal_map_location", (0.0, 0.0, 0.0)),
        "metal_map_rotation": loc("metal_map_rotation", (0.0, 0.0, 0.0)),
        "metal_map_scale": loc("metal_map_scale", (1.0, 1.0, 1.0)),
        "metal_map_type": int(pr.get("metal_map_type", 2) if pr.get("metal_map_type") is not None else 2),
        "normal_image_path": pr.get("normal_image_path") or "",
        "normal_image_colorspace": pr.get("normal_image_colorspace") or "",
        "normal_tex_vector_mode": int(pr.get("normal_tex_vector_mode", 0) or 0),
        "normal_map_location": loc("normal_map_location", (0.0, 0.0, 0.0)),
        "normal_map_rotation": loc("normal_map_rotation", (0.0, 0.0, 0.0)),
        "normal_map_scale": loc("normal_map_scale", (1.0, 1.0, 1.0)),
        "normal_map_type": int(pr.get("normal_map_type", 2) if pr.get("normal_map_type") is not None else 2),
        "normal_strength": float(pr.get("normal_strength", 1.0) if pr.get("normal_strength") is not None else 1.0),
        "ior_image_path": pr.get("ior_image_path") or "",
        "ior_image_colorspace": pr.get("ior_image_colorspace") or "",
        "ior_tex_vector_mode": int(pr.get("ior_tex_vector_mode", 0) or 0),
        "ior_map_location": loc("ior_map_location", (0.0, 0.0, 0.0)),
        "ior_map_rotation": loc("ior_map_rotation", (0.0, 0.0, 0.0)),
        "ior_map_scale": loc("ior_map_scale", (1.0, 1.0, 1.0)),
        "ior_map_type": int(pr.get("ior_map_type", 2) if pr.get("ior_map_type") is not None else 2),
        "alpha_image_path": pr.get("alpha_image_path") or "",
        "alpha_image_colorspace": pr.get("alpha_image_colorspace") or "",
        "alpha_tex_vector_mode": int(pr.get("alpha_tex_vector_mode", 0) or 0),
        "alpha_map_location": loc("alpha_map_location", (0.0, 0.0, 0.0)),
        "alpha_map_rotation": loc("alpha_map_rotation", (0.0, 0.0, 0.0)),
        "alpha_map_scale": loc("alpha_map_scale", (1.0, 1.0, 1.0)),
        "alpha_map_type": int(pr.get("alpha_map_type", 2) if pr.get("alpha_map_type") is not None else 2),
        "trans_image_path": pr.get("trans_image_path") or "",
        "trans_image_colorspace": pr.get("trans_image_colorspace") or "",
        "trans_tex_vector_mode": int(pr.get("trans_tex_vector_mode", 0) or 0),
        "trans_map_location": loc("trans_map_location", (0.0, 0.0, 0.0)),
        "trans_map_rotation": loc("trans_map_rotation", (0.0, 0.0, 0.0)),
        "trans_map_scale": loc("trans_map_scale", (1.0, 1.0, 1.0)),
        "trans_map_type": int(pr.get("trans_map_type", 2) if pr.get("trans_map_type") is not None else 2),
        "spec_image_path": pr.get("spec_image_path") or "",
        "spec_image_colorspace": pr.get("spec_image_colorspace") or "",
        "spec_tex_vector_mode": int(pr.get("spec_tex_vector_mode", 0) or 0),
        "spec_map_location": loc("spec_map_location", (0.0, 0.0, 0.0)),
        "spec_map_rotation": loc("spec_map_rotation", (0.0, 0.0, 0.0)),
        "spec_map_scale": loc("spec_map_scale", (1.0, 1.0, 1.0)),
        "spec_map_type": int(pr.get("spec_map_type", 2) if pr.get("spec_map_type") is not None else 2),
        "coat_image_path": pr.get("coat_image_path") or "",
        "coat_image_colorspace": pr.get("coat_image_colorspace") or "",
        "coat_tex_vector_mode": int(pr.get("coat_tex_vector_mode", 0) or 0),
        "coat_map_location": loc("coat_map_location", (0.0, 0.0, 0.0)),
        "coat_map_rotation": loc("coat_map_rotation", (0.0, 0.0, 0.0)),
        "coat_map_scale": loc("coat_map_scale", (1.0, 1.0, 1.0)),
        "coat_map_type": int(pr.get("coat_map_type", 2) if pr.get("coat_map_type") is not None else 2),
        "sheen_image_path": pr.get("sheen_image_path") or "",
        "sheen_image_colorspace": pr.get("sheen_image_colorspace") or "",
        "sheen_tex_vector_mode": int(pr.get("sheen_tex_vector_mode", 0) or 0),
        "sheen_map_location": loc("sheen_map_location", (0.0, 0.0, 0.0)),
        "sheen_map_rotation": loc("sheen_map_rotation", (0.0, 0.0, 0.0)),
        "sheen_map_scale": loc("sheen_map_scale", (1.0, 1.0, 1.0)),
        "sheen_map_type": int(pr.get("sheen_map_type", 2) if pr.get("sheen_map_type") is not None else 2),
        "emit_str_image_path": pr.get("emit_str_image_path") or "",
        "emit_str_image_colorspace": pr.get("emit_str_image_colorspace") or "",
        "emit_str_tex_vector_mode": int(pr.get("emit_str_tex_vector_mode", 0) or 0),
        "emit_str_map_location": loc("emit_str_map_location", (0.0, 0.0, 0.0)),
        "emit_str_map_rotation": loc("emit_str_map_rotation", (0.0, 0.0, 0.0)),
        "emit_str_map_scale": loc("emit_str_map_scale", (1.0, 1.0, 1.0)),
        "emit_str_map_type": int(pr.get("emit_str_map_type", 2) if pr.get("emit_str_map_type") is not None else 2),
    }
    return out


def _any_tex_path(pr: dict) -> bool:
    return bool(
        (pr.get("image_path") or "")
        or (pr.get("rough_image_path") or "")
        or (pr.get("metal_image_path") or "")
        or (pr.get("normal_image_path") or "")
        or (pr.get("ior_image_path") or "")
        or (pr.get("alpha_image_path") or "")
        or (pr.get("trans_image_path") or "")
        or (pr.get("spec_image_path") or "")
        or (pr.get("coat_image_path") or "")
        or (pr.get("sheen_image_path") or "")
        or (pr.get("emit_str_image_path") or "")
    )


def pack_simple_scene(scene, depsgraph=None) -> dict:
    """Pack a simple scene into Python buffers + metadata.

    Returns a dict with keys matching QT_SimpleScene fields (lists/floats).
    Does not build ctypes — engine.py does that.
    """
    # Prefer evaluated objects when a depsgraph is provided.
    if depsgraph is not None:
        scene_eval = getattr(depsgraph, "scene_eval", None) or getattr(depsgraph, "scene", None)
        if scene_eval is not None:
            scene = scene_eval
    handles = classify_simple(scene)
    mesh_obj = handles["mesh"]
    lamp = handles["light"]
    cam_obj = handles["camera"]
    mat = handles["material"]

    # Evaluated mesh for modifiers.
    if depsgraph is not None:
        try:
            mesh_obj = mesh_obj.evaluated_get(depsgraph)
        except Exception:
            pass

    verts, tris = _mesh_arrays(mesh_obj)
    mesh_tfm = _matrix_3x4(mesh_obj.matrix_world)
    verts = _world_verts(verts, mesh_tfm)
    mesh_tfm = _identity_3x4()
    pr = _principled_from_material(mat)
    base, rough, metal, ior, alpha = (
        pr["base_color"], pr["roughness"], pr["metallic"], pr["ior"], pr["alpha"]
    )
    ntris = len(tris) // 3
    tex_fields = _pack_tex_fields(pr)
    uvs: List[float] = []
    if _any_tex_path(pr):
        uvs = _mesh_corner_uvs(mesh_obj, ntris)
    width, height, samples = _render_size(scene)

    cam_data = cam_obj.data
    lens = float(getattr(cam_data, "lens", 50.0) or 50.0)
    sensor_w_mm = float(getattr(cam_data, "sensor_width", 36.0) or 36.0)
    sensor_h_mm = float(getattr(cam_data, "sensor_height", 24.0) or 24.0)
    fov = 2.0 * math.atan((sensor_w_mm * 0.5) / lens)
    near = float(getattr(cam_data, "clip_start", 0.1) or 0.1)
    far = float(getattr(cam_data, "clip_end", 1000.0) or 1000.0)

    lamp_data = lamp.data
    size = float(getattr(lamp_data, "size", 1.0) or 1.0)
    # Square area: sizeu = sizev = size (Blender AREA default).
    size_y = getattr(lamp_data, "size_y", None)
    sizeu = size
    sizev = float(size_y) if size_y is not None and getattr(lamp_data, "shape", "SQUARE") == "RECTANGLE" else size

    return {
        "width": width,
        "height": height,
        "samples": samples,
        "verts": verts,
        "tris": tris,
        "mesh_tfm": mesh_tfm,
        "cam_tfm": _matrix_3x4(cam_obj.matrix_world),
        "cam_fov": fov,
        "cam_sensor_w": sensor_w_mm / 1000.0,
        "cam_sensor_h": sensor_h_mm / 1000.0,
        "cam_near": near,
        "cam_far": far,
        "light_tfm": _matrix_3x4(lamp.matrix_world),
        "light_sizeu": sizeu,
        "light_sizev": sizev,
        "light_strength": list(_light_strength(lamp, scene)),
        "base_color": list(base),
        "roughness": rough,
        "metallic": metal,
        "ior": ior,
        "alpha": alpha,
        "world_strength": _world_strength(scene),
        "uvs": uvs,
        **tex_fields,
    }


QT_MAX_MESHES = 32
QT_MAX_LIGHTS = 16


def _visible_objects(scene, depsgraph=None):
    """MESH/LIGHT/CAMERA lists in depsgraph instance order when available."""
    meshes = []
    lights = []
    cams = []
    if depsgraph is not None and hasattr(depsgraph, "object_instances"):
        seen = set()
        for inst in depsgraph.object_instances:
            obj = getattr(inst, "object", None)
            if obj is None:
                continue
            if getattr(obj, "hide_render", False):
                continue
            key = getattr(obj, "name_full", None) or id(obj)
            if key in seen:
                continue
            seen.add(key)
            otype = getattr(obj, "type", None)
            if otype == "MESH":
                meshes.append(obj)
            elif otype == "LIGHT":
                lights.append(obj)
            elif otype == "CAMERA":
                cams.append(obj)
        if meshes or lights or cams:
            return meshes, lights, cams
    objs = [o for o in (getattr(scene, "objects", []) or [])
            if not getattr(o, "hide_render", False)]
    meshes = [o for o in objs if getattr(o, "type", None) == "MESH"]
    lights = [o for o in objs if getattr(o, "type", None) == "LIGHT"]
    cams = [o for o in objs if getattr(o, "type", None) == "CAMERA"]
    return meshes, lights, cams


def _area_light_sizes(lamp_data):
    size = float(getattr(lamp_data, "size", 1.0) or 1.0)
    size_y = getattr(lamp_data, "size_y", None)
    sizeu = size
    sizev = float(size_y) if size_y is not None and getattr(lamp_data, "shape", "SQUARE") == "RECTANGLE" else size
    return sizeu, sizev


def classify_scene(scene, depsgraph=None) -> dict:
    """Validate + return handles for Slice 2c (N mesh + N AREA). Raises otherwise."""
    if scene is None:
        raise QuantTraceSyncError("no scene")
    meshes, lights, cams = _visible_objects(scene, depsgraph=depsgraph)
    if not (1 <= len(meshes) <= QT_MAX_MESHES):
        raise QuantTraceSyncError(
            f"need 1..{QT_MAX_MESHES} meshes, got {len(meshes)}"
        )
    if not (1 <= len(lights) <= QT_MAX_LIGHTS):
        raise QuantTraceSyncError(
            f"need 1..{QT_MAX_LIGHTS} lights, got {len(lights)}"
        )
    if len(cams) != 1:
        raise QuantTraceSyncError(f"need exactly 1 camera, got {len(cams)}")
    for lamp in lights:
        data = getattr(lamp, "data", None)
        ltype = getattr(data, "type", None) if data is not None else None
        if data is None or ltype not in ("AREA", "POINT", "SUN", "SPOT"):
            raise QuantTraceSyncError(
                f"light {getattr(lamp, 'name', '?')} must be AREA/POINT/SUN/SPOT "
                f"(got {ltype})"
            )
    mats = []
    for mesh_obj in meshes:
        mlist = list(getattr(mesh_obj.data, "materials", []) or [])
        mat = mlist[0] if mlist else None
        _principled_from_material(mat)
        mats.append(mat)
    _world_strength(scene)
    return {
        "meshes": meshes,
        "lights": lights,
        "camera": cams[0],
        "materials": mats,
    }


def can_sync_scene(scene, depsgraph=None) -> bool:
    try:
        classify_scene(scene, depsgraph=depsgraph)
        return True
    except QuantTraceSyncError:
        return False


def pack_scene(scene, depsgraph=None) -> dict:
    """Pack N meshes + N AREA lights into Python buffers for QT_Scene.

    Returns dict with width/height/samples, camera fields, world_strength,
    and lists `meshes` / `lights` (each a dict of arrays/floats).
    """
    if depsgraph is not None:
        scene_eval = getattr(depsgraph, "scene_eval", None) or getattr(depsgraph, "scene", None)
        if scene_eval is not None:
            scene = scene_eval
    handles = classify_scene(scene, depsgraph=depsgraph)
    mesh_objs = list(handles["meshes"])
    lamps = list(handles["lights"])
    cam_obj = handles["camera"]
    mats = list(handles["materials"])

    packed_meshes = []
    for mesh_obj, mat in zip(mesh_objs, mats):
        eval_obj = mesh_obj
        if depsgraph is not None:
            try:
                eval_obj = mesh_obj.evaluated_get(depsgraph)
            except Exception:
                eval_obj = mesh_obj
        verts, tris = _mesh_arrays(eval_obj)
        tfm = _matrix_3x4(eval_obj.matrix_world)
        pr = _principled_from_material(mat)
        base, rough, metal, ior, alpha = (
            pr["base_color"], pr["roughness"], pr["metallic"], pr["ior"], pr["alpha"]
        )
        tex_fields = _pack_tex_fields(pr)
        uvs: List[float] = []
        if _any_tex_path(pr):
            uvs = _mesh_corner_uvs(eval_obj, len(tris) // 3)
        packed_meshes.append({
            "verts": verts,
            "tris": tris,
            "tfm": tfm,
            "base_color": list(base),
            "roughness": rough,
            "metallic": metal,
            "ior": ior,
            "alpha": alpha,
            "name": getattr(mesh_obj, "name", "") or "",
            "uvs": uvs,
            **tex_fields,
        })

    packed_lights = []
    for lamp in lamps:
        lamp_data = lamp.data
        ltype = getattr(lamp_data, "type", "AREA")
        if ltype == "POINT":
            kind = 1  # QT_LIGHT_POINT
            sizeu = sizev = 0.0
            radius = float(getattr(lamp_data, "shadow_soft_size", 0.0) or 0.0)
            angle = 0.0
            smooth = 0.0
            # Blender Cycles sync: is_sphere = !use_soft_falloff
            soft_fo = bool(getattr(lamp_data, "use_soft_falloff", True))
            is_sphere = 0 if soft_fo else 1
        elif ltype == "SUN":
            kind = 2  # QT_LIGHT_SUN
            sizeu = sizev = 0.0
            radius = 0.0
            angle = float(getattr(lamp_data, "angle", 0.0091803) or 0.0091803)
            smooth = 0.0
            is_sphere = 0
        elif ltype == "SPOT":
            kind = 3  # QT_LIGHT_SPOT
            sizeu = sizev = 0.0
            radius = float(getattr(lamp_data, "shadow_soft_size", 0.0) or 0.0)
            # Blender: spotsize→angle, spotblend→smooth
            angle = float(getattr(lamp_data, "spot_size", 0.785398) or 0.785398)
            smooth = float(getattr(lamp_data, "spot_blend", 0.15) or 0.0)
            soft_fo = bool(getattr(lamp_data, "use_soft_falloff", True))
            is_sphere = 0 if soft_fo else 1
        else:
            kind = 0  # QT_LIGHT_AREA
            sizeu, sizev = _area_light_sizes(lamp_data)
            radius = 0.0
            angle = 0.0
            smooth = 0.0
            is_sphere = 0
        packed_lights.append({
            "tfm": _matrix_3x4(lamp.matrix_world),
            "sizeu": sizeu,
            "sizev": sizev,
            "strength": list(_light_strength(lamp, scene)),
            "name": getattr(lamp, "name", "") or "",
            "kind": kind,
            "radius": radius,
            "angle": angle,
            "is_sphere": is_sphere,
            "smooth": smooth,
        })

    width, height, samples = _render_size(scene)
    cam_data = cam_obj.data
    lens = float(getattr(cam_data, "lens", 50.0) or 50.0)
    sensor_w_mm = float(getattr(cam_data, "sensor_width", 36.0) or 36.0)
    sensor_h_mm = float(getattr(cam_data, "sensor_height", 24.0) or 24.0)
    # Prefer Blender's own angle (sensor_fit AUTO already applied) over lens math.
    fov = 2.0 * math.atan((sensor_w_mm * 0.5) / lens)
    near = float(getattr(cam_data, "clip_start", 0.1) or 0.1)
    far = float(getattr(cam_data, "clip_end", 1000.0) or 1000.0)

    return {
        "width": width,
        "height": height,
        "samples": samples,
        "meshes": packed_meshes,
        "lights": packed_lights,
        "cam_tfm": _matrix_3x4(cam_obj.matrix_world),
        "cam_fov": fov,
        "cam_sensor_w": sensor_w_mm / 1000.0,
        "cam_sensor_h": sensor_h_mm / 1000.0,
        "cam_near": near,
        "cam_far": far,
        "world_strength": _world_strength(scene),
    }



def _fill_tex_ctypes(desc, packed: dict, keep: list) -> None:
    """Write base/rough/metal TEX_IMAGE fields onto a QT_Mesh/SimpleScene-like struct."""
    def enc(key):
        b = (packed.get(key) or "").encode("utf-8")
        keep.append(b)
        return b if b else None

    def vec3(attr, key, default=(0.0, 0.0, 0.0)):
        for i, v in enumerate(packed.get(key) or default):
            getattr(desc, attr)[i] = float(v)

    desc.image_path = enc("image_path")
    desc.image_colorspace = enc("image_colorspace")
    desc.tex_vector_mode = int(packed.get("tex_vector_mode", 0) or 0)
    vec3("map_location", "map_location")
    vec3("map_rotation", "map_rotation")
    vec3("map_scale", "map_scale", (1.0, 1.0, 1.0))
    desc.map_type = int(packed.get("map_type", 2) if packed.get("map_type") is not None else 2)

    desc.rough_image_path = enc("rough_image_path")
    desc.rough_image_colorspace = enc("rough_image_colorspace")
    desc.rough_tex_vector_mode = int(packed.get("rough_tex_vector_mode", 0) or 0)
    vec3("rough_map_location", "rough_map_location")
    vec3("rough_map_rotation", "rough_map_rotation")
    vec3("rough_map_scale", "rough_map_scale", (1.0, 1.0, 1.0))
    desc.rough_map_type = int(
        packed.get("rough_map_type", 2) if packed.get("rough_map_type") is not None else 2
    )

    desc.metal_image_path = enc("metal_image_path")
    desc.metal_image_colorspace = enc("metal_image_colorspace")
    desc.metal_tex_vector_mode = int(packed.get("metal_tex_vector_mode", 0) or 0)
    vec3("metal_map_location", "metal_map_location")
    vec3("metal_map_rotation", "metal_map_rotation")
    vec3("metal_map_scale", "metal_map_scale", (1.0, 1.0, 1.0))
    desc.metal_map_type = int(
        packed.get("metal_map_type", 2) if packed.get("metal_map_type") is not None else 2
    )

    desc.normal_image_path = enc("normal_image_path")
    desc.normal_image_colorspace = enc("normal_image_colorspace")
    desc.normal_tex_vector_mode = int(packed.get("normal_tex_vector_mode", 0) or 0)
    vec3("normal_map_location", "normal_map_location")
    vec3("normal_map_rotation", "normal_map_rotation")
    vec3("normal_map_scale", "normal_map_scale", (1.0, 1.0, 1.0))
    desc.normal_map_type = int(
        packed.get("normal_map_type", 2) if packed.get("normal_map_type") is not None else 2
    )
    desc.normal_strength = float(
        packed.get("normal_strength", 1.0) if packed.get("normal_strength") is not None else 1.0
    )

    desc.ior_image_path = enc("ior_image_path")
    desc.ior_image_colorspace = enc("ior_image_colorspace")
    desc.ior_tex_vector_mode = int(packed.get("ior_tex_vector_mode", 0) or 0)
    vec3("ior_map_location", "ior_map_location")
    vec3("ior_map_rotation", "ior_map_rotation")
    vec3("ior_map_scale", "ior_map_scale", (1.0, 1.0, 1.0))
    desc.ior_map_type = int(
        packed.get("ior_map_type", 2) if packed.get("ior_map_type") is not None else 2
    )

    desc.alpha_image_path = enc("alpha_image_path")
    desc.alpha_image_colorspace = enc("alpha_image_colorspace")
    desc.alpha_tex_vector_mode = int(packed.get("alpha_tex_vector_mode", 0) or 0)
    vec3("alpha_map_location", "alpha_map_location")
    vec3("alpha_map_rotation", "alpha_map_rotation")
    vec3("alpha_map_scale", "alpha_map_scale", (1.0, 1.0, 1.0))
    desc.alpha_map_type = int(
        packed.get("alpha_map_type", 2) if packed.get("alpha_map_type") is not None else 2
    )

    desc.trans_image_path = enc("trans_image_path")
    desc.trans_image_colorspace = enc("trans_image_colorspace")
    desc.trans_tex_vector_mode = int(packed.get("trans_tex_vector_mode", 0) or 0)
    vec3("trans_map_location", "trans_map_location")
    vec3("trans_map_rotation", "trans_map_rotation")
    vec3("trans_map_scale", "trans_map_scale", (1.0, 1.0, 1.0))
    desc.trans_map_type = int(
        packed.get("trans_map_type", 2) if packed.get("trans_map_type") is not None else 2
    )

    desc.spec_image_path = enc("spec_image_path")
    desc.spec_image_colorspace = enc("spec_image_colorspace")
    desc.spec_tex_vector_mode = int(packed.get("spec_tex_vector_mode", 0) or 0)
    vec3("spec_map_location", "spec_map_location")
    vec3("spec_map_rotation", "spec_map_rotation")
    vec3("spec_map_scale", "spec_map_scale", (1.0, 1.0, 1.0))
    desc.spec_map_type = int(
        packed.get("spec_map_type", 2) if packed.get("spec_map_type") is not None else 2
    )

    desc.coat_image_path = enc("coat_image_path")
    desc.coat_image_colorspace = enc("coat_image_colorspace")
    desc.coat_tex_vector_mode = int(packed.get("coat_tex_vector_mode", 0) or 0)
    vec3("coat_map_location", "coat_map_location")
    vec3("coat_map_rotation", "coat_map_rotation")
    vec3("coat_map_scale", "coat_map_scale", (1.0, 1.0, 1.0))
    desc.coat_map_type = int(
        packed.get("coat_map_type", 2) if packed.get("coat_map_type") is not None else 2
    )

    desc.sheen_image_path = enc("sheen_image_path")
    desc.sheen_image_colorspace = enc("sheen_image_colorspace")
    desc.sheen_tex_vector_mode = int(packed.get("sheen_tex_vector_mode", 0) or 0)
    vec3("sheen_map_location", "sheen_map_location")
    vec3("sheen_map_rotation", "sheen_map_rotation")
    vec3("sheen_map_scale", "sheen_map_scale", (1.0, 1.0, 1.0))
    desc.sheen_map_type = int(
        packed.get("sheen_map_type", 2) if packed.get("sheen_map_type") is not None else 2
    )

    desc.emit_str_image_path = enc("emit_str_image_path")
    desc.emit_str_image_colorspace = enc("emit_str_image_colorspace")
    desc.emit_str_tex_vector_mode = int(packed.get("emit_str_tex_vector_mode", 0) or 0)
    vec3("emit_str_map_location", "emit_str_map_location")
    vec3("emit_str_map_rotation", "emit_str_map_rotation")
    vec3("emit_str_map_scale", "emit_str_map_scale", (1.0, 1.0, 1.0))
    desc.emit_str_map_type = int(
        packed.get("emit_str_map_type", 2) if packed.get("emit_str_map_type") is not None else 2
    )


def make_qt_simple_scene_type():
    """ctypes Structure matching QT_SimpleScene in quanttrace.h."""

    class QT_SimpleScene(ctypes.Structure):
        _fields_ = [
            ("width", ctypes.c_int),
            ("height", ctypes.c_int),
            ("samples", ctypes.c_int),
            ("nverts", ctypes.c_int),
            ("ntris", ctypes.c_int),
            ("verts", ctypes.POINTER(ctypes.c_float)),
            ("tris", ctypes.POINTER(ctypes.c_int)),
            ("mesh_tfm", ctypes.c_float * 12),
            ("cam_tfm", ctypes.c_float * 12),
            ("cam_fov", ctypes.c_float),
            ("cam_sensor_w", ctypes.c_float),
            ("cam_sensor_h", ctypes.c_float),
            ("cam_near", ctypes.c_float),
            ("cam_far", ctypes.c_float),
            ("light_tfm", ctypes.c_float * 12),
            ("light_sizeu", ctypes.c_float),
            ("light_sizev", ctypes.c_float),
            ("light_strength", ctypes.c_float * 3),
            ("base_color", ctypes.c_float * 3),
            ("roughness", ctypes.c_float),
            ("metallic", ctypes.c_float),
            ("ior", ctypes.c_float),
            ("alpha", ctypes.c_float),
            ("world_strength", ctypes.c_float),
            ("exr_path", ctypes.c_char_p),
            ("uvs", ctypes.POINTER(ctypes.c_float)),
            ("image_path", ctypes.c_char_p),
            ("image_colorspace", ctypes.c_char_p),
            ("tex_vector_mode", ctypes.c_int),
            ("map_location", ctypes.c_float * 3),
            ("map_rotation", ctypes.c_float * 3),
            ("map_scale", ctypes.c_float * 3),
            ("map_type", ctypes.c_int),
            ("rough_image_path", ctypes.c_char_p),
            ("rough_image_colorspace", ctypes.c_char_p),
            ("rough_tex_vector_mode", ctypes.c_int),
            ("rough_map_location", ctypes.c_float * 3),
            ("rough_map_rotation", ctypes.c_float * 3),
            ("rough_map_scale", ctypes.c_float * 3),
            ("rough_map_type", ctypes.c_int),
            ("metal_image_path", ctypes.c_char_p),
            ("metal_image_colorspace", ctypes.c_char_p),
            ("metal_tex_vector_mode", ctypes.c_int),
            ("metal_map_location", ctypes.c_float * 3),
            ("metal_map_rotation", ctypes.c_float * 3),
            ("metal_map_scale", ctypes.c_float * 3),
            ("metal_map_type", ctypes.c_int),
            ("normal_image_path", ctypes.c_char_p),
            ("normal_image_colorspace", ctypes.c_char_p),
            ("normal_tex_vector_mode", ctypes.c_int),
            ("normal_map_location", ctypes.c_float * 3),
            ("normal_map_rotation", ctypes.c_float * 3),
            ("normal_map_scale", ctypes.c_float * 3),
            ("normal_map_type", ctypes.c_int),
            ("normal_strength", ctypes.c_float),
            ("ior_image_path", ctypes.c_char_p),
            ("ior_image_colorspace", ctypes.c_char_p),
            ("ior_tex_vector_mode", ctypes.c_int),
            ("ior_map_location", ctypes.c_float * 3),
            ("ior_map_rotation", ctypes.c_float * 3),
            ("ior_map_scale", ctypes.c_float * 3),
            ("ior_map_type", ctypes.c_int),
            ("alpha_image_path", ctypes.c_char_p),
            ("alpha_image_colorspace", ctypes.c_char_p),
            ("alpha_tex_vector_mode", ctypes.c_int),
            ("alpha_map_location", ctypes.c_float * 3),
            ("alpha_map_rotation", ctypes.c_float * 3),
            ("alpha_map_scale", ctypes.c_float * 3),
            ("alpha_map_type", ctypes.c_int),
            ("trans_image_path", ctypes.c_char_p),
            ("trans_image_colorspace", ctypes.c_char_p),
            ("trans_tex_vector_mode", ctypes.c_int),
            ("trans_map_location", ctypes.c_float * 3),
            ("trans_map_rotation", ctypes.c_float * 3),
            ("trans_map_scale", ctypes.c_float * 3),
            ("trans_map_type", ctypes.c_int),
            ("spec_image_path", ctypes.c_char_p),
            ("spec_image_colorspace", ctypes.c_char_p),
            ("spec_tex_vector_mode", ctypes.c_int),
            ("spec_map_location", ctypes.c_float * 3),
            ("spec_map_rotation", ctypes.c_float * 3),
            ("spec_map_scale", ctypes.c_float * 3),
            ("spec_map_type", ctypes.c_int),
            ("coat_image_path", ctypes.c_char_p),
            ("coat_image_colorspace", ctypes.c_char_p),
            ("coat_tex_vector_mode", ctypes.c_int),
            ("coat_map_location", ctypes.c_float * 3),
            ("coat_map_rotation", ctypes.c_float * 3),
            ("coat_map_scale", ctypes.c_float * 3),
            ("coat_map_type", ctypes.c_int),
            ("sheen_image_path", ctypes.c_char_p),
            ("sheen_image_colorspace", ctypes.c_char_p),
            ("sheen_tex_vector_mode", ctypes.c_int),
            ("sheen_map_location", ctypes.c_float * 3),
            ("sheen_map_rotation", ctypes.c_float * 3),
            ("sheen_map_scale", ctypes.c_float * 3),
            ("sheen_map_type", ctypes.c_int),
            ("emit_str_image_path", ctypes.c_char_p),
            ("emit_str_image_colorspace", ctypes.c_char_p),
            ("emit_str_tex_vector_mode", ctypes.c_int),
            ("emit_str_map_location", ctypes.c_float * 3),
            ("emit_str_map_rotation", ctypes.c_float * 3),
            ("emit_str_map_scale", ctypes.c_float * 3),
            ("emit_str_map_type", ctypes.c_int),
        ]

    return QT_SimpleScene


def to_ctypes(packed: dict, QT_SimpleScene, exr_path: Optional[str] = None):
    """Build a QT_SimpleScene + keep-alive buffers from pack_simple_scene output."""
    verts = (ctypes.c_float * len(packed["verts"]))(*packed["verts"])
    tris = (ctypes.c_int * len(packed["tris"]))(*packed["tris"])
    desc = QT_SimpleScene()
    desc.width = int(packed["width"])
    desc.height = int(packed["height"])
    desc.samples = int(packed["samples"])
    desc.nverts = len(packed["verts"]) // 3
    desc.ntris = len(packed["tris"]) // 3
    desc.verts = ctypes.cast(verts, ctypes.POINTER(ctypes.c_float))
    desc.tris = ctypes.cast(tris, ctypes.POINTER(ctypes.c_int))
    for i, v in enumerate(packed["mesh_tfm"]):
        desc.mesh_tfm[i] = float(v)
    for i, v in enumerate(packed["cam_tfm"]):
        desc.cam_tfm[i] = float(v)
    desc.cam_fov = float(packed["cam_fov"])
    desc.cam_sensor_w = float(packed["cam_sensor_w"])
    desc.cam_sensor_h = float(packed["cam_sensor_h"])
    desc.cam_near = float(packed["cam_near"])
    desc.cam_far = float(packed["cam_far"])
    for i, v in enumerate(packed["light_tfm"]):
        desc.light_tfm[i] = float(v)
    desc.light_sizeu = float(packed["light_sizeu"])
    desc.light_sizev = float(packed["light_sizev"])
    for i, v in enumerate(packed["light_strength"]):
        desc.light_strength[i] = float(v)
    for i, v in enumerate(packed["base_color"]):
        desc.base_color[i] = float(v)
    desc.roughness = float(packed["roughness"])
    desc.metallic = float(packed["metallic"])
    desc.ior = float(packed["ior"])
    desc.alpha = float(packed["alpha"])
    desc.world_strength = float(packed["world_strength"])
    if exr_path:
        desc.exr_path = exr_path.encode("utf-8")
    else:
        desc.exr_path = None
    uvs_list = packed.get("uvs") or []
    uvs_buf = (ctypes.c_float * len(uvs_list))(*uvs_list) if uvs_list else None
    if uvs_buf is not None:
        desc.uvs = ctypes.cast(uvs_buf, ctypes.POINTER(ctypes.c_float))
    else:
        desc.uvs = None
    tex_keep: list = []
    _fill_tex_ctypes(desc, packed, tex_keep)
    # Keep buffers alive with the struct.
    desc._keep = (verts, tris, uvs_buf, tex_keep)
    return desc


def make_qt_scene_types():
    """ctypes Structures matching QT_Mesh / QT_Light / QT_Scene."""

    class QT_Mesh(ctypes.Structure):
        _fields_ = [
            ("nverts", ctypes.c_int),
            ("ntris", ctypes.c_int),
            ("verts", ctypes.POINTER(ctypes.c_float)),
            ("tris", ctypes.POINTER(ctypes.c_int)),
            ("tfm", ctypes.c_float * 12),
            ("base_color", ctypes.c_float * 3),
            ("roughness", ctypes.c_float),
            ("metallic", ctypes.c_float),
            ("ior", ctypes.c_float),
            ("alpha", ctypes.c_float),
            ("name", ctypes.c_char_p),
            ("uvs", ctypes.POINTER(ctypes.c_float)),
            ("image_path", ctypes.c_char_p),
            ("image_colorspace", ctypes.c_char_p),
            ("tex_vector_mode", ctypes.c_int),
            ("map_location", ctypes.c_float * 3),
            ("map_rotation", ctypes.c_float * 3),
            ("map_scale", ctypes.c_float * 3),
            ("map_type", ctypes.c_int),
            ("rough_image_path", ctypes.c_char_p),
            ("rough_image_colorspace", ctypes.c_char_p),
            ("rough_tex_vector_mode", ctypes.c_int),
            ("rough_map_location", ctypes.c_float * 3),
            ("rough_map_rotation", ctypes.c_float * 3),
            ("rough_map_scale", ctypes.c_float * 3),
            ("rough_map_type", ctypes.c_int),
            ("metal_image_path", ctypes.c_char_p),
            ("metal_image_colorspace", ctypes.c_char_p),
            ("metal_tex_vector_mode", ctypes.c_int),
            ("metal_map_location", ctypes.c_float * 3),
            ("metal_map_rotation", ctypes.c_float * 3),
            ("metal_map_scale", ctypes.c_float * 3),
            ("metal_map_type", ctypes.c_int),
            ("normal_image_path", ctypes.c_char_p),
            ("normal_image_colorspace", ctypes.c_char_p),
            ("normal_tex_vector_mode", ctypes.c_int),
            ("normal_map_location", ctypes.c_float * 3),
            ("normal_map_rotation", ctypes.c_float * 3),
            ("normal_map_scale", ctypes.c_float * 3),
            ("normal_map_type", ctypes.c_int),
            ("normal_strength", ctypes.c_float),
            ("ior_image_path", ctypes.c_char_p),
            ("ior_image_colorspace", ctypes.c_char_p),
            ("ior_tex_vector_mode", ctypes.c_int),
            ("ior_map_location", ctypes.c_float * 3),
            ("ior_map_rotation", ctypes.c_float * 3),
            ("ior_map_scale", ctypes.c_float * 3),
            ("ior_map_type", ctypes.c_int),
            ("alpha_image_path", ctypes.c_char_p),
            ("alpha_image_colorspace", ctypes.c_char_p),
            ("alpha_tex_vector_mode", ctypes.c_int),
            ("alpha_map_location", ctypes.c_float * 3),
            ("alpha_map_rotation", ctypes.c_float * 3),
            ("alpha_map_scale", ctypes.c_float * 3),
            ("alpha_map_type", ctypes.c_int),
            ("trans_image_path", ctypes.c_char_p),
            ("trans_image_colorspace", ctypes.c_char_p),
            ("trans_tex_vector_mode", ctypes.c_int),
            ("trans_map_location", ctypes.c_float * 3),
            ("trans_map_rotation", ctypes.c_float * 3),
            ("trans_map_scale", ctypes.c_float * 3),
            ("trans_map_type", ctypes.c_int),
            ("spec_image_path", ctypes.c_char_p),
            ("spec_image_colorspace", ctypes.c_char_p),
            ("spec_tex_vector_mode", ctypes.c_int),
            ("spec_map_location", ctypes.c_float * 3),
            ("spec_map_rotation", ctypes.c_float * 3),
            ("spec_map_scale", ctypes.c_float * 3),
            ("spec_map_type", ctypes.c_int),
            ("coat_image_path", ctypes.c_char_p),
            ("coat_image_colorspace", ctypes.c_char_p),
            ("coat_tex_vector_mode", ctypes.c_int),
            ("coat_map_location", ctypes.c_float * 3),
            ("coat_map_rotation", ctypes.c_float * 3),
            ("coat_map_scale", ctypes.c_float * 3),
            ("coat_map_type", ctypes.c_int),
            ("sheen_image_path", ctypes.c_char_p),
            ("sheen_image_colorspace", ctypes.c_char_p),
            ("sheen_tex_vector_mode", ctypes.c_int),
            ("sheen_map_location", ctypes.c_float * 3),
            ("sheen_map_rotation", ctypes.c_float * 3),
            ("sheen_map_scale", ctypes.c_float * 3),
            ("sheen_map_type", ctypes.c_int),
            ("emit_str_image_path", ctypes.c_char_p),
            ("emit_str_image_colorspace", ctypes.c_char_p),
            ("emit_str_tex_vector_mode", ctypes.c_int),
            ("emit_str_map_location", ctypes.c_float * 3),
            ("emit_str_map_rotation", ctypes.c_float * 3),
            ("emit_str_map_scale", ctypes.c_float * 3),
            ("emit_str_map_type", ctypes.c_int),
        ]

    class QT_Light(ctypes.Structure):
        _fields_ = [
            ("tfm", ctypes.c_float * 12),
            ("sizeu", ctypes.c_float),
            ("sizev", ctypes.c_float),
            ("strength", ctypes.c_float * 3),
            ("name", ctypes.c_char_p),
            ("kind", ctypes.c_int),
            ("radius", ctypes.c_float),
            ("angle", ctypes.c_float),
            ("is_sphere", ctypes.c_int),
            ("smooth", ctypes.c_float),
        ]

    class QT_Scene(ctypes.Structure):
        _fields_ = [
            ("width", ctypes.c_int),
            ("height", ctypes.c_int),
            ("samples", ctypes.c_int),
            ("nmeshes", ctypes.c_int),
            ("nlights", ctypes.c_int),
            ("meshes", ctypes.POINTER(QT_Mesh)),
            ("lights", ctypes.POINTER(QT_Light)),
            ("cam_tfm", ctypes.c_float * 12),
            ("cam_fov", ctypes.c_float),
            ("cam_sensor_w", ctypes.c_float),
            ("cam_sensor_h", ctypes.c_float),
            ("cam_near", ctypes.c_float),
            ("cam_far", ctypes.c_float),
            ("world_strength", ctypes.c_float),
            ("exr_path", ctypes.c_char_p),
        ]

    return QT_Mesh, QT_Light, QT_Scene


def to_ctypes_scene(packed: dict, QT_Mesh, QT_Light, QT_Scene, exr_path=None):
    """Build a QT_Scene + keep-alive buffers from pack_scene output."""
    nmeshes = len(packed["meshes"])
    nlights = len(packed["lights"])
    meshes_arr = (QT_Mesh * nmeshes)()
    lights_arr = (QT_Light * nlights)()
    keep = []
    for i, m in enumerate(packed["meshes"]):
        verts = (ctypes.c_float * len(m["verts"]))(*m["verts"])
        tris = (ctypes.c_int * len(m["tris"]))(*m["tris"])
        keep.append((verts, tris))
        meshes_arr[i].nverts = len(m["verts"]) // 3
        meshes_arr[i].ntris = len(m["tris"]) // 3
        meshes_arr[i].verts = ctypes.cast(verts, ctypes.POINTER(ctypes.c_float))
        meshes_arr[i].tris = ctypes.cast(tris, ctypes.POINTER(ctypes.c_int))
        for j, v in enumerate(m["tfm"]):
            meshes_arr[i].tfm[j] = float(v)
        for j, v in enumerate(m["base_color"]):
            meshes_arr[i].base_color[j] = float(v)
        meshes_arr[i].roughness = float(m["roughness"])
        meshes_arr[i].metallic = float(m["metallic"])
        meshes_arr[i].ior = float(m["ior"])
        meshes_arr[i].alpha = float(m["alpha"])
        name = m.get("name") or ""
        nb = name.encode("utf-8")
        keep.append(nb)
        meshes_arr[i].name = nb
        uvs_list = m.get("uvs") or []
        if uvs_list:
            uvs_buf = (ctypes.c_float * len(uvs_list))(*uvs_list)
            keep.append(uvs_buf)
            meshes_arr[i].uvs = ctypes.cast(uvs_buf, ctypes.POINTER(ctypes.c_float))
        else:
            meshes_arr[i].uvs = None
        _fill_tex_ctypes(meshes_arr[i], m, keep)
    for i, L in enumerate(packed["lights"]):
        for j, v in enumerate(L["tfm"]):
            lights_arr[i].tfm[j] = float(v)
        lights_arr[i].sizeu = float(L["sizeu"])
        lights_arr[i].sizev = float(L["sizev"])
        for j, v in enumerate(L["strength"]):
            lights_arr[i].strength[j] = float(v)
        lname = L.get("name") or ""
        lb = lname.encode("utf-8")
        keep.append(lb)
        lights_arr[i].name = lb
        lights_arr[i].kind = int(L.get("kind", 0))
        lights_arr[i].radius = float(L.get("radius", 0.0))
        lights_arr[i].angle = float(L.get("angle", 0.0))
        lights_arr[i].is_sphere = int(L.get("is_sphere", 0))
        lights_arr[i].smooth = float(L.get("smooth", 0.0))
    desc = QT_Scene()
    desc.width = int(packed["width"])
    desc.height = int(packed["height"])
    desc.samples = int(packed["samples"])
    desc.nmeshes = nmeshes
    desc.nlights = nlights
    desc.meshes = ctypes.cast(meshes_arr, ctypes.POINTER(QT_Mesh))
    desc.lights = ctypes.cast(lights_arr, ctypes.POINTER(QT_Light))
    for i, v in enumerate(packed["cam_tfm"]):
        desc.cam_tfm[i] = float(v)
    desc.cam_fov = float(packed["cam_fov"])
    desc.cam_sensor_w = float(packed["cam_sensor_w"])
    desc.cam_sensor_h = float(packed["cam_sensor_h"])
    desc.cam_near = float(packed["cam_near"])
    desc.cam_far = float(packed["cam_far"])
    desc.world_strength = float(packed["world_strength"])
    if exr_path:
        desc.exr_path = exr_path.encode("utf-8")
    else:
        desc.exr_path = None
    desc._keep = (meshes_arr, lights_arr, keep)
    return desc

