# Datablock dedup relink, ray-visibility trim, and opt-in camera culling.
# Every write goes through the Journal; action payload shapes must match the
# revert handlers in journal.py (_revert_data_relink / _revert_tex_swap) exactly.

import bpy

from .. import compat
from ..analysis import memory_model
from . import guards
from .textures_apply import reassign_user_nodes

SKIP_IMAGE_SOURCES = {"TILED", "SEQUENCE", "MOVIE"}
RAY_VIS_PROPS = ("visible_camera", "visible_diffuse",
                 "visible_glossy", "visible_transmission")
# Conservative default: off-screen objects can still appear in mirrors and
# glass, so glossy/transmission visibility is kept unless the artist opts out.
RAY_VIS_CONSERVATIVE = ("visible_camera", "visible_diffuse")
# Coarse per-vertex mesh memory estimate (co + normals + loop/poly share + BVH
# margin). Savings figures derived from it are labeled estimates.
EST_BYTES_PER_VERTEX = 40
BYTES_PER_MB = 1024 * 1024
MAX_GROUP_DEPTH = 4


def _mesh_relink_skip_reason(obj, scene, guard_cache):
    if compat.is_linked(obj):
        return "linked object"
    if compat.is_linked(obj.data):
        return "linked mesh data"
    if not guards.in_object_mode(obj):
        # obj.data assignment outside Object Mode is a silent no-op (4.5-5.1):
        # journaling it would record a phantom relink.
        return f"object in {obj.mode} mode"
    if obj.data.shape_keys is not None:
        return "mesh has shape keys"
    for mod in obj.modifiers:
        # Multires sculpt data is bound to its specific mesh datablock.
        if mod.type == "MULTIRES":
            return "multires modifier"
    # The loop below walks bpy.data.objects, not scene.objects, so without
    # these two checks a dedup run from scene A relinks scene B's objects and
    # files the revert entry in A's journal -- B can never undo it.
    if scene is None:
        if len(bpy.data.scenes) > 1:
            return "no target scene given (cross-scene safety)"
    elif obj.name not in scene.objects:
        return "object not in this scene"
    elif guards.used_outside_scene(obj, scene, guard_cache):
        return "used by other scenes"
    return None


def relink_duplicate_meshes(groups, jrnl, scene=None):
    """Point every object using a duplicate mesh at its group keeper ([0]).

    scene: the scene this dedup acts for; objects belonging to any other scene
    are skipped so their revert entry never lands in the wrong journal.
    Returns {'merged': int, 'saved_mb': float (estimate), 'skipped': [(name, reason)]}.
    """
    merged = 0
    skipped = []
    relinked_verts = {}
    guard_cache = {}
    for group in groups:
        keeper = bpy.data.meshes.get(group[0])
        if keeper is None or compat.is_linked(keeper):
            skipped.append((group[0], "keeper missing or linked"))
            continue
        non_keepers = set(group[1:])
        for obj in bpy.data.objects:
            if obj.type != "MESH" or obj.data is None:
                continue
            if obj.data.name not in non_keepers:
                continue
            reason = _mesh_relink_skip_reason(obj, scene, guard_cache)
            if reason is not None:
                skipped.append((obj.name, reason))
                continue
            old = obj.data
            had_fake_user = old.use_fake_user
            try:
                obj.data = keeper
            except (AttributeError, TypeError) as exc:
                skipped.append((obj.name, f"data relink failed: {exc}"))
                continue
            if obj.data is not keeper:
                # Read-back guard: the assignment can no-op without raising.
                skipped.append((obj.name, "data relink did not take effect"))
                continue
            old.use_fake_user = True
            # Payload shape must match journal._revert_data_relink exactly.
            jrnl.record_action(
                "DATA_RELINK",
                {"object": obj.name, "old_mesh": old.name, "new_mesh": keeper.name,
                 "old_had_fake_user": had_fake_user},
                "dedup",
            )
            merged += 1
            relinked_verts[old.name] = len(old.vertices)
    saved_mb = sum(relinked_verts.values()) * EST_BYTES_PER_VERTEX / BYTES_PER_MB
    return {"merged": merged, "saved_mb": round(saved_mb, 2), "skipped": skipped}


