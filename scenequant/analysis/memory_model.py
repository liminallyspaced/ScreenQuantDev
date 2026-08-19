# Render-memory cost model. Read-only: estimates texture + geometry + runtime
# overhead of the render-enabled part of a scene, and queries GPU VRAM via
# nvidia-smi. Headless-safe: driven entirely by the scene/depsgraph passed in,
# never bpy.context. All node-tree walking is delegated to scenequant.nodes.

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field

from .. import compat, nodes
from ..constants import (
    BUDGET_HEADROOM,
    BYTES_PER_TRIANGLE,
    GEOMETRY_TYPES,
    MAX_EXTRA_SUBDIV_LEVELS,
)

TEXTURE_CHANNELS = 4
BYTES_PER_FLOAT_CHANNEL = 4
BYTES_PER_BYTE_CHANNEL = 1
BYTES_PER_MB = 1024 * 1024
SUBDIV_QUAD_FACTOR = 4      # each subdivision level quadruples the face count
NVIDIA_SMI_TIMEOUT_S = 5
# What DWM/other apps typically still need on top of the sampled memory.used.
VRAM_OS_MARGIN_MB = 512
# memory.used moves as other apps come and go, but the budget threshold is
# asked for on every solve, audit and render pre-flight: sample at most this often.
VRAM_USED_TTL_S = 30.0

# Coarse non-mesh heuristics: a curves control point costs about a triangle
# (float4 key + BVH share); a point-cloud point is leaner (pos + radius).
BYTES_PER_CURVES_POINT = 120
BYTES_PER_CLOUD_POINT = 48
POINT_TYPES = {"CURVES", "POINTCLOUD"}

# Cycles GPU runtime floor + per-pixel buffers. Base covers the CUDA/OptiX
# context and OIDN model weights; the per-megapixel term covers film/adaptive
# buffers (x1), denoiser aux passes + working set (+2), and extra render
# passes (+0.25 each). Calibrated to keep the measured 1920x1080 GPU+OIDN
# reference at ~500 MB (the old flat FIXED_OVERHEAD_MB), while a 4K OIDN
# render lands in the observed 0.7-1.5 GB range instead of 500.
OVERHEAD_BASE_MB = 400.0
OVERHEAD_MB_PER_MPIXEL = 16.0
BASE_BUFFER_FACTOR = 1.0
DENOISE_BUFFER_FACTOR = 2.0
PASS_BUFFER_FACTOR = 0.25
PIXELS_PER_MPIXEL = 1_000_000.0

_EXTRA_PASS_PROPS = (
    "use_pass_z", "use_pass_mist", "use_pass_normal", "use_pass_position",
    "use_pass_vector", "use_pass_object_index", "use_pass_material_index",
    "use_pass_diffuse_direct", "use_pass_diffuse_indirect", "use_pass_diffuse_color",
    "use_pass_glossy_direct", "use_pass_glossy_indirect", "use_pass_glossy_color",
    "use_pass_transmission_direct", "use_pass_transmission_indirect",
    "use_pass_transmission_color", "use_pass_emit", "use_pass_environment",
    "use_pass_shadow", "use_pass_ambient_occlusion",
)


@dataclass
class MemoryEstimate:
    texture_mb: float
    geometry_mb: float
    total_mb: float            # texture + geometry + overhead
    per_image_mb: dict         # image name -> MB (render-referenced, incl. world/env)
    # One entry per DISTINCT evaluated geometry, keyed by its first render user
    # ('<name> (instanced)' for instance sources). Objects sharing that geometry
    # — Alt-D copies, collection instances — carry no entry of their own: they
    # add no memory, so excluding one of them frees nothing.
    per_object_geo_mb: dict
    render_triangles: int
    overhead_mb: float = 0.0   # resolution/pass/denoiser-aware runtime floor
    caveats: list = field(default_factory=list)  # honest gaps in this estimate


def images_used_by_render(scene):
    """LEGACY shape {image_name: [(material_name, node_name)]}, materials only.

    Delegates to nodes.material_image_users: TEX_SWAP revert resolves the
    pairs via bpy.data.materials, so world/env images never appear here.
    """
    return nodes.material_image_users(scene)


