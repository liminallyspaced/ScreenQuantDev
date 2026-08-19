# Texture quantizer: copy -> scale -> reassign user nodes.
# Invariant #2: the original image datablock is never mutated; a scaled copy is
# swapped into user nodes and the original is kept via use_fake_user.
# Invariant #1: every datablock write is recorded through the Journal.

import bpy

from .. import compat, nodes
from ..constants import GEOMETRY_TYPES
from ..journal import _find_nodes
from ..analysis import coverage as coverage_analysis
from ..analysis import memory_model
from . import guards

SKIP_SOURCES = {"TILED", "SEQUENCE", "MOVIE"}
MIN_EDGE_PX = 1
# Invariant #4: enabling Simplify while simplify_subdivision_render == 0
# flattens all subsurf at render time; 6 matches the 4.5.5/5.1.2 factory
# default for both the viewport and render caps.
SAFE_SUBDIV_RENDER = 6
# Factory default for both child-particle caps; a hand-set 0 deletes them all.
SAFE_CHILD_PARTICLES = 1.0


def _scaled_dims(width, height, target_px):
    """New (w, h): long edge scaled to target_px, aspect preserved, min 1 px."""
    if width >= height:
        return target_px, max(MIN_EDGE_PX, round(height * target_px / width))
    return max(MIN_EDGE_PX, round(width * target_px / height)), target_px


def reassign_user_nodes(users, new_image, expected_image):
    """Point each (material_name, node_name) pair at new_image.

    Node names repeat across nested group instances, so a name match alone can
    hit the wrong node: only nodes currently showing expected_image are touched.
    Returns the pairs actually reassigned — journal TEX_SWAP payloads must list
    only nodes that really changed so revert restores exactly those.
    """
    reassigned = []
    for mat_name, node_name in users:
        mat = bpy.data.materials.get(mat_name)
        if mat is None or mat.node_tree is None:
            continue
        for node in _find_nodes(mat.node_tree, node_name):
            if getattr(node, "image", None) is not expected_image:
                continue
            node.image = new_image
            reassigned.append((mat_name, node_name))
    return reassigned


def _quantize_skip_reason(image, scene, guard_cache=None):
    if guards.image_keep_override(image):
        return "image marked Keep"
    if compat.is_linked(image):
        return "linked library image"
    if image.source in SKIP_SOURCES:
        return f"source is {image.source}"
    if not image.has_data and not image.filepath:
        return "no pixel data and no filepath"
    if scene is not None and _used_by_world(image, scene):
        # Quantizing swaps MATERIAL nodes to the copy, but the world's node
        # tree keeps pointing at the full-res original — so both stay resident
        # and memory GROWS while the operator reports a saving. The solver
        # already excludes these; this is the standalone operator's guard.
        return "used by world environment"
    if scene is not None and guards.used_outside_scene(image, scene, guard_cache):
        # The node swap affects every scene whose materials show this image;
        # sizing from one scene's coverage would blur the others.
        return "image used by other scenes"
    return None


def _used_by_world(image, scene):
    world = getattr(scene, "world", None)
    if world is None:
        return False
    return any(found is image for found, _node
               in nodes.iter_tree_image_nodes(getattr(world, "node_tree", None)))


