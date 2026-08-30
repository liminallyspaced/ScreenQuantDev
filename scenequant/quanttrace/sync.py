# QuantTrace depsgraph → QT_SimpleScene packer (Slice 2b).
#
# Walks a Blender depsgraph and packs camera / meshes / Principled /
# AREA lights / world into ctypes QT_SimpleScene (1+1) or QT_Scene (N+N)
# for quanttrace_render_scene_rgba / quanttrace_render_qt_scene_rgba.
# Slice 2aw: up to 2048 meshes + 128 AREA/POINT/SUN/SPOT lights (was 32/16).
# Slice 2f: TEX_IMAGE → Principled Base Color (default UV; disk or packed).
# Slice 2h: TEX_COORD UV (+ optional Mapping POINT/VECTOR constants) → TEX_IMAGE Vector.
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
# Slice 2az: Principled.Normal ← Bevel (samples + unlinked Radius). Nested
#   NormalMap / Bump OK; Bump.Normal ← NormalMap OK (loft Metal_Sheet).
# Slice 2ba: ColorRamp (VALTORGB) → Principled.Roughness. Official
#   colorramp_to_array LUT size+1=257. Fac unlinked float OR Fac ← TEX_IMAGE
#   (reuse rough_image_*). n==0 skips (2az/2i bit-identical). Noise/Fresnel/
#   LayerWeight/GROUP/Mix Fac named refuse Slice 2ba. Color output → Roughness.
# Slice 2y: Principled Thin Wall unlinked BOOLEAN + unlinked Transmission Weight
#   constant. Linked Thin Wall still refuses (BOOLEAN, not TEX_IMAGE).
# Slice 2aa: Environment Texture world (empty path = Slice 2b black).
# Slice 2ab: TEX_COORD Object-with-pointer (use_transform + ob_tfm).
#   Empty Object ref stays Slice 2l (use_transform=0). Mesh-level one pointer.
# Slice 2af: packed-only images materialize to /tmp/quanttrace_packed/ (filepath ABI).
# Slice 2ag: Mapping L/R/S linked Combine XYZ / Value (same float3 ABI).
# Slice 2ah: world Background Strength linked from ShaderNodeValue (same float ABI).
# Slice 2ai: ShaderNodeMath ADD/SUB/MUL/DIV/POWER → Strength (fold into float).
# Slice 2at: 3-deep constant Math nest → Strength (fold max depth 3; 2ai was 2).
#   Identity: 0–2-deep still bit-identical. 4-deep still refuses.
# Slice 2au: MULTIPLY(TEX_ENVIRONMENT/TEX_IMAGE/TEX_SKY.Color, 0) or
#   MULTIPLY(0, tex.Color) → 0.0 (proven const 0; do not evaluate the texture).
#   Outer DIV/ADD then fold as today. Non-zero tex Math / ADD/SUB/DIV/POWER
#   with a tex Color input still refuse.
# Slice 2av: Mapping vector_type POINT accepted (world env/sky/teximage Vector
#   and mesh TEX_IMAGE). NODE_MAPPING_TYPE_POINT=0; VECTOR=2 still. TEXTURE/
#   NORMAL still refuse. POINT uses Location (rotate(vector*scale)+location);
#   VECTOR ignores Location. Native already set_mapping_type(world_map_type).
# Slice 2aj: ShaderNodeMix FLOAT / MixRGB constant → Strength (fold into float).
# Slice 2ak: ShaderNodeMapRange FLOAT LINEAR + ShaderNodeClamp → Strength (fold into float).
# Slice 2al: world Background Color constant ABI (world_color float3).
#   Unlinked non-black Color, ShaderNodeRGB, MixRGB/Mix FLOAT constants,
#   Value/Math → Color as grey. TEX_ENVIRONMENT still wins (color stays 0).
# Slice 2am: ShaderNodeTexSky → Background Color (world_sky_* after world_color).
#   type 0 = 2al/2aa. 1=PREETHAM 2=HOSEK 3=NISHITA/MULTIPLE 4=SINGLE.
#   Path empty, world_color zeros. Unlinked Vector only.
#   Slice 2ar: linked Sky Vector (TEX_COORD / Mapping) accepted.
#   Slice 2as: RGB Curves accepted (packed LUT). Noise still refuses.
#   Slice 2at: 3-deep constant Math → Strength (fold max 3). Noise still refuses.
#   Slice 2au: TEX_ENVIRONMENT×0 MULTIPLY folds to 0.0 (then outer DIV/ADD).
# Slice 2an: ShaderNodeTexImage → Background Color (world_color_image_* after
#   world_sky_ozone_density). Empty path = 2aa/2al/2am bit-identical. Priority:
#   TEX_ENVIRONMENT → TEX_SKY → TEX_IMAGE → RGB/Mix. Vector via world_tex_vector_*
#   (same 2ac/2ae shapes). Noise / multi-link Color still refuse; RGB Curves → 2as.
# Slice 2ax: peel REROUTE + unlinked Gamma + HueSat on Principled Base Color
#   (base_gamma / base_hsv_*). Identity skips native nodes (2f bit-identical).
#   Mix on Base Color still refuses (named Slice 2ax). Object+material in errors.
# Slice 2ao: peel unlinked Gamma + HueSat on world Color (one of each, either
#   order walking toward the source). Identity (gamma=1, hue=0.5, sat=1, val=1,
#   fac=1) keeps 2aa/2al/2am/2an bit-identical. Native applies loft order:
#   Color source → Gamma → HSV → Background. Linked Gamma/Hue/Sat/Value/Fac,
#   Noise, Mix after HSV, second Gamma/HueSat still refuse; RGB Curves → 2as.
# Slice 2ap: also peel one unlinked BrightContrast (Bright+Contrast unlinked
#   floats). Identity bright=0 contrast=0 skips native node — 2ao/2an/2am/2aa/
#   2al bit-identical. Up to 3 hops (Gamma, HueSat, BrightContrast, any order).
#   Native loft: Color → Gamma → HSV → BrightContrast → Background. Second
#   BrightContrast / linked Bright/Contrast refuse. Noise / Mix after HSV /
#   second Gamma/HueSat still refuse; linked Sky Vector → 2ar; RGB Curves → 2as.
# Slice 2ar: linked Sky Vector (TEX_COORD / Mapping) on TEX_SKY.
# Slice 2as: ShaderNodeRGBCurve → world Color packed LUT (world_curves_*).
#   n==0 skip; Fac==0 skip; official curvemapping_color_to_array (257).
#   Noise / Vector Curves / Float Curve / second RGB Curves / linked Fac refuse.
# Slice 2bd: ShaderNodeRGBCurve → Principled Base Color packed LUT (base_curves_*).
#   n==0 / Fac==0 skip (2ay/2ax/2f bit-identical). Unlinked Fac; Color-in
#   TEX_IMAGE / Mix / Gamma/HSV / constant. Linked Fac / second Curves /
#   Vector/Float Curve refuse Slice 2bd. Native Mix then Curves (loft
#   Concrete_Facade: dual TEX Mix → Curves → Base Color).
# Slice 2bg: nested constant Mix / Curves(constant) on Mix A/B fold to
#   dual-constant MixColorNode (optional Fac←Fresnel 2bf). No new C++ ABI.
#   Curves Color-in←TEX_IMAGE on Mix side is Slice 2bh (not 2bg refuse).
# Slice 2bi: Normal Map Color ← Combine RGB + Invert G of Separate←TEX_IMAGE
#   (normal_invert_g_enable / fac; coat_normal_invert_g_*). enable=0 keeps
#   2j TEX_IMAGE Color bit-identical. Cite SeparateColorNode / InvertNode /
#   CombineColorNode RGB. Linked Fac / HSV-HSL mode / Invert on R|B /
#   mismatched TEX / GROUP / Mix Color named refuse Slice 2bi.
# Slice 2bh: RGB Curves ← TEX_IMAGE on Mix A/B of Principled Base Color
#   (base_mix_curves_* after last base_curves_*). One-side LUT only.
#   Native: ImageTexture → RGBCurves → Mix A or B; other side 2ay
#   (const RGB or second TEX_IMAGE); then 2bd Curves-after-Mix if n>0.
#   n==0 / NULL / fac==0 skips mix-side RGBCurvesNode (2bg/2ay/2bf/2bd
#   bit-identical). Do not reuse base_curves_* (different graph position).
#   Linked Fac / Vector Curves / Float Curve / second Curves on same side /
#   Noise Color-in / GROUP / Fac←NEW_GEOMETRY/INVERT refuse Slice 2bh.
# Slice 2be: Invert → Principled.Roughness (rough_invert_enable / fac).
#   enable=0 skips InvertNode (2ba/2bb/2i bit-identical). Unlinked Fac;
#   Color <- TEX_IMAGE or ColorRamp (or constant Color fold via Rec.709
#   NODE_CONVERT_CF). Linked Fac / nested Invert / GROUP / Mix / Noise
#   Color named refuse Slice 2be.
# Slice 2bj: SEPARATE_COLOR → Principled.Roughness (rough_separate_enable /
#   rough_separate_channel after rough_invert_*). enable=0 skips
#   SeparateColorNode — 2be/2ba/2bb/2i bit-identical. RGB mode only;
#   channel 0=Red/1=Green/2=Blue from TEX_IMAGE Color (or constant fold).
#   HSV/HSL / Invert←Separate / GROUP / Mix named refuse Slice 2bj.
# Slice 2bl: SEPARATE_COLOR → Bump.Height (bump_separate_enable /
#   bump_separate_channel after bump_noise_*). enable=0 skips
#   SeparateColorNode — 2bc/2x bit-identical. RGB mode only; loft
#   Sideboard Blue ← TEX_IMAGE Color (or constant fold). HSV/HSL /
#   Invert←Separate into Height / GROUP / Mix named refuse Slice 2bl.
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
    """Validate MAPPING: POINT or VECTOR, Vector←TEX_COORD, L/R/S unlinked or 2ag constants.

    NODE_MAPPING_TYPE_POINT=0, TEXTURE=1, VECTOR=2, NORMAL=3
    (cycles-src/src/kernel/svm/types.h + mapping_util.h).
    POINT: rotate(vector * scale) + location.
    VECTOR: rotate(vector * scale) — Location packed for ABI, SVM ignores it.
    TEXTURE accepted Slice 2ay (map_type=1); NORMAL still refuse.
    """
    vtype = str(getattr(map_node, "vector_type", "POINT") or "POINT").upper()
    if vtype == "POINT":
        map_type = 0
    elif vtype == "TEXTURE":
        # Slice 2ay: loft Metal_Sheet / Concrete dual-TEX Mix uses Mapping TEXTURE.
        # Native MappingNode already set_mapping_type(NODE_MAPPING_TYPE_TEXTURE=1).
        map_type = 1
    elif vtype == "VECTOR":
        map_type = 2
    else:
        raise QuantTraceSyncError(
            f"Mapping vector_type={vtype!r} refused "
            "(Slice 2ay accepts POINT/TEXTURE/VECTOR; NORMAL still refuse)"
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
    return (
        _float3_from_mapping_lrs_sock(loc_s, "Location"),
        _float3_from_mapping_lrs_sock(rot_s, "Rotation"),
        _float3_from_mapping_lrs_sock(scl_s, "Scale"),
        map_type,
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
    # Slice 2bi identity — enable=0 skips Separate/InvertG/Combine (2j bit-identical).
    out[f"{prefix}invert_g_enable"] = 0
    out[f"{prefix}invert_g_fac"] = 1.0
    return out


def _empty_bump_noise_info(prefix: str = "bump_") -> dict:
    """Slice 2bc identity — enable=0 skips Noise on Bump Height (2x bit-identical)."""
    pfx = f"{prefix}noise_"
    return {
        f"{pfx}enable": 0,
        f"{pfx}dimensions": 3,
        f"{pfx}type": 1,  # QT_NOISE_FBM
        f"{pfx}normalize": 1,
        f"{pfx}w": 0.0,
        f"{pfx}scale": 5.0,
        f"{pfx}detail": 2.0,
        f"{pfx}roughness": 0.5,
        f"{pfx}lacunarity": 2.0,
        f"{pfx}offset": 0.0,
        f"{pfx}gain": 1.0,
        f"{pfx}distortion": 0.0,
        f"{pfx}use_color": 0,
    }


def _empty_bump_separate_info(prefix: str = "bump_") -> dict:
    """Slice 2bl identity — enable=0 skips SeparateColor on Bump Height."""
    return {
        f"{prefix}separate_enable": 0,
        f"{prefix}separate_channel": 2,  # Blue (loft Sideboard)
    }


def _empty_bump_info(prefix: str = "bump_") -> dict:
    out = _prefix_tex(_empty_tex_info(), prefix)
    out[f"{prefix}strength"] = 1.0
    out[f"{prefix}distance"] = 0.001
    out[f"{prefix}invert"] = 0
    out.update(_empty_bump_noise_info(prefix))
    out.update(_empty_bump_separate_info(prefix))
    return out


def _empty_bevel_info() -> dict:
    """Slice 2az: Bevel off — bit-identical with prior slices."""
    return {
        "bevel_enable": 0,
        "bevel_samples": 4,
        "bevel_radius": 0.05,
    }


def _empty_rough_ramp_noise_info() -> dict:
    """Slice 2bb identity — enable=0 skips NoiseTextureNode (2ba bit-identical)."""
    return {
        "rough_ramp_noise_enable": 0,
        "rough_ramp_noise_dimensions": 3,
        "rough_ramp_noise_type": 1,  # QT_NOISE_FBM
        "rough_ramp_noise_normalize": 1,
        "rough_ramp_noise_w": 0.0,
        "rough_ramp_noise_scale": 5.0,  # Blender 5.2 RNA default; unused when enable=0
        "rough_ramp_noise_detail": 2.0,
        "rough_ramp_noise_roughness": 0.5,
        "rough_ramp_noise_lacunarity": 2.0,
        "rough_ramp_noise_offset": 0.0,
        "rough_ramp_noise_gain": 1.0,
        "rough_ramp_noise_distortion": 0.0,
        "rough_ramp_noise_use_color": 0,
    }


_QT_NOISE_TYPE = {
    "MULTIFRACTAL": 0,
    "FBM": 1,
    "HYBRID_MULTIFRACTAL": 2,
    "RIDGED_MULTIFRACTAL": 3,
    "HETERO_TERRAIN": 4,
}
_QT_NOISE_DIM = {"1D": 1, "2D": 2, "3D": 3, "4D": 4}


def _empty_rough_invert_info() -> dict:
    """Slice 2be identity — enable=0 skips InvertNode (2ba/2bb/2i bit-identical)."""
    return {
        "rough_invert_enable": 0,
        "rough_invert_fac": 1.0,
        **_empty_rough_separate_info(),
    }


def _empty_rough_separate_info() -> dict:
    """Slice 2bj identity — enable=0 skips SeparateColorNode."""
    return {
        "rough_separate_enable": 0,
        "rough_separate_channel": 1,  # Green (loft Sideboard)
    }


def _empty_rough_ramp_info() -> dict:
    """Slice 2ba/2bb/2be: no ColorRamp — 2i TEX_IMAGE / constant roughness."""
    return {
        "rough_ramp": [],
        "rough_ramp_alpha": [],
        "rough_ramp_n": 0,
        "rough_ramp_interpolate": 1,
        "rough_ramp_fac": 0.5,
        **_empty_rough_ramp_noise_info(),
        **_empty_rough_invert_info(),
    }


def _rgb_to_y_cf(rgb) -> float:
    """NODE_CONVERT_CF: linear_rgb_to_gray = dot(c, film.rgb_to_y) Rec.709."""
    r, g, b = float(rgb[0]), float(rgb[1]), float(rgb[2])
    return 0.2126729 * r + 0.7151522 * g + 0.0721750 * b


def _invert_mix_rgb(color, fac: float):
    """Cycles InvertNode: factor*(1-color) + (1-factor)*color per channel."""
    f = float(fac)
    return tuple(f * (1.0 - float(x)) + (1.0 - f) * float(x) for x in color[:3])


def _require_unlinked_float_noise(node, names, label: str, where: str, slice_tag: str) -> float:
    """Unlinked Noise socket constant. None-check — never `or` (0 valid)."""
    inputs = getattr(node, "inputs", None)
    if inputs is None:
        raise QuantTraceSyncError(
            f"{where}.{label} has no inputs ({slice_tag})"
        )
    sock = _sock_ident_or_name(inputs, *names)
    if sock is None:
        raise QuantTraceSyncError(
            f"{where}.{label} missing ({slice_tag})"
        )
    if getattr(sock, "is_linked", False):
        raise QuantTraceSyncError(
            f"{where}.{label} is linked refused "
            f"({slice_tag}: unlinked constants only)"
        )
    v = getattr(sock, "default_value", None)
    if v is None:
        raise QuantTraceSyncError(
            f"{where}.{label} has no default_value ({slice_tag})"
        )
    return float(v)


def _noise_mapping_is_identity(node) -> bool:
    """Blender TexMapping identity (loft Plane: POINT loc0 rot0 scale1)."""
    tm = getattr(node, "texture_mapping", None)
    if tm is None:
        return True
    loc = tuple(float(x) for x in (getattr(tm, "translation", (0.0, 0.0, 0.0)) or (0, 0, 0)))
    rot = tuple(float(x) for x in (getattr(tm, "rotation", (0.0, 0.0, 0.0)) or (0, 0, 0)))
    scale = tuple(float(x) for x in (getattr(tm, "scale", (1.0, 1.0, 1.0)) or (1, 1, 1)))
    if any(abs(x) > 1e-8 for x in loc) or any(abs(x) > 1e-8 for x in rot):
        return False
    if any(abs(x - 1.0) > 1e-8 for x in scale):
        return False
    return True


def _pack_noise_rna(fn, fs, *, where: str, slice_tag: str, key_prefix: str) -> dict:
    """Pack ShaderNodeTexNoise Factor/Color RNA (2bb ramp Fac / 2bc bump Height).

    Proven loft Plane subset: 3D FBM normalize, Vector unlinked Generated,
    all float inputs unlinked. Packs full Blender 5.2 RNA Cycles uses
    (dimensions, type, normalize, W/Scale/Detail/Roughness/Lacunarity/
    Offset/Gain/Distortion). Linked Vector / non-identity texture_mapping
    refuse by name.
    """
    out = {
        f"{key_prefix}enable": 0,
        f"{key_prefix}dimensions": 3,
        f"{key_prefix}type": 1,
        f"{key_prefix}normalize": 1,
        f"{key_prefix}w": 0.0,
        f"{key_prefix}scale": 5.0,
        f"{key_prefix}detail": 2.0,
        f"{key_prefix}roughness": 0.5,
        f"{key_prefix}lacunarity": 2.0,
        f"{key_prefix}offset": 0.0,
        f"{key_prefix}gain": 1.0,
        f"{key_prefix}distortion": 0.0,
        f"{key_prefix}use_color": 0,
    }
    out_name = getattr(fs, "name", None) if fs is not None else None
    out_ident = getattr(fs, "identifier", None) if fs is not None else None
    names = {str(out_name or ""), str(out_ident or "")}
    if names & {"Color", "color"}:
        use_color = 1
    elif names & {"Fac", "Factor", "fac"}:
        use_color = 0
    else:
        raise QuantTraceSyncError(
            f"{where} output {out_name!r} refused "
            f"({slice_tag}: Factor or Color only)"
        )
    inputs = getattr(fn, "inputs", None)
    vec = _sock_ident_or_name(inputs, "Vector") if inputs is not None else None
    if vec is not None and getattr(vec, "is_linked", False):
        raise QuantTraceSyncError(
            f"{where} Vector is linked refused "
            f"({slice_tag}: unlinked Generated default only)"
        )
    if not _noise_mapping_is_identity(fn):
        raise QuantTraceSyncError(
            f"{where} texture_mapping refused "
            f"({slice_tag}: identity mapping only)"
        )
    dims_s = str(getattr(fn, "noise_dimensions", "3D") or "3D")
    dims = _QT_NOISE_DIM.get(dims_s)
    if dims is None:
        raise QuantTraceSyncError(
            f"{where} dimensions {dims_s!r} refused ({slice_tag})"
        )
    type_s = str(getattr(fn, "noise_type", "FBM") or "FBM")
    ntype = _QT_NOISE_TYPE.get(type_s)
    if ntype is None:
        raise QuantTraceSyncError(
            f"{where} type {type_s!r} refused ({slice_tag})"
        )
    out[f"{key_prefix}enable"] = 1
    out[f"{key_prefix}dimensions"] = dims
    out[f"{key_prefix}type"] = ntype
    out[f"{key_prefix}normalize"] = 1 if bool(getattr(fn, "normalize", True)) else 0
    out[f"{key_prefix}w"] = _require_unlinked_float_noise(
        fn, ("W",), "W", where, slice_tag
    )
    out[f"{key_prefix}scale"] = _require_unlinked_float_noise(
        fn, ("Scale",), "Scale", where, slice_tag
    )
    out[f"{key_prefix}detail"] = _require_unlinked_float_noise(
        fn, ("Detail",), "Detail", where, slice_tag
    )
    out[f"{key_prefix}roughness"] = _require_unlinked_float_noise(
        fn, ("Roughness",), "Roughness", where, slice_tag
    )
    out[f"{key_prefix}lacunarity"] = _require_unlinked_float_noise(
        fn, ("Lacunarity",), "Lacunarity", where, slice_tag
    )
    out[f"{key_prefix}offset"] = _require_unlinked_float_noise(
        fn, ("Offset",), "Offset", where, slice_tag
    )
    out[f"{key_prefix}gain"] = _require_unlinked_float_noise(
        fn, ("Gain",), "Gain", where, slice_tag
    )
    out[f"{key_prefix}distortion"] = _require_unlinked_float_noise(
        fn, ("Distortion",), "Distortion", where, slice_tag
    )
    out[f"{key_prefix}use_color"] = use_color
    return out


def _pack_noise_for_ramp_fac(fn, fs, ctx: str) -> dict:
    """Slice 2bb: ShaderNodeTexNoise Factor/Color → ColorRamp.Fac."""
    return _pack_noise_rna(
        fn,
        fs,
        where=f"{ctx} Principled.Roughness ColorRamp.Fac Noise",
        slice_tag="Slice 2bb",
        key_prefix="rough_ramp_noise_",
    )



def _pack_bump_separate(from_node, from_sock, *, label: str = "Normal", prefix: str = "bump_") -> dict:
    """Slice 2bl: SEPARATE_COLOR.{R|G|B} <- TEX_IMAGE Color (or constant fold)."""
    ctx_label = f"Principled.{label} Bump Height"
    mode = str(getattr(from_node, "mode", "RGB") or "RGB").upper()
    if mode != "RGB":
        raise QuantTraceSyncError(
            f"{ctx_label} Separate Color mode={mode!r} refused "
            f"(Slice 2bl: RGB only; HSV/HSL still refuse)"
        )
    out_name = getattr(from_sock, "name", "") if from_sock is not None else ""
    channel_map = {
        "Red": 0, "R": 0,
        "Green": 1, "G": 1,
        "Blue": 2, "B": 2,
    }
    if out_name not in channel_map:
        raise QuantTraceSyncError(
            f"{ctx_label} Separate output {out_name!r} refused "
            f"(Slice 2bl: Red/Green/Blue only)"
        )
    channel = channel_map[out_name]
    inputs = getattr(from_node, "inputs", None)
    color_sock = _sock_ident_or_name(inputs, "Color") if inputs is not None else None
    # Constant fold: unlinked Color / RGB node → no height source (flat bump).
    def _fold_const(col):
        # Constant Height → dH=0; skip bump image/noise/separate (2x empty).
        out = {**_prefix_tex(_empty_tex_info(), prefix), **_empty_bump_noise_info(prefix)}
        out[f"{prefix}separate_enable"] = 0
        out[f"{prefix}separate_channel"] = int(channel)
        out["_bump_separate_folded"] = float(col[channel] if isinstance(col, (tuple, list)) else 0.0)
        return out

    if color_sock is None or not getattr(color_sock, "is_linked", False):
        dv = getattr(color_sock, "default_value", None) if color_sock is not None else None
        try:
            col = (float(dv[0]), float(dv[1]), float(dv[2]))
        except (TypeError, IndexError, ValueError):
            col = (0.0, 0.0, 0.0)
        return _fold_const(col)
    clinks = list(getattr(color_sock, "links", None) or [])
    if len(clinks) != 1:
        raise QuantTraceSyncError(
            f"{ctx_label} Separate.Color has multiple links (Slice 2bl)"
        )
    cn = getattr(clinks[0], "from_node", None)
    cs = getattr(clinks[0], "from_socket", None)
    cn, cs = _peel_reroute(cn, cs)
    ntype_c = getattr(cn, "type", None) if cn is not None else None
    if ntype_c == "RGB" or (
        cn is not None and getattr(cn, "bl_idname", "") == "ShaderNodeRGB"
    ):
        dv = getattr(cs, "default_value", None) if cs is not None else None
        try:
            col = (float(dv[0]), float(dv[1]), float(dv[2]))
        except (TypeError, IndexError, ValueError):
            col = (0.0, 0.0, 0.0)
        return _fold_const(col)
    if ntype_c != "TEX_IMAGE":
        raise QuantTraceSyncError(
            f"{ctx_label} Separate.Color from {ntype_c!r} refused "
            f"(Slice 2bl: TEX_IMAGE Color or constant RGB only; GROUP / Mix / "
            f"Noise / Invert still refuse)"
        )
    out_c = getattr(cs, "name", "") if cs is not None else ""
    if out_c not in ("Color", "color"):
        raise QuantTraceSyncError(
            f"{ctx_label} Separate.Color from TEX_IMAGE "
            f"output {out_c!r} refused (Slice 2bl: Color only)"
        )
    class _L:
        pass
    class _S:
        pass
    link = _L()
    link.from_node = cn
    link.from_socket = cs
    dummy = _S()
    dummy.links = [link]
    tex = _tex_image_from_sock(dummy, f"{label} Bump Height")
    out = {**_prefix_tex(tex, prefix), **_empty_bump_noise_info(prefix)}
    out[f"{prefix}separate_enable"] = 1
    out[f"{prefix}separate_channel"] = int(channel)
    return out


def _pack_noise_for_bump_height(fn, fs, *, label: str = "Normal") -> dict:
    """Slice 2bc: ShaderNodeTexNoise Factor/Color → Bump.Height."""
    return _pack_noise_rna(
        fn,
        fs,
        where=f"Principled.{label} Bump Height Noise",
        slice_tag="Slice 2bc",
        key_prefix="bump_noise_",
    )


def _pack_color_ramp_lut(node) -> tuple:
    """Official intern/cycles/blender/util.h colorramp_to_array.

    RAMP_TABLE_SIZE=256; full_size = size+1 = 257; evaluate(i/size).
    CONSTANT → interpolate=0; LINEAR/EASE/CARDINAL/B_SPLINE → 1 (lerp LUT).
    bpy ColorRamp.evaluate(t) matches BKE_colorband_evaluate.
    """
    cr = getattr(node, "color_ramp", None)
    if cr is None:
        raise QuantTraceSyncError(
            "Principled.Roughness ColorRamp missing color_ramp (Slice 2ba)"
        )
    interp = str(getattr(cr, "interpolation", "LINEAR") or "LINEAR")
    interpolate = 0 if interp == "CONSTANT" else 1
    n = _RAMP_TABLE_SIZE + 1
    rgb = []
    alpha = []
    for i in range(n):
        tval = float(i) / float(_RAMP_TABLE_SIZE)
        col = cr.evaluate(tval)
        rgb.extend((float(col[0]), float(col[1]), float(col[2])))
        alpha.append(float(col[3]) if len(col) > 3 else 1.0)
    return rgb, alpha, n, interpolate


def _is_invert_node(node) -> bool:
    if node is None:
        return False
    if getattr(node, "type", None) == "INVERT":
        return True
    return getattr(node, "bl_idname", "") == "ShaderNodeInvert"


def _is_colorramp_node(node) -> bool:
    if node is None:
        return False
    if getattr(node, "type", None) in ("VALTORGB",):
        return True
    return getattr(node, "bl_idname", "") == "ShaderNodeValToRGB"


def _invert_fac_unlinked(node, ctx: str) -> float:
    """Unlinked Invert Fac/Factor (Blender 5.2 RNA name Factor). Linked refuse 2be."""
    inputs = getattr(node, "inputs", None)
    sock = _sock_ident_or_name(inputs, "Fac", "Factor") if inputs is not None else None
    if sock is None:
        return 1.0
    if getattr(sock, "is_linked", False):
        flinks = list(getattr(sock, "links", None) or [])
        ftype = None
        if flinks:
            fn = getattr(flinks[0], "from_node", None)
            fs = getattr(flinks[0], "from_socket", None)
            fn, fs = _peel_reroute(fn, fs)
            ftype = getattr(fn, "type", None) if fn is not None else None
        raise QuantTraceSyncError(
            f"{ctx} Principled.Roughness Invert.Fac from {ftype!r} refused "
            f"(Slice 2be: unlinked Fac only; linked Invert Fac still refuse)"
        )
    v = getattr(sock, "default_value", None)
    try:
        return float(v) if v is not None else 1.0
    except (TypeError, ValueError):
        return 1.0


def _stamp_rough_invert(tex, ramp, enable: int, fac: float):
    ramp = dict(ramp)
    ramp["rough_invert_enable"] = 1 if enable else 0
    ramp["rough_invert_fac"] = float(fac)
    return tex, ramp


def _stamp_rough_separate(tex, ramp, enable: int, channel: int):
    ramp = dict(ramp)
    ramp["rough_separate_enable"] = 1 if enable else 0
    ramp["rough_separate_channel"] = int(channel)
    return tex, ramp


def _pack_rough_colorramp(from_node, from_sock, ctx: str):
    """Slice 2ba/2bb ColorRamp LUT + Fac unlinked / TEX_IMAGE / TEX_NOISE."""
    empty_tex = _empty_tex_info()
    out_name = getattr(from_sock, "name", "Color") if from_sock is not None else "Color"
    if out_name not in ("Color", "color"):
        raise QuantTraceSyncError(
            f"{ctx} Principled.Roughness ColorRamp output {out_name!r} "
            f"refused (Slice 2ba: Color only this hour)"
        )
    rgb, alpha, n, interpolate = _pack_color_ramp_lut(from_node)
    ramp = {
        "rough_ramp": rgb,
        "rough_ramp_alpha": alpha,
        "rough_ramp_n": n,
        "rough_ramp_interpolate": interpolate,
        "rough_ramp_fac": 0.5,
        **_empty_rough_ramp_noise_info(),
        **_empty_rough_invert_info(),
    }
    fac_sock = None
    inputs = getattr(from_node, "inputs", None)
    if inputs is not None:
        fac_sock = _sock_ident_or_name(inputs, "Fac", "Factor")
    if fac_sock is None or not getattr(fac_sock, "is_linked", False):
        if fac_sock is not None:
            v = getattr(fac_sock, "default_value", None)
            if v is not None:
                ramp["rough_ramp_fac"] = float(v)
        return empty_tex, ramp
    flinks = list(getattr(fac_sock, "links", None) or [])
    if len(flinks) != 1:
        raise QuantTraceSyncError(
            f"{ctx} Principled.Roughness ColorRamp.Fac has multiple links "
            f"(Slice 2ba)"
        )
    fn = getattr(flinks[0], "from_node", None)
    fs = getattr(flinks[0], "from_socket", None)
    fn, fs = _peel_reroute(fn, fs)
    ftype = getattr(fn, "type", None) if fn is not None else None
    if ftype == "TEX_IMAGE":
        tex = _tex_image_from_tex_node(fn, fs, "ColorRamp.Fac", ctx=ctx)
        return tex, ramp
    if ftype in ("TEX_NOISE", "NOISE") or (
        fn is not None
        and getattr(fn, "bl_idname", "") == "ShaderNodeTexNoise"
    ):
        noise = _pack_noise_for_ramp_fac(fn, fs, ctx)
        ramp.update(noise)
        return empty_tex, ramp
    raise QuantTraceSyncError(
        f"{ctx} Principled.Roughness ColorRamp.Fac from {ftype!r} refused "
        f"(Slice 2bb: unlinked Fac, TEX_IMAGE Color, or TEX_NOISE "
        f"Factor/Color; Fresnel/LayerWeight/GROUP/Mix/linked Noise "
        f"Vector still refuse)"
    )


def _fold_invert_constant(color, fac: float, empty_tex, empty_ramp):
    """Python-only constant Invert → roughness float (NODE_CONVERT_CF Rec.709)."""
    inv = _invert_mix_rgb(color, fac)
    y = _rgb_to_y_cf(inv)
    ramp = dict(empty_ramp)
    ramp["roughness_folded"] = float(y)
    return empty_tex, ramp



def _fold_separate_constant(color, channel: int, empty_tex, empty_ramp):
    """Python-only constant Separate RGB channel → roughness float."""
    try:
        rgb = (float(color[0]), float(color[1]), float(color[2]))
    except (TypeError, IndexError, ValueError):
        rgb = (0.0, 0.0, 0.0)
    ch = 0 if channel <= 0 else (2 if channel >= 2 else 1)
    ramp = dict(empty_ramp)
    ramp["roughness_folded"] = float(rgb[ch])
    return empty_tex, ramp



def _pack_rough_separate(from_node, from_sock, ctx, empty_tex, empty_ramp):
    """Slice 2bj: SEPARATE_COLOR.{R|G|B} <- TEX_IMAGE Color (or constant fold)."""
    mode = str(getattr(from_node, "mode", "RGB") or "RGB").upper()
    if mode != "RGB":
        raise QuantTraceSyncError(
            f"{ctx} Principled.Roughness Separate Color mode={mode!r} refused "
            f"(Slice 2bj: RGB only; HSV/HSL still refuse)"
        )
    out_name = getattr(from_sock, "name", "") if from_sock is not None else ""
    channel_map = {
        "Red": 0, "R": 0,
        "Green": 1, "G": 1,
        "Blue": 2, "B": 2,
    }
    if out_name not in channel_map:
        raise QuantTraceSyncError(
            f"{ctx} Principled.Roughness Separate output {out_name!r} refused "
            f"(Slice 2bj: Red/Green/Blue only)"
        )
    channel = channel_map[out_name]
    inputs = getattr(from_node, "inputs", None)
    color_sock = _sock_ident_or_name(inputs, "Color") if inputs is not None else None
    if color_sock is None or not getattr(color_sock, "is_linked", False):
        dv = getattr(color_sock, "default_value", None) if color_sock is not None else None
        try:
            col = (float(dv[0]), float(dv[1]), float(dv[2]))
        except (TypeError, IndexError, ValueError):
            col = (0.0, 0.0, 0.0)
        return _fold_separate_constant(col, channel, empty_tex, empty_ramp)
    clinks = list(getattr(color_sock, "links", None) or [])
    if len(clinks) != 1:
        raise QuantTraceSyncError(
            f"{ctx} Principled.Roughness Separate.Color has multiple links "
            f"(Slice 2bj)"
        )
    cn = getattr(clinks[0], "from_node", None)
    cs = getattr(clinks[0], "from_socket", None)
    cn, cs = _peel_reroute(cn, cs)
    ntype_c = getattr(cn, "type", None) if cn is not None else None
    if ntype_c == "RGB" or (
        cn is not None and getattr(cn, "bl_idname", "") == "ShaderNodeRGB"
    ):
        dv = getattr(cs, "default_value", None) if cs is not None else None
        try:
            col = (float(dv[0]), float(dv[1]), float(dv[2]))
        except (TypeError, IndexError, ValueError):
            col = (0.0, 0.0, 0.0)
        return _fold_separate_constant(col, channel, empty_tex, empty_ramp)
    if ntype_c != "TEX_IMAGE":
        raise QuantTraceSyncError(
            f"{ctx} Principled.Roughness Separate.Color from {ntype_c!r} refused "
            f"(Slice 2bj: TEX_IMAGE Color or constant RGB only; GROUP / Mix / "
            f"Noise / Invert still refuse)"
        )
    out_c = getattr(cs, "name", "") if cs is not None else ""
    if out_c not in ("Color", "color"):
        raise QuantTraceSyncError(
            f"{ctx} Principled.Roughness Separate.Color from TEX_IMAGE "
            f"output {out_c!r} refused (Slice 2bj: Color only)"
        )
    tex = _tex_image_from_tex_node(cn, cs, "Roughness", ctx=ctx)
    return _stamp_rough_separate(tex, empty_ramp, 1, channel)


def _roughness_tex_and_ramp(sock, *, object_name: str = "", mat=None):
    """Slice 2ba/2bb/2be: peel REROUTE + Invert, ColorRamp LUT, TEX_IMAGE."""
    ctx = _mat_refuse_ctx(object_name, mat)
    empty_tex = _empty_tex_info()
    empty_ramp = _empty_rough_ramp_info()
    links = list(getattr(sock, "links", None) or [])
    if not links:
        return empty_tex, empty_ramp
    if len(links) != 1:
        raise QuantTraceSyncError(
            f"{ctx} Principled.Roughness has multiple links (Slice 2ba)"
        )
    from_node = getattr(links[0], "from_node", None)
    from_sock = getattr(links[0], "from_socket", None)
    from_node, from_sock = _peel_reroute(from_node, from_sock)
    invert_enable = 0
    invert_fac = 1.0
    if _is_invert_node(from_node):
        out_name = (
            getattr(from_sock, "name", "Color") if from_sock is not None else "Color"
        )
        if out_name not in ("Color", "color"):
            raise QuantTraceSyncError(
                f"{ctx} Principled.Roughness Invert output {out_name!r} "
                f"refused (Slice 2be: Color only)"
            )
        invert_fac = _invert_fac_unlinked(from_node, ctx)
        inputs = getattr(from_node, "inputs", None)
        color_sock = (
            _sock_ident_or_name(inputs, "Color") if inputs is not None else None
        )
        if color_sock is None or not getattr(color_sock, "is_linked", False):
            dv = getattr(color_sock, "default_value", None) if color_sock is not None else None
            try:
                col = (float(dv[0]), float(dv[1]), float(dv[2]))
            except (TypeError, IndexError, ValueError):
                col = (0.0, 0.0, 0.0)
            return _fold_invert_constant(col, invert_fac, empty_tex, empty_ramp)
        clinks = list(getattr(color_sock, "links", None) or [])
        if len(clinks) != 1:
            raise QuantTraceSyncError(
                f"{ctx} Principled.Roughness Invert.Color has multiple links "
                f"(Slice 2be)"
            )
        cn = getattr(clinks[0], "from_node", None)
        cs = getattr(clinks[0], "from_socket", None)
        cn, cs = _peel_reroute(cn, cs)
        if _is_invert_node(cn):
            raise QuantTraceSyncError(
                f"{ctx} Principled.Roughness Invert.Color from nested Invert "
                f"refused (Slice 2be: one Invert this hour)"
            )
        ntype_c = getattr(cn, "type", None) if cn is not None else None
        if ntype_c == "RGB" or (
            cn is not None and getattr(cn, "bl_idname", "") == "ShaderNodeRGB"
        ):
            dv = getattr(cs, "default_value", None) if cs is not None else None
            try:
                col = (float(dv[0]), float(dv[1]), float(dv[2]))
            except (TypeError, IndexError, ValueError):
                col = (0.0, 0.0, 0.0)
            return _fold_invert_constant(col, invert_fac, empty_tex, empty_ramp)
        if abs(float(invert_fac)) <= 1e-12:
            invert_enable = 0
        else:
            invert_enable = 1
        from_node, from_sock = cn, cs
    ntype = getattr(from_node, "type", None) if from_node is not None else None
    # Slice 2bj: SEPARATE_COLOR / SEPRGB → Roughness (RGB channel).
    if _is_separate_color_node(from_node):
        if invert_enable:
            raise QuantTraceSyncError(
                f"{ctx} Principled.Roughness Invert.Color from SEPARATE_COLOR "
                f"refused (Slice 2bj: Separate→Roughness only; Invert←Separate "
                f"still refuse)"
            )
        return _pack_rough_separate(from_node, from_sock, ctx, empty_tex, empty_ramp)
    if _is_colorramp_node(from_node):
        tex, ramp = _pack_rough_colorramp(from_node, from_sock, ctx)
        return _stamp_rough_invert(tex, ramp, invert_enable, invert_fac)
    if ntype == "TEX_IMAGE":
        tex = _tex_image_from_tex_node(from_node, from_sock, "Roughness", ctx=ctx)
        return _stamp_rough_invert(tex, empty_ramp, invert_enable, invert_fac)
    if invert_enable:
        raise QuantTraceSyncError(
            f"{ctx} Principled.Roughness Invert.Color from {ntype!r} refused "
            f"(Slice 2be: Invert Color <- TEX_IMAGE Color or ColorRamp Color; "
            f"unlinked Fac; linked Fac / GROUP / Mix / Noise / nested Invert "
            f"still refuse)"
        )
    raise QuantTraceSyncError(
        f"{ctx} Principled.Roughness from {ntype!r} refused "
        f"(Slice 2bj: Invert, ColorRamp, TEX_IMAGE Color, or SEPARATE_COLOR "
        f"RGB channel only)"
    )


def _bump_from_sock(sock, *, prefix: str = "bump_", label: str = "Normal") -> dict:
    """Principled.{label} <- Bump.Normal; Height <- TEX_IMAGE Color or TEX_NOISE.

    Strength and Distance must be unlinked floats (Blender 5.2 RNA 1.0 / 0.001).
    Normal input: unlinked OR ← Normal Map (Slice 2az loft Bevel←Bump←NormalMap).
    invert RNA True is OK (packed as bump_invert 1).
    use_object_space is not a Blender 5.2 property -- native forces false.
    Packed-only images materialize via _abspath_image (Slice 2af).
    Slice 2bc: Height may be TEX_NOISE Color/Factor (peel REROUTE).
    enable=0 + bump_image_path keeps Slice 2x bit-identical.
    """
    empty = _empty_bump_info(prefix)
    if sock is None:
        return {**empty, **_empty_normal_info()}
    links = list(getattr(sock, "links", None) or [])
    if not links:
        return {**empty, **_empty_normal_info()}
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
    normal_info = _empty_normal_info()
    if normal_in is not None and getattr(normal_in, "is_linked", False):
        # Slice 2az: Bump.Normal ← Normal Map only (loft).
        n_links = list(getattr(normal_in, "links", None) or [])
        if len(n_links) != 1:
            raise QuantTraceSyncError("Bump Normal input has multiple links")
        n_from = getattr(n_links[0], "from_node", None)
        n_type = getattr(n_from, "type", None) if n_from is not None else None
        if n_type != "NORMAL_MAP":
            raise QuantTraceSyncError(
                f"Bump Normal from {n_type!r} refused "
                "(Slice 2az: Normal Map only under Bump Normal)"
            )
        normal_info = _normal_map_from_sock(
            normal_in, prefix="normal_", label="Bump Normal"
        )
    if height_sock is None or not getattr(height_sock, "is_linked", False):
        raise QuantTraceSyncError(
            "Bump Height must be TEX_IMAGE Color, TEX_NOISE Factor/Color, "
            "or SEPARATE_COLOR RGB channel (Slice 2bl)"
        )
    hlinks = list(getattr(height_sock, "links", None) or [])
    if len(hlinks) != 1:
        raise QuantTraceSyncError("Bump Height has multiple links")
    hn = getattr(hlinks[0], "from_node", None)
    hs = getattr(hlinks[0], "from_socket", None)
    hn, hs = _peel_reroute(hn, hs)
    htype = getattr(hn, "type", None) if hn is not None else None
    noise_info = _empty_bump_noise_info(prefix)
    sep_info = _empty_bump_separate_info(prefix)
    if htype in ("TEX_NOISE", "NOISE") or (
        hn is not None and getattr(hn, "bl_idname", "") == "ShaderNodeTexNoise"
    ):
        noise_info = _pack_noise_for_bump_height(hn, hs, label=label)
        tex = _empty_tex_info()
        out = {**_prefix_tex(tex, prefix), **normal_info, **noise_info, **sep_info}
    elif htype in ("SEPARATE_COLOR", "SEPRGB"):
        packed_sep = _pack_bump_separate(hn, hs, label=label, prefix=prefix)
        # packed_sep already includes prefix_tex + noise empty + separate_*
        out = {**packed_sep, **normal_info}
        # drop private fold marker from mesh ABI
        out.pop("_bump_separate_folded", None)
    elif htype == "TEX_IMAGE":
        class _L:
            pass
        class _S:
            pass
        link = _L()
        link.from_node = hn
        link.from_socket = hs
        dummy = _S()
        dummy.links = [link]
        tex = _tex_image_from_sock(dummy, f"{label} Bump Height")
        out = {**_prefix_tex(tex, prefix), **normal_info, **noise_info, **sep_info}
    elif htype == "INVERT":
        # Named REFUSE: Invert←Separate into Height (Slice 2bl).
        inv_color = None
        if hn is not None and getattr(hn, "inputs", None) is not None:
            inv_color = _sock_ident_or_name(hn.inputs, "Color")
        if inv_color is not None and getattr(inv_color, "is_linked", False):
            il = list(getattr(inv_color, "links", None) or [])
            if len(il) == 1:
                inn, _ = _peel_reroute(il[0].from_node, il[0].from_socket)
                if getattr(inn, "type", None) in ("SEPARATE_COLOR", "SEPRGB"):
                    raise QuantTraceSyncError(
                        f"Principled.{label} Bump Height Invert.Color from "
                        f"SEPARATE_COLOR refused (Slice 2bl: Invert←Separate "
                        f"into Height still refuse)"
                    )
        raise QuantTraceSyncError(
            f"Principled.{label} Bump Height from 'INVERT' refused "
            f"(Slice 2bl: TEX_IMAGE Color, TEX_NOISE Factor/Color, or "
            f"SEPARATE_COLOR RGB channel; Invert/VALTORGB/MATH/GROUP still refuse)"
        )
    else:
        raise QuantTraceSyncError(
            f"Principled.{label} Bump Height from {htype!r} refused "
            f"(Slice 2bl: TEX_IMAGE Color, TEX_NOISE Factor/Color, or "
            f"SEPARATE_COLOR RGB channel; VALTORGB/MATH/GROUP/Invert still refuse)"
        )
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


def _bevel_from_sock(sock) -> dict:
    """Principled.Normal ← Bevel.Normal (Slice 2az).

    Samples from node.samples (default 4). Radius unlinked float (RNA 0.05).
    Bevel.Normal input: unlinked (geometric) OR ← Normal Map OR ← Bump
    (Bump may itself nest Normal Map — loft Metal_Sheet / Concrete).
    """
    empty = {**_empty_normal_info(), **_empty_bump_info(), **_empty_bevel_info()}
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
    if ntype != "BEVEL":
        raise QuantTraceSyncError(
            f"Principled.Normal from {ntype!r} refused (Slice 2az: Bevel only here)"
        )
    sock_name = getattr(from_sock, "name", "") if from_sock is not None else ""
    if sock_name not in ("Normal", "normal"):
        raise QuantTraceSyncError(
            "Principled.Normal must come from Bevel Normal (Slice 2az)"
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

    radius_sock = _in("Radius")
    normal_in = _in("Normal")
    if radius_sock is not None and getattr(radius_sock, "is_linked", False):
        raise QuantTraceSyncError(
            "Bevel Radius is linked (Slice 2az: unlinked float only)"
        )
    samples = int(getattr(from_node, "samples", 4) or 4)
    if samples < 1:
        samples = 1
    if samples > 128:
        samples = 128
    radius = 0.05
    if radius_sock is not None:
        radius = float(getattr(radius_sock, "default_value", 0.05))
    inner = {**_empty_normal_info(), **_empty_bump_info()}
    if normal_in is not None and getattr(normal_in, "is_linked", False):
        n_links = list(getattr(normal_in, "links", None) or [])
        if len(n_links) != 1:
            raise QuantTraceSyncError("Bevel Normal input has multiple links")
        n_from = getattr(n_links[0], "from_node", None)
        n_type = getattr(n_from, "type", None) if n_from is not None else None
        if n_type == "NORMAL_MAP":
            inner = {**_normal_map_from_sock(normal_in), **_empty_bump_info()}
        elif n_type == "BUMP":
            inner = _bump_from_sock(normal_in, label="Bevel Normal")
        else:
            raise QuantTraceSyncError(
                f"Bevel Normal from {n_type!r} refused "
                "(Slice 2az: Normal Map or Bump only under Bevel)"
            )
    return {
        **inner,
        "bevel_enable": 1,
        "bevel_samples": samples,
        "bevel_radius": radius,
    }


def _principled_normal_dispatch(sock) -> dict:
    """Principled.Normal ← Normal Map (2j) or Bump (2x) or Bevel (2az)."""
    empty = {**_empty_normal_info(), **_empty_bump_info(), **_empty_bevel_info()}
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
        return {**_normal_map_from_sock(sock), **_empty_bump_info(), **_empty_bevel_info()}
    if ntype == "BUMP":
        return {**_empty_bevel_info(), **_bump_from_sock(sock)}
    if ntype == "BEVEL":
        return _bevel_from_sock(sock)
    raise QuantTraceSyncError(
        f"Principled.Normal from {ntype!r} refused "
        "(Slice 2az: Normal Map, Bump, or Bevel only)"
    )



def _is_combine_color_node(node) -> bool:
    if node is None:
        return False
    if getattr(node, "type", None) in ("COMBINE_COLOR", "COMBRGB"):
        return True
    return getattr(node, "bl_idname", "") in (
        "ShaderNodeCombineColor",
        "ShaderNodeCombineRGB",
    )


def _is_separate_color_node(node) -> bool:
    if node is None:
        return False
    if getattr(node, "type", None) in ("SEPARATE_COLOR", "SEPRGB"):
        return True
    return getattr(node, "bl_idname", "") in (
        "ShaderNodeSeparateColor",
        "ShaderNodeSeparateRGB",
    )


def _invert_fac_unlinked_any(node, ctx: str) -> float:
    """Unlinked Invert Fac/Factor. Linked refuse with Slice 2bi tag."""
    inputs = getattr(node, "inputs", None)
    sock = _sock_ident_or_name(inputs, "Fac", "Factor") if inputs is not None else None
    if sock is None:
        return 1.0
    if getattr(sock, "is_linked", False):
        flinks = list(getattr(sock, "links", None) or [])
        ftype = None
        if flinks:
            fn = getattr(flinks[0], "from_node", None)
            fs = getattr(flinks[0], "from_socket", None)
            fn, fs = _peel_reroute(fn, fs)
            ftype = getattr(fn, "type", None) if fn is not None else None
        raise QuantTraceSyncError(
            f"{ctx} Invert.Fac from {ftype!r} refused "
            f"(Slice 2bi: unlinked Fac only; linked Invert Fac still refuse)"
        )
    v = getattr(sock, "default_value", None)
    try:
        return float(v) if v is not None else 1.0
    except (TypeError, ValueError):
        return 1.0


def _separate_channel_tex(sock, want_out: str, ctx: str):
    """If sock <- SEPARATE_COLOR.{want_out} <- TEX_IMAGE Color, return (tex_node, tex_sock).

    want_out is Red/Green/Blue (also accepts R/G/B). RGB mode only.
    """
    if sock is None or not getattr(sock, "is_linked", False):
        return None
    links = list(getattr(sock, "links", None) or [])
    if len(links) != 1:
        return None
    fn = getattr(links[0], "from_node", None)
    fs = getattr(links[0], "from_socket", None)
    fn, fs = _peel_reroute(fn, fs)
    if not _is_separate_color_node(fn):
        return None
    mode = str(getattr(fn, "mode", "RGB") or "RGB").upper()
    if mode != "RGB":
        raise QuantTraceSyncError(
            f"{ctx} Separate Color mode={mode!r} refused "
            f"(Slice 2bi: RGB only; HSV/HSL still refuse)"
        )
    out_name = getattr(fs, "name", "") if fs is not None else ""
    aliases = {
        "Red": ("Red", "R"),
        "Green": ("Green", "G"),
        "Blue": ("Blue", "B"),
    }
    if out_name not in aliases.get(want_out, (want_out,)):
        return None
    inputs = getattr(fn, "inputs", None)
    cin = None
    if inputs is not None:
        cin = inputs.get("Color") if hasattr(inputs, "get") else None
        if cin is None:
            for s in inputs:
                if getattr(s, "name", None) == "Color":
                    cin = s
                    break
    if cin is None or not getattr(cin, "is_linked", False):
        return None
    clinks = list(getattr(cin, "links", None) or [])
    if len(clinks) != 1:
        return None
    tn = getattr(clinks[0], "from_node", None)
    ts = getattr(clinks[0], "from_socket", None)
    tn, ts = _peel_reroute(tn, ts)
    if getattr(tn, "type", None) != "TEX_IMAGE":
        return None
    if getattr(ts, "name", None) not in ("Color", "color"):
        return None
    return tn, ts


def _tex_image_same(a_node, b_node) -> bool:
    if a_node is None or b_node is None:
        return False
    if a_node is b_node:
        return True
    ia = getattr(a_node, "image", None)
    ib = getattr(b_node, "image", None)
    if ia is not None and ib is not None and ia is ib:
        return True
    return False


def _try_normal_invert_g_combine(color_sock, *, label: str):
    """Detect Combine RGB with Invert on Green of same-TEX Separate.

    Returns (tex_dict, invert_fac) or None if not this pattern.
    Raises QuantTraceSyncError for near-miss COMBINE graphs (named refuse).
    """
    ctx = f"{label} Map Color"
    if color_sock is None or not getattr(color_sock, "is_linked", False):
        return None
    links = list(getattr(color_sock, "links", None) or [])
    if len(links) != 1:
        return None
    fn = getattr(links[0], "from_node", None)
    fs = getattr(links[0], "from_socket", None)
    fn, fs = _peel_reroute(fn, fs)
    if not _is_combine_color_node(fn):
        return None
    out_name = getattr(fs, "name", "") if fs is not None else ""
    if out_name not in ("Color", "color", "Image", "image"):
        raise QuantTraceSyncError(
            f"{ctx} Combine output {out_name!r} refused (Slice 2bi: Color only)"
        )
    mode = str(getattr(fn, "mode", "RGB") or "RGB").upper()
    if mode != "RGB":
        raise QuantTraceSyncError(
            f"{ctx} Combine Color mode={mode!r} refused "
            f"(Slice 2bi: RGB only; HSV/HSL still refuse)"
        )
    inputs = getattr(fn, "inputs", None)
    if inputs is None:
        raise QuantTraceSyncError(f"{ctx} Combine missing inputs (Slice 2bi)")
    r_sock = inputs.get("Red") if hasattr(inputs, "get") else None
    g_sock = inputs.get("Green") if hasattr(inputs, "get") else None
    b_sock = inputs.get("Blue") if hasattr(inputs, "get") else None
    if r_sock is None or g_sock is None or b_sock is None:
        for s in inputs:
            nm = getattr(s, "name", None)
            if nm in ("Red", "R") and r_sock is None:
                r_sock = s
            elif nm in ("Green", "G") and g_sock is None:
                g_sock = s
            elif nm in ("Blue", "B") and b_sock is None:
                b_sock = s
    r_info = _separate_channel_tex(r_sock, "Red", ctx)
    b_info = _separate_channel_tex(b_sock, "Blue", ctx)
    if r_info is None or b_info is None:
        raise QuantTraceSyncError(
            f"{ctx} Combine R/B must be Separate.RGB of TEX_IMAGE "
            f"(Slice 2bi: Invert-G Y-flip only; other Combine graphs refuse)"
        )
    if not getattr(g_sock, "is_linked", False):
        raise QuantTraceSyncError(
            f"{ctx} Combine Green unlinked refused (Slice 2bi)"
        )
    glinks = list(getattr(g_sock, "links", None) or [])
    if len(glinks) != 1:
        raise QuantTraceSyncError(
            f"{ctx} Combine Green has multiple links (Slice 2bi)"
        )
    gn = getattr(glinks[0], "from_node", None)
    gs = getattr(glinks[0], "from_socket", None)
    gn, gs = _peel_reroute(gn, gs)
    if not _is_invert_node(gn):
        gtype = getattr(gn, "type", None) if gn is not None else None
        raise QuantTraceSyncError(
            f"{ctx} Combine Green from {gtype!r} refused "
            f"(Slice 2bi: Invert on Green only; Invert on R/B / Mix / GROUP refuse)"
        )
    if getattr(gs, "name", None) not in ("Color", "color"):
        raise QuantTraceSyncError(
            f"{ctx} Invert output {getattr(gs, 'name', None)!r} refused "
            f"(Slice 2bi: Color only)"
        )
    fac = _invert_fac_unlinked_any(gn, ctx)
    inv_color = None
    ginputs = getattr(gn, "inputs", None)
    if ginputs is not None:
        inv_color = ginputs.get("Color") if hasattr(ginputs, "get") else None
        if inv_color is None:
            for s in ginputs:
                if getattr(s, "name", None) == "Color":
                    inv_color = s
                    break
    g_info = _separate_channel_tex(inv_color, "Green", ctx)
    if g_info is None:
        raise QuantTraceSyncError(
            f"{ctx} Invert.Color must be Separate.Green of TEX_IMAGE "
            f"(Slice 2bi)"
        )
    if not (
        _tex_image_same(r_info[0], g_info[0]) and _tex_image_same(r_info[0], b_info[0])
    ):
        raise QuantTraceSyncError(
            f"{ctx} Combine R/G/B from mismatched TEX_IMAGE refused (Slice 2bi)"
        )
    tex = _tex_image_from_tex_node(r_info[0], r_info[1], f"{label} Map Color")
    return tex, fac


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
    invert_g_enable = 0
    invert_g_fac = 1.0
    # Slice 2bi: peel REROUTE; try Combine+InvertG before TEX_IMAGE.
    clinks = list(getattr(color_sock, "links", None) or [])
    cfn = cfs = None
    if len(clinks) == 1:
        cfn = getattr(clinks[0], "from_node", None)
        cfs = getattr(clinks[0], "from_socket", None)
        cfn, cfs = _peel_reroute(cfn, cfs)
    ctype = getattr(cfn, "type", None) if cfn is not None else None
    if _is_combine_color_node(cfn):
        tex, invert_g_fac = _try_normal_invert_g_combine(color_sock, label=label)
        invert_g_enable = 1
    elif ctype == "TEX_IMAGE":
        tex = _tex_image_from_sock(color_sock, f"{label} Map Color")
    else:
        raise QuantTraceSyncError(
            f"Normal Map Color link is not TEX_IMAGE "
            f"(Slice 2f/2h/2i; from {ctype!r}; Slice 2bi covers Combine+InvertG only)"
        )
    out = _prefix_tex(tex, prefix)
    out[f"{prefix}strength"] = strength
    out[f"{prefix}space"] = space_i
    out[f"{prefix}invert_g_enable"] = int(invert_g_enable)
    out[f"{prefix}invert_g_fac"] = float(invert_g_fac)
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



def _base_gamma_hsv_identity():
    """Slice 2ax identity — skip Gamma/HSV on Principled Base Color (2f bit-identical)."""
    return {
        "base_gamma": 1.0,
        "base_hsv_hue": 0.5,
        "base_hsv_sat": 1.0,
        "base_hsv_val": 1.0,
        "base_hsv_fac": 1.0,
    }


def _base_mix_identity():
    """Slice 2ay identity — skip MixColorNode on Principled Base Color (2ax/2f bit-identical)."""
    return {
        "base_mix_type": 0,
        "base_mix_fac": 0.5,
        "base_mix_other": (0.0, 0.0, 0.0),
        "base_mix_chain_is_a": 1,
        "base_mix_clamp_factor": 0,
        "base_mix_clamp_result": 0,
        "base_mix_b_image_path": "",
        "base_mix_b_image_colorspace": "",
        "base_mix_fresnel_enable": 0,
        "base_mix_fresnel_ior": 1.45,
        # Slice 2bh identity — n==0 skips mix-side RGBCurvesNode.
        "base_mix_curves": None,
        "base_mix_curves_n": 0,
        "base_mix_curves_min_x": 0.0,
        "base_mix_curves_max_x": 1.0,
        "base_mix_curves_fac": 1.0,
        "base_mix_curves_extrapolate": 1,
        "base_mix_curves_on_a": 1,
    }


def _base_curves_identity():
    """Slice 2bd identity — skip RGBCurvesNode on Principled Base Color (2ay/2ax/2f bit-identical)."""
    return {
        "base_curves": None,
        "base_curves_n": 0,
        "base_curves_min_x": 0.0,
        "base_curves_max_x": 1.0,
        "base_curves_fac": 1.0,
        "base_curves_extrapolate": 1,
    }


def _tex_vector_source_key(tex_node):
    """Comparable Vector-graph key for dual TEX_IMAGE Mix (Slice 2ay).

    Accepts: both unlinked UV, both the same Mapping node, both Mapping nodes
    with equal vector_type + L/R/S + same TEX_COORD space (loft Metal_Sheet
    uses two identical TEXTURE Mappings ← UV), or both the same TEX_COORD
    output. Mismatched graphs refuse rather than inventing a second vector ABI.
    """
    inputs = getattr(tex_node, "inputs", None)
    if inputs is None:
        return ("unlinked",)
    getter = getattr(inputs, "get", None)
    vec = getter("Vector") if callable(getter) else None
    if vec is None or not getattr(vec, "is_linked", False):
        return ("unlinked",)
    vlinks = list(getattr(vec, "links", None) or [])
    if len(vlinks) != 1:
        return ("multi", id(tex_node))
    vnode = getattr(vlinks[0], "from_node", None)
    vsock = getattr(vlinks[0], "from_socket", None)
    # Peel REROUTE on Vector source.
    vnode, vsock = _peel_reroute(vnode, vsock)
    vtype = getattr(vnode, "type", None) if vnode is not None else None
    vname = getattr(vsock, "name", "") if vsock is not None else ""
    if vtype == "TEX_COORD":
        return ("texcoord", str(vname).strip().lower())
    if vtype == "MAPPING":
        def _f3(sock_names, default):
            for nm in sock_names:
                s = None
                inputs_m = getattr(vnode, "inputs", None)
                if inputs_m is not None:
                    g = getattr(inputs_m, "get", None)
                    s = g(nm) if callable(g) else None
                if s is None:
                    continue
                if getattr(s, "is_linked", False):
                    return ("linked", nm)
                dv = getattr(s, "default_value", default)
                return tuple(round(float(dv[i]), 6) for i in range(3))
            return tuple(round(float(default[i]), 6) for i in range(3))
        loc = _f3(("Location",), (0.0, 0.0, 0.0))
        rot = _f3(("Rotation",), (0.0, 0.0, 0.0))
        scale = _f3(("Scale",), (1.0, 1.0, 1.0))
        mtype = str(getattr(vnode, "vector_type", "POINT") or "POINT").upper()
        space = "UV"
        vec_in = None
        inputs_m = getattr(vnode, "inputs", None)
        if inputs_m is not None:
            g = getattr(inputs_m, "get", None)
            vec_in = g("Vector") if callable(g) else None
        if vec_in is not None and getattr(vec_in, "is_linked", False):
            ml = list(getattr(vec_in, "links", None) or [])
            if len(ml) == 1:
                tn = getattr(ml[0], "from_node", None)
                ts = getattr(ml[0], "from_socket", None)
                tn, ts = _peel_reroute(tn, ts)
                if getattr(tn, "type", None) == "TEX_COORD":
                    space = str(getattr(ts, "name", "UV") or "UV").strip().lower()
                else:
                    space = ("other", getattr(tn, "type", None))
            else:
                space = ("multi",)
        elif vec_in is not None:
            space = "unlinked"
        return ("mapping", mtype, loc, rot, scale, space)
    return ("other", vtype)


def _mix_side_tex_node(sock):
    """If Mix A/B is linked TEX_IMAGE Color (peel REROUTE), return that node else None."""
    if sock is None or not getattr(sock, "is_linked", False):
        return None
    links = list(getattr(sock, "links", None) or [])
    if len(links) != 1:
        return None
    fn = getattr(links[0], "from_node", None)
    fs = getattr(links[0], "from_socket", None)
    fn, fs = _peel_reroute(fn, fs)
    if getattr(fn, "type", None) != "TEX_IMAGE":
        return None
    sock_name = getattr(fs, "name", "Color") if fs is not None else "Color"
    if sock_name not in ("Color", "color"):
        return None
    return fn


def _try_fold_linked_constant_mix_side(sock, ctx: str):
    """Slice 2bg: if Mix A/B links to both-unlinked constant Mix, return folded RGB.

    Returns None when the side is not a Mix (TEX_IMAGE / Curves / etc. stay chain).
    Raises QuantTraceSyncError when the side is a nested Mix that is not
    constant-foldable (linked Fac/A/B, VECTOR, unsupported blend).
    """
    if sock is None or not getattr(sock, "is_linked", False):
        return None
    links = list(getattr(sock, "links", None) or [])
    if len(links) != 1:
        return None
    fn = getattr(links[0], "from_node", None)
    fs = getattr(links[0], "from_socket", None)
    fn, fs = _peel_reroute(fn, fs)
    ntype = getattr(fn, "type", None) if fn is not None else None
    if ntype not in ("MIX", "MIX_RGB"):
        return None
    if ntype == "MIX":
        data_type = str(getattr(fn, "data_type", "FLOAT") or "FLOAT")
        if data_type in ("VECTOR", "ROTATION"):
            raise QuantTraceSyncError(
                f"{ctx} Principled.Base Color Mix nested Mix data_type {data_type!r} "
                "refused (Slice 2bg: RGBA constant Mix fold only)"
            )
        if data_type == "FLOAT":
            raise QuantTraceSyncError(
                f"{ctx} Principled.Base Color Mix nested FLOAT Mix refused "
                "(Slice 2bg: RGBA constant Mix fold only)"
            )
        if data_type not in ("RGBA", "COLOR"):
            raise QuantTraceSyncError(
                f"{ctx} Principled.Base Color Mix nested Mix data_type {data_type!r} "
                "refused (Slice 2bg)"
            )
    fac_sock, a_sock, b_sock = _mix_input_socks(fn)
    a_l = bool(getattr(a_sock, "is_linked", False)) if a_sock is not None else False
    b_l = bool(getattr(b_sock, "is_linked", False)) if b_sock is not None else False
    fac_l = bool(getattr(fac_sock, "is_linked", False)) if fac_sock is not None else False
    if fac_l or a_l or b_l:
        raise QuantTraceSyncError(
            f"{ctx} Principled.Base Color Mix nested Mix not constant-foldable refused "
            "(Slice 2bg: both-unlinked constant Mix on A/B only; "
            "nested TEX_IMAGE/Curves/Fresnel Mix still refuse)"
        )
    return _fold_constant_mix_base_rgb(fn, ctx)


def _eval_rgb_curves_constant(node, rgb, ctx: str):
    """Evaluate ShaderNodeRGBCurve on a constant RGB (pack-time fold, Slice 2bg).

    Matches Blender CurveMapping channel then master I (identity R/G/B + I mid
    is the loft Material.003 shape). Fac unlinked blend: (1-fac)*in + fac*curved.
    """
    mapping = getattr(node, "mapping", None)
    if mapping is None:
        raise QuantTraceSyncError(
            f"{ctx} Principled.Base Color RGB Curves missing mapping (Slice 2bg)"
        )
    inputs = getattr(node, "inputs", None)
    fac_sock = None
    if inputs is not None:
        g = getattr(inputs, "get", None)
        if callable(g):
            fac_sock = g("Fac") or g("Factor")
        if fac_sock is None:
            fac_sock = _sock_ident_or_name(inputs, "Fac", "Factor")
    if fac_sock is not None and getattr(fac_sock, "is_linked", False):
        raise QuantTraceSyncError(
            f"{ctx} Principled.Base Color RGB Curves.Fac is linked refused "
            "(Slice 2bg: unlinked Fac only)"
        )
    fac = 1.0
    if fac_sock is not None and getattr(fac_sock, "default_value", None) is not None:
        fac = float(fac_sock.default_value)
    curves = list(getattr(mapping, "curves", None) or [])
    if len(curves) < 4:
        raise QuantTraceSyncError(
            f"{ctx} Principled.Base Color RGB Curves needs 4 curves (Slice 2bg)"
        )
    mapping.update()
    mapR, mapG, mapB, mapI = curves[0], curves[1], curves[2], curves[3]
    r = float(mapping.evaluate(mapR, float(rgb[0])))
    g = float(mapping.evaluate(mapG, float(rgb[1])))
    b = float(mapping.evaluate(mapB, float(rgb[2])))
    r = float(mapping.evaluate(mapI, r))
    g = float(mapping.evaluate(mapI, g))
    b = float(mapping.evaluate(mapI, b))
    curved = (r, g, b)
    if fac == 0.0:
        return (float(rgb[0]), float(rgb[1]), float(rgb[2]))
    if fac == 1.0:
        return curved
    return tuple((1.0 - fac) * float(rgb[i]) + fac * curved[i] for i in range(3))


def _constant_rgb_from_sock_or_link(sock, ctx: str):
    """Unlinked RGB / RGB node / both-unlinked constant Mix → RGB, else None.

    Raises when a nested Mix is present but not foldable (Slice 2bg).
    """
    if sock is None:
        return None
    if not getattr(sock, "is_linked", False):
        stype = getattr(sock, "type", None)
        dv = getattr(sock, "default_value", None)
        if stype == "RGBA" or (hasattr(dv, "__len__") and not isinstance(dv, (str, bytes))):
            return (float(dv[0]), float(dv[1]), float(dv[2]))
        try:
            v = float(dv) if dv is not None else 0.0
        except (TypeError, ValueError):
            return None
        return (v, v, v)
    links = list(getattr(sock, "links", None) or [])
    if len(links) != 1:
        return None
    fn = getattr(links[0], "from_node", None)
    fs = getattr(links[0], "from_socket", None)
    fn, fs = _peel_reroute(fn, fs)
    ntype = getattr(fn, "type", None) if fn is not None else None
    if ntype == "RGB":
        # ShaderNodeRGB: output Color default, or inputs[0]
        outs = getattr(fn, "outputs", None)
        if outs:
            ov = getattr(outs[0], "default_value", None)
            if ov is not None and hasattr(ov, "__len__"):
                return (float(ov[0]), float(ov[1]), float(ov[2]))
        return None
    if ntype in ("MIX", "MIX_RGB"):
        return _try_fold_linked_constant_mix_side(sock, ctx)
    return None


def _try_eval_linked_curves_constant_side(sock, ctx: str):
    """If sock ← CURVE_RGB Color with constant Color-in, return curved RGB else None.

    None when the side is not Curves (caller may treat as chain / TEX / etc.).
    Raises when Curves is present but Color-in is not constant-foldable.
    """
    if sock is None or not getattr(sock, "is_linked", False):
        return None
    links = list(getattr(sock, "links", None) or [])
    if len(links) != 1:
        return None
    fn = getattr(links[0], "from_node", None)
    fs = getattr(links[0], "from_socket", None)
    fn, fs = _peel_reroute(fn, fs)
    ntype = getattr(fn, "type", None) if fn is not None else None
    fsname = str(getattr(fs, "name", "") or "") if fs is not None else ""
    if ntype != "CURVE_RGB":
        return None
    if fsname not in ("Color", "color", ""):
        raise QuantTraceSyncError(
            f"{ctx} Principled.Base Color Mix Curves out {fsname!r} refused "
            "(Slice 2bg: Color out only)"
        )
    inputs = getattr(fn, "inputs", None)
    color_sock = None
    if inputs is not None:
        g = getattr(inputs, "get", None)
        if callable(g):
            color_sock = g("Color")
        if color_sock is None:
            color_sock = _sock_ident_or_name(inputs, "Color")
    cin = _constant_rgb_from_sock_or_link(color_sock, ctx)
    if cin is None:
        # Slice 2bh: TEX_IMAGE Color-in is packed as mix-side LUT, not folded.
        tex = _mix_side_tex_node(color_sock)
        if tex is not None:
            return None
        ntype_in = "?"
        if color_sock is not None and getattr(color_sock, "is_linked", False):
            cl = list(getattr(color_sock, "links", None) or [])
            if cl:
                cn = getattr(cl[0], "from_node", None)
                cs = getattr(cl[0], "from_socket", None)
                cn, cs = _peel_reroute(cn, cs)
                ntype_in = getattr(cn, "type", None) if cn is not None else "?"
        raise QuantTraceSyncError(
            f"{ctx} Principled.Base Color Mix Curves Color-in from {ntype_in!r} refused "
            "(Slice 2bh: constant fold is 2bg; TEX_IMAGE Color is mix-side LUT; "
            "Noise/GROUP/nested Mix/Invert Color-in still refuse)"
        )
    return _eval_rgb_curves_constant(fn, cin, ctx)


def _tex_color_out_sock(tex_node):
    """Color output socket of a TEX_IMAGE node."""
    outs = getattr(tex_node, "outputs", None)
    if outs is None:
        return None
    g = getattr(outs, "get", None)
    if callable(g):
        sock = g("Color")
        if sock is not None:
            return sock
    try:
        return outs[0]
    except (IndexError, TypeError, KeyError):
        return None


def _base_mix_curves_identity():
    """Slice 2bh identity — skip mix-side RGBCurvesNode (2ay/2bg bit-identical)."""
    return {
        "base_mix_curves": None,
        "base_mix_curves_n": 0,
        "base_mix_curves_min_x": 0.0,
        "base_mix_curves_max_x": 1.0,
        "base_mix_curves_fac": 1.0,
        "base_mix_curves_extrapolate": 1,
        "base_mix_curves_on_a": 1,
    }


def _try_pack_mix_side_curves_tex(sock, ctx: str):
    """If Mix A/B ← CURVE_RGB Color with TEX_IMAGE Color-in, return (tex, curves_dict).

    None when the side is not Curves, or Curves with constant Color-in (2bg fold).
    Raises named Slice 2bh for linked Fac, Noise/GROUP/nested Mix Color-in,
    Vector/Float Curve, non-Color out.
    Fac==0 packs n==0 so native skips (bare TEX_IMAGE on that Mix side).
    """
    if sock is None or not getattr(sock, "is_linked", False):
        return None
    links = list(getattr(sock, "links", None) or [])
    if len(links) != 1:
        return None
    fn = getattr(links[0], "from_node", None)
    fs = getattr(links[0], "from_socket", None)
    fn, fs = _peel_reroute(fn, fs)
    ntype = getattr(fn, "type", None) if fn is not None else None
    fsname = str(getattr(fs, "name", "") or "") if fs is not None else ""
    if ntype in ("CURVE_VEC", "CURVE_VECTOR", "CURVE_FLOAT"):
        raise QuantTraceSyncError(
            f"{ctx} Principled.Base Color Mix {ntype!r} on Mix side refused "
            "(Slice 2bh: ShaderNodeRGBCurve only; Vector/Float Curve still refuse)"
        )
    if ntype != "CURVE_RGB":
        return None
    if fsname not in ("Color", "color", ""):
        raise QuantTraceSyncError(
            f"{ctx} Principled.Base Color Mix Curves out {fsname!r} refused "
            "(Slice 2bh: Color out only)"
        )
    inputs = getattr(fn, "inputs", None)
    color_sock = None
    if inputs is not None:
        g = getattr(inputs, "get", None)
        if callable(g):
            color_sock = g("Color")
        if color_sock is None:
            color_sock = _sock_ident_or_name(inputs, "Color")
    # Constant Color-in Curves stay 2bg fold — not a mix-side LUT.
    cin = _constant_rgb_from_sock_or_link(color_sock, ctx)
    if cin is not None:
        return None
    tex = _mix_side_tex_node(color_sock)
    if tex is None:
        ntype_in = "?"
        if color_sock is not None and getattr(color_sock, "is_linked", False):
            cl = list(getattr(color_sock, "links", None) or [])
            if cl:
                cn = getattr(cl[0], "from_node", None)
                cs = getattr(cl[0], "from_socket", None)
                cn, cs = _peel_reroute(cn, cs)
                ntype_in = getattr(cn, "type", None) if cn is not None else "?"
        raise QuantTraceSyncError(
            f"{ctx} Principled.Base Color Mix Curves Color-in from {ntype_in!r} refused "
            "(Slice 2bh: TEX_IMAGE Color only; Noise/GROUP/nested Mix/Invert still refuse)"
        )
    packed = _pack_rgb_curves_lut(fn, ctx=ctx, slice_tag="2bh")
    ident = dict(_base_mix_curves_identity())
    if float(packed["fac"]) == 0.0:
        return tex, ident
    ident["base_mix_curves"] = packed["curves"]
    ident["base_mix_curves_n"] = packed["n"]
    ident["base_mix_curves_min_x"] = packed["min_x"]
    ident["base_mix_curves_max_x"] = packed["max_x"]
    ident["base_mix_curves_fac"] = packed["fac"]
    ident["base_mix_curves_extrapolate"] = packed["extrapolate"]
    return tex, ident


def _fold_constant_mix_rgb(mix_node, ctx: str, sock_label: str = "Base Color", slice_tag: str = "Slice 2ay"):
    """Fold both-unlinked constant Mix into RGB (prefer over Mix ABI)."""
    fac_sock, a_sock, b_sock = _mix_input_socks(mix_node)
    if fac_sock is None or a_sock is None or b_sock is None:
        raise QuantTraceSyncError(
            f"{ctx} Principled.{sock_label} constant Mix missing Fac/A/B ({slice_tag})"
        )
    if getattr(fac_sock, "is_linked", False):
        raise QuantTraceSyncError(
            f"{ctx} Principled.{sock_label} Mix Factor is linked refused ({slice_tag})"
        )
    op = str(getattr(mix_node, "blend_type", "MIX") or "MIX")
    if op not in _WORLD_STRENGTH_MIX_OPS:
        raise QuantTraceSyncError(
            f"{ctx} Principled.{sock_label} Mix blend_type {op!r} refused "
            f"({slice_tag}: MIX/ADD/SUBTRACT/MULTIPLY/DIVIDE only)"
        )
    fac = float(getattr(fac_sock, "default_value", 0.5) or 0.0)
    if bool(getattr(mix_node, "clamp_factor", False)):
        fac = min(1.0, max(0.0, fac))

    def _rgb(sock):
        stype = getattr(sock, "type", None)
        dv = getattr(sock, "default_value", None)
        if stype == "RGBA" or (hasattr(dv, "__len__") and not isinstance(dv, (str, bytes))):
            return (float(dv[0]), float(dv[1]), float(dv[2]))
        v = float(dv or 0.0)
        return (v, v, v)

    a = _rgb(a_sock)
    b = _rgb(b_sock)
    if op == "MIX":
        out = tuple((1.0 - fac) * a[i] + fac * b[i] for i in range(3))
    elif op == "ADD":
        out = tuple(a[i] + fac * b[i] for i in range(3))
    elif op == "SUBTRACT":
        out = tuple(a[i] - fac * b[i] for i in range(3))
    elif op == "MULTIPLY":
        out = tuple(a[i] * ((1.0 - fac) + fac * b[i]) for i in range(3))
    elif op == "DIVIDE":
        out = []
        for i in range(3):
            denom = (1.0 - fac) + fac * b[i]
            out.append(a[i] / denom if abs(denom) > 1e-12 else 0.0)
        out = tuple(out)
    else:
        raise QuantTraceSyncError(
            f"{ctx} Principled.{sock_label} Mix fold unsupported ({slice_tag})"
        )
    if bool(
        getattr(mix_node, "clamp_result", False)
        or getattr(mix_node, "use_clamp", False)
    ):
        out = tuple(min(1.0, max(0.0, c)) for c in out)
    return out


def _fold_constant_mix_base_rgb(mix_node, ctx: str):
    """Compat wrapper — Base Color constant Mix fold (Slice 2ay)."""
    return _fold_constant_mix_rgb(mix_node, ctx, "Base Color", "Slice 2ay")


def _spec_tint_mix_identity():
    """Slice 2bk identity — skip MixColorNode on Principled Specular Tint (2u bit-identical)."""
    return {
        "spec_tint_mix_type": 0,
        "spec_tint_mix_fac": 0.5,
        "spec_tint_mix_other": (0.0, 0.0, 0.0),
        "spec_tint_mix_chain_is_a": 1,
        "spec_tint_mix_clamp_factor": 0,
        "spec_tint_mix_clamp_result": 0,
        "spec_tint_mix_b_image_path": "",
        "spec_tint_mix_b_image_colorspace": "",
        "spec_tint_gamma": 1.0,
        "spec_tint_hsv_hue": 0.5,
        "spec_tint_hsv_sat": 1.0,
        "spec_tint_hsv_val": 1.0,
        "spec_tint_hsv_fac": 1.0,
    }


def _peel_spec_tint_mix(from_node, from_sock, ctx: str):
    """Peel Mix immediately on Principled Specular Tint (Slice 2bk).

    Slim reuse of Base Color Mix shapes (2ay): constant fold / one-side TEX +
    const / dual TEX_IMAGE. Fac linked (Fresnel/GROUP/Noise/…) and Curves-on-
    Mix-side named refuse Slice 2bk — loft Specular Tint census is constant-only
    Mix (Sideboard) plus Fac←GROUP (Botaniq pots).

    Returns (from_node, from_sock, mix_dict, dual_b_tex_or_None, folded_rgb_or_None).
    folded_rgb set when both-unlinked constant Mix (mix_type stays 0).
    """
    mix = dict(_spec_tint_mix_identity())
    from_node, from_sock = _peel_reroute(from_node, from_sock)
    ntype = getattr(from_node, "type", None) if from_node is not None else None
    if ntype not in ("MIX", "MIX_RGB"):
        return from_node, from_sock, mix, None, None
    if ntype == "MIX":
        data_type = str(getattr(from_node, "data_type", "FLOAT") or "FLOAT")
        if data_type in ("VECTOR", "ROTATION"):
            raise QuantTraceSyncError(
                f"{ctx} Principled.Specular Tint Mix data_type {data_type!r} refused "
                "(Slice 2bk: ShaderNodeMix RGBA / MixRGB only)"
            )
        if data_type == "FLOAT":
            return from_node, from_sock, mix, None, None
        if data_type not in ("RGBA", "COLOR"):
            raise QuantTraceSyncError(
                f"{ctx} Principled.Specular Tint Mix data_type {data_type!r} refused "
                "(Slice 2bk: RGBA / MixRGB only)"
            )
    op = str(getattr(from_node, "blend_type", "MIX") or "MIX")
    if op not in _WORLD_STRENGTH_MIX_OPS:
        raise QuantTraceSyncError(
            f"{ctx} Principled.Specular Tint Mix blend_type {op!r} refused "
            "(Slice 2bk: MIX/ADD/SUBTRACT/MULTIPLY/DIVIDE only)"
        )
    fac_sock, a_sock, b_sock = _mix_input_socks(from_node)
    if fac_sock is None:
        raise QuantTraceSyncError(
            f"{ctx} Principled.Specular Tint Mix missing Factor (Slice 2bk)"
        )
    if getattr(fac_sock, "is_linked", False):
        flinks = list(getattr(fac_sock, "links", None) or [])
        ftype = None
        if len(flinks) == 1:
            fnode = getattr(flinks[0], "from_node", None)
            fsock = getattr(flinks[0], "from_socket", None)
            fnode, fsock = _peel_reroute(fnode, fsock)
            ftype = getattr(fnode, "type", None) if fnode is not None else None
        raise QuantTraceSyncError(
            f"{ctx} Principled.Specular Tint Mix Factor from {ftype!r} refused "
            "(Slice 2bk: unlinked Fac only; Fresnel/GROUP/TEX_IMAGE/Noise/"
            "LayerWeight/Geometry/Invert still refuse)"
        )
    a_linked = bool(getattr(a_sock, "is_linked", False)) if a_sock is not None else False
    b_linked = bool(getattr(b_sock, "is_linked", False)) if b_sock is not None else False
    clamp_factor = bool(getattr(from_node, "clamp_factor", False))
    clamp_result = bool(
        getattr(from_node, "clamp_result", False)
        or getattr(from_node, "use_clamp", False)
    )
    fac = 0.5
    if getattr(fac_sock, "default_value", None) is not None:
        fac = float(fac_sock.default_value)
    if clamp_factor:
        fac = min(1.0, max(0.0, fac))

    if not a_linked and not b_linked:
        folded = _fold_constant_mix_rgb(from_node, ctx, "Specular Tint", "Slice 2bk")
        return None, None, mix, None, folded

    if a_linked and b_linked:
        tex_a = _mix_side_tex_node(a_sock)
        tex_b = _mix_side_tex_node(b_sock)
        if tex_a is not None and tex_b is not None:
            key_a = _tex_vector_source_key(tex_a)
            key_b = _tex_vector_source_key(tex_b)
            if key_a != key_b:
                raise QuantTraceSyncError(
                    f"{ctx} Principled.Specular Tint Mix dual TEX_IMAGE Vector graphs differ "
                    "(Slice 2bk: shared unlinked UV / same Mapping / same TEX_COORD only)"
                )
            mix["spec_tint_mix_type"] = int(_WORLD_MIX_TYPE_MAP[op])
            mix["spec_tint_mix_fac"] = float(fac)
            mix["spec_tint_mix_other"] = (0.0, 0.0, 0.0)
            mix["spec_tint_mix_chain_is_a"] = 1
            mix["spec_tint_mix_clamp_factor"] = 1 if clamp_factor else 0
            mix["spec_tint_mix_clamp_result"] = 1 if clamp_result else 0
            return tex_a, _tex_color_out_sock(tex_a), mix, tex_b, None
        raise QuantTraceSyncError(
            f"{ctx} Principled.Specular Tint Mix both sides linked refused "
            "(Slice 2bk: dual TEX_IMAGE Color or constant fold; "
            "Curves/Fresnel/nested Mix still refuse)"
        )

    chain_is_a = 1 if a_linked else 0
    other_sock = b_sock if a_linked else a_sock
    chain_sock = a_sock if a_linked else b_sock
    if other_sock is None or chain_sock is None:
        raise QuantTraceSyncError(
            f"{ctx} Principled.Specular Tint Mix missing A/B (Slice 2bk)"
        )
    links0 = list(getattr(chain_sock, "links", None) or [])
    if len(links0) == 1:
        cn = getattr(links0[0], "from_node", None)
        cs = getattr(links0[0], "from_socket", None)
        cn, cs = _peel_reroute(cn, cs)
        if getattr(cn, "type", None) == "CURVE_RGB":
            raise QuantTraceSyncError(
                f"{ctx} Principled.Specular Tint Mix Curves-on-Mix-side refused "
                "(Slice 2bk: TEX_IMAGE / constant only; Curves still refuse)"
            )
    stype = getattr(other_sock, "type", None)
    dv = getattr(other_sock, "default_value", None)
    if stype == "RGBA" or (hasattr(dv, "__len__") and not isinstance(dv, (str, bytes))):
        try:
            other = (float(dv[0]), float(dv[1]), float(dv[2]))
        except (TypeError, IndexError, ValueError) as e:
            raise QuantTraceSyncError(
                f"{ctx} Principled.Specular Tint Mix other side not constant RGB "
                "(Slice 2bk)"
            ) from e
    else:
        try:
            v = float(dv) if dv is not None else 0.0
        except (TypeError, ValueError) as e:
            raise QuantTraceSyncError(
                f"{ctx} Principled.Specular Tint Mix other side not constant "
                "(Slice 2bk)"
            ) from e
        other = (v, v, v)
    mix["spec_tint_mix_type"] = int(_WORLD_MIX_TYPE_MAP[op])
    mix["spec_tint_mix_fac"] = float(fac)
    mix["spec_tint_mix_other"] = other
    mix["spec_tint_mix_chain_is_a"] = int(chain_is_a)
    mix["spec_tint_mix_clamp_factor"] = 1 if clamp_factor else 0
    mix["spec_tint_mix_clamp_result"] = 1 if clamp_result else 0
    links = list(getattr(chain_sock, "links", None) or [])
    if len(links) != 1:
        raise QuantTraceSyncError(
            f"{ctx} Principled.Specular Tint Mix chain multi-link refused (Slice 2bk)"
        )
    fn = getattr(links[0], "from_node", None)
    fs = getattr(links[0], "from_socket", None)
    fn, fs = _peel_reroute(fn, fs)
    return fn, fs, mix, None, None



def _peel_spec_tint_gamma_hsv(from_node, from_sock, ctx: str):
    """Peel one unlinked Gamma + HueSat on Specular Tint chain (Slice 2bk).

    Returns (from_node, from_sock, unlinked_rgb_or_None, gh_dict).
    RGB Curves refuse. Always peel REROUTE first.
    """
    gh = {
        "spec_tint_gamma": 1.0,
        "spec_tint_hsv_hue": 0.5,
        "spec_tint_hsv_sat": 1.0,
        "spec_tint_hsv_val": 1.0,
        "spec_tint_hsv_fac": 1.0,
    }
    seen_gamma = False
    seen_hsv = False
    unlinked_rgb = None
    from_node, from_sock = _peel_reroute(from_node, from_sock)
    for _hop in range(3):
        ntype = getattr(from_node, "type", None) if from_node is not None else None
        if ntype == "GAMMA":
            if seen_gamma:
                raise QuantTraceSyncError(
                    f"{ctx} Principled.Specular Tint second Gamma refused (Slice 2bk)"
                )
            gh["spec_tint_gamma"] = _require_unlinked_float_mesh(
                from_node, ("Gamma",), "Gamma.Gamma", ctx
            )
            # Fix label in error by catching — _require says Base Color. Inline instead:
            seen_gamma = True
            from_node, from_sock, unlinked_rgb = _gamma_hsv_color_source_mesh(from_node, ctx)
            if unlinked_rgb is not None:
                break
            continue
        if ntype == "HUE_SAT":
            if seen_hsv:
                raise QuantTraceSyncError(
                    f"{ctx} Principled.Specular Tint second HueSat refused (Slice 2bk)"
                )
            gh["spec_tint_hsv_hue"] = _require_unlinked_float_mesh(
                from_node, ("Hue",), "HueSat.Hue", ctx
            )
            gh["spec_tint_hsv_sat"] = _require_unlinked_float_mesh(
                from_node, ("Saturation",), "HueSat.Saturation", ctx
            )
            gh["spec_tint_hsv_val"] = _require_unlinked_float_mesh(
                from_node, ("Value",), "HueSat.Value", ctx
            )
            gh["spec_tint_hsv_fac"] = _require_unlinked_float_mesh(
                from_node, ("Fac", "Factor"), "HueSat.Fac", ctx
            )
            seen_hsv = True
            from_node, from_sock, unlinked_rgb = _gamma_hsv_color_source_mesh(from_node, ctx)
            if unlinked_rgb is not None:
                break
            continue
        if ntype == "CURVE_RGB":
            raise QuantTraceSyncError(
                f"{ctx} Principled.Specular Tint RGB Curves refused "
                "(Slice 2bk: Gamma/HueSat only; Curves still refuse)"
            )
        break
    from_node, from_sock = _peel_reroute(from_node, from_sock)
    return from_node, from_sock, unlinked_rgb, gh

def _spec_tint_tex_and_mix(sock, *, object_name: str = "", mat=None):
    """Principled Specular Tint: peel REROUTE + Mix then TEX_IMAGE / constant fold.

    Returns (tex_info_with_mix, specular_tint_rgb).
    specular_tint_rgb is always a float3 (default 1,1,1 or fold / socket default).
    """
    ctx = _mat_refuse_ctx(object_name, mat)
    empty = _empty_tex_info()
    mix = dict(_spec_tint_mix_identity())
    default_tint = (1.0, 1.0, 1.0)
    if sock is not None and not getattr(sock, "is_linked", False):
        dv = getattr(sock, "default_value", None)
        if hasattr(dv, "__len__") and not isinstance(dv, (str, bytes)):
            try:
                default_tint = (float(dv[0]), float(dv[1]), float(dv[2]))
            except (TypeError, IndexError, ValueError):
                pass
        return {**empty, **mix}, default_tint
    if sock is None or not getattr(sock, "is_linked", False):
        return {**empty, **mix}, default_tint
    links = list(getattr(sock, "links", None) or [])
    if not links:
        return {**empty, **mix}, default_tint
    if len(links) != 1:
        raise QuantTraceSyncError(
            f"{ctx} Principled.Specular Tint has multiple links (Slice 2bk)"
        )
    from_node = getattr(links[0], "from_node", None)
    from_sock = getattr(links[0], "from_socket", None)
    from_node, from_sock = _peel_reroute(from_node, from_sock)
    from_node, from_sock, mix, dual_b, folded = _peel_spec_tint_mix(
        from_node, from_sock, ctx
    )
    if folded is not None:
        return {**empty, **mix}, folded
    # Slice 2bk: peel Gamma + HueSat on Mix chain (loft Sideboard:
    # TEX → Gamma → HueSat → Mix B). Reuse Base Color peel helpers with
    # Specular Tint labels; drop Curves (named refuse if present).
    ntype0 = getattr(from_node, "type", None) if from_node is not None else None
    if ntype0 in ("GAMMA", "HUE_SAT", "CURVE_RGB"):
        from_node, from_sock, unlinked_rgb, gh = _peel_spec_tint_gamma_hsv(
            from_node, from_sock, ctx
        )
        mix.update(gh)
        if unlinked_rgb is not None:
            # Constant under Gamma/HSV on Mix chain → fold into specular_tint via
            # Mix other/chain: treat as chain const by setting specular_tint and
            # keeping Mix (A/B const already peeled). For one-side Mix, chain const
            # means both sides constant after fold — recompute.
            if int(mix.get("spec_tint_mix_type", 0) or 0) != 0:
                # Chain was linked; now constant — fold Mix with other + this const.
                other = tuple(mix.get("spec_tint_mix_other") or (0.0, 0.0, 0.0))
                chain_is_a = int(mix.get("spec_tint_mix_chain_is_a", 1) or 1)
                fac = float(mix.get("spec_tint_mix_fac", 0.5))
                a = unlinked_rgb if chain_is_a else other
                b = other if chain_is_a else unlinked_rgb
                # Only MIX blend for this fold path (Sideboard).
                op_t = int(mix.get("spec_tint_mix_type", 1) or 1)
                if op_t == 1:  # MIX
                    folded2 = tuple((1.0 - fac) * a[i] + fac * b[i] for i in range(3))
                else:
                    raise QuantTraceSyncError(
                        f"{ctx} Principled.Specular Tint Mix constant-chain fold "
                        f"unsupported blend type {op_t} (Slice 2bk)"
                    )
                if int(mix.get("spec_tint_mix_clamp_result", 0) or 0):
                    folded2 = tuple(min(1.0, max(0.0, c)) for c in folded2)
                return {**empty, **_spec_tint_mix_identity()}, folded2
            return {**empty, **mix}, unlinked_rgb
    ntype = getattr(from_node, "type", None) if from_node is not None else None
    if (
        mix.get("spec_tint_mix_type", 0) == 0
        and dual_b is None
        and ntype in ("MIX", "MIX_RGB")
    ):
        raise QuantTraceSyncError(
            f"{ctx} Principled.Specular Tint from {ntype!r} refused "
            "(Slice 2bk: RGBA Mix chain / dual TEX_IMAGE / constant fold only)"
        )
    if ntype == "TEX_IMAGE":
        sock_name = getattr(from_sock, "name", "Color") if from_sock is not None else "Color"
        if sock_name not in ("Color", "color"):
            raise QuantTraceSyncError(
                f"{ctx} Principled.Specular Tint must come from Image Texture Color "
                f"(Slice 2bk; got {sock_name!r})"
            )
        tex = _tex_image_from_tex_node(from_node, from_sock, "Specular Tint", ctx)
        if dual_b is not None:
            img = getattr(dual_b, "image", None)
            if img is None:
                raise QuantTraceSyncError(
                    f"{ctx} Principled.Specular Tint Mix B TEX_IMAGE has no image "
                    "(Slice 2bk)"
                )
            path = _abspath_image(img)
            if not path:
                raise QuantTraceSyncError(
                    f"{ctx} Principled.Specular Tint Mix B TEX_IMAGE has no filepath "
                    "(Slice 2bk)"
                )
            cs = ""
            settings = getattr(img, "colorspace_settings", None)
            if settings is not None:
                cs = str(getattr(settings, "name", "") or "")
            mix["spec_tint_mix_b_image_path"] = path
            mix["spec_tint_mix_b_image_colorspace"] = cs
        return {**tex, **mix}, default_tint
    if ntype in ("MIX", "MIX_RGB"):
        raise QuantTraceSyncError(
            f"{ctx} Principled.Specular Tint from {ntype!r} refused "
            "(Slice 2bk: second Mix / unsupported Mix shape)"
        )
    raise QuantTraceSyncError(
        f"{ctx} Principled.Specular Tint link is not TEX_IMAGE "
        f"(Slice 2bk; got {ntype!r})"
    )



def _peel_base_color_mix(from_node, from_sock, ctx: str):
    """Peel Mix immediately on Principled Base Color (Slice 2ay / 2bf / 2bg).

    Returns (from_node, from_sock, mix_dict, dual_b_tex_node_or_None).
    Shape 1: exactly one of A/B linked = chain; other unlinked constant RGB.
    Shape 2: both linked TEX_IMAGE Color with matching Vector graphs; dual_b
    is the non-chain TEX_IMAGE node; chain side returned as from_node/from_sock.
    Shape 3 (Slice 2bg): both linked, but one side is both-unlinked constant Mix
    → fold that side to RGB so the outer Mix becomes one-side-linked (other side
    stays chain: TEX_IMAGE / Curves / Gamma…). Nested Mix with linked inputs refuse.
    Shape 4 (Slice 2bh): RGB Curves ← TEX_IMAGE Color on one Mix A/B side
    (other side const RGB or TEX_IMAGE). Mix-side LUT, not base_curves_*.
    Both-unlinked constants: leave Mix in place (fold later; mix_type stays 0).
    Linked Fac: Fresnel Factor (IOR+Normal unlinked) is Slice 2bf;
    other Fac sources / VECTOR / unsupported blend / both-linked non-fold refuse.
    """
    mix = dict(_base_mix_identity())
    from_node, from_sock = _peel_reroute(from_node, from_sock)
    ntype = getattr(from_node, "type", None) if from_node is not None else None
    if ntype not in ("MIX", "MIX_RGB"):
        return from_node, from_sock, mix, None
    if ntype == "MIX":
        data_type = str(getattr(from_node, "data_type", "FLOAT") or "FLOAT")
        if data_type in ("VECTOR", "ROTATION"):
            raise QuantTraceSyncError(
                f"{ctx} Principled.Base Color Mix data_type {data_type!r} refused "
                "(Slice 2ay: ShaderNodeMix RGBA / MixRGB only)"
            )
        if data_type == "FLOAT":
            # Constant FLOAT Mix may fold; leave for later classify.
            return from_node, from_sock, mix, None
        if data_type not in ("RGBA", "COLOR"):
            raise QuantTraceSyncError(
                f"{ctx} Principled.Base Color Mix data_type {data_type!r} refused "
                "(Slice 2ay: RGBA / MixRGB only)"
            )
    op = str(getattr(from_node, "blend_type", "MIX") or "MIX")
    if op not in _WORLD_STRENGTH_MIX_OPS:
        raise QuantTraceSyncError(
            f"{ctx} Principled.Base Color Mix blend_type {op!r} refused "
            "(Slice 2ay: MIX/ADD/SUBTRACT/MULTIPLY/DIVIDE only)"
        )
    fac_sock, a_sock, b_sock = _mix_input_socks(from_node)
    if fac_sock is None:
        raise QuantTraceSyncError(
            f"{ctx} Principled.Base Color Mix missing Factor (Slice 2ay)"
        )
    if getattr(fac_sock, "is_linked", False):
        flinks = list(getattr(fac_sock, "links", None) or [])
        if len(flinks) != 1:
            raise QuantTraceSyncError(
                f"{ctx} Principled.Base Color Mix Factor multi-link refused "
                "(Slice 2bf)"
            )
        fnode = getattr(flinks[0], "from_node", None)
        fsock = getattr(flinks[0], "from_socket", None)
        fnode, fsock = _peel_reroute(fnode, fsock)
        ftype = getattr(fnode, "type", None) if fnode is not None else None
        fsname = str(getattr(fsock, "name", "") or "") if fsock is not None else ""
        if ftype != "FRESNEL" or fsname not in ("Fac", "Factor", "fac"):
            raise QuantTraceSyncError(
                f"{ctx} Principled.Base Color Mix Factor from {ftype!r} refused "
                "(Slice 2bf: Fresnel Fac IOR+Normal unlinked only; "
                "TEX_IMAGE/Noise/LayerWeight/GROUP/Geometry/Invert still refuse)"
            )
        inputs_f = getattr(fnode, "inputs", None)
        ior_sock = None
        nrm_sock = None
        if inputs_f is not None:
            g = getattr(inputs_f, "get", None)
            if callable(g):
                ior_sock = g("IOR")
                nrm_sock = g("Normal")
        if ior_sock is not None and getattr(ior_sock, "is_linked", False):
            raise QuantTraceSyncError(
                f"{ctx} Principled.Base Color Mix Fresnel.IOR is linked refused "
                "(Slice 2bf)"
            )
        if nrm_sock is not None and getattr(nrm_sock, "is_linked", False):
            raise QuantTraceSyncError(
                f"{ctx} Principled.Base Color Mix Fresnel.Normal is linked refused "
                "(Slice 2bf: unlinked Normal only)"
            )
        ior = 1.45
        if ior_sock is not None and getattr(ior_sock, "default_value", None) is not None:
            ior = float(ior_sock.default_value)
        mix["base_mix_fresnel_enable"] = 1
        mix["base_mix_fresnel_ior"] = float(ior)
    a_linked = bool(getattr(a_sock, "is_linked", False)) if a_sock is not None else False
    b_linked = bool(getattr(b_sock, "is_linked", False)) if b_sock is not None else False
    if not a_linked and not b_linked:
        if int(mix.get("base_mix_fresnel_enable") or 0):
            raise QuantTraceSyncError(
                f"{ctx} Principled.Base Color Mix both sides unlinked with Fresnel Fac refused "
                "(Slice 2bf: chain or dual TEX_IMAGE)"
            )
        # Both unlinked constants → fold into base_color later (mix_type 0).
        return from_node, from_sock, mix, None
    clamp_factor = bool(getattr(from_node, "clamp_factor", False))
    clamp_result = bool(
        getattr(from_node, "clamp_result", False)
        or getattr(from_node, "use_clamp", False)
    )
    fac = float(getattr(fac_sock, "default_value", 0.5) or 0.0)
    # Do not use `or` on fac — 0.0 is valid.
    if getattr(fac_sock, "default_value", None) is not None:
        fac = float(fac_sock.default_value)
    if clamp_factor:
        fac = min(1.0, max(0.0, fac))

    if a_linked and b_linked:
        tex_a = _mix_side_tex_node(a_sock)
        tex_b = _mix_side_tex_node(b_sock)
        # Slice 2bh: RGB Curves ← TEX_IMAGE on one Mix side (loft Carpet:
        # A=TEX_IMAGE, B=Curves←same TEX, Fac←Fresnel). One LUT only.
        curv_tex_a = _try_pack_mix_side_curves_tex(a_sock, ctx)
        curv_tex_b = _try_pack_mix_side_curves_tex(b_sock, ctx)
        if curv_tex_a is not None and curv_tex_b is not None:
            raise QuantTraceSyncError(
                f"{ctx} Principled.Base Color Mix both sides RGB Curves←TEX_IMAGE refused "
                "(Slice 2bh: one mix-side LUT only)"
            )
        side_a = tex_a
        side_b = tex_b
        mix_curves = dict(_base_mix_curves_identity())
        if curv_tex_a is not None:
            side_a = curv_tex_a[0]
            mix_curves = dict(curv_tex_a[1])
            mix_curves["base_mix_curves_on_a"] = 1
        if curv_tex_b is not None:
            side_b = curv_tex_b[0]
            mix_curves = dict(curv_tex_b[1])
            mix_curves["base_mix_curves_on_a"] = 0
        if side_a is not None and side_b is not None:
            key_a = _tex_vector_source_key(side_a)
            key_b = _tex_vector_source_key(side_b)
            if key_a != key_b:
                raise QuantTraceSyncError(
                    f"{ctx} Principled.Base Color Mix dual TEX_IMAGE Vector graphs differ "
                    "(Slice 2ay: shared unlinked UV / same Mapping / same TEX_COORD only)"
                )
            # Primary chain = A (chain_is_a=1); B path = other image.
            mix["base_mix_type"] = int(_WORLD_MIX_TYPE_MAP[op])
            mix["base_mix_fac"] = float(fac)
            mix["base_mix_other"] = (0.0, 0.0, 0.0)
            mix["base_mix_chain_is_a"] = 1
            mix["base_mix_clamp_factor"] = 1 if clamp_factor else 0
            mix["base_mix_clamp_result"] = 1 if clamp_result else 0
            mix.update(mix_curves)
            # B image path filled by caller after packing side_b.
            return side_a, _tex_color_out_sock(side_a), mix, side_b
        # Slice 2bh: Curves←TEX on one side + constant on the other (folded Mix / Curves).
        # Slice 2bg: fold constant nested Mix and/or Curves(constant) on A/B.
        # Native mesh order is Color→Mix→Curves (2bd Concrete_Facade). Loft
        # Material.003 is Mix(const, Curves(const)) — fold Curves on constants
        # into Mix A/B so Factor←Fresnel stays correct (no new C++ ABI).
        fold_a = _try_fold_linked_constant_mix_side(a_sock, ctx)
        fold_b = _try_fold_linked_constant_mix_side(b_sock, ctx)
        curv_a = _try_eval_linked_curves_constant_side(a_sock, ctx)
        curv_b = _try_eval_linked_curves_constant_side(b_sock, ctx)
        const_a = fold_a if fold_a is not None else curv_a
        const_b = fold_b if fold_b is not None else curv_b
        if const_a is not None and const_b is not None:
            mix["base_mix_type"] = int(_WORLD_MIX_TYPE_MAP[op])
            mix["base_mix_fac"] = float(fac)
            mix["base_mix_other"] = const_b
            mix["base_mix_chain_is_a"] = 1
            mix["base_mix_clamp_factor"] = 1 if clamp_factor else 0
            mix["base_mix_clamp_result"] = 1 if clamp_result else 0
            # Chain constant rides base_color via caller (_chain_const_rgb).
            mix["_chain_const_rgb"] = const_a
            return None, None, mix, None
        if const_a is not None and const_b is None:
            # A constant; B is chain (TEX_IMAGE / Curves←TEX / Gamma…).
            mix["base_mix_type"] = int(_WORLD_MIX_TYPE_MAP[op])
            mix["base_mix_fac"] = float(fac)
            mix["base_mix_other"] = const_a
            mix["base_mix_chain_is_a"] = 0
            mix["base_mix_clamp_factor"] = 1 if clamp_factor else 0
            mix["base_mix_clamp_result"] = 1 if clamp_result else 0
            if curv_tex_b is not None:
                mix.update(curv_tex_b[1])
                mix["base_mix_curves_on_a"] = 0
                return curv_tex_b[0], _tex_color_out_sock(curv_tex_b[0]), mix, None
            links = list(getattr(b_sock, "links", None) or [])
            if len(links) != 1:
                raise QuantTraceSyncError(
                    f"{ctx} Principled.Base Color Mix chain multi-link refused "
                    "(Slice 2bg)"
                )
            fn = getattr(links[0], "from_node", None)
            fs = getattr(links[0], "from_socket", None)
            fn, fs = _peel_reroute(fn, fs)
            return fn, fs, mix, None
        if const_b is not None and const_a is None:
            mix["base_mix_type"] = int(_WORLD_MIX_TYPE_MAP[op])
            mix["base_mix_fac"] = float(fac)
            mix["base_mix_other"] = const_b
            mix["base_mix_chain_is_a"] = 1
            mix["base_mix_clamp_factor"] = 1 if clamp_factor else 0
            mix["base_mix_clamp_result"] = 1 if clamp_result else 0
            if curv_tex_a is not None:
                mix.update(curv_tex_a[1])
                mix["base_mix_curves_on_a"] = 1
                return curv_tex_a[0], _tex_color_out_sock(curv_tex_a[0]), mix, None
            links = list(getattr(a_sock, "links", None) or [])
            if len(links) != 1:
                raise QuantTraceSyncError(
                    f"{ctx} Principled.Base Color Mix chain multi-link refused "
                    "(Slice 2bg)"
                )
            fn = getattr(links[0], "from_node", None)
            fs = getattr(links[0], "from_socket", None)
            fn, fs = _peel_reroute(fn, fs)
            return fn, fs, mix, None
        # One side Curves←TEX, other neither const nor TEX (leftover).
        if curv_tex_a is not None or curv_tex_b is not None:
            raise QuantTraceSyncError(
                f"{ctx} Principled.Base Color Mix Curves←TEX_IMAGE other side refused "
                "(Slice 2bh: other Mix input const RGB or TEX_IMAGE Color only)"
            )
        raise QuantTraceSyncError(
            f"{ctx} Principled.Base Color Mix both sides linked refused "
            "(Slice 2bh: dual TEX_IMAGE Color, Curves←TEX_IMAGE on one Mix side, "
            "or constant nested Mix / Curves(constant) fold; nested non-constant Mix still refuse)"
        )

    # Exactly one side linked = chain; other must be unlinked constant RGB.
    chain_is_a = 1 if a_linked else 0
    other_sock = b_sock if a_linked else a_sock
    chain_sock = a_sock if a_linked else b_sock
    if other_sock is None or chain_sock is None:
        raise QuantTraceSyncError(
            f"{ctx} Principled.Base Color Mix missing A/B (Slice 2ay)"
        )
    stype = getattr(other_sock, "type", None)
    dv = getattr(other_sock, "default_value", None)
    if stype == "RGBA" or (hasattr(dv, "__len__") and not isinstance(dv, (str, bytes))):
        try:
            other = (float(dv[0]), float(dv[1]), float(dv[2]))
        except (TypeError, IndexError, ValueError) as e:
            raise QuantTraceSyncError(
                f"{ctx} Principled.Base Color Mix other side not constant RGB "
                "(Slice 2ay)"
            ) from e
    else:
        try:
            v = float(dv) if dv is not None else 0.0
        except (TypeError, ValueError) as e:
            raise QuantTraceSyncError(
                f"{ctx} Principled.Base Color Mix other side not constant "
                "(Slice 2ay)"
            ) from e
        other = (v, v, v)
    mix["base_mix_type"] = int(_WORLD_MIX_TYPE_MAP[op])
    mix["base_mix_fac"] = float(fac)
    mix["base_mix_other"] = other
    mix["base_mix_chain_is_a"] = int(chain_is_a)
    mix["base_mix_clamp_factor"] = 1 if clamp_factor else 0
    mix["base_mix_clamp_result"] = 1 if clamp_result else 0
    # Slice 2bh: chain is RGB Curves ← TEX_IMAGE (CLAIM: TEX→Curves→Mix A).
    # Pack mix-side LUT and peel Color-in as the chain (do not reuse 2bd
    # base_curves_* — that is Curves AFTER Mix).
    curv_tex = _try_pack_mix_side_curves_tex(chain_sock, ctx)
    if curv_tex is not None:
        mix.update(curv_tex[1])
        mix["base_mix_curves_on_a"] = int(chain_is_a)
        return curv_tex[0], _tex_color_out_sock(curv_tex[0]), mix, None
    links = list(getattr(chain_sock, "links", None) or [])
    if len(links) != 1:
        raise QuantTraceSyncError(
            f"{ctx} Principled.Base Color Mix chain multi-link refused (Slice 2ay)"
        )
    fn = getattr(links[0], "from_node", None)
    fs = getattr(links[0], "from_socket", None)
    fn, fs = _peel_reroute(fn, fs)
    return fn, fs, mix, None


def _peel_reroute(from_node, from_sock):
    """Follow REROUTE until the real source (no ABI; loft uses REROUTE freely)."""
    for _ in range(64):
        ntype = getattr(from_node, "type", None) if from_node is not None else None
        if ntype != "REROUTE":
            return from_node, from_sock
        inputs = getattr(from_node, "inputs", None)
        if inputs is None or len(inputs) < 1:
            return from_node, from_sock
        rin = inputs[0]
        if not getattr(rin, "is_linked", False):
            return from_node, from_sock
        links = list(getattr(rin, "links", None) or [])
        if len(links) != 1:
            return from_node, from_sock
        from_node = getattr(links[0], "from_node", None)
        from_sock = getattr(links[0], "from_socket", None)
    return from_node, from_sock


def _mat_refuse_ctx(object_name: str, mat) -> str:
    mat_name = getattr(mat, "name", "") if mat is not None else ""
    ob = object_name or "?"
    mn = mat_name or "?"
    return f"object={ob!r} material={mn!r}"


def _require_unlinked_float_mesh(node, names, label: str, ctx: str) -> float:
    """Unlinked float for Base Color Gamma/HueSat. None-check — never `or` (hue 0 valid)."""
    inputs = getattr(node, "inputs", None)
    if inputs is None:
        raise QuantTraceSyncError(
            f"{ctx} Principled.Base Color {label} has no inputs (Slice 2ax)"
        )
    sock = _sock_ident_or_name(inputs, *names)
    if sock is None:
        raise QuantTraceSyncError(
            f"{ctx} Principled.Base Color {label} missing (Slice 2ax)"
        )
    if getattr(sock, "is_linked", False):
        raise QuantTraceSyncError(
            f"{ctx} Principled.Base Color {label} is linked refused "
            f"(Slice 2ax: texture-driven Gamma/Hue/Sat/Value/Fac still refuse)"
        )
    v = getattr(sock, "default_value", None)
    if v is None:
        raise QuantTraceSyncError(
            f"{ctx} Principled.Base Color {label} has no default_value (Slice 2ax)"
        )
    return float(v)


def _gamma_hsv_color_source_mesh(node, ctx: str):
    """Color input of Gamma/HueSat: (from_node, from_sock, unlinked_rgb_or_None)."""
    inputs = getattr(node, "inputs", None)
    if inputs is None:
        raise QuantTraceSyncError(
            f"{ctx} Principled.Base Color Gamma/HueSat has no inputs (Slice 2ax)"
        )
    color_in = _sock_ident_or_name(inputs, "Color")
    if color_in is None:
        raise QuantTraceSyncError(
            f"{ctx} Principled.Base Color Gamma/HueSat missing Color (Slice 2ax)"
        )
    if not getattr(color_in, "is_linked", False):
        col = getattr(color_in, "default_value", (0.8, 0.8, 0.8, 1.0))
        rgb = (float(col[0]), float(col[1]), float(col[2]))
        return None, None, rgb
    links = list(getattr(color_in, "links", None) or [])
    if len(links) != 1:
        raise QuantTraceSyncError(
            f"{ctx} Principled.Base Color Gamma/HueSat Color multi-link refused "
            f"(Slice 2ax)"
        )
    fn = getattr(links[0], "from_node", None)
    fs = getattr(links[0], "from_socket", None)
    fn, fs = _peel_reroute(fn, fs)
    return fn, fs, None


def _peel_base_color_gamma_hsv(from_node, from_sock, ctx: str):
    """Peel one unlinked Gamma + HueSat + RGB Curves on Principled Base Color (≤3 hops).

    Returns (from_node, from_sock, unlinked_rgb_or_None, gamma_hsv_dict, curves_dict).
    Mix remaining after Curves is left for the caller (loft Concrete_Facade:
    Mix → Curves → Principled). Mix after Gamma/HueSat with no Curves still
    refuses Slice 2ay. Noise / second Gamma/HueSat/Curves / Vector/Float Curve
    refuse. Always peel REROUTE before classifying.
    """
    gh = dict(_base_gamma_hsv_identity())
    curves = dict(_base_curves_identity())
    seen_gamma = False
    seen_hsv = False
    seen_curves = False
    unlinked_rgb = None
    from_node, from_sock = _peel_reroute(from_node, from_sock)
    for _hop in range(3):
        ntype = getattr(from_node, "type", None) if from_node is not None else None
        if ntype == "GAMMA":
            if seen_gamma:
                raise QuantTraceSyncError(
                    f"{ctx} Principled.Base Color second Gamma refused (Slice 2ax)"
                )
            gh["base_gamma"] = _require_unlinked_float_mesh(
                from_node, ("Gamma",), "Gamma.Gamma", ctx
            )
            seen_gamma = True
            from_node, from_sock, unlinked_rgb = _gamma_hsv_color_source_mesh(
                from_node, ctx
            )
            if unlinked_rgb is not None:
                break
            continue
        if ntype == "HUE_SAT":
            if seen_hsv:
                raise QuantTraceSyncError(
                    f"{ctx} Principled.Base Color second HueSat refused (Slice 2ax)"
                )
            gh["base_hsv_hue"] = _require_unlinked_float_mesh(
                from_node, ("Hue",), "HueSat.Hue", ctx
            )
            gh["base_hsv_sat"] = _require_unlinked_float_mesh(
                from_node, ("Saturation",), "HueSat.Saturation", ctx
            )
            gh["base_hsv_val"] = _require_unlinked_float_mesh(
                from_node, ("Value",), "HueSat.Value", ctx
            )
            gh["base_hsv_fac"] = _require_unlinked_float_mesh(
                from_node, ("Fac", "Factor"), "HueSat.Fac", ctx
            )
            seen_hsv = True
            from_node, from_sock, unlinked_rgb = _gamma_hsv_color_source_mesh(
                from_node, ctx
            )
            if unlinked_rgb is not None:
                break
            continue
        if ntype == "CURVE_RGB":
            if seen_curves:
                raise QuantTraceSyncError(
                    f"{ctx} Principled.Base Color second RGB Curves refused "
                    "(Slice 2bd)"
                )
            packed = _pack_base_rgb_curves_lut(from_node, ctx)
            # Fac==0: Cycles folds — keep n==0 so native skips (bit-identical).
            if float(packed["base_curves_fac"]) == 0.0:
                packed = dict(_base_curves_identity())
                packed["base_curves_fac"] = 0.0
            curves.update(packed)
            seen_curves = True
            from_node, from_sock, unlinked_rgb = _gamma_hsv_color_source_mesh(
                from_node, ctx
            )
            if unlinked_rgb is not None:
                break
            continue
        if ntype in ("CURVE_VEC", "CURVE_VECTOR", "CURVE_FLOAT"):
            raise QuantTraceSyncError(
                f"{ctx} Principled.Base Color from {ntype!r} refused "
                "(Slice 2bd: ShaderNodeRGBCurve only; Vector/Float Curve still refuse)"
            )
        break
    from_node, from_sock = _peel_reroute(from_node, from_sock)
    ntype = getattr(from_node, "type", None) if from_node is not None else None
    if ntype in ("MIX", "MIX_RGB"):
        # Loft Concrete_Facade: Mix is Color-in of Curves — leave for caller.
        if int(curves.get("base_curves_n", 0) or 0) == 0:
            raise QuantTraceSyncError(
                f"{ctx} Principled.Base Color from {ntype!r} refused "
                f"(Slice 2ay: unsupported Mix after Gamma/HueSat peel)"
            )
    if ntype in ("TEX_NOISE", "NOISE"):
        raise QuantTraceSyncError(
            f"{ctx} Principled.Base Color Noise refused (Slice 2bd)"
        )
    if ntype in ("CURVE_VEC", "CURVE_VECTOR", "CURVE_FLOAT"):
        raise QuantTraceSyncError(
            f"{ctx} Principled.Base Color from {ntype!r} refused "
            "(Slice 2bd: ShaderNodeRGBCurve only)"
        )
    if ntype == "CURVE_RGB":
        raise QuantTraceSyncError(
            f"{ctx} Principled.Base Color RGB Curves hop refused "
            "(Slice 2bd: ≤3 hops; second Curves or Curves beyond Gamma/HSV chain)"
        )
    return from_node, from_sock, unlinked_rgb, gh, curves


def _base_color_tex_and_gh(sock, *, object_name: str = "", mat=None):
    """Principled Base Color: peel REROUTE + Mix + Curves + Gamma/HueSat then TEX_IMAGE/constant.

    Returns (tex_info_with_mix_and_curves, gamma_hsv_dict, base_color_rgb_or_None).
    Mix peel (Slice 2ay) runs first if Mix is immediate, then Curves/Gamma/HSV
    (Slice 2bd/2ax). If Curves Color-in is Mix (loft Concrete_Facade), Mix is
    peeled after Curves. tex_info carries base_mix_* and base_curves_*.
    """
    ctx = _mat_refuse_ctx(object_name, mat)
    empty = _empty_tex_info()
    gh = dict(_base_gamma_hsv_identity())
    mix = dict(_base_mix_identity())
    curves = dict(_base_curves_identity())
    ident = {**empty, **mix, **curves}
    if sock is None or not getattr(sock, "is_linked", False):
        return ident, gh, None
    links = list(getattr(sock, "links", None) or [])
    if not links:
        return ident, gh, None
    if len(links) != 1:
        raise QuantTraceSyncError(
            f"{ctx} Principled.Base Color has multiple links (Slice 2bd)"
        )
    from_node = getattr(links[0], "from_node", None)
    from_sock = getattr(links[0], "from_socket", None)
    from_node, from_sock = _peel_reroute(from_node, from_sock)
    from_node, from_sock, mix, dual_b = _peel_base_color_mix(from_node, from_sock, ctx)
    # Slice 2bg: dual-constant Mix (nested Mix / Curves fold) → base_color chain.
    chain_const = mix.pop("_chain_const_rgb", None)
    if chain_const is not None:
        return {**empty, **mix, **curves}, gh, chain_const
    # Both-unlinked constant Mix left in place — fold now (mix_type stays 0).
    ntype0 = getattr(from_node, "type", None) if from_node is not None else None
    if (
        mix.get("base_mix_type", 0) == 0
        and dual_b is None
        and ntype0 in ("MIX", "MIX_RGB")
    ):
        fac_sock, a_sock, b_sock = _mix_input_socks(from_node)
        a_l = bool(getattr(a_sock, "is_linked", False)) if a_sock is not None else False
        b_l = bool(getattr(b_sock, "is_linked", False)) if b_sock is not None else False
        if not a_l and not b_l:
            folded = _fold_constant_mix_base_rgb(from_node, ctx)
            return {**empty, **mix, **curves}, gh, folded
        # FLOAT Mix or other leftover — refuse named 2ay.
        raise QuantTraceSyncError(
            f"{ctx} Principled.Base Color from {ntype0!r} refused "
            f"(Slice 2ay: RGBA Mix chain / dual TEX_IMAGE / constant fold only)"
        )
    from_node, from_sock, unlinked_rgb, gh, curves = _peel_base_color_gamma_hsv(
        from_node, from_sock, ctx
    )
    # Loft Concrete_Facade: remaining Mix is Color-in of Curves.
    ntype_m = getattr(from_node, "type", None) if from_node is not None else None
    if (
        mix.get("base_mix_type", 0) == 0
        and dual_b is None
        and ntype_m in ("MIX", "MIX_RGB")
        and int(curves.get("base_curves_n", 0) or 0) > 0
    ):
        from_node, from_sock, mix, dual_b = _peel_base_color_mix(
            from_node, from_sock, ctx
        )
        ntype_m = getattr(from_node, "type", None) if from_node is not None else None
        if (
            mix.get("base_mix_type", 0) == 0
            and dual_b is None
            and ntype_m in ("MIX", "MIX_RGB")
        ):
            fac_sock, a_sock, b_sock = _mix_input_socks(from_node)
            a_l = bool(getattr(a_sock, "is_linked", False)) if a_sock is not None else False
            b_l = bool(getattr(b_sock, "is_linked", False)) if b_sock is not None else False
            if not a_l and not b_l:
                folded = _fold_constant_mix_base_rgb(from_node, ctx)
                return {**empty, **mix, **curves}, gh, folded
            raise QuantTraceSyncError(
                f"{ctx} Principled.Base Color from {ntype_m!r} refused "
                f"(Slice 2bd: Mix Color-in of RGB Curves must be RGBA chain / dual TEX_IMAGE)"
            )
        # Mix peel walked to TEX/constant; re-peel Gamma/HSV on remaining if needed.
        if unlinked_rgb is None:
            from_node, from_sock, unlinked_rgb, gh2, curves2 = _peel_base_color_gamma_hsv(
                from_node, from_sock, ctx
            )
            # Keep already-packed curves (second peel must not find another Curves).
            if int(curves2.get("base_curves_n", 0) or 0) > 0:
                raise QuantTraceSyncError(
                    f"{ctx} Principled.Base Color second RGB Curves refused (Slice 2bd)"
                )
            if gh2.get("base_gamma") != 1.0 or gh2.get("base_hsv_hue") != 0.5:
                gh = gh2
    if unlinked_rgb is not None:
        return {**empty, **mix, **curves}, gh, unlinked_rgb
    ntype = getattr(from_node, "type", None) if from_node is not None else None
    if ntype == "TEX_IMAGE":
        sock_name = getattr(from_sock, "name", "Color") if from_sock is not None else "Color"
        if sock_name not in ("Color", "color"):
            raise QuantTraceSyncError(
                f"{ctx} Principled.Base Color must come from Image Texture Color "
                f"(Slice 2bd; got {sock_name!r})"
            )
        tex = _tex_image_from_tex_node(from_node, from_sock, "Base Color", ctx)
        if dual_b is not None:
            img = getattr(dual_b, "image", None)
            if img is None:
                raise QuantTraceSyncError(
                    f"{ctx} Principled.Base Color Mix B TEX_IMAGE has no image "
                    "(Slice 2ay)"
                )
            path = _abspath_image(img)
            if not path:
                raise QuantTraceSyncError(
                    f"{ctx} Principled.Base Color Mix B TEX_IMAGE has no filepath "
                    "(Slice 2ay)"
                )
            cs = ""
            settings = getattr(img, "colorspace_settings", None)
            if settings is not None:
                cs = str(getattr(settings, "name", "") or "")
            mix["base_mix_b_image_path"] = path
            mix["base_mix_b_image_colorspace"] = cs
        return {**tex, **mix, **curves}, gh, None
    if ntype in ("MIX", "MIX_RGB"):
        raise QuantTraceSyncError(
            f"{ctx} Principled.Base Color from {ntype!r} refused "
            f"(Slice 2ay: second Mix / unsupported Mix shape)"
        )
    if ntype in ("TEX_NOISE", "NOISE"):
        raise QuantTraceSyncError(
            f"{ctx} Principled.Base Color Noise refused (Slice 2bd)"
        )
    raise QuantTraceSyncError(
        f"{ctx} Principled.Base Color from {ntype!r} refused "
        f"(Slice 2bd: TEX_IMAGE / Mix / unlinked Gamma/HueSat / RGB Curves / constant only)"
    )


def _tex_image_from_tex_node(from_node, from_sock, sock_label: str, ctx: str = ""):
    """Pack TEX_IMAGE node already resolved (after REROUTE/Gamma/HueSat peel)."""
    # Delegate to _tex_image_from_sock by synthesizing a sock-like with one link.
    class _L:
        pass
    class _S:
        pass
    link = _L()
    link.from_node = from_node
    link.from_sock = from_sock
    sock = _S()
    sock.links = [link]
    try:
        return _tex_image_from_sock(sock, sock_label)
    except QuantTraceSyncError as e:
        msg = str(e)
        if ctx and not msg.startswith(ctx):
            raise QuantTraceSyncError(f"{ctx} {msg}") from e
        raise



def _peel_surface_reroute(node):
    """Peel REROUTE chain from Material Output Surface (Slice 2bm)."""
    for _ in range(64):
        if node is None or getattr(node, "type", None) != "REROUTE":
            return node
        inputs = getattr(node, "inputs", None)
        if not inputs or not inputs[0].is_linked:
            return node
        links = list(inputs[0].links or [])
        if len(links) != 1:
            return node
        node = links[0].from_node
    return node


def _material_surface_root(mat):
    """Material Output ← Surface peeled root node, or None."""
    if mat is None or not getattr(mat, "use_nodes", False) or mat.node_tree is None:
        return None
    out = None
    for n in mat.node_tree.nodes:
        if getattr(n, "type", None) == "OUTPUT_MATERIAL":
            out = n
            break
    if out is None:
        return None
    surf = out.inputs.get("Surface") if getattr(out, "inputs", None) else None
    if surf is None or not getattr(surf, "is_linked", False):
        return None
    links = list(surf.links or [])
    if len(links) != 1:
        return None
    return _peel_surface_reroute(links[0].from_node)


def _glass_distribution_code(glass_node) -> int:
    """Blender Glass distribution → ABI int (0 Beckmann / 1 GGX / 2 Multi-GGX)."""
    dist = str(getattr(glass_node, "distribution", "") or "").upper()
    if dist in ("GGX",):
        return 1
    if dist in ("MULTI_GGX", "MULTIGGX", "MULTI-GGX"):
        return 2
    # BECKMANN / SHARP (legacy) / unknown → Beckmann (loft Glass_02)
    return 0


def _glass_from_material(mat, *, object_name: str = "") -> dict:
    """Map pure ShaderNodeBsdfGlass → Material Output into Principled-shaped dict.

    Principled transmission is NOT stock-parity with GlassBsdfNode (HDR cube
    Δmax ~0.15), so packer sets glass_bsdf_enable=1 and native emits
    GlassBsdfNode. Color/Roughness/IOR reuse base_color/roughness/ior.
    Linked Color/Roughness/IOR/Normal/Thin Film refuse (Slice 2bm).
    Mix Shader / nested Light Path glass refuse (Slice 2bm follow-up).
    """
    ctx = _mat_refuse_ctx(object_name, mat)
    root = _material_surface_root(mat)
    if root is None:
        raise QuantTraceSyncError(
            f"{ctx} material has no Principled BSDF (Slice 2b); "
            f"Surface unlinked/missing refused (Slice 2bm)"
        )
    rtype = getattr(root, "type", None)
    if rtype == "MIX_SHADER":
        raise QuantTraceSyncError(
            f"{ctx} material Surface Mix Shader refused "
            f"(Slice 2bm: pure Glass BSDF → Output only; "
            f"nested Light Path / Mix glass is a follow-up)"
        )
    if rtype != "BSDF_GLASS":
        raise QuantTraceSyncError(
            f"{ctx} material has no Principled BSDF (Slice 2b); "
            f"Surface={rtype!r} refused (Slice 2bm: pure Glass BSDF → Output only)"
        )
    # Refuse linked sockets — this slice is constant Glass only (Glass_02 shape).
    for label, names in (
        ("Color", ("Color",)),
        ("Roughness", ("Roughness",)),
        ("IOR", ("IOR",)),
        ("Normal", ("Normal",)),
        ("Thin Film Thickness", ("Thin Film Thickness",)),
        ("Thin Film IOR", ("Thin Film IOR",)),
    ):
        _n, sock = _input_by_names(root, *names)
        if sock is not None and getattr(sock, "is_linked", False):
            raise QuantTraceSyncError(
                f"{ctx} Glass BSDF.{label} is linked refused "
                f"(Slice 2bm: unlinked Color/Roughness/IOR/Normal only)"
            )
    col_sock = root.inputs.get("Color")
    rough_sock = root.inputs.get("Roughness")
    ior_sock = root.inputs.get("IOR")
    if col_sock is None or rough_sock is None or ior_sock is None:
        raise QuantTraceSyncError(
            f"{ctx} Glass BSDF missing Color/Roughness/IOR (Slice 2bm)"
        )
    col = col_sock.default_value
    base = (float(col[0]), float(col[1]), float(col[2]))
    rough = float(rough_sock.default_value)
    ior = float(ior_sock.default_value)
    dist = _glass_distribution_code(root)
    # Start from the same empty Principled-shaped dict as no-nodes materials.
    empty = {
        "base_color": base,
        "roughness": rough,
        "metallic": 0.0,
        "ior": ior,
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
        **_spec_tint_mix_identity(),
        "specular_tint": (1.0, 1.0, 1.0),
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
        **_empty_bevel_info(),
        **_empty_rough_ramp_info(),
        "thin_wall": 0,
        "transmission_weight": 0.0,
        "tex_ob_ref": None,
        **_base_gamma_hsv_identity(),
        **_base_mix_identity(),
        **_base_curves_identity(),
        "glass_bsdf_enable": 1,
        "glass_distribution": int(dist),
    }
    return empty


def _principled_from_material(mat, *, object_name: str = "") -> dict:
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
        **_spec_tint_mix_identity(),
        "specular_tint": (1.0, 1.0, 1.0),
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
        **_empty_bevel_info(),
        **_empty_rough_ramp_info(),
        "thin_wall": 0,
        "transmission_weight": 0.0,
        "tex_ob_ref": None,
        **_base_gamma_hsv_identity(),
        **_base_mix_identity(),
        **_base_curves_identity(),
        "glass_bsdf_enable": 0,
        "glass_distribution": 0,
    }
    if mat is None:
        raise QuantTraceSyncError(
            f"{_mat_refuse_ctx(object_name, mat)} mesh has no material"
        )
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
        # Slice 2bm: pure Glass BSDF → Output maps via glass_bsdf_enable.
        return _glass_from_material(mat, object_name=object_name)
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
    # Slice 2ax: Base Color peels REROUTE + Gamma/HueSat then TEX_IMAGE/constant.
    _bc_name, base_sock = _input_by_names(bsdf, "Base Color")
    base_tex, base_gh, peeled_rgb = _base_color_tex_and_gh(
        base_sock, object_name=object_name, mat=mat
    )
    # Slice 2ba/2bb/2be: Roughness peels REROUTE then Invert then ColorRamp
    # (Fac unlinked / TEX_IMAGE / TEX_NOISE) or TEX_IMAGE.
    _rname, rough_sock = _input_by_names(bsdf, "Roughness")
    roughness_folded = None
    if rough_sock is not None and getattr(rough_sock, "is_linked", False):
        rough_tex, rough_ramp = _roughness_tex_and_ramp(
            rough_sock, object_name=object_name, mat=mat
        )
        roughness_folded = rough_ramp.pop("roughness_folded", None)
    else:
        rough_ramp = _empty_rough_ramp_info()
    # Slice 2bk: Specular Tint peels REROUTE + Mix then TEX_IMAGE / constant fold.
    _st_name, spec_tint_sock = _input_by_names(bsdf, "Specular Tint")
    spec_tint_tex, specular_tint_rgb = _spec_tint_tex_and_mix(
        spec_tint_sock, object_name=object_name, mat=mat
    )
    # 5.x names first; legacy Transmission / Specular / Coat / Sheen / Emission accepted.
    # Base Color handled above (2ax) — do not call TEX_IMAGE-only packer on it.
    # Roughness handled above (2ba) — do not call TEX_IMAGE-only packer on it.
    allowed = (
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
        if kind == "metal":
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
    if peeled_rgb is not None:
        base_rgb = peeled_rgb
    else:
        base = bsdf.inputs["Base Color"].default_value
        base_rgb = (float(base[0]), float(base[1]), float(base[2]))
    return {
        "base_color": base_rgb,
        "roughness": (
            float(roughness_folded)
            if roughness_folded is not None
            else float(bsdf.inputs["Roughness"].default_value)
        ),
        "metallic": float(bsdf.inputs["Metallic"].default_value),
        "ior": float(bsdf.inputs["IOR"].default_value),
        "alpha": float(bsdf.inputs["Alpha"].default_value),
        **base_tex,
        **base_gh,
        **_prefix_tex(rough_tex, "rough_"),
        **rough_ramp,
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
        **{
            k: v for k, v in spec_tint_tex.items()
            if str(k).startswith("spec_tint_mix_")
            or str(k) in (
                "spec_tint_gamma", "spec_tint_hsv_hue", "spec_tint_hsv_sat",
                "spec_tint_hsv_val", "spec_tint_hsv_fac",
            )
        },
        "specular_tint": specular_tint_rgb,
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
        "glass_bsdf_enable": 0,
        "glass_distribution": 0,
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
_WORLD_STRENGTH_MIX_OPS = frozenset(
    {"MIX", "ADD", "SUBTRACT", "MULTIPLY", "DIVIDE"}
)
_WORLD_STRENGTH_FOLD_MAX_DEPTH = 3  # Slice 2at: 3-deep Math nest; 2ai was 2


def _color_to_float(val) -> float:
    """Cycles NODE_CONVERT_CF: average RGB (Strength is a float)."""
    if val is None:
        return 0.0
    try:
        return (float(val[0]) + float(val[1]) + float(val[2])) / 3.0
    except (TypeError, IndexError, ValueError):
        try:
            return float(val or 0.0)
        except (TypeError, ValueError):
            return 0.0


def _sock_default_as_float(sock) -> float:
    dv = getattr(sock, "default_value", 0.0)
    stype = getattr(sock, "type", None)
    if stype in ("RGBA", "VECTOR"):
        return _color_to_float(dv)
    try:
        return float(dv or 0.0)
    except (TypeError, ValueError):
        return _color_to_float(dv)


def _mix_blend_float(op: str, fac: float, a: float, b: float) -> float:
    """Cycles svm_mix_* on scalars (fac already clamp_factor'd)."""
    if op == "MIX":
        return a * (1.0 - fac) + b * fac
    if op == "ADD":
        return a + fac * b
    if op == "SUBTRACT":
        return a - fac * b
    if op == "MULTIPLY":
        return a * (1.0 - fac + fac * b)
    denom = 1.0 - fac + fac * b
    if abs(denom) < 1e-12:
        raise QuantTraceSyncError(
            "world Background Strength Mix DIVIDE by zero refused (Slice 2aj)"
        )
    return a / denom


def _world_strength_const_input(sock, label: str, *, depth: int) -> float:
    """Resolve a Strength-graph socket to a constant float (2ah/2ai/2aj)."""
    if sock is None:
        raise QuantTraceSyncError(f"{label} missing (Slice 2aj)")
    if not getattr(sock, "is_linked", False):
        return _sock_default_as_float(sock)
    links = list(getattr(sock, "links", None) or [])
    if len(links) != 1:
        raise QuantTraceSyncError(f"{label} multi-link refused (Slice 2aj)")
    from_node = getattr(links[0], "from_node", None)
    from_sock = getattr(links[0], "from_socket", None)
    ntype = getattr(from_node, "type", None) if from_node is not None else None
    if ntype == "VALUE":
        if from_sock is None:
            raise QuantTraceSyncError(
                f"{label} Value link has no from_socket (Slice 2ah)"
            )
        return float(getattr(from_sock, "default_value", 0.0) or 0.0)
    if ntype == "RGB":
        if from_sock is None:
            raise QuantTraceSyncError(
                f"{label} RGB link has no from_socket (Slice 2aj)"
            )
        return _color_to_float(getattr(from_sock, "default_value", None))
    if ntype == "MATH":
        if depth >= _WORLD_STRENGTH_FOLD_MAX_DEPTH:
            raise QuantTraceSyncError(
                f"{label} Math nest too deep (Slice 2at max "
                f"{_WORLD_STRENGTH_FOLD_MAX_DEPTH})"
            )
        return _fold_world_strength_math(from_node, depth=depth)
    if ntype in ("MIX", "MIX_RGB"):
        if depth >= _WORLD_STRENGTH_FOLD_MAX_DEPTH:
            raise QuantTraceSyncError(
                f"{label} Mix nest too deep (Slice 2aj max "
                f"{_WORLD_STRENGTH_FOLD_MAX_DEPTH})"
            )
        return _fold_world_strength_mix(from_node, depth=depth)
    if ntype == "MAP_RANGE":
        if depth >= _WORLD_STRENGTH_FOLD_MAX_DEPTH:
            raise QuantTraceSyncError(
                f"{label} Map Range nest too deep (Slice 2ak max "
                f"{_WORLD_STRENGTH_FOLD_MAX_DEPTH})"
            )
        return _fold_world_strength_map_range(from_node, depth=depth)
    if ntype == "CLAMP":
        if depth >= _WORLD_STRENGTH_FOLD_MAX_DEPTH:
            raise QuantTraceSyncError(
                f"{label} Clamp nest too deep (Slice 2ak max "
                f"{_WORLD_STRENGTH_FOLD_MAX_DEPTH})"
            )
        return _fold_world_strength_clamp(from_node, depth=depth)
    raise QuantTraceSyncError(
        f"{label} linked from {ntype!r} refused "
        "(Slice 2ak: Value/Math/Mix/RGB/Map Range/Clamp/unlinked float only; "
        "TEX_IMAGE/RGB Curves/Noise/texture-driven graphs still refuse)"
    )


def _world_strength_math_input(sock, label: str, *, depth: int) -> float:
    """Resolve a Math Value input (2ai; Mix/Value/unlinked also OK via 2aj)."""
    return _world_strength_const_input(sock, label, depth=depth)


_TEX_COLOR_STRENGTH_TYPES = frozenset(
    {"TEX_ENVIRONMENT", "TEX_IMAGE", "TEX_SKY"}
)


def _is_tex_color_strength_leaf(sock) -> bool:
    """True iff sock is a single Color link from ENV / IMAGE / SKY (Slice 2au).

    Color socket by name or identifier only — Vector / Alpha still refuse.
    """
    if sock is None or not getattr(sock, "is_linked", False):
        return False
    links = list(getattr(sock, "links", None) or [])
    if len(links) != 1:
        return False
    from_node = getattr(links[0], "from_node", None)
    from_sock = getattr(links[0], "from_socket", None)
    ntype = getattr(from_node, "type", None) if from_node is not None else None
    if ntype not in _TEX_COLOR_STRENGTH_TYPES:
        return False
    if from_sock is None:
        return False
    name = str(getattr(from_sock, "name", "") or "")
    ident = str(getattr(from_sock, "identifier", "") or "")
    return name == "Color" or ident == "Color"


def _tex_color_strength_leaf_type(sock):
    """Node type of a tex-Color leaf, or None."""
    if not _is_tex_color_strength_leaf(sock):
        return None
    links = list(getattr(sock, "links", None) or [])
    from_node = getattr(links[0], "from_node", None)
    return getattr(from_node, "type", None) if from_node is not None else None


def _fold_world_strength_math(node, *, depth: int = 0) -> float:
    """Fold ShaderNodeMath ADD/SUB/MUL/DIV/POWER with constant inputs (2ai/2au).

    Slice 2au: MULTIPLY(tex.Color, 0) or MULTIPLY(0, tex.Color) → 0.0 when
    tex is TEX_ENVIRONMENT / TEX_IMAGE / TEX_SKY and the other operand is a
    proven constant 0 (|c| < 1e-12). 0 * x = 0 for any finite x — the
    texture is not evaluated. Non-zero tex MULTIPLY and ADD/SUB/DIV/POWER
    with a tex Color input still refuse (Slice 2au).
    """
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
    a_tex = _is_tex_color_strength_leaf(a_sock)
    b_tex = _is_tex_color_strength_leaf(b_sock)
    if a_tex and b_tex:
        raise QuantTraceSyncError(
            "world Background Strength Math both-sides "
            "TEX_ENVIRONMENT/TEX_IMAGE/TEX_SKY Color refused (Slice 2au)"
        )
    if a_tex or b_tex:
        ntype = _tex_color_strength_leaf_type(a_sock if a_tex else b_sock)
        if op != "MULTIPLY":
            raise QuantTraceSyncError(
                f"world Background Strength Math {op} {ntype}.Color "
                "refused (Slice 2au: only MULTIPLY ×0 folds; "
                "ADD/SUBTRACT/DIVIDE/POWER with a tex Color input still refuse)"
            )
        const_sock = b_sock if a_tex else a_sock
        const_label = (
            "world Background Strength Math.Value_001"
            if a_tex
            else "world Background Strength Math.Value"
        )
        # Proven const 0 only. Do not swallow unrelated QuantTraceSyncError
        # (Noise, nest-too-deep, Vector, Alpha, unfoldable graphs).
        c = _world_strength_const_input(
            const_sock, const_label, depth=depth + 1
        )
        if abs(c) < 1e-12:
            return 0.0
        raise QuantTraceSyncError(
            f"world Background Strength Math MULTIPLY {ntype}.Color "
            "× non-zero refused (Slice 2au: spatially varying; only ×0 folds)"
        )
    a = _world_strength_const_input(
        a_sock, "world Background Strength Math.Value", depth=depth + 1
    )
    b = _world_strength_const_input(
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
    try:
        return float(a ** b)
    except (OverflowError, ValueError) as e:
        raise QuantTraceSyncError(
            f"world Background Strength Math POWER failed ({e}) (Slice 2ai)"
        ) from e


def _sock_ident_or_name(inputs, *keys):
    """bpy Mix sockets key by display name; identifier lives on the socket."""
    getter = getattr(inputs, "get", None)
    for key in keys:
        if callable(getter):
            sock = getter(key)
            if sock is not None:
                return sock
        for sock in inputs:
            if getattr(sock, "identifier", None) == key or getattr(sock, "name", None) == key:
                if getattr(sock, "enabled", True) or getattr(sock, "identifier", None) == key:
                    return sock
    return None


def _mix_input_socks(node):
    """Factor / A / B sockets for ShaderNodeMix or MixRGB (Slice 2aj)."""
    inputs = getattr(node, "inputs", None)
    if inputs is None:
        raise QuantTraceSyncError(
            "world Background Strength Mix has no inputs (Slice 2aj)"
        )
    ntype = getattr(node, "type", None)
    if ntype == "MIX_RGB":
        fac = _sock_ident_or_name(inputs, "Fac", "Factor")
        a = _sock_ident_or_name(inputs, "Color1")
        b = _sock_ident_or_name(inputs, "Color2")
        if fac is None or a is None or b is None:
            try:
                fac = fac or inputs[0]
                a = a or inputs[1]
                b = b or inputs[2]
            except (IndexError, TypeError, KeyError) as e:
                raise QuantTraceSyncError(
                    "world Background Strength MixRGB missing Fac/Color1/Color2 "
                    "(Slice 2aj)"
                ) from e
        return fac, a, b
    data_type = str(getattr(node, "data_type", "FLOAT") or "FLOAT")
    if data_type in ("VECTOR", "ROTATION"):
        raise QuantTraceSyncError(
            f"world Background Strength Mix data_type {data_type!r} refused "
            "(Slice 2aj: FLOAT or constant RGBA only)"
        )
    fac = _sock_ident_or_name(inputs, "Factor_Float", "Factor", "Fac")
    if data_type == "RGBA":
        a = _sock_ident_or_name(inputs, "A_Color", "A")
        b = _sock_ident_or_name(inputs, "B_Color", "B")
    else:
        a = _sock_ident_or_name(inputs, "A_Float", "A")
        b = _sock_ident_or_name(inputs, "B_Float", "B")
    if fac is None or a is None or b is None:
        try:
            enabled = [s for s in inputs if getattr(s, "enabled", True)]
            fac = fac or enabled[0]
            a = a or enabled[1]
            b = b or enabled[2]
        except (IndexError, TypeError, KeyError) as e:
            raise QuantTraceSyncError(
                "world Background Strength Mix missing Factor/A/B (Slice 2aj)"
            ) from e
    return fac, a, b


def _mix_color_rgb(sock, label: str, *, depth: int):
    """Resolve Mix A/B to RGB. TEX_IMAGE / unfoldable color graphs refuse."""
    if sock is None:
        raise QuantTraceSyncError(f"{label} missing (Slice 2aj)")
    stype = getattr(sock, "type", None)
    if stype != "RGBA":
        v = _world_strength_const_input(sock, label, depth=depth)
        return (v, v, v)
    if not getattr(sock, "is_linked", False):
        dv = getattr(sock, "default_value", (0.0, 0.0, 0.0, 1.0))
        return (float(dv[0]), float(dv[1]), float(dv[2]))
    links = list(getattr(sock, "links", None) or [])
    if len(links) != 1:
        raise QuantTraceSyncError(f"{label} multi-link refused (Slice 2aj)")
    from_node = getattr(links[0], "from_node", None)
    from_sock = getattr(links[0], "from_socket", None)
    ntype = getattr(from_node, "type", None) if from_node is not None else None
    if ntype == "RGB":
        if from_sock is None:
            raise QuantTraceSyncError(
                f"{label} RGB link has no from_socket (Slice 2aj)"
            )
        dv = getattr(from_sock, "default_value", (0.0, 0.0, 0.0, 1.0))
        return (float(dv[0]), float(dv[1]), float(dv[2]))
    if ntype in ("VALUE", "MATH", "MIX", "MIX_RGB"):
        v = _world_strength_const_input(sock, label, depth=depth)
        return (v, v, v)
    raise QuantTraceSyncError(
        f"{label} color-linked from {ntype!r} refused "
        "(Slice 2aj: unlinked/RGB/Value/Math/Mix only; "
        "TEX_IMAGE/Sky/Nishita still refuse)"
    )


def _fold_world_strength_mix(node, *, depth: int = 0) -> float:
    """Fold ShaderNodeMix FLOAT / MixRGB with constant Factor+A/B (2aj)."""
    op = str(getattr(node, "blend_type", "MIX") or "MIX")
    if op not in _WORLD_STRENGTH_MIX_OPS:
        raise QuantTraceSyncError(
            f"world Background Strength Mix blend_type {op!r} refused "
            "(Slice 2aj: MIX/ADD/SUBTRACT/MULTIPLY/DIVIDE only)"
        )
    fac_sock, a_sock, b_sock = _mix_input_socks(node)
    fac = _world_strength_const_input(
        fac_sock, "world Background Strength Mix.Factor", depth=depth + 1
    )
    if bool(getattr(node, "clamp_factor", False)):
        fac = min(1.0, max(0.0, fac))
    a_is_color = getattr(a_sock, "type", None) == "RGBA"
    b_is_color = getattr(b_sock, "type", None) == "RGBA"
    if a_is_color or b_is_color:
        ar, ag, ab = _mix_color_rgb(
            a_sock, "world Background Strength Mix.A", depth=depth + 1
        )
        br, bg, bb = _mix_color_rgb(
            b_sock, "world Background Strength Mix.B", depth=depth + 1
        )
        r = _mix_blend_float(op, fac, ar, br)
        g = _mix_blend_float(op, fac, ag, bg)
        bch = _mix_blend_float(op, fac, ab, bb)
        result = (r + g + bch) / 3.0
    else:
        a = _world_strength_const_input(
            a_sock, "world Background Strength Mix.A", depth=depth + 1
        )
        b = _world_strength_const_input(
            b_sock, "world Background Strength Mix.B", depth=depth + 1
        )
        result = _mix_blend_float(op, fac, a, b)
    if bool(getattr(node, "clamp_result", False) or getattr(node, "use_clamp", False)):
        result = min(1.0, max(0.0, result))
    return float(result)


def _fold_world_strength_map_range(node, *, depth: int = 0) -> float:
    """Fold ShaderNodeMapRange FLOAT LINEAR with constant sockets (Slice 2ak).

    Matches Cycles svm_node_map_range LINEAR, then optional RANGE clamp on
    To Min/To Max when node.clamp is set (MapRangeNode::expand inserts ClampNode).
    VECTOR / STEPPED / SMOOTHSTEP / SMOOTHERSTEP refuse.
    """
    data_type = str(getattr(node, "data_type", "FLOAT") or "FLOAT")
    if data_type != "FLOAT":
        raise QuantTraceSyncError(
            f"world Background Strength Map Range data_type {data_type!r} refused "
            "(Slice 2ak: FLOAT LINEAR only)"
        )
    interp = str(getattr(node, "interpolation_type", "LINEAR") or "LINEAR")
    if interp != "LINEAR":
        raise QuantTraceSyncError(
            f"world Background Strength Map Range interpolation {interp!r} refused "
            "(Slice 2ak: LINEAR only; STEPPED/SMOOTHSTEP/SMOOTHERSTEP still refuse)"
        )
    inputs = getattr(node, "inputs", None)
    if inputs is None:
        raise QuantTraceSyncError(
            "world Background Strength Map Range has no inputs (Slice 2ak)"
        )
    value_sock = _sock_ident_or_name(inputs, "Value")
    from_min_sock = _sock_ident_or_name(inputs, "From Min")
    from_max_sock = _sock_ident_or_name(inputs, "From Max")
    to_min_sock = _sock_ident_or_name(inputs, "To Min")
    to_max_sock = _sock_ident_or_name(inputs, "To Max")
    if None in (value_sock, from_min_sock, from_max_sock, to_min_sock, to_max_sock):
        try:
            enabled = [s for s in inputs if getattr(s, "enabled", True)]
            value_sock = value_sock or enabled[0]
            from_min_sock = from_min_sock or enabled[1]
            from_max_sock = from_max_sock or enabled[2]
            to_min_sock = to_min_sock or enabled[3]
            to_max_sock = to_max_sock or enabled[4]
        except (IndexError, TypeError, KeyError) as e:
            raise QuantTraceSyncError(
                "world Background Strength Map Range missing Value/From Min/"
                "From Max/To Min/To Max (Slice 2ak)"
            ) from e
    value = _world_strength_const_input(
        value_sock, "world Background Strength Map Range.Value", depth=depth + 1
    )
    from_min = _world_strength_const_input(
        from_min_sock, "world Background Strength Map Range.From Min", depth=depth + 1
    )
    from_max = _world_strength_const_input(
        from_max_sock, "world Background Strength Map Range.From Max", depth=depth + 1
    )
    to_min = _world_strength_const_input(
        to_min_sock, "world Background Strength Map Range.To Min", depth=depth + 1
    )
    to_max = _world_strength_const_input(
        to_max_sock, "world Background Strength Map Range.To Max", depth=depth + 1
    )
    if abs(from_max - from_min) < 1e-12:
        result = 0.0
    else:
        factor = (value - from_min) / (from_max - from_min)
        result = to_min + factor * (to_max - to_min)
    if bool(getattr(node, "clamp", False)):
        # Cycles MapRangeNode::expand → ClampNode RANGE on To Min / To Max.
        if to_min > to_max:
            result = min(to_min, max(to_max, result))
        else:
            result = min(to_max, max(to_min, result))
    return float(result)


def _fold_world_strength_clamp(node, *, depth: int = 0) -> float:
    """Fold ShaderNodeClamp MINMAX/RANGE with constant Value/Min/Max (Slice 2ak)."""
    ctype = str(getattr(node, "clamp_type", "MINMAX") or "MINMAX")
    if ctype not in ("MINMAX", "RANGE"):
        raise QuantTraceSyncError(
            f"world Background Strength Clamp clamp_type {ctype!r} refused "
            "(Slice 2ak: MINMAX/RANGE only)"
        )
    inputs = getattr(node, "inputs", None)
    if inputs is None:
        raise QuantTraceSyncError(
            "world Background Strength Clamp has no inputs (Slice 2ak)"
        )
    value_sock = _sock_ident_or_name(inputs, "Value")
    min_sock = _sock_ident_or_name(inputs, "Min")
    max_sock = _sock_ident_or_name(inputs, "Max")
    if None in (value_sock, min_sock, max_sock):
        try:
            value_sock = value_sock or inputs[0]
            min_sock = min_sock or inputs[1]
            max_sock = max_sock or inputs[2]
        except (IndexError, TypeError, KeyError) as e:
            raise QuantTraceSyncError(
                "world Background Strength Clamp missing Value/Min/Max (Slice 2ak)"
            ) from e
    value = _world_strength_const_input(
        value_sock, "world Background Strength Clamp.Value", depth=depth + 1
    )
    mn = _world_strength_const_input(
        min_sock, "world Background Strength Clamp.Min", depth=depth + 1
    )
    mx = _world_strength_const_input(
        max_sock, "world Background Strength Clamp.Max", depth=depth + 1
    )
    if ctype == "RANGE" and mn > mx:
        mn, mx = mx, mn
    # Cycles util clamp(value, min, max) == min(max(value, min), max); no swap on MINMAX.
    return float(min(mx, max(mn, value)))


def _world_strength_from_sock(sock) -> float:
    """Resolve Background.Strength to a constant float (Slice 2ah/2ai/2aj/2ak/2at/2au).

    Accepts unlinked default_value, ShaderNodeValue, ShaderNodeMath
    (ADD/SUBTRACT/MULTIPLY/DIVIDE/POWER, nest depth ≤3 — Slice 2at; 2ai was 2),
    ShaderNodeMix / MixRGB whose Factor + A/B fold to constants (unlinked
    floats / Value / RGB / shallow Math/Mix), ShaderNodeMapRange FLOAT LINEAR
    (Value/From Min/Max/To Min/Max constant; clamp RNA → RANGE clamp on To
    Min/Max), or ShaderNodeClamp MINMAX/RANGE. FLOAT mix type is the primary
    Mix path; constant RGBA / MixRGB folds via per-channel blend then RGB
    average (NODE_CONVERT_CF). Slice 2au: MULTIPLY(TEX_ENVIRONMENT.Color, 0)
    or MULTIPLY(0, tex.Color) folds to 0.0 (TEX_IMAGE / TEX_SKY Color too;
    proven const 0; texture is not evaluated). Multi-link, TEX_IMAGE /
    color-linked Mix / RGB Curves / Noise / VECTOR Mix / VECTOR Map Range /
    non-LINEAR Map Range / non-zero tex Math / ADD/SUB/DIV/POWER with a tex
    Color input / 4-deep Math / kitchens refuse.
    """
    if sock is None:
        return 0.0
    if not getattr(sock, "is_linked", False):
        return float(getattr(sock, "default_value", 0.0) or 0.0)
    links = list(getattr(sock, "links", None) or [])
    if len(links) != 1:
        raise QuantTraceSyncError(
            "world Background Strength multi-link refused (Slice 2aj)"
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
    if ntype in ("MIX", "MIX_RGB"):
        return _fold_world_strength_mix(from_node, depth=0)
    if ntype == "MAP_RANGE":
        return _fold_world_strength_map_range(from_node, depth=0)
    if ntype == "CLAMP":
        return _fold_world_strength_clamp(from_node, depth=0)
    raise QuantTraceSyncError(
        f"world Background Strength linked from {ntype!r} refused "
        "(Slice 2ak: ShaderNodeValue / ShaderNodeMath / ShaderNodeMix / "
        "MixRGB / Map Range FLOAT LINEAR / Clamp / unlinked float only; "
        "TEX_IMAGE/RGB Curves/Noise still refuse)"
    )



def _fold_world_color_mix(node, *, depth: int = 0):
    """Fold MixRGB / Mix FLOAT+RGBA to constant RGB (Slice 2al).

    MixRGB Color1/Color2 stay RGB. Mix FLOAT A/B become grey (v,v,v).
    MIX/ADD/SUBTRACT/MULTIPLY/DIVIDE; clamp_factor honoured.
    """
    op = str(getattr(node, "blend_type", "MIX") or "MIX")
    if op not in _WORLD_STRENGTH_MIX_OPS:
        raise QuantTraceSyncError(
            f"world Background Color Mix blend_type {op!r} refused "
            "(Slice 2al: MIX/ADD/SUBTRACT/MULTIPLY/DIVIDE only)"
        )
    if depth >= _WORLD_STRENGTH_FOLD_MAX_DEPTH:
        raise QuantTraceSyncError(
            f"world Background Color Mix nest too deep (Slice 2al max "
            f"{_WORLD_STRENGTH_FOLD_MAX_DEPTH})"
        )
    fac_sock, a_sock, b_sock = _mix_input_socks(node)
    try:
        fac = _world_strength_const_input(
            fac_sock, "world Background Color Mix.Factor", depth=depth + 1
        )
    except QuantTraceSyncError as e:
        raise QuantTraceSyncError(f"{e} (Slice 2al Color)") from e
    if bool(getattr(node, "clamp_factor", False)):
        fac = min(1.0, max(0.0, fac))
    try:
        ar, ag, ab = _mix_color_rgb(
            a_sock, "world Background Color Mix.A", depth=depth + 1
        )
        br, bg, bb = _mix_color_rgb(
            b_sock, "world Background Color Mix.B", depth=depth + 1
        )
    except QuantTraceSyncError as e:
        msg = str(e)
        if "Slice 2al" not in msg:
            raise QuantTraceSyncError(f"{msg} (Slice 2al)") from e
        raise
    r = _mix_blend_float(op, fac, ar, br)
    g = _mix_blend_float(op, fac, ag, bg)
    bch = _mix_blend_float(op, fac, ab, bb)
    if bool(getattr(node, "clamp_result", False) or getattr(node, "use_clamp", False)):
        r = min(1.0, max(0.0, r))
        g = min(1.0, max(0.0, g))
        bch = min(1.0, max(0.0, bch))
    return (float(r), float(g), float(bch))


def _rgb_from_sock_or_node(from_node, from_sock):
    """ShaderNodeRGB output / node color as float3."""
    dv = None
    if from_sock is not None:
        dv = getattr(from_sock, "default_value", None)
    if dv is None and from_node is not None:
        outs = getattr(from_node, "outputs", None)
        getter = getattr(outs, "get", None) if outs is not None else None
        cs = getter("Color") if callable(getter) else None
        if cs is None and outs:
            try:
                cs = outs[0]
            except (IndexError, TypeError, KeyError):
                cs = None
        if cs is not None:
            dv = getattr(cs, "default_value", None)
    if dv is None:
        raise QuantTraceSyncError(
            "world Background Color RGB has no Color value (Slice 2al)"
        )
    return (float(dv[0]), float(dv[1]), float(dv[2]))


def _world_sky_empty():
    """Slice 2am zeros — type 0 keeps 2al/2aa bit-identical."""
    return {
        "world_sky_type": 0,
        "world_sky_sun_direction": (0.0, 0.0, 0.0),
        "world_sky_turbidity": 0.0,
        "world_sky_ground_albedo": 0.0,
        "world_sky_sun_disc": 0,
        "world_sky_sun_size": 0.0,
        "world_sky_sun_intensity": 0.0,
        "world_sky_sun_elevation": 0.0,
        "world_sky_sun_rotation": 0.0,
        "world_sky_altitude": 0.0,
        "world_sky_air_density": 0.0,
        "world_sky_aerosol_density": 0.0,
        "world_sky_ozone_density": 0.0,
    }


def _pack_world_sky_from_node(node) -> dict:
    """Pack ShaderNodeTexSky RNA into world_sky_* + Vector (Slice 2am / 2ar).

    Slice 2am: unlinked Vector (mode 0 → LINK_TEXTURE_GENERATED).
    Slice 2ar: Vector ← TEX_COORD (Generated/Object/Camera/Window/Reflection/UV)
    or Mapping(VECTOR) ← TEX_COORD, same modes as env 2ac/2ae / TEX_IMAGE 2an.
    Returns world_sky_* plus world_tex_vector_mode / world_map_* / world_ob_ref.
    Blender 5.2 sky_type default is MULTIPLE_SCATTERING (legacy RNA NISHITA).
    dust_density is the older name for aerosol_density.
    RGB Curves / Noise still refuse elsewhere.
    """
    tex_vector_mode = 0  # QT_TEX_VECTOR_UNLINKED → LINK_TEXTURE_GENERATED
    map_location = (0.0, 0.0, 0.0)
    map_rotation = (0.0, 0.0, 0.0)
    map_scale = (1.0, 1.0, 1.0)
    map_type = 2
    world_ob_ref = None

    vec_sock = None
    inputs = getattr(node, "inputs", None)
    if inputs is not None:
        for inp in list(inputs):
            ident = str(getattr(inp, "identifier", "") or "")
            name = str(getattr(inp, "name", "") or "")
            if ident == "Vector" or name == "Vector":
                vec_sock = inp
                break
        if vec_sock is None:
            getter = getattr(inputs, "get", None)
            vec_sock = getter("Vector") if callable(getter) else None
    if vec_sock is not None and getattr(vec_sock, "is_linked", False):
        vlinks = list(getattr(vec_sock, "links", None) or [])
        if len(vlinks) != 1:
            raise QuantTraceSyncError(
                "world Background Color TEX_SKY Vector has multiple links "
                "(Slice 2ar)"
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
                tex_vector_mode = 3
            elif key == "object":
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
                    f"world Background Color TEX_SKY Vector TEX_COORD output "
                    f"{vname!r} refused (Slice 2ar)"
                )
        elif vtype == "MAPPING":
            if vname not in ("Vector", "vector"):
                raise QuantTraceSyncError(
                    "world Background Color TEX_SKY Vector must come from "
                    "Mapping Vector (Slice 2ar)"
                )
            try:
                map_location, map_rotation, map_scale, map_type, space = (
                    _mapping_constants(vnode)
                )
            except QuantTraceSyncError as e:
                msg = str(e)
                if "Slice 2" in msg:
                    raise QuantTraceSyncError(
                        msg.replace("Slice 2ag", "Slice 2ar")
                        .replace("Slice 2h", "Slice 2ar")
                        .replace("Slice 2k", "Slice 2ar")
                        .replace("Slice 2l", "Slice 2ar")
                        .replace("Slice 2m", "Slice 2ar")
                        .replace("Slice 2n", "Slice 2ar")
                        .replace("Slice 2ac", "Slice 2ar")
                        .replace("Slice 2ae", "Slice 2ar")
                        .replace("Slice 2ab", "Slice 2ar")
                        .replace("Slice 2an", "Slice 2ar")
                    ) from e
                raise QuantTraceSyncError(f"{msg} (Slice 2ar)") from e
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
                f"world Background Color TEX_SKY Vector from {vtype!r} refused "
                "(Slice 2ar: TEX_COORD or Mapping←TEX_COORD only; "
                "Noise/RGB Curves still refuse)"
            )

    rna = str(getattr(node, "sky_type", "") or "").upper()
    if rna in ("NISHITA", "MULTIPLE_SCATTERING"):
        sky_type = 3
    elif rna in ("HOSEK_WILKIE", "HOSEK"):
        sky_type = 2
    elif rna == "PREETHAM":
        sky_type = 1
    elif rna == "SINGLE_SCATTERING":
        sky_type = 4
    else:
        raise QuantTraceSyncError(
            f"world Background Color TEX_SKY sky_type {rna!r} refused "
            "(Slice 2am: PREETHAM/HOSEK_WILKIE/NISHITA/MULTIPLE_SCATTERING/"
            "SINGLE_SCATTERING)"
        )
    sd = getattr(node, "sun_direction", (0.0, 0.0, 1.0))
    try:
        sun_dir = (float(sd[0]), float(sd[1]), float(sd[2]))
    except (TypeError, IndexError):
        sun_dir = (0.0, 0.0, 1.0)
    aerosol = getattr(node, "aerosol_density", None)
    if aerosol is None:
        aerosol = getattr(node, "dust_density", 1.0)
    return {
        "world_sky_type": int(sky_type),
        "world_sky_sun_direction": sun_dir,
        "world_sky_turbidity": float(getattr(node, "turbidity", 2.2)),
        "world_sky_ground_albedo": float(getattr(node, "ground_albedo", 0.3)),
        "world_sky_sun_disc": 1 if bool(getattr(node, "sun_disc", True)) else 0,
        "world_sky_sun_size": float(getattr(node, "sun_size", 0.009512)),
        "world_sky_sun_intensity": float(getattr(node, "sun_intensity", 1.0)),
        "world_sky_sun_elevation": float(getattr(node, "sun_elevation", 0.0)),
        "world_sky_sun_rotation": float(getattr(node, "sun_rotation", 0.0)),
        "world_sky_altitude": float(getattr(node, "altitude", 100.0)),
        "world_sky_air_density": float(getattr(node, "air_density", 1.0)),
        "world_sky_aerosol_density": float(aerosol if aerosol is not None else 1.0),
        "world_sky_ozone_density": float(getattr(node, "ozone_density", 1.0)),
        "world_tex_vector_mode": int(tex_vector_mode),
        "world_map_location": map_location,
        "world_map_rotation": map_rotation,
        "world_map_scale": map_scale,
        "world_map_type": map_type,
        "world_ob_ref": world_ob_ref,
    }


def _world_color_from_linked(from_node, from_sock):
    """Resolve a linked Background Color source to constant RGB (Slice 2al).

    TEX_ENVIRONMENT is not folded here — caller keeps the env path and
    leaves world_color at (0,0,0). TEX_SKY is packed by the caller (Slice 2am).
    TEX_IMAGE is packed by the caller (Slice 2an) — not refused here.
    """
    ntype = getattr(from_node, "type", None) if from_node is not None else None
    if ntype == "RGB":
        return _rgb_from_sock_or_node(from_node, from_sock)
    if ntype == "VALUE":
        if from_sock is None:
            raise QuantTraceSyncError(
                "world Background Color Value link has no from_socket "
                "(Slice 2al)"
            )
        v = float(getattr(from_sock, "default_value", 0.0) or 0.0)
        return (v, v, v)
    if ntype == "MATH":
        v = _fold_world_strength_math(from_node, depth=0)
        return (float(v), float(v), float(v))
    if ntype in ("MIX", "MIX_RGB"):
        return _fold_world_color_mix(from_node, depth=0)
    raise QuantTraceSyncError(
        f"world Background Color linked from {ntype!r} refused "
        "(Slice 2aq: TEX_IMAGE/TEX_ENVIRONMENT/TEX_SKY/RGB/Mix/Value/Math + "
        "unlinked Gamma/HueSat/BrightContrast/Mix-chain; Noise/RGB Curves/"
        "linked Fac / both-linked non-constant Mix still refuse)"
    )



def _world_color_image_empty():
    """Slice 2an zeros — empty path keeps 2aa/2al/2am bit-identical."""
    return {
        "world_color_image_path": "",
        "world_color_image_colorspace": "",
        "world_color_image_projection": 0,
    }


def _pack_world_color_image_from_node(from_node) -> dict:
    """Pack ShaderNodeTexImage → Background Color (Slice 2an).

    Returns world_color_image_* plus world_tex_vector_mode / world_map_* /
    world_ob_ref (same Vector shapes as env 2ac/2ae). Path empty refused.
    """
    img = getattr(from_node, "image", None)
    path = _abspath_image(img)
    if not path:
        raise QuantTraceSyncError(
            "world Background Color TEX_IMAGE has no disk filepath and no "
            "packed pixels (Slice 2af / Slice 2an)"
        )
    proj_rna = str(getattr(from_node, "projection", "FLAT") or "").upper()
    if proj_rna == "FLAT":
        proj = 0
    elif proj_rna == "BOX":
        proj = 1
    elif proj_rna == "SPHERE":
        proj = 2
    elif proj_rna == "TUBE":
        proj = 3
    else:
        raise QuantTraceSyncError(
            f"world Background Color TEX_IMAGE projection {proj_rna!r} refused "
            "(Slice 2an: FLAT/BOX/SPHERE/TUBE)"
        )
    cs = ""
    if img is not None:
        cs_settings = getattr(img, "colorspace_settings", None)
        if cs_settings is not None:
            cs = str(getattr(cs_settings, "name", "") or "")

    tex_vector_mode = 0  # QT_TEX_VECTOR_UNLINKED → LINK_TEXTURE_UV
    map_location = (0.0, 0.0, 0.0)
    map_rotation = (0.0, 0.0, 0.0)
    map_scale = (1.0, 1.0, 1.0)
    map_type = 2
    world_ob_ref = None
    vec_sock = from_node.inputs.get("Vector") if from_node is not None else None
    if vec_sock is not None and getattr(vec_sock, "is_linked", False):
        vlinks = list(getattr(vec_sock, "links", None) or [])
        if len(vlinks) != 1:
            raise QuantTraceSyncError(
                "world Background Color TEX_IMAGE Vector has multiple links "
                "(Slice 2an)"
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
                tex_vector_mode = 3
            elif key == "object":
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
                    f"world Background Color TEX_IMAGE Vector TEX_COORD output "
                    f"{vname!r} refused (Slice 2an)"
                )
        elif vtype == "MAPPING":
            if vname not in ("Vector", "vector"):
                raise QuantTraceSyncError(
                    "world Background Color TEX_IMAGE Vector must come from "
                    "Mapping Vector (Slice 2an)"
                )
            try:
                map_location, map_rotation, map_scale, map_type, space = (
                    _mapping_constants(vnode)
                )
            except QuantTraceSyncError as e:
                msg = str(e)
                if "Slice 2" in msg:
                    raise QuantTraceSyncError(
                        msg.replace("Slice 2ag", "Slice 2an")
                        .replace("Slice 2h", "Slice 2an")
                        .replace("Slice 2k", "Slice 2an")
                        .replace("Slice 2l", "Slice 2an")
                        .replace("Slice 2m", "Slice 2an")
                        .replace("Slice 2n", "Slice 2an")
                        .replace("Slice 2ac", "Slice 2an")
                        .replace("Slice 2ae", "Slice 2an")
                        .replace("Slice 2ab", "Slice 2an")
                    ) from e
                raise QuantTraceSyncError(f"{msg} (Slice 2an)") from e
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
                f"world Background Color TEX_IMAGE Vector from {vtype!r} "
                "refused (Slice 2an: TEX_COORD or Mapping←TEX_COORD only)"
            )

    return {
        "world_color_image_path": path,
        "world_color_image_colorspace": cs,
        "world_color_image_projection": proj,
        "world_tex_vector_mode": tex_vector_mode,
        "world_map_location": map_location,
        "world_map_rotation": map_rotation,
        "world_map_scale": map_scale,
        "world_map_type": map_type,
        "world_ob_ref": world_ob_ref,
    }


def _world_gamma_hsv_identity():
    """Slice 2ao/2ap/2aq/2as identity — skip Gamma/HSV/BrightContrast/Mix/Curves.

    Keeps 2aa/2al/2am/2an/2ao/2ap/2aq/2ar bit-identical when all identity.
    """
    return {
        "world_gamma": 1.0,
        "world_hsv_hue": 0.5,
        "world_hsv_sat": 1.0,
        "world_hsv_val": 1.0,
        "world_hsv_fac": 1.0,
        "world_bright": 0.0,
        "world_contrast": 0.0,
        "world_mix_type": 0,
        "world_mix_fac": 0.5,
        "world_mix_other": (0.0, 0.0, 0.0),
        "world_mix_chain_is_a": 1,
        "world_mix_clamp_factor": 0,
        "world_mix_clamp_result": 0,
        "world_curves": None,
        "world_curves_n": 0,
        "world_curves_min_x": 0.0,
        "world_curves_max_x": 1.0,
        "world_curves_fac": 1.0,
        "world_curves_extrapolate": 1,
    }


def _require_unlinked_float(node, names, label: str) -> float:
    """Require an unlinked float socket (Slice 2ao/2ap Gamma/Hue/Sat/Value/Fac/Bright/Contrast)."""
    inputs = getattr(node, "inputs", None)
    if inputs is None:
        raise QuantTraceSyncError(
            f"world Background Color {label} has no inputs (Slice 2ap)"
        )
    sock = _sock_ident_or_name(inputs, *names)
    if sock is None:
        raise QuantTraceSyncError(
            f"world Background Color {label} missing (Slice 2ap)"
        )
    if getattr(sock, "is_linked", False):
        raise QuantTraceSyncError(
            f"world Background Color {label} is linked refused "
            "(Slice 2ap: texture-driven Gamma/Hue/Sat/Value/Fac/Bright/Contrast still refuse)"
        )
    return float(getattr(sock, "default_value", 0.0) or 0.0)


def _gamma_hsv_color_source(node):
    """Color input of Gamma/HueSat/BrightContrast: (from_node, from_sock, unlinked_rgb_or_None)."""
    inputs = getattr(node, "inputs", None)
    if inputs is None:
        raise QuantTraceSyncError(
            "world Background Color Gamma/HueSat/BrightContrast has no inputs (Slice 2ap)"
        )
    color_in = _sock_ident_or_name(inputs, "Color")
    if color_in is None:
        raise QuantTraceSyncError(
            "world Background Color Gamma/HueSat/BrightContrast missing Color (Slice 2ap)"
        )
    if not getattr(color_in, "is_linked", False):
        col = getattr(color_in, "default_value", (0.0, 0.0, 0.0, 1.0))
        rgb = (float(col[0]), float(col[1]), float(col[2]))
        return None, None, rgb
    links = list(getattr(color_in, "links", None) or [])
    if len(links) != 1:
        raise QuantTraceSyncError(
            "world Background Color Gamma/HueSat/BrightContrast Color multi-link refused "
            "(Slice 2ap)"
        )
    return (
        getattr(links[0], "from_node", None),
        getattr(links[0], "from_socket", None),
        None,
    )


_WORLD_MIX_TYPE_MAP = {
    "MIX": 1,
    "ADD": 2,
    "SUBTRACT": 3,
    "MULTIPLY": 4,
    "DIVIDE": 5,
}


def _peel_world_mix(from_node, from_sock):
    """Peel Mix immediately on Background Color (Slice 2aq).

    Background ← Mix(chain, constant) with unlinked Factor packs world_mix_*
    and returns the chain side for Gamma/HSV/BC peel. Both-sides-constant Mix
    is left in place for Slice 2al fold into world_color (mix_type stays 0).
    ShaderNodeMix data_type RGBA (Blender 5.2 COLOR) or MIX_RGB; FLOAT/VECTOR
    Mix left for 2al or refused. Cite Cycles MixColorNode / NodeMix.
    """
    mix = {
        "world_mix_type": 0,
        "world_mix_fac": 0.5,
        "world_mix_other": (0.0, 0.0, 0.0),
        "world_mix_chain_is_a": 1,
        "world_mix_clamp_factor": 0,
        "world_mix_clamp_result": 0,
    }
    ntype = getattr(from_node, "type", None) if from_node is not None else None
    if ntype not in ("MIX", "MIX_RGB"):
        return from_node, from_sock, mix
    if ntype == "MIX":
        data_type = str(getattr(from_node, "data_type", "FLOAT") or "FLOAT")
        if data_type in ("VECTOR", "ROTATION"):
            raise QuantTraceSyncError(
                f"world Background Color Mix data_type {data_type!r} refused "
                "(Slice 2aq: ShaderNodeMix RGBA / MixRGB only)"
            )
        if data_type == "FLOAT":
            # Constant FLOAT Mix still folds via 2al; chain Mix after HSV is RGBA.
            return from_node, from_sock, mix
        if data_type != "RGBA":
            raise QuantTraceSyncError(
                f"world Background Color Mix data_type {data_type!r} refused "
                "(Slice 2aq: RGBA / MixRGB only)"
            )
    op = str(getattr(from_node, "blend_type", "MIX") or "MIX")
    if op not in _WORLD_STRENGTH_MIX_OPS:
        raise QuantTraceSyncError(
            f"world Background Color Mix blend_type {op!r} refused "
            "(Slice 2aq: MIX/ADD/SUBTRACT/MULTIPLY/DIVIDE only)"
        )
    fac_sock, a_sock, b_sock = _mix_input_socks(from_node)
    if fac_sock is None:
        raise QuantTraceSyncError(
            "world Background Color Mix missing Factor (Slice 2aq)"
        )
    if getattr(fac_sock, "is_linked", False):
        raise QuantTraceSyncError(
            "world Background Color Mix Factor is linked refused "
            "(Slice 2aq: unlinked Factor only)"
        )
    a_linked = bool(getattr(a_sock, "is_linked", False)) if a_sock is not None else False
    b_linked = bool(getattr(b_sock, "is_linked", False)) if b_sock is not None else False
    if not a_linked and not b_linked:
        # Both unlinked constants → Slice 2al fold into world_color.
        return from_node, from_sock, mix
    if a_linked and b_linked:
        # Both linked — leave for 2al fold (RGB/Value/Math); chain graphs refuse there.
        return from_node, from_sock, mix
    # Exactly one side linked = chain; other must be unlinked constant RGB.
    chain_is_a = 1 if a_linked else 0
    other_sock = b_sock if a_linked else a_sock
    chain_sock = a_sock if a_linked else b_sock
    if other_sock is None or chain_sock is None:
        raise QuantTraceSyncError(
            "world Background Color Mix missing A/B (Slice 2aq)"
        )
    stype = getattr(other_sock, "type", None)
    dv = getattr(other_sock, "default_value", None)
    if stype == "RGBA" or (hasattr(dv, "__len__") and not isinstance(dv, (str, bytes))):
        try:
            other = (float(dv[0]), float(dv[1]), float(dv[2]))
        except (TypeError, IndexError, ValueError) as e:
            raise QuantTraceSyncError(
                "world Background Color Mix other side not constant RGB "
                "(Slice 2aq)"
            ) from e
    else:
        try:
            v = float(dv or 0.0)
        except (TypeError, ValueError) as e:
            raise QuantTraceSyncError(
                "world Background Color Mix other side not constant "
                "(Slice 2aq)"
            ) from e
        other = (v, v, v)
    fac = float(getattr(fac_sock, "default_value", 0.5) or 0.0)
    clamp_factor = bool(getattr(from_node, "clamp_factor", False))
    if clamp_factor:
        fac = min(1.0, max(0.0, fac))
    clamp_result = bool(
        getattr(from_node, "clamp_result", False)
        or getattr(from_node, "use_clamp", False)
    )
    mix["world_mix_type"] = int(_WORLD_MIX_TYPE_MAP[op])
    mix["world_mix_fac"] = float(fac)
    mix["world_mix_other"] = other
    mix["world_mix_chain_is_a"] = int(chain_is_a)
    mix["world_mix_clamp_factor"] = 1 if clamp_factor else 0
    mix["world_mix_clamp_result"] = 1 if clamp_result else 0
    links = list(getattr(chain_sock, "links", None) or [])
    if len(links) != 1:
        raise QuantTraceSyncError(
            "world Background Color Mix chain multi-link refused (Slice 2aq)"
        )
    return (
        getattr(links[0], "from_node", None),
        getattr(links[0], "from_socket", None),
        mix,
    )


_RAMP_TABLE_SIZE = 256  # Cycles RAMP_TABLE_SIZE; table length = size + 1 = 257


def _pack_rgb_curves_lut(node, *, ctx: str, slice_tag: str) -> dict:
    """Official Cycles curvemapping_color_to_array (rgb_curve=true).

    DNA/cm order used by Cycles util.h: cm[0]=R, cm[1]=G, cm[2]=B, cm[3]=I.
    bpy mapping.curves mirrors that DNA for ShaderNodeRGBCurve.
    Call mapping.update() before evaluate (== BKE_curvemapping_changed_all + init).
    Fac must be unlinked. Linked Fac refuses (named slice_tag).
    Returns generic keys: curves / n / min_x / max_x / fac / extrapolate.
    """
    mapping = getattr(node, "mapping", None)
    if mapping is None:
        raise QuantTraceSyncError(
            f"{ctx} RGB Curves missing mapping (Slice {slice_tag})"
        )
    curves = list(getattr(mapping, "curves", None) or [])
    if len(curves) < 4:
        raise QuantTraceSyncError(
            f"{ctx} RGB Curves needs 4 curves got {len(curves)} "
            f"(Slice {slice_tag})"
        )
    # Fac unlinked (Cycles folds fac==0; we still pack and let native skip).
    inputs = getattr(node, "inputs", None)
    if inputs is None:
        raise QuantTraceSyncError(
            f"{ctx} RGBCurves.Fac has no inputs (Slice {slice_tag})"
        )
    fac_sock = _sock_ident_or_name(inputs, "Fac", "Factor")
    if fac_sock is None:
        raise QuantTraceSyncError(
            f"{ctx} RGBCurves.Fac missing (Slice {slice_tag})"
        )
    if getattr(fac_sock, "is_linked", False):
        from_n = None
        links = list(getattr(fac_sock, "links", None) or [])
        if links:
            from_n = getattr(links[0], "from_node", None)
        ntype = getattr(from_n, "type", None) if from_n is not None else "?"
        raise QuantTraceSyncError(
            f"{ctx} RGBCurves.Fac from {ntype!r} is linked refused "
            f"(Slice {slice_tag}: unlinked Fac only; Noise/TEX_IMAGE/Value Fac still refuse)"
        )
    fac_v = getattr(fac_sock, "default_value", None)
    fac = 0.0 if fac_v is None else float(fac_v)
    # min/max of first/last point.x across 4 curves
    min_x = float("inf")
    max_x = float("-inf")
    for cm in curves[:4]:
        pts = list(getattr(cm, "points", None) or [])
        if not pts:
            raise QuantTraceSyncError(
                f"{ctx} RGB Curves empty curve (Slice {slice_tag})"
            )
        min_x = min(min_x, float(pts[0].location[0]))
        max_x = max(max_x, float(pts[-1].location[0]))
    range_x = max_x - min_x
    mapping.update()
    mapR, mapG, mapB, mapI = curves[0], curves[1], curves[2], curves[3]
    lut = []
    n = _RAMP_TABLE_SIZE + 1
    for i in range(n):
        tval = min_x + (float(i) / float(_RAMP_TABLE_SIZE)) * range_x
        ti = float(mapping.evaluate(mapI, tval))
        lut.extend(
            (
                float(mapping.evaluate(mapR, ti)),
                float(mapping.evaluate(mapG, ti)),
                float(mapping.evaluate(mapB, ti)),
            )
        )
    extend = str(getattr(mapping, "extend", "") or "")
    extrapolate = 1 if extend == "EXTRAPOLATED" else 0
    # Identity LUT smoke: mid sample ~ (0.5,0.5,0.5) when all curves identity.
    mid = n // 2
    print(
        f"QUANTTRACE_SLICE{slice_tag.upper()}_LUT",
        "n", n,
        "min_x", min_x, "max_x", max_x,
        "fac", fac, "extrapolate", extrapolate,
        "sample0", tuple(lut[0:3]),
        "sample_mid", tuple(lut[mid * 3 : mid * 3 + 3]),
        "sample_end", tuple(lut[-3:]),
    )
    return {
        "curves": lut,
        "n": n,
        "min_x": float(min_x),
        "max_x": float(max_x),
        "fac": float(fac),
        "extrapolate": int(extrapolate),
    }


def _pack_world_rgb_curves_lut(node) -> dict:
    """Slice 2as wrapper — world_curves_* keys."""
    packed = _pack_rgb_curves_lut(
        node, ctx="world Background Color", slice_tag="2as"
    )
    return {
        "world_curves": packed["curves"],
        "world_curves_n": packed["n"],
        "world_curves_min_x": packed["min_x"],
        "world_curves_max_x": packed["max_x"],
        "world_curves_fac": packed["fac"],
        "world_curves_extrapolate": packed["extrapolate"],
    }


def _pack_base_rgb_curves_lut(node, ctx: str) -> dict:
    """Slice 2bd wrapper — base_curves_* keys."""
    packed = _pack_rgb_curves_lut(node, ctx=ctx, slice_tag="2bd")
    return {
        "base_curves": packed["curves"],
        "base_curves_n": packed["n"],
        "base_curves_min_x": packed["min_x"],
        "base_curves_max_x": packed["max_x"],
        "base_curves_fac": packed["fac"],
        "base_curves_extrapolate": packed["extrapolate"],
    }


def _peel_world_gamma_hsv(from_node, from_sock):
    """Peel one unlinked Gamma + HueSat + BrightContrast + RGB Curves (≤4 hops).

    Returns (from_node, from_sock, unlinked_rgb_or_None, gamma_hsv_bc_curves_dict).
    Remaining source is resolved by the caller (TEX_ENVIRONMENT / TEX_SKY /
    TEX_IMAGE / RGB/Mix/Value/Math). Second Gamma/HueSat/BrightContrast/Curves
    refuses. Linked Gamma/Hue/Sat/Value/Fac/Bright/Contrast/Curves.Fac refuses.
    Native applies loft order Color → RGBCurves → Gamma → HSV → BrightContrast →
    Mix → Background regardless of peel order (Slice 2as). Caller peels Mix first.
    """
    gh = dict(_world_gamma_hsv_identity())
    seen_gamma = False
    seen_hsv = False
    seen_bc = False
    seen_curves = False
    unlinked_rgb = None
    for _hop in range(4):
        ntype = getattr(from_node, "type", None) if from_node is not None else None
        if ntype == "GAMMA":
            if seen_gamma:
                raise QuantTraceSyncError(
                    "world Background Color second Gamma refused (Slice 2as)"
                )
            gh["world_gamma"] = _require_unlinked_float(
                from_node, ("Gamma",), "Gamma.Gamma"
            )
            seen_gamma = True
            from_node, from_sock, unlinked_rgb = _gamma_hsv_color_source(from_node)
            if unlinked_rgb is not None:
                break
            continue
        if ntype == "HUE_SAT":
            if seen_hsv:
                raise QuantTraceSyncError(
                    "world Background Color second HueSat refused (Slice 2as)"
                )
            gh["world_hsv_hue"] = _require_unlinked_float(
                from_node, ("Hue",), "HueSat.Hue"
            )
            gh["world_hsv_sat"] = _require_unlinked_float(
                from_node, ("Saturation",), "HueSat.Saturation"
            )
            gh["world_hsv_val"] = _require_unlinked_float(
                from_node, ("Value",), "HueSat.Value"
            )
            gh["world_hsv_fac"] = _require_unlinked_float(
                from_node, ("Fac", "Factor"), "HueSat.Fac"
            )
            seen_hsv = True
            from_node, from_sock, unlinked_rgb = _gamma_hsv_color_source(from_node)
            if unlinked_rgb is not None:
                break
            continue
        if ntype in ("BRIGHTCONTRAST", "BRIGHTNESS_CONTRAST"):
            if seen_bc:
                raise QuantTraceSyncError(
                    "world Background Color second Bright/Contrast refused "
                    "(Slice 2as)"
                )
            gh["world_bright"] = _require_unlinked_float(
                from_node, ("Bright", "Brightness"), "BrightContrast.Bright"
            )
            gh["world_contrast"] = _require_unlinked_float(
                from_node, ("Contrast",), "BrightContrast.Contrast"
            )
            seen_bc = True
            from_node, from_sock, unlinked_rgb = _gamma_hsv_color_source(from_node)
            if unlinked_rgb is not None:
                break
            continue
        if ntype == "CURVE_RGB":
            if seen_curves:
                raise QuantTraceSyncError(
                    "world Background Color second RGB Curves refused (Slice 2as)"
                )
            packed = _pack_world_rgb_curves_lut(from_node)
            # Fac==0: Cycles folds — keep n==0 so native skips (bit-identical).
            if float(packed["world_curves_fac"]) == 0.0:
                packed = {
                    "world_curves": None,
                    "world_curves_n": 0,
                    "world_curves_min_x": 0.0,
                    "world_curves_max_x": 1.0,
                    "world_curves_fac": 0.0,
                    "world_curves_extrapolate": 1,
                }
            gh.update(packed)
            seen_curves = True
            from_node, from_sock, unlinked_rgb = _gamma_hsv_color_source(from_node)
            if unlinked_rgb is not None:
                break
            continue
        if ntype in ("CURVE_VEC", "CURVE_VECTOR", "CURVE_FLOAT"):
            raise QuantTraceSyncError(
                f"world Background Color {ntype!r} refused "
                "(Slice 2as: ShaderNodeRGBCurve only; Vector/Float Curve still refuse)"
            )
        break
    ntype = getattr(from_node, "type", None) if from_node is not None else None
    if ntype == "CURVE_RGB":
        # Hop cap exhausted with another Curves ahead — refuse.
        raise QuantTraceSyncError(
            "world Background Color RGB Curves hop refused (Slice 2as: ≤4 hops; "
            "second Curves or Curves beyond Gamma/HSV/BC chain)"
        )
    if ntype in ("TEX_NOISE", "NOISE"):
        raise QuantTraceSyncError(
            "world Background Color Noise refused (Slice 2as)"
        )
    if ntype in ("CURVE_VEC", "CURVE_VECTOR", "CURVE_FLOAT"):
        raise QuantTraceSyncError(
            f"world Background Color {ntype!r} refused "
            "(Slice 2as: ShaderNodeRGBCurve only)"
        )
    return from_node, from_sock, unlinked_rgb, gh


def _world_info(scene) -> dict:
    """Pack world Background + Env / Sky / ImageTexture Color (2aa/2al/2am/2an/2ao/2ap).

    Returns dict:
      world_strength: float
      world_color: (r,g,b) Background Color when path empty (default 0,0,0)
      world_image_path: str (empty = use world_color, Slice 2b/2al)
      world_image_colorspace: str
      world_projection: int (0=EQUIRECTANGULAR, 1=MIRROR_BALL)
      world_tex_vector_mode: int (QT_TEX_VECTOR_*; 0 = unlinked)
      world_map_location / rotation / scale / type: Mapping constants (Slice 2ac)
      world_sky_*: Slice 2am Sky Texture (type 0 = none)
      world_color_image_*: Slice 2an Image Texture → Color (empty path = none)

    Empty path keeps locked-cube black worlds bit-identical when world_color is 0
    and world_sky_type is 0 and world_color_image_path is empty and Gamma/HSV/
    BrightContrast/Mix are identity (Slice 2ao/2ap/2aq).
    Slice 2al: unlinked Color (incl. non-black), ShaderNodeRGB, MixRGB / Mix
    FLOAT constants, Value/Math → Color as grey. TEX_ENVIRONMENT still wins
    (world_color stays 0,0,0). Slice 2am: ShaderNodeTexSky (unlinked Vector)
    packs world_sky_* (path empty, color zeros). Slice 2an: ShaderNodeTexImage
    Color → Background Color (path empty + color zeros + sky_type 0); Vector
    same shapes as env 2ac/2ae. Slice 2ao/2ap/2aq: peel Mix (chain+constant)
    then unlinked Gamma + HueSat + BrightContrast (one of each, any order,
    ≤3 hops) then resolve remaining source as today. Native loft order Color
    → RGBCurves → Gamma → HSV → BrightContrast → Mix → Background. Noise /
    linked Fac / both-sides-linked Mix (non-constant) / second Mix / linked
    Gamma/Hue/Sat/Value/Fac/Bright/Contrast / second Gamma/HueSat/BrightContrast
    / VECTOR Mix / Vector Curves / Float Curve refuse. Slice 2ar: linked Sky
    Vector accepted. Slice 2as: RGB Curves accepted (packed LUT, n==0 skip).
    Slice 2ac: Vector may be TEX_COORD Generated/Object/Camera/Window/Reflection
    or Mapping(VECTOR, unlinked L/R/S) ← TEX_COORD (same graph shapes as mesh
    TEX_IMAGE). UV accepted for ABI parity but uncommon on env. Other shapes
    refuse with Slice 2ac in the error.
    Slice 2ah/2ai/2aj/2ak/2at/2au: Strength may be unlinked default_value,
    ShaderNodeValue, ShaderNodeMath (ADD/SUB/MUL/DIV/POWER, nest ≤3),
    ShaderNodeMix FLOAT / MixRGB whose Factor+A/B fold to constants
    (Value/unlinked/RGB/shallow Math/Mix), ShaderNodeMapRange FLOAT LINEAR,
    or ShaderNodeClamp MINMAX/RANGE. Slice 2au folds MULTIPLY(tex.Color, 0)
    / MULTIPLY(0, tex.Color) → 0.0 (TEX_ENVIRONMENT / TEX_IMAGE / TEX_SKY
    Color; proven const 0). 4-deep Math / TEX_IMAGE / color-linked Mix /
    RGB Curves / Noise / non-zero tex Math / ADD/SUB/DIV/POWER with a tex
    Color input still refuse. Slice 2av: Mapping POINT accepted (map_type 0);
    VECTOR still map_type 2. TEXTURE accepted (2ay); NORMAL still refuse.
    """
    empty = {
        "world_strength": 0.0,
        "world_color": (0.0, 0.0, 0.0),
        "world_image_path": "",
        "world_image_colorspace": "",
        "world_projection": 0,
        "world_tex_vector_mode": 0,
        "world_map_location": (0.0, 0.0, 0.0),
        "world_map_rotation": (0.0, 0.0, 0.0),
        "world_map_scale": (1.0, 1.0, 1.0),
        "world_map_type": 2,
        **_world_sky_empty(),
        **_world_color_image_empty(),
        **_world_gamma_hsv_identity(),
    }
    world = getattr(scene, "world", None)
    if world is None:
        return empty
    if not getattr(world, "use_nodes", False) or world.node_tree is None:
        # Nodeless world color — Slice 2al accepts non-black world.color.
        col = getattr(world, "color", (0.0, 0.0, 0.0))
        rgb = (float(col[0]), float(col[1]), float(col[2]))
        if abs(rgb[0]) + abs(rgb[1]) + abs(rgb[2]) > 1e-6:
            return {**empty, "world_color": rgb, "world_strength": 1.0}
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
        world_color = (0.0, 0.0, 0.0)
        if color_sock is not None:
            col = color_sock.default_value
            world_color = (float(col[0]), float(col[1]), float(col[2]))
        return {
            **empty,
            "world_strength": strength,
            "world_color": world_color,
        }
    # Color linked — optional Mix peel (Slice 2aq), then Gamma/HueSat/
    # BrightContrast (2ap), then TEX_ENVIRONMENT (2aa), TEX_SKY (2am),
    # TEX_IMAGE (2an), or RGB/Mix (2al).
    links = list(getattr(color_sock, "links", None) or [])
    if len(links) != 1:
        raise QuantTraceSyncError(
            "world Background Color multi-link refused "
            "(Slice 2aa/2al/2am/2an/2ao/2ap/2aq)"
        )
    from_node = getattr(links[0], "from_node", None)
    from_sock = getattr(links[0], "from_socket", None)
    from_node, from_sock, mix = _peel_world_mix(from_node, from_sock)
    from_node, from_sock, unlinked_rgb, gh = _peel_world_gamma_hsv(
        from_node, from_sock
    )
    gh = {**gh, **mix}
    if unlinked_rgb is not None:
        return {
            **empty,
            "world_strength": strength,
            "world_color": unlinked_rgb,
            **gh,
        }
    ntype = getattr(from_node, "type", None) if from_node is not None else None
    if int(mix.get("world_mix_type", 0) or 0) != 0 and ntype in ("MIX", "MIX_RGB"):
        raise QuantTraceSyncError(
            "world Background Color second Mix refused (Slice 2aq)"
        )
    if ntype == "TEX_SKY":
        sky = _pack_world_sky_from_node(from_node)
        return {
            **empty,
            "world_strength": strength,
            "world_color": (0.0, 0.0, 0.0),
            **sky,
            **gh,
        }
    if ntype == "TEX_IMAGE":
        ci = _pack_world_color_image_from_node(from_node)
        return {
            **empty,
            "world_strength": strength,
            "world_color": (0.0, 0.0, 0.0),
            **ci,
            **gh,
        }
    if ntype != "TEX_ENVIRONMENT":
        world_color = _world_color_from_linked(from_node, from_sock)
        return {
            **empty,
            "world_strength": strength,
            "world_color": world_color,
            **gh,
        }
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
        "world_color": (0.0, 0.0, 0.0),
        "world_image_path": path,
        "world_image_colorspace": cs,
        "world_projection": proj,
        "world_tex_vector_mode": tex_vector_mode,
        "world_map_location": map_location,
        "world_map_rotation": map_rotation,
        "world_map_scale": map_scale,
        "world_map_type": map_type,
        "world_ob_ref": world_ob_ref,
        **_world_sky_empty(),
        **_world_color_image_empty(),
        **gh,
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
    _principled_from_material(mat, object_name=getattr(mesh_obj, "name", "") or "")
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
        # Slice 2bi: None-check — enable 0 / fac 0.0 valid — never `or`.
        "normal_invert_g_enable": int(
            pr["normal_invert_g_enable"]
            if pr.get("normal_invert_g_enable") is not None
            else 0
        ),
        "normal_invert_g_fac": float(
            pr["normal_invert_g_fac"] if pr.get("normal_invert_g_fac") is not None else 1.0
        ),
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
        "coat_normal_invert_g_enable": int(
            pr["coat_normal_invert_g_enable"]
            if pr.get("coat_normal_invert_g_enable") is not None
            else 0
        ),
        "coat_normal_invert_g_fac": float(
            pr["coat_normal_invert_g_fac"]
            if pr.get("coat_normal_invert_g_fac") is not None
            else 1.0
        ),
        "spec_tint_image_path": pr.get("spec_tint_image_path") or "",
        "spec_tint_image_colorspace": pr.get("spec_tint_image_colorspace") or "",
        "spec_tint_tex_vector_mode": int(pr.get("spec_tint_tex_vector_mode", 0) or 0),
        "spec_tint_map_location": loc("spec_tint_map_location", (0.0, 0.0, 0.0)),
        "spec_tint_map_rotation": loc("spec_tint_map_rotation", (0.0, 0.0, 0.0)),
        "spec_tint_map_scale": loc("spec_tint_map_scale", (1.0, 1.0, 1.0)),
        "spec_tint_map_type": int(pr.get("spec_tint_map_type", 2) if pr.get("spec_tint_map_type") is not None else 2),
        "specular_tint": tuple(
            float(x) for x in (pr.get("specular_tint") or (1.0, 1.0, 1.0))[:3]
        ),
        "spec_tint_mix_type": int(
            pr["spec_tint_mix_type"] if pr.get("spec_tint_mix_type") is not None else 0
        ),
        "spec_tint_mix_fac": float(
            pr["spec_tint_mix_fac"] if pr.get("spec_tint_mix_fac") is not None else 0.5
        ),
        "spec_tint_mix_other": tuple(
            float(x) for x in (pr.get("spec_tint_mix_other") or (0.0, 0.0, 0.0))[:3]
        ),
        "spec_tint_mix_chain_is_a": int(
            pr["spec_tint_mix_chain_is_a"] if pr.get("spec_tint_mix_chain_is_a") is not None else 1
        ),
        "spec_tint_mix_clamp_factor": int(
            pr["spec_tint_mix_clamp_factor"] if pr.get("spec_tint_mix_clamp_factor") is not None else 0
        ),
        "spec_tint_mix_clamp_result": int(
            pr["spec_tint_mix_clamp_result"] if pr.get("spec_tint_mix_clamp_result") is not None else 0
        ),
        "spec_tint_mix_b_image_path": pr.get("spec_tint_mix_b_image_path") or "",
        "spec_tint_mix_b_image_colorspace": pr.get("spec_tint_mix_b_image_colorspace") or "",
        "spec_tint_gamma": float(
            pr["spec_tint_gamma"] if pr.get("spec_tint_gamma") is not None else 1.0
        ),
        "spec_tint_hsv_hue": float(
            pr["spec_tint_hsv_hue"] if pr.get("spec_tint_hsv_hue") is not None else 0.5
        ),
        "spec_tint_hsv_sat": float(
            pr["spec_tint_hsv_sat"] if pr.get("spec_tint_hsv_sat") is not None else 1.0
        ),
        "spec_tint_hsv_val": float(
            pr["spec_tint_hsv_val"] if pr.get("spec_tint_hsv_val") is not None else 1.0
        ),
        "spec_tint_hsv_fac": float(
            pr["spec_tint_hsv_fac"] if pr.get("spec_tint_hsv_fac") is not None else 1.0
        ),
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
        "bump_noise_enable": int(
            pr["bump_noise_enable"]
            if pr.get("bump_noise_enable") is not None
            else 0
        ),
        "bump_noise_dimensions": int(
            pr["bump_noise_dimensions"]
            if pr.get("bump_noise_dimensions") is not None
            else 3
        ),
        "bump_noise_type": int(
            pr["bump_noise_type"]
            if pr.get("bump_noise_type") is not None
            else 1
        ),
        "bump_noise_normalize": int(
            pr["bump_noise_normalize"]
            if pr.get("bump_noise_normalize") is not None
            else 1
        ),
        "bump_noise_w": float(
            pr["bump_noise_w"]
            if pr.get("bump_noise_w") is not None
            else 0.0
        ),
        "bump_noise_scale": float(
            pr["bump_noise_scale"]
            if pr.get("bump_noise_scale") is not None
            else 5.0
        ),
        "bump_noise_detail": float(
            pr["bump_noise_detail"]
            if pr.get("bump_noise_detail") is not None
            else 2.0
        ),
        "bump_noise_roughness": float(
            pr["bump_noise_roughness"]
            if pr.get("bump_noise_roughness") is not None
            else 0.5
        ),
        "bump_noise_lacunarity": float(
            pr["bump_noise_lacunarity"]
            if pr.get("bump_noise_lacunarity") is not None
            else 2.0
        ),
        "bump_noise_offset": float(
            pr["bump_noise_offset"]
            if pr.get("bump_noise_offset") is not None
            else 0.0
        ),
        "bump_noise_gain": float(
            pr["bump_noise_gain"]
            if pr.get("bump_noise_gain") is not None
            else 1.0
        ),
        "bump_noise_distortion": float(
            pr["bump_noise_distortion"]
            if pr.get("bump_noise_distortion") is not None
            else 0.0
        ),
        "bump_noise_use_color": int(
            pr["bump_noise_use_color"]
            if pr.get("bump_noise_use_color") is not None
            else 0
        ),
        "bump_separate_enable": int(
            pr["bump_separate_enable"]
            if pr.get("bump_separate_enable") is not None
            else 0
        ),
        "bump_separate_channel": int(
            pr["bump_separate_channel"]
            if pr.get("bump_separate_channel") is not None
            else 2
        ),
        "bevel_enable": int(pr.get("bevel_enable", 0) or 0),
        "bevel_samples": int(
            pr["bevel_samples"] if pr.get("bevel_samples") is not None else 4
        ),
        "bevel_radius": float(
            pr["bevel_radius"] if pr.get("bevel_radius") is not None else 0.05
        ),
        "rough_ramp": list(pr.get("rough_ramp") or []),
        "rough_ramp_alpha": list(pr.get("rough_ramp_alpha") or []),
        "rough_ramp_n": int(
            pr["rough_ramp_n"] if pr.get("rough_ramp_n") is not None else 0
        ),
        "rough_ramp_interpolate": int(
            pr["rough_ramp_interpolate"]
            if pr.get("rough_ramp_interpolate") is not None
            else 1
        ),
        "rough_ramp_fac": float(
            pr["rough_ramp_fac"] if pr.get("rough_ramp_fac") is not None else 0.5
        ),
        "rough_ramp_noise_enable": int(
            pr["rough_ramp_noise_enable"]
            if pr.get("rough_ramp_noise_enable") is not None
            else 0
        ),
        "rough_ramp_noise_dimensions": int(
            pr["rough_ramp_noise_dimensions"]
            if pr.get("rough_ramp_noise_dimensions") is not None
            else 3
        ),
        "rough_ramp_noise_type": int(
            pr["rough_ramp_noise_type"]
            if pr.get("rough_ramp_noise_type") is not None
            else 1
        ),
        "rough_ramp_noise_normalize": int(
            pr["rough_ramp_noise_normalize"]
            if pr.get("rough_ramp_noise_normalize") is not None
            else 1
        ),
        "rough_ramp_noise_w": float(
            pr["rough_ramp_noise_w"]
            if pr.get("rough_ramp_noise_w") is not None
            else 0.0
        ),
        "rough_ramp_noise_scale": float(
            pr["rough_ramp_noise_scale"]
            if pr.get("rough_ramp_noise_scale") is not None
            else 5.0
        ),
        "rough_ramp_noise_detail": float(
            pr["rough_ramp_noise_detail"]
            if pr.get("rough_ramp_noise_detail") is not None
            else 2.0
        ),
        "rough_ramp_noise_roughness": float(
            pr["rough_ramp_noise_roughness"]
            if pr.get("rough_ramp_noise_roughness") is not None
            else 0.5
        ),
        "rough_ramp_noise_lacunarity": float(
            pr["rough_ramp_noise_lacunarity"]
            if pr.get("rough_ramp_noise_lacunarity") is not None
            else 2.0
        ),
        "rough_ramp_noise_offset": float(
            pr["rough_ramp_noise_offset"]
            if pr.get("rough_ramp_noise_offset") is not None
            else 0.0
        ),
        "rough_ramp_noise_gain": float(
            pr["rough_ramp_noise_gain"]
            if pr.get("rough_ramp_noise_gain") is not None
            else 1.0
        ),
        "rough_ramp_noise_distortion": float(
            pr["rough_ramp_noise_distortion"]
            if pr.get("rough_ramp_noise_distortion") is not None
            else 0.0
        ),
        "rough_ramp_noise_use_color": int(
            pr["rough_ramp_noise_use_color"]
            if pr.get("rough_ramp_noise_use_color") is not None
            else 0
        ),
        "rough_invert_enable": int(
            pr["rough_invert_enable"]
            if pr.get("rough_invert_enable") is not None
            else 0
        ),
        "rough_invert_fac": float(
            pr["rough_invert_fac"] if pr.get("rough_invert_fac") is not None else 1.0
        ),
        "rough_separate_enable": int(
            pr["rough_separate_enable"]
            if pr.get("rough_separate_enable") is not None
            else 0
        ),
        "rough_separate_channel": int(
            pr["rough_separate_channel"]
            if pr.get("rough_separate_channel") is not None
            else 1
        ),
        "glass_bsdf_enable": int(
            pr["glass_bsdf_enable"]
            if pr.get("glass_bsdf_enable") is not None
            else 0
        ),
        "glass_distribution": int(
            pr["glass_distribution"]
            if pr.get("glass_distribution") is not None
            else 0
        ),
        "thin_wall": int(pr.get("thin_wall", 0) or 0),
        "transmission_weight": float(
            pr.get("transmission_weight", 0.0) if pr.get("transmission_weight") is not None else 0.0
        ),
        # Slice 2ax: None-check — do not use `or` (gamma 1.0 / hue 0.5 / fac 1.0 identity).
        "base_gamma": float(
            pr["base_gamma"] if pr.get("base_gamma") is not None else 1.0
        ),
        "base_hsv_hue": float(
            pr["base_hsv_hue"] if pr.get("base_hsv_hue") is not None else 0.5
        ),
        "base_hsv_sat": float(
            pr["base_hsv_sat"] if pr.get("base_hsv_sat") is not None else 1.0
        ),
        "base_hsv_val": float(
            pr["base_hsv_val"] if pr.get("base_hsv_val") is not None else 1.0
        ),
        "base_hsv_fac": float(
            pr["base_hsv_fac"] if pr.get("base_hsv_fac") is not None else 1.0
        ),
        # Slice 2ay: None-check — do not use `or` (type 0 / fac 0.0 valid).
        "base_mix_type": int(
            pr["base_mix_type"] if pr.get("base_mix_type") is not None else 0
        ),
        "base_mix_fac": float(
            pr["base_mix_fac"] if pr.get("base_mix_fac") is not None else 0.5
        ),
        "base_mix_other": tuple(
            float(x) for x in (pr.get("base_mix_other") or (0.0, 0.0, 0.0))[:3]
        ),
        "base_mix_chain_is_a": int(
            pr["base_mix_chain_is_a"] if pr.get("base_mix_chain_is_a") is not None else 1
        ),
        "base_mix_clamp_factor": int(
            pr["base_mix_clamp_factor"] if pr.get("base_mix_clamp_factor") is not None else 0
        ),
        "base_mix_clamp_result": int(
            pr["base_mix_clamp_result"] if pr.get("base_mix_clamp_result") is not None else 0
        ),
        "base_mix_b_image_path": pr.get("base_mix_b_image_path") or "",
        "base_mix_b_image_colorspace": pr.get("base_mix_b_image_colorspace") or "",
        "base_mix_fresnel_enable": int(
            pr["base_mix_fresnel_enable"]
            if pr.get("base_mix_fresnel_enable") is not None
            else 0
        ),
        "base_mix_fresnel_ior": float(
            pr["base_mix_fresnel_ior"]
            if pr.get("base_mix_fresnel_ior") is not None
            else 1.45
        ),
        # Slice 2bd: None-check — n==0 / fac 0.0 valid.
        "base_curves": list(pr.get("base_curves") or []) if pr.get("base_curves") else None,
        "base_curves_n": int(
            pr["base_curves_n"] if pr.get("base_curves_n") is not None else 0
        ),
        "base_curves_min_x": float(
            pr["base_curves_min_x"] if pr.get("base_curves_min_x") is not None else 0.0
        ),
        "base_curves_max_x": float(
            pr["base_curves_max_x"] if pr.get("base_curves_max_x") is not None else 1.0
        ),
        "base_curves_fac": float(
            pr["base_curves_fac"] if pr.get("base_curves_fac") is not None else 1.0
        ),
        "base_curves_extrapolate": int(
            pr["base_curves_extrapolate"] if pr.get("base_curves_extrapolate") is not None else 1
        ),
        # Slice 2bh: mix-side LUT. n==0 / fac 0.0 valid — never `or`.
        "base_mix_curves": list(pr.get("base_mix_curves") or []) if pr.get("base_mix_curves") else None,
        "base_mix_curves_n": int(
            pr["base_mix_curves_n"] if pr.get("base_mix_curves_n") is not None else 0
        ),
        "base_mix_curves_min_x": float(
            pr["base_mix_curves_min_x"] if pr.get("base_mix_curves_min_x") is not None else 0.0
        ),
        "base_mix_curves_max_x": float(
            pr["base_mix_curves_max_x"] if pr.get("base_mix_curves_max_x") is not None else 1.0
        ),
        "base_mix_curves_fac": float(
            pr["base_mix_curves_fac"] if pr.get("base_mix_curves_fac") is not None else 1.0
        ),
        "base_mix_curves_extrapolate": int(
            pr["base_mix_curves_extrapolate"] if pr.get("base_mix_curves_extrapolate") is not None else 1
        ),
        "base_mix_curves_on_a": int(
            pr["base_mix_curves_on_a"] if pr.get("base_mix_curves_on_a") is not None else 1
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
        or (pr.get("spec_tint_mix_b_image_path") or "")
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
    pr = _principled_from_material(
        mat, object_name=getattr(mesh_obj, "name", "") or ""
    )
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


QT_MAX_MESHES = 2048
QT_MAX_LIGHTS = 128


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
        _principled_from_material(
            mat, object_name=getattr(mesh_obj, "name", "") or ""
        )
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
        pr = _principled_from_material(
            mat, object_name=getattr(mesh_obj, "name", "") or ""
        )
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
    # Slice 2bk: specular_tint default (1,1,1); mix type 0 / fac 0.0 valid — never `or`.
    st = packed.get("specular_tint") or (1.0, 1.0, 1.0)
    for i, v in enumerate(st[:3]):
        desc.specular_tint[i] = float(v)
    def _bi_st(key, default):
        v = packed.get(key, default)
        if v is None:
            return int(default)
        return int(v)
    def _bf_st(key, default):
        v = packed.get(key, default)
        if v is None:
            return float(default)
        return float(v)
    desc.spec_tint_mix_type = _bi_st("spec_tint_mix_type", 0)
    desc.spec_tint_mix_fac = _bf_st("spec_tint_mix_fac", 0.5)
    sto = packed.get("spec_tint_mix_other") or (0.0, 0.0, 0.0)
    for i, v in enumerate(sto[:3]):
        desc.spec_tint_mix_other[i] = float(v)
    desc.spec_tint_mix_chain_is_a = _bi_st("spec_tint_mix_chain_is_a", 1)
    desc.spec_tint_mix_clamp_factor = _bi_st("spec_tint_mix_clamp_factor", 0)
    desc.spec_tint_mix_clamp_result = _bi_st("spec_tint_mix_clamp_result", 0)
    stb = (packed.get("spec_tint_mix_b_image_path") or "").encode("utf-8")
    stbcs = (packed.get("spec_tint_mix_b_image_colorspace") or "").encode("utf-8")
    keep.append(stb)
    keep.append(stbcs)
    desc.spec_tint_mix_b_image_path = stb if stb else None
    desc.spec_tint_mix_b_image_colorspace = stbcs if stbcs else None
    desc.spec_tint_gamma = _bf_st("spec_tint_gamma", 1.0)
    desc.spec_tint_hsv_hue = _bf_st("spec_tint_hsv_hue", 0.5)
    desc.spec_tint_hsv_sat = _bf_st("spec_tint_hsv_sat", 1.0)
    desc.spec_tint_hsv_val = _bf_st("spec_tint_hsv_val", 1.0)
    desc.spec_tint_hsv_fac = _bf_st("spec_tint_hsv_fac", 1.0)

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
    def _bn_i(key, default):
        v = packed.get(key, default)
        if v is None:
            return int(default)
        return int(v)
    def _bn_f(key, default):
        v = packed.get(key, default)
        if v is None:
            return float(default)
        return float(v)
    desc.bump_noise_enable = _bn_i("bump_noise_enable", 0)
    desc.bump_noise_dimensions = _bn_i("bump_noise_dimensions", 3)
    desc.bump_noise_type = _bn_i("bump_noise_type", 1)
    desc.bump_noise_normalize = _bn_i("bump_noise_normalize", 1)
    desc.bump_noise_w = _bn_f("bump_noise_w", 0.0)
    desc.bump_noise_scale = _bn_f("bump_noise_scale", 5.0)
    desc.bump_noise_detail = _bn_f("bump_noise_detail", 2.0)
    desc.bump_noise_roughness = _bn_f("bump_noise_roughness", 0.5)
    desc.bump_noise_lacunarity = _bn_f("bump_noise_lacunarity", 2.0)
    desc.bump_noise_offset = _bn_f("bump_noise_offset", 0.0)
    desc.bump_noise_gain = _bn_f("bump_noise_gain", 1.0)
    desc.bump_noise_distortion = _bn_f("bump_noise_distortion", 0.0)
    desc.bump_noise_use_color = _bn_i("bump_noise_use_color", 0)
    desc.bump_separate_enable = _bn_i("bump_separate_enable", 0)
    desc.bump_separate_channel = _bn_i("bump_separate_channel", 2)
    desc.thin_wall = int(packed.get("thin_wall", 0) or 0)
    desc.transmission_weight = float(
        packed.get("transmission_weight", 0.0) if packed.get("transmission_weight") is not None else 0.0
    )
    desc.tex_ob_use_transform = int(packed.get("tex_ob_use_transform", 0) or 0)
    tfm = packed.get("tex_ob_tfm") or _identity_3x4()
    for i, v in enumerate(tfm):
        desc.tex_ob_tfm[i] = float(v)
    # Slice 2ax: identity defaults. Do not use `or` — hue 0.0 / gamma 1.0 valid.
    def _bf(key, default):
        v = packed.get(key, default)
        if v is None:
            return float(default)
        return float(v)
    desc.base_gamma = _bf("base_gamma", 1.0)
    desc.base_hsv_hue = _bf("base_hsv_hue", 0.5)
    desc.base_hsv_sat = _bf("base_hsv_sat", 1.0)
    desc.base_hsv_val = _bf("base_hsv_val", 1.0)
    desc.base_hsv_fac = _bf("base_hsv_fac", 1.0)
    # Slice 2ay: type 0 / fac 0.0 valid — never `or` on type/fac.
    def _bi(key, default):
        v = packed.get(key, default)
        if v is None:
            return int(default)
        return int(v)
    desc.base_mix_type = _bi("base_mix_type", 0)
    desc.base_mix_fac = _bf("base_mix_fac", 0.5)
    other = packed.get("base_mix_other") or (0.0, 0.0, 0.0)
    for i, v in enumerate(other[:3]):
        desc.base_mix_other[i] = float(v)
    desc.base_mix_chain_is_a = _bi("base_mix_chain_is_a", 1)
    desc.base_mix_clamp_factor = _bi("base_mix_clamp_factor", 0)
    desc.base_mix_clamp_result = _bi("base_mix_clamp_result", 0)
    bip = (packed.get("base_mix_b_image_path") or "").encode("utf-8")
    bics = (packed.get("base_mix_b_image_colorspace") or "").encode("utf-8")
    keep.append(bip)
    keep.append(bics)
    desc.base_mix_b_image_path = bip if bip else None
    desc.base_mix_b_image_colorspace = bics if bics else None
    # Slice 2bf: enable 0 / ior 1.45 — never `or` on enable/ior.
    desc.base_mix_fresnel_enable = _bi("base_mix_fresnel_enable", 0)
    desc.base_mix_fresnel_ior = _bf("base_mix_fresnel_ior", 1.45)
    # Slice 2bd: n==0 skip; fac 0.0 valid — never `or` on n/fac.
    desc.base_curves_min_x = _bf("base_curves_min_x", 0.0)
    desc.base_curves_max_x = _bf("base_curves_max_x", 1.0)
    desc.base_curves_fac = _bf("base_curves_fac", 1.0)
    _exb = packed.get("base_curves_extrapolate", 1)
    desc.base_curves_extrapolate = 1 if _exb is None else int(_exb)
    bcurves_list = packed.get("base_curves") or []
    bcurves_n = packed.get("base_curves_n", 0)
    bcurves_n = 0 if bcurves_n is None else int(bcurves_n)
    if bcurves_list and bcurves_n > 0:
        bflat = [float(v) for v in bcurves_list]
        if len(bflat) < bcurves_n * 3:
            raise QuantTraceSyncError(
                f"base_curves len {len(bflat)} < n*3={bcurves_n * 3} (Slice 2bd)"
            )
        bcurves_buf = (ctypes.c_float * (bcurves_n * 3))(*bflat[: bcurves_n * 3])
        keep.append(bcurves_buf)
        desc.base_curves = ctypes.cast(bcurves_buf, ctypes.POINTER(ctypes.c_float))
        desc.base_curves_n = bcurves_n
    else:
        desc.base_curves = None
        desc.base_curves_n = 0
    # Slice 2bh: mix-side LUT. n==0 skip; fac 0.0 / on_a 0 valid — never `or`.
    desc.base_mix_curves_min_x = _bf("base_mix_curves_min_x", 0.0)
    desc.base_mix_curves_max_x = _bf("base_mix_curves_max_x", 1.0)
    desc.base_mix_curves_fac = _bf("base_mix_curves_fac", 1.0)
    _exm = packed.get("base_mix_curves_extrapolate", 1)
    desc.base_mix_curves_extrapolate = 1 if _exm is None else int(_exm)
    desc.base_mix_curves_on_a = _bi("base_mix_curves_on_a", 1)
    # Slice 2bi: enable 0 / fac 0.0 valid — never `or`.
    desc.normal_invert_g_enable = _bi("normal_invert_g_enable", 0)
    desc.normal_invert_g_fac = _bf("normal_invert_g_fac", 1.0)
    desc.coat_normal_invert_g_enable = _bi("coat_normal_invert_g_enable", 0)
    desc.coat_normal_invert_g_fac = _bf("coat_normal_invert_g_fac", 1.0)
    mcurves_list = packed.get("base_mix_curves") or []
    mcurves_n = packed.get("base_mix_curves_n", 0)
    mcurves_n = 0 if mcurves_n is None else int(mcurves_n)
    if mcurves_list and mcurves_n > 0:
        mflat = [float(v) for v in mcurves_list]
        if len(mflat) < mcurves_n * 3:
            raise QuantTraceSyncError(
                f"base_mix_curves len {len(mflat)} < n*3={mcurves_n * 3} (Slice 2bh)"
            )
        mcurves_buf = (ctypes.c_float * (mcurves_n * 3))(*mflat[: mcurves_n * 3])
        keep.append(mcurves_buf)
        desc.base_mix_curves = ctypes.cast(mcurves_buf, ctypes.POINTER(ctypes.c_float))
        desc.base_mix_curves_n = mcurves_n
    else:
        desc.base_mix_curves = None
        desc.base_mix_curves_n = 0
    # Slice 2az: bevel_enable 0 / samples 4 / radius 0.05 — never `or` on samples.
    desc.bevel_enable = _bi("bevel_enable", 0)
    desc.bevel_samples = _bi("bevel_samples", 4)
    desc.bevel_radius = _bf("bevel_radius", 0.05)
    # Slice 2ba: n==0 skip; interpolate 0 is CONSTANT — never `or` on n/interp.
    ramp_n = packed.get("rough_ramp_n", 0)
    ramp_n = 0 if ramp_n is None else int(ramp_n)
    ramp_list = packed.get("rough_ramp") or []
    ramp_alpha_list = packed.get("rough_ramp_alpha") or []
    desc.rough_ramp_interpolate = _bi("rough_ramp_interpolate", 1)
    desc.rough_ramp_fac = _bf("rough_ramp_fac", 0.5)
    # Slice 2bb: enable 0 / type 0 / scale 0 valid — never `or` on ints/floats.
    desc.rough_ramp_noise_enable = _bi("rough_ramp_noise_enable", 0)
    desc.rough_ramp_noise_dimensions = _bi("rough_ramp_noise_dimensions", 3)
    desc.rough_ramp_noise_type = _bi("rough_ramp_noise_type", 1)
    desc.rough_ramp_noise_normalize = _bi("rough_ramp_noise_normalize", 1)
    desc.rough_ramp_noise_w = _bf("rough_ramp_noise_w", 0.0)
    desc.rough_ramp_noise_scale = _bf("rough_ramp_noise_scale", 5.0)
    desc.rough_ramp_noise_detail = _bf("rough_ramp_noise_detail", 2.0)
    desc.rough_ramp_noise_roughness = _bf("rough_ramp_noise_roughness", 0.5)
    desc.rough_ramp_noise_lacunarity = _bf("rough_ramp_noise_lacunarity", 2.0)
    desc.rough_ramp_noise_offset = _bf("rough_ramp_noise_offset", 0.0)
    desc.rough_ramp_noise_gain = _bf("rough_ramp_noise_gain", 1.0)
    desc.rough_ramp_noise_distortion = _bf("rough_ramp_noise_distortion", 0.0)
    desc.rough_ramp_noise_use_color = _bi("rough_ramp_noise_use_color", 0)
    # Slice 2be: enable 0 / fac 0.0 valid — never `or` on enable/fac.
    desc.rough_invert_enable = _bi("rough_invert_enable", 0)
    desc.rough_invert_fac = _bf("rough_invert_fac", 1.0)
    # Slice 2bj: enable 0 / channel 0 valid — never `or` on enable/channel.
    desc.rough_separate_enable = _bi("rough_separate_enable", 0)
    desc.rough_separate_channel = _bi("rough_separate_channel", 1)
    # Slice 2bm: enable 0 / distribution 0 valid — never `or` on enable/dist.
    desc.glass_bsdf_enable = _bi("glass_bsdf_enable", 0)
    desc.glass_distribution = _bi("glass_distribution", 0)
    if ramp_list and ramp_n > 0:
        flat = [float(v) for v in ramp_list]
        if len(flat) < ramp_n * 3:
            raise QuantTraceSyncError(
                f"rough_ramp len {len(flat)} < n*3={ramp_n * 3} (Slice 2ba)"
            )
        ramp_buf = (ctypes.c_float * (ramp_n * 3))(*flat[: ramp_n * 3])
        keep.append(ramp_buf)
        desc.rough_ramp = ctypes.cast(ramp_buf, ctypes.POINTER(ctypes.c_float))
        desc.rough_ramp_n = ramp_n
        if ramp_alpha_list:
            aflat = [float(v) for v in ramp_alpha_list]
            if len(aflat) < ramp_n:
                raise QuantTraceSyncError(
                    f"rough_ramp_alpha len {len(aflat)} < n={ramp_n} (Slice 2ba)"
                )
            abuf = (ctypes.c_float * ramp_n)(*aflat[:ramp_n])
            keep.append(abuf)
            desc.rough_ramp_alpha = ctypes.cast(
                abuf, ctypes.POINTER(ctypes.c_float)
            )
        else:
            desc.rough_ramp_alpha = None
    else:
        desc.rough_ramp = None
        desc.rough_ramp_alpha = None
        desc.rough_ramp_n = 0


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
            ("world_color", ctypes.c_float * 3),
            ("world_sky_type", ctypes.c_int),
            ("world_sky_sun_direction", ctypes.c_float * 3),
            ("world_sky_turbidity", ctypes.c_float),
            ("world_sky_ground_albedo", ctypes.c_float),
            ("world_sky_sun_disc", ctypes.c_int),
            ("world_sky_sun_size", ctypes.c_float),
            ("world_sky_sun_intensity", ctypes.c_float),
            ("world_sky_sun_elevation", ctypes.c_float),
            ("world_sky_sun_rotation", ctypes.c_float),
            ("world_sky_altitude", ctypes.c_float),
            ("world_sky_air_density", ctypes.c_float),
            ("world_sky_aerosol_density", ctypes.c_float),
            ("world_sky_ozone_density", ctypes.c_float),
            ("world_color_image_path", ctypes.c_char_p),
            ("world_color_image_colorspace", ctypes.c_char_p),
            ("world_color_image_projection", ctypes.c_int),
            ("world_gamma", ctypes.c_float),
            ("world_hsv_hue", ctypes.c_float),
            ("world_hsv_sat", ctypes.c_float),
            ("world_hsv_val", ctypes.c_float),
            ("world_hsv_fac", ctypes.c_float),
            ("world_bright", ctypes.c_float),
            ("world_contrast", ctypes.c_float),
            ("world_mix_type", ctypes.c_int),
            ("world_mix_fac", ctypes.c_float),
            ("world_mix_other", ctypes.c_float * 3),
            ("world_mix_chain_is_a", ctypes.c_int),
            ("world_mix_clamp_factor", ctypes.c_int),
            ("world_mix_clamp_result", ctypes.c_int),
            ("world_curves", ctypes.POINTER(ctypes.c_float)),
            ("world_curves_n", ctypes.c_int),
            ("world_curves_min_x", ctypes.c_float),
            ("world_curves_max_x", ctypes.c_float),
            ("world_curves_fac", ctypes.c_float),
            ("world_curves_extrapolate", ctypes.c_int),
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
            ("specular_tint", ctypes.c_float * 3),
            ("spec_tint_mix_type", ctypes.c_int),
            ("spec_tint_mix_fac", ctypes.c_float),
            ("spec_tint_mix_other", ctypes.c_float * 3),
            ("spec_tint_mix_chain_is_a", ctypes.c_int),
            ("spec_tint_mix_clamp_factor", ctypes.c_int),
            ("spec_tint_mix_clamp_result", ctypes.c_int),
            ("spec_tint_mix_b_image_path", ctypes.c_char_p),
            ("spec_tint_mix_b_image_colorspace", ctypes.c_char_p),
            ("spec_tint_gamma", ctypes.c_float),
            ("spec_tint_hsv_hue", ctypes.c_float),
            ("spec_tint_hsv_sat", ctypes.c_float),
            ("spec_tint_hsv_val", ctypes.c_float),
            ("spec_tint_hsv_fac", ctypes.c_float),
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
            ("bump_noise_enable", ctypes.c_int),
            ("bump_noise_dimensions", ctypes.c_int),
            ("bump_noise_type", ctypes.c_int),
            ("bump_noise_normalize", ctypes.c_int),
            ("bump_noise_w", ctypes.c_float),
            ("bump_noise_scale", ctypes.c_float),
            ("bump_noise_detail", ctypes.c_float),
            ("bump_noise_roughness", ctypes.c_float),
            ("bump_noise_lacunarity", ctypes.c_float),
            ("bump_noise_offset", ctypes.c_float),
            ("bump_noise_gain", ctypes.c_float),
            ("bump_noise_distortion", ctypes.c_float),
            ("bump_noise_use_color", ctypes.c_int),
            ("bump_separate_enable", ctypes.c_int),
            ("bump_separate_channel", ctypes.c_int),
            ("thin_wall", ctypes.c_int),
            ("transmission_weight", ctypes.c_float),
            ("tex_ob_use_transform", ctypes.c_int),
            ("tex_ob_tfm", ctypes.c_float * 12),
            ("base_gamma", ctypes.c_float),
            ("base_hsv_hue", ctypes.c_float),
            ("base_hsv_sat", ctypes.c_float),
            ("base_hsv_val", ctypes.c_float),
            ("base_hsv_fac", ctypes.c_float),
            ("base_mix_type", ctypes.c_int),
            ("base_mix_fac", ctypes.c_float),
            ("base_mix_other", ctypes.c_float * 3),
            ("base_mix_chain_is_a", ctypes.c_int),
            ("base_mix_clamp_factor", ctypes.c_int),
            ("base_mix_clamp_result", ctypes.c_int),
            ("base_mix_b_image_path", ctypes.c_char_p),
            ("base_mix_b_image_colorspace", ctypes.c_char_p),
            ("base_mix_fresnel_enable", ctypes.c_int),
            ("base_mix_fresnel_ior", ctypes.c_float),
            ("base_curves", ctypes.POINTER(ctypes.c_float)),
            ("base_curves_n", ctypes.c_int),
            ("base_curves_min_x", ctypes.c_float),
            ("base_curves_max_x", ctypes.c_float),
            ("base_curves_fac", ctypes.c_float),
            ("base_curves_extrapolate", ctypes.c_int),
            ("base_mix_curves", ctypes.POINTER(ctypes.c_float)),
            ("base_mix_curves_n", ctypes.c_int),
            ("base_mix_curves_min_x", ctypes.c_float),
            ("base_mix_curves_max_x", ctypes.c_float),
            ("base_mix_curves_fac", ctypes.c_float),
            ("base_mix_curves_extrapolate", ctypes.c_int),
            ("base_mix_curves_on_a", ctypes.c_int),
            ("normal_invert_g_enable", ctypes.c_int),
            ("normal_invert_g_fac", ctypes.c_float),
            ("coat_normal_invert_g_enable", ctypes.c_int),
            ("coat_normal_invert_g_fac", ctypes.c_float),
            ("bevel_enable", ctypes.c_int),
            ("bevel_samples", ctypes.c_int),
            ("bevel_radius", ctypes.c_float),
            ("rough_ramp", ctypes.POINTER(ctypes.c_float)),
            ("rough_ramp_alpha", ctypes.POINTER(ctypes.c_float)),
            ("rough_ramp_n", ctypes.c_int),
            ("rough_ramp_interpolate", ctypes.c_int),
            ("rough_ramp_fac", ctypes.c_float),
            ("rough_ramp_noise_enable", ctypes.c_int),
            ("rough_ramp_noise_dimensions", ctypes.c_int),
            ("rough_ramp_noise_type", ctypes.c_int),
            ("rough_ramp_noise_normalize", ctypes.c_int),
            ("rough_ramp_noise_w", ctypes.c_float),
            ("rough_ramp_noise_scale", ctypes.c_float),
            ("rough_ramp_noise_detail", ctypes.c_float),
            ("rough_ramp_noise_roughness", ctypes.c_float),
            ("rough_ramp_noise_lacunarity", ctypes.c_float),
            ("rough_ramp_noise_offset", ctypes.c_float),
            ("rough_ramp_noise_gain", ctypes.c_float),
            ("rough_ramp_noise_distortion", ctypes.c_float),
            ("rough_ramp_noise_use_color", ctypes.c_int),
            ("rough_invert_enable", ctypes.c_int),
            ("rough_invert_fac", ctypes.c_float),
            ("rough_separate_enable", ctypes.c_int),
            ("rough_separate_channel", ctypes.c_int),
            ("glass_bsdf_enable", ctypes.c_int),
            ("glass_distribution", ctypes.c_int),
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
    _wmt = packed.get("world_map_type", 2)
    desc.world_map_type = int(_wmt if _wmt is not None else 2)  # POINT=0 is valid
    desc.world_ob_use_transform = int(packed.get("world_ob_use_transform", 0) or 0)
    tfm = packed.get("world_ob_tfm") or _identity_3x4()
    for i, v in enumerate(tfm):
        desc.world_ob_tfm[i] = float(v)
    wc = packed.get("world_color") or (0.0, 0.0, 0.0)
    for i, v in enumerate(wc[:3]):
        desc.world_color[i] = float(v)
    desc.world_sky_type = int(packed.get("world_sky_type", 0) or 0)
    sd = packed.get("world_sky_sun_direction") or (0.0, 0.0, 0.0)
    for i, v in enumerate(sd[:3]):
        desc.world_sky_sun_direction[i] = float(v)
    desc.world_sky_turbidity = float(packed.get("world_sky_turbidity", 0.0) or 0.0)
    desc.world_sky_ground_albedo = float(packed.get("world_sky_ground_albedo", 0.0) or 0.0)
    desc.world_sky_sun_disc = int(packed.get("world_sky_sun_disc", 0) or 0)
    desc.world_sky_sun_size = float(packed.get("world_sky_sun_size", 0.0) or 0.0)
    desc.world_sky_sun_intensity = float(packed.get("world_sky_sun_intensity", 0.0) or 0.0)
    desc.world_sky_sun_elevation = float(packed.get("world_sky_sun_elevation", 0.0) or 0.0)
    desc.world_sky_sun_rotation = float(packed.get("world_sky_sun_rotation", 0.0) or 0.0)
    desc.world_sky_altitude = float(packed.get("world_sky_altitude", 0.0) or 0.0)
    desc.world_sky_air_density = float(packed.get("world_sky_air_density", 0.0) or 0.0)
    desc.world_sky_aerosol_density = float(packed.get("world_sky_aerosol_density", 0.0) or 0.0)
    desc.world_sky_ozone_density = float(packed.get("world_sky_ozone_density", 0.0) or 0.0)
    # Slice 2an: Image Texture → world Color (strings filled by callers into
    # desc + keep-alive; projection int here).
    desc.world_color_image_projection = int(
        packed.get("world_color_image_projection", 0) or 0
    )
    # Slice 2ao/2ap: identity defaults. Do not use `or` — 0.0 is a valid gamma/bright.
    def _wf(key, default):
        v = packed.get(key, default)
        if v is None:
            return float(default)
        return float(v)
    desc.world_gamma = _wf("world_gamma", 1.0)
    desc.world_hsv_hue = _wf("world_hsv_hue", 0.5)
    desc.world_hsv_sat = _wf("world_hsv_sat", 1.0)
    desc.world_hsv_val = _wf("world_hsv_val", 1.0)
    desc.world_hsv_fac = _wf("world_hsv_fac", 1.0)
    # Slice 2ap: identity defaults bright=0 contrast=0. Do not use `or`.
    desc.world_bright = _wf("world_bright", 0.0)
    desc.world_contrast = _wf("world_contrast", 0.0)
    # Slice 2aq: mix_type=0 identity. Do not use `or` on floats / chain_is_a=0.
    desc.world_mix_type = int(packed.get("world_mix_type", 0) or 0)
    desc.world_mix_fac = _wf("world_mix_fac", 0.5)
    mo = packed.get("world_mix_other") or (0.0, 0.0, 0.0)
    for i in range(3):
        desc.world_mix_other[i] = float(mo[i])
    _cia = packed.get("world_mix_chain_is_a", 1)
    desc.world_mix_chain_is_a = 0 if _cia is None else int(_cia)
    desc.world_mix_clamp_factor = int(packed.get("world_mix_clamp_factor", 0) or 0)
    desc.world_mix_clamp_result = int(packed.get("world_mix_clamp_result", 0) or 0)
    # Slice 2as defaults; pointer filled by to_ctypes / to_ctypes_scene.
    desc.world_curves = None
    desc.world_curves_n = 0
    desc.world_curves_min_x = _wf("world_curves_min_x", 0.0)
    desc.world_curves_max_x = _wf("world_curves_max_x", 1.0)
    desc.world_curves_fac = _wf("world_curves_fac", 1.0)
    _ex = packed.get("world_curves_extrapolate", 1)
    desc.world_curves_extrapolate = 1 if _ex is None else int(_ex)

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
    wcip = (packed.get("world_color_image_path") or "").encode("utf-8")
    wcics = (packed.get("world_color_image_colorspace") or "").encode("utf-8")
    desc.world_color_image_path = wcip if wcip else None
    desc.world_color_image_colorspace = wcics if wcics else None
    _fill_world_vec_ctypes(desc, packed)
    curves_list = packed.get("world_curves") or []
    curves_n = int(packed.get("world_curves_n", 0) or 0)
    curves_buf = None
    if curves_list and curves_n > 0:
        flat = [float(v) for v in curves_list]
        if len(flat) < curves_n * 3:
            raise QuantTraceSyncError(
                f"world_curves len {len(flat)} < n*3={curves_n * 3} (Slice 2as)"
            )
        curves_buf = (ctypes.c_float * (curves_n * 3))(*flat[: curves_n * 3])
        desc.world_curves = ctypes.cast(curves_buf, ctypes.POINTER(ctypes.c_float))
        desc.world_curves_n = curves_n
    else:
        desc.world_curves = None
        desc.world_curves_n = 0
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
    desc._keep = (verts, tris, uvs_buf, tex_keep, wip, wics, wcip, wcics, curves_buf)
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
            ("specular_tint", ctypes.c_float * 3),
            ("spec_tint_mix_type", ctypes.c_int),
            ("spec_tint_mix_fac", ctypes.c_float),
            ("spec_tint_mix_other", ctypes.c_float * 3),
            ("spec_tint_mix_chain_is_a", ctypes.c_int),
            ("spec_tint_mix_clamp_factor", ctypes.c_int),
            ("spec_tint_mix_clamp_result", ctypes.c_int),
            ("spec_tint_mix_b_image_path", ctypes.c_char_p),
            ("spec_tint_mix_b_image_colorspace", ctypes.c_char_p),
            ("spec_tint_gamma", ctypes.c_float),
            ("spec_tint_hsv_hue", ctypes.c_float),
            ("spec_tint_hsv_sat", ctypes.c_float),
            ("spec_tint_hsv_val", ctypes.c_float),
            ("spec_tint_hsv_fac", ctypes.c_float),
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
            ("bump_noise_enable", ctypes.c_int),
            ("bump_noise_dimensions", ctypes.c_int),
            ("bump_noise_type", ctypes.c_int),
            ("bump_noise_normalize", ctypes.c_int),
            ("bump_noise_w", ctypes.c_float),
            ("bump_noise_scale", ctypes.c_float),
            ("bump_noise_detail", ctypes.c_float),
            ("bump_noise_roughness", ctypes.c_float),
            ("bump_noise_lacunarity", ctypes.c_float),
            ("bump_noise_offset", ctypes.c_float),
            ("bump_noise_gain", ctypes.c_float),
            ("bump_noise_distortion", ctypes.c_float),
            ("bump_noise_use_color", ctypes.c_int),
            ("bump_separate_enable", ctypes.c_int),
            ("bump_separate_channel", ctypes.c_int),
            ("thin_wall", ctypes.c_int),
            ("transmission_weight", ctypes.c_float),
            ("tex_ob_use_transform", ctypes.c_int),
            ("tex_ob_tfm", ctypes.c_float * 12),
            ("base_gamma", ctypes.c_float),
            ("base_hsv_hue", ctypes.c_float),
            ("base_hsv_sat", ctypes.c_float),
            ("base_hsv_val", ctypes.c_float),
            ("base_hsv_fac", ctypes.c_float),
            ("base_mix_type", ctypes.c_int),
            ("base_mix_fac", ctypes.c_float),
            ("base_mix_other", ctypes.c_float * 3),
            ("base_mix_chain_is_a", ctypes.c_int),
            ("base_mix_clamp_factor", ctypes.c_int),
            ("base_mix_clamp_result", ctypes.c_int),
            ("base_mix_b_image_path", ctypes.c_char_p),
            ("base_mix_b_image_colorspace", ctypes.c_char_p),
            ("base_mix_fresnel_enable", ctypes.c_int),
            ("base_mix_fresnel_ior", ctypes.c_float),
            ("base_curves", ctypes.POINTER(ctypes.c_float)),
            ("base_curves_n", ctypes.c_int),
            ("base_curves_min_x", ctypes.c_float),
            ("base_curves_max_x", ctypes.c_float),
            ("base_curves_fac", ctypes.c_float),
            ("base_curves_extrapolate", ctypes.c_int),
            ("base_mix_curves", ctypes.POINTER(ctypes.c_float)),
            ("base_mix_curves_n", ctypes.c_int),
            ("base_mix_curves_min_x", ctypes.c_float),
            ("base_mix_curves_max_x", ctypes.c_float),
            ("base_mix_curves_fac", ctypes.c_float),
            ("base_mix_curves_extrapolate", ctypes.c_int),
            ("base_mix_curves_on_a", ctypes.c_int),
            ("normal_invert_g_enable", ctypes.c_int),
            ("normal_invert_g_fac", ctypes.c_float),
            ("coat_normal_invert_g_enable", ctypes.c_int),
            ("coat_normal_invert_g_fac", ctypes.c_float),
            ("bevel_enable", ctypes.c_int),
            ("bevel_samples", ctypes.c_int),
            ("bevel_radius", ctypes.c_float),
            ("rough_ramp", ctypes.POINTER(ctypes.c_float)),
            ("rough_ramp_alpha", ctypes.POINTER(ctypes.c_float)),
            ("rough_ramp_n", ctypes.c_int),
            ("rough_ramp_interpolate", ctypes.c_int),
            ("rough_ramp_fac", ctypes.c_float),
            ("rough_ramp_noise_enable", ctypes.c_int),
            ("rough_ramp_noise_dimensions", ctypes.c_int),
            ("rough_ramp_noise_type", ctypes.c_int),
            ("rough_ramp_noise_normalize", ctypes.c_int),
            ("rough_ramp_noise_w", ctypes.c_float),
            ("rough_ramp_noise_scale", ctypes.c_float),
            ("rough_ramp_noise_detail", ctypes.c_float),
            ("rough_ramp_noise_roughness", ctypes.c_float),
            ("rough_ramp_noise_lacunarity", ctypes.c_float),
            ("rough_ramp_noise_offset", ctypes.c_float),
            ("rough_ramp_noise_gain", ctypes.c_float),
            ("rough_ramp_noise_distortion", ctypes.c_float),
            ("rough_ramp_noise_use_color", ctypes.c_int),
            ("rough_invert_enable", ctypes.c_int),
            ("rough_invert_fac", ctypes.c_float),
            ("rough_separate_enable", ctypes.c_int),
            ("rough_separate_channel", ctypes.c_int),
            ("glass_bsdf_enable", ctypes.c_int),
            ("glass_distribution", ctypes.c_int),
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
            ("world_color", ctypes.c_float * 3),
            ("world_sky_type", ctypes.c_int),
            ("world_sky_sun_direction", ctypes.c_float * 3),
            ("world_sky_turbidity", ctypes.c_float),
            ("world_sky_ground_albedo", ctypes.c_float),
            ("world_sky_sun_disc", ctypes.c_int),
            ("world_sky_sun_size", ctypes.c_float),
            ("world_sky_sun_intensity", ctypes.c_float),
            ("world_sky_sun_elevation", ctypes.c_float),
            ("world_sky_sun_rotation", ctypes.c_float),
            ("world_sky_altitude", ctypes.c_float),
            ("world_sky_air_density", ctypes.c_float),
            ("world_sky_aerosol_density", ctypes.c_float),
            ("world_sky_ozone_density", ctypes.c_float),
            ("world_color_image_path", ctypes.c_char_p),
            ("world_color_image_colorspace", ctypes.c_char_p),
            ("world_color_image_projection", ctypes.c_int),
            ("world_gamma", ctypes.c_float),
            ("world_hsv_hue", ctypes.c_float),
            ("world_hsv_sat", ctypes.c_float),
            ("world_hsv_val", ctypes.c_float),
            ("world_hsv_fac", ctypes.c_float),
            ("world_bright", ctypes.c_float),
            ("world_contrast", ctypes.c_float),
            ("world_mix_type", ctypes.c_int),
            ("world_mix_fac", ctypes.c_float),
            ("world_mix_other", ctypes.c_float * 3),
            ("world_mix_chain_is_a", ctypes.c_int),
            ("world_mix_clamp_factor", ctypes.c_int),
            ("world_mix_clamp_result", ctypes.c_int),
            ("world_curves", ctypes.POINTER(ctypes.c_float)),
            ("world_curves_n", ctypes.c_int),
            ("world_curves_min_x", ctypes.c_float),
            ("world_curves_max_x", ctypes.c_float),
            ("world_curves_fac", ctypes.c_float),
            ("world_curves_extrapolate", ctypes.c_int),
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
    wcip = (packed.get("world_color_image_path") or "").encode("utf-8")
    wcics = (packed.get("world_color_image_colorspace") or "").encode("utf-8")
    keep.append(wcip)
    keep.append(wcics)
    desc.world_color_image_path = wcip if wcip else None
    desc.world_color_image_colorspace = wcics if wcics else None
    _fill_world_vec_ctypes(desc, packed)
    curves_list = packed.get("world_curves") or []
    curves_n = int(packed.get("world_curves_n", 0) or 0)
    if curves_list and curves_n > 0:
        flat = [float(v) for v in curves_list]
        if len(flat) < curves_n * 3:
            raise QuantTraceSyncError(
                f"world_curves len {len(flat)} < n*3={curves_n * 3} (Slice 2as)"
            )
        curves_buf = (ctypes.c_float * (curves_n * 3))(*flat[: curves_n * 3])
        keep.append(curves_buf)
        desc.world_curves = ctypes.cast(curves_buf, ctypes.POINTER(ctypes.c_float))
        desc.world_curves_n = curves_n
    else:
        desc.world_curves = None
        desc.world_curves_n = 0
    if exr_path:
        desc.exr_path = exr_path.encode("utf-8")
    else:
        desc.exr_path = None
    desc._keep = (meshes_arr, lights_arr, keep)
    return desc