def image_mb(image):
    """Uncompressed render-memory footprint of one image datablock, in MB."""
    width, height = image.size[0], image.size[1]
    if not width or not height:
        return 0.0  # size (0,0): data not loadable, nothing resident to count
    bytes_per_channel = (
        BYTES_PER_FLOAT_CHANNEL if image.is_float else BYTES_PER_BYTE_CHANNEL
    )
    total_bytes = float(width) * height * TEXTURE_CHANNELS * bytes_per_channel
    # use_half_precision halves float textures only where Cycles honors it
    # (<= 5.1; 5.2 ignores the flag). Byte images are unaffected.
    if (image.is_float and compat.supports_half_precision()
            and getattr(image, "use_half_precision", False)):
        total_bytes /= 2.0
    return total_bytes / BYTES_PER_MB


def estimate_scene_memory(scene, depsgraph):
    """MemoryEstimate for the render-enabled portion of the scene."""
    caveats = []
    per_image_mb = _per_image_memory(scene, caveats)
    per_object_geo_mb, render_triangles, counted_data = _real_object_geometry(
        scene, depsgraph, caveats)
    render_triangles += _instanced_geometry(
        depsgraph, counted_data, per_object_geo_mb, caveats)
    overhead = overhead_mb(scene)
    texture_mb = sum(per_image_mb.values())
    geometry_mb = sum(per_object_geo_mb.values())
    return MemoryEstimate(
        texture_mb=texture_mb,
        geometry_mb=geometry_mb,
        total_mb=texture_mb + geometry_mb + overhead,
        per_image_mb=per_image_mb,
        per_object_geo_mb=per_object_geo_mb,
        render_triangles=render_triangles,
        overhead_mb=overhead,
        caveats=caveats,
    )


def overhead_mb(scene):
    """Content-independent Cycles runtime footprint for this scene's output."""
    render = scene.render
    scale = render.resolution_percentage / 100.0
    pixels = round(render.resolution_x * scale) * round(render.resolution_y * scale)
    factor = BASE_BUFFER_FACTOR
    cycles = getattr(scene, "cycles", None)
    if cycles is not None and getattr(cycles, "use_denoising", False):
        factor += DENOISE_BUFFER_FACTOR
    factor += PASS_BUFFER_FACTOR * _extra_pass_count(scene)
    return OVERHEAD_BASE_MB + OVERHEAD_MB_PER_MPIXEL * (pixels / PIXELS_PER_MPIXEL) * factor


def _extra_pass_count(scene):
    # MAX, not sum: Cycles renders view layers one after another, so only the
    # heaviest layer's pass buffers are ever resident at once. Summing booked a
    # phantom several hundred MB on any file using per-layer passes.
    counts = [
        sum(1 for prop in _EXTRA_PASS_PROPS if getattr(view_layer, prop, False))
        for view_layer in scene.view_layers if view_layer.use
    ]
    return max(counts) if counts else 0


# ------------------------------------------------------------------- textures

def _per_image_memory(scene, caveats):
    """image name -> MB, world/environment textures included.

    Every distinct datablock is counted once (by pointer). Cross-library name
    collisions are summed under the shared name — the total stays honest — and
    named in caveats because name-keyed actions cannot target them safely.
    """
    per_image_mb = {}
    counted = set()
    collisions = nodes.image_name_collisions()
    flagged = set()
    for image, _node, _owner in nodes.iter_render_image_nodes(scene):
        key = image.as_pointer()
        if key in counted:
            continue
        counted.add(key)
        per_image_mb[image.name] = per_image_mb.get(image.name, 0.0) + image_mb(image)
        if image.name in collisions:
            flagged.add(image.name)
    for name in sorted(flagged):
        caveats.append(
            "image name '%s' is shared across libraries: memory is summed but "
            "name-keyed actions must skip it" % name)
    return per_image_mb


# ------------------------------------------------------------------- geometry

def _render_geometry_objects(scene):
    # View-layer collection exclusion is not checked; hide_render is the filter.
    for obj in scene.objects:
        if obj.type in GEOMETRY_TYPES and not obj.hide_render:
            yield obj


