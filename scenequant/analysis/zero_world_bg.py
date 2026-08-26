# ZERO_WORLD_BG: sampling_method NONE when World Surface is proven-zero
# emission *and* a spatial texture still feeds Color (so Cycles keeps MIS).
#
# Scene-agnostic world-DNA lever. Classifier reads World.use_nodes, the
# World Output Surface graph, world.cycles.sampling_method, library,
# animation_data, Volume socket, and portal lights. Same code for any
# .blend — the write fires iff a noded world is proven-zero *and* still
# spatially varying, never because of a file name.
#
# Complementary to WORLD_MIS_NONE. That Auto lever owns *solid* worlds
# (use_nodes False, or a tree with no TEX_ENVIRONMENT / TEX_SKY / …).
# intern/cycles/scene/light.cpp LightManager::test_enabled_lights
# (blender-v4.5-release and blender-v5.1-release):
#   Shader *shader = scene->background->get_shader(scene);
#   const bool disable_mis = !(has_portal || shader->has_surface_spatial_varying);
# Solid (no spatial-varying) already auto-disables MIS. WORLD_MIS_NONE
# is therefore a no-op on the tax this lever targets.
#
# intern/cycles/scene/svm.cpp SVMCompiler::generate_node:
#   if (current_type == SHADER_TYPE_SURFACE && node->has_spatial_varying())
#       current_shader->has_surface_spatial_varying = true;
# Environment / Sky / Image textures on the compiled surface graph latch
# that flag even when Background Strength is 0.
#
# intern/cycles/scene/shader.cpp output_estimate_emission:
#   Background / Emission: color (unlinked) * strength (unlinked, or
#   recursive if linked). Color *linked* only marks is_constant=false;
#   Strength 0 still yields zero_float3(). estimate_emission then sets
#   emission_sampling = NONE. test_enabled_lights does *not* consult
#   emission_estimate — spatial-varying + use_mis keeps the background
#   light enabled.
#
# intern/cycles/blender/light.cpp sync_background_light:
#   4.5: if (sample_as_light || world_use_portal) create LIGHT_BACKGROUND
#   5.1: always create; light->set_use_mis(sample_as_light)
#   sampling_method != NONE → sample_as_light true.
# intern/cycles/scene/light.cpp device_update_background then
# shade_background_pixels (default 1024×512, or the env-tex resolution)
# to build the importance CDF. Strength 0 + connected HDRI still pays
# that map.
#
# The leftover is the RNA MIS enable: sampling_method NONE makes
# sample_as_light false. With no portals, 4.5 never creates the
# background light; 5.1 creates it with use_mis false and
# test_enabled_lights sets is_enabled false (no portal, no
# use_mis×spatial). device_update_background early-returns. Camera
# rays still evaluate the (black) world shader; we do not unlink.
#
# WORLD_MIS_NONE already covers solid. This lever requires a spatial
# texture *on the reachable Color path* so we do not write NONE for a
# disconnected env tex that simplify would drop anyway.
# Volume linked = skip (world volume is a different bill).
# Portal lights = skip (has_portal forces background_enabled and still
# builds the map). Linked / animated / HERO skipped. GROUP on Color =
# unproven.
#
# NOT in default Auto Make it Fast until a measured pair exists.
# zero_world_bg_actions is not called from build_speed_plan.
# No bpy.ops. Importable without Blender (duck-typed scene + world).

SPEED_KIND = "ZERO_WORLD_BG"
PROP = "sampling_method"
PROP_PATH = "cycles.sampling_method"
TARGET = "NONE"
ZERO_EPS = 1e-4
OPAQUE_FAC = 1.0 - 1e-4