def _image_relink_skip_reason(image, name, users_map):
    if image is None:
        return "image not found"
    if compat.is_linked(image):
        return "linked library image"
    if guards.image_keep_override(image):
        # KEEP means "never downscale or replace" — quantize and half-float
        # both honor it, and merging replaces the datablock outright.
        return "image marked Keep"
    if image.source in SKIP_IMAGE_SOURCES:
        return f"source is {image.source}"
    if not users_map.get(name):
        return "no render users"
    return None


def _prefer_keep_keeper(group):
    """Promote a KEEP-marked member to keeper so the group still merges.

    Without this a KEEP image sitting anywhere but position 0 blocks its own
    merge: it may not be replaced, yet the others are pointed at a keeper it
    is identical to. Order is otherwise untouched (keeper-first by user count).
    """
    for name in group[1:]:
        image = bpy.data.images.get(name)
        if image is not None and guards.image_keep_override(image):
            return [name] + [other for other in group if other != name]
    return list(group)


def relink_duplicate_images(groups, jrnl, users_map):
    """Repoint duplicate images' user nodes at the group keeper via TEX_SWAP.

    users_map: image name -> [(material_name, node_name)] from
    memory_model.images_used_by_render — passed in, never recomputed here.
    Revert safety: journal._revert_tex_swap removes new_image only when its
    users == 0; the keeper always retains its own original nodes, so it
    survives revert while each non-keeper is restored into its nodes.
    Returns {'merged': int, 'saved_mb': float, 'skipped': [(name, reason)]}.
    """
    merged = 0
    skipped = []
    saved_mb = 0.0
    for original_group in groups:
        group = _prefer_keep_keeper(original_group)
        keeper = bpy.data.images.get(group[0])
        if keeper is None or compat.is_linked(keeper):
            skipped.append((group[0], "keeper missing or linked"))
            continue
        for name in group[1:]:
            image = bpy.data.images.get(name)
            reason = _image_relink_skip_reason(image, name, users_map)
            if reason is not None:
                skipped.append((name, reason))
                continue
            had_fake_user = image.use_fake_user
            reassigned = reassign_user_nodes(users_map[name], keeper, image)
            if not reassigned:
                skipped.append((name, "user nodes not found"))
                continue
            image.use_fake_user = True
            # Payload shape must match journal._revert_tex_swap exactly.
            jrnl.record_action(
                "TEX_SWAP",
                {"orig_image": image.name, "new_image": keeper.name,
                 "users": reassigned, "orig_had_fake_user": had_fake_user},
                "dedup",
            )
            merged += 1
            saved_mb += memory_model.image_mb(image)
    return {"merged": merged, "saved_mb": round(saved_mb, 2), "skipped": skipped}


