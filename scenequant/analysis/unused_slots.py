# L3 UNUSED_SLOTS: prune material slots that no polygon references.
# Graph/datablock lever. Not a Cycles RNA knob.
#
# Walks hide_render=False MESH objects. Unique local meshes only
# (mesh.library / obj.library skipped). Slot index is polygon.material_index.
# Apply removes from the high index down so remaining unused indices stay
# valid; Blender's materials.pop remaps used face indices. Journal one
# SLOT_REMOVE per slot so revert can reinsert the material at that index.
#
# NOT in default Auto Make it Fast until a measured loft pair exists.
# No bpy.ops. Importable without Blender (duck-typed scene + meshes).

ACTION_KIND = "SLOT_REMOVE"
SPEED_KIND = "UNUSED_SLOTS"


def _protected(obj):
    override = getattr(getattr(obj, "scenequant", None), "override", "AUTO")
    return override not in (None, "", "AUTO")


def _is_linked_id(datablock):
    if datablock is None:
        return False
    if getattr(datablock, "library", None) is not None:
        return True
    return getattr(datablock, "override_library", None) is not None


def _slot_material(item):
    if item is None:
        return None
    return getattr(item, "material", item)


def _materials(mesh):
    return getattr(mesh, "materials", None)


def _used_indices(mesh):
    used = set()
    polys = getattr(mesh, "polygons", None)
    if not polys:
        return used
    for poly in polys:
        used.add(int(getattr(poly, "material_index", 0) or 0))
    return used


def _n_faces(mesh):
    polys = getattr(mesh, "polygons", None)
    if not polys:
        return 0
    try:
        return len(polys)
    except TypeError:
        return 0


def _iter_slot_materials(obj, mesh):
    """Yield (index, material) for the mesh slot list.

    Prefer mesh.materials (what polygon.material_index addresses). Fall
    back to the representative object's material_slots.
    """
    mats = _materials(mesh)
    if mats is not None:
        try:
            n = len(mats)
        except TypeError:
            n = 0
        if n:
            for i, item in enumerate(mats):
                yield i, _slot_material(item)
            return
    slots = getattr(obj, "material_slots", None) or ()
    for i, slot in enumerate(slots):
        yield i, _slot_material(slot)


def classify_unused_slots(scene):
    """Return one prune record per unused filled slot on unique local meshes.

    Skip linked meshes, HERO/EXCLUDE objects (any render-visible user),
    and a prune that would leave zero materials on a mesh that has faces.
    """
    groups = {}
    order = []
    for obj in getattr(scene, "objects", ()) or ():
        if getattr(obj, "type", "") != "MESH":
            continue
        if getattr(obj, "hide_render", False):
            continue
        mesh = getattr(obj, "data", None)
        if mesh is None:
            continue
        key = id(mesh)
        if key not in groups:
            groups[key] = {"mesh": mesh, "objects": []}
            order.append(key)
        groups[key]["objects"].append(obj)

    records = []
    for key in order:
        group = groups[key]
        mesh = group["mesh"]
        objects = group["objects"]
        if _is_linked_id(mesh):
            continue
        if any(_is_linked_id(obj) for obj in objects):
            continue
        if any(_protected(obj) for obj in objects):
            continue
        records.extend(_candidates_for_mesh(mesh, objects))
    return records


def _candidates_for_mesh(mesh, objects):
    obj = objects[0]
    slots = list(_iter_slot_materials(obj, mesh))
    if not slots:
        return []
    used = _used_indices(mesh)
    unused = []
    filled = []
    for index, mat in slots:
        if mat is None:
            continue
        filled.append(index)
        if index not in used:
            unused.append((index, mat))
    if not unused:
        return []
    n_faces = _n_faces(mesh)
    remaining = len(filled) - len(unused)
    if remaining <= 0 and n_faces > 0:
        return []
    users = [getattr(o, "name", "") or "" for o in objects]
    mesh_name = getattr(mesh, "name", "") or ""
    obj_name = getattr(obj, "name", "") or ""
    out = []
    for index, mat in unused:
        out.append({
            "mesh": mesh_name,
            "object": obj_name,
            "index": int(index),
            "material": getattr(mat, "name", "") or "",
            "users": list(users),
            "n_faces": n_faces,
        })
    return out