def _real_object_geometry(scene, depsgraph, caveats):
    """(per_object_geo_mb, render_triangles, counted data pointers).

    Counted per DISTINCT evaluated datablock, exactly like the instancing path:
    Cycles allocates one geometry per evaluated mesh and instances it, so five
    Alt-D copies of a 100k-tri mesh cost one mesh, not five. Counting them per
    object booked 200 copies of a 57 MB mesh as 11.4 GB.
    """
    per_object = {}
    triangles_total = 0
    counted_data = set()
    volumes = []
    adaptive = []
    for obj in _render_geometry_objects(scene):
        if obj.type == "VOLUME":
            volumes.append(obj.name)
            continue
        data_key = evaluated_data_pointer(obj, depsgraph)
        if data_key is not None and data_key in counted_data:
            continue  # shares its geometry with an object already counted
        is_adaptive = uses_adaptive_subdivision(scene, obj)
        if is_adaptive:
            adaptive.append(obj.name)
        mb, triangles = _object_geometry(
            obj, depsgraph, apply_render_subdiv=not is_adaptive)
        per_object[obj.name] = mb
        triangles_total += triangles
        if data_key is not None:
            counted_data.add(data_key)
    if volumes:
        caveats.append("VOLUME grids not modeled: " + ", ".join(sorted(volumes)))
    if adaptive:
        caveats.append(
            "adaptive subdivision (dicing) makes render geometry unestimable; "
            "counted at viewport level only: " + ", ".join(sorted(adaptive)))
    return per_object, triangles_total, counted_data


def evaluated_data_pointer(obj, depsgraph):
    """Pointer to obj's EVALUATED geometry datablock — Cycles' unit of geometry
    allocation, and therefore the estimator's unit of counting.

    Probe-verified on 4.5.5 and 5.1.2: objects sharing one modifier-free mesh
    all resolve to a single pointer, while every object carrying its own
    modifier stack gets a distinct evaluated copy (so a merged-but-modified
    group still costs one geometry per object). Instances of any kind —
    collection, geometry nodes, particles — resolve to their source's pointer.
    """
    data = getattr(obj.evaluated_get(depsgraph), "data", None)
    return data.as_pointer() if data is not None else None


def _object_geometry(obj, depsgraph, apply_render_subdiv=True):
    """(MB, triangles) one real object contributes at render time.

    MESH/CURVE/SURFACE/META/FONT tessellate via evaluated to_mesh; CURVES and
    POINTCLOUD use per-point heuristics on the evaluated data (their triangle
    contribution is 0 — geometry_mb stays the source of truth).
    """
    eval_obj = obj.evaluated_get(depsgraph)
    if obj.type in POINT_TYPES:
        points = _point_count(getattr(eval_obj, "data", None))
        bytes_per = (BYTES_PER_CURVES_POINT if obj.type == "CURVES"
                     else BYTES_PER_CLOUD_POINT)
        return points * bytes_per / BYTES_PER_MB, 0
    triangles = _evaluated_triangle_count(eval_obj)
    if apply_render_subdiv:
        # The depsgraph evaluates viewport modifier levels; scale by the extra
        # render-only SUBSURF/MULTIRES levels to approximate the render mesh.
        triangles *= SUBDIV_QUAD_FACTOR ** extra_render_subdiv_levels(obj)
    return triangles * BYTES_PER_TRIANGLE / BYTES_PER_MB, triangles


def _point_count(data):
    points = getattr(data, "points", None)  # CurvesGeometry/PointCloud RNA
    return len(points) if points is not None else 0


def _evaluated_triangle_count(eval_obj):
    try:
        mesh = eval_obj.to_mesh()
    except RuntimeError:
        return 0  # evaluated object cannot yield a mesh; contributes no triangles
    if mesh is None:
        return 0
    try:
        mesh.calc_loop_triangles()
        triangles = len(mesh.loop_triangles)
    finally:
        eval_obj.to_mesh_clear()
    return triangles


def uses_adaptive_subdivision(scene, obj):
    """Cycles adaptive dicing: 4**levels no longer bounds the render mesh."""
    cycles_scene = getattr(scene, "cycles", None)
    if cycles_scene is None:
        return False
    # 4.x gates dicing behind feature_set EXPERIMENTAL and flags it on
    # obj.cycles; 5.0+ removed the gate and moved the flag onto the modifier.
    feature_set = getattr(cycles_scene, "feature_set", None)
    if feature_set is not None and feature_set != "EXPERIMENTAL":
        return False
    object_flag = getattr(getattr(obj, "cycles", None),
                          "use_adaptive_subdivision", False)
    return any(
        mod.type == "SUBSURF" and mod.show_render
        and (object_flag or getattr(mod, "use_adaptive_subdivision", False))
        for mod in getattr(obj, "modifiers", ())
    )


def extra_render_subdiv_levels(obj):
    """Subdivision levels the render applies beyond the viewport evaluation."""
    extra = 0
    for modifier in getattr(obj, "modifiers", ()):
        if modifier.type not in ("SUBSURF", "MULTIRES"):
            continue
        if not modifier.show_render:
            continue
        if not modifier.show_viewport:
            # Viewport skipped it entirely; render applies its full level count.
            extra += modifier.render_levels
        else:
            extra += max(0, modifier.render_levels - modifier.levels)
    return min(extra, MAX_EXTRA_SUBDIV_LEVELS)


