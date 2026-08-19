# Report-card audit. Read-only: consumes analysis results, never writes to the
# scene. All datablock lookups go by name against bpy.data (background-safe);
# node-tree walking is delegated to scenequant.nodes. One sanctioned exception
# to the no-bpy.context rule: Cycles compute preferences are process-global
# with no scene-side path, read (never written) in _cycles_gpu_backends.

from dataclasses import dataclass, field

import bpy

from .. import compat, nodes
from ..constants import NODE_GROUP_MAX_DEPTH, SEVERITY_ORDER
from . import coverage as coverage_analysis
from . import memory_model

MEGABYTE = 1024.0 * 1024.0
PERSISTENT_HEADROOM_FACTOR = 1.2
TEX_OVERSIZE_FACTOR = 2.0
# World textures wrap 360 degrees; below this multiple of the film long edge an
# equirect map can still be wanted sharp as a visible background.
ENV_VS_FILM_FACTOR = 4.0
FLOAT_WASTE_MIN_PIXELS = 1_000_000
SANE_MAX_BOUNCES = 8
CHILD_MISMATCH_FACTOR = 4.0
MAX_LISTED_ITEMS = 20
SUBDIV_MODIFIER_TYPES = ("SUBSURF", "MULTIRES")
GRADE_WEIGHTS = {"critical": 3.0, "high": 1.0, "medium": 0.4, "info": 0.0}
GRADE_START = 10.0
GRADE_BANDS = (("A", 9.0), ("B", 7.5), ("C", 6.0), ("D", 4.0))
# Ordered by preference: the first backend with a non-CPU device is suggested.
GPU_BACKENDS = ("OPTIX", "CUDA", "HIP", "METAL", "ONEAPI")
# Deform motion blur stores 2**(steps-1)-1 EXTRA vertex-position arrays per
# object — a float3 each, not another copy of the BVH-inclusive geometry.
MOTION_BLUR_MIN_STEPS = 2
MOTION_BLUR_BYTES_PER_VERTEX = 12
# Emissive meshes at or below this frame-area fraction are neon/CRT-style
# props, not light sources worth light-tree sampling.
TINY_EMITTER_COVERAGE = 0.01
DEFAULT_OFFSCREEN_DICING_SCALE = 4.0


@dataclass
class Finding:
    code: str          # stable id, e.g. 'TEX_OVERSIZED'
    severity: str      # 'critical' | 'high' | 'medium' | 'info'
    message: str       # artist language, includes concrete numbers
    fix_hint: str = ""  # operator idname that fixes it, '' if none
    est_savings_mb: float = 0.0
    items: list = field(default_factory=list)


def run_audit(scene, coverage, mem, dedup_meshes, dedup_images, vram_mb):
    """All checks over precomputed analysis results.

    coverage: dict[name, CoverageInfo]; mem: MemoryEstimate; dedup_*: keeper-first
    name groups; vram_mb: budget or detected VRAM in MB (0/None = unknown).
    """
    checks = (
        _check_vram_overbudget(mem, vram_mb),
        _check_device_not_gpu(scene),
        _check_tex_oversized(scene, coverage, mem),
        _check_env_oversized(scene, mem),
        _check_tex_float_waste(mem),
        _check_dup_mesh_data(scene, dedup_meshes),
        _check_dup_image_data(dedup_images, mem),
        _check_offscreen_rendered(scene, coverage, mem),
        _check_collection_offscreen(scene, coverage, mem),
        _check_hidden_cost(scene, mem),
        _check_subdiv_mismatch(scene, mem),
        _check_motion_blur_steps(scene, mem),
        _check_fixed_sampling(scene),
        _check_no_persistent(scene, mem, vram_mb),
        _check_bounces_high(scene),
        _check_tiny_emitters(scene, coverage),
        _check_curves_thick(scene),
        _check_adaptive_dicing(scene),
        _check_orphan_data(),
        _check_particle_mismatch(scene),
        _check_estimate_caveats(mem),
    )
    findings = [finding for finding in checks if finding is not None]
    findings.sort(key=lambda finding: SEVERITY_ORDER.index(finding.severity))
    return findings


def grade(findings):
    score = GRADE_START
    for finding in findings:
        score -= GRADE_WEIGHTS.get(finding.severity, 0.0)
    for letter, threshold in GRADE_BANDS:
        if score >= threshold:
            return letter
    return "F"


