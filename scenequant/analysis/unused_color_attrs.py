# L3b UNUSED_COLOR_ATTRS: inventory color attributes no used-face shader
# references. Graph/datablock lever. Not a Cycles RNA knob.
#
# Walks hide_render=False MESH objects. Unique local meshes only
# (mesh.library / obj.library / override skipped). Skip HERO/EXCLUDE.
# Skip any mesh whose objects have modifiers (Geometry Nodes / deform
# may consume attributes — conservative).
#
# A color attribute (mesh.color_attributes, or vertex_colors fallback)
# is UNUSED when no used-face material on that mesh names it via
# ATTRIBUTE / VERTEX_COLOR / Color Attribute (name match, case-sensitive).
# UV maps (including UVMap) and position/normal built-ins are never
# candidates.
#
# Inventory-only this pass: apply would drop pixel values and revert
# can only restore an empty same-named layer. Not in default Auto
# Make it Fast. No bpy.ops. Importable without Blender (duck-typed).

SPEED_KIND = "UNUSED_COLOR_ATTRS"

ATTRIBUTE_TYPES = frozenset({
    "ATTRIBUTE", "VERTEX_COLOR", "VERTEXCOLOR", "COLOR_ATTRIBUTE",
})
ATTRIBUTE_IDNAMES = frozenset({
    "ShaderNodeAttribute", "ShaderNodeVertexColor",
    "ShaderNodeColorAttribute",
})
GROUP_TYPES = frozenset({"GROUP"})
GROUP_IDNAMES = frozenset({"ShaderNodeGroup"})
COLOR_DATA_TYPES = frozenset({
    "FLOAT_COLOR", "BYTE_COLOR", "COLOR",
})
BUILTIN_ATTR_NAMES = frozenset({
    "position", "normal", "tangent", "undisplaced", "generated",
})


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


def _iter_slot_materials(obj, mesh):
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


def _has_modifiers(obj):
    mods = getattr(obj, "modifiers", None)
    if mods is None:
        return False
    try:
        if len(mods) > 0:
            return True
    except TypeError:
        pass
    try:
        for _item in mods:
            return True
    except TypeError:
        return bool(mods)
    return False


def _uv_layer_names(mesh):
    names = set()
    for layer in getattr(mesh, "uv_layers", None) or ():
        name = getattr(layer, "name", None)
        if name:
            names.add(name)
    return names


def _iter_color_attrs(mesh):
    if hasattr(mesh, "color_attributes"):
        for attr in getattr(mesh, "color_attributes") or ():
            yield attr
        return
    for attr in getattr(mesh, "vertex_colors", None) or ():
        yield attr


def _is_color_attr(attr):
    dtype = str(getattr(attr, "data_type", "") or "").upper()
    if not dtype:
        return True
    return dtype in COLOR_DATA_TYPES


def _is_builtin_name(name):
    return (name or "").lower() in BUILTIN_ATTR_NAMES


def _node_type(node):
    return getattr(node, "type", "") or ""


def _is_type(node, types, idnames):
    if node is None:
        return False
    if _node_type(node) in types:
        return True
    return getattr(node, "bl_idname", "") in idnames


def _node_attr_name(node):
    for key in ("layer_name", "attribute_name"):
        value = getattr(node, key, None)
        if isinstance(value, str) and value:
            return value
    return ""


def _material_attr_refs(material):
    """Return (referenced_names, has_group) for a material node tree."""
    names = set()
    has_group = False
    if material is None:
        return names, has_group
    if getattr(material, "use_nodes", True) is False:
        return names, has_group
    tree = getattr(material, "node_tree", None)
    if tree is None:
        return names, has_group
    for node in getattr(tree, "nodes", ()) or ():
        if _is_type(node, GROUP_TYPES, GROUP_IDNAMES):
            has_group = True
            continue
        if _is_type(node, ATTRIBUTE_TYPES, ATTRIBUTE_IDNAMES):
            name = _node_attr_name(node)
            if name:
                names.add(name)
    return names, has_group


def classify_unused_color_attrs(scene):
    """Return one inventory record per unused color attribute.

    Skip linked meshes, HERO/EXCLUDE objects (any render-visible user),
    meshes with modifiers, UV maps, and position/normal built-ins.
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
        if any(_has_modifiers(obj) for obj in objects):
            continue
        records.extend(_candidates_for_mesh(mesh, objects))
    return records


def _candidates_for_mesh(mesh, objects):
    obj = objects[0]
    used = _used_indices(mesh)
    used_mats = []
    seen = set()
    for index, mat in _iter_slot_materials(obj, mesh):
        if mat is None or index not in used:
            continue
        ident = id(mat)
        if ident in seen:
            continue
        seen.add(ident)
        used_mats.append(mat)

    referenced = set()
    for mat in used_mats:
        names, has_group = _material_attr_refs(mat)
        if has_group:
            return []
        referenced |= names

    uv_names = _uv_layer_names(mesh)
    users = [getattr(o, "name", "") or "" for o in objects]
    mesh_name = getattr(mesh, "name", "") or ""
    obj_name = getattr(obj, "name", "") or ""
    out = []
    for attr in _iter_color_attrs(mesh):
        name = getattr(attr, "name", "") or ""
        if not name:
            continue
        if name == "UVMap" or name in uv_names:
            continue
        if _is_builtin_name(name):
            continue
        if not _is_color_attr(attr):
            continue
        if name in referenced:
            continue
        out.append({
            "mesh": mesh_name,
            "object": obj_name,
            "attr_name": name,
            "domain": getattr(attr, "domain", "") or "",
            "data_type": getattr(attr, "data_type", "") or "",
            "users": list(users),
        })
    return out


def inventory_counts(records):
    recs = list(records or ())
    meshes = set()
    for rec in recs:
        name = rec.get("mesh")
        if name:
            meshes.add(name)
        else:
            meshes.add(id(rec))
    return {
        "UNIQUE_MESHES_WITH_UNUSED": len(meshes),
        "UNUSED_COLOR_ATTRS": len(recs),
    }


def format_inventory(records):
    counts = inventory_counts(records)
    recs = list(records or ())
    lines = [
        "UNUSED_COLOR_ATTRS inventory (inventory only; Auto off; no time claim)",
        "  UNIQUE_MESHES_WITH_UNUSED=%d  UNUSED_COLOR_ATTRS=%d"
        % (counts["UNIQUE_MESHES_WITH_UNUSED"],
           counts["UNUSED_COLOR_ATTRS"]),
    ]
    for rec in recs:
        lines.append(
            "  mesh=%s  attr=%s  domain=%s  data_type=%s  users=%s"
            % (rec.get("mesh", ""), rec.get("attr_name", ""),
               rec.get("domain", ""), rec.get("data_type", ""),
               ",".join(rec.get("users") or [])))
    return "\n".join(lines)


def print_inventory(records):
    print(format_inventory(records))
