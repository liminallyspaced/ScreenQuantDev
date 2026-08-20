# L5 PORTAL_MESH: inventory mesh/curve cards whose used-face material
# mixes Transparent BSDF with Fac linked to Geometry Backfacing.
# Graph pattern only. Not a Cycles RNA knob. Inventory + classify only
# — no convert, no light create.
#
# SPEED_KIND stays "PORTAL_MESH" for journal/plan stability. Each record
# has role:
#   MESH_EMIT_BACKFACE  Mix(Transparent, Emission) Fac=Backfacing.
#                       The card *emits*. Classroom dayLight_portal
#                       (hallWindow / windows) is this class: invisible
#                       from behind, lamp from the front.
#   WORLD_PORTAL_CARD   Transparent+Backfacing without proven Emission.
#                       Rare. Different class from emit cards.
#
# Never convert MESH_EMIT_BACKFACE to Cycles Light.cycles.is_portal
# (intern/cycles/scene/light.cpp). Portal lights do **not emit** — they
# are importance-sampling rectangles for the world environment.
# Replacing an emit card with is_portal=True drops the lamp and only
# helps if an HDRI/world is the real source. Classroom leftover Shade
# Shadow is transparent retrace through that card, not missing world MIS.
#
# Later convert (Manual, unbuilt) for MESH_EMIT_BACKFACE would be an
# AREA light matching strength×area + hide_render on the mesh, not a
# portal. World-portal cards are a different class and still unbuilt.
#
# Walks hide_render=False MESH/CURVE objects. Skip HERO/EXCLUDE, linked
# ids, GROUP trees, BSDF_GLASS / refraction / principled transmission,
# and objects that already are Cycles portal lights. Do NOT require the
# word "portal" in the name. Do not write integrator RNA. Do not create
# lights. Not in default Auto Make it Fast. Importable without Blender
# (duck-typed scene + node trees).

SPEED_KIND = "PORTAL_MESH"
ROLE_MESH_EMIT_BACKFACE = "MESH_EMIT_BACKFACE"
ROLE_WORLD_PORTAL_CARD = "WORLD_PORTAL_CARD"