# ------------------------------------------------------------------ helpers

def _cap(names):
    if len(names) <= MAX_LISTED_ITEMS:
        return list(names)
    extra = len(names) - MAX_LISTED_ITEMS
    return list(names[:MAX_LISTED_ITEMS]) + ["+%d more" % extra]


def _plural(count):
    return "" if count == 1 else "s"


def _pct(fraction):
    value = fraction * 100.0
    return "%.1f" % value if value < 10 else "%.0f" % value


def _next_pow2(value):
    result = 1
    while result < value:
        result *= 2
    return result


def _cov_attr(info, name, default=0):
    # CoverageInfo dataclass normally; tolerate dicts from a JSON round-trip.
    if isinstance(info, dict):
        return info.get(name, default)
    return getattr(info, name, default)


def _cycles(scene):
    # Cycles-only checks are meaningless under EEVEE/Workbench.
    if scene.render.engine != "CYCLES":
        return None
    return getattr(scene, "cycles", None)


def _override(obj):
    settings = getattr(obj, "scenequant", None)
    return getattr(settings, "override", "AUTO")


def _mesh_mb(mesh):
    return memory_model.mesh_datablock_mb(mesh)


def _image_mb_by_name(name, mem):
    known = mem.per_image_mb.get(name)
    if known is not None:
        return known
    image = bpy.data.images.get(name)
    return memory_model.image_mb(image) if image is not None else 0.0


def image_object_map(scene, object_names):
    """image name -> set of object names, via material slots of the given objects."""
    mapping = {}
    for name in object_names:
        obj = scene.objects.get(name)
        if obj is None:
            continue
        for slot in getattr(obj, "material_slots", ()):
            mat = slot.material
            if mat is None:
                continue
            for image, _node in nodes.iter_tree_image_nodes(getattr(mat, "node_tree", None)):
                mapping.setdefault(image.name, set()).add(name)
    return mapping


def _min_texture_size(scene):
    """The artist's quantize floor — the audit must size against the same one."""
    settings = getattr(scene, "scenequant", None)
    return int(getattr(settings, "min_texture_size", 0) or 0)


def _world_image_names():
    names = set()
    for world in bpy.data.worlds:
        for image, _node in nodes.iter_tree_image_nodes(getattr(world, "node_tree", None)):
            names.add(image.name)
    return names


def _cycles_gpu_backends():
    """(compute_device_type, backends with a non-CPU device). Never raises."""
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
    except (AttributeError, KeyError):
        return None, ()
    device_type = getattr(prefs, "compute_device_type", None)
    available = []
    for backend in GPU_BACKENDS:
        try:
            devices = prefs.get_devices_for_type(backend)
        except Exception:
            continue  # backend not compiled in / device query failed: not available
        if any(getattr(device, "type", "CPU") != "CPU" for device in devices):
            available.append(backend)
    return device_type, tuple(available)


def _tree_emits(tree, visited, depth):
    # Emission is not an image-node concern, so nodes.py's walker does not
    # apply; same visited-set and depth discipline against cyclic groups though.
    if tree is None or depth > NODE_GROUP_MAX_DEPTH or tree in visited:
        return False
    visited.add(tree)
    for node in tree.nodes:
        node_type = getattr(node, "type", "")
        if node_type == "EMISSION":
            return True
        if node_type == "BSDF_PRINCIPLED":
            strength = node.inputs.get("Emission Strength")
            if strength is not None and (
                    strength.is_linked
                    or getattr(strength, "default_value", 0.0) > 0.0):
                return True
        if node_type == "GROUP" and getattr(node, "node_tree", None) is not None:
            if _tree_emits(node.node_tree, visited, depth + 1):
                return True
    return False


# ------------------------------------------------------------------- checks

def _check_vram_overbudget(mem, vram_mb):
    if not vram_mb or vram_mb <= 0:
        return None
    # vram_mb is the PHYSICAL budget; the reserve is applied once, by the same
    # helper the solver and the render pre-flight use. Applying a second 0.85
    # here left the artist with 72% of their card.
    limit = memory_model.effective_budget_threshold_mb(vram_mb)
    if mem.total_mb <= limit:
        return None
    over = mem.total_mb - limit
    message = (
        "Estimated render memory %.0f MB is over the %.0f MB usable share of "
        "your %.0f MB budget — Cycles will silently spill to system RAM and "
        "slow down several-fold. Reduce by at least %.0f MB." %
        (mem.total_mb, limit, vram_mb, over)
    )
    return Finding("VRAM_OVERBUDGET", "critical", message,
                   "scenequant.fit_budget", round(over, 1), [])


