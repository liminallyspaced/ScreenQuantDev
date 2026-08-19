# Fit-in-budget plan builder. Pure planning: reads the scene and datablocks,
# NEVER writes and never touches the journal. Each PlanAction payload carries
# everything the apply/ modules need to execute it later. apply.guards is the
# one allowed apply/ import: read-only preconditions shared with the apply
# layer so the plan excludes exactly what apply would refuse.

from dataclasses import dataclass, field

import bpy

from .. import compat, nodes
from ..analysis import coverage as coverage_analysis
from ..analysis import memory_model
from ..apply import guards
from ..constants import (
    GEOMETRY_TYPES,
    MAX_EXTRA_SUBDIV_LEVELS,
    SUBDIV_COVERAGE,
)

HALF_FLOAT_FACTOR = 0.5         # 16-bit float halves float-texture memory
TEX_LIMIT_SIZES = (2048, 1024)  # global clamp ladder, tried largest first
QUANTIZE_VISUAL_COST = 1
TEX_LIMIT_VISUAL_COST = 2
SKIP_IMAGE_SOURCES = {"TILED", "SEQUENCE", "MOVIE"}


@dataclass
class PlanAction:
    kind: str            # 'DEDUP' | 'HALF_FLOAT' | 'TRIM_OFFSCREEN' | 'SUBDIV_TRIM' | 'QUANTIZE' | 'TEX_LIMIT'
    label: str
    est_savings_mb: float
    visual_cost: int     # 0 free ... 3 noticeable
    payload: dict


@dataclass
class Plan:
    actions: list
    est_before_mb: float
    est_after_mb: float
    budget_mb: float
    fits: bool
    shortfall_mb: float = 0.0        # MB still over the headroom threshold when not fitting
    caveats: list = field(default_factory=list)  # estimator gaps + solver exclusions


def build_plan(scene, coverage, mem, dedup_meshes, dedup_images, budget_mb, settings):
    budget = max(float(budget_mb or 0.0), 0.0)
    # budget_mb is PHYSICAL VRAM; the reserve is applied here, once, by the
    # shared helper the audit and the render pre-flight also call.
    threshold = memory_model.effective_budget_threshold_mb(budget)
    caveats = list(getattr(mem, "caveats", None) or ())
    protected = _protected_object_names(scene)
    collisions = nodes.image_name_collisions()
    img_state = _image_state(mem, collisions)
    img_objects = _images_to_objects(scene)
    # One collection/scene map build for every cross-scene guard in this plan.
    guard_cache = {}
    actions = []
    saved = 0.0

    def still_over():
        return (mem.total_mb - saved) > threshold

    if still_over():
        action = _dedup_action(scene, dedup_meshes, dedup_images, img_state,
                               img_objects, collisions, caveats)
        if action is not None:
            actions.append(action)
            saved += action.est_savings_mb
    if still_over() and compat.supports_half_precision():
        action = _half_float_action(img_state, img_objects, protected)
        if action is not None:
            actions.append(action)
            saved += action.est_savings_mb
    # Ray-visibility trim keeps geometry in the BVH: frees no memory, saves
    # render time only. Always offered, never counted toward budget fitting.
    trim = _trim_action(scene, coverage, mem, protected, guard_cache)
    if trim is not None:
        actions.append(trim)
    if still_over():
        action = _subdiv_trim_action(scene, coverage, mem, protected, caveats,
                                     guard_cache)
        if action is not None:
            actions.append(action)
            saved += action.est_savings_mb
    if still_over():
        action = _quantize_action(scene, img_state, img_objects, coverage,
                                  protected, settings, caveats, guard_cache)
        if action is not None:
            actions.append(action)
            saved += action.est_savings_mb
    if still_over():
        action = _tex_limit_action(img_state, mem.total_mb - saved, threshold)
        if action is not None:
            actions.append(action)
            saved += action.est_savings_mb

    est_after = mem.total_mb - saved
    return Plan(
        actions=actions,
        est_before_mb=mem.total_mb,
        est_after_mb=est_after,
        budget_mb=budget,
        fits=est_after <= threshold,
        shortfall_mb=max(0.0, est_after - threshold),
        caveats=caveats,
    )


def _protected_object_names(scene):
    """HERO and EXCLUDE overrides: their textures/visibility are off-limits."""
    protected = set()
    for obj in scene.objects:
        overrides = getattr(obj, "scenequant", None)
        if getattr(overrides, "override", "AUTO") != "AUTO":
            protected.add(obj.name)
    return protected


