# L3 UNUSED_SLOTS: prune unused filled slots whose shader is unique vs
# used-face materials. Graph/datablock lever. Not a Cycles RNA knob.
#
# Cycles get_used_shaders() unions unique shaders. A second slot of an
# already-used material is RNA noise (no extra compile, no extra attrs).
# A unique unused material still compiles and unions its attribute
# requests onto the mesh — those are the keepers.
#
# Walks hide_render=False MESH objects. Unique local meshes only
# (mesh.library / obj.library skipped). Slot index is polygon.material_index.
# Apply pops only unique unused slots whose extra_attrs is non-empty AND
# does not contain GROUP — that is the Cycles extra-attribute tax
# (UV / UV_TANGENT / VCOL / GENERATED). Empty extra_attrs still compiles
# the unique shader but does not union extra mesh attributes vs used-face
# shaders; GROUP is unexpanded so extra is unproven. Inventory still
# lists every unique unused slot. Apply removes from the high index down
# so remaining unused indices stay valid; Blender's materials.pop remaps
# used face indices. Journal one SLOT_REMOVE per slot so revert can
# reinsert the material at that index.
#
# NOT in default Auto Make it Fast until a measured loft pair exists.
# unused_slots_actions is not called from build_speed_plan.
# No bpy.ops. Importable without Blender (duck-typed scene + meshes).

ACTION_KIND = "SLOT_REMOVE"
SPEED_KIND = "UNUSED_SLOTS"
INVENTORY_EXAMPLE_ROWS = 12

IMAGE_NODE_TYPES = frozenset({"TEX_IMAGE", "TEX_ENVIRONMENT"})
IMAGE_NODE_IDNAMES = frozenset({
    "ShaderNodeTexImage", "ShaderNodeTexEnvironment",
})
UVMAP_TYPES = frozenset({"UVMAP"})
UVMAP_IDNAMES = frozenset({"ShaderNodeUVMap"})
TANGENT_TYPES = frozenset({"TANGENT", "NORMAL_MAP"})
TANGENT_IDNAMES = frozenset({
    "ShaderNodeTangent", "ShaderNodeNormalMap",
})
TEX_COORD_TYPES = frozenset({"TEX_COORD"})
TEX_COORD_IDNAMES = frozenset({"ShaderNodeTexCoord"})
ATTRIBUTE_TYPES = frozenset({"ATTRIBUTE"})
ATTRIBUTE_IDNAMES = frozenset({"ShaderNodeAttribute"})
VCOL_NODE_TYPES = frozenset({"VERTEX_COLOR", "VERTEXCOLOR"})
VCOL_NODE_IDNAMES = frozenset({"ShaderNodeVertexColor"})
GROUP_TYPES = frozenset({"GROUP"})
GROUP_IDNAMES = frozenset({"ShaderNodeGroup"})
GENERATED_OR_OBJECT = frozenset({"GENERATED", "OBJECT"})
VCOL_NAME_TOKENS = frozenset({
    "color", "col", "vcol", "vertexcolor", "vertexcol", "vertexcolour",
    "cd", "colattr", "paint",
})


class _RecordList(list):
    """Prune records plus skip counters for inventory_counts."""

    def __init__(self, records=(), skipped_duplicate_unused=0):
        super().__init__(records)
        self.skipped_duplicate_unused = int(skipped_duplicate_unused or 0)


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


def _node_type(node):
    return getattr(node, "type", "") or ""


def _sock(owner, *names, collection="inputs"):
    socks = getattr(owner, collection, None)
    if socks is None:
        return None
    getter = getattr(socks, "get", None)
    if getter is not None:
        for name in names:
            sock = getter(name)
            if sock is not None:
                return sock
    for sock in socks or ():
        ident = getattr(sock, "identifier", None)
        name = getattr(sock, "name", None)
        if ident in names or name in names:
            return sock
    return None


def _iter_socks(owner, collection="inputs"):
    socks = getattr(owner, collection, None)
    if socks is None:
        return
    for sock in socks or ():
        yield sock