def _check_device_not_gpu(scene):
    cycles = _cycles(scene)
    if cycles is None:
        return None
    try:
        device_type, backends = _cycles_gpu_backends()
        if not backends:
            return None  # no GPU visible (or prefs unreadable): nothing to enable
        best = backends[0]
        if device_type in (None, "NONE"):
            message = (
                "Renders are running on the CPU — Cycles has no GPU backend "
                "selected while a %s-capable GPU sits idle. Enable %s under "
                "Preferences > System > Cycles Render Devices, then set this "
                "scene's Render Properties > Device to GPU Compute." %
                (best, best)
            )
        elif getattr(cycles, "device", "GPU") == "CPU":
            message = (
                "Renders are running on the CPU although %s is configured — "
                "set Render Properties > Device to GPU Compute." % device_type
            )
        else:
            return None
        return Finding("DEVICE_NOT_GPU", "high", message, "", 0.0, [])
    except Exception:
        return None  # device preferences must never break the audit


def _check_tex_oversized(scene, coverage, mem):
    usage = image_object_map(scene, list(coverage.keys()))
    world_images = _world_image_names()
    min_size = _min_texture_size(scene)
    items = []
    savings = 0.0
    worst = None  # (saved_mb, name, long_px, needed_px, coverage_fraction)
    for image_name, current_mb in mem.per_image_mb.items():
        users = usage.get(image_name)
        if not users:
            continue
        image = bpy.data.images.get(image_name)
        if image is None or image.size[0] == 0 or image.size[1] == 0:
            continue
        # Never promise savings the quantizer will refuse to deliver.
        if image.source in ("TILED", "SEQUENCE", "MOVIE") or image.library is not None:
            continue
        if image_name in world_images:
            # The world keeps the full-res original resident whatever the
            # material nodes point at, so the quantizer refuses these
            # (ENV_OVERSIZED covers them, via the global clamp).
            continue
        long_px = max(image.size[0], image.size[1])
        infos = [coverage[n] for n in users if n in coverage]
        # THE sizing rule, shared with the quantizer and the solver: sizing
        # from raw needed_texture_px while they scale by UV utilization is how
        # this check came to promise 63 MB the quantizer delivered 0 of.
        needed = max((coverage_analysis.scaled_needed_px(
            _cov_attr(i, "needed_texture_px", 0),
            _cov_attr(i, "uv_utilization", 1.0), long_px, min_size)
            for i in infos), default=0)
        if needed <= 0 or long_px <= TEX_OVERSIZE_FACTOR * needed:
            continue
        scale = needed / long_px
        saved = current_mb * (1.0 - scale * scale)
        savings += saved
        cover = max((_cov_attr(i, "max_coverage", 0.0) for i in infos), default=0.0)
        items.append("%s (%d px -> %d px)" % (image_name, long_px, needed))
        if worst is None or saved > worst[0]:
            worst = (saved, image_name, long_px, needed, cover)
    if not items:
        return None
    count = len(items)
    lead = "1 texture carries" if count == 1 else "%d textures carry" % count
    message = (
        "%s more resolution than the camera can ever see — worst is '%s' at "
        "%d px on an object covering %s%% of the frame (%d px would suffice). "
        "Quantizing reclaims ~%.0f MB." %
        (lead, worst[1], worst[2], _pct(worst[4]), worst[3], savings)
    )
    return Finding("TEX_OVERSIZED", "high", message,
                   "scenequant.quantize_textures", round(savings, 1), _cap(items))