def trim_offscreen(scene, coverage, jrnl, keep_reflections=True, progress=None):
    """Disable ray visibility on meshes never near the camera frustum.

    Uses near_frustum_ever (generous margin) so frame-sampling gaps and fast
    movers are never trimmed. visible_shadow is always kept True; with
    keep_reflections (default) glossy/transmission stay on too, so mirrors and
    glass remain correct at the cost of a smaller speedup.
    progress: optional callable (index, total, label); exceptions ignored.
    Returns {'trimmed': int, 'objects': [names], 'skipped': [(name, reason)]}.
    """
    props = RAY_VIS_CONSERVATIVE if keep_reflections else RAY_VIS_PROPS
    trimmed = []
    skipped = []
    guard_cache = {}  # the cross-scene guard's maps, built once for the pass
    candidates = [obj for obj in scene.objects
                  if obj.type == "MESH" and not obj.hide_render]
    for index, obj in enumerate(candidates):
        guards.notify_progress(progress, index, len(candidates), obj.name)
        info = coverage.get(obj.name)
        if info is not None and info.near_frustum_ever:
            continue  # visible or near-visible: not a trim candidate
        if info is None:
            skipped.append((obj.name, "no coverage data"))
            continue
        if obj.scenequant.override != "AUTO":
            skipped.append((obj.name, f"override {obj.scenequant.override}"))
            continue
        if compat.is_linked(obj):
            skipped.append((obj.name, "linked object"))
            continue
        if guards.used_outside_scene(obj, scene, guard_cache):
            # visible_* is datablock-level: trimming from this scene's coverage
            # would also hide the object in every other scene rendering it.
            skipped.append((obj.name, "used by other scenes"))
            continue
        if is_emissive(obj):
            skipped.append((obj.name, "emissive material"))
            continue
        if obj.particle_systems:
            # Emitter bbox says nothing about where its particles/hair render.
            skipped.append((obj.name, "has particle systems"))
            continue
        changed = False
        for prop in props:
            # Object.visible_* are native Object RNA (3.0+), hasattr-guarded
            # inside set_prop for safety.
            changed = jrnl.set_prop(obj, prop, False, "trim") or changed
        if changed:
            trimmed.append(obj.name)
        else:
            skipped.append((obj.name, "ray visibility already off"))
    return {"trimmed": len(trimmed), "objects": trimmed, "skipped": skipped}


SUBDIV_MOD_TYPES = {"SUBSURF", "MULTIRES"}
# Below this frame-area fraction, render-only subdivision levels cannot be seen;
# each extra level still multiplies triangle count (and VRAM/BVH cost) by 4.
DEFAULT_SUBDIV_COVERAGE = 0.05


def trim_subdiv(scene, coverage, jrnl, coverage_threshold=DEFAULT_SUBDIV_COVERAGE,
                progress=None):
    """Cap render subdivision at the viewport level on low-coverage objects.

    The geometry side of quantization: an object covering <5% of the frame gets
    no visible benefit from subdiv levels the artist only ever saw applied in
    renders. progress: optional callable (index, total, label); exceptions
    ignored. Returns {'capped': int, 'objects': [names], 'saved_tris': int,
    'skipped': [(name, reason)]}.
    """
    capped = []
    skipped = []
    saved_tris = 0
    guard_cache = {}  # the cross-scene guard's maps, built once for the pass
    candidates = [obj for obj in scene.objects
                  if obj.type == "MESH" and obj.data is not None
                  and not obj.hide_render]
    for index, obj in enumerate(candidates):
        guards.notify_progress(progress, index, len(candidates), obj.name)
        info = coverage.get(obj.name)
        if info is not None and info.max_coverage >= coverage_threshold:
            continue  # big on screen: not a trim candidate
        # show_render False modifiers cost nothing at render time (and the
        # solver books no savings for them): capping would be a phantom write.
        mods = [m for m in obj.modifiers
                if m.type in SUBDIV_MOD_TYPES and m.show_render
                and m.render_levels > m.levels]
        if not mods:
            continue
        if info is None:
            skipped.append((obj.name, "no coverage data"))
            continue
        if obj.scenequant.override != "AUTO":
            skipped.append((obj.name, f"override {obj.scenequant.override}"))
            continue
        if compat.is_linked(obj):
            skipped.append((obj.name, "linked object"))
            continue
        if guards.used_outside_scene(obj, scene, guard_cache):
            # render_levels lives on the object's modifier: capping from this
            # scene's coverage would degrade every other scene rendering it.
            skipped.append((obj.name, "used by other scenes"))
            continue
        base_tris = max(1, len(obj.data.polygons)) * 2
        changed = False
        for mod in mods:
            if '"' in mod.name:
                # A double-quote breaks the journal's RNA path literal
                # modifiers["<name>"].render_levels -- unrevertable, so skip.
                skipped.append((obj.name, f"modifier name contains '\"': {mod.name}"))
                continue
            path = f'modifiers["{mod.name}"].render_levels'
            old_levels = mod.render_levels
            if jrnl.set_prop(obj, path, mod.levels, "trim"):
                saved_tris += base_tris * (4 ** old_levels - 4 ** mod.levels)
                changed = True
            else:
                skipped.append((obj.name, f"could not cap modifier {mod.name}"))
        if changed:
            capped.append(obj.name)
    return {"capped": len(capped), "objects": capped,
            "saved_tris": saved_tris, "skipped": skipped}


