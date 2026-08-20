# L5 PORTAL_MESH: inventory mesh/curve cards whose used-face material
# mixes Transparent BSDF with Fac linked to Geometry Backfacing.
# Graph pattern + optional Manual BACKFACE_EMIT_OPAQUE apply.
# Not a Cycles integrator knob. Never is_portal. Never AREA convert.
#
# SPEED_KIND stays "PORTAL_MESH" for journal/plan stability. Each record
# has role:
#   MESH_EMIT_BACKFACE  Mix(Transparent, Emission) Fac=Backfacing.
#                       The card *emits*. Classroom dayLight_portal
#                       (hallWindow / windows) is this class: invisible
#                       from behind, lamp from the front.
#   WORLD_PORTAL_CARD   Transparent+Backfacing without proven Emission.
#                       Rare. Different class from emit cards. Not this apply.
#
# Never convert MESH_EMIT_BACKFACE to Cycles Light.cycles.is_portal
# (intern/cycles/scene/light.cpp). Portal lights do **not emit** — they
# are importance-sampling rectangles for the world environment.
# Replacing an emit card with is_portal=True drops the lamp and only
# helps if an HDRI/world is the real source. Classroom leftover Shade
# Shadow is transparent retrace through that card, not missing world MIS.
#
# Transparent still sitting in the Mix latches SD_HAS_TRANSPARENT_SHADOW
# on the whole shader (intern/cycles/scene/shader.cpp / kernel shadow
# retrace). BACKFACE_EMIT_OPAQUE unlinks that Transparent mix input
# (NODE_UNLINK) so the Surface is Emission-only. Replacement for the
# missing backface-is-invisible behavior is material use_backface_culling
# (hasattr-gated; Blender 4.1+ Cycles). That cull is RNA, but it is the
# pair for the graph write, not a new integrator knob. Never write
# integrator RNA.
#
# Quality: outside the room the card disappears (cull) instead of being
# transparent. Window rebate / two-way views can change. Auto off until
# HDR-FLIP on Classroom and loft. Manual-first. Apply is NOT called from
# Auto / build_speed_plan.
#
# Later AREA convert (Manual, unbuilt) is a different lever: AREA light
# matching strength×area + hide_render on the mesh, not a portal.
# World-portal cards are a different class and still unbuilt.
#
# Walks hide_render=False MESH/CURVE objects. Skip HERO/EXCLUDE, linked
# ids, GROUP trees, BSDF_GLASS / refraction / principled transmission,
# and objects that already are Cycles portal lights. Do NOT require the
# word "portal" in the name. Do not write integrator RNA. Do not create
# lights. Not in default Auto Make it Fast. Importable without Blender
# (duck-typed scene + node trees).

SPEED_KIND = "PORTAL_MESH"
SPEED_KIND_OPAQUE = "BACKFACE_EMIT_OPAQUE"
ROLE_MESH_EMIT_BACKFACE = "MESH_EMIT_BACKFACE"
ROLE_WORLD_PORTAL_CARD = "WORLD_PORTAL_CARD"
ACTION_KIND = "NODE_UNLINK"
CULL_ATTR = "use_backface_culling"

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



def _unlink_target_for_emit_backface(material):
    """Return (mix, trans_sock, from_node, from_sock) for NODE_UNLINK.

    The Transparent shader input of a Mix(Transparent, Emission)
    Fac=Backfacing graph. Empty tuple of Nones if this is not that
    pattern or the Transparent input is not linked.
    """
    none = (None, None, None, None)
    if material is None:
        return none
    if getattr(material, "use_nodes", True) is False:
        return none
    tree = getattr(material, "node_tree", None)
    if tree is None:
        return none
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
            trans_sock = None
            if a_trans and b_emit:
                trans_sock = shaders[0]
            elif a_emit and b_trans:
                trans_sock = shaders[1]
            if trans_sock is None or not getattr(trans_sock, "is_linked", False):
                continue
            from_node, from_sock = _link_source(trans_sock)
            return mix, trans_sock, from_node, from_sock
    return none


def _opaque_fields(material, role):
    """opaque_ok plus NODE_UNLINK payload fields for one material.

    True only for MESH_EMIT_BACKFACE when (a) Transparent is a mix
    input we can NODE_UNLINK and (b) the material has
    use_backface_culling. Missing cull attr → opaque_ok False with a
    note that cull is required (still inventory the candidate).
    WORLD_PORTAL_CARD is never this apply.
    """
    fields = {
        "opaque_ok": False,
        "opaque_note": "",
        "node": "",
        "socket": "",
        "from_node": "",
        "from_socket": "",
    }
    if role != ROLE_MESH_EMIT_BACKFACE:
        return fields
    mix, trans_sock, from_node, from_sock = _unlink_target_for_emit_backface(
        material)
    can_unlink = (
        mix is not None and trans_sock is not None
        and getattr(trans_sock, "is_linked", False)
    )
    if mix is not None:
        fields["node"] = getattr(mix, "name", "") or ""
    fields["socket"] = _socket_name(trans_sock)
    fields["from_node"] = (
        getattr(from_node, "name", "") or "") if from_node else ""
    fields["from_socket"] = _socket_name(from_sock)
    if not can_unlink:
        fields["opaque_note"] = "Transparent mix input not unlinkable"
        return fields
    if not hasattr(material, CULL_ATTR):
        fields["opaque_note"] = (
            "cull required; use_backface_culling missing"
        )
        return fields
    fields["opaque_ok"] = True
    return fields


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
            rec = {
                "object": getattr(obj, "name", "") or "",
                "mesh": getattr(mesh, "name", "") or "",
                "material": getattr(mat, "name", "") or "",
                "reason": reason,
                "role": role,
            }
            rec.update(_opaque_fields(mat, role))
            records.append(rec)
    return records