def _check_env_oversized(scene, mem):
    world = scene.world
    if world is None:
        return None
    film_long = max(scene.render.resolution_x, scene.render.resolution_y)
    if film_long <= 0:
        return None
    items = []
    savings = 0.0
    worst = None  # (saved_mb, name, long_px)
    seen = set()
    for image, _node in nodes.iter_tree_image_nodes(getattr(world, "node_tree", None)):
        key = image.as_pointer()
        if key in seen:
            continue
        seen.add(key)
        if image.size[0] == 0 or image.size[1] == 0:
            continue
        long_px = max(image.size[0], image.size[1])
        if long_px <= ENV_VS_FILM_FACTOR * film_long:
            continue
        target = _next_pow2(film_long)
        scale = target / long_px
        saved = _image_mb_by_name(image.name, mem) * (1.0 - scale * scale)
        savings += saved
        items.append("%s (%d px, film long edge %d px)"
                     % (image.name, long_px, film_long))
        if worst is None or saved > worst[0]:
            worst = (saved, image.name, long_px)
    if not items:
        return None
    message = (
        "World environment texture '%s' is %d px across — %.0fx your %d px "
        "render. Unless it appears as a razor-sharp background, a "
        "film-resolution copy lights the scene identically and frees ~%.0f MB "
        "(Cycles' render Texture Limit clamps world textures too)." %
        (worst[1], worst[2], worst[2] / float(film_long), film_long, savings)
    )
    return Finding("ENV_OVERSIZED", "medium", message,
                   "scenequant.fit_budget", round(savings, 1), _cap(items))


def _check_tex_float_waste(mem):
    world_images = _world_image_names()
    items = []
    savings = 0.0
    for image_name, current_mb in mem.per_image_mb.items():
        image = bpy.data.images.get(image_name)
        if image is None or not image.is_float:
            continue
        if image.size[0] * image.size[1] < FLOAT_WASTE_MIN_PIXELS:
            continue
        lowered = image_name.lower()
        if image_name in world_images or "hdr" in lowered or "env" in lowered:
            continue
        items.append("%s (%.0f MB float)" % (image_name, current_mb))
        savings += current_mb * 0.5  # float32 -> half precision
    if not items:
        return None
    count = len(items)
    message = (
        "%d full-float texture%s look%s like plain color maps — 32-bit float "
        "costs 4x a byte texture. Half precision would reclaim ~%.0f MB; verify "
        "%s not displacement or HDRI maps first." %
        (count, _plural(count), "s" if count == 1 else "", savings,
         "it is" if count == 1 else "they are")
    )
    return Finding("TEX_FLOAT_WASTE", "medium", message,
                   "scenequant.fit_budget", round(savings, 1), _cap(items))


def _check_dup_mesh_data(scene, dedup_meshes):
    if not dedup_meshes:
        return None
    items = []
    dup_count = 0
    for group in dedup_meshes:
        keeper = group[0]
        for name in group[1:]:
            dup_count += 1
            items.append("%s = %s" % (name, keeper))
    # Shared with the solver so the report card cannot promise a merge the plan
    # then refuses: only members with a modifier-free render user free memory,
    # because every object carrying a modifier stack keeps its own evaluated
    # copy whichever mesh it points at.
    savings, barren = memory_model.dedup_mesh_savings_mb(scene, dedup_meshes)
    group_count = len(dedup_meshes)
    if savings > 0.0:
        tail = ("relinking to shared data saves ~%.0f MB with zero visual "
                "change." % savings)
    else:
        tail = ("relinking to shared data is still worth doing for file size "
                "and editing, but frees no render memory here: every user "
                "carries a modifier stack, so Cycles evaluates each object "
                "separately either way.")
    if barren and savings > 0.0:
        tail += (" %d group%s free nothing for that same reason."
                 % (barren, _plural(barren)))
    message = (
        "%d mesh datablock%s are exact copies of %d original%s — %s" %
        (dup_count, _plural(dup_count), group_count, _plural(group_count), tail)
    )
    return Finding("DUP_MESH_DATA", "high", message,
                   "scenequant.dedup", round(savings, 1), _cap(items))


def _check_dup_image_data(dedup_images, mem):
    if not dedup_images:
        return None
    items = []
    savings = 0.0
    dup_count = 0
    for group in dedup_images:
        keeper = group[0]
        for name in group[1:]:
            dup_count += 1
            savings += _image_mb_by_name(name, mem)
            items.append("%s = %s" % (name, keeper))
    group_count = len(dedup_images)
    message = (
        "%d image datablock%s duplicate %d original%s pixel-for-pixel — merging "
        "saves ~%.0f MB with zero visual change." %
        (dup_count, _plural(dup_count), group_count, _plural(group_count), savings)
    )
    return Finding("DUP_IMAGE_DATA", "high", message,
                   "scenequant.dedup", round(savings, 1), _cap(items))


