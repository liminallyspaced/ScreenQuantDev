# Camera-aware screen-coverage analysis. Read-only: samples frames, projects
# bound-box corners into camera NDC, derives per-object texture needs.
# Headless-safe: driven entirely by the scene passed in, never bpy.context.

import math
from dataclasses import dataclass

from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

from ..constants import GEOMETRY_TYPES

MIN_NEEDED_TEXTURE_PX = 64
FULL_COVERAGE = 1.0
# Destructive consumers (trim/cull) must use near_frustum_ever, computed with
# this generous margin: frame sampling can miss an object that is only visible
# between sampled frames, and a fast mover near the frustum edge is the classic
# case. in_frustum_ever keeps the tight margin for analysis/reporting.
TRIM_SAFETY_MARGIN = 0.5
# Floor for the active-UV bbox area fraction: below this the estimate is more
# likely a degenerate/overlapping unwrap than a real 20x-denser atlas need.
UV_UTILIZATION_MIN = 0.05


@dataclass
class CoverageInfo:
    object_name: str
    max_coverage: float        # 0..1 fraction of frame area (conservative bbox over-estimate)
    in_frustum_ever: bool
    near_frustum_ever: bool    # like in_frustum_ever but with TRIM_SAFETY_MARGIN
    min_camera_distance: float
    needed_texture_px: int
    uv_utilization: float = 1.0  # active-UV bbox area fraction, clamped [0.05, 1.0]


def compute_coverage(scene, objects, frame_samples=5, quality_factor=2.0,
                     frustum_margin=0.15, progress=None):
    """Per-object screen coverage across the scene frame range.

    Returns {object_name: CoverageInfo} for renderable-geometry objects
    (GEOMETRY_TYPES) with hide_render False — not only meshes — plus
    collection-instance objects (EMPTY / instance_type COLLECTION). EMPTY
    is not added to GEOMETRY_TYPES (VRAM/audit stay mesh-like).
    progress, when given, is called as progress(i, total, label) once per
    sampled frame. Raises ValueError when the scene has no active camera.
    """
    if scene.camera is None:
        raise ValueError(
            "SceneQuant: scene '%s' has no active camera (scene.camera is None); "
            "set one before running coverage analysis" % scene.name
        )
    renderables = [obj for obj in objects
                   if obj.type in GEOMETRY_TYPES and not obj.hide_render]
    seen = {id(obj) for obj in renderables}
    for obj in objects:
        if id(obj) in seen or obj.hide_render:
            continue
        if (obj.type == "EMPTY"
                or getattr(obj, "instance_type", None) == "COLLECTION"
                or getattr(obj, "instance_collection", None) is not None):
            renderables.append(obj)
            seen.add(id(obj))
    # per object: [max_coverage, in_frustum_ever, near_frustum_ever, min_camera_distance]
    stats = {obj.name: [0.0, False, False, math.inf] for obj in renderables}
    utilization = {obj.name: _uv_utilization(obj) for obj in renderables}

    original_frame = scene.frame_current
    try:
        frames = _sample_frames(scene.frame_start, scene.frame_end, frame_samples)
        for index, frame in enumerate(frames):
            if progress is not None:
                progress(index, len(frames), "frame %d" % frame)
            scene.frame_set(frame)
            camera = scene.camera  # re-read: camera markers can rebind per frame
            if camera is None:
                continue
            for obj in renderables:
                area, in_frustum, near, distance = _frame_coverage(
                    scene, camera, obj, frustum_margin
                )
                entry = stats[obj.name]
                entry[0] = max(entry[0], area)
                entry[1] = entry[1] or in_frustum
                entry[2] = entry[2] or near
                entry[3] = min(entry[3], distance)
    finally:
        scene.frame_set(original_frame)

    long_edge_px = _render_long_edge_px(scene)
    return {
        name: CoverageInfo(
            object_name=name,
            max_coverage=coverage,
            in_frustum_ever=in_frustum,
            near_frustum_ever=near,
            min_camera_distance=distance,
            needed_texture_px=_needed_texture_px(coverage, long_edge_px, quality_factor),
            uv_utilization=utilization[name],
        )
        for name, (coverage, in_frustum, near, distance) in stats.items()
    }


def _uv_utilization(obj):
    """Fraction of the UV square the active UV layer's bbox spans.

    An object mapped to a small atlas region needs a denser texture than raw
    coverage suggests. Clamped to [0.05, 1.0]; 1.0 when there is no UV data
    (non-mesh types, unwrapped-less meshes) — unknown layouts must never
    inflate needed_texture_px.
    """
    data = getattr(obj, "data", None)
    layers = getattr(data, "uv_layers", None)
    active = getattr(layers, "active", None) if layers is not None else None
    loops = getattr(active, "data", None) if active is not None else None
    if not loops:
        return 1.0
    try:
        import numpy as np  # bundled with Blender
        buffer = np.empty(len(loops) * 2, dtype=np.float32)
        loops.foreach_get("uv", buffer)
        area = float((buffer[0::2].max() - buffer[0::2].min())
                     * (buffer[1::2].max() - buffer[1::2].min()))
    except (AttributeError, TypeError, RuntimeError, ImportError):
        return 1.0  # uv accessor absent on this version/type: assume full use
    if not math.isfinite(area):
        return 1.0
    return min(1.0, max(UV_UTILIZATION_MIN, area))