def _iter_links(sock):
    if sock is None:
        return
    links = getattr(sock, "links", None)
    if links:
        for link in links:
            yield link
        return
    link = getattr(sock, "link", None)
    if link is not None:
        yield link
        return
    from_node = getattr(sock, "from_node", None)
    if from_node is not None:
        yield _FakeLink(from_node, getattr(sock, "from_socket", None))


class _FakeLink:
    def __init__(self, from_node, from_socket):
        self.from_node = from_node
        self.from_socket = from_socket


def _socket_name(sock):
    if sock is None:
        return ""
    return getattr(sock, "identifier", None) or getattr(sock, "name", "") or ""


def _is_type(node, types, idnames):
    if node is None:
        return False
    if _node_type(node) in types:
        return True
    return getattr(node, "bl_idname", "") in idnames


def _output_linked(node, *names):
    sock = _sock(node, *names, collection="outputs")
    if sock is None:
        return False
    if getattr(sock, "is_linked", False):
        return True
    links = getattr(sock, "links", None)
    return bool(links)


def _vector_coord_kind(node):
    """Return GENERATED/OBJECT if Vector is explicitly those TEX_COORD outputs."""
    vec = _sock(node, "Vector")
    if vec is None or not getattr(vec, "is_linked", False):
        return None
    for link in _iter_links(vec):
        from_node = getattr(link, "from_node", None)
        from_sock = getattr(link, "from_socket", None)
        if not _is_type(from_node, TEX_COORD_TYPES, TEX_COORD_IDNAMES):
            continue
        name = _socket_name(from_sock).upper()
        if name in GENERATED_OR_OBJECT:
            return name
    return None


def _norm_attr_name(name):
    raw = (name or "").strip().lower()
    return raw.replace(" ", "").replace("_", "").replace("-", "")


def _is_vcol_name(name):
    token = _norm_attr_name(name)
    if not token:
        return False
    if token in VCOL_NAME_TOKENS:
        return True
    if "vcol" in token or "vertexcol" in token or "vertexcolour" in token:
        return True
    if token.startswith("col") and token != "collision":
        return True
    return False


def _attribute_is_vcol(node):
    name = (getattr(node, "attribute_name", None)
            or getattr(node, "layer_name", None)
            or "")
    if _is_vcol_name(name):
        return True
    data_type = str(getattr(node, "data_type", "") or "").upper()
    if data_type in {"COLOR", "BYTE_COLOR", "FLOAT_COLOR"}:
        return True
    return False


def _material_attr_tokens(material):
    """Conservative attr tokens a material may request on a mesh.

    Duck-typed: no bpy. Walks node types, does not recurse into groups.
    GROUP is recorded as an unknown extra so inventory can list it; apply
    does not pop GROUP (tree not expanded).
    """
    tokens = set()
    if material is None:
        return tokens
    if getattr(material, "use_nodes", True) is False:
        return tokens
    tree = getattr(material, "node_tree", None)
    if tree is None:
        return tokens
    for node in getattr(tree, "nodes", ()) or ():
        if _is_type(node, GROUP_TYPES, GROUP_IDNAMES):
            tokens.add("GROUP")
            continue
        if _is_type(node, IMAGE_NODE_TYPES, IMAGE_NODE_IDNAMES):
            if _vector_coord_kind(node) not in GENERATED_OR_OBJECT:
                tokens.add("UV")
            continue
        if _is_type(node, UVMAP_TYPES, UVMAP_IDNAMES):
            tokens.add("UV")
            continue
        if _is_type(node, TANGENT_TYPES, TANGENT_IDNAMES):
            tokens.add("UV_TANGENT")
            continue
        if _is_type(node, VCOL_NODE_TYPES, VCOL_NODE_IDNAMES):
            tokens.add("VCOL")
            continue
        if _is_type(node, ATTRIBUTE_TYPES, ATTRIBUTE_IDNAMES):
            if _attribute_is_vcol(node):
                tokens.add("VCOL")
            continue
        if _is_type(node, TEX_COORD_TYPES, TEX_COORD_IDNAMES):
            if _output_linked(node, "Generated", "GENERATED"):
                tokens.add("GENERATED")
            if _output_linked(node, "UV"):
                tokens.add("UV")
            continue
    return tokens