def inventory_counts(records):
    meshes = set()
    for rec in records or ():
        name = rec.get("mesh")
        if name:
            meshes.add(name)
        else:
            meshes.add(id(rec))
    return {
        "UNIQUE_MESHES_WITH_UNUSED": len(meshes),
        "UNIQUE_UNUSED_SLOTS": len(list(records or ())),
    }


def format_inventory(records):
    records = list(records or ())
    counts = inventory_counts(records)
    lines = [
        "UNUSED_SLOTS inventory (apply exists; Auto off; no time claim)",
        "  UNIQUE_MESHES_WITH_UNUSED=%d  UNIQUE_UNUSED_SLOTS=%d"
        % (counts["UNIQUE_MESHES_WITH_UNUSED"],
           counts["UNIQUE_UNUSED_SLOTS"]),
    ]
    for rec in records:
        lines.append(
            "  mesh=%s  index=%s  material=%s  users=%s"
            % (rec.get("mesh", ""), rec.get("index", ""),
               rec.get("material", ""),
               ",".join(rec.get("users") or [])))
    return "\n".join(lines)


def print_inventory(records):
    print(format_inventory(records))


def _find_mesh(scene, name):
    for obj in getattr(scene, "objects", ()) or ():
        mesh = getattr(obj, "data", None)
        if mesh is not None and getattr(mesh, "name", None) == name:
            return mesh, obj
    return None, None


def _shift_poly_indices(mesh, index, delta):
    polys = getattr(mesh, "polygons", None)
    if not polys or not delta:
        return
    if delta > 0:
        for poly in polys:
            if getattr(poly, "material_index", 0) >= index:
                poly.material_index += delta
    else:
        for poly in polys:
            if getattr(poly, "material_index", 0) > index:
                poly.material_index += delta


def _pop_material(mesh, index):
    """Remove slot `index`. bpy IDMaterials.pop remaps face indices;
    a plain list does not, so we remap lists ourselves. Duck-typed
    collections that implement pop() are assumed to remap like Blender.
    """
    mats = _materials(mesh)
    if mats is None:
        return False
    try:
        n = len(mats)
    except TypeError:
        return False
    if not (0 <= index < n):
        return False
    pop = getattr(mats, "pop", None)
    if pop is not None:
        try:
            pop(index=index)
        except TypeError:
            try:
                pop(index)
            except Exception:
                return False
        except Exception:
            return False
        if len(mats) != n - 1:
            return False
        if isinstance(mats, list):
            _shift_poly_indices(mesh, index, -1)
        return True
    try:
        del mats[index]
    except Exception:
        return False
    if len(mats) != n - 1:
        return False
    _shift_poly_indices(mesh, index, -1)
    return True


def _insert_material(mesh, index, mat):
    """Reinsert `mat` at `index` and bump face indices >= index.

    bpy IDMaterials has append and item assignment, not insert(). Append
    at end then rotate pointers so we do not pop (pop would remap twice).
    """
    mats = _materials(mesh)
    if mats is None or index < 0:
        return False
    try:
        n = len(mats)
    except TypeError:
        return False
    append = getattr(mats, "append", None)
    if append is None:
        return False
    try:
        while len(mats) < index:
            append(None)
        if len(mats) == index:
            append(mat)
            return True
        append(mat)
        last = len(mats) - 1
        for i in range(last, index, -1):
            mats[i] = mats[i - 1]
        mats[index] = mat
    except Exception:
        return False
    _shift_poly_indices(mesh, index, +1)
    return True


def _material_at(mesh, index):
    mats = _materials(mesh)
    if mats is None:
        return None
    try:
        if not (0 <= index < len(mats)):
            return None
        return _slot_material(mats[index])
    except Exception:
        return None


def _safe_to_prune(mesh, recs):
    n_faces = _n_faces(mesh)
    mats = _materials(mesh)
    filled = 0
    if mats is not None:
        for item in mats:
            if _slot_material(item) is not None:
                filled += 1
    prune_n = len(recs)
    remaining = filled - prune_n
    if remaining <= 0 and n_faces > 0:
        return False
    return True