def _check_offscreen_rendered(scene, coverage, mem):
    items = []
    bvh_mb = 0.0
    for name, info in coverage.items():
        # Mirror the trim guard: only objects outside the GENEROUS margin count.
        if _cov_attr(info, "near_frustum_ever", _cov_attr(info, "in_frustum_ever", True)):
            continue
        obj = scene.objects.get(name)
        if obj is None or obj.hide_render:
            continue
        if _override(obj) != "AUTO":
            continue  # HERO/EXCLUDE objects are never trimmed
        if obj.type != "MESH":
            # trim_offscreen only ever looks at meshes; listing curves and the
            # rest advertised a fix that would silently pass them over.
            continue
        items.append(name)
        bvh_mb += mem.per_object_geo_mb.get(name, 0.0)
    if not items:
        return None
    count = len(items)
    if count == 1:
        lead = "1 object never enters the camera view on any sampled frame but still renders fully"
    else:
        lead = ("%d objects never enter the camera view on any sampled frame "
                "but still render fully" % count)
    # est_savings_mb stays 0: the trim turns ray visibility off, which stops
    # rays but keeps every triangle in the BVH. The solver says so itself, so
    # booking geometry MB here made the report card contradict the plan.
    message = (
        "%s — rays spent off-screen on ~%.0f MB of geometry. The trim is a "
        "render-TIME win: it frees no memory (the geometry stays in the BVH) "
        "and keeps their shadows intact." % (lead, bvh_mb)
    )
    return Finding("OFFSCREEN_RENDERED", "high", message,
                   "scenequant.trim_offscreen", 0.0, _cap(items))


def _check_collection_offscreen(scene, coverage, mem):
    items = []
    savings = 0.0
    instanced = _instanced_collections(scene)
    for collection in scene.collection.children:
        objects = list(collection.all_objects)
        if not objects:
            continue
        if collection in instanced:
            # An Empty instances this collection (or a parent of it), so its
            # geometry stays resident for the instancer: excluding the SOURCE
            # frees nothing.
            continue
        offscreen = 0
        eligible = True
        for obj in objects:
            if obj.hide_render:
                continue  # already not rendering; excluding still drops sync cost
            info = coverage.get(obj.name)
            # Lights/cameras (no coverage) and protected objects veto the whole
            # collection: excluding it would change lighting or lose a camera.
            if info is None or _override(obj) != "AUTO":
                eligible = False
                break
            if _cov_attr(info, "near_frustum_ever",
                         _cov_attr(info, "in_frustum_ever", True)):
                eligible = False
                break
            offscreen += 1
        if not eligible or offscreen == 0:
            continue
        collection_mb = sum(
            mem.per_object_geo_mb.get(obj.name, 0.0) for obj in objects)
        savings += collection_mb
        items.append("%s (%d object%s, ~%.0f MB)"
                     % (collection.name, len(objects), _plural(len(objects)),
                        collection_mb))
    if not items:
        return None
    count = len(items)
    message = (
        "%d whole collection%s never enter%s the camera view on any sampled "
        "frame — Exclude (the View Layer checkbox) unloads ~%.0f MB entirely, "
        "a stronger win than per-object trims. Their shadows and reflections "
        "WILL disappear; use the trim instead if those matter." %
        (count, _plural(count), "s" if count == 1 else "", savings)
    )
    return Finding("COLLECTION_OFFSCREEN", "info", message,
                   "", round(savings, 1), _cap(items))


def _instanced_collections(scene):
    """Collections that some render-enabled object instances, plus everything
    nested inside them: excluding such a collection frees no memory, because
    the instancer still pulls its geometry in."""
    sources = set()
    for obj in scene.objects:
        if obj.hide_render:
            continue
        _add_collection_tree(getattr(obj, "instance_collection", None), sources, 0)
    return sources


def _add_collection_tree(collection, sink, depth):
    if collection is None or collection in sink or depth > NODE_GROUP_MAX_DEPTH:
        return
    sink.add(collection)
    for child in collection.children:
        _add_collection_tree(child, sink, depth + 1)