def _image_state(mem, collisions):
    """Mutable planning copy of per-image memory; rungs update it so later
    rungs never double-count savings on the same image. Collided names stay
    countable for the global clamp but are barred from name-keyed rungs."""
    state = {}
    for name, mb in mem.per_image_mb.items():
        image = bpy.data.images.get(name)
        if image is None:
            state[name] = {"mb": float(mb), "long_edge": 0, "is_float": False,
                           "half": False, "collided": name in collisions,
                           "keep": False, "skip_reason": "missing datablock"}
            continue
        state[name] = {
            "mb": float(mb),
            "long_edge": max(image.size[0], image.size[1]),
            "is_float": bool(image.is_float),
            "half": bool(getattr(image, "use_half_precision", False)),
            "collided": name in collisions,
            "keep": guards.image_keep_override(image),
            "skip_reason": _image_skip_reason(image),
        }
    return state


def _image_skip_reason(image):
    if compat.is_linked(image):
        return "linked"
    if image.source in SKIP_IMAGE_SOURCES:
        return "source " + image.source
    if image.size[0] <= 0 or image.size[1] <= 0:
        return "no pixel data"
    return None


def _images_to_objects(scene):
    """image name -> set of render-enabled object names whose materials use it.

    Material trees only (via nodes.iter_tree_image_nodes): world-referenced
    images get no object users here, which keeps them out of the user-keyed
    rungs; quantize additionally excludes world images explicitly."""
    mapping = {}
    material_images = {}
    for obj in scene.objects:
        if obj.type not in GEOMETRY_TYPES or obj.hide_render:
            continue
        for slot in getattr(obj, "material_slots", ()):
            material = slot.material
            if material is None:
                continue
            names = material_images.get(material)
            if names is None:
                names = {image.name for image, _node in
                         nodes.iter_tree_image_nodes(getattr(material, "node_tree", None))}
                material_images[material] = names
            for image_name in names:
                mapping.setdefault(image_name, set()).add(obj.name)
    return mapping


def _dedup_action(scene, dedup_meshes, dedup_images, img_state, img_objects,
                  collisions, caveats):
    mesh_groups = [list(group) for group in dedup_meshes if len(group) > 1]
    image_groups = [list(group) for group in dedup_images if len(group) > 1]
    if not mesh_groups and not image_groups:
        return None
    mesh_mb = _dedup_mesh_savings(scene, mesh_groups, caveats)
    image_mb = 0.0
    ambiguous = 0
    for group in image_groups:
        if any(name in collisions for name in group):
            # bpy.data.images.get on these names is ambiguous across libraries;
            # the merge is not counted (and should be skipped at apply time).
            ambiguous += 1
            continue
        for name in group[1:]:
            image_mb += _retire_duplicate_image(name, group[0], img_state, img_objects)
    if ambiguous:
        caveats.append(
            "dedup: %d image group(s) with cross-library name collisions "
            "excluded from savings" % ambiguous)
    n_meshes = sum(len(group) - 1 for group in mesh_groups)
    n_images = sum(len(group) - 1 for group in image_groups)
    total = mesh_mb + image_mb
    label = (f"{n_meshes} duplicate meshes + {n_images} duplicate images "
             f"→ shared data (~{total:.0f} MB)")
    payload = {"mesh_groups": mesh_groups, "image_groups": image_groups}
    return PlanAction("DEDUP", label, total, 0, payload)


def _dedup_mesh_savings(scene, mesh_groups, caveats):
    """Estimator-backed mesh merge savings, shared with the audit so the report
    card and the plan cannot disagree (memory_model.dedup_mesh_savings_mb)."""
    total, barren = memory_model.dedup_mesh_savings_mb(scene, mesh_groups)
    if barren:
        caveats.append(
            "dedup: %d mesh group(s) merge without freeing VRAM (Cycles shares "
            "geometry only between modifier-free objects; every object with a "
            "modifier stack keeps its own evaluated copy)" % barren)
    return total


def _retire_duplicate_image(name, keeper, img_state, img_objects):
    """Fold a non-keeper duplicate into the keeper's planning state and
    return the MB it frees. Keeper inherits its users for later sizing."""
    users = img_objects.pop(name, set())
    if users:
        img_objects.setdefault(keeper, set()).update(users)
    state = img_state.pop(name, None)
    if state is not None:
        return state["mb"]
    # Not render-referenced (or deleted since the scan): frees no render memory.
    return 0.0


