# QuantTrace depsgraph → QT_SimpleScene packer (Slice 2b).
#
# Walks a Blender depsgraph and packs camera / meshes / Principled /
# AREA lights / world into ctypes QT_SimpleScene (1+1) or QT_Scene (N+N)
# for quanttrace_render_scene_rgba / quanttrace_render_qt_scene_rgba.
# Slice 2c/2d: up to 32 meshes + 16 AREA/POINT/SUN/SPOT lights, constant Principled.
# Slice 2f: TEX_IMAGE → Principled Base Color (default UV; disk or packed).
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
#   (legacy Coat/Clearcoat, Sheen; Strength-only Emission).
# Slice 2r: TEX_IMAGE → Principled Emission Color (legacy Emission). Color socket,
#   not float.
# Slice 2s: TEX_IMAGE → Principled Coat Roughness / Coat IOR / Coat Tint /
#   Sheen Roughness / Sheen Tint.
# Slice 2t: Principled.Coat Normal ← Normal Map (Tangent) ← TEX_IMAGE Color
#   (same Vector rules as Normal). Object/World/Bump/linked Strength still refuse.
# Slice 2u: TEX_IMAGE → Principled Specular Tint / Thin Film Thickness+IOR /
#   Subsurface Weight / Radius / Scale.
# Slice 2v: TEX_IMAGE → Principled Subsurface IOR / Subsurface Anisotropy /
#   Diffuse Roughness. Thin Wall is BOOLEAN in 5.2 — packer refuses TEX_IMAGE.
# Slice 2w: TEX_IMAGE → Principled Anisotropic / Rotation / Tangent.
# Slice 2x: Principled.Normal ← Bump ← TEX_IMAGE Height (bump_* ABI).
#   Coat Normal stays Normal-Map-only (Bump on Coat Normal refuses).
# Slice 2y: Principled Thin Wall unlinked BOOLEAN + unlinked Transmission Weight
#   constant. Linked Thin Wall still refuses (BOOLEAN, not TEX_IMAGE).
# Slice 2aa: Environment Texture world (empty path = Slice 2b black).
# Slice 2ab: TEX_COORD Object-with-pointer (use_transform + ob_tfm).
#   Empty Object ref stays Slice 2l (use_transform=0). Mesh-level one pointer.
# Slice 2af: packed-only images materialize to /tmp/quanttrace_packed/ (filepath ABI).
# Slice 2ag: Mapping L/R/S linked Combine XYZ / Value (same float3 ABI).
# Slice 2ah: world Background Strength linked from ShaderNodeValue (same float ABI).
#   TEX_IMAGE/Mix/RGB/Noise/Math → Strength / Sky/Nishita kitchens still refuse.
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


# Slice 2af: packed-only images materialize to a stable temp under this dir.
_PACKED_IMAGE_CACHE_DIR = "/tmp/quanttrace_packed"


def _guess_image_ext(raw: bytes, img) -> str:
    """Extension for materialized packed bytes (ABI stays filepath)."""
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if len(raw) >= 4 and raw[:4] == b"v/1\x01":
        return ".exr"
    if raw.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if raw.startswith(b"BM"):
        return ".bmp"
    if raw.startswith(b"II") or raw.startswith(b"MM"):
        return ".tif"
    fmt = str(getattr(img, "file_format", "") or "").upper()
    mapping = {
        "PNG": ".png",
        "JPEG": ".jpg",
        "JPG": ".jpg",
        "OPEN_EXR": ".exr",
        "OPEN_EXR_MULTILAYER": ".exr",
        "TIFF": ".tif",
        "BMP": ".bmp",
        "TARGA": ".tga",
        "TARGA_RAW": ".tga",
        "HDR": ".hdr",
        "WEBP": ".webp",
    }
    if fmt in mapping:
        return mapping[fmt]
    # Prefer filepath suffix when present (even if file is gone).
    for attr in ("filepath", "filepath_raw"):
        fp = str(getattr(img, attr, "") or "")
        if "." in fp:
            suf = os.path.splitext(fp)[1].lower()
            if suf in (".png", ".jpg", ".jpeg", ".exr", ".tif", ".tiff",
                       ".bmp", ".tga", ".hdr", ".webp"):
                return ".jpg" if suf == ".jpeg" else (".tif" if suf == ".tiff" else suf)
    return ".bin"


def _materialize_packed_image(img) -> str:
    """Write packed_file bytes to /tmp/quanttrace_packed/<name>_<hash>.<ext>.

    Stable within a session (same bytes → same path). Empty if no packed bytes.
    """
    pf = getattr(img, "packed_file", None)
    if pf is None:
        return ""
    data = getattr(pf, "data", None)
    if not data:
        return ""
    try:
        raw = bytes(data)
    except Exception:
        return ""
    if not raw:
        return ""
    import hashlib

    digest = hashlib.sha1(raw).hexdigest()[:16]
    name = str(getattr(img, "name", "img") or "img")
    safe = "".join(c if (c.isalnum() or c in "-_") else "_" for c in name)[:64] or "img"
    ext = _guess_image_ext(raw, img)
    out_dir = _PACKED_IMAGE_CACHE_DIR
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError:
        return ""
    out = os.path.join(out_dir, f"{safe}_{digest}{ext}")
    if not os.path.isfile(out) or os.path.getsize(out) != len(raw):
        try:
            with open(out, "wb") as f:
                f.write(raw)
        except OSError:
            return ""
    return out if os.path.isfile(out) else ""


def _abspath_image(img) -> str:
    """Disk filepath for a Blender Image (Slice 2af: packed-only → temp).

    Prefers an existing on-disk filepath. If missing (packed-only or deleted
    original), materializes packed_file bytes under /tmp/quanttrace_packed/
    and returns that path for the existing image_path ABI. Empty only when
    truly missing pixels/file.
    """
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
    if raw:
        # bpy.path.abspath when available (// relative).
        try:
            import bpy  # type: ignore
            abspath = getattr(getattr(bpy, "path", None), "abspath", None)
            if callable(abspath):
                raw = abspath(raw)
        except Exception:
            pass
        disk = os.path.abspath(os.path.expanduser(raw))
        if os.path.isfile(disk):
            return disk
    # Slice 2af: packed-only (or filepath pointing at a gone file).
    packed = _materialize_packed_image(img)
    if packed:
        return packed
    return ""


def _sock_default_float3(sock) -> Tuple[float, float, float]:
    """Unlinked Vector/Location/Rotation/Scale default as float3."""
    dv = getattr(sock, "default_value", (0.0, 0.0, 0.0))
    return (float(dv[0]), float(dv[1]), float(dv[2]))


def _constant_float_from_value_sock(sock, label: str) -> float:
    """Unlinked float default, or single VALUE node with constant output (Slice 2ag)."""
    if sock is None:
        raise QuantTraceSyncError(f"{label} missing")
    if not getattr(sock, "is_linked", False):
        return float(getattr(sock, "default_value", 0.0) or 0.0)
    links = list(getattr(sock, "links", None) or [])
    if len(links) != 1:
        raise QuantTraceSyncError(
            f"{label} has multiple links (Slice 2ag: Value or unlinked only)"
        )
    from_node = getattr(links[0], "from_node", None)
    from_sock = getattr(links[0], "from_socket", None)
    ntype = getattr(from_node, "type", None) if from_node is not None else None
    if ntype != "VALUE":
        raise QuantTraceSyncError(
            f"{label} linked from {ntype!r} refused "
            "(Slice 2ag: Value node or unlinked float only)"
        )
    if from_sock is None:
        raise QuantTraceSyncError(f"{label} Value link has no from_socket")
    return float(getattr(from_sock, "default_value", 0.0) or 0.0)


def _float3_from_mapping_lrs_sock(sock, name: str) -> Tuple[float, float, float]:
    """Resolve Mapping Location/Rotation/Scale to float3 (unlinked or linked constants).

    Slice 2ag accepts:
      - unlinked socket default (Slice 2h)
      - Combine XYZ ← unlinked X/Y/Z defaults or Value→X/Y/Z
      - single Value → VECTOR (Blender/Cycles float→float3 = (v,v,v))
    Location may be is_unavailable under VECTOR (Blender 5.2); still pack for ABI.
    VECTOR SVM ignores Location; Rotation + Scale matter.
    """
    if sock is None:
        raise QuantTraceSyncError(f"Mapping missing {name}")
    if not getattr(sock, "is_linked", False):
        return _sock_default_float3(sock)
    links = list(getattr(sock, "links", None) or [])
    if len(links) != 1:
        raise QuantTraceSyncError(
            f"Mapping.{name} has multiple links (Slice 2ag)"
        )
    from_node = getattr(links[0], "from_node", None)
    from_sock = getattr(links[0], "from_socket", None)
    ntype = getattr(from_node, "type", None) if from_node is not None else None
    sname = getattr(from_sock, "name", "") if from_sock is not None else ""
    if ntype == "COMBXYZ":
        if sname not in ("Vector", "vector", ""):
            raise QuantTraceSyncError(
                f"Mapping.{name} must come from Combine XYZ Vector "
                f"(got {sname!r})"
            )
        inputs = getattr(from_node, "inputs", None)
        if inputs is None:
            raise QuantTraceSyncError(f"Mapping.{name} Combine XYZ has no inputs")
        getter = getattr(inputs, "get", None)
        x_s = getter("X") if callable(getter) else None
        y_s = getter("Y") if callable(getter) else None
        z_s = getter("Z") if callable(getter) else None
        if x_s is None or y_s is None or z_s is None:
            # Fall back to positional (X,Y,Z order).
            try:
                x_s = x_s or inputs[0]
                y_s = y_s or inputs[1]
                z_s = z_s or inputs[2]
            except (IndexError, TypeError, KeyError) as e:
                raise QuantTraceSyncError(
                    f"Mapping.{name} Combine XYZ missing X/Y/Z"
                ) from e
        return (
            _constant_float_from_value_sock(
                x_s, f"Mapping.{name}/CombineXYZ.X"
            ),
            _constant_float_from_value_sock(
                y_s, f"Mapping.{name}/CombineXYZ.Y"
            ),
            _constant_float_from_value_sock(
                z_s, f"Mapping.{name}/CombineXYZ.Z"
            ),
        )
    if ntype == "VALUE":
        # Cycles NODE_CONVERT_FV: float → float3(v,v,v).
        v = float(getattr(from_sock, "default_value", 0.0) or 0.0)
        return (v, v, v)
    raise QuantTraceSyncError(
        f"Mapping.{name} is linked from {ntype!r} "
        "(Slice 2ag needs Combine XYZ or Value constants; "
        "TEX_COORD/TEX_IMAGE/nested Mapping refused)"
    )