def _check_hidden_cost(scene, mem):
    items = []
    hidden_mb = 0.0
    hidden_objects = 0
    mismatched_mods = 0
    for obj in scene.objects:
        if obj.hide_viewport and not obj.hide_render:
            hidden_objects += 1
            hidden_mb += mem.per_object_geo_mb.get(obj.name, 0.0)
            items.append("%s (hidden in viewport, still renders)" % obj.name)
        for mod in getattr(obj, "modifiers", ()):
            if mod.show_render != mod.show_viewport:
                mismatched_mods += 1
                state = "render-only" if mod.show_render else "viewport-only"
                items.append("%s / %s (%s modifier)" % (obj.name, mod.name, state))
    if not items:
        return None
    clauses = []
    if hidden_objects:
        clauses.append("%d object%s hidden only in the viewport still render (~%.0f MB)"
                       % (hidden_objects, _plural(hidden_objects), hidden_mb))
    if mismatched_mods:
        clauses.append("%d modifier%s differ between viewport and render"
                       % (mismatched_mods, _plural(mismatched_mods)))
    message = ("What you preview is not what you pay for: " + "; ".join(clauses) + ".")
    return Finding("HIDDEN_COST", "medium", message,
                   "", round(hidden_mb, 1), _cap(items))


def _check_subdiv_mismatch(scene, mem):
    items = []
    savings = 0.0
    for obj in scene.objects:
        if obj.hide_render:
            continue  # nothing renders, so no render-time cost to reclaim
        if memory_model.uses_adaptive_subdivision(scene, obj):
            continue  # dicing decides the render mesh; 4**levels says nothing
        mods = [mod for mod in getattr(obj, "modifiers", ())
                if mod.type in SUBDIV_MODIFIER_TYPES and mod.show_render
                and (not mod.show_viewport
                     or getattr(mod, "render_levels", 0) > getattr(mod, "levels", 0))]
        if not mods:
            continue
        # Per OBJECT, once: the object's geometry MB already carries ALL its
        # extra levels, so charging it again per modifier booked 149.6% of the
        # object. extra_render_subdiv_levels is the same total the estimator
        # multiplied by, show_render-aware and capped.
        extra = memory_model.extra_render_subdiv_levels(obj)
        if extra <= 0:
            continue
        geo = mem.per_object_geo_mb.get(obj.name, 0.0)
        savings += geo * (1.0 - 1.0 / (4 ** extra))
        for mod in mods:
            items.append("%s / %s (%d -> %d levels)"
                         % (obj.name, mod.name, getattr(mod, "levels", 0),
                            getattr(mod, "render_levels", 0)))
    if not items:
        return None
    count = len(items)
    message = (
        "%d subdivision modifier%s go%s higher at render time than in the "
        "viewport — every extra level is 4x the polygons (~%.0f MB more than "
        "the viewport shows)." %
        (count, _plural(count), "es" if count == 1 else "", savings)
    )
    return Finding("SUBDIV_MISMATCH", "medium", message,
                   "", round(savings, 1), _cap(items))


def _check_motion_blur_steps(scene, mem):
    if _cycles(scene) is None:
        return None
    if not getattr(scene.render, "use_motion_blur", False):
        return None
    items = []
    savings = 0.0
    for obj in scene.objects:
        if obj.hide_render:
            continue
        cycles_obj = getattr(obj, "cycles", None)
        if cycles_obj is None:
            continue
        if not getattr(cycles_obj, "use_motion_blur", True):
            continue
        if not getattr(cycles_obj, "use_deform_motion", False):
            continue
        steps = getattr(cycles_obj, "motion_steps", 1)
        if steps < MOTION_BLUR_MIN_STEPS:
            continue
        copies = 2 ** (steps - 1)
        # What deform motion blur actually stores is one extra float3 vertex
        # position array per additional step — NOT another copy of the
        # BVH-inclusive geometry MB, which overstated an 8-step object 19.6x.
        vertices = len(getattr(getattr(obj, "data", None), "vertices", ()) or ())
        savings += (vertices * MOTION_BLUR_BYTES_PER_VERTEX
                    * (copies - 1) / MEGABYTE)
        items.append("%s (%d steps = %d position arrays)"
                     % (obj.name, steps, copies))
    if not items:
        return None
    count = len(items)
    message = (
        "%d object%s store%s extra vertex positions for deformation motion "
        "blur — each step doubles the count (2^(steps-1)), ~%.0f MB beyond "
        "the base meshes. Objects that only move rigidly need Deformation "
        "off; true deformers rarely need more than 2 steps." %
        (count, _plural(count), "s" if count == 1 else "", savings)
    )
    return Finding("MOTION_BLUR_STEPS", "medium", message,
                   "", round(savings, 1), _cap(items))