def _half_float_action(img_state, img_objects, protected):
    names = []
    total = 0.0
    for name, state in sorted(img_state.items()):
        if (state["skip_reason"] or state["collided"] or state["keep"]
                or not state["is_float"] or state["half"]):
            continue
        users = img_objects.get(name, set())
        # Unknown users can't be cleared against HERO/EXCLUDE: leave untouched.
        if not users or users & protected:
            continue
        gain = state["mb"] * HALF_FLOAT_FACTOR
        state["mb"] -= gain
        state["half"] = True
        total += gain
        names.append(name)
    if not names:
        return None
    label = f"{len(names)} float textures → half precision (~{total:.0f} MB)"
    return PlanAction("HALF_FLOAT", label, total, 0, {"images": names})


def _trim_action(scene, coverage, mem, protected, guard_cache=None):
    names = []
    bvh_mb = 0.0
    for name, info in sorted(coverage.items()):
        # near_frustum_ever mirrors the apply-side trim guard (generous margin).
        if getattr(info, "near_frustum_ever", info.in_frustum_ever) or name in protected:
            continue
        obj = scene.objects.get(name)
        # Coverage now spans all geometry types; apply trims meshes only.
        if obj is None or obj.type != "MESH" or obj.hide_render:
            continue
        # Mirror apply-side refusals so the plan's object count stays honest.
        if compat.is_linked(obj) or guards.used_outside_scene(obj, scene, guard_cache):
            continue
        # Emissive objects are re-filtered at apply time (objects_apply.trim_offscreen).
        names.append(name)
        bvh_mb += mem.per_object_geo_mb.get(name, 0.0)
    if not names:
        return None
    label = (f"{len(names)} off-screen objects → ray visibility off "
             f"(saves render time; frees 0 MB — ~{bvh_mb:.0f} MB stays in BVH)")
    return PlanAction("TRIM_OFFSCREEN", label, 0.0, 0, {"objects": names})


def _subdiv_trim_action(scene, coverage, mem, protected, caveats, guard_cache=None):
    """Render-subdiv caps on low-coverage objects: real geometry MB, freed.

    Mirrors memory_model's show_render-aware, total-capped extra-levels
    accounting, so booked savings match what the estimator would re-measure
    after objects_apply.trim_subdiv runs."""
    names = []
    total = 0.0
    adaptive = []
    for name, info in sorted(coverage.items()):
        if name in protected or info.max_coverage >= SUBDIV_COVERAGE:
            continue
        obj = scene.objects.get(name)
        if obj is None or obj.type != "MESH" or obj.hide_render:
            continue
        if compat.is_linked(obj) or guards.used_outside_scene(obj, scene, guard_cache):
            continue  # apply-side skips these: no savings will materialize
        if memory_model.uses_adaptive_subdivision(scene, obj):
            adaptive.append(name)
            continue
        before = memory_model.extra_render_subdiv_levels(obj)
        after = _extra_levels_after_cap(obj)
        if before <= after:
            continue  # nothing render-visible to cap (e.g. show_render off)
        geo_mb = mem.per_object_geo_mb.get(name, 0.0)
        total += geo_mb * (1.0 - 1.0 / (4 ** (before - after)))
        names.append(name)
    if adaptive:
        caveats.append(
            "subdiv trim: adaptive-subdivision object(s) excluded "
            "(render geometry unestimable): " + ", ".join(adaptive))
    if not names:
        return None
    label = (f"{len(names)} low-coverage objects → render subdivision capped "
             f"at viewport level (~{total:.0f} MB)")
    return PlanAction("SUBDIV_TRIM", label, total, 0, {"objects": names})


def _extra_levels_after_cap(obj):
    """memory_model.extra_render_subdiv_levels as it will read AFTER
    objects_apply.trim_subdiv sets render_levels = levels on every cappable
    modifier: viewport-visible modifiers then contribute 0 extra levels;
    viewport-hidden ones still apply min(render_levels, levels) at render."""
    extra = 0
    for modifier in getattr(obj, "modifiers", ()):
        if modifier.type not in ("SUBSURF", "MULTIRES") or not modifier.show_render:
            continue
        if not modifier.show_viewport:
            extra += min(modifier.render_levels, modifier.levels)
    return min(extra, MAX_EXTRA_SUBDIV_LEVELS)