def inventory_counts(records):
    recs = list(records or ())
    objects = set()
    meshes = set()
    materials = set()
    emit = 0
    world = 0
    opaque = 0
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
        if rec.get("opaque_ok"):
            opaque += 1
    return {
        "PORTAL_MESH": len(recs),
        "UNIQUE_OBJECTS": len(objects),
        "UNIQUE_MESHES": len(meshes),
        "UNIQUE_MATERIALS": len(materials),
        "MESH_EMIT_BACKFACE": emit,
        "WORLD_PORTAL_CARD": world,
        "OPAQUE_OK": opaque,
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
        "  MESH_EMIT_BACKFACE=%d  WORLD_PORTAL_CARD=%d  OPAQUE_OK=%d"
        % (counts["MESH_EMIT_BACKFACE"], counts["WORLD_PORTAL_CARD"],
           counts["OPAQUE_OK"]),
    ]
    for rec in recs:
        note = rec.get("opaque_note") or ""
        note_s = ("  note=%s" % note) if note else ""
        lines.append(
            "  object=%s  mesh=%s  material=%s  role=%s  "
            "opaque_ok=%s  reason=%s%s"
            % (rec.get("object", ""), rec.get("mesh", ""),
               rec.get("material", ""), rec.get("role", ""),
               rec.get("opaque_ok", False), rec.get("reason", ""),
               note_s))
    return "\n".join(lines)


def print_inventory(records):
    print(format_inventory(records))


def _find_material(scene, name):
    if not name:
        return None
    for obj in getattr(scene, "objects", ()) or ():
        mesh = getattr(obj, "data", None)
        mats = _materials(mesh) if mesh is not None else None
        if mats is not None:
            try:
                items = list(mats)
            except TypeError:
                items = []
            for item in items:
                mat = _slot_material(item)
                if mat is not None and getattr(mat, "name", None) == name:
                    return mat
        for slot in getattr(obj, "material_slots", ()) or ():
            mat = _slot_material(slot)
            if mat is not None and getattr(mat, "name", None) == name:
                return mat
    return None


def _find_node(tree, name):
    if tree is None or not name:
        return None
    nodes = getattr(tree, "nodes", None)
    getter = getattr(nodes, "get", None)
    if getter is not None:
        try:
            node = getter(name)
            if node is not None:
                return node
        except Exception:
            pass
    for node in nodes or ():
        if getattr(node, "name", None) == name:
            return node
    return None


def _find_socket(socks, name):
    if socks is None or not name:
        return None
    getter = getattr(socks, "get", None)
    if getter is not None:
        sock = getter(name)
        if sock is not None:
            return sock
    for sock in socks or ():
        if getattr(sock, "identifier", None) == name or getattr(sock, "name", None) == name:
            return sock
    return None


def _unlink_socket(tree, sock):
    """Remove every link into sock. Returns [(from_node, from_socket), ...]."""
    removed = []
    links = list(_iter_links(sock))
    tree_links = getattr(tree, "links", None)
    remover = getattr(tree_links, "remove", None)
    for link in links:
        from_node = getattr(link, "from_node", None)
        from_sock = getattr(link, "from_socket", None)
        if remover is not None:
            try:
                remover(link)
            except Exception:
                continue
        else:
            for owner in (sock, from_sock):
                if owner is None:
                    continue
                bucket = getattr(owner, "links", None)
                if bucket is not None:
                    try:
                        bucket.remove(link)
                    except (ValueError, AttributeError):
                        pass
                try:
                    owner.is_linked = bool(bucket)
                except Exception:
                    pass
            if isinstance(tree_links, list):
                try:
                    tree_links.remove(link)
                except ValueError:
                    pass
        removed.append((from_node, from_sock))
    try:
        sock.is_linked = False
    except Exception:
        pass
    return removed