# Backward-compat aliases from before the names were promoted to public API.
_uses_adaptive_subdivision = uses_adaptive_subdivision
_extra_render_subdiv_levels = extra_render_subdiv_levels


def _instanced_geometry(depsgraph, counted_data, per_object_geo_mb, caveats):
    """Geometry reached only through instancing (collection instances, geometry
    nodes, particles). Cycles shares memory between instances of one datablock,
    so each distinct instanced datablock is counted ONCE; entries are labeled
    '<name> (instanced)' because the source is usually not in scene.objects.
    Returns the triangles added.
    """
    triangles_total = 0
    volumes = []
    for inst in depsgraph.object_instances:
        # DepsgraphObjectInstance is reused while iterating: read, never keep.
        if not inst.is_instance:
            continue  # real objects are counted from scene.objects
        parent = getattr(inst.parent, "original", inst.parent)
        if parent is not None and parent.hide_render:
            continue
        source = inst.object
        original = getattr(source, "original", source)
        if original is None or getattr(original, "type", "") not in GEOMETRY_TYPES:
            continue
        # Keyed on the EVALUATED datablock, the same unit _real_object_geometry
        # counts, so an instance source that is also a real scene object is
        # never counted twice (probe-verified for collection, geometry-nodes
        # and particle instancing on 4.5.5 and 5.1.2).
        data = getattr(source, "data", None)
        if data is None or data.as_pointer() in counted_data:
            continue
        counted_data.add(data.as_pointer())
        if original.type == "VOLUME":
            volumes.append(original.name)
            continue
        mb, triangles = _instance_source_geometry(source, original)
        if mb <= 0.0:
            continue
        label = original.name + " (instanced)"
        per_object_geo_mb[label] = per_object_geo_mb.get(label, 0.0) + mb
        triangles_total += triangles
    if volumes:
        caveats.append(
            "instanced VOLUME grids not modeled: " + ", ".join(sorted(set(volumes))))
    return triangles_total


def _instance_source_geometry(source, original):
    """(MB, triangles) for one instanced source; source is already evaluated."""
    if original.type in POINT_TYPES:
        points = _point_count(getattr(source, "data", None))
        bytes_per = (BYTES_PER_CURVES_POINT if original.type == "CURVES"
                     else BYTES_PER_CLOUD_POINT)
        return points * bytes_per / BYTES_PER_MB, 0
    triangles = _evaluated_triangle_count(source)
    triangles *= SUBDIV_QUAD_FACTOR ** extra_render_subdiv_levels(original)
    return triangles * BYTES_PER_TRIANGLE / BYTES_PER_MB, triangles


# ---------------------------------------------------------------------- dedup

def mesh_datablock_mb(mesh):
    """Render memory one mesh datablock holds, from O(1) RNA reads.

    Fan triangulation: an n-gon yields n-2 triangles, so tris = loops - 2*polys.
    Deliberately avoids calc_loop_triangles(), a side effect planners must not
    trigger.
    """
    triangles = max(len(mesh.loops) - 2 * len(mesh.polygons), 0)
    return triangles * BYTES_PER_TRIANGLE / BYTES_PER_MB


def dedup_mesh_savings_mb(scene, mesh_groups):
    """(MB relinking these mesh groups frees, count of groups that free none).

    THE shared answer for both the solver and the audit — booking savings the
    other one refuses is how the report card and the plan came to disagree.
    Matches the estimator exactly: geometry costs one allocation per distinct
    EVALUATED datablock, so a merge only frees memory for members that have a
    modifier-free render user. An object carrying a modifier stack keeps its
    own evaluated copy whichever mesh it points at, so it books nothing.
    """
    users = _mesh_render_users(scene)
    total = 0.0
    barren = 0
    for group in mesh_groups:
        # Members whose geometry can actually be shared after the relink; all
        # of them collapse onto the keeper's single evaluated datablock.
        shareable = [name for name in group
                     if any(not obj.modifiers for obj in users.get(name, ()))]
        if len(shareable) < 2:
            barren += 1
            continue
        for name in shareable[1:]:
            total += mesh_datablock_mb(users[name][0].data)
    return total, barren


