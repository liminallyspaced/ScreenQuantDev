# Shared apply-layer preconditions. Headless-safe: the scene is always passed
# in, never read from bpy.context. Guards only read; all writes stay with the
# callers (and therefore with the Journal).

import bpy

# user_map chains deeper than this cannot be proven scene-local and count as
# used outside: a false positive skips one optimization, a false negative
# silently corrupts another scene's render.
MAX_USER_HOPS = 4


def in_object_mode(obj):
    """True when obj is safe for datablock relinks. Assigning obj.data outside
    Object Mode is a silent no-op on 4.5-5.1 (no exception, no change)."""
    return getattr(obj, "mode", "OBJECT") == "OBJECT"


def image_keep_override(image):
    """True when the artist marked this image Keep. The Image property group is
    registered by the UI layer; getattr-guarded so this is safe before then."""
    override = getattr(image, "scenequant", None)
    return override is not None and getattr(override, "override", "AUTO") == "KEEP"


def notify_progress(progress, index, total, label):
    """Best-effort call of an optional progress(index, total, label) callback.
    The callback is UI-owned; a broken one must never abort an apply pass."""
    if progress is None:
        return
    try:
        progress(index, total, label)
    except Exception:
        pass


def used_outside_scene(datablock, scene, cache=None):
    """True when writes tied to `datablock` could leak into another scene.

    Precision, by case:
    - single-scene file: exact (always False);
    - Object: users_scene, PLUS collection instancing -- users_scene omits a
      scene that renders the object only through an Empty's
      instance_collection, which read as a clean false negative;
    - Mesh/Image/other IDs: best effort -- bpy.data.user_map users are chased
      through Material/Mesh/node-group hops until an Object (users_scene),
      World, or Scene settles it. Brush users are ignored (never rendered);
      any unknown user kind, or a chain deeper than MAX_USER_HOPS, counts as
      outside.
    cache: an optional dict, shared across one operation's calls, holding the
    collection maps the instancing check builds. Free in single-scene files.
    Cost: user_map scans all of bpy.data per hop. Per-candidate calls are fine
    for tens of datablocks in multi-scene files and free in single-scene files.
    """
    if len(bpy.data.scenes) <= 1:
        return False
    if isinstance(datablock, bpy.types.Object):
        if any(s is not scene for s in datablock.users_scene):
            return True
        return _instanced_into_other_scene(datablock, scene, cache)
    return _users_reach_outside(datablock, scene)


def _instanced_into_other_scene(obj, scene, cache):
    """True when another scene instances a collection that contains obj.

    Object.users_scene only lists scenes obj is LINKED into, so an Empty in
    scene B with instance_collection = a collection holding obj renders obj in
    B while users_scene says A only.
    """
    instancing = _collection_instancing_scenes(cache)
    if not instancing:
        return False
    parents = _collection_parents(cache)
    pending = list(obj.users_collection)
    seen = set()
    while pending:
        collection = pending.pop()
        if collection in seen:
            continue
        seen.add(collection)
        if any(s is not scene for s in instancing.get(collection, ())):
            return True
        # Instancing a parent collection renders every child's contents too.
        pending.extend(parents.get(collection, ()))
    return False


def _collection_instancing_scenes(cache):
    """collection -> set of scenes holding an object that instances it."""
    if cache is not None and "instancing_scenes" in cache:
        return cache["instancing_scenes"]
    mapping = {}
    for other in bpy.data.scenes:
        for obj in other.objects:
            source = getattr(obj, "instance_collection", None)
            if source is not None:
                mapping.setdefault(source, set()).add(other)
    if cache is not None:
        cache["instancing_scenes"] = mapping
    return mapping


def _collection_parents(cache):
    """child collection -> [collections nesting it]; bpy exposes no parent."""
    if cache is not None and "collection_parents" in cache:
        return cache["collection_parents"]
    parents = {}
    for collection in bpy.data.collections:
        for child in collection.children:
            parents.setdefault(child, []).append(collection)
    if cache is not None:
        cache["collection_parents"] = parents
    return parents


def _users_reach_outside(datablock, scene):
    pending = {datablock}
    seen = set()
    for _hop in range(MAX_USER_HOPS):
        if not pending:
            return False
        try:
            user_map = bpy.data.user_map(subset=list(pending))
        except (TypeError, ValueError):
            return True  # API refused the subset: cannot prove scene-local
        seen |= pending
        pending = set()
        for users in user_map.values():
            for user in users:
                if user in seen:
                    continue
                verdict = _user_reaches_outside(user, scene)
                if verdict is True:
                    return True
                if verdict is None:
                    pending.add(user)
    return bool(pending)  # unresolved chains: cannot prove scene-local


def _user_reaches_outside(user, scene):
    """True = provably outside, False = settled inside, None = chase further."""
    if isinstance(user, bpy.types.Object):
        return any(s is not scene for s in user.users_scene)
    if isinstance(user, bpy.types.Scene):
        return user is not scene
    if isinstance(user, bpy.types.World):
        return any(s is not scene and s.world is user for s in bpy.data.scenes)
    if isinstance(user, (bpy.types.Material, bpy.types.Mesh, bpy.types.NodeTree)):
        return None
    if isinstance(user, bpy.types.Brush):
        return False  # brushes never contribute to a render
    return True  # unknown user kind: cannot prove scene-local
