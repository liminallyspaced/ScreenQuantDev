# ZERO_SHADER_LIGHT: hide_render on local Lights whose Cycles shader
# emission_estimate is proven 0 while RNA energy is not.
#
# Scene-agnostic object-DNA + light-tree lever. Classifier reads object
# type, Light.use_nodes, the Light Output Surface graph, Light.energy,
# hide_render, library, portal flag, and animation_data. Same code for
# interior / exterior / product / vehicle — the write fires iff a
# render-visible local noded light has proven-zero shader emission, never
# because of a file name or "interior" / chair counts.
#
# Complementary to ZERO_ENERGY_LIGHT. That lever is RNA energy == 0.
# Cycles 4.5 intern/cycles/blender/light.cpp sync_light:
#   const float3 strength = light_color * energy * exp2f(exposure);
#   light->set_strength(strength);
# No energy-0 early-out, and no node-tree read. RNA energy 10 + shader
# Strength 0 still becomes a Cycles Light with non-zero strength.
#
# intern/cycles/blender/shader.cpp sync_lights:
#   if (b_light.use_nodes() && b_light.node_tree()) {
#     add_nodes(...);            // Light Output Surface graph
#   } else {
#     emission->set_strength(1.0f);  // use_nodes off → shader is 1
#   }
# use_nodes False ignores any leftover tree (do not classify from it).
#
# intern/cycles/scene/shader.cpp output_estimate_emission:
#   Emission / Background / Principled: color (unlinked) * strength
#   (unlinked, or recursive if linked). Mix Fac unlinked interpolates;
#   Fac linked adds both sides. Unconnected Surface → zero_float3().
# intern/cycles/scene/light.cpp Light::has_contribution:
#   if (strength == zero_float3()) return false;   // RNA energy 0
#   ...
#   return !is_zero(effective_shader->emission_estimate);
# Disabled lights are skipped in the sampling distribution / light tree
# *after* they are Cycles objects (object.cpp sync_object: lights skip
# camera cull and always sync when show_lights).
#
# The leftover is membership: hide_render drops the object from
# DEG_OBJECT_ITER_FOR_RENDER_ENGINE so sync_light never runs. Portal
# lights (Light.cycles.is_portal) are skipped — they do not emit; hiding
# one would drop a world-MIS rectangle. Linked / animated / HERO skipped.
# RNA energy == 0 is owned by ZERO_ENERGY_LIGHT (do not double-count).
# GROUP / texture / Math / Light Path / Light Falloff / IES = unproven.
#
# NOT in default Auto Make it Fast until a measured pair exists.
# zero_shader_light_actions is not called from build_speed_plan.
# No bpy.ops. Importable without Blender (duck-typed scene + lights).

SPEED_KIND = "ZERO_SHADER_LIGHT"
PROP = "hide_render"
ZERO_EPS = 1e-4
OPAQUE_FAC = 1.0 - 1e-4

OUTPUT_TYPES = frozenset({"OUTPUT_LIGHT", "OUTPUT_MATERIAL"})
OUTPUT_IDNAMES = frozenset({
    "ShaderNodeOutputLight", "ShaderNodeOutputMaterial",
})
EMISSION_TYPES = frozenset({"EMISSION", "BACKGROUND", "BSDF_PRINCIPLED"})
EMISSION_IDNAMES = frozenset({
    "ShaderNodeEmission", "ShaderNodeBackground", "ShaderNodeBsdfPrincipled",
})
MIX_TYPES = frozenset({"MIX_SHADER"})
MIX_IDNAMES = frozenset({"ShaderNodeMixShader"})
ADD_TYPES = frozenset({"ADD_SHADER"})
ADD_IDNAMES = frozenset({"ShaderNodeAddShader"})
VALUE_TYPES = frozenset({"VALUE"})
VALUE_IDNAMES = frozenset({"ShaderNodeValue"})
REROUTE_TYPES = frozenset({"REROUTE"})
REROUTE_IDNAMES = frozenset({"NodeReroute"})
GROUP_TYPES = frozenset({"GROUP"})
GROUP_IDNAMES = frozenset({"ShaderNodeGroup", "ShaderNodeCustomGroup"})
RGB_TYPES = frozenset({"RGB"})
RGB_IDNAMES = frozenset({"ShaderNodeRGB"})


def classify_zero_shader_lights(scene):
    """Records for local render-visible noded Lights with proven-zero shader.

    Empty list if the engine is not CYCLES, or no qualifying lights.
    RNA energy == 0 is not classified here (ZERO_ENERGY_LIGHT).
    """
    if getattr(getattr(scene, "render", None), "engine", "CYCLES") != "CYCLES":
        return []
    records = []
    for obj in getattr(scene, "objects", ()) or ():
        rec = _classify_one(obj)
        if rec is not None:
            records.append(rec)
    return records