def quantize_image(image, target_px, jrnl, users, tag="quantize", scene=None,
                   guard_cache=None):
    """Copy-downscale one image and repoint its user nodes at the copy.

    users: precomputed [(material_name, node_name)] for this image.
    scene: when given, world-referenced images and images reachable from other
    scenes are skipped. guard_cache: optional dict shared across one pass.
    Returns a skip-reason string, or None on success.
    """
    reason = _quantize_skip_reason(image, scene, guard_cache)
    if reason is not None:
        return reason
    width, height = image.size[0], image.size[1]
    long_edge = max(width, height)
    if long_edge == 0:
        return "size unknown (data not loadable)"
    if long_edge <= target_px:
        return f"long edge already <= {target_px} px"

    copy = image.copy()
    copy.name = image.name + ".sq" + str(target_px)
    new_w, new_h = _scaled_dims(width, height, target_px)
    try:
        copy.scale(new_w, new_h)
    except (RuntimeError, ValueError) as exc:
        bpy.data.images.remove(copy)
        return f"scale failed: {exc}"
    # DATA-LOSS GUARD: the copy inherited the original's filepath. Left unpacked
    # and dirty, "Save All Modified Images" would overwrite the artist's source
    # file with the downscaled buffer, and reopening the .blend would reload the
    # copy at full resolution. Always detach the path and pack the scaled buffer;
    # a copy that cannot be packed is unsafe to keep at all.
    copy.filepath_raw = ""
    try:
        copy.pack()
    except (RuntimeError, ValueError) as exc:
        bpy.data.images.remove(copy)
        return f"pack failed, copy discarded for safety: {exc}"

    had_fake_user = image.use_fake_user
    reassigned = reassign_user_nodes(users, copy, image)
    if not reassigned:
        bpy.data.images.remove(copy)
        return "no user nodes found to reassign"
    image.use_fake_user = True
    # Payload shape must match journal._revert_tex_swap exactly.
    jrnl.record_action(
        "TEX_SWAP",
        {"orig_image": image.name, "new_image": copy.name, "users": reassigned,
         "orig_had_fake_user": had_fake_user},
        tag,
    )
    return None


def _material_objects_map(scene):
    """material name -> [render-enabled geometry objects]. Spans all
    GEOMETRY_TYPES so a texture whose most demanding user is a CURVE/CURVES/
    etc. object is not undersized. No bpy.context use."""
    mapping = {}
    for obj in scene.objects:
        if obj.type not in GEOMETRY_TYPES or obj.hide_render:
            continue
        for slot in obj.material_slots:
            if slot.material is not None:
                mapping.setdefault(slot.material.name, []).append(obj)
    return mapping


def _needed_px(image, user_pairs, mat_objects, coverage, min_size=0):
    """(target edge px over all objects using the image, pin_reason).

    Sized through coverage.scaled_needed_px, the one rule the solver and the
    audit also use. pin_reason is non-None when a protected or coverage-less
    user pins the image at its original size; 0 means no using object resolved.
    """
    original_edge = max(image.size[0], image.size[1])
    needed = 0
    for mat_name, _node_name in user_pairs:
        for obj in mat_objects.get(mat_name, ()):
            if obj.scenequant.override in {"HERO", "EXCLUDE"}:
                return original_edge, f"protected object {obj.name} uses it"
            info = coverage.get(obj.name)
            if info is None:
                return original_edge, f"user {obj.name} has no coverage data"
            needed = max(needed, _utilization_scaled_px(
                info, original_edge, min_size))
    return needed, None


def _utilization_scaled_px(info, image_long_edge=0, min_size=0):
    """Delegates to coverage.scaled_needed_px — the single sizing rule. Kept as
    a named entry point because the report's per-image target preview reaches
    for the apply layer's sizing by name."""
    return coverage_analysis.scaled_needed_px(
        info.needed_texture_px, getattr(info, "uv_utilization", 1.0),
        image_long_edge, min_size)