def _check_fixed_sampling(scene):
    cycles = _cycles(scene)
    if cycles is None:
        return None
    if getattr(cycles, "use_adaptive_sampling", True):
        return None
    samples = getattr(cycles, "samples", 0)
    message = (
        "Adaptive sampling is off: every pixel gets all %d samples even where "
        "the image is already clean. Turning it on typically cuts 10-30%% of "
        "render time with no visible change." % samples
    )
    return Finding("FIXED_SAMPLING", "high", message, "scenequant.autotune", 0.0, [])


def _check_no_persistent(scene, mem, vram_mb):
    if _cycles(scene) is None:
        return None
    if scene.frame_end <= scene.frame_start:
        return None
    if scene.render.use_persistent_data:
        return None
    # Against the USABLE share, not the physical total: persistent data keeps
    # the whole scene resident, so it must not be suggested on headroom that
    # the OS and other apps are already holding.
    usable = memory_model.effective_budget_threshold_mb(vram_mb)
    if not usable or mem.total_mb * PERSISTENT_HEADROOM_FACTOR >= usable:
        return None
    frames = scene.frame_end - scene.frame_start + 1
    message = (
        "Animation of %d frames renders without Persistent Data — Cycles "
        "rebuilds the whole scene every frame. You have VRAM headroom "
        "(%.0f MB estimated of %.0f MB usable), so enabling it is a free "
        "per-frame speedup." % (frames, mem.total_mb, usable)
    )
    return Finding("NO_PERSISTENT", "info", message, "scenequant.autotune", 0.0, [])


def _check_bounces_high(scene):
    cycles = _cycles(scene)
    if cycles is None:
        return None
    bounces = getattr(cycles, "max_bounces", 0)
    if bounces <= SANE_MAX_BOUNCES:
        return None
    message = (
        "Max light bounces is %d — beyond %d the image almost never changes "
        "outside glass-heavy scenes, but every ray keeps bouncing." %
        (bounces, SANE_MAX_BOUNCES)
    )
    return Finding("BOUNCES_HIGH", "medium", message, "scenequant.autotune", 0.0, [])


def _check_tiny_emitters(scene, coverage):
    if _cycles(scene) is None:
        return None
    material_users = {}
    for name in coverage:
        obj = scene.objects.get(name)
        if obj is None:
            continue
        for slot in getattr(obj, "material_slots", ()):
            if slot.material is not None:
                material_users.setdefault(slot.material, []).append(name)
    items = []
    for material, users in material_users.items():
        sampling = getattr(getattr(material, "cycles", None),
                           "emission_sampling", None)
        if sampling in (None, "NONE"):
            continue
        infos = [coverage[name] for name in users]
        # Off-screen emitters may be deliberate hidden light sources — turning
        # sampling off would kill their light. Only visible tiny props qualify.
        if not all(_cov_attr(info, "in_frustum_ever", True) for info in infos):
            continue
        biggest = max(_cov_attr(info, "max_coverage", 0.0) for info in infos)
        if biggest >= TINY_EMITTER_COVERAGE:
            continue
        if not _tree_emits(getattr(material, "node_tree", None), set(), 0):
            continue
        items.append("%s (%d object%s, max %s%% of frame)"
                     % (material.name, len(users), _plural(len(users)),
                        _pct(biggest)))
    if not items:
        return None
    count = len(items)
    message = (
        "%d emissive material%s appear%s only on meshes covering under %s%% of "
        "the frame (neon/CRT-style props) — setting their Emission Sampling to "
        "'None' stops Cycles treating each one as a light source, which cuts "
        "sampling cost with little visual change." %
        (count, _plural(count), "s" if count == 1 else "",
         _pct(TINY_EMITTER_COVERAGE))
    )
    return Finding("TINY_EMITTERS", "info", message, "", 0.0, _cap(items))


