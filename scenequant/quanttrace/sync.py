# QuantTrace depsgraph → QT_SimpleScene packer (Slice 2b).
#
# Walks a Blender depsgraph and packs camera / meshes / Principled /
# AREA lights / world into ctypes QT_SimpleScene (1+1) or QT_Scene (N+N)
# for quanttrace_render_scene_rgba / quanttrace_render_qt_scene_rgba.
# Slice 2c/2d: up to 32 meshes + 16 AREA/POINT/SUN lights, constant Principled.
# Linked Principled sockets / SPOT / HDR worlds still refuse.
# Slice 2d: AREA + POINT + SUN; Blender random_id from object name.
# Make it Fast stays on stock Cycles.

from __future__ import annotations

import ctypes
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


def _principled_from_material(mat) -> Tuple[Tuple[float, float, float], float, float, float, float]:
    """Return (base_rgb, roughness, metallic, ior, alpha) or raise."""
    if mat is None:
        raise QuantTraceSyncError("mesh has no material")
    if not getattr(mat, "use_nodes", False) or mat.node_tree is None:
        # Nodeless: approximate Blender default Principled.
        diff = getattr(mat, "diffuse_color", (0.8, 0.8, 0.8, 1.0))
        return (float(diff[0]), float(diff[1]), float(diff[2])), 0.5, 0.0, 1.45, 1.0
    bsdf = None
    for node in mat.node_tree.nodes:
        if getattr(node, "type", None) == "BSDF_PRINCIPLED":
            bsdf = node
            break
    if bsdf is None:
        raise QuantTraceSyncError("material has no Principled BSDF (Slice 2b)")
    # Linked sockets are unsupported this slice — require defaults.
    for sock_name in ("Base Color", "Roughness", "Metallic", "IOR", "Alpha"):
        sock = bsdf.inputs.get(sock_name)
        if sock is None:
            continue
        if getattr(sock, "is_linked", False):
            raise QuantTraceSyncError(
                f"Principled.{sock_name} is linked (Slice 2b needs constants)"
            )
    base = bsdf.inputs["Base Color"].default_value
    return (
        (float(base[0]), float(base[1]), float(base[2])),
        float(bsdf.inputs["Roughness"].default_value),
        float(bsdf.inputs["Metallic"].default_value),
        float(bsdf.inputs["IOR"].default_value),
        float(bsdf.inputs["Alpha"].default_value),
    )


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
    base, rough, metal, ior, alpha = _principled_from_material(mat)
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
        if data is None or ltype not in ("AREA", "POINT", "SUN"):
            raise QuantTraceSyncError(
                f"light {getattr(lamp, 'name', '?')} must be AREA/POINT/SUN "
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
        base, rough, metal, ior, alpha = _principled_from_material(mat)
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
        elif ltype == "SUN":
            kind = 2  # QT_LIGHT_SUN
            sizeu = sizev = 0.0
            radius = 0.0
            angle = float(getattr(lamp_data, "angle", 0.0091803) or 0.0091803)
        else:
            kind = 0  # QT_LIGHT_AREA
            sizeu, sizev = _area_light_sizes(lamp_data)
            radius = 0.0
            angle = 0.0
        packed_lights.append({
            "tfm": _matrix_3x4(lamp.matrix_world),
            "sizeu": sizeu,
            "sizev": sizev,
            "strength": list(_light_strength(lamp, scene)),
            "name": getattr(lamp, "name", "") or "",
            "kind": kind,
            "radius": radius,
            "angle": angle,
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
    # Keep buffers alive with the struct.
    desc._keep = (verts, tris)
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