def classify_unused_slots(scene):
    """Return one prune record per unique unused filled slot.

    Skip linked meshes, HERO/EXCLUDE objects (any render-visible user),
    a prune that would leave zero materials on a mesh that has faces,
    and unused slots whose material is already among used-face materials
    (duplicate of a live shader — Cycles get_used_shaders no-op).
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
    skipped_duplicate = 0
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
        recs, skipped = _candidates_for_mesh(mesh, objects)
        records.extend(recs)
        skipped_duplicate += skipped
    return _RecordList(records, skipped_duplicate)


def _candidates_for_mesh(mesh, objects):
    obj = objects[0]
    slots = list(_iter_slot_materials(obj, mesh))
    if not slots:
        return [], 0
    used = _used_indices(mesh)
    unused = []
    filled = []
    used_mats = set()
    for index, mat in slots:
        if mat is None:
            continue
        filled.append(index)
        if index in used:
            used_mats.add(mat)
        else:
            unused.append((index, mat))
    if not unused:
        return [], 0
    unique_unused = []
    skipped = 0
    for index, mat in unused:
        if mat in used_mats:
            skipped += 1
            continue
        unique_unused.append((index, mat))
    if not unique_unused:
        return [], skipped
    n_faces = _n_faces(mesh)
    remaining = len(filled) - len(unique_unused)
    if remaining <= 0 and n_faces > 0:
        return [], skipped
    users = [getattr(o, "name", "") or "" for o in objects]
    mesh_name = getattr(mesh, "name", "") or ""
    obj_name = getattr(obj, "name", "") or ""
    used_tokens = set()
    for mat in used_mats:
        used_tokens |= _material_attr_tokens(mat)
    out = []
    for index, mat in unique_unused:
        tokens = _material_attr_tokens(mat)
        extra = sorted(tokens - used_tokens)
        out.append({
            "mesh": mesh_name,
            "object": obj_name,
            "index": int(index),
            "material": getattr(mat, "name", "") or "",
            "users": list(users),
            "n_faces": n_faces,
            "unique_shader": True,
            "extra_attrs": extra,
        })
    return out, skipped


def extra_attr_apply_eligible(rec):
    """True when apply should pop this unique unused slot.

    extra_attrs must be non-empty and must not contain GROUP. Empty
    extra_attrs: unique shader still compiles, no extra attr union.
    GROUP: node group not expanded, extra unproven.
    """
    extra = list((rec or {}).get("extra_attrs") or [])
    if not extra:
        return False
    if "GROUP" in extra:
        return False
    return True


def inventory_counts(records):
    skipped = int(getattr(records, "skipped_duplicate_unused", 0) or 0)
    recs = list(records or ())
    meshes = set()
    shaders = set()
    extra_slots = 0
    extra_apply_slots = 0
    extra_shaders = set()
    for rec in recs:
        name = rec.get("mesh")
        if name:
            meshes.add(name)
        else:
            meshes.add(id(rec))
        mat = rec.get("material")
        if mat:
            shaders.add(mat)
        extra = rec.get("extra_attrs") or []
        if extra:
            extra_slots += 1
            if mat:
                extra_shaders.add(mat)
        if extra_attr_apply_eligible(rec):
            extra_apply_slots += 1
    return {
        "UNIQUE_MESHES_WITH_UNUSED": len(meshes),
        "UNIQUE_UNUSED_SLOTS": len(recs),
        "UNIQUE_UNUSED_SHADERS": len(shaders),
        "SKIPPED_DUPLICATE_UNUSED": skipped,
        "EXTRA_ATTR_SLOTS": extra_slots,
        "EXTRA_ATTR_APPLY_SLOTS": extra_apply_slots,
        "EXTRA_ATTR_SHADERS": len(extra_shaders),
    }


def format_inventory(records):
    counts = inventory_counts(records)
    recs = list(records or ())
    lines = [
        "UNUSED_SLOTS inventory (apply exists; Auto off; no time claim)",
        "  UNIQUE_MESHES_WITH_UNUSED=%d  UNIQUE_UNUSED_SLOTS=%d"
        % (counts["UNIQUE_MESHES_WITH_UNUSED"],
           counts["UNIQUE_UNUSED_SLOTS"]),
        "  UNIQUE_UNUSED_SHADERS=%d  SKIPPED_DUPLICATE_UNUSED=%d  "
        "EXTRA_ATTR_SLOTS=%d  EXTRA_ATTR_APPLY_SLOTS=%d  EXTRA_ATTR_SHADERS=%d"
        % (counts["UNIQUE_UNUSED_SHADERS"],
           counts["SKIPPED_DUPLICATE_UNUSED"],
           counts["EXTRA_ATTR_SLOTS"],
           counts["EXTRA_ATTR_APPLY_SLOTS"],
           counts["EXTRA_ATTR_SHADERS"]),
        "  APPLY vs inventory: EXTRA_ATTR_APPLY_SLOTS=%d of "
        "UNIQUE_UNUSED_SLOTS=%d (skip empty extra_attrs and GROUP)"
        % (counts["EXTRA_ATTR_APPLY_SLOTS"], counts["UNIQUE_UNUSED_SLOTS"]),
    ]
    shader_counts = {}
    extra_shader_counts = {}
    apply_shader_counts = {}
    token_hist = {}
    for rec in recs:
        mat = rec.get("material") or ""
        shader_counts[mat] = shader_counts.get(mat, 0) + 1
        extra = rec.get("extra_attrs") or []
        if extra:
            extra_shader_counts[mat] = extra_shader_counts.get(mat, 0) + 1
            for tok in extra:
                token_hist[tok] = token_hist.get(tok, 0) + 1
        if extra_attr_apply_eligible(rec):
            apply_shader_counts[mat] = apply_shader_counts.get(mat, 0) + 1
    lines.append("  UNIQUE_UNUSED_SHADERS list (material, slots):")
    for mat in sorted(shader_counts):
        lines.append("    %s  %d" % (mat, shader_counts[mat]))
    lines.append("  EXTRA_ATTR_SHADERS list (material, slots, apply):")
    for mat in sorted(extra_shader_counts):
        tag = "APPLY" if apply_shader_counts.get(mat, 0) else "skip"
        lines.append("    %s  %d  %s" % (mat, extra_shader_counts[mat], tag))
    if token_hist:
        parts = ["%s=%d" % (k, token_hist[k]) for k in sorted(token_hist)]
        lines.append("  extra_attrs tokens: " + " ".join(parts))
    shown = recs[:INVENTORY_EXAMPLE_ROWS]
    for rec in shown:
        extra = rec.get("extra_attrs") or []
        extra_s = (" extra_attrs=%s" % ",".join(extra)) if extra else ""
        lines.append(
            "  mesh=%s  index=%s  material=%s  unique_shader=%s  users=%s%s"
            % (rec.get("mesh", ""), rec.get("index", ""),
               rec.get("material", ""), rec.get("unique_shader", True),
               ",".join(rec.get("users") or []), extra_s))
    more = len(recs) - len(shown)
    if more > 0:
        lines.append("  ... %d more" % more)
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
    """Pop unique unused slots with proven extra attrs. Journal SLOT_REMOVE.

    Only records whose extra_attrs is non-empty and does not contain GROUP.
    Empty extra_attrs and GROUP stay. Unique-shader / linked / HERO gates
    live in classify; remaining>=1 if faces is re-checked here. Not a
    Cycles RNA knob. Not called by Make it Fast Auto.
    """
    if records is None:
        records = classify_unused_slots(scene)
    records = [rec for rec in (records or ())
               if extra_attr_apply_eligible(rec)]
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