OUTPUT_TYPES = frozenset({"OUTPUT_WORLD", "OUTPUT_MATERIAL", "OUTPUT_LIGHT"})
OUTPUT_IDNAMES = frozenset({
    "ShaderNodeOutputWorld", "ShaderNodeOutputMaterial",
    "ShaderNodeOutputLight",
})
EMISSION_TYPES = frozenset({"BACKGROUND", "EMISSION", "BSDF_PRINCIPLED"})
EMISSION_IDNAMES = frozenset({
    "ShaderNodeBackground", "ShaderNodeEmission", "ShaderNodeBsdfPrincipled",
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
MIX_COLOR_TYPES = frozenset({"MIX_RGB", "MIX"})
MIX_COLOR_IDNAMES = frozenset({"ShaderNodeMixRGB", "ShaderNodeMix"})
COLOR_PASSTHRU_TYPES = frozenset({
    "INVERT", "GAMMA", "HUE_SAT", "BRIGHTCONTRAST", "CURVE_RGB", "RGBTOBW",
})
COLOR_PASSTHRU_IDNAMES = frozenset({
    "ShaderNodeInvert", "ShaderNodeGamma", "ShaderNodeHueSaturation",
    "ShaderNodeBrightContrast", "ShaderNodeRGBCurve", "ShaderNodeRGBToBW",
})
SPATIAL_TYPES = frozenset({
    "TEX_ENVIRONMENT", "TEX_SKY", "TEX_IMAGE", "TEX_NOISE", "TEX_WAVE",
    "TEX_MUSGRAVE", "TEX_VORONOI", "TEX_MAGIC", "TEX_GRADIENT",
    "TEX_CHECKER", "TEX_BRICK", "TEX_WHITE_NOISE", "TEX_GABOR",
    "TEX_POINTDENSITY", "TEX_IES",
})
SPATIAL_IDNAMES = frozenset({
    "ShaderNodeTexEnvironment", "ShaderNodeTexSky", "ShaderNodeTexImage",
    "ShaderNodeTexNoise", "ShaderNodeTexWave", "ShaderNodeTexMusgrave",
    "ShaderNodeTexVoronoi", "ShaderNodeTexMagic", "ShaderNodeTexGradient",
    "ShaderNodeTexChecker", "ShaderNodeTexBrick", "ShaderNodeTexWhiteNoise",
    "ShaderNodeTexGabor", "ShaderNodeTexPointDensity", "ShaderNodeTexIES",
})


def classify_zero_world_bg(scene):
    """Records when a noded world is proven-zero *and* still spatially varying.

    Empty list if the engine is not CYCLES, sampling is already NONE,
    WORLD_MIS_NONE would own a solid tree, or any conservative gate fails.
    """
    rec = _classify(scene)
    return [rec] if rec is not None else []


def apply_zero_world_bg(scene, jrnl, records=None):
    """sampling_method NONE through the journal. Re-prove the gap.

    Never unlinks nodes. Never writes world color / Strength. Never
    touches portals. Returns the applied records (empty if the gate
    failed or set_prop did not stick).
    """
    if records is None:
        records = classify_zero_world_bg(scene)
    if not records:
        return []
    if _classify(scene) is None:
        return []
    world = getattr(scene, "world", None)
    if world is None:
        return []
    wcycles = getattr(world, "cycles", None)
    if wcycles is None or not hasattr(wcycles, PROP):
        return []
    if getattr(wcycles, PROP, None) == TARGET:
        return []
    ok = jrnl.set_prop(world, PROP_PATH, TARGET)
    if not ok:
        return []
    return list(records)


def inventory_counts(records):
    n = len(records or [])
    return {
        "ZERO_WORLD_BG": n,
        "NODE_UNLINKS": 0,
        "WORLD_MIS_NONE": 0,
    }


# ------------------------------------------------------------------ gates


def _classify(scene):
    if getattr(getattr(scene, "render", None), "engine", "CYCLES") != "CYCLES":
        return None
    world = getattr(scene, "world", None)
    if world is None:
        return None
    if _protected(world) or _is_linked(world):
        return None
    if _has_anim(world) or _has_anim(getattr(world, "node_tree", None)):
        return None
    wcycles = getattr(world, "cycles", None)
    if wcycles is None or not hasattr(wcycles, PROP):
        return None
    current = getattr(wcycles, PROP, None)
    if current == TARGET or current is None:
        return None
    if not getattr(world, "use_nodes", False):
        return None
    tree = getattr(world, "node_tree", None)
    if tree is None:
        return None
    if _volume_linked(tree):
        return None
    if _scene_has_portal(scene):
        return None
    if _shader_emission_zero(tree) is not True:
        return None
    spatial = _color_path_spatial(tree)
    if spatial is not True:
        return None
    return {
        "class": SPEED_KIND,
        "prop": PROP,
        "from": current,
        "to": TARGET,
        "use_nodes": True,
        "spatial": True,
    }


def _shader_emission_zero(tree):
    """True iff World Output Surface is proven zero (Cycles estimate)."""
    output = _world_output(tree)
    if output is None:
        return False
    surf = _sock(output, "Surface")
    return _link_emission_zero(surf) is True


def _color_path_spatial(tree):
    """True iff a spatial texture is reachable from Background Color.

    False = no spatial on the live Color path (WORLD_MIS_NONE / Cycles
    auto-disable already cover). None-equivalent is False here: GROUP /
    mute / unknown = unproven, so we do not fire.
    """
    output = _world_output(tree)
    if output is None:
        return False
    surf = _sock(output, "Surface")
    return _link_spatial(surf) is True


def _world_output(tree):
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
        if ntype == "OUTPUT_WORLD" or bl_id == "ShaderNodeOutputWorld":
            return node
    return pool[0]


def _volume_linked(tree):
    output = _world_output(tree)
    if output is None:
        return False
    vol = _sock(output, "Volume")
    return bool(vol is not None and getattr(vol, "is_linked", False))


def _link_emission_zero(sock, seen=None):
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


def _link_spatial(sock, seen=None):
    """True iff the linked closure's Color path has a spatial texture."""
    if sock is None or not getattr(sock, "is_linked", False):
        return False
    node, from_sock = _link_source(sock)
    if node is None:
        return False
    return _node_spatial(node, from_sock, seen) is True


def _node_spatial(node, from_sock, seen=None):
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
    if ntype in SPATIAL_TYPES or bl_id in SPATIAL_IDNAMES:
        return True
    if ntype in REROUTE_TYPES or bl_id in REROUTE_IDNAMES:
        return _link_spatial(_first_input(node), seen)
    if ntype in EMISSION_TYPES or bl_id in EMISSION_IDNAMES:
        principled = ntype == "BSDF_PRINCIPLED" or bl_id == "ShaderNodeBsdfPrincipled"
        color = _sock(node, "Emission Color" if principled else "Color")
        return _sock_spatial(color, seen)
    if ntype in MIX_TYPES or bl_id in MIX_IDNAMES:
        return _mix_spatial(node, seen)
    if ntype in ADD_TYPES or bl_id in ADD_IDNAMES:
        shader_a = _sock(node, "Shader", "Closure1")
        shader_b = _sock(node, "Shader.001", "Shader_001", "Closure2")
        return _link_spatial(shader_a, seen) is True or _link_spatial(shader_b, seen) is True
    if ntype in MIX_COLOR_TYPES or bl_id in MIX_COLOR_IDNAMES:
        return _mix_color_spatial(node, seen)
    if ntype in COLOR_PASSTHRU_TYPES or bl_id in COLOR_PASSTHRU_IDNAMES:
        return _any_input_spatial(node, seen)
    if ntype in RGB_TYPES or bl_id in RGB_IDNAMES:
        return False
    return False


def _sock_spatial(sock, seen):
    if sock is None or not getattr(sock, "is_linked", False):
        return False
    node, from_sock = _link_source(sock)
    if node is None:
        return False
    return _node_spatial(node, from_sock, seen) is True


def _mix_spatial(node, seen):
    fac = _sock(node, "Fac", "Factor")
    shader_a = _sock(node, "Shader", "Closure1")
    shader_b = _sock(node, "Shader.001", "Shader_001", "Closure2")
    if fac is None or getattr(fac, "is_linked", False):
        return (_link_spatial(shader_a, seen) is True
                or _link_spatial(shader_b, seen) is True)
    fac_val = getattr(fac, "default_value", None)
    if not isinstance(fac_val, (int, float)):
        return (_link_spatial(shader_a, seen) is True
                or _link_spatial(shader_b, seen) is True)
    if abs(float(fac_val)) <= ZERO_EPS:
        return _link_spatial(shader_a, seen) is True
    if float(fac_val) >= OPAQUE_FAC:
        return _link_spatial(shader_b, seen) is True
    return (_link_spatial(shader_a, seen) is True
            or _link_spatial(shader_b, seen) is True)


def _mix_color_spatial(node, seen):
    a = _sock(node, "Color1", "A", "A_Color", "A_Float")
    b = _sock(node, "Color2", "B", "B_Color", "B_Float")
    fac = _sock(node, "Fac", "Factor", "Factor_Float")
    if fac is not None and not getattr(fac, "is_linked", False):
        fac_val = getattr(fac, "default_value", None)
        if isinstance(fac_val, (int, float)):
            if abs(float(fac_val)) <= ZERO_EPS:
                return _sock_spatial(a, seen)
            if float(fac_val) >= OPAQUE_FAC:
                return _sock_spatial(b, seen)
    return _sock_spatial(a, seen) or _sock_spatial(b, seen)


def _any_input_spatial(node, seen):
    for sock in getattr(node, "inputs", ()) or ():
        if _sock_spatial(sock, seen):
            return True
    return False


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


def _scene_has_portal(scene):
    for obj in getattr(scene, "objects", ()) or ():
        if getattr(obj, "type", "") != "LIGHT":
            continue
        data = getattr(obj, "data", None)
        cycles = getattr(data, "cycles", None)
        if bool(getattr(cycles, "is_portal", False)):
            return True
    return False


def _protected(datablock):
    return getattr(getattr(datablock, "scenequant", None), "override", "AUTO") != "AUTO"


def _is_linked(datablock):
    if getattr(datablock, "library", None) is not None:
        return True
    tree = getattr(datablock, "node_tree", None)
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