def apply_unused_slots(scene, jrnl, records=None, tag="speed"):
    """Remove unused filled slots, high index first. Journal SLOT_REMOVE.

    Not a Cycles RNA knob. Not called by Make it Fast Auto.
    """
    if records is None:
        records = classify_unused_slots(scene)
    grouped = {}
    order = []
    for rec in records or ():
        key = rec.get("mesh")
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(rec)

    applied = []
    for key in order:
        recs = grouped[key]
        mesh, _obj = _find_mesh(scene, key)
        if mesh is None or _is_linked_id(mesh):
            continue
        recs_sorted = sorted(recs, key=lambda r: int(r.get("index", 0)),
                             reverse=True)
        if not _safe_to_prune(mesh, recs_sorted):
            continue
        for rec in recs_sorted:
            idx = int(rec.get("index", -1))
            mat = _material_at(mesh, idx)
            if mat is None:
                continue
            payload = {
                "mesh": key,
                "index": idx,
                "material": getattr(mat, "name", "") or rec.get("material", ""),
                "object": rec.get("object", ""),
            }
            if not _pop_material(mesh, idx):
                continue
            if jrnl is not None:
                jrnl.record_action(ACTION_KIND, payload, tag)
            applied.append(payload)
    return applied


def _lookup_material(name, scene=None, materials=None):
    if not name:
        return None
    if isinstance(materials, dict) and name in materials:
        return materials[name]
    if materials is not None and not isinstance(materials, dict):
        for item in materials:
            if getattr(item, "name", None) == name:
                return item
    if scene is not None:
        getter = getattr(scene, "materials_by_name", None)
        if isinstance(getter, dict) and name in getter:
            return getter[name]
        for obj in getattr(scene, "objects", ()) or ():
            mesh = getattr(obj, "data", None)
            if mesh is None:
                continue
            mats = _materials(mesh)
            if mats is None:
                continue
            for item in mats:
                mat = _slot_material(item)
                if mat is not None and getattr(mat, "name", None) == name:
                    return mat
            for slot in getattr(obj, "material_slots", ()) or ():
                mat = _slot_material(slot)
                if mat is not None and getattr(mat, "name", None) == name:
                    return mat
    try:
        import bpy
        return bpy.data.materials.get(name)
    except Exception:
        return None


def restore_slot_remove_on_mesh(mesh, payload, material=None):
    """Reinsert one SLOT_REMOVE payload onto an already-resolved mesh."""
    if mesh is None or not isinstance(payload, dict):
        return False
    if _is_linked_id(mesh):
        return False
    index = payload.get("index")
    try:
        index = int(index)
    except (TypeError, ValueError):
        return False
    if index < 0:
        return False
    mat = material
    if mat is None:
        return False
    return _insert_material(mesh, index, mat)


def restore_slot_remove(payload, meshes=None, materials=None, scene=None):
    """Name-lookup helper for tests and journal revert."""
    if not isinstance(payload, dict):
        return False
    name = payload.get("mesh")
    mesh = None
    if isinstance(meshes, dict):
        mesh = meshes.get(name)
    elif meshes is not None:
        for item in meshes:
            if getattr(item, "name", None) == name:
                mesh = item
                break
    obj = None
    if mesh is None and scene is not None:
        mesh, obj = _find_mesh(scene, name)
    if mesh is None:
        try:
            import bpy
            mesh = bpy.data.meshes.get(name) if isinstance(name, str) else None
        except Exception:
            mesh = None
    mat = _lookup_material(payload.get("material"), scene=scene,
                           materials=materials)
    return restore_slot_remove_on_mesh(mesh, payload, material=mat)


def revert_unused_slots(scene, jrnl, materials=None):
    """Restore SLOT_REMOVE entries recorded on jrnl. Returns insert count."""
    entries = list(getattr(jrnl, "entries", None) or ())
    kept = []
    count = 0
    # Newest-first so a low index is restored before a higher one that
    # was removed first (apply pops high→low, journal appends in that order).
    for entry in reversed(entries):
        if isinstance(entry, dict) and entry.get("kind") == ACTION_KIND:
            payload = entry.get("payload") or {}
            if restore_slot_remove(payload, scene=scene, materials=materials):
                count += 1
                continue
        kept.append(entry)
    kept.reverse()
    if hasattr(jrnl, "entries"):
        jrnl.entries = kept
    return count