def quantize_by_coverage(scene, coverage, jrnl, settings, progress=None):
    """Downscale every render-used image to its coverage-driven need.

    progress: optional callable (index, total, label); exceptions ignored.
    Returns {'changed': int, 'skipped': [(name, reason)], 'saved_mb': float}.
    """
    users_map = memory_model.images_used_by_render(scene)
    mat_objects = _material_objects_map(scene)
    min_size = int(settings.min_texture_size)
    guard_cache = {}  # one collection/scene map build for the whole pass
    changed = 0
    skipped = []
    saved_mb = 0.0
    for index, (name, pairs) in enumerate(users_map.items()):
        guards.notify_progress(progress, index, len(users_map), name)
        image = bpy.data.images.get(name)
        if image is None:
            skipped.append((name, "image not found"))
            continue
        target, pin_reason = _needed_px(image, pairs, mat_objects, coverage,
                                        min_size)
        if pin_reason is not None:
            skipped.append((name, pin_reason))
            continue
        if target <= 0:
            skipped.append((name, "no render users resolved"))
            continue
        width, height = image.size[0], image.size[1]
        before_mb = memory_model.image_mb(image)
        reason = quantize_image(image, target, jrnl, pairs, tag="quantize",
                                scene=scene, guard_cache=guard_cache)
        if reason is not None:
            skipped.append((name, reason))
            continue
        changed += 1
        new_w, new_h = _scaled_dims(width, height, target)
        saved_mb += before_mb * (1.0 - (new_w * new_h) / float(width * height))
    return {"changed": changed, "skipped": skipped, "saved_mb": round(saved_mb, 2)}


def set_half_precision(images, jrnl, scene=None):
    """Enable 16-bit storage on float images; returns count changed.

    Gated on compat.supports_half_precision(): Cycles honors
    Image.use_half_precision only on <= 5.1 (5.2 texture cache supersedes it).
    scene: the scene this pass acts for. use_half_precision is a datablock
    flag, so setting it from one scene degrades the image in every scene using
    it — and two scenes journaling opposite writes both revert to a state the
    artist never chose. Without a scene, multi-scene files are left alone
    rather than written blind.
    """
    if not compat.supports_half_precision():
        return 0
    guard_cache = {}
    changed = 0
    for image in images:
        if compat.is_linked(image) or not image.is_float:
            continue
        if guards.image_keep_override(image):
            # KEEP promises "never downscale or replace"; half precision is a
            # (mild) precision loss, so it honors the override too.
            continue
        if scene is None:
            if len(bpy.data.scenes) > 1:
                continue
        elif guards.used_outside_scene(image, scene, guard_cache):
            continue
        if jrnl.set_prop(image, "use_half_precision", True, "quantize"):
            changed += 1
    return changed


def apply_texture_limit(scene, jrnl, size_str, tag="quantize"):
    """Global render texture clamp via Simplify + cycles.texture_limit_render."""
    render = scene.render
    simplify_was_on = render.use_simplify
    jrnl.set_prop(scene, "render.use_simplify", True, tag)
    # Killer-zero neutralization, applied to the VIEWPORT and RENDER caps
    # alike. Factory default is 6 / 1.0 (4.5.5/5.1.2), so a 0 here was set by
    # hand; it is inert while Simplify is off but flattens all subsurf and
    # deletes every child particle the moment Simplify turns on. Neutralize
    # only when THIS call is what enables Simplify -- with Simplify already on,
    # the 0 is a state the artist has actually been looking at.
    # These MUST be real writes: an earlier version "pinned" the viewport caps
    # by writing back their current value, which set_prop discards as a no-op,
    # so nothing was journaled and enabling Simplify silently flattened the
    # artist's viewport.
    if not simplify_was_on:
        if render.simplify_subdivision == 0:
            jrnl.set_prop(scene, "render.simplify_subdivision",
                          SAFE_SUBDIV_RENDER, tag)
        if render.simplify_subdivision_render == 0:
            jrnl.set_prop(scene, "render.simplify_subdivision_render",
                          SAFE_SUBDIV_RENDER, tag)
        if render.simplify_child_particles == 0.0:
            jrnl.set_prop(scene, "render.simplify_child_particles",
                          SAFE_CHILD_PARTICLES, tag)
        if render.simplify_child_particles_render == 0.0:
            jrnl.set_prop(scene, "render.simplify_child_particles_render",
                          SAFE_CHILD_PARTICLES, tag)
    # hasattr-guarded inside set_prop: non-Cycles scenes are a silent no-write,
    # visible via the journal's False return (nothing recorded).
    jrnl.set_prop(scene, "cycles.texture_limit_render", size_str, tag)