def _compute_coverage(scene):
    from ..analysis import coverage as coverage_analysis
    settings = scene.scenequant
    meshes = [obj for obj in scene.objects if obj.type == "MESH"]
    return coverage_analysis.compute_coverage(
        scene,
        meshes,
        frame_samples=settings.coverage_frame_samples,
        quality_factor=settings.quality_factor,
    )


def enable_paranoid_cull(scene, jrnl, margin=0.25, coverage=None):
    """Opt-in Cycles camera culling for zero-coverage, non-emissive AUTO objects.

    Scene-level flags plus the required per-object object.cycles.use_camera_cull
    (the scene flag alone does nothing). Recomputes coverage only when none is
    passed. Returns {'culled': int, 'objects': [names], 'skipped': [...]}.
    """
    if not compat.has(scene, "cycles"):
        return {"culled": 0, "objects": [],
                "skipped": [("scene", "cycles settings unavailable")]}
    if coverage is None:
        coverage = _compute_coverage(scene)
    jrnl.set_prop(scene, "cycles.use_camera_cull", True, "cull")
    jrnl.set_prop(scene, "cycles.camera_cull_margin", margin, "cull")
    culled = []
    skipped = []
    for obj in scene.objects:
        if obj.type != "MESH" or obj.hide_render:
            continue
        info = coverage.get(obj.name)
        if info is not None and (info.max_coverage > 0.0 or info.near_frustum_ever):
            continue  # ever visible: not a cull candidate
        if info is None:
            skipped.append((obj.name, "no coverage data"))
            continue
        if obj.scenequant.override != "AUTO":
            skipped.append((obj.name, f"override {obj.scenequant.override}"))
            continue
        if compat.is_linked(obj):
            skipped.append((obj.name, "linked object"))
            continue
        if is_emissive(obj):
            skipped.append((obj.name, "emissive material"))
            continue
        if obj.particle_systems:
            skipped.append((obj.name, "has particle systems"))
            continue
        if jrnl.set_prop(obj, "cycles.use_camera_cull", True, "cull"):
            culled.append(obj.name)
        else:
            skipped.append((obj.name, "cull flag unavailable or already set"))
    return {"culled": len(culled), "objects": culled, "skipped": skipped}


def is_emissive(obj):
    """True if any material slot plausibly emits light. Errs toward True:
    trimming a light source is worse than missing a trim candidate."""
    for slot in obj.material_slots:
        mat = slot.material
        if mat is None:
            continue
        tree = getattr(mat, "node_tree", None)
        if tree is None:
            # Nodeless/legacy material: cannot prove non-emissive.
            return True
        if _tree_is_emissive(tree, 0):
            return True
    return False


def _tree_is_emissive(tree, depth):
    if depth > MAX_GROUP_DEPTH:
        return True  # too deep to prove non-emissive
    for node in tree.nodes:
        if node.type == "EMISSION" and any(out.is_linked for out in node.outputs):
            return True
        if node.type == "BSDF_PRINCIPLED" and _principled_emits(node):
            return True
        if node.type == "GROUP" and node.node_tree is not None:
            if _tree_is_emissive(node.node_tree, depth + 1):
                return True
    return False


def _principled_emits(node):
    # Input is named 'Emission Strength' on 4.x/5.x; inputs.get guards others.
    strength = node.inputs.get("Emission Strength")
    if strength is not None:
        if strength.is_linked:
            return True  # texture-driven strength: cannot prove zero
        return getattr(strength, "default_value", 0.0) > 0.0
    color = node.inputs.get("Emission")  # pre-4.x color-only variant
    if color is None:
        return False
    if color.is_linked:
        return True
    value = getattr(color, "default_value", None)
    return value is not None and any(c > 0.0 for c in tuple(value)[:3])