def _check_curves_thick(scene):
    if _cycles(scene) is None:
        return None
    curves = [obj.name for obj in scene.objects
              if obj.type == "CURVES" and not obj.hide_render]
    if not curves:
        return None
    # 4.5 enum: RIBBONS/THICK; 5.1 adds THICK_LINEAR — match by substring.
    shape = getattr(getattr(scene, "cycles_curves", None), "shape", None)
    if shape is None or "RIBBON" in shape:
        return None
    count = len(curves)
    message = (
        "%d hair/curves object%s render%s as full 3D strand geometry (Curve "
        "Shape '%s') — 'Rounded Ribbons' renders typical hair markedly cheaper "
        "with a near-identical look. Heavy grooms can also trade speed for "
        "memory by disabling the dedicated curve BVH." %
        (count, _plural(count), "s" if count == 1 else "", shape)
    )
    return Finding("CURVES_THICK", "info", message, "", 0.0, _cap(curves))


def _check_adaptive_dicing(scene):
    cycles = _cycles(scene)
    if cycles is None:
        return None
    scale = getattr(cycles, "offscreen_dicing_scale", None)
    if scale is None or scale > DEFAULT_OFFSCREEN_DICING_SCALE:
        return None
    names = [obj.name for obj in scene.objects
             if not obj.hide_render
             and memory_model.uses_adaptive_subdivision(scene, obj)]
    if not names:
        return None
    count = len(names)
    message = (
        "%d object%s use%s adaptive subdivision with Offscreen Dicing Scale at "
        "%.0f (the default) — raising it to 8-16 coarsens dicing only outside "
        "the camera view, often a free geometry-memory win." %
        (count, _plural(count), "s" if count == 1 else "", scale)
    )
    return Finding("ADAPTIVE_DICING", "info", message, "", 0.0, _cap(names))


def _check_orphan_data():
    items = []
    savings = 0.0
    count = 0
    for mesh in bpy.data.meshes:
        if mesh.users == 0 and not compat.is_linked(mesh):
            count += 1
            savings += _mesh_mb(mesh)
            items.append("mesh %s" % mesh.name)
    for image in bpy.data.images:
        if image.users == 0 and not compat.is_linked(image):
            count += 1
            savings += memory_model.image_mb(image)
            items.append("image %s" % image.name)
    for mat in bpy.data.materials:
        if mat.users == 0 and not compat.is_linked(mat):
            count += 1
            items.append("material %s" % mat.name)
    if count == 0:
        return None
    # No fix_hint on purpose: SceneQuant's own Purge Backups only removes
    # SceneQuant revert backups, never user orphans — pointing at it would
    # destroy the revert story while leaving these untouched.
    message = (
        "%d unused datablock%s (~%.0f MB) ride along in this file — Blender "
        "keeps them in RAM all session. Use Blender's own File > Clean Up > "
        "Purge Unused Data; purging is permanent and NOT covered by Revert." %
        (count, _plural(count), savings)
    )
    return Finding("ORPHAN_DATA", "info", message,
                   "", round(savings, 1), _cap(items))


def _check_particle_mismatch(scene):
    items = []
    worst_ratio = 0.0
    for obj in scene.objects:
        for psys in getattr(obj, "particle_systems", ()):
            settings = psys.settings
            if settings is None or getattr(settings, "child_type", "NONE") == "NONE":
                continue
            viewport = getattr(settings, "child_percent", 0)
            render = getattr(settings, "rendered_child_count", 0)
            effective_viewport = max(1, viewport)
            if render < CHILD_MISMATCH_FACTOR * effective_viewport:
                continue
            worst_ratio = max(worst_ratio, render / float(effective_viewport))
            items.append("%s / %s (%d viewport -> %d render children)"
                         % (obj.name, psys.name, viewport, render))
    if not items:
        return None
    count = len(items)
    message = (
        "%d particle system%s render far more children than the viewport shows "
        "(up to %.0fx) — renders are much heavier than the preview suggests." %
        (count, _plural(count), worst_ratio)
    )
    return Finding("PARTICLE_MISMATCH", "medium", message, "", 0.0, _cap(items))


def _check_estimate_caveats(mem):
    caveats = list(getattr(mem, "caveats", ()) or ())
    if not caveats:
        return None
    count = len(caveats)
    message = (
        "The memory estimate has %d known blind spot%s — treat the estimated "
        "total as a floor, not a ceiling." % (count, _plural(count))
    )
    return Finding("ESTIMATE_CAVEATS", "info", message, "", 0.0, _cap(caveats))