def _journal_cull(jrnl, mat, tag):
    """Set use_backface_culling True and journal the RNA write.

    Same shape as other material RNA (journal.set_prop). Duck journals
    without set_prop still setattr and append a prop entry so revert
    can restore the flag.
    """
    if not hasattr(mat, CULL_ATTR):
        return False
    if getattr(mat, CULL_ATTR, True) is not False:
        return False
    setter = getattr(jrnl, "set_prop", None) if jrnl is not None else None
    if setter is not None:
        return bool(setter(mat, CULL_ATTR, True, tag))
    old = getattr(mat, CULL_ATTR)
    try:
        setattr(mat, CULL_ATTR, True)
    except (AttributeError, TypeError):
        return False
    if jrnl is not None and hasattr(jrnl, "entries"):
        jrnl.entries.append({
            "t": "prop",
            "kind": "Material",
            "name": getattr(mat, "name", "") or "",
            "path": CULL_ATTR,
            "old": old,
            "new": True,
            "tag": tag,
        })
    return True


def apply_backface_emit_opaque(scene, jrnl, records=None, tag="speed"):
    """Unlink Transparent on MESH_EMIT_BACKFACE + journal backface cull.

    Only opaque_ok records. NODE_UNLINK the Transparent mix input so
    Cycles drops SD_HAS_TRANSPARENT_SHADOW; if cull is currently False,
    set use_backface_culling True and journal that RNA. Not called by
    Make it Fast Auto. Never writes integrator RNA. Never is_portal.
    Never AREA convert.
    """
    if records is None:
        records = classify_portal_meshes(scene)
    applied = []
    for rec in records or ():
        if rec.get("role") != ROLE_MESH_EMIT_BACKFACE:
            continue
        if not rec.get("opaque_ok"):
            continue
        mat = _find_material(scene, rec.get("material"))
        if mat is None or _is_linked_id(mat):
            continue
        if not hasattr(mat, CULL_ATTR):
            continue
        tree = getattr(mat, "node_tree", None)
        if tree is None:
            continue
        mix, trans_sock, _from_node, _from_sock = (
            _unlink_target_for_emit_backface(mat))
        if trans_sock is None or not getattr(trans_sock, "is_linked", False):
            continue
        removed = _unlink_socket(tree, trans_sock)
        payloads = []
        for from_node, from_sock in removed:
            payload = {
                "material": rec.get("material"),
                "node": getattr(mix, "name", "") if mix else rec.get("node", ""),
                "socket": _socket_name(trans_sock) or rec.get("socket", ""),
                "from_node": (
                    getattr(from_node, "name", "") if from_node
                    else rec.get("from_node", "")),
                "from_socket": (
                    _socket_name(from_sock) or rec.get("from_socket", "")),
            }
            if jrnl is not None:
                recorder = getattr(jrnl, "record_action", None)
                if recorder is not None:
                    recorder(ACTION_KIND, payload, tag)
            payloads.append(payload)
        _journal_cull(jrnl, mat, tag)
        applied.extend(payloads)
    return applied


def restore_node_unlink_on_material(mat, payload):
    """Relink one NODE_UNLINK payload onto an already-resolved material."""
    if mat is None or not isinstance(payload, dict):
        return False
    tree = getattr(mat, "node_tree", None)
    if tree is None:
        return False
    to_node = _find_node(tree, payload.get("node"))
    from_node = _find_node(tree, payload.get("from_node"))
    if to_node is None or from_node is None:
        return False
    to_sock = _find_socket(getattr(to_node, "inputs", None), payload.get("socket"))
    from_sock = _find_socket(getattr(from_node, "outputs", None),
                             payload.get("from_socket"))
    if from_sock is None:
        from_sock = _find_socket(getattr(from_node, "inputs", None),
                                 payload.get("from_socket"))
    if to_sock is None or from_sock is None:
        return False
    if getattr(to_sock, "is_linked", False):
        return True
    linker = getattr(getattr(tree, "links", None), "new", None)
    if linker is None:
        return False
    try:
        linker(from_sock, to_sock)
    except Exception:
        return False
    return bool(getattr(to_sock, "is_linked", False))


def _restore_cull_entry(scene, entry):
    mat = _find_material(scene, entry.get("name"))
    if mat is None or not hasattr(mat, CULL_ATTR):
        return False
    try:
        setattr(mat, CULL_ATTR, entry.get("old"))
    except (AttributeError, TypeError):
        return False
    return getattr(mat, CULL_ATTR) == entry.get("old")


def revert_backface_emit_opaque(scene, jrnl):
    """Restore NODE_UNLINK Mix links and journaled use_backface_culling.

    Newest-first so RNA cull is restored before the Mix relink when
    apply wrote unlink then cull. Returns restored entry count.
    """
    entries = list(getattr(jrnl, "entries", None) or ())
    consumed = set()
    count = 0
    for entry in reversed(entries):
        if not isinstance(entry, dict):
            continue
        if (entry.get("t") == "prop"
                and entry.get("path") == CULL_ATTR):
            if _restore_cull_entry(scene, entry):
                consumed.add(id(entry))
                count += 1
            continue
        if entry.get("kind") == ACTION_KIND:
            payload = entry.get("payload") or {}
            mat = _find_material(scene, payload.get("material"))
            if restore_node_unlink_on_material(mat, payload):
                consumed.add(id(entry))
                count += 1
    if hasattr(jrnl, "entries"):
        jrnl.entries = [e for e in entries if id(e) not in consumed]
    return count