def _mesh_render_users(scene):
    """mesh datablock name -> [render-enabled MESH objects using it]."""
    users = {}
    for obj in scene.objects:
        if obj.type == "MESH" and not obj.hide_render and obj.data is not None:
            users.setdefault(obj.data.name, []).append(obj)
    return users


# ----------------------------------------------------------------------- VRAM

NVIDIA_SMI_CANDIDATES = (
    r"C:\Windows\System32\nvidia-smi.exe",
    r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
    "/usr/bin/nvidia-smi",
    "/usr/local/bin/nvidia-smi",
)


def nvidia_smi_binaries():
    """PATH first, then well-known install locations. Deduped, existing files only
    except a final bare 'nvidia-smi' so a missing PATH still tries execvp."""
    found = []
    which = shutil.which("nvidia-smi")
    if which:
        found.append(which)
    for path in NVIDIA_SMI_CANDIDATES:
        if path not in found and os.path.isfile(path):
            found.append(path)
    if not found:
        found.append("nvidia-smi")
    return found


def _nvidia_smi_rows(fields):
    """Rows of ints for the requested --query-gpu fields; None on any failure."""
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)  # no console flash
    query_tail = ["--query-gpu=" + ",".join(fields),
                  "--format=csv,noheader,nounits"]
    for binary in nvidia_smi_binaries():
        try:
            proc = subprocess.run(
                [binary] + query_tail, capture_output=True, text=True,
                timeout=NVIDIA_SMI_TIMEOUT_S, creationflags=creationflags,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode != 0:
            continue
        try:
            rows = [
                [int(cell.strip()) for cell in line.split(",")]
                for line in proc.stdout.splitlines() if line.strip()
            ]
        except ValueError:
            continue
        if rows and all(len(row) == len(fields) for row in rows):
            return rows
    return None


def detect_vram_mb():
    """Physical VRAM in MB via nvidia-smi; min across GPUs; None on any failure."""
    rows = _nvidia_smi_rows(("memory.total",))
    if rows is None:
        return None
    return min(row[0] for row in rows)


_vram_sample_cache = {"at": None, "sample": None}


def vram_sample_mb():
    """(physical total MB, MB other processes hold) for the smallest GPU, or
    None when nvidia-smi cannot answer.

    Cached for VRAM_USED_TTL_S: the solver, the audit and the render pre-flight
    all ask for the budget threshold, and none of them should pay for an
    nvidia-smi subprocess each time.
    """
    now = time.monotonic()
    stamp = _vram_sample_cache["at"]
    if stamp is not None and now - stamp < VRAM_USED_TTL_S:
        return _vram_sample_cache["sample"]
    rows = _nvidia_smi_rows(("memory.total", "memory.used"))
    sample = None
    if rows is not None:
        total, used = min(rows, key=lambda row: row[0])
        sample = (float(total), float(used))
    _vram_sample_cache["at"] = now
    _vram_sample_cache["sample"] = sample
    return sample


def effective_budget_threshold_mb(budget_mb):
    """MB a render may actually use, given a budget_mb ceiling in VRAM.

    budget_mb is the card's physical total, or a smaller ceiling the artist
    chose, with NO reserve subtracted — this function is the one and only place
    the reserve is applied. Solver, audit and pre-flight all call it; each
    applying its own 0.85 left the artist with 72% of their VRAM and made the
    Detect-VRAM button cost a gigabyte.

    min of two ceilings, not max: a flat BUDGET_HEADROOM reserve on the chosen
    budget, and what is physically left on the CARD once the memory other apps
    already hold is subtracted (Windows DWM alone can sit on 1-2 GB, more than
    a flat 15% on an 8 GB card). Taking the max discarded the measured branch
    exactly when it mattered most.

    The measured term is computed against the card's real total, never against
    the budget: subtracting card-wide usage from a smaller chosen ceiling
    double-counts memory that was never inside that ceiling, and drove the
    threshold to 0 for anyone who asked for less than their whole card. When
    budget_mb IS the physical total the two are the same number, which is the
    Detect-VRAM case. The term is skipped entirely — leaving the flat reserve —
    when nvidia-smi cannot answer.
    """
    budget = max(float(budget_mb or 0.0), 0.0)
    if budget <= 0.0:
        return 0.0
    threshold = BUDGET_HEADROOM * budget
    sample = vram_sample_mb()
    if sample is None:
        return threshold
    total, used = sample
    return max(0.0, min(threshold, total - used - VRAM_OS_MARGIN_MB))