def apply_zero_shader_lights(scene, jrnl, records=None):
    """hide_render True through the journal. Re-prove shader emission == 0.

    Never writes Light.energy. Never unlinks nodes. Never touches portals.
    Returns the applied records (empty if every gate failed).
    """
    if records is None:
        records = classify_zero_shader_lights(scene)
    if not records:
        return []
    applied = []
    for rec in records:
        obj = _get_object(scene, rec.get("object"))
        if obj is None:
            continue
        if _classify_one(obj) is None:
            continue
        if getattr(obj, PROP, False):
            continue
        ok = jrnl.set_prop(obj, PROP, True)
        if ok:
            applied.append(rec)
    return applied


def inventory_counts(records):
    n = len(records or [])
    return {
        "ZERO_SHADER_LIGHT": n,
        "ENERGY_WRITES": 0,
        "NODE_UNLINKS": 0,
    }


# ------------------------------------------------------------------ gates


def _classify_one(obj):
    if getattr(obj, "type", "") != "LIGHT":
        return None
    if getattr(obj, PROP, False):
        return None
    if _protected(obj) or _is_linked(obj):
        return None
    data = getattr(obj, "data", None)
    if data is None:
        return None
    if _has_anim(obj) or _has_anim(data) or _has_anim(getattr(data, "node_tree", None)):
        return None
    if _is_portal(data):
        return None
    if not getattr(data, "use_nodes", False):
        return None
    tree = getattr(data, "node_tree", None)
    if tree is None:
        return None
    energy = getattr(data, "energy", None)
    if not isinstance(energy, (int, float)):
        return None
    if energy == 0:
        return None
    if _shader_emission_zero(tree) is not True:
        return None
    name = getattr(obj, "name", None)
    if not name:
        return None
    return {
        "class": SPEED_KIND,
        "object": name,
        "prop": PROP,
        "from": False,
        "to": True,
        "energy": float(energy),
        "light_type": getattr(data, "type", "") or "",
        "use_nodes": True,
    }


def _shader_emission_zero(tree):
    """True iff Light Output Surface is proven zero (Cycles estimate).

    False = live or unproven. Conservative: GROUP / texture / Math / unknown
    on the reachable path is unproven.
    """
    output = _light_output(tree)
    if output is None:
        return False
    surf = _sock(output, "Surface")
    return _link_emission_zero(surf) is True


def _light_output(tree):
    candidates = []
    for node in getattr(tree, "nodes", ()) or ():
        if getattr(node, "mute", False):
            continue
        ntype = _node_type(node)
        bl_id = getattr(node, "bl_idname", "") or ""
        if ntype in OUTPUT_TYPES or bl_id in OUTPUT_IDNAMES:
            candidates.append(node)
    if not candidates:
        return None
    active = [n for n in candidates if getattr(n, "is_active_output", True)]
    pool = active or candidates
    for node in pool:
        ntype = _node_type(node)
        bl_id = getattr(node, "bl_idname", "") or ""
        if ntype == "OUTPUT_LIGHT" or bl_id == "ShaderNodeOutputLight":
            return node
    return pool[0]


def _link_emission_zero(sock, seen=None):
    """True iff the linked closure is proven-zero. Unlinked Surface is 0."""
    if sock is None:
        return False
    if not getattr(sock, "is_linked", False):
        return True
    node, from_sock = _link_source(sock)
    if node is None:
        return False
    return _node_emission_zero(node, from_sock, seen)


def _node_emission_zero(node, from_sock, seen=None):
    if node is None:
        return False
    if seen is None:
        seen = set()
    marker = id(node)
    if marker in seen:
        return False
    seen = set(seen)
    seen.add(marker)
    if len(seen) > 16:
        return False
    if getattr(node, "mute", False):
        return False
    if _is_group(node):
        return False
    ntype = _node_type(node)
    bl_id = getattr(node, "bl_idname", "") or ""
    if ntype in REROUTE_TYPES or bl_id in REROUTE_IDNAMES:
        return _link_emission_zero(_first_input(node), seen)
    if ntype in EMISSION_TYPES or bl_id in EMISSION_IDNAMES:
        return _emission_node_zero(node)
    if ntype in MIX_TYPES or bl_id in MIX_IDNAMES:
        return _mix_emission_zero(node, seen)
    if ntype in ADD_TYPES or bl_id in ADD_IDNAMES:
        return _add_emission_zero(node, seen)
    return False


def _emission_node_zero(node):
    ntype = _node_type(node)
    bl_id = getattr(node, "bl_idname", "") or ""
    principled = ntype == "BSDF_PRINCIPLED" or bl_id == "ShaderNodeBsdfPrincipled"
    strength = _sock(node, "Emission Strength" if principled else "Strength")
    color = _sock(node, "Emission Color" if principled else "Color")
    if _proven_zero_scalar(strength):
        return True
    if _unlinked_black(color) and _strength_finite(strength):
        return True
    return False