def _quantize_action(scene, img_state, img_objects, coverage, protected,
                     settings, caveats, guard_cache=None):
    """Read-only mirror of textures_apply sizing: UV-utilization-scaled need,
    clamped to the original long edge, min_texture_size floor. Excludes what
    the apply layer refuses: KEEP images, world-referenced images (the world
    keeps the full-res original resident) and images used by other scenes."""
    min_px = int(settings.min_texture_size)
    world_images = _world_image_names(scene)
    targets = {}
    total = 0.0
    world_skips = []
    cross_scene_skips = []
    for name, state in sorted(img_state.items()):
        if (state["skip_reason"] or state["collided"] or state["keep"]
                or state["mb"] <= 0.0 or state["long_edge"] <= 0):
            continue
        users = img_objects.get(name, set())
        if not users or users & protected:
            continue
        if name in world_images:
            world_skips.append(name)
            continue
        target = _needed_px(users, coverage, state["long_edge"], min_px)
        if target is None:
            continue  # a user has no coverage info: cannot bound the need
        if state["long_edge"] <= target:
            continue
        if _used_by_other_scenes(name, scene, guard_cache):
            cross_scene_skips.append(name)
            continue
        area_ratio = (target / state["long_edge"]) ** 2
        total += state["mb"] * (1.0 - area_ratio)
        state["mb"] *= area_ratio
        state["long_edge"] = target
        targets[name] = target
    _note_quantize_skips(caveats, world_skips, cross_scene_skips)
    if not targets:
        return None
    label = f"{len(targets)} textures → coverage-needed size (~{total:.0f} MB)"
    return PlanAction("QUANTIZE", label, total, QUANTIZE_VISUAL_COST, targets)


def _world_image_names(scene):
    return {name for name, entry in nodes.all_render_images(scene).items()
            if entry["world"]}


def _used_by_other_scenes(name, scene, guard_cache=None):
    image = bpy.data.images.get(name)
    return image is not None and guards.used_outside_scene(image, scene, guard_cache)


def _note_quantize_skips(caveats, world_skips, cross_scene_skips):
    if world_skips:
        caveats.append(
            "quantize: world-referenced image(s) excluded — the world keeps "
            "the full-res original resident (the global texture clamp still "
            "covers them): " + ", ".join(world_skips))
    if cross_scene_skips:
        caveats.append("quantize: image(s) used by other scenes excluded: "
                       + ", ".join(cross_scene_skips))


def _needed_px(users, coverage, long_edge, min_px):
    """Target size for a texture shared by `users`, sized for its most
    demanding one through the single sizing rule (coverage.scaled_needed_px).
    None if any user is untracked — skip the image rather than guess."""
    target = 0
    for obj_name in users:
        info = coverage.get(obj_name)
        if info is None:
            return None
        target = max(target, coverage_analysis.scaled_needed_px(
            info.needed_texture_px, getattr(info, "uv_utilization", 1.0),
            long_edge, min_px))
    return target


def _tex_limit_action(img_state, current_mb, threshold):
    chosen = None
    chosen_mb = 0.0
    for size in TEX_LIMIT_SIZES:
        saving = _clamp_saving(img_state, size)
        if saving <= 0.0:
            continue
        chosen, chosen_mb = size, saving
        if current_mb - saving <= threshold:
            break  # smallest sufficient clamp; otherwise fall through to 1024
    if chosen is None:
        return None
    label = (f"Global render texture clamp {chosen}px (~{chosen_mb:.0f} MB) "
             f"— affects ALL textures including hero objects")
    return PlanAction("TEX_LIMIT", label, chosen_mb, TEX_LIMIT_VISUAL_COST,
                      {"size": str(chosen)})


def _clamp_saving(img_state, size):
    """texture_limit_render clamps every texture globally, so HERO, Keep,
    world/environment, name-collided AND skip_reason images (linked, TILED,
    ...) all count here — the clamp is a render setting, not a datablock edit,
    so nothing exempts them. Read-only: later calls must see unmutated state."""
    total = 0.0
    for state in img_state.values():
        if state["mb"] <= 0.0 or state["long_edge"] <= size:
            continue
        total += state["mb"] * (1.0 - (size / state["long_edge"]) ** 2)
    return total