def _frame_coverage(scene, camera, obj, margin):
    """One object at the current frame -> (coverage_area, in_frustum, near_frustum, distance)."""
    camera_location = camera.matrix_world.translation
    # bound_box corners are object-local; matrix_world lifts them to world space.
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    distance = min((corner - camera_location).length for corner in corners)
    if _camera_inside_bbox(obj, camera_location):
        return FULL_COVERAGE, True, True, 0.0

    ndc = [world_to_camera_view(scene, camera, corner) for corner in corners]
    # world_to_camera_view: x,y in [0,1] means inside frame; z<0 means behind camera.
    in_front = [point for point in ndc if point.z > 0.0]
    if not in_front:
        return 0.0, False, False, distance
    # Behind-camera projections mirror through the view plane, so a mixed-sign
    # rect is garbage; clamping the rect over ALL corners makes partially-behind
    # objects read as large coverage (conservative) instead of nonsense.
    rect_points = ndc if len(in_front) < len(ndc) else in_front
    area = _clamped_rect_area(rect_points)
    in_frustum = area > 0.0 or _any_point_in_margin(in_front, margin)
    near = in_frustum or _any_point_in_margin(in_front, TRIM_SAFETY_MARGIN)
    return area, in_frustum, near, distance


def _camera_inside_bbox(obj, camera_location):
    try:
        local = obj.matrix_world.inverted() @ camera_location
    except ValueError:
        # Degenerate (zero-scale) matrix cannot be inverted; treat camera as outside.
        return False
    xs = [corner[0] for corner in obj.bound_box]
    ys = [corner[1] for corner in obj.bound_box]
    zs = [corner[2] for corner in obj.bound_box]
    return (
        min(xs) <= local.x <= max(xs)
        and min(ys) <= local.y <= max(ys)
        and min(zs) <= local.z <= max(zs)
    )


def _clamped_rect_area(points):
    """Area of the projected rect intersected with the [0,1]^2 frame."""
    min_x = _clamp01(min(point.x for point in points))
    max_x = _clamp01(max(point.x for point in points))
    min_y = _clamp01(min(point.y for point in points))
    max_y = _clamp01(max(point.y for point in points))
    return max(0.0, max_x - min_x) * max(0.0, max_y - min_y)


def _clamp01(value):
    return min(1.0, max(0.0, value))


def _any_point_in_margin(points, margin):
    low = -margin
    high = 1.0 + margin
    return any(low <= p.x <= high and low <= p.y <= high for p in points)


def _sample_frames(frame_start, frame_end, frame_samples):
    """Evenly spread frames always including first and last; deduped, in order."""
    if frame_end <= frame_start or frame_samples <= 1:
        return [frame_start]
    count = min(frame_samples, frame_end - frame_start + 1)
    span = frame_end - frame_start
    frames = []
    for index in range(count):
        frame = frame_start + round(span * index / (count - 1))
        if frame not in frames:
            frames.append(frame)
    return frames


def _render_long_edge_px(scene):
    # resolution_percentage deliberately ignored: texture needs are sized for
    # the full-resolution final render, immune to Draft mode's 50% or preview
    # percentages being active while the artist quantizes.
    render = scene.render
    return max(render.resolution_x, render.resolution_y)


def scaled_needed_px(needed_px, uv_utilization, image_long_edge=0, min_size=0):
    """The size one image is actually sized to for a user with this coverage.

    THE single sizing rule. The quantizer, the solver AND the audit must all
    ask this function: when the audit sized from raw needed_texture_px while
    the quantizer scaled by UV utilization, the report promised savings the
    quantizer then refused to deliver.

    An object mapped to a small fraction of the UV square needs more texels per
    screen pixel, so the raw need scales by 1/sqrt(utilization) and snaps up to
    a power of two (matching _needed_texture_px's steps). image_long_edge caps
    the result — upscaling is never a saving — and min_size floors it; pass 0
    for either to skip that clamp.
    """
    utilization = max(float(uv_utilization or FULL_COVERAGE), UV_UTILIZATION_MIN)
    scaled = _next_pow2(math.ceil(max(0, needed_px) / math.sqrt(utilization)))
    if image_long_edge > 0:
        scaled = min(scaled, image_long_edge)
    return max(scaled, min_size)


def _needed_texture_px(max_coverage, long_edge_px, quality_factor):
    # Raw coverage need only. The UV-utilization correction (1/sqrt(utilization)
    # for atlas textures) is applied by consumers via scaled_needed_px above —
    # never baked in here, or the apply side would double it.
    ideal = math.sqrt(max(0.0, max_coverage)) * long_edge_px * quality_factor
    return max(MIN_NEEDED_TEXTURE_PX, _next_pow2(math.ceil(ideal)))


def _next_pow2(value):
    result = 1
    while result < value:
        result *= 2
    return result