def _tex_coord_space_from_vector_link(vec_sock) -> str:
    """Return 'UV', 'Generated', 'Object', 'Camera', 'Window', or 'Reflection'.

    Object may have an empty reference (Slice 2l / NODE_TEXCO_OBJECT) or a
    bpy object pointer (Slice 2ab / NODE_TEXCO_OBJECT_WITH_TRANSFORM).
    The pointer itself is collected by _tex_image_from_sock / packer, not
    returned here. Camera uses scene Camera::worldtocamera (NODE_TEXCO_CAMERA);
    no extra inverse-matrix ABI. from_instancer/from_dupli unused.
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
        # Slice 2ab: pointer is collected at pack time (mesh-level).
        # Empty ref stays Slice 2l (use_transform=0).
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


def _tex_coord_object_from_vec_sock(vec_sock):
    """bpy object on TEX_COORD.object when Vector is Object; else None.

    Slice 2ab: pointer set → pack use_transform. Empty ref stays 2l.
    from_instancer / from_dupli unused.
    """
    if vec_sock is None:
        return None
    links = list(getattr(vec_sock, "links", None) or [])
    if len(links) != 1:
        return None
    from_node = getattr(links[0], "from_node", None)
    from_sock = getattr(links[0], "from_socket", None)
    if from_node is None or getattr(from_node, "type", None) != "TEX_COORD":
        return None
    key = str(getattr(from_sock, "name", "") if from_sock is not None else "").strip().lower()
    if key != "object":
        return None
    return getattr(from_node, "object", None)


def _tex_ob_key(obj):
    return getattr(obj, "name_full", None) or getattr(obj, "name", None) or id(obj)


def _resolve_tex_ob_ref(*infos):
    """One Object pointer per mesh. Same object (or pointer + empties) OK."""
    found = []
    keys = []
    for info in infos:
        if not info:
            continue
        ref = info.get("tex_ob_ref") if isinstance(info, dict) else None
        if ref is None:
            continue
        key = _tex_ob_key(ref)
        if key not in keys:
            keys.append(key)
            found.append(ref)
    if len(found) > 1:
        names = [getattr(o, "name", "?") for o in found]
        raise QuantTraceSyncError(
            "TEX_COORD Object sockets on the same mesh point at different "
            f"objects {names} (Slice 2ab: one Object reference per mesh)"
        )
    return found[0] if found else None


def _pack_tex_ob_fields(pr: dict, depsgraph=None) -> dict:
    """Mesh-level use_transform + matrix_world 3x4 (Slice 2ab)."""
    obj = pr.get("tex_ob_ref") if pr else None
    if obj is None:
        return {
            "tex_ob_use_transform": 0,
            "tex_ob_tfm": list(_identity_3x4()),
        }
    eval_obj = obj
    if depsgraph is not None:
        getter = getattr(obj, "evaluated_get", None)
        if callable(getter):
            try:
                eval_obj = getter(depsgraph)
            except Exception:
                eval_obj = obj
    mw = getattr(eval_obj, "matrix_world", None)
    if mw is None:
        mw = getattr(obj, "matrix_world", None)
    if mw is None:
        raise QuantTraceSyncError(
            "TEX_COORD Object pointer has no matrix_world (Slice 2ab)"
        )
    return {
        "tex_ob_use_transform": 1,
        "tex_ob_tfm": _matrix_3x4(mw),
    }



def _finalize_world_pack(scene, depsgraph=None) -> dict:
    """_world_info + Slice 2ae world_ob_* (drops bpy world_ob_ref)."""
    wi = dict(_world_info(scene))
    wi.update(_pack_world_ob_fields(wi, depsgraph=depsgraph))
    wi.pop("world_ob_ref", None)
    return wi


def _pack_world_ob_fields(wi: dict, depsgraph=None) -> dict:
    """World-level use_transform + matrix_world 3x4 (Slice 2ae).

    Reuses the same matrix_world 3x4 path as mesh `_pack_tex_ob_fields`.
    Empty Object ref → use_transform=0 (bit-identical Slice 2ac).
    """
    obj = wi.get("world_ob_ref") if wi else None
    if obj is None:
        return {
            "world_ob_use_transform": 0,
            "world_ob_tfm": list(_identity_3x4()),
        }
    eval_obj = obj
    if depsgraph is not None:
        getter = getattr(obj, "evaluated_get", None)
        if callable(getter):
            try:
                eval_obj = getter(depsgraph)
            except Exception:
                eval_obj = obj
    mw = getattr(eval_obj, "matrix_world", None)
    if mw is None:
        mw = getattr(obj, "matrix_world", None)
    if mw is None:
        raise QuantTraceSyncError(
            "Environment Texture Object pointer has no matrix_world (Slice 2ae)"
        )
    return {
        "world_ob_use_transform": 1,
        "world_ob_tfm": _matrix_3x4(mw),
    }

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
    """Validate MAPPING: VECTOR type, Vector←TEX_COORD, L/R/S unlinked or Slice 2ag constants."""
    vtype = str(getattr(map_node, "vector_type", "POINT") or "POINT").upper()
    if vtype != "VECTOR":
        raise QuantTraceSyncError(
            f"Mapping vector_type={vtype!r} refused (Slice 2h/2ag needs VECTOR)"
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
    # NODE_MAPPING_TYPE_VECTOR == 2 (POINT=0, TEXTURE=1, VECTOR=2, NORMAL=3)
    # VECTOR SVM ignores Location; still pack for ABI honesty (Slice 2ag).
    return (
        _float3_from_mapping_lrs_sock(loc_s, "Location"),
        _float3_from_mapping_lrs_sock(rot_s, "Rotation"),
        _float3_from_mapping_lrs_sock(scl_s, "Scale"),
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
        "tex_ob_ref": None,  # bpy object; mesh-level resolve in packer
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
    tex_ob_ref = None

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
                tex_vector_mode = 5  # QT_TEX_VECTOR_TEXCOORD_OBJECT
                tex_ob_ref = getattr(vnode, "object", None)
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
                vec_in = _mapping_input_by_name(vnode, "Vector")
                tex_ob_ref = _tex_coord_object_from_vec_sock(vec_in)
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
            "Image Texture has no disk filepath and no packed pixels (Slice 2af)"
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
        "tex_ob_ref": tex_ob_ref,
    }


def _tex_image_from_base_color(sock) -> dict:
    """Compat wrapper: Base Color TEX_IMAGE (Slice 2f/2h)."""
    return _tex_image_from_sock(sock, "Base Color")



def _prefix_tex(info: dict, prefix: str) -> dict:
    """Remap image_path/… keys to rough_/metal_/normal_/ior_/alpha_/trans_/spec_/coat_/sheen_/emit_str_/emit_color_/coat_rough_/coat_ior_/coat_tint_/sheen_rough_/sheen_tint_/coat_normal_/spec_tint_/film_thick_/film_ior_/sss_weight_/sss_radius_/sss_scale_/sss_ior_/sss_aniso_/thin_wall_/diffuse_rough_/aniso_/aniso_rot_/tangent_/bump_ (or keep for base)."""
    if not prefix:
        return dict(info)
    out = {
        f"{prefix}image_path": info.get("image_path") or "",
        f"{prefix}image_colorspace": info.get("image_colorspace") or "",
        f"{prefix}tex_vector_mode": int(info.get("tex_vector_mode", 0) or 0),
        f"{prefix}map_location": info.get("map_location") or (0.0, 0.0, 0.0),
        f"{prefix}map_rotation": info.get("map_rotation") or (0.0, 0.0, 0.0),
        f"{prefix}map_scale": info.get("map_scale") or (1.0, 1.0, 1.0),
        f"{prefix}map_type": int(info.get("map_type", 2) if info.get("map_type") is not None else 2),
    }
    # Mesh-level Object pointer (Slice 2ab) — do not prefix.
    if "tex_ob_ref" in info:
        out["tex_ob_ref"] = info.get("tex_ob_ref")
    return out



def _empty_normal_info(prefix: str = "normal_") -> dict:
    out = _prefix_tex(_empty_tex_info(), prefix)
    out[f"{prefix}strength"] = 1.0
    out[f"{prefix}space"] = 0  # QT_NORMAL_MAP_TANGENT
    return out


def _empty_bump_info(prefix: str = "bump_") -> dict:
    """Empty bump_* ABI. Distance is Blender 5.2 RNA 0.001, not Cycles 0.1."""
    out = _prefix_tex(_empty_tex_info(), prefix)
    out[f"{prefix}strength"] = 1.0
    out[f"{prefix}distance"] = 0.001
    out[f"{prefix}invert"] = 0
    return out


def _bump_from_sock(sock, *, prefix: str = "bump_", label: str = "Normal") -> dict:
    """Principled.{label} <- Bump.Normal; Height <- TEX_IMAGE Color.

    Strength and Distance must be unlinked floats (Blender 5.2 RNA 1.0 / 0.001).
    Normal input unlinked. invert RNA True is OK (packed as bump_invert 1).
    use_object_space is not a Blender 5.2 property -- native forces false.
    Packed-only images materialize via _abspath_image (Slice 2af).
    """
    empty = _empty_bump_info(prefix)
    if sock is None:
        return empty
    links = list(getattr(sock, "links", None) or [])
    if not links:
        return empty
    if len(links) != 1:
        raise QuantTraceSyncError(f"Principled.{label} has multiple links")
    src = links[0]
    from_node = getattr(src, "from_node", None)
    from_sock = getattr(src, "from_socket", None)
    ntype = getattr(from_node, "type", None) if from_node is not None else None
    if ntype != "BUMP":
        raise QuantTraceSyncError(
            f"Principled.{label} from {ntype!r} refused (Slice 2x: Bump only here)"
        )
    sock_name = getattr(from_sock, "name", "") if from_sock is not None else ""
    if sock_name not in ("Normal", "normal"):
        raise QuantTraceSyncError(
            f"Principled.{label} must come from Bump Normal (Slice 2x)"
        )
    inputs = getattr(from_node, "inputs", None)
    getter = getattr(inputs, "get", None) if inputs is not None else None

    def _in(name):
        if callable(getter):
            s = getter(name)
            if s is not None:
                return s
        if inputs is not None:
            for s in inputs:
                if getattr(s, "name", None) == name or getattr(s, "identifier", None) == name:
                    return s
        return None

    strength_sock = _in("Strength")
    distance_sock = _in("Distance")
    height_sock = _in("Height")
    normal_in = _in("Normal")
    if strength_sock is not None and getattr(strength_sock, "is_linked", False):
        raise QuantTraceSyncError(
            "Bump Strength is linked (Slice 2x: unlinked float only)"
        )
    if distance_sock is not None and getattr(distance_sock, "is_linked", False):
        raise QuantTraceSyncError(
            "Bump Distance is linked (Slice 2x: unlinked float only)"
        )
    if normal_in is not None and getattr(normal_in, "is_linked", False):
        raise QuantTraceSyncError(
            "Bump Normal input is linked (Slice 2x: unlinked only)"
        )
    if height_sock is None or not getattr(height_sock, "is_linked", False):
        raise QuantTraceSyncError(
            "Bump Height must be TEX_IMAGE Color (Slice 2x)"
        )
    tex = _tex_image_from_sock(height_sock, f"{label} Bump Height")
    out = _prefix_tex(tex, prefix)
    strength = 1.0
    if strength_sock is not None:
        strength = float(getattr(strength_sock, "default_value", 1.0))
    distance = 0.001
    if distance_sock is not None:
        distance = float(getattr(distance_sock, "default_value", 0.001))
    invert = bool(getattr(from_node, "invert", False))
    out[f"{prefix}strength"] = strength
    out[f"{prefix}distance"] = distance
    out[f"{prefix}invert"] = 1 if invert else 0
    return out


def _principled_normal_dispatch(sock) -> dict:
    """Principled.Normal <- Normal Map (2j) or Bump (2x). Packer fills one."""
    empty = {**_empty_normal_info(), **_empty_bump_info()}
    if sock is None:
        return empty
    links = list(getattr(sock, "links", None) or [])
    if not links:
        return empty
    if len(links) != 1:
        raise QuantTraceSyncError("Principled.Normal has multiple links")
    src = links[0]
    from_node = getattr(src, "from_node", None)
    ntype = getattr(from_node, "type", None) if from_node is not None else None
    if ntype == "NORMAL_MAP":
        return {**_normal_map_from_sock(sock), **_empty_bump_info()}
    if ntype == "BUMP":
        return {**_empty_normal_info(), **_bump_from_sock(sock)}
    raise QuantTraceSyncError(
        f"Principled.Normal from {ntype!r} refused "
        "(Slice 2x: Normal Map or Bump only)"
    )


def _normal_map_from_sock(sock, *, prefix: str = "normal_", label: str = "Normal") -> dict:
    """Principled.{label} ← Normal Map.Normal; Color ← TEX_IMAGE; Strength unlinked.

    Space TANGENT/OBJECT/WORLD (Slice 2z) + BLENDER_OBJECT/BLENDER_WORLD
    (Slice 2ad). Bump-on-this-helper, linked Strength, packed-only,
    custom uv_map refuse.
    """
    empty = _empty_normal_info(prefix)
    if sock is None:
        return empty
    links = list(getattr(sock, "links", None) or [])
    if not links:
        return empty
    if len(links) != 1:
        raise QuantTraceSyncError(f"Principled.{label} has multiple links")
    src = links[0]
    from_node = getattr(src, "from_node", None)
    from_sock = getattr(src, "from_socket", None)
    ntype = getattr(from_node, "type", None) if from_node is not None else None
    if ntype != "NORMAL_MAP":
        raise QuantTraceSyncError(
            f"Principled.{label} from {ntype!r} refused "
            "(Slice 2t: Normal Map only; Bump/etc refuse)"
        )
    sock_name = getattr(from_sock, "name", "") if from_sock is not None else ""
    if sock_name not in ("Normal", "normal"):
        raise QuantTraceSyncError(
            f"Principled.{label} must come from Normal Map Normal (Slice 2t)"
        )
    space = str(getattr(from_node, "space", "TANGENT") or "TANGENT").upper()
    # Blender 5.2 RNA + Cycles NodeNormalMapSpace (kernel/svm/types.h):
    # TANGENT=0 OBJECT=1 WORLD=2 BLENDER_OBJECT=3 BLENDER_WORLD=4.
    # BLENDER_* flips color.y/z in svm (tex_coord.h "strange blender convention").
    _SPACE = {
        "TANGENT": 0,
        "OBJECT": 1,
        "WORLD": 2,
        "BLENDER_OBJECT": 3,
        "BLENDER_WORLD": 4,
    }
    if space not in _SPACE:
        raise QuantTraceSyncError(
            f"Normal Map space={space!r} refused "
            "(Slice 2ad: TANGENT/OBJECT/WORLD/BLENDER_OBJECT/BLENDER_WORLD only)"
        )
    space_i = _SPACE[space]
    uv_map = str(getattr(from_node, "uv_map", "") or "").strip()
    if uv_map:
        raise QuantTraceSyncError(
            f"Normal Map uv_map={uv_map!r} refused (Slice 2t: default UV only)"
        )
    inputs = getattr(from_node, "inputs", None)
    getter = getattr(inputs, "get", None) if inputs is not None else None
    strength_sock = getter("Strength") if callable(getter) else None
    color_sock = getter("Color") if callable(getter) else None
    if strength_sock is not None and getattr(strength_sock, "is_linked", False):
        raise QuantTraceSyncError(
            "Normal Map Strength is linked (Slice 2t: unlinked float only)"
        )
    strength = 1.0
    if strength_sock is not None:
        strength = float(getattr(strength_sock, "default_value", 1.0))
    if color_sock is None or not getattr(color_sock, "is_linked", False):
        raise QuantTraceSyncError(
            "Normal Map Color must be TEX_IMAGE (Slice 2t)"
        )
    tex = _tex_image_from_sock(color_sock, f"{label} Map Color")
    out = _prefix_tex(tex, prefix)
    out[f"{prefix}strength"] = strength
    out[f"{prefix}space"] = space_i
    return out


def _input_by_names(bsdf, *names):
    """First matching Principled input (Blender 5.x name, then legacy).

    Keyed get can miss panel-unavailable sockets (e.g. Subsurface IOR when
    subsurface_method != RANDOM_WALK_SKIN); fall back to iterating inputs.
    """
    inputs = getattr(bsdf, "inputs", None)
    if inputs is None:
        return None, None
    getter = getattr(inputs, "get", None)
    for name in names:
        sock = getter(name) if callable(getter) else None
        if sock is not None:
            return name, sock
        for s in inputs:
            if getattr(s, "name", None) == name or getattr(s, "identifier", None) == name:
                return name, s
    return None, None


def _principled_from_material(mat) -> dict:
    """Return principled dict (constants + optional TEX_IMAGE on Base/Rough/Metal/IOR/Alpha/Trans/Spec/Coat/Sheen/EmitStr/EmitColor)."""
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
        **_prefix_tex(_empty_tex_info(), "emit_color_"),
        **_prefix_tex(_empty_tex_info(), "coat_rough_"),
        **_prefix_tex(_empty_tex_info(), "coat_ior_"),
        **_prefix_tex(_empty_tex_info(), "coat_tint_"),
        **_prefix_tex(_empty_tex_info(), "sheen_rough_"),
        **_prefix_tex(_empty_tex_info(), "sheen_tint_"),
        **_empty_normal_info("coat_normal_"),
        **_prefix_tex(_empty_tex_info(), "spec_tint_"),
        **_prefix_tex(_empty_tex_info(), "film_thick_"),
        **_prefix_tex(_empty_tex_info(), "film_ior_"),
        **_prefix_tex(_empty_tex_info(), "sss_weight_"),
        **_prefix_tex(_empty_tex_info(), "sss_radius_"),
        **_prefix_tex(_empty_tex_info(), "sss_scale_"),
        **_prefix_tex(_empty_tex_info(), "sss_ior_"),
        **_prefix_tex(_empty_tex_info(), "sss_aniso_"),
        **_prefix_tex(_empty_tex_info(), "thin_wall_"),
        **_prefix_tex(_empty_tex_info(), "diffuse_rough_"),
        **_prefix_tex(_empty_tex_info(), "aniso_"),
        **_prefix_tex(_empty_tex_info(), "aniso_rot_"),
        **_prefix_tex(_empty_tex_info(), "tangent_"),
        **_empty_bump_info(),
        "thin_wall": 0,
        "transmission_weight": 0.0,
        "tex_ob_ref": None,
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
    emit_color_tex = _empty_tex_info()
    coat_rough_tex = _empty_tex_info()
    coat_ior_tex = _empty_tex_info()
    coat_tint_tex = _empty_tex_info()
    sheen_rough_tex = _empty_tex_info()
    sheen_tint_tex = _empty_tex_info()
    spec_tint_tex = _empty_tex_info()
    film_thick_tex = _empty_tex_info()
    film_ior_tex = _empty_tex_info()
    sss_weight_tex = _empty_tex_info()
    sss_radius_tex = _empty_tex_info()
    sss_scale_tex = _empty_tex_info()
    sss_ior_tex = _empty_tex_info()
    sss_aniso_tex = _empty_tex_info()
    diffuse_rough_tex = _empty_tex_info()
    aniso_tex = _empty_tex_info()
    aniso_rot_tex = _empty_tex_info()
    tangent_tex = _empty_tex_info()
    # 5.x names first; legacy Transmission / Specular / Coat / Sheen / Emission accepted.
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
        ("Emission Color", ("Emission Color", "Emission"), "emit_color"),
        ("Coat Roughness", ("Coat Roughness",), "coat_rough"),
        ("Coat IOR", ("Coat IOR",), "coat_ior"),
        ("Coat Tint", ("Coat Tint",), "coat_tint"),
        ("Sheen Roughness", ("Sheen Roughness",), "sheen_rough"),
        ("Sheen Tint", ("Sheen Tint",), "sheen_tint"),
        ("Specular Tint", ("Specular Tint",), "spec_tint"),
        ("Thin Film Thickness", ("Thin Film Thickness",), "film_thick"),
        ("Thin Film IOR", ("Thin Film IOR",), "film_ior"),
        ("Subsurface Weight", ("Subsurface Weight", "Subsurface"), "sss_weight"),
        ("Subsurface Radius", ("Subsurface Radius",), "sss_radius"),
        ("Subsurface Scale", ("Subsurface Scale",), "sss_scale"),
        ("Subsurface IOR", ("Subsurface IOR",), "sss_ior"),
        ("Subsurface Anisotropy", ("Subsurface Anisotropy",), "sss_aniso"),
        ("Diffuse Roughness", ("Diffuse Roughness",), "diffuse_rough"),
        ("Anisotropic", ("Anisotropic",), "aniso"),
        ("Anisotropic Rotation", ("Anisotropic Rotation",), "aniso_rot"),
        ("Tangent", ("Tangent",), "tangent"),
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
        elif kind == "emit_color":
            emit_color_tex = tex
        elif kind == "coat_rough":
            coat_rough_tex = tex
        elif kind == "coat_ior":
            coat_ior_tex = tex
        elif kind == "coat_tint":
            coat_tint_tex = tex
        elif kind == "sheen_rough":
            sheen_rough_tex = tex
        elif kind == "sheen_tint":
            sheen_tint_tex = tex
        elif kind == "spec_tint":
            spec_tint_tex = tex
        elif kind == "film_thick":
            film_thick_tex = tex
        elif kind == "film_ior":
            film_ior_tex = tex
        elif kind == "sss_weight":
            sss_weight_tex = tex
        elif kind == "sss_radius":
            sss_radius_tex = tex
        elif kind == "sss_scale":
            sss_scale_tex = tex
        elif kind == "sss_ior":
            sss_ior_tex = tex
        elif kind == "sss_aniso":
            sss_aniso_tex = tex
        elif kind == "diffuse_rough":
            diffuse_rough_tex = tex
        elif kind == "aniso":
            aniso_tex = tex
        elif kind == "aniso_rot":
            aniso_rot_tex = tex
        elif kind == "tangent":
            tangent_tex = tex
    # Thin Wall is BOOLEAN in Blender 5.2 — not a TEX_IMAGE-mappable float.
    # Linked still refuses. Unlinked packs 0/1 from RNA default_value.
    thin_wall = 0
    _tw_name, thin_wall_sock = _input_by_names(bsdf, "Thin Wall")
    if thin_wall_sock is not None and getattr(thin_wall_sock, "is_linked", False):
        raise QuantTraceSyncError(
            "Principled.Thin Wall is BOOLEAN, not TEX_IMAGE (linked Thin Wall still refuses)"
        )
    if thin_wall_sock is not None:
        thin_wall = 1 if bool(thin_wall_sock.default_value) else 0
    # Unlinked Transmission Weight RNA default (0.0 if missing / linked).
    # Linked TEX_IMAGE still wins via trans_ (Slice 2p); native skips the constant.
    transmission_weight = 0.0
    _tr_name, trans_w_sock = _input_by_names(bsdf, "Transmission Weight", "Transmission")
    if trans_w_sock is not None and not getattr(trans_w_sock, "is_linked", False):
        try:
            transmission_weight = float(trans_w_sock.default_value)
        except (TypeError, ValueError):
            transmission_weight = 0.0
    _cn_name, coat_n_sock = _input_by_names(bsdf, "Coat Normal")
    coat_normal_info = _normal_map_from_sock(
        coat_n_sock, prefix="coat_normal_", label="Coat Normal"
    )
    # Coat Normal stays Normal-Map-only (2t). Bump on Coat Normal still refuses.
    normal_info = _principled_normal_dispatch(bsdf.inputs.get("Normal"))
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
        **_prefix_tex(emit_color_tex, "emit_color_"),
        **_prefix_tex(coat_rough_tex, "coat_rough_"),
        **_prefix_tex(coat_ior_tex, "coat_ior_"),
        **_prefix_tex(coat_tint_tex, "coat_tint_"),
        **_prefix_tex(sheen_rough_tex, "sheen_rough_"),
        **_prefix_tex(sheen_tint_tex, "sheen_tint_"),
        **coat_normal_info,
        **_prefix_tex(spec_tint_tex, "spec_tint_"),
        **_prefix_tex(film_thick_tex, "film_thick_"),
        **_prefix_tex(film_ior_tex, "film_ior_"),
        **_prefix_tex(sss_weight_tex, "sss_weight_"),
        **_prefix_tex(sss_radius_tex, "sss_radius_"),
        **_prefix_tex(sss_scale_tex, "sss_scale_"),
        **_prefix_tex(sss_ior_tex, "sss_ior_"),
        **_prefix_tex(sss_aniso_tex, "sss_aniso_"),
        **_prefix_tex(_empty_tex_info(), "thin_wall_"),
        **_prefix_tex(diffuse_rough_tex, "diffuse_rough_"),
        **_prefix_tex(aniso_tex, "aniso_"),
        **_prefix_tex(aniso_rot_tex, "aniso_rot_"),
        **_prefix_tex(tangent_tex, "tangent_"),
        **{k: v for k, v in normal_info.items() if str(k).startswith("bump_")},
        "thin_wall": int(thin_wall),
        "transmission_weight": float(transmission_weight),
        "tex_ob_ref": _resolve_tex_ob_ref(
            base_tex, rough_tex, metal_tex, ior_tex, alpha_tex, trans_tex,
            spec_tex, coat_tex, sheen_tex, emit_str_tex, emit_color_tex,
            coat_rough_tex, coat_ior_tex, coat_tint_tex, sheen_rough_tex,
            sheen_tint_tex, spec_tint_tex, film_thick_tex, film_ior_tex,
            sss_weight_tex, sss_radius_tex, sss_scale_tex, sss_ior_tex,
            sss_aniso_tex, diffuse_rough_tex, aniso_tex, aniso_rot_tex,
            tangent_tex, normal_info, coat_normal_info,
        ),
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



_WORLD_STRENGTH_MATH_OPS = frozenset(
    {"ADD", "SUBTRACT", "MULTIPLY", "DIVIDE", "POWER"}
)
_WORLD_STRENGTH_MATH_MAX_DEPTH = 2  # Math → (Value|unlinked|Math…) one nest OK


def _world_strength_math_input(sock, label: str, *, depth: int) -> float:
    """Resolve a Math Value input: unlinked float, Value, or shallow Math (2ai)."""
    if sock is None:
        raise QuantTraceSyncError(f"{label} missing (Slice 2ai)")
    if not getattr(sock, "is_linked", False):
        return float(getattr(sock, "default_value", 0.0) or 0.0)
    links = list(getattr(sock, "links", None) or [])
    if len(links) != 1:
        raise QuantTraceSyncError(
            f"{label} multi-link refused (Slice 2ai)"
        )
    from_node = getattr(links[0], "from_node", None)
    from_sock = getattr(links[0], "from_socket", None)
    ntype = getattr(from_node, "type", None) if from_node is not None else None
    if ntype == "VALUE":
        if from_sock is None:
            raise QuantTraceSyncError(
                f"{label} Value link has no from_socket (Slice 2ai)"
            )
        return float(getattr(from_sock, "default_value", 0.0) or 0.0)
    if ntype == "MATH":
        if depth >= _WORLD_STRENGTH_MATH_MAX_DEPTH:
            raise QuantTraceSyncError(
                f"{label} Math nest too deep (Slice 2ai max "
                f"{_WORLD_STRENGTH_MATH_MAX_DEPTH})"
            )
        return _fold_world_strength_math(from_node, depth=depth)
    raise QuantTraceSyncError(
        f"{label} linked from {ntype!r} refused "
        "(Slice 2ai: Value/Math/unlinked float only; "
        "TEX_IMAGE/Mix/RGB Curves/Noise still refuse)"
    )


def _fold_world_strength_math(node, *, depth: int = 0) -> float:
    """Fold ShaderNodeMath ADD/SUB/MUL/DIV/POWER with constant inputs (2ai)."""
    op = str(getattr(node, "operation", "") or "")
    if op not in _WORLD_STRENGTH_MATH_OPS:
        raise QuantTraceSyncError(
            f"world Background Strength Math operation {op!r} refused "
            "(Slice 2ai: ADD/SUBTRACT/MULTIPLY/DIVIDE/POWER only)"
        )
    inputs = getattr(node, "inputs", None)
    if inputs is None:
        raise QuantTraceSyncError(
            "world Background Strength Math has no inputs (Slice 2ai)"
        )
    getter = getattr(inputs, "get", None)
    a_sock = getter("Value") if callable(getter) else None
    b_sock = getter("Value_001") if callable(getter) else None
    if a_sock is None or b_sock is None:
        try:
            a_sock = a_sock or inputs[0]
            b_sock = b_sock or inputs[1]
        except (IndexError, TypeError, KeyError) as e:
            raise QuantTraceSyncError(
                "world Background Strength Math missing Value/Value_001 "
                "(Slice 2ai)"
            ) from e
    a = _world_strength_math_input(
        a_sock, "world Background Strength Math.Value", depth=depth + 1
    )
    b = _world_strength_math_input(
        b_sock, "world Background Strength Math.Value_001", depth=depth + 1
    )
    if op == "ADD":
        return float(a + b)
    if op == "SUBTRACT":
        return float(a - b)
    if op == "MULTIPLY":
        return float(a * b)
    if op == "DIVIDE":
        if abs(b) < 1e-12:
            raise QuantTraceSyncError(
                "world Background Strength Math DIVIDE by zero refused "
                "(Slice 2ai)"
            )
        return float(a / b)
    # POWER
    try:
        return float(a ** b)
    except (OverflowError, ValueError) as e:
        raise QuantTraceSyncError(
            f"world Background Strength Math POWER failed ({e}) (Slice 2ai)"
        ) from e


def _world_strength_from_sock(sock) -> float:
    """Resolve Background.Strength to a constant float (Slice 2ah/2ai).

    Accepts unlinked default_value, ShaderNodeValue, or ShaderNodeMath whose
    Value inputs are unlinked floats / Value / shallow Math
    (ADD/SUBTRACT/MULTIPLY/DIVIDE/POWER). Multi-link, TEX_IMAGE / Mix /
    RGB Curves / Noise / texture-driven Math / kitchens refuse.
    """
    if sock is None:
        return 0.0
    if not getattr(sock, "is_linked", False):
        return float(getattr(sock, "default_value", 0.0) or 0.0)
    links = list(getattr(sock, "links", None) or [])
    if len(links) != 1:
        raise QuantTraceSyncError(
            "world Background Strength multi-link refused (Slice 2ai)"
        )
    from_node = getattr(links[0], "from_node", None)
    from_sock = getattr(links[0], "from_socket", None)
    ntype = getattr(from_node, "type", None) if from_node is not None else None
    if ntype == "VALUE":
        if from_sock is None:
            raise QuantTraceSyncError(
                "world Background Strength Value link has no from_socket "
                "(Slice 2ah)"
            )
        return float(getattr(from_sock, "default_value", 0.0) or 0.0)
    if ntype == "MATH":
        return _fold_world_strength_math(from_node, depth=0)
    raise QuantTraceSyncError(
        f"world Background Strength linked from {ntype!r} refused "
        "(Slice 2ai: ShaderNodeValue / ShaderNodeMath / unlinked float only; "
        "TEX_IMAGE/Mix/RGB Curves/Noise still refuse)"
    )


def _world_info(scene) -> dict:
    """Pack world Background + optional Environment Texture (Slice 2aa/2ac/2ah/2ai).

    Returns dict:
      world_strength: float
      world_image_path: str (empty = black Background Color, Slice 2b)
      world_image_colorspace: str
      world_projection: int (0=EQUIRECTANGULAR, 1=MIRROR_BALL)
      world_tex_vector_mode: int (QT_TEX_VECTOR_*; 0 = unlinked LINK_POSITION)
      world_map_location / rotation / scale / type: Mapping constants (Slice 2ac)

    Empty path keeps locked-cube black worlds bit-identical.
    Slice 2ac: Vector may be TEX_COORD Generated/Object/Camera/Window/Reflection
    or Mapping(VECTOR, unlinked L/R/S) ← TEX_COORD (same graph shapes as mesh
    TEX_IMAGE). UV accepted for ABI parity but uncommon on env. Other shapes
    refuse with Slice 2ac in the error.
    Slice 2ah/2ai: Strength may be unlinked default_value, ShaderNodeValue,
    or ShaderNodeMath (ADD/SUB/MUL/DIV/POWER) ← Value/unlinked/shallow Math.
    TEX_IMAGE/Mix/RGB/Noise/texture-driven Math → Strength still refuse.
    """
    empty = {
        "world_strength": 0.0,
        "world_image_path": "",
        "world_image_colorspace": "",
        "world_projection": 0,
        "world_tex_vector_mode": 0,
        "world_map_location": (0.0, 0.0, 0.0),
        "world_map_rotation": (0.0, 0.0, 0.0),
        "world_map_scale": (1.0, 1.0, 1.0),
        "world_map_type": 2,
    }
    world = getattr(scene, "world", None)
    if world is None:
        return empty
    if not getattr(world, "use_nodes", False) or world.node_tree is None:
        # Nodeless world color — Slice 2b only supports black+strength.
        col = getattr(world, "color", (0.0, 0.0, 0.0))
        if abs(float(col[0])) + abs(float(col[1])) + abs(float(col[2])) > 1e-6:
            raise QuantTraceSyncError("nodeless world color not black (Slice 2b)")
        return empty
    bg = None
    for node in world.node_tree.nodes:
        if getattr(node, "type", None) == "BACKGROUND":
            bg = node
            break
    if bg is None:
        return empty
    strength_sock = bg.inputs.get("Strength")
    strength = _world_strength_from_sock(strength_sock)
    color_sock = bg.inputs.get("Color")
    if color_sock is None or not getattr(color_sock, "is_linked", False):
        if color_sock is not None:
            col = color_sock.default_value
            if abs(float(col[0])) + abs(float(col[1])) + abs(float(col[2])) > 1e-6:
                raise QuantTraceSyncError(
                    "world Background Color not black (Slice 2b/2aa)"
                )
        return {
            **empty,
            "world_strength": strength,
        }
    # Color linked — only TEX_ENVIRONMENT with disk filepath.
    links = list(getattr(color_sock, "links", None) or [])
    if len(links) != 1:
        raise QuantTraceSyncError(
            "world Background Color multi-link refused (Slice 2aa)"
        )
    from_node = getattr(links[0], "from_node", None)
    ntype = getattr(from_node, "type", None) if from_node is not None else None
    if ntype != "TEX_ENVIRONMENT":
        raise QuantTraceSyncError(
            f"world Background Color linked from {ntype!r} "
            "(Slice 2aa: TEX_ENVIRONMENT only; Slice 2ac refuses "
            "Sky/Nishita/TEX_IMAGE/RGB/Mix)"
        )
    img = getattr(from_node, "image", None)
    path = _abspath_image(img)
    if not path:
        raise QuantTraceSyncError(
            "Environment Texture has no disk filepath and no packed pixels "
            "(Slice 2af)"
        )
    proj_rna = str(getattr(from_node, "projection", "EQUIRECTANGULAR") or "").upper()
    if proj_rna == "EQUIRECTANGULAR":
        proj = 0
    elif proj_rna == "MIRROR_BALL":
        proj = 1
    else:
        raise QuantTraceSyncError(
            f"Environment Texture projection {proj_rna!r} refused (Slice 2aa)"
        )
    cs = ""
    if img is not None:
        cs_settings = getattr(img, "colorspace_settings", None)
        if cs_settings is not None:
            cs = str(getattr(cs_settings, "name", "") or "")

    # Slice 2ac/2ae: parse Vector like mesh TEX_IMAGE (2h/2k/2l/2m/2n/2ab).
    tex_vector_mode = 0  # QT_TEX_VECTOR_UNLINKED → LINK_POSITION
    map_location = (0.0, 0.0, 0.0)
    map_rotation = (0.0, 0.0, 0.0)
    map_scale = (1.0, 1.0, 1.0)
    map_type = 2
    world_ob_ref = None  # Slice 2ae: Object pointer (empty-ref stays None)
    vec_sock = from_node.inputs.get("Vector") if from_node is not None else None
    if vec_sock is not None and getattr(vec_sock, "is_linked", False):
        vlinks = list(getattr(vec_sock, "links", None) or [])
        if len(vlinks) != 1:
            raise QuantTraceSyncError(
                "Environment Texture Vector has multiple links (Slice 2ae)"
            )
        vsrc = vlinks[0]
        vnode = getattr(vsrc, "from_node", None)
        vsock = getattr(vsrc, "from_socket", None)
        vtype = getattr(vnode, "type", None) if vnode is not None else None
        vname = getattr(vsock, "name", "") if vsock is not None else ""
        if vtype == "TEX_COORD":
            key = str(vname).strip().lower()
            if key == "uv":
                tex_vector_mode = 1
            elif key == "generated":
                tex_vector_mode = 3  # QT_TEX_VECTOR_TEXCOORD_GENERATED
            elif key == "object":
                # Slice 2ae: pointer → pack world_ob_*; empty-ref stays 2ac.
                world_ob_ref = getattr(vnode, "object", None)
                tex_vector_mode = 5
            elif key == "camera":
                tex_vector_mode = 7
            elif key == "window":
                tex_vector_mode = 9
            elif key == "reflection":
                tex_vector_mode = 11
            else:
                raise QuantTraceSyncError(
                    f"Environment Texture Vector TEX_COORD output {vname!r} "
                    "refused (Slice 2ae)"
                )
        elif vtype == "MAPPING":
            if vname not in ("Vector", "vector"):
                raise QuantTraceSyncError(
                    "Environment Texture Vector must come from Mapping Vector "
                    "(Slice 2ae)"
                )
            # Re-wrap Mapping L/R/S linked errors with Slice 2ae name.
            try:
                map_location, map_rotation, map_scale, map_type, space = (
                    _mapping_constants(vnode)
                )
            except QuantTraceSyncError as e:
                msg = str(e)
                if "Slice 2h" in msg or "Slice 2" in msg:
                    raise QuantTraceSyncError(
                        msg.replace("Slice 2ag", "Slice 2ae")
                        .replace("Slice 2h", "Slice 2ae")
                        .replace("Slice 2k", "Slice 2ae")
                        .replace("Slice 2l", "Slice 2ae")
                        .replace("Slice 2m", "Slice 2ae")
                        .replace("Slice 2n", "Slice 2ae")
                        .replace("Slice 2ac", "Slice 2ae")
                        .replace("Slice 2ab", "Slice 2ae")
                    ) from e
                raise QuantTraceSyncError(f"{msg} (Slice 2ae)") from e
            if space == "Generated":
                tex_vector_mode = 4
            elif space == "Object":
                vec_in = _mapping_input_by_name(vnode, "Vector")
                world_ob_ref = _tex_coord_object_from_vec_sock(vec_in)
                tex_vector_mode = 6
            elif space == "Camera":
                tex_vector_mode = 8
            elif space == "Window":
                tex_vector_mode = 10
            elif space == "Reflection":
                tex_vector_mode = 12
            else:
                tex_vector_mode = 2  # UV Mapping
        else:
            raise QuantTraceSyncError(
                f"Environment Texture Vector from {vtype!r} refused "
                "(Slice 2ae: TEX_COORD or Mapping←TEX_COORD only)"
            )

    return {
        "world_strength": strength,
        "world_image_path": path,
        "world_image_colorspace": cs,
        "world_projection": proj,
        "world_tex_vector_mode": tex_vector_mode,
        "world_map_location": map_location,
        "world_map_rotation": map_rotation,
        "world_map_scale": map_scale,
        "world_map_type": map_type,
        "world_ob_ref": world_ob_ref,
    }



def _world_strength(scene) -> float:
    """Back-compat: strength only (calls _world_info)."""
    return float(_world_info(scene)["world_strength"])


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
    _world_info(scene)
    return {
        "mesh": mesh_obj,
        "light": lamp,
        "camera": cams[0],
        "material": mat,
    }



def _pack_tex_fields(pr: dict, depsgraph=None) -> dict:
    """Flatten base/rough/metal/normal/ior/alpha/trans/spec/coat/sheen/emit_str/emit_color/coat_rough/coat_ior/coat_tint/sheen_rough/sheen_tint/coat_normal/spec_tint/film_thick/film_ior/sss_weight/sss_radius/sss_scale/sss_ior/sss_aniso/thin_wall/diffuse_rough/aniso/aniso_rot/tangent/bump TEX_IMAGE fields."""
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
        "normal_space": int(pr.get("normal_space", 0) or 0),
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
        "emit_color_image_path": pr.get("emit_color_image_path") or "",
        "emit_color_image_colorspace": pr.get("emit_color_image_colorspace") or "",
        "emit_color_tex_vector_mode": int(pr.get("emit_color_tex_vector_mode", 0) or 0),
        "emit_color_map_location": loc("emit_color_map_location", (0.0, 0.0, 0.0)),
        "emit_color_map_rotation": loc("emit_color_map_rotation", (0.0, 0.0, 0.0)),
        "emit_color_map_scale": loc("emit_color_map_scale", (1.0, 1.0, 1.0)),
        "emit_color_map_type": int(pr.get("emit_color_map_type", 2) if pr.get("emit_color_map_type") is not None else 2),
        "coat_rough_image_path": pr.get("coat_rough_image_path") or "",
        "coat_rough_image_colorspace": pr.get("coat_rough_image_colorspace") or "",
        "coat_rough_tex_vector_mode": int(pr.get("coat_rough_tex_vector_mode", 0) or 0),
        "coat_rough_map_location": loc("coat_rough_map_location", (0.0, 0.0, 0.0)),
        "coat_rough_map_rotation": loc("coat_rough_map_rotation", (0.0, 0.0, 0.0)),
        "coat_rough_map_scale": loc("coat_rough_map_scale", (1.0, 1.0, 1.0)),
        "coat_rough_map_type": int(pr.get("coat_rough_map_type", 2) if pr.get("coat_rough_map_type") is not None else 2),
        "coat_ior_image_path": pr.get("coat_ior_image_path") or "",
        "coat_ior_image_colorspace": pr.get("coat_ior_image_colorspace") or "",
        "coat_ior_tex_vector_mode": int(pr.get("coat_ior_tex_vector_mode", 0) or 0),
        "coat_ior_map_location": loc("coat_ior_map_location", (0.0, 0.0, 0.0)),
        "coat_ior_map_rotation": loc("coat_ior_map_rotation", (0.0, 0.0, 0.0)),
        "coat_ior_map_scale": loc("coat_ior_map_scale", (1.0, 1.0, 1.0)),
        "coat_ior_map_type": int(pr.get("coat_ior_map_type", 2) if pr.get("coat_ior_map_type") is not None else 2),
        "coat_tint_image_path": pr.get("coat_tint_image_path") or "",
        "coat_tint_image_colorspace": pr.get("coat_tint_image_colorspace") or "",
        "coat_tint_tex_vector_mode": int(pr.get("coat_tint_tex_vector_mode", 0) or 0),
        "coat_tint_map_location": loc("coat_tint_map_location", (0.0, 0.0, 0.0)),
        "coat_tint_map_rotation": loc("coat_tint_map_rotation", (0.0, 0.0, 0.0)),
        "coat_tint_map_scale": loc("coat_tint_map_scale", (1.0, 1.0, 1.0)),
        "coat_tint_map_type": int(pr.get("coat_tint_map_type", 2) if pr.get("coat_tint_map_type") is not None else 2),
        "sheen_rough_image_path": pr.get("sheen_rough_image_path") or "",
        "sheen_rough_image_colorspace": pr.get("sheen_rough_image_colorspace") or "",
        "sheen_rough_tex_vector_mode": int(pr.get("sheen_rough_tex_vector_mode", 0) or 0),
        "sheen_rough_map_location": loc("sheen_rough_map_location", (0.0, 0.0, 0.0)),
        "sheen_rough_map_rotation": loc("sheen_rough_map_rotation", (0.0, 0.0, 0.0)),
        "sheen_rough_map_scale": loc("sheen_rough_map_scale", (1.0, 1.0, 1.0)),
        "sheen_rough_map_type": int(pr.get("sheen_rough_map_type", 2) if pr.get("sheen_rough_map_type") is not None else 2),
        "sheen_tint_image_path": pr.get("sheen_tint_image_path") or "",
        "sheen_tint_image_colorspace": pr.get("sheen_tint_image_colorspace") or "",
        "sheen_tint_tex_vector_mode": int(pr.get("sheen_tint_tex_vector_mode", 0) or 0),
        "sheen_tint_map_location": loc("sheen_tint_map_location", (0.0, 0.0, 0.0)),
        "sheen_tint_map_rotation": loc("sheen_tint_map_rotation", (0.0, 0.0, 0.0)),
        "sheen_tint_map_scale": loc("sheen_tint_map_scale", (1.0, 1.0, 1.0)),
        "sheen_tint_map_type": int(pr.get("sheen_tint_map_type", 2) if pr.get("sheen_tint_map_type") is not None else 2),
        "coat_normal_image_path": pr.get("coat_normal_image_path") or "",
        "coat_normal_image_colorspace": pr.get("coat_normal_image_colorspace") or "",
        "coat_normal_tex_vector_mode": int(pr.get("coat_normal_tex_vector_mode", 0) or 0),
        "coat_normal_map_location": loc("coat_normal_map_location", (0.0, 0.0, 0.0)),
        "coat_normal_map_rotation": loc("coat_normal_map_rotation", (0.0, 0.0, 0.0)),
        "coat_normal_map_scale": loc("coat_normal_map_scale", (1.0, 1.0, 1.0)),
        "coat_normal_map_type": int(pr.get("coat_normal_map_type", 2) if pr.get("coat_normal_map_type") is not None else 2),
        "coat_normal_strength": float(pr.get("coat_normal_strength", 1.0) if pr.get("coat_normal_strength") is not None else 1.0),
        "coat_normal_space": int(pr.get("coat_normal_space", 0) or 0),
        "spec_tint_image_path": pr.get("spec_tint_image_path") or "",
        "spec_tint_image_colorspace": pr.get("spec_tint_image_colorspace") or "",
        "spec_tint_tex_vector_mode": int(pr.get("spec_tint_tex_vector_mode", 0) or 0),
        "spec_tint_map_location": loc("spec_tint_map_location", (0.0, 0.0, 0.0)),
        "spec_tint_map_rotation": loc("spec_tint_map_rotation", (0.0, 0.0, 0.0)),
        "spec_tint_map_scale": loc("spec_tint_map_scale", (1.0, 1.0, 1.0)),
        "spec_tint_map_type": int(pr.get("spec_tint_map_type", 2) if pr.get("spec_tint_map_type") is not None else 2),
        "film_thick_image_path": pr.get("film_thick_image_path") or "",
        "film_thick_image_colorspace": pr.get("film_thick_image_colorspace") or "",
        "film_thick_tex_vector_mode": int(pr.get("film_thick_tex_vector_mode", 0) or 0),
        "film_thick_map_location": loc("film_thick_map_location", (0.0, 0.0, 0.0)),
        "film_thick_map_rotation": loc("film_thick_map_rotation", (0.0, 0.0, 0.0)),
        "film_thick_map_scale": loc("film_thick_map_scale", (1.0, 1.0, 1.0)),
        "film_thick_map_type": int(pr.get("film_thick_map_type", 2) if pr.get("film_thick_map_type") is not None else 2),
        "film_ior_image_path": pr.get("film_ior_image_path") or "",
        "film_ior_image_colorspace": pr.get("film_ior_image_colorspace") or "",
        "film_ior_tex_vector_mode": int(pr.get("film_ior_tex_vector_mode", 0) or 0),
        "film_ior_map_location": loc("film_ior_map_location", (0.0, 0.0, 0.0)),
        "film_ior_map_rotation": loc("film_ior_map_rotation", (0.0, 0.0, 0.0)),
        "film_ior_map_scale": loc("film_ior_map_scale", (1.0, 1.0, 1.0)),
        "film_ior_map_type": int(pr.get("film_ior_map_type", 2) if pr.get("film_ior_map_type") is not None else 2),
        "sss_weight_image_path": pr.get("sss_weight_image_path") or "",
        "sss_weight_image_colorspace": pr.get("sss_weight_image_colorspace") or "",
        "sss_weight_tex_vector_mode": int(pr.get("sss_weight_tex_vector_mode", 0) or 0),
        "sss_weight_map_location": loc("sss_weight_map_location", (0.0, 0.0, 0.0)),
        "sss_weight_map_rotation": loc("sss_weight_map_rotation", (0.0, 0.0, 0.0)),
        "sss_weight_map_scale": loc("sss_weight_map_scale", (1.0, 1.0, 1.0)),
        "sss_weight_map_type": int(pr.get("sss_weight_map_type", 2) if pr.get("sss_weight_map_type") is not None else 2),
        "sss_radius_image_path": pr.get("sss_radius_image_path") or "",
        "sss_radius_image_colorspace": pr.get("sss_radius_image_colorspace") or "",
        "sss_radius_tex_vector_mode": int(pr.get("sss_radius_tex_vector_mode", 0) or 0),
        "sss_radius_map_location": loc("sss_radius_map_location", (0.0, 0.0, 0.0)),
        "sss_radius_map_rotation": loc("sss_radius_map_rotation", (0.0, 0.0, 0.0)),
        "sss_radius_map_scale": loc("sss_radius_map_scale", (1.0, 1.0, 1.0)),
        "sss_radius_map_type": int(pr.get("sss_radius_map_type", 2) if pr.get("sss_radius_map_type") is not None else 2),
        "sss_scale_image_path": pr.get("sss_scale_image_path") or "",
        "sss_scale_image_colorspace": pr.get("sss_scale_image_colorspace") or "",
        "sss_scale_tex_vector_mode": int(pr.get("sss_scale_tex_vector_mode", 0) or 0),
        "sss_scale_map_location": loc("sss_scale_map_location", (0.0, 0.0, 0.0)),
        "sss_scale_map_rotation": loc("sss_scale_map_rotation", (0.0, 0.0, 0.0)),
        "sss_scale_map_scale": loc("sss_scale_map_scale", (1.0, 1.0, 1.0)),
        "sss_scale_map_type": int(pr.get("sss_scale_map_type", 2) if pr.get("sss_scale_map_type") is not None else 2),
        "sss_ior_image_path": pr.get("sss_ior_image_path") or "",
        "sss_ior_image_colorspace": pr.get("sss_ior_image_colorspace") or "",
        "sss_ior_tex_vector_mode": int(pr.get("sss_ior_tex_vector_mode", 0) or 0),
        "sss_ior_map_location": loc("sss_ior_map_location", (0.0, 0.0, 0.0)),
        "sss_ior_map_rotation": loc("sss_ior_map_rotation", (0.0, 0.0, 0.0)),
        "sss_ior_map_scale": loc("sss_ior_map_scale", (1.0, 1.0, 1.0)),
        "sss_ior_map_type": int(pr.get("sss_ior_map_type", 2) if pr.get("sss_ior_map_type") is not None else 2),
        "sss_aniso_image_path": pr.get("sss_aniso_image_path") or "",
        "sss_aniso_image_colorspace": pr.get("sss_aniso_image_colorspace") or "",
        "sss_aniso_tex_vector_mode": int(pr.get("sss_aniso_tex_vector_mode", 0) or 0),
        "sss_aniso_map_location": loc("sss_aniso_map_location", (0.0, 0.0, 0.0)),
        "sss_aniso_map_rotation": loc("sss_aniso_map_rotation", (0.0, 0.0, 0.0)),
        "sss_aniso_map_scale": loc("sss_aniso_map_scale", (1.0, 1.0, 1.0)),
        "sss_aniso_map_type": int(pr.get("sss_aniso_map_type", 2) if pr.get("sss_aniso_map_type") is not None else 2),
        "thin_wall_image_path": pr.get("thin_wall_image_path") or "",
        "thin_wall_image_colorspace": pr.get("thin_wall_image_colorspace") or "",
        "thin_wall_tex_vector_mode": int(pr.get("thin_wall_tex_vector_mode", 0) or 0),
        "thin_wall_map_location": loc("thin_wall_map_location", (0.0, 0.0, 0.0)),
        "thin_wall_map_rotation": loc("thin_wall_map_rotation", (0.0, 0.0, 0.0)),
        "thin_wall_map_scale": loc("thin_wall_map_scale", (1.0, 1.0, 1.0)),
        "thin_wall_map_type": int(pr.get("thin_wall_map_type", 2) if pr.get("thin_wall_map_type") is not None else 2),
        "diffuse_rough_image_path": pr.get("diffuse_rough_image_path") or "",
        "diffuse_rough_image_colorspace": pr.get("diffuse_rough_image_colorspace") or "",
        "diffuse_rough_tex_vector_mode": int(pr.get("diffuse_rough_tex_vector_mode", 0) or 0),
        "diffuse_rough_map_location": loc("diffuse_rough_map_location", (0.0, 0.0, 0.0)),
        "diffuse_rough_map_rotation": loc("diffuse_rough_map_rotation", (0.0, 0.0, 0.0)),
        "diffuse_rough_map_scale": loc("diffuse_rough_map_scale", (1.0, 1.0, 1.0)),
        "diffuse_rough_map_type": int(pr.get("diffuse_rough_map_type", 2) if pr.get("diffuse_rough_map_type") is not None else 2),
        "aniso_image_path": pr.get("aniso_image_path") or "",
        "aniso_image_colorspace": pr.get("aniso_image_colorspace") or "",
        "aniso_tex_vector_mode": int(pr.get("aniso_tex_vector_mode", 0) or 0),
        "aniso_map_location": loc("aniso_map_location", (0.0, 0.0, 0.0)),
        "aniso_map_rotation": loc("aniso_map_rotation", (0.0, 0.0, 0.0)),
        "aniso_map_scale": loc("aniso_map_scale", (1.0, 1.0, 1.0)),
        "aniso_map_type": int(pr.get("aniso_map_type", 2) if pr.get("aniso_map_type") is not None else 2),
        "aniso_rot_image_path": pr.get("aniso_rot_image_path") or "",
        "aniso_rot_image_colorspace": pr.get("aniso_rot_image_colorspace") or "",
        "aniso_rot_tex_vector_mode": int(pr.get("aniso_rot_tex_vector_mode", 0) or 0),
        "aniso_rot_map_location": loc("aniso_rot_map_location", (0.0, 0.0, 0.0)),
        "aniso_rot_map_rotation": loc("aniso_rot_map_rotation", (0.0, 0.0, 0.0)),
        "aniso_rot_map_scale": loc("aniso_rot_map_scale", (1.0, 1.0, 1.0)),
        "aniso_rot_map_type": int(pr.get("aniso_rot_map_type", 2) if pr.get("aniso_rot_map_type") is not None else 2),
        "tangent_image_path": pr.get("tangent_image_path") or "",
        "tangent_image_colorspace": pr.get("tangent_image_colorspace") or "",
        "tangent_tex_vector_mode": int(pr.get("tangent_tex_vector_mode", 0) or 0),
        "tangent_map_location": loc("tangent_map_location", (0.0, 0.0, 0.0)),
        "tangent_map_rotation": loc("tangent_map_rotation", (0.0, 0.0, 0.0)),
        "tangent_map_scale": loc("tangent_map_scale", (1.0, 1.0, 1.0)),
        "tangent_map_type": int(pr.get("tangent_map_type", 2) if pr.get("tangent_map_type") is not None else 2),
        "bump_image_path": pr.get("bump_image_path") or "",
        "bump_image_colorspace": pr.get("bump_image_colorspace") or "",
        "bump_tex_vector_mode": int(pr.get("bump_tex_vector_mode", 0) or 0),
        "bump_map_location": loc("bump_map_location", (0.0, 0.0, 0.0)),
        "bump_map_rotation": loc("bump_map_rotation", (0.0, 0.0, 0.0)),
        "bump_map_scale": loc("bump_map_scale", (1.0, 1.0, 1.0)),
        "bump_map_type": int(pr.get("bump_map_type", 2) if pr.get("bump_map_type") is not None else 2),
        "bump_strength": float(pr.get("bump_strength", 1.0) if pr.get("bump_strength") is not None else 1.0),
        "bump_distance": float(pr.get("bump_distance", 0.001) if pr.get("bump_distance") is not None else 0.001),
        "bump_invert": int(pr.get("bump_invert", 0) or 0),
        "thin_wall": int(pr.get("thin_wall", 0) or 0),
        "transmission_weight": float(
            pr.get("transmission_weight", 0.0) if pr.get("transmission_weight") is not None else 0.0
        ),
    }
    out.update(_pack_tex_ob_fields(pr, depsgraph=depsgraph))
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
        or (pr.get("emit_color_image_path") or "")
        or (pr.get("coat_rough_image_path") or "")
        or (pr.get("coat_ior_image_path") or "")
        or (pr.get("coat_tint_image_path") or "")
        or (pr.get("sheen_rough_image_path") or "")
        or (pr.get("sheen_tint_image_path") or "")
        or (pr.get("coat_normal_image_path") or "")
        or (pr.get("spec_tint_image_path") or "")
        or (pr.get("film_thick_image_path") or "")
        or (pr.get("film_ior_image_path") or "")
        or (pr.get("sss_weight_image_path") or "")
        or (pr.get("sss_radius_image_path") or "")
        or (pr.get("sss_scale_image_path") or "")
        or (pr.get("sss_ior_image_path") or "")
        or (pr.get("sss_aniso_image_path") or "")
        or (pr.get("thin_wall_image_path") or "")
        or (pr.get("diffuse_rough_image_path") or "")
        or (pr.get("aniso_image_path") or "")
        or (pr.get("aniso_rot_image_path") or "")
        or (pr.get("tangent_image_path") or "")
        or (pr.get("bump_image_path") or "")
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
    tex_fields = _pack_tex_fields(pr, depsgraph=depsgraph)
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
        **_finalize_world_pack(scene, depsgraph=depsgraph),
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
    _world_info(scene)
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

    Returns dict with width/height/samples, camera fields, world_* fields,
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
        tex_fields = _pack_tex_fields(pr, depsgraph=depsgraph)
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
        **_finalize_world_pack(scene, depsgraph=depsgraph),
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
    desc.normal_space = int(packed.get("normal_space", 0) or 0)

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

    desc.emit_color_image_path = enc("emit_color_image_path")
    desc.emit_color_image_colorspace = enc("emit_color_image_colorspace")
    desc.emit_color_tex_vector_mode = int(packed.get("emit_color_tex_vector_mode", 0) or 0)
    vec3("emit_color_map_location", "emit_color_map_location")
    vec3("emit_color_map_rotation", "emit_color_map_rotation")
    vec3("emit_color_map_scale", "emit_color_map_scale", (1.0, 1.0, 1.0))
    desc.emit_color_map_type = int(
        packed.get("emit_color_map_type", 2) if packed.get("emit_color_map_type") is not None else 2
    )

    desc.coat_rough_image_path = enc("coat_rough_image_path")
    desc.coat_rough_image_colorspace = enc("coat_rough_image_colorspace")
    desc.coat_rough_tex_vector_mode = int(packed.get("coat_rough_tex_vector_mode", 0) or 0)
    vec3("coat_rough_map_location", "coat_rough_map_location")
    vec3("coat_rough_map_rotation", "coat_rough_map_rotation")
    vec3("coat_rough_map_scale", "coat_rough_map_scale", (1.0, 1.0, 1.0))
    desc.coat_rough_map_type = int(
        packed.get("coat_rough_map_type", 2) if packed.get("coat_rough_map_type") is not None else 2
    )

    desc.coat_ior_image_path = enc("coat_ior_image_path")
    desc.coat_ior_image_colorspace = enc("coat_ior_image_colorspace")
    desc.coat_ior_tex_vector_mode = int(packed.get("coat_ior_tex_vector_mode", 0) or 0)
    vec3("coat_ior_map_location", "coat_ior_map_location")
    vec3("coat_ior_map_rotation", "coat_ior_map_rotation")
    vec3("coat_ior_map_scale", "coat_ior_map_scale", (1.0, 1.0, 1.0))
    desc.coat_ior_map_type = int(
        packed.get("coat_ior_map_type", 2) if packed.get("coat_ior_map_type") is not None else 2
    )

    desc.coat_tint_image_path = enc("coat_tint_image_path")
    desc.coat_tint_image_colorspace = enc("coat_tint_image_colorspace")
    desc.coat_tint_tex_vector_mode = int(packed.get("coat_tint_tex_vector_mode", 0) or 0)
    vec3("coat_tint_map_location", "coat_tint_map_location")
    vec3("coat_tint_map_rotation", "coat_tint_map_rotation")
    vec3("coat_tint_map_scale", "coat_tint_map_scale", (1.0, 1.0, 1.0))
    desc.coat_tint_map_type = int(
        packed.get("coat_tint_map_type", 2) if packed.get("coat_tint_map_type") is not None else 2
    )

    desc.sheen_rough_image_path = enc("sheen_rough_image_path")
    desc.sheen_rough_image_colorspace = enc("sheen_rough_image_colorspace")
    desc.sheen_rough_tex_vector_mode = int(packed.get("sheen_rough_tex_vector_mode", 0) or 0)
    vec3("sheen_rough_map_location", "sheen_rough_map_location")
    vec3("sheen_rough_map_rotation", "sheen_rough_map_rotation")
    vec3("sheen_rough_map_scale", "sheen_rough_map_scale", (1.0, 1.0, 1.0))
    desc.sheen_rough_map_type = int(
        packed.get("sheen_rough_map_type", 2) if packed.get("sheen_rough_map_type") is not None else 2
    )

    desc.sheen_tint_image_path = enc("sheen_tint_image_path")
    desc.sheen_tint_image_colorspace = enc("sheen_tint_image_colorspace")
    desc.sheen_tint_tex_vector_mode = int(packed.get("sheen_tint_tex_vector_mode", 0) or 0)
    vec3("sheen_tint_map_location", "sheen_tint_map_location")
    vec3("sheen_tint_map_rotation", "sheen_tint_map_rotation")
    vec3("sheen_tint_map_scale", "sheen_tint_map_scale", (1.0, 1.0, 1.0))
    desc.sheen_tint_map_type = int(
        packed.get("sheen_tint_map_type", 2) if packed.get("sheen_tint_map_type") is not None else 2
    )

    desc.coat_normal_image_path = enc("coat_normal_image_path")
    desc.coat_normal_image_colorspace = enc("coat_normal_image_colorspace")
    desc.coat_normal_tex_vector_mode = int(packed.get("coat_normal_tex_vector_mode", 0) or 0)
    vec3("coat_normal_map_location", "coat_normal_map_location")
    vec3("coat_normal_map_rotation", "coat_normal_map_rotation")
    vec3("coat_normal_map_scale", "coat_normal_map_scale", (1.0, 1.0, 1.0))
    desc.coat_normal_map_type = int(
        packed.get("coat_normal_map_type", 2) if packed.get("coat_normal_map_type") is not None else 2
    )
    desc.coat_normal_strength = float(
        packed.get("coat_normal_strength", 1.0) if packed.get("coat_normal_strength") is not None else 1.0
    )
    desc.coat_normal_space = int(packed.get("coat_normal_space", 0) or 0)

    desc.spec_tint_image_path = enc("spec_tint_image_path")
    desc.spec_tint_image_colorspace = enc("spec_tint_image_colorspace")
    desc.spec_tint_tex_vector_mode = int(packed.get("spec_tint_tex_vector_mode", 0) or 0)
    vec3("spec_tint_map_location", "spec_tint_map_location")
    vec3("spec_tint_map_rotation", "spec_tint_map_rotation")
    vec3("spec_tint_map_scale", "spec_tint_map_scale", (1.0, 1.0, 1.0))
    desc.spec_tint_map_type = int(
        packed.get("spec_tint_map_type", 2) if packed.get("spec_tint_map_type") is not None else 2
    )

    desc.film_thick_image_path = enc("film_thick_image_path")
    desc.film_thick_image_colorspace = enc("film_thick_image_colorspace")
    desc.film_thick_tex_vector_mode = int(packed.get("film_thick_tex_vector_mode", 0) or 0)
    vec3("film_thick_map_location", "film_thick_map_location")
    vec3("film_thick_map_rotation", "film_thick_map_rotation")
    vec3("film_thick_map_scale", "film_thick_map_scale", (1.0, 1.0, 1.0))
    desc.film_thick_map_type = int(
        packed.get("film_thick_map_type", 2) if packed.get("film_thick_map_type") is not None else 2
    )

    desc.film_ior_image_path = enc("film_ior_image_path")
    desc.film_ior_image_colorspace = enc("film_ior_image_colorspace")
    desc.film_ior_tex_vector_mode = int(packed.get("film_ior_tex_vector_mode", 0) or 0)
    vec3("film_ior_map_location", "film_ior_map_location")
    vec3("film_ior_map_rotation", "film_ior_map_rotation")
    vec3("film_ior_map_scale", "film_ior_map_scale", (1.0, 1.0, 1.0))
    desc.film_ior_map_type = int(
        packed.get("film_ior_map_type", 2) if packed.get("film_ior_map_type") is not None else 2
    )

    desc.sss_weight_image_path = enc("sss_weight_image_path")
    desc.sss_weight_image_colorspace = enc("sss_weight_image_colorspace")
    desc.sss_weight_tex_vector_mode = int(packed.get("sss_weight_tex_vector_mode", 0) or 0)
    vec3("sss_weight_map_location", "sss_weight_map_location")
    vec3("sss_weight_map_rotation", "sss_weight_map_rotation")
    vec3("sss_weight_map_scale", "sss_weight_map_scale", (1.0, 1.0, 1.0))
    desc.sss_weight_map_type = int(
        packed.get("sss_weight_map_type", 2) if packed.get("sss_weight_map_type") is not None else 2
    )

    desc.sss_radius_image_path = enc("sss_radius_image_path")
    desc.sss_radius_image_colorspace = enc("sss_radius_image_colorspace")
    desc.sss_radius_tex_vector_mode = int(packed.get("sss_radius_tex_vector_mode", 0) or 0)
    vec3("sss_radius_map_location", "sss_radius_map_location")
    vec3("sss_radius_map_rotation", "sss_radius_map_rotation")
    vec3("sss_radius_map_scale", "sss_radius_map_scale", (1.0, 1.0, 1.0))
    desc.sss_radius_map_type = int(
        packed.get("sss_radius_map_type", 2) if packed.get("sss_radius_map_type") is not None else 2
    )

    desc.sss_scale_image_path = enc("sss_scale_image_path")
    desc.sss_scale_image_colorspace = enc("sss_scale_image_colorspace")
    desc.sss_scale_tex_vector_mode = int(packed.get("sss_scale_tex_vector_mode", 0) or 0)
    vec3("sss_scale_map_location", "sss_scale_map_location")
    vec3("sss_scale_map_rotation", "sss_scale_map_rotation")
    vec3("sss_scale_map_scale", "sss_scale_map_scale", (1.0, 1.0, 1.0))
    desc.sss_scale_map_type = int(
        packed.get("sss_scale_map_type", 2) if packed.get("sss_scale_map_type") is not None else 2
    )

    desc.sss_ior_image_path = enc("sss_ior_image_path")
    desc.sss_ior_image_colorspace = enc("sss_ior_image_colorspace")
    desc.sss_ior_tex_vector_mode = int(packed.get("sss_ior_tex_vector_mode", 0) or 0)
    vec3("sss_ior_map_location", "sss_ior_map_location")
    vec3("sss_ior_map_rotation", "sss_ior_map_rotation")
    vec3("sss_ior_map_scale", "sss_ior_map_scale", (1.0, 1.0, 1.0))
    desc.sss_ior_map_type = int(
        packed.get("sss_ior_map_type", 2) if packed.get("sss_ior_map_type") is not None else 2
    )

    desc.sss_aniso_image_path = enc("sss_aniso_image_path")
    desc.sss_aniso_image_colorspace = enc("sss_aniso_image_colorspace")
    desc.sss_aniso_tex_vector_mode = int(packed.get("sss_aniso_tex_vector_mode", 0) or 0)
    vec3("sss_aniso_map_location", "sss_aniso_map_location")
    vec3("sss_aniso_map_rotation", "sss_aniso_map_rotation")
    vec3("sss_aniso_map_scale", "sss_aniso_map_scale", (1.0, 1.0, 1.0))
    desc.sss_aniso_map_type = int(
        packed.get("sss_aniso_map_type", 2) if packed.get("sss_aniso_map_type") is not None else 2
    )

    desc.thin_wall_image_path = enc("thin_wall_image_path")
    desc.thin_wall_image_colorspace = enc("thin_wall_image_colorspace")
    desc.thin_wall_tex_vector_mode = int(packed.get("thin_wall_tex_vector_mode", 0) or 0)
    vec3("thin_wall_map_location", "thin_wall_map_location")
    vec3("thin_wall_map_rotation", "thin_wall_map_rotation")
    vec3("thin_wall_map_scale", "thin_wall_map_scale", (1.0, 1.0, 1.0))
    desc.thin_wall_map_type = int(
        packed.get("thin_wall_map_type", 2) if packed.get("thin_wall_map_type") is not None else 2
    )

    desc.diffuse_rough_image_path = enc("diffuse_rough_image_path")
    desc.diffuse_rough_image_colorspace = enc("diffuse_rough_image_colorspace")
    desc.diffuse_rough_tex_vector_mode = int(packed.get("diffuse_rough_tex_vector_mode", 0) or 0)
    vec3("diffuse_rough_map_location", "diffuse_rough_map_location")
    vec3("diffuse_rough_map_rotation", "diffuse_rough_map_rotation")
    vec3("diffuse_rough_map_scale", "diffuse_rough_map_scale", (1.0, 1.0, 1.0))
    desc.diffuse_rough_map_type = int(
        packed.get("diffuse_rough_map_type", 2) if packed.get("diffuse_rough_map_type") is not None else 2
    )

    desc.aniso_image_path = enc("aniso_image_path")
    desc.aniso_image_colorspace = enc("aniso_image_colorspace")
    desc.aniso_tex_vector_mode = int(packed.get("aniso_tex_vector_mode", 0) or 0)
    vec3("aniso_map_location", "aniso_map_location")
    vec3("aniso_map_rotation", "aniso_map_rotation")
    vec3("aniso_map_scale", "aniso_map_scale", (1.0, 1.0, 1.0))
    desc.aniso_map_type = int(
        packed.get("aniso_map_type", 2) if packed.get("aniso_map_type") is not None else 2
    )

    desc.aniso_rot_image_path = enc("aniso_rot_image_path")
    desc.aniso_rot_image_colorspace = enc("aniso_rot_image_colorspace")
    desc.aniso_rot_tex_vector_mode = int(packed.get("aniso_rot_tex_vector_mode", 0) or 0)
    vec3("aniso_rot_map_location", "aniso_rot_map_location")
    vec3("aniso_rot_map_rotation", "aniso_rot_map_rotation")
    vec3("aniso_rot_map_scale", "aniso_rot_map_scale", (1.0, 1.0, 1.0))
    desc.aniso_rot_map_type = int(
        packed.get("aniso_rot_map_type", 2) if packed.get("aniso_rot_map_type") is not None else 2
    )

    desc.tangent_image_path = enc("tangent_image_path")
    desc.tangent_image_colorspace = enc("tangent_image_colorspace")
    desc.tangent_tex_vector_mode = int(packed.get("tangent_tex_vector_mode", 0) or 0)
    vec3("tangent_map_location", "tangent_map_location")
    vec3("tangent_map_rotation", "tangent_map_rotation")
    vec3("tangent_map_scale", "tangent_map_scale", (1.0, 1.0, 1.0))
    desc.tangent_map_type = int(
        packed.get("tangent_map_type", 2) if packed.get("tangent_map_type") is not None else 2
    )

    desc.bump_image_path = enc("bump_image_path")
    desc.bump_image_colorspace = enc("bump_image_colorspace")
    desc.bump_tex_vector_mode = int(packed.get("bump_tex_vector_mode", 0) or 0)
    vec3("bump_map_location", "bump_map_location")
    vec3("bump_map_rotation", "bump_map_rotation")
    vec3("bump_map_scale", "bump_map_scale", (1.0, 1.0, 1.0))
    desc.bump_map_type = int(
        packed.get("bump_map_type", 2) if packed.get("bump_map_type") is not None else 2
    )
    desc.bump_strength = float(
        packed.get("bump_strength", 1.0) if packed.get("bump_strength") is not None else 1.0
    )
    desc.bump_distance = float(
        packed.get("bump_distance", 0.001) if packed.get("bump_distance") is not None else 0.001
    )
    desc.bump_invert = int(packed.get("bump_invert", 0) or 0)
    desc.thin_wall = int(packed.get("thin_wall", 0) or 0)
    desc.transmission_weight = float(
        packed.get("transmission_weight", 0.0) if packed.get("transmission_weight") is not None else 0.0
    )
    desc.tex_ob_use_transform = int(packed.get("tex_ob_use_transform", 0) or 0)
    tfm = packed.get("tex_ob_tfm") or _identity_3x4()
    for i, v in enumerate(tfm):
        desc.tex_ob_tfm[i] = float(v)


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
            ("world_image_path", ctypes.c_char_p),
            ("world_image_colorspace", ctypes.c_char_p),
            ("world_projection", ctypes.c_int),
            ("world_tex_vector_mode", ctypes.c_int),
            ("world_map_location", ctypes.c_float * 3),
            ("world_map_rotation", ctypes.c_float * 3),
            ("world_map_scale", ctypes.c_float * 3),
            ("world_map_type", ctypes.c_int),
            ("world_ob_use_transform", ctypes.c_int),
            ("world_ob_tfm", ctypes.c_float * 12),
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
            ("normal_space", ctypes.c_int),
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
            ("emit_color_image_path", ctypes.c_char_p),
            ("emit_color_image_colorspace", ctypes.c_char_p),
            ("emit_color_tex_vector_mode", ctypes.c_int),
            ("emit_color_map_location", ctypes.c_float * 3),
            ("emit_color_map_rotation", ctypes.c_float * 3),
            ("emit_color_map_scale", ctypes.c_float * 3),
            ("emit_color_map_type", ctypes.c_int),
            ("coat_rough_image_path", ctypes.c_char_p),
            ("coat_rough_image_colorspace", ctypes.c_char_p),
            ("coat_rough_tex_vector_mode", ctypes.c_int),
            ("coat_rough_map_location", ctypes.c_float * 3),
            ("coat_rough_map_rotation", ctypes.c_float * 3),
            ("coat_rough_map_scale", ctypes.c_float * 3),
            ("coat_rough_map_type", ctypes.c_int),
            ("coat_ior_image_path", ctypes.c_char_p),
            ("coat_ior_image_colorspace", ctypes.c_char_p),
            ("coat_ior_tex_vector_mode", ctypes.c_int),
            ("coat_ior_map_location", ctypes.c_float * 3),
            ("coat_ior_map_rotation", ctypes.c_float * 3),
            ("coat_ior_map_scale", ctypes.c_float * 3),
            ("coat_ior_map_type", ctypes.c_int),
            ("coat_tint_image_path", ctypes.c_char_p),
            ("coat_tint_image_colorspace", ctypes.c_char_p),
            ("coat_tint_tex_vector_mode", ctypes.c_int),
            ("coat_tint_map_location", ctypes.c_float * 3),
            ("coat_tint_map_rotation", ctypes.c_float * 3),
            ("coat_tint_map_scale", ctypes.c_float * 3),
            ("coat_tint_map_type", ctypes.c_int),
            ("sheen_rough_image_path", ctypes.c_char_p),
            ("sheen_rough_image_colorspace", ctypes.c_char_p),
            ("sheen_rough_tex_vector_mode", ctypes.c_int),
            ("sheen_rough_map_location", ctypes.c_float * 3),
            ("sheen_rough_map_rotation", ctypes.c_float * 3),
            ("sheen_rough_map_scale", ctypes.c_float * 3),
            ("sheen_rough_map_type", ctypes.c_int),
            ("sheen_tint_image_path", ctypes.c_char_p),
            ("sheen_tint_image_colorspace", ctypes.c_char_p),
            ("sheen_tint_tex_vector_mode", ctypes.c_int),
            ("sheen_tint_map_location", ctypes.c_float * 3),
            ("sheen_tint_map_rotation", ctypes.c_float * 3),
            ("sheen_tint_map_scale", ctypes.c_float * 3),
            ("sheen_tint_map_type", ctypes.c_int),
            ("coat_normal_image_path", ctypes.c_char_p),
            ("coat_normal_image_colorspace", ctypes.c_char_p),
            ("coat_normal_tex_vector_mode", ctypes.c_int),
            ("coat_normal_map_location", ctypes.c_float * 3),
            ("coat_normal_map_rotation", ctypes.c_float * 3),
            ("coat_normal_map_scale", ctypes.c_float * 3),
            ("coat_normal_map_type", ctypes.c_int),
            ("coat_normal_strength", ctypes.c_float),
            ("coat_normal_space", ctypes.c_int),
            ("spec_tint_image_path", ctypes.c_char_p),
            ("spec_tint_image_colorspace", ctypes.c_char_p),
            ("spec_tint_tex_vector_mode", ctypes.c_int),
            ("spec_tint_map_location", ctypes.c_float * 3),
            ("spec_tint_map_rotation", ctypes.c_float * 3),
            ("spec_tint_map_scale", ctypes.c_float * 3),
            ("spec_tint_map_type", ctypes.c_int),
            ("film_thick_image_path", ctypes.c_char_p),
            ("film_thick_image_colorspace", ctypes.c_char_p),
            ("film_thick_tex_vector_mode", ctypes.c_int),
            ("film_thick_map_location", ctypes.c_float * 3),
            ("film_thick_map_rotation", ctypes.c_float * 3),
            ("film_thick_map_scale", ctypes.c_float * 3),
            ("film_thick_map_type", ctypes.c_int),
            ("film_ior_image_path", ctypes.c_char_p),
            ("film_ior_image_colorspace", ctypes.c_char_p),
            ("film_ior_tex_vector_mode", ctypes.c_int),
            ("film_ior_map_location", ctypes.c_float * 3),
            ("film_ior_map_rotation", ctypes.c_float * 3),
            ("film_ior_map_scale", ctypes.c_float * 3),
            ("film_ior_map_type", ctypes.c_int),
            ("sss_weight_image_path", ctypes.c_char_p),
            ("sss_weight_image_colorspace", ctypes.c_char_p),
            ("sss_weight_tex_vector_mode", ctypes.c_int),
            ("sss_weight_map_location", ctypes.c_float * 3),
            ("sss_weight_map_rotation", ctypes.c_float * 3),
            ("sss_weight_map_scale", ctypes.c_float * 3),
            ("sss_weight_map_type", ctypes.c_int),
            ("sss_radius_image_path", ctypes.c_char_p),
            ("sss_radius_image_colorspace", ctypes.c_char_p),
            ("sss_radius_tex_vector_mode", ctypes.c_int),
            ("sss_radius_map_location", ctypes.c_float * 3),
            ("sss_radius_map_rotation", ctypes.c_float * 3),
            ("sss_radius_map_scale", ctypes.c_float * 3),
            ("sss_radius_map_type", ctypes.c_int),
            ("sss_scale_image_path", ctypes.c_char_p),
            ("sss_scale_image_colorspace", ctypes.c_char_p),
            ("sss_scale_tex_vector_mode", ctypes.c_int),
            ("sss_scale_map_location", ctypes.c_float * 3),
            ("sss_scale_map_rotation", ctypes.c_float * 3),
            ("sss_scale_map_scale", ctypes.c_float * 3),
            ("sss_scale_map_type", ctypes.c_int),
            ("sss_ior_image_path", ctypes.c_char_p),
            ("sss_ior_image_colorspace", ctypes.c_char_p),
            ("sss_ior_tex_vector_mode", ctypes.c_int),
            ("sss_ior_map_location", ctypes.c_float * 3),
            ("sss_ior_map_rotation", ctypes.c_float * 3),
            ("sss_ior_map_scale", ctypes.c_float * 3),
            ("sss_ior_map_type", ctypes.c_int),
            ("sss_aniso_image_path", ctypes.c_char_p),
            ("sss_aniso_image_colorspace", ctypes.c_char_p),
            ("sss_aniso_tex_vector_mode", ctypes.c_int),
            ("sss_aniso_map_location", ctypes.c_float * 3),
            ("sss_aniso_map_rotation", ctypes.c_float * 3),
            ("sss_aniso_map_scale", ctypes.c_float * 3),
            ("sss_aniso_map_type", ctypes.c_int),
            ("thin_wall_image_path", ctypes.c_char_p),
            ("thin_wall_image_colorspace", ctypes.c_char_p),
            ("thin_wall_tex_vector_mode", ctypes.c_int),
            ("thin_wall_map_location", ctypes.c_float * 3),
            ("thin_wall_map_rotation", ctypes.c_float * 3),
            ("thin_wall_map_scale", ctypes.c_float * 3),
            ("thin_wall_map_type", ctypes.c_int),
            ("diffuse_rough_image_path", ctypes.c_char_p),
            ("diffuse_rough_image_colorspace", ctypes.c_char_p),
            ("diffuse_rough_tex_vector_mode", ctypes.c_int),
            ("diffuse_rough_map_location", ctypes.c_float * 3),
            ("diffuse_rough_map_rotation", ctypes.c_float * 3),
            ("diffuse_rough_map_scale", ctypes.c_float * 3),
            ("diffuse_rough_map_type", ctypes.c_int),
            ("aniso_image_path", ctypes.c_char_p),
            ("aniso_image_colorspace", ctypes.c_char_p),
            ("aniso_tex_vector_mode", ctypes.c_int),
            ("aniso_map_location", ctypes.c_float * 3),
            ("aniso_map_rotation", ctypes.c_float * 3),
            ("aniso_map_scale", ctypes.c_float * 3),
            ("aniso_map_type", ctypes.c_int),
            ("aniso_rot_image_path", ctypes.c_char_p),
            ("aniso_rot_image_colorspace", ctypes.c_char_p),
            ("aniso_rot_tex_vector_mode", ctypes.c_int),
            ("aniso_rot_map_location", ctypes.c_float * 3),
            ("aniso_rot_map_rotation", ctypes.c_float * 3),
            ("aniso_rot_map_scale", ctypes.c_float * 3),
            ("aniso_rot_map_type", ctypes.c_int),
            ("tangent_image_path", ctypes.c_char_p),
            ("tangent_image_colorspace", ctypes.c_char_p),
            ("tangent_tex_vector_mode", ctypes.c_int),
            ("tangent_map_location", ctypes.c_float * 3),
            ("tangent_map_rotation", ctypes.c_float * 3),
            ("tangent_map_scale", ctypes.c_float * 3),
            ("tangent_map_type", ctypes.c_int),
            ("bump_image_path", ctypes.c_char_p),
            ("bump_image_colorspace", ctypes.c_char_p),
            ("bump_tex_vector_mode", ctypes.c_int),
            ("bump_map_location", ctypes.c_float * 3),
            ("bump_map_rotation", ctypes.c_float * 3),
            ("bump_map_scale", ctypes.c_float * 3),
            ("bump_map_type", ctypes.c_int),
            ("bump_strength", ctypes.c_float),
            ("bump_distance", ctypes.c_float),
            ("bump_invert", ctypes.c_int),
            ("thin_wall", ctypes.c_int),
            ("transmission_weight", ctypes.c_float),
            ("tex_ob_use_transform", ctypes.c_int),
            ("tex_ob_tfm", ctypes.c_float * 12),
        ]

    return QT_SimpleScene


def _fill_world_vec_ctypes(desc, packed):
    """Lockstep world_tex_vector_mode + Mapping + world_ob_* (Slice 2ac/2ae)."""
    desc.world_tex_vector_mode = int(packed.get("world_tex_vector_mode", 0) or 0)
    for i, v in enumerate(packed.get("world_map_location") or (0.0, 0.0, 0.0)):
        desc.world_map_location[i] = float(v)
    for i, v in enumerate(packed.get("world_map_rotation") or (0.0, 0.0, 0.0)):
        desc.world_map_rotation[i] = float(v)
    for i, v in enumerate(packed.get("world_map_scale") or (1.0, 1.0, 1.0)):
        desc.world_map_scale[i] = float(v)
    desc.world_map_type = int(packed.get("world_map_type", 2) or 2)
    desc.world_ob_use_transform = int(packed.get("world_ob_use_transform", 0) or 0)
    tfm = packed.get("world_ob_tfm") or _identity_3x4()
    for i, v in enumerate(tfm):
        desc.world_ob_tfm[i] = float(v)

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
    wip = (packed.get("world_image_path") or "").encode("utf-8")
    wics = (packed.get("world_image_colorspace") or "").encode("utf-8")
    desc.world_image_path = wip if wip else None
    desc.world_image_colorspace = wics if wics else None
    desc.world_projection = int(packed.get("world_projection", 0) or 0)
    _fill_world_vec_ctypes(desc, packed)
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
    desc._keep = (verts, tris, uvs_buf, tex_keep, wip, wics)
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
            ("normal_space", ctypes.c_int),
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
            ("emit_color_image_path", ctypes.c_char_p),
            ("emit_color_image_colorspace", ctypes.c_char_p),
            ("emit_color_tex_vector_mode", ctypes.c_int),
            ("emit_color_map_location", ctypes.c_float * 3),
            ("emit_color_map_rotation", ctypes.c_float * 3),
            ("emit_color_map_scale", ctypes.c_float * 3),
            ("emit_color_map_type", ctypes.c_int),
            ("coat_rough_image_path", ctypes.c_char_p),
            ("coat_rough_image_colorspace", ctypes.c_char_p),
            ("coat_rough_tex_vector_mode", ctypes.c_int),
            ("coat_rough_map_location", ctypes.c_float * 3),
            ("coat_rough_map_rotation", ctypes.c_float * 3),
            ("coat_rough_map_scale", ctypes.c_float * 3),
            ("coat_rough_map_type", ctypes.c_int),
            ("coat_ior_image_path", ctypes.c_char_p),
            ("coat_ior_image_colorspace", ctypes.c_char_p),
            ("coat_ior_tex_vector_mode", ctypes.c_int),
            ("coat_ior_map_location", ctypes.c_float * 3),
            ("coat_ior_map_rotation", ctypes.c_float * 3),
            ("coat_ior_map_scale", ctypes.c_float * 3),
            ("coat_ior_map_type", ctypes.c_int),
            ("coat_tint_image_path", ctypes.c_char_p),
            ("coat_tint_image_colorspace", ctypes.c_char_p),
            ("coat_tint_tex_vector_mode", ctypes.c_int),
            ("coat_tint_map_location", ctypes.c_float * 3),
            ("coat_tint_map_rotation", ctypes.c_float * 3),
            ("coat_tint_map_scale", ctypes.c_float * 3),
            ("coat_tint_map_type", ctypes.c_int),
            ("sheen_rough_image_path", ctypes.c_char_p),
            ("sheen_rough_image_colorspace", ctypes.c_char_p),
            ("sheen_rough_tex_vector_mode", ctypes.c_int),
            ("sheen_rough_map_location", ctypes.c_float * 3),
            ("sheen_rough_map_rotation", ctypes.c_float * 3),
            ("sheen_rough_map_scale", ctypes.c_float * 3),
            ("sheen_rough_map_type", ctypes.c_int),
            ("sheen_tint_image_path", ctypes.c_char_p),
            ("sheen_tint_image_colorspace", ctypes.c_char_p),
            ("sheen_tint_tex_vector_mode", ctypes.c_int),
            ("sheen_tint_map_location", ctypes.c_float * 3),
            ("sheen_tint_map_rotation", ctypes.c_float * 3),
            ("sheen_tint_map_scale", ctypes.c_float * 3),
            ("sheen_tint_map_type", ctypes.c_int),
            ("coat_normal_image_path", ctypes.c_char_p),
            ("coat_normal_image_colorspace", ctypes.c_char_p),
            ("coat_normal_tex_vector_mode", ctypes.c_int),
            ("coat_normal_map_location", ctypes.c_float * 3),
            ("coat_normal_map_rotation", ctypes.c_float * 3),
            ("coat_normal_map_scale", ctypes.c_float * 3),
            ("coat_normal_map_type", ctypes.c_int),
            ("coat_normal_strength", ctypes.c_float),
            ("coat_normal_space", ctypes.c_int),
            ("spec_tint_image_path", ctypes.c_char_p),
            ("spec_tint_image_colorspace", ctypes.c_char_p),
            ("spec_tint_tex_vector_mode", ctypes.c_int),
            ("spec_tint_map_location", ctypes.c_float * 3),
            ("spec_tint_map_rotation", ctypes.c_float * 3),
            ("spec_tint_map_scale", ctypes.c_float * 3),
            ("spec_tint_map_type", ctypes.c_int),
            ("film_thick_image_path", ctypes.c_char_p),
            ("film_thick_image_colorspace", ctypes.c_char_p),
            ("film_thick_tex_vector_mode", ctypes.c_int),
            ("film_thick_map_location", ctypes.c_float * 3),
            ("film_thick_map_rotation", ctypes.c_float * 3),
            ("film_thick_map_scale", ctypes.c_float * 3),
            ("film_thick_map_type", ctypes.c_int),
            ("film_ior_image_path", ctypes.c_char_p),
            ("film_ior_image_colorspace", ctypes.c_char_p),
            ("film_ior_tex_vector_mode", ctypes.c_int),
            ("film_ior_map_location", ctypes.c_float * 3),
            ("film_ior_map_rotation", ctypes.c_float * 3),
            ("film_ior_map_scale", ctypes.c_float * 3),
            ("film_ior_map_type", ctypes.c_int),
            ("sss_weight_image_path", ctypes.c_char_p),
            ("sss_weight_image_colorspace", ctypes.c_char_p),
            ("sss_weight_tex_vector_mode", ctypes.c_int),
            ("sss_weight_map_location", ctypes.c_float * 3),
            ("sss_weight_map_rotation", ctypes.c_float * 3),
            ("sss_weight_map_scale", ctypes.c_float * 3),
            ("sss_weight_map_type", ctypes.c_int),
            ("sss_radius_image_path", ctypes.c_char_p),
            ("sss_radius_image_colorspace", ctypes.c_char_p),
            ("sss_radius_tex_vector_mode", ctypes.c_int),
            ("sss_radius_map_location", ctypes.c_float * 3),
            ("sss_radius_map_rotation", ctypes.c_float * 3),
            ("sss_radius_map_scale", ctypes.c_float * 3),
            ("sss_radius_map_type", ctypes.c_int),
            ("sss_scale_image_path", ctypes.c_char_p),
            ("sss_scale_image_colorspace", ctypes.c_char_p),
            ("sss_scale_tex_vector_mode", ctypes.c_int),
            ("sss_scale_map_location", ctypes.c_float * 3),
            ("sss_scale_map_rotation", ctypes.c_float * 3),
            ("sss_scale_map_scale", ctypes.c_float * 3),
            ("sss_scale_map_type", ctypes.c_int),
            ("sss_ior_image_path", ctypes.c_char_p),
            ("sss_ior_image_colorspace", ctypes.c_char_p),
            ("sss_ior_tex_vector_mode", ctypes.c_int),
            ("sss_ior_map_location", ctypes.c_float * 3),
            ("sss_ior_map_rotation", ctypes.c_float * 3),
            ("sss_ior_map_scale", ctypes.c_float * 3),
            ("sss_ior_map_type", ctypes.c_int),
            ("sss_aniso_image_path", ctypes.c_char_p),
            ("sss_aniso_image_colorspace", ctypes.c_char_p),
            ("sss_aniso_tex_vector_mode", ctypes.c_int),
            ("sss_aniso_map_location", ctypes.c_float * 3),
            ("sss_aniso_map_rotation", ctypes.c_float * 3),
            ("sss_aniso_map_scale", ctypes.c_float * 3),
            ("sss_aniso_map_type", ctypes.c_int),
            ("thin_wall_image_path", ctypes.c_char_p),
            ("thin_wall_image_colorspace", ctypes.c_char_p),
            ("thin_wall_tex_vector_mode", ctypes.c_int),
            ("thin_wall_map_location", ctypes.c_float * 3),
            ("thin_wall_map_rotation", ctypes.c_float * 3),
            ("thin_wall_map_scale", ctypes.c_float * 3),
            ("thin_wall_map_type", ctypes.c_int),
            ("diffuse_rough_image_path", ctypes.c_char_p),
            ("diffuse_rough_image_colorspace", ctypes.c_char_p),
            ("diffuse_rough_tex_vector_mode", ctypes.c_int),
            ("diffuse_rough_map_location", ctypes.c_float * 3),
            ("diffuse_rough_map_rotation", ctypes.c_float * 3),
            ("diffuse_rough_map_scale", ctypes.c_float * 3),
            ("diffuse_rough_map_type", ctypes.c_int),
            ("aniso_image_path", ctypes.c_char_p),
            ("aniso_image_colorspace", ctypes.c_char_p),
            ("aniso_tex_vector_mode", ctypes.c_int),
            ("aniso_map_location", ctypes.c_float * 3),
            ("aniso_map_rotation", ctypes.c_float * 3),
            ("aniso_map_scale", ctypes.c_float * 3),
            ("aniso_map_type", ctypes.c_int),
            ("aniso_rot_image_path", ctypes.c_char_p),
            ("aniso_rot_image_colorspace", ctypes.c_char_p),
            ("aniso_rot_tex_vector_mode", ctypes.c_int),
            ("aniso_rot_map_location", ctypes.c_float * 3),
            ("aniso_rot_map_rotation", ctypes.c_float * 3),
            ("aniso_rot_map_scale", ctypes.c_float * 3),
            ("aniso_rot_map_type", ctypes.c_int),
            ("tangent_image_path", ctypes.c_char_p),
            ("tangent_image_colorspace", ctypes.c_char_p),
            ("tangent_tex_vector_mode", ctypes.c_int),
            ("tangent_map_location", ctypes.c_float * 3),
            ("tangent_map_rotation", ctypes.c_float * 3),
            ("tangent_map_scale", ctypes.c_float * 3),
            ("tangent_map_type", ctypes.c_int),
            ("bump_image_path", ctypes.c_char_p),
            ("bump_image_colorspace", ctypes.c_char_p),
            ("bump_tex_vector_mode", ctypes.c_int),
            ("bump_map_location", ctypes.c_float * 3),
            ("bump_map_rotation", ctypes.c_float * 3),
            ("bump_map_scale", ctypes.c_float * 3),
            ("bump_map_type", ctypes.c_int),
            ("bump_strength", ctypes.c_float),
            ("bump_distance", ctypes.c_float),
            ("bump_invert", ctypes.c_int),
            ("thin_wall", ctypes.c_int),
            ("transmission_weight", ctypes.c_float),
            ("tex_ob_use_transform", ctypes.c_int),
            ("tex_ob_tfm", ctypes.c_float * 12),
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
            ("world_image_path", ctypes.c_char_p),
            ("world_image_colorspace", ctypes.c_char_p),
            ("world_projection", ctypes.c_int),
            ("world_tex_vector_mode", ctypes.c_int),
            ("world_map_location", ctypes.c_float * 3),
            ("world_map_rotation", ctypes.c_float * 3),
            ("world_map_scale", ctypes.c_float * 3),
            ("world_map_type", ctypes.c_int),
            ("world_ob_use_transform", ctypes.c_int),
            ("world_ob_tfm", ctypes.c_float * 12),
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
    wip = (packed.get("world_image_path") or "").encode("utf-8")
    wics = (packed.get("world_image_colorspace") or "").encode("utf-8")
    keep.append(wip)
    keep.append(wics)
    desc.world_image_path = wip if wip else None
    desc.world_image_colorspace = wics if wics else None
    desc.world_projection = int(packed.get("world_projection", 0) or 0)
    _fill_world_vec_ctypes(desc, packed)
    if exr_path:
        desc.exr_path = exr_path.encode("utf-8")
    else:
        desc.exr_path = None
    desc._keep = (meshes_arr, lights_arr, keep)
    return desc