GEOMETRY_OBJECT_TYPES = frozenset({"MESH", "CURVE"})
MIX_TYPES = frozenset({"MIX_SHADER"})
MIX_IDNAMES = frozenset({"ShaderNodeMixShader"})
TRANSPARENT_TYPES = frozenset({"BSDF_TRANSPARENT"})
TRANSPARENT_IDNAMES = frozenset({"ShaderNodeBsdfTransparent"})
EMISSION_TYPES = frozenset({"EMISSION"})
EMISSION_IDNAMES = frozenset({"ShaderNodeEmission"})
GEOMETRY_TYPES = frozenset({"NEW_GEOMETRY", "GEOMETRY"})
GEOMETRY_IDNAMES = frozenset({"ShaderNodeNewGeometry", "ShaderNodeGeometry"})
OUTPUT_TYPES = frozenset({"OUTPUT_MATERIAL"})
OUTPUT_IDNAMES = frozenset({"ShaderNodeOutputMaterial"})
GROUP_TYPES = frozenset({"GROUP"})
GROUP_IDNAMES = frozenset({"ShaderNodeGroup"})
GLASS_TYPES = frozenset({"BSDF_GLASS", "BSDF_REFRACTION"})
GLASS_IDNAMES = frozenset({
    "ShaderNodeBsdfGlass", "ShaderNodeBsdfRefraction",
})
BACKFACING_NAMES = frozenset({
    "Backfacing", "BACKFACING", "Is Backfacing",
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


def _used_face_materials(obj, mesh):
    """Materials that actually sit on used faces (or all slots if no polys)."""
    used = _used_indices(mesh)
    out = []
    seen = set()
    slots = list(_iter_slot_materials(obj, mesh))
    if not slots:
        return out
    if not used:
        # CURVE / empty mesh: treat every filled slot as used-face.
        for _index, mat in slots:
            if mat is None:
                continue
            ident = id(mat)
            if ident in seen:
                continue
            seen.add(ident)
            out.append(mat)
        return out
    for index, mat in slots:
        if mat is None or index not in used:
            continue
        ident = id(mat)
        if ident in seen:
            continue
        seen.add(ident)
        out.append(mat)
    return out


def _node_type(node):
    return getattr(node, "type", "") or ""


def _is_type(node, types, idnames):
    if node is None:
        return False
    if _node_type(node) in types:
        return True
    return getattr(node, "bl_idname", "") in idnames


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


def _link_source(sock):
    if sock is None or not getattr(sock, "is_linked", False):
        return None, None
    for link in _iter_links(sock):
        return getattr(link, "from_node", None), getattr(link, "from_socket", None)
    return None, None


def _socket_name(sock):
    if sock is None:
        return ""
    return getattr(sock, "identifier", None) or getattr(sock, "name", "") or ""


def _is_group_node(node):
    return _is_type(node, GROUP_TYPES, GROUP_IDNAMES)


def _tree_has_group(tree):
    for node in getattr(tree, "nodes", ()) or ():
        if _is_group_node(node):
            return True
    return False


def _principled_transmits(node):
    sock = _sock(node, "Transmission Weight", "Transmission")
    if sock is None:
        return False
    if getattr(sock, "is_linked", False):
        return True
    value = getattr(sock, "default_value", 0.0)
    return isinstance(value, (int, float)) and value > 0.2


def _tree_is_glass(tree):
    for node in getattr(tree, "nodes", ()) or ():
        if _is_type(node, GLASS_TYPES, GLASS_IDNAMES):
            return True
        if _node_type(node) == "BSDF_PRINCIPLED" and _principled_transmits(node):
            return True
    return False


def _find_output_nodes(tree):
    found = []
    for node in getattr(tree, "nodes", ()) or ():
        if _is_type(node, OUTPUT_TYPES, OUTPUT_IDNAMES):
            found.append(node)
    return found


def _mix_shader_inputs(node):
    """Return (fac_socket, [shader_socket, ...]) in node input order.

    Mix Shader is (1-Fac)*Shader + Fac*Shader_001.
    """
    fac = None
    shaders = []
    for sock in _iter_socks(node, "inputs"):
        ident = getattr(sock, "identifier", "") or ""
        name = getattr(sock, "name", "") or ""
        if ident == "Fac" or name == "Fac" or ident == "Factor" or name == "Factor":
            fac = sock
            continue
        shaders.append(sock)
    if fac is None:
        fac = _sock(node, "Fac", "Factor")
    return fac, shaders


def _shader_is_only_transparent(sock, seen=None):
    if sock is None or not getattr(sock, "is_linked", False):
        return False
    from_node, _from_sock = _link_source(sock)
    return _node_is_only_transparent(from_node, seen)


def _node_is_only_transparent(node, seen=None):
    if node is None:
        return False
    if seen is None:
        seen = set()
    ident = id(node)
    if ident in seen:
        return True
    seen.add(ident)
    if _is_group_node(node):
        return False
    if _is_type(node, TRANSPARENT_TYPES, TRANSPARENT_IDNAMES):
        return True
    if _is_type(node, MIX_TYPES, MIX_IDNAMES):
        _fac, shaders = _mix_shader_inputs(node)
        linked = False
        for sock in shaders:
            if not getattr(sock, "is_linked", False):
                continue
            linked = True
            if not _shader_is_only_transparent(sock, seen):
                return False
        return linked
    if _node_type(node) == "ADD_SHADER":
        linked = False
        for sock in _iter_socks(node, "inputs"):
            if not getattr(sock, "is_linked", False):
                continue
            linked = True
            if not _shader_is_only_transparent(sock, seen):
                return False
        return linked
    return False


def _shader_is_only_emission(sock, seen=None):
    if sock is None or not getattr(sock, "is_linked", False):
        return False
    from_node, _from_sock = _link_source(sock)
    return _node_is_only_emission(from_node, seen)


def _node_is_only_emission(node, seen=None):
    if node is None:
        return False
    if seen is None:
        seen = set()
    ident = id(node)
    if ident in seen:
        return True
    seen.add(ident)
    if _is_group_node(node):
        return False
    if _is_type(node, EMISSION_TYPES, EMISSION_IDNAMES):
        return True
    if _is_type(node, MIX_TYPES, MIX_IDNAMES):
        _fac, shaders = _mix_shader_inputs(node)
        linked = False
        for sock in shaders:
            if not getattr(sock, "is_linked", False):
                continue
            linked = True
            if not _shader_is_only_emission(sock, seen):
                return False
        return linked
    if _node_type(node) == "ADD_SHADER":
        linked = False
        for sock in _iter_socks(node, "inputs"):
            if not getattr(sock, "is_linked", False):
                continue
            linked = True
            if not _shader_is_only_emission(sock, seen):
                return False
        return linked
    return False


def _fac_is_backfacing(sock):
    """True iff Fac is linked to Geometry / NEW_GEOMETRY Backfacing.

    Incoming (or any other Geometry socket) is a different trick — not enough.
    """
    if sock is None or not getattr(sock, "is_linked", False):
        return False
    from_node, from_sock = _link_source(sock)
    if not _is_type(from_node, GEOMETRY_TYPES, GEOMETRY_IDNAMES):
        return False
    name = _socket_name(from_sock)
    if name in BACKFACING_NAMES:
        return True
    # Defensive: some DNA dumps only expose the display name.
    if (name or "").replace(" ", "").lower() == "backfacing":
        return True
    return False


def _reachable_mix_shaders(surface_sock):
    """Yield Mix Shader nodes that feed Surface (direct or via Mix/Add chain)."""
    seen = set()
    stack = [surface_sock]
    while stack:
        current = stack.pop()
        if current is None or not getattr(current, "is_linked", False):
            continue
        for link in _iter_links(current):
            node = getattr(link, "from_node", None)
            if node is None:
                continue
            ident = id(node)
            if ident in seen:
                continue
            seen.add(ident)
            if _is_type(node, MIX_TYPES, MIX_IDNAMES):
                yield node
                _fac, shaders = _mix_shader_inputs(node)
                for sock in shaders:
                    stack.append(sock)
                continue
            if _node_type(node) == "ADD_SHADER":
                for sock in _iter_socks(node, "inputs"):
                    stack.append(sock)
                continue


def _material_portal_role(material):
    """Return (role, reason) or ("", "").

    MESH_EMIT_BACKFACE: Mix(Transparent, Emission) Fac=Backfacing.
    WORLD_PORTAL_CARD: Mix with Transparent + Backfacing Fac and no
    proven Emission on either shader input. Never treat the latter as
    the former. Never convert MESH_EMIT_BACKFACE to cycles.is_portal.
    """
    if material is None:
        return "", ""
    if getattr(material, "use_nodes", True) is False:
        return "", ""
    tree = getattr(material, "node_tree", None)
    if tree is None:
        return "", ""
    if _tree_has_group(tree):
        return "", ""
    if _tree_is_glass(tree):
        return "", ""
    for out in _find_output_nodes(tree):
        surface = _sock(out, "Surface")
        for mix in _reachable_mix_shaders(surface):
            fac, shaders = _mix_shader_inputs(mix)
            if len(shaders) < 2:
                continue
            if not _fac_is_backfacing(fac):
                continue
            a_trans = _shader_is_only_transparent(shaders[0])
            b_trans = _shader_is_only_transparent(shaders[1])
            a_emit = _shader_is_only_emission(shaders[0])
            b_emit = _shader_is_only_emission(shaders[1])
            if (a_trans and b_emit) or (a_emit and b_trans):
                return ROLE_MESH_EMIT_BACKFACE, (
                    "Mix(Transparent, Emission) Fac=Geometry.Backfacing"
                )
            if (a_trans or b_trans) and not a_emit and not b_emit:
                return ROLE_WORLD_PORTAL_CARD, (
                    "Mix(Transparent) Fac=Geometry.Backfacing; "
                    "no proven Emission"
                )
    return "", ""


def _material_is_portal_pattern(material):
    """Return (True, reason) if the material matches either PORTAL_MESH role."""
    role, reason = _material_portal_role(material)
    return bool(role), reason


def _is_cycles_portal_light(obj):
    """True if the object is already a Cycles portal light (type LIGHT)."""
    otype = getattr(obj, "type", "") or ""
    if otype not in ("LIGHT", "LAMP"):
        return False
    data = getattr(obj, "data", None)
    cycles = getattr(data, "cycles", None) if data is not None else None
    if cycles is not None and getattr(cycles, "is_portal", False):
        return True
    if getattr(obj, "cycles", None) is not None:
        if getattr(obj.cycles, "is_portal", False):
            return True
    return False


def classify_portal_meshes(scene):
    """Return one inventory record per PORTAL_MESH candidate.

    Each record has role MESH_EMIT_BACKFACE or WORLD_PORTAL_CARD.
    Classroom dayLight_portal is MESH_EMIT_BACKFACE — never convert
    that role to cycles.is_portal (drops emission). Skip HERO/EXCLUDE,
    linked object/mesh/material, GROUP trees, glass / refraction /
    principled transmission, and Cycles portal lights. Name is not how
    we detect.
    """
    records = []
    seen_keys = set()
    for obj in getattr(scene, "objects", ()) or ():
        if getattr(obj, "type", "") not in GEOMETRY_OBJECT_TYPES:
            continue
        if getattr(obj, "hide_render", False):
            continue
        if _protected(obj):
            continue
        if _is_linked_id(obj):
            continue
        if _is_cycles_portal_light(obj):
            continue
        mesh = getattr(obj, "data", None)
        if mesh is None:
            continue
        if _is_linked_id(mesh):
            continue
        mats = _used_face_materials(obj, mesh)
        if not mats:
            continue
        for mat in mats:
            if _is_linked_id(mat):
                continue
            role, reason = _material_portal_role(mat)
            if not role:
                continue
            key = (getattr(obj, "name", "") or "",
                   getattr(mesh, "name", "") or "",
                   getattr(mat, "name", "") or "")
            if key in seen_keys:
                continue
            seen_keys.add(key)
            records.append({
                "object": getattr(obj, "name", "") or "",
                "mesh": getattr(mesh, "name", "") or "",
                "material": getattr(mat, "name", "") or "",
                "reason": reason,
                "role": role,
            })
    return records


def inventory_counts(records):
    recs = list(records or ())
    objects = set()
    meshes = set()
    materials = set()
    emit = 0
    world = 0
    for rec in recs:
        if rec.get("object"):
            objects.add(rec["object"])
        if rec.get("mesh"):
            meshes.add(rec["mesh"])
        if rec.get("material"):
            materials.add(rec["material"])
        role = rec.get("role") or ""
        if role == ROLE_MESH_EMIT_BACKFACE:
            emit += 1
        elif role == ROLE_WORLD_PORTAL_CARD:
            world += 1
    return {
        "PORTAL_MESH": len(recs),
        "UNIQUE_OBJECTS": len(objects),
        "UNIQUE_MESHES": len(meshes),
        "UNIQUE_MATERIALS": len(materials),
        "MESH_EMIT_BACKFACE": emit,
        "WORLD_PORTAL_CARD": world,
    }


def format_inventory(records):
    counts = inventory_counts(records)
    recs = list(records or ())
    lines = [
        "PORTAL_MESH inventory (inventory only; Auto off; no convert; "
        "no time claim; never is_portal for MESH_EMIT_BACKFACE)",
        "  PORTAL_MESH=%d  UNIQUE_OBJECTS=%d  UNIQUE_MESHES=%d  "
        "UNIQUE_MATERIALS=%d"
        % (counts["PORTAL_MESH"], counts["UNIQUE_OBJECTS"],
           counts["UNIQUE_MESHES"], counts["UNIQUE_MATERIALS"]),
        "  MESH_EMIT_BACKFACE=%d  WORLD_PORTAL_CARD=%d"
        % (counts["MESH_EMIT_BACKFACE"], counts["WORLD_PORTAL_CARD"]),
    ]
    for rec in recs:
        lines.append(
            "  object=%s  mesh=%s  material=%s  role=%s  reason=%s"
            % (rec.get("object", ""), rec.get("mesh", ""),
               rec.get("material", ""), rec.get("role", ""),
               rec.get("reason", "")))
    return "\n".join(lines)


def print_inventory(records):
    print(format_inventory(records))