def _mix_emission_zero(node, seen):
    fac = _sock(node, "Fac", "Factor")
    shader_a = _sock(node, "Shader", "Closure1")
    shader_b = _sock(node, "Shader.001", "Shader_001", "Closure2")
    if fac is None or getattr(fac, "is_linked", False):
        return _both_zero(shader_a, shader_b, seen)
    fac_val = getattr(fac, "default_value", None)
    if not isinstance(fac_val, (int, float)):
        return False
    if abs(float(fac_val)) <= ZERO_EPS:
        return _link_emission_zero(shader_a, seen) is True
    if float(fac_val) >= OPAQUE_FAC:
        return _link_emission_zero(shader_b, seen) is True
    return _both_zero(shader_a, shader_b, seen)


def _add_emission_zero(node, seen):
    shader_a = _sock(node, "Shader", "Closure1")
    shader_b = _sock(node, "Shader.001", "Shader_001", "Closure2")
    return _both_zero(shader_a, shader_b, seen)


def _both_zero(shader_a, shader_b, seen):
    a = _link_emission_zero(shader_a, seen)
    b = _link_emission_zero(shader_b, seen)
    return a is True and b is True


def _proven_zero_scalar(sock):
    """Unlinked ~0 or a Value node ~0. One hop. No Math / GROUP / texture."""
    if sock is None:
        return False
    if not getattr(sock, "is_linked", False):
        return _near_zero_float(getattr(sock, "default_value", None))
    node, from_sock = _link_source(sock)
    if node is None or _is_group(node):
        return False
    if getattr(node, "mute", False):
        return False
    ntype = _node_type(node)
    bl_id = getattr(node, "bl_idname", "") or ""
    if ntype in REROUTE_TYPES or bl_id in REROUTE_IDNAMES:
        return _proven_zero_scalar(_first_input(node))
    if ntype in VALUE_TYPES or bl_id in VALUE_IDNAMES:
        value = _constant_float(node, from_sock)
        return value is not None and _near_zero_float(value)
    return False


def _unlinked_black(sock):
    if sock is None or getattr(sock, "is_linked", False):
        return False
    return _near_zero_vector(getattr(sock, "default_value", None))


def _strength_finite(sock):
    """Strength is a number (linked or not). Used only with unlinked-black color."""
    if sock is None:
        return True
    if getattr(sock, "is_linked", False):
        return False
    return isinstance(getattr(sock, "default_value", None), (int, float))


def _constant_float(node, sock):
    if sock is not None:
        value = getattr(sock, "default_value", None)
        if isinstance(value, (int, float)):
            return float(value)
    out = _sock(node, "Value", collection="outputs")
    if out is not None:
        value = getattr(out, "default_value", None)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def _near_zero_float(value):
    return isinstance(value, (int, float)) and abs(float(value)) <= ZERO_EPS


def _near_zero_vector(value):
    if _near_zero_float(value):
        return True
    try:
        seq = list(value)
    except TypeError:
        return False
    if not seq:
        return False
    return all(_near_zero_float(item) for item in seq[:3])


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


def _first_input(node):
    socks = getattr(node, "inputs", None)
    if not socks:
        return None
    for sock in socks:
        return sock
    return None


def _link_source(sock):
    if sock is None or not getattr(sock, "is_linked", False):
        return None, None
    links = getattr(sock, "links", None) or ()
    for link in links:
        return getattr(link, "from_node", None), getattr(link, "from_socket", None)
    link = getattr(sock, "link", None)
    if link is not None:
        return getattr(link, "from_node", None), getattr(link, "from_socket", None)
    from_node = getattr(sock, "from_node", None)
    if from_node is not None:
        return from_node, getattr(sock, "from_socket", None)
    return None, None


def _node_type(node):
    return getattr(node, "type", "") or ""


def _is_group(node):
    ntype = _node_type(node)
    bl_id = getattr(node, "bl_idname", "") or ""
    return ntype in GROUP_TYPES or bl_id in GROUP_IDNAMES


def _is_portal(data):
    cycles = getattr(data, "cycles", None)
    return bool(getattr(cycles, "is_portal", False))


def _protected(obj):
    return getattr(getattr(obj, "scenequant", None), "override", "AUTO") != "AUTO"


def _is_linked(obj):
    if getattr(obj, "library", None) is not None:
        return True
    data = getattr(obj, "data", None)
    if getattr(data, "library", None) is not None:
        return True
    tree = getattr(data, "node_tree", None)
    return getattr(tree, "library", None) is not None


def _has_anim(id_block):
    if id_block is None:
        return False
    ad = getattr(id_block, "animation_data", None)
    if ad is None:
        return False
    if getattr(ad, "action", None) is not None:
        return True
    tracks = getattr(ad, "nla_tracks", None) or ()
    if any(getattr(track, "strips", None) for track in tracks):
        return True
    drivers = getattr(ad, "drivers", None) or ()
    if drivers:
        return True
    return False


def _get_object(scene, name):
    if not name:
        return None
    objects = getattr(scene, "objects", None)
    getter = getattr(objects, "get", None)
    if getter is not None:
        try:
            return getter(name)
        except Exception:
            pass
    for obj in objects or ():
        if getattr(obj, "name", None) == name:
            return obj
    return None
