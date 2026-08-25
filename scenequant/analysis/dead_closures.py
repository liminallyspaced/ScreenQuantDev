# L1 DEAD_CLOSURE_PRUNE: classify sockets that latch transparent / volume
# flags but are proven not to contribute. Analyze-only by default.
#
# Walks the same hide_render=False GEOMETRY_TYPES materials as
# scenequant.nodes.iter_render_materials / iter_render_image_nodes.
# No bpy.ops. Importable without Blender (duck-typed scene + node trees).
#
# Mix Shader Fac proven 0/1 + unused Transparent BSDF is
# PRUNE_MIX_TRANSPARENT (L1.5). Apply unlinks the dead shader input
# (NODE_UNLINK passthrough). It is NOT wired into Make it Fast Auto.
# Displacement proven-zero is PRUNE_DISPLACE (L1.6). Unlink the
# Displacement socket so Cycles drops has_displacement. Same apply.
# Subsurface Weight proven-zero is PRUNE_SSS (L1.7). Unlink Weight
# only (Scale default 0.1; unlinking Scale would ENABLE SSS).
# Emission Strength proven-zero is PRUNE_EMISSION. Unlink Strength
# only (Color default white). Same NODE_UNLINK apply. Not in Auto.
# Transmission Weight proven-zero is PRUNE_TRANSMISSION. Linked 0 is
# not glass (Cycles has no has_surface_transmission link latch).
# Same NODE_UNLINK apply. Not in Auto.
# Never writes scene.cycles.* or use_transparent_shadow.

import os

PRUNE_ALPHA = "PRUNE_ALPHA"
PRUNE_VOLUME = "PRUNE_VOLUME"
PRUNE_MIX_TRANSPARENT = "PRUNE_MIX_TRANSPARENT"
PRUNE_DISPLACE = "PRUNE_DISPLACE"
PRUNE_SSS = "PRUNE_SSS"
PRUNE_EMISSION = "PRUNE_EMISSION"
PRUNE_TRANSMISSION = "PRUNE_TRANSMISSION"
PRUNE_AOV = "PRUNE_AOV"
KEEP_REAL_CUTOUT = "KEEP_REAL_CUTOUT"
KEEP_GLASS = "KEEP_GLASS"
SKIP_GROUP = "SKIP_GROUP"
SKIP_LINKED = "SKIP_LINKED"

ALL_CLASSES = (
    PRUNE_ALPHA, PRUNE_VOLUME, PRUNE_MIX_TRANSPARENT, PRUNE_DISPLACE,
    PRUNE_SSS, PRUNE_EMISSION, PRUNE_TRANSMISSION, PRUNE_AOV,
    KEEP_REAL_CUTOUT, KEEP_GLASS, SKIP_GROUP, SKIP_LINKED,
)
PRUNE_CLASSES = frozenset({
    PRUNE_ALPHA, PRUNE_VOLUME, PRUNE_MIX_TRANSPARENT, PRUNE_DISPLACE,
    PRUNE_SSS, PRUNE_EMISSION, PRUNE_TRANSMISSION, PRUNE_AOV,
})

# Cycles CLOSURE_WEIGHT_CUTOFF is ~1e-5. Only treat a constant as opaque
# when it is at least this close to 1.0 (conservative).
OPAQUE_ALPHA = 1.0 - 1e-4
# Proven-zero for Displacement / Height / Scale (same eps as Mix Fac=0).
ZERO_EPS = 1e-4

VOLUME_PROVEN = frozenset({
    "PRINCIPLED_VOLUME", "VOLUME_SCATTER", "VOLUME_ABSORPTION",
})
GLASS_TYPES = frozenset({"BSDF_GLASS", "BSDF_REFRACTION"})
GROUP_TYPES = frozenset({"GROUP"})
IMAGE_NODE_TYPES = frozenset({"TEX_IMAGE", "TEX_ENVIRONMENT"})
IMAGE_NODE_IDNAMES = frozenset({
    "ShaderNodeTexImage", "ShaderNodeTexEnvironment",
})
# Conservative: these in the Alpha source hop are not proven-opaque.
UNSAFE_ALPHA_TYPES = frozenset({
    "GROUP", "LIGHT_PATH", "VALTORGB", "CURVE_RGB", "CURVE_VEC",
    "CURVE_FLOAT", "SEPRGB", "SEPHSV", "SEPARATE_COLOR",
    "MATH", "MIX", "MIX_RGB", "MIX_COLOR", "HUE_SAT", "RAMP",
    "ATTRIBUTE", "UVMAP", "TEX_COORD", "FRESNEL", "LAYER_WEIGHT",
    "SHADER_TO_RGB", "HOLDOUT",
})
CUTOUT_SURFACE = frozenset({
    "BSDF_DIFFUSE", "BSDF_GLOSSY", "BSDF_PRINCIPLED",
    "BSDF_TRANSLUCENT", "BSDF_VELVET", "BSDF_TOON",
})
JPEG_EXTS = frozenset({".jpg", ".jpeg", ".jpe"})
NO_ALPHA_FORMATS = frozenset({"JPEG", "JPG", "BMP"})
JPEG_SOI = b"\xff\xd8"
BMP_MAGIC = b"BM"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
NO_ALPHA_MODES = frozenset({"NONE", "IGNORE"})
COMBINED_PASS_NAMES = frozenset({"Image", "Alpha", "Combined"})
# View-layer RNA sockets that are not custom AOVs (same map as PASS_PRUNE).
PASS_SOCKET_NAMES = frozenset({
    "Depth", "Mist", "Normal", "UV", "Vector", "IndexOB", "IndexMA",
    "DiffDir", "DiffInd", "DiffCol", "GlossDir", "GlossInd", "GlossCol",
    "TransDir", "TransInd", "TransCol", "Emit", "Env", "Shadow", "AO",
    "VolumeDir", "VolumeInd", "Position", "Image", "Alpha", "Combined",
})

ACTION_KIND = "NODE_UNLINK"
SPEED_KIND = "DEAD_CLOSURE_PRUNE"


def _geometry_types():
    try:
        from ..constants import GEOMETRY_TYPES
        return GEOMETRY_TYPES
    except Exception:
        return frozenset({
            "MESH", "CURVE", "SURFACE", "META", "FONT",
            "CURVES", "POINTCLOUD", "VOLUME",
        })


def _walk_render_materials(scene):
    """Same filter as scenequant.nodes.iter_render_materials."""
    types = _geometry_types()
    seen = {}
    order = []
    for obj in getattr(scene, "objects", ()) or ():
        if getattr(obj, "type", "") not in types:
            continue
        if getattr(obj, "hide_render", False):
            continue
        obj_name = getattr(obj, "name", "") or ""
        for slot in getattr(obj, "material_slots", ()) or ():
            material = getattr(slot, "material", None)
            if material is None:
                continue
            key = id(material)
            if key not in seen:
                seen[key] = (material, [])
                order.append(key)
            users = seen[key][1]
            if obj_name and obj_name not in users:
                users.append(obj_name)
    for key in order:
        yield seen[key]


def iter_render_materials(scene):
    """Yield (material, user_names). Prefers scenequant.nodes when imported."""
    try:
        from .. import nodes
        walker = getattr(nodes, "iter_render_materials", None)
        if walker is not None:
            return walker(scene)
    except Exception:
        pass
    return _walk_render_materials(scene)


def _protected(obj):
    override = getattr(getattr(obj, "scenequant", None), "override", "AUTO")
    return override not in (None, "", "AUTO")


def _is_linked_id(datablock):
    if datablock is None:
        return False
    if getattr(datablock, "library", None) is not None:
        return True
    return getattr(datablock, "override_library", None) is not None


def _user_objects(scene, names):
    wanted = set(names or ())
    found = []
    for obj in getattr(scene, "objects", ()) or ():
        if getattr(obj, "name", None) in wanted:
            found.append(obj)
    return found


def _any_protected(scene, user_names):
    for obj in _user_objects(scene, user_names):
        if _protected(obj):
            return True
    return False


def _record(material, node, socket, cls, reason, users, **extra):
    rec = {
        "material": getattr(material, "name", "") or "",
        "node": getattr(node, "name", "") if node is not None else "",
        "socket": socket or "",
        "class": cls,
        "reason": reason,
        "users": list(users or []),
    }
    rec.update(extra)
    return rec


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


def _node_type(node):
    return getattr(node, "type", "") or ""


def _is_image_node(node):
    if node is None:
        return False
    if _node_type(node) in IMAGE_NODE_TYPES:
        return True
    return getattr(node, "bl_idname", "") in IMAGE_NODE_IDNAMES


def _is_group_node(node):
    return _node_type(node) == "GROUP" or getattr(node, "bl_idname", "") == "ShaderNodeGroup"


def _tree_has_group(tree):
    for node in getattr(tree, "nodes", ()) or ():
        if _is_group_node(node):
            return True
    return False


def _tree_is_glass(tree):
    for node in getattr(tree, "nodes", ()) or ():
        ntype = _node_type(node)
        if ntype in GLASS_TYPES:
            return True
        if ntype == "BSDF_PRINCIPLED" and _principled_transmits(node):
            return True
    return False


def _principled_transmits(node):
    """True iff this Principled is real glass / refraction.

    Linked Transmission Weight at proven 0 is NOT glass. Cycles 4.5
    has no has_surface_transmission link-OR latch (unlike Alpha/SSS).
    Weight is stack_assign into NODE_CLOSURE_BSDF; unlinked default 0
    is a constant 0. Texture / Math / GROUP stay glass (conservative).
    Unlinked default > 0.2 stays glass. BSDF_GLASS is a different check.
    """
    sock = _sock(node, "Transmission Weight", "Transmission")
    if sock is None:
        return False
    if getattr(sock, "is_linked", False):
        if _proven_zero_scalar(sock):
            return False
        return True
    value = getattr(sock, "default_value", 0.0)
    return isinstance(value, (int, float)) and value > 0.2


def _find_output_nodes(tree):
    found = []
    for node in getattr(tree, "nodes", ()) or ():
        ntype = _node_type(node)
        bl_id = getattr(node, "bl_idname", "")
        if ntype == "OUTPUT_MATERIAL" or bl_id == "ShaderNodeOutputMaterial":
            found.append(node)
    return found


def _reachable_nodes(sock):
    seen = set()
    out = []
    stack = [sock]
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
            out.append(node)
            for inp in _iter_socks(node, "inputs"):
                stack.append(inp)
    return out


def _socket_name(sock):
    if sock is None:
        return ""
    return getattr(sock, "identifier", None) or getattr(sock, "name", "") or ""


def _constant_float(node, sock):
    if sock is not None:
        value = getattr(sock, "default_value", None)
        if isinstance(value, (int, float)):
            return float(value)
    if node is None:
        return None
    out = _sock(node, "Value", "Fac", collection="outputs")
    if out is not None:
        value = getattr(out, "default_value", None)
        if isinstance(value, (int, float)):
            return float(value)
    value = getattr(node, "outputs", None)
    return None


def _packed_file_prefix(image, n=8):
    """First n bytes of image.packed_file.data. Never the whole blob.

    Empty / missing data returns None (do not guess). Live bpy PackedFile
    and DNA ducks both expose .data; a boolean leftover has no .data.
    """
    packed = getattr(image, "packed_file", None)
    if packed is None or packed is False:
        return None
    data = getattr(packed, "data", None)
    if data is None:
        return None
    try:
        prefix = data[:n]
    except TypeError:
        return None
    if isinstance(prefix, memoryview):
        prefix = prefix.tobytes()
    elif isinstance(prefix, bytearray):
        prefix = bytes(prefix)
    elif isinstance(prefix, str):
        return None
    elif not isinstance(prefix, bytes):
        try:
            prefix = bytes(prefix)
        except (TypeError, ValueError):
            return None
    if not prefix:
        return None
    return prefix


def _image_has_no_alpha(image):
    """True only when the file is proven to have no alpha channel.

    channels / file_format / extension stay first and can prove without
    packed data. PackedFile magic is an extra proof for packed JPEGs
    (and BMP) whose filepath is empty or not useful. PNG signature is
    the alpha path: do not prune from magic. Empty packed data does
    not guess.
    """
    if image is None:
        return False
    channels = getattr(image, "channels", None)
    if isinstance(channels, int):
        if channels >= 4:
            return False
        if channels in (1, 2, 3):
            return True
    fmt = str(getattr(image, "file_format", "") or "").upper()
    if fmt in NO_ALPHA_FORMATS:
        return True
    path = (getattr(image, "filepath", None)
            or getattr(image, "filepath_raw", None)
            or "")
    ext = os.path.splitext(str(path))[1].lower()
    if ext in JPEG_EXTS or ext == ".bmp":
        return True
    magic = _packed_file_prefix(image, 8)
    if magic is not None:
        if len(magic) >= 2 and magic[:2] == JPEG_SOI:
            return True
        if len(magic) >= 2 and magic[:2] == BMP_MAGIC:
            return True
        if magic == PNG_SIGNATURE:
            return False
    return False


def _image_alpha_ignored(image):
    mode = str(getattr(image, "alpha_mode", "") or "").upper()
    return mode in NO_ALPHA_MODES


def _alpha_output_has_cutout_user(from_node, from_sock, tree):
    """True if this Image Alpha also drives a Transparent mix (real cutout)."""
    if from_sock is None:
        return False
    for link in getattr(from_sock, "links", None) or ():
        to_node = getattr(link, "to_node", None)
        if to_node is None:
            continue
        if _node_type(to_node) == "MIX_SHADER" and _tree_has_transparent_mix(tree):
            return True
    return False


def _mix_shader_inputs(node):
    """Return (fac_socket, [shader_socket, ...]) in node input order.

    Mix Shader is (1-Fac)*Shader + Fac*Shader_001. First shader is live
    at Fac=0; second is live at Fac=1. Identifiers are Fac / Shader /
    Shader_001 in Blender; duck tests may use Shader.001.
    """
    fac = None
    shaders = []
    for sock in _iter_socks(node, "inputs"):
        ident = getattr(sock, "identifier", "") or ""
        name = getattr(sock, "name", "") or ""
        if ident == "Fac" or name == "Fac":
            fac = sock
            continue
        shaders.append(sock)
    if fac is None:
        fac = _sock(node, "Fac")
    return fac, shaders


def _proven_constant_fac(sock):
    """Return a float iff Fac is proven constant; else None.

    Proven: unconnected default_value, or a Value node. Texture / Light
    Path / Mix / Group / anything else is unproven (KEEP / skip).
    """
    if sock is None:
        return None
    if not getattr(sock, "is_linked", False):
        value = getattr(sock, "default_value", None)
        if isinstance(value, (int, float)):
            return float(value)
        return None
    from_node, from_sock = _link_source(sock)
    if from_node is None:
        return None
    ntype = _node_type(from_node)
    bl_id = getattr(from_node, "bl_idname", "") or ""
    if ntype == "VALUE" or bl_id == "ShaderNodeValue":
        return _constant_float(from_node, from_sock)
    return None


def _shader_is_only_transparent(sock, seen=None):
    """True if this shader socket is Transparent BSDF or a chain of only those."""
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
    ntype = _node_type(node)
    if ntype == "BSDF_TRANSPARENT":
        return True
    if ntype == "MIX_SHADER":
        _fac, shaders = _mix_shader_inputs(node)
        linked = False
        for sock in shaders:
            if not getattr(sock, "is_linked", False):
                continue
            linked = True
            if not _shader_is_only_transparent(sock, seen):
                return False
        return linked
    if ntype == "ADD_SHADER":
        linked = False
        for sock in _iter_socks(node, "inputs"):
            if not getattr(sock, "is_linked", False):
                continue
            linked = True
            if not _shader_is_only_transparent(sock, seen):
                return False
        return linked
    return False


def _tree_has_transparent_mix(tree):
    types = {_node_type(n) for n in getattr(tree, "nodes", ()) or ()}
    if "BSDF_TRANSPARENT" not in types:
        return False
    if not (types & CUTOUT_SURFACE):
        return False
    for node in getattr(tree, "nodes", ()) or ():
        if _node_type(node) != "MIX_SHADER":
            continue
        fac, _shaders = _mix_shader_inputs(node)
        if fac is None or not getattr(fac, "is_linked", False):
            continue
        value = _proven_constant_fac(fac)
        if value is not None and (value >= OPAQUE_ALPHA or value <= 1e-4):
            # Fac is a proven 0/1 Value — not a real cutout.
            continue
        return True
    return False


def _mix_nodes_feeding_surface(output, tree):
    """Mix Shaders feeding Surface, including chained mixes."""
    surface = _sock(output, "Surface") if output is not None else None
    if surface is not None and getattr(surface, "is_linked", False):
        reachable = _reachable_nodes(surface)
        return [n for n in reachable if _node_type(n) == "MIX_SHADER"]
    return [n for n in getattr(tree, "nodes", ()) or ()
            if _node_type(n) == "MIX_SHADER"]


def _classify_mix_transparent(mix_node):
    """Return (node, socket, class, reason, from_node, from_sock) or None.

    Unlink the dead Transparent input so the mix becomes a passthrough.
    Existing apply_dead_closures NODE_UNLINK reverts that unlink.
    """
    fac, shaders = _mix_shader_inputs(mix_node)
    if len(shaders) < 2:
        return None
    value = _proven_constant_fac(fac)
    if value is None:
        return None
    first, second = shaders[0], shaders[1]
    if value >= OPAQUE_ALPHA:
        dead = first
    elif value <= 1e-4:
        dead = second
    else:
        return None
    if not _shader_is_only_transparent(dead):
        return None
    from_node, from_sock = _link_source(dead)
    reason = (
        "MIX_TRANSPARENT: Mix Shader Fac=%.4g unused Transparent BSDF"
        % value
    )
    return (mix_node, _socket_name(dead), PRUNE_MIX_TRANSPARENT,
            reason, from_node, from_sock)


def _classify_alpha_source(from_node, from_sock, tree):
    """Return (class, reason, alpha_src) or None if not a verdict."""
    if from_node is None:
        return None
    ntype = _node_type(from_node)
    src_name = _socket_name(from_sock)
    if ntype in UNSAFE_ALPHA_TYPES or _is_group_node(from_node):
        return (KEEP_REAL_CUTOUT,
                "Alpha source is %s (not proven opaque)" % (ntype or "unknown"),
                "OTHER")
    if ntype == "VALUE":
        value = _constant_float(from_node, from_sock)
        if value is not None and value >= OPAQUE_ALPHA:
            return (PRUNE_ALPHA,
                    "Principled Alpha linked to Value=%.4g (opaque)" % value,
                    "CONST(%.4g)" % value)
        if value is not None:
            return (KEEP_REAL_CUTOUT,
                    "Principled Alpha linked to Value=%.4g (real alpha)" % value,
                    "CONST(%.4g)" % value)
        return None
    if _is_image_node(from_node):
        image = getattr(from_node, "image", None)
        path = ""
        channels = None
        mode = ""
        if image is not None:
            path = (getattr(image, "filepath", None)
                    or getattr(image, "filepath_raw", None)
                    or "")
            channels = getattr(image, "channels", None)
            mode = str(getattr(image, "alpha_mode", "") or "")
        src = "IMAGE(%s, channels=%s, alpha_mode=%s)" % (
            path or getattr(image, "name", "") if image is not None else "?",
            channels, mode or "?")
        if src_name and src_name not in ("Alpha", "A"):
            return (KEEP_REAL_CUTOUT,
                    "Principled Alpha linked to Image %s (mask, not Alpha)" % src_name,
                    src)
        if image is None:
            return (KEEP_REAL_CUTOUT,
                    "Principled Alpha linked to Image with no datablock",
                    "IMAGE(?, channels=?, alpha_mode=?)")
        if _image_alpha_ignored(image):
            if _alpha_output_has_cutout_user(from_node, from_sock, tree):
                return (KEEP_REAL_CUTOUT,
                        "Image alpha_mode IGNORE but Alpha also drives a cutout mix",
                        src)
            return (PRUNE_ALPHA,
                    "Image alpha_mode %s (alpha ignored)" % (mode or "IGNORE"),
                    src)
        if _image_has_no_alpha(image):
            return (PRUNE_ALPHA,
                    "Image has no alpha channel (JPEG / opaque)",
                    src)
        return (KEEP_REAL_CUTOUT,
                "Image has an alpha channel (real cutout)",
                src)
    return (KEEP_REAL_CUTOUT,
            "Principled Alpha source %s is not proven opaque" % (ntype or "unknown"),
            "OTHER")


def _classify_volume(output_node, tree):
    sock = _sock(output_node, "Volume")
    if sock is None or not getattr(sock, "is_linked", False):
        return None
    from_node, from_sock = _link_source(sock)
    nodes = _reachable_nodes(sock)
    types = {_node_type(n) for n in nodes}
    if types & GROUP_TYPES:
        return None  # tree-level SKIP_GROUP already fired
    proven = [n for n in nodes if _node_type(n) in VOLUME_PROVEN]
    if proven:
        all_zero = True
        for node in proven:
            dens = _sock(node, "Density")
            if dens is None:
                all_zero = False
                break
            if getattr(dens, "is_linked", False):
                all_zero = False
                break
            value = getattr(dens, "default_value", 1.0)
            if not (isinstance(value, (int, float)) and value <= 0.0):
                all_zero = False
                break
        if not all_zero:
            return None
        return (output_node, "Volume", PRUNE_VOLUME,
                "Volume linked to volume node(s) with unlinked Density=0",
                from_node, from_sock)
    return (output_node, "Volume", PRUNE_VOLUME,
            "Volume linked to a subgraph with no volume nodes",
            from_node, from_sock)


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
    return all(_near_zero_float(item) for item in seq)


def _proven_zero_scalar(sock):
    """True iff sock is unlinked ~0 or a Value node ~0. One hop. No Math."""
    if sock is None:
        return False
    if not getattr(sock, "is_linked", False):
        return _near_zero_float(getattr(sock, "default_value", None))
    from_node, from_sock = _link_source(sock)
    if from_node is None or _is_group_node(from_node):
        return False
    ntype = _node_type(from_node)
    bl_id = getattr(from_node, "bl_idname", "") or ""
    if ntype == "VALUE" or bl_id == "ShaderNodeValue":
        value = _constant_float(from_node, from_sock)
        return value is not None and _near_zero_float(value)
    return False


def _source_is_proven_zero(node, sock):
    """Immediate Displacement source is a proven 0 / zero vector.

    Proven: Value ~0, Vector/RGB ~0, Combine XYZ all ~0, Displacement
    Height+Scale ~0, Vector Displacement Scale ~0. Texture / noise /
    attribute / GROUP / driver-unknown / Math = not proven.
    """
    if node is None or _is_group_node(node):
        return False
    ntype = _node_type(node)
    bl_id = getattr(node, "bl_idname", "") or ""
    if ntype == "VALUE" or bl_id == "ShaderNodeValue":
        value = _constant_float(node, sock)
        return value is not None and _near_zero_float(value)
    if (ntype in ("COMBXYZ", "COMBINE_XYZ", "COMB_XYZ")
            or bl_id == "ShaderNodeCombineXYZ"):
        return (
            _proven_zero_scalar(_sock(node, "X"))
            and _proven_zero_scalar(_sock(node, "Y"))
            and _proven_zero_scalar(_sock(node, "Z"))
        )
    if ntype in ("VECTOR", "RGB") or bl_id == "ShaderNodeRGB":
        value = getattr(sock, "default_value", None) if sock is not None else None
        if value is None:
            out = _sock(node, "Vector", "Color", "RGB", collection="outputs")
            value = getattr(out, "default_value", None) if out is not None else None
        return _near_zero_vector(value)
    if ntype == "DISPLACEMENT" or bl_id == "ShaderNodeDisplacement":
        return (
            _proven_zero_scalar(_sock(node, "Height"))
            and _proven_zero_scalar(_sock(node, "Scale"))
        )
    if (ntype in ("VECTOR_DISPLACEMENT", "VECTOR_DISPLACE")
            or bl_id == "ShaderNodeVectorDisplacement"):
        return _proven_zero_scalar(_sock(node, "Scale"))
    return False


def _classify_displace(output_node, tree):
    """Return prune tuple if Displacement is linked to proven-zero.

    Unconnected Displacement is already dead — no record.
    """
    sock = _sock(output_node, "Displacement")
    if sock is None or not getattr(sock, "is_linked", False):
        return None
    from_node, from_sock = _link_source(sock)
    if from_node is None:
        return None
    if not _source_is_proven_zero(from_node, from_sock):
        return None
    return (output_node, "Displacement", PRUNE_DISPLACE,
            "Displacement linked to proven-zero constant / zero-scale Displacement",
            from_node, from_sock)


def _is_float_sock(sock):
    """True when default_value is a scalar (not Color / vector)."""
    if sock is None:
        return False
    stype = getattr(sock, "type", None)
    if stype in ("VALUE", "INT"):
        return True
    if stype in ("RGBA", "VECTOR", "SHADER", "COLOR"):
        return False
    value = getattr(sock, "default_value", None)
    return isinstance(value, (int, float))


def _classify_sss(principled_node):
    """Return prune tuple if Subsurface Weight is linked to proven-zero.

    A link alone on Weight latches KERNEL_FEATURE_SUBSURFACE because
    Scale default is 0.1 (not zero). Unlink Weight only (default 0).
    Never unlink Scale — that would ENABLE SSS on a real-weight material.
    Weight unlinked 0 is already dead — no record.
    """
    sock = _sock(principled_node, "Subsurface Weight")
    if sock is None:
        sock = _sock(principled_node, "Subsurface")
        if sock is None or not _is_float_sock(sock):
            return None
    if not getattr(sock, "is_linked", False):
        return None
    if not _proven_zero_scalar(sock):
        return None
    from_node, from_sock = _link_source(sock)
    return (principled_node, _socket_name(sock), PRUNE_SSS,
            "Principled Subsurface Weight linked to proven-zero (false SSS latch)",
            from_node, from_sock)


def _classify_emission(principled_node):
    """Return prune tuple if Emission Strength is linked to proven-zero.

    A link alone on Strength latches has_surface_emission because Color
    default is white. Unlink Strength only (default 0). Never unlink Color.
    After unlink, has_surface_emission is false even if Color is white.
    """
    sock = _sock(principled_node, "Emission Strength")
    if sock is None:
        sock = _sock(principled_node, "Emission")
        if sock is None or not _is_float_sock(sock):
            return None
    if not getattr(sock, "is_linked", False):
        return None
    if not _proven_zero_scalar(sock):
        return None
    from_node, from_sock = _link_source(sock)
    return (principled_node, _socket_name(sock), PRUNE_EMISSION,
            "Principled Emission Strength linked to proven-zero "
            "(false mesh-light latch)",
            from_node, from_sock)


def _classify_transmission(principled_node):
    """Return prune tuple if Transmission Weight is linked to proven-zero.

    Cycles has no has_surface_transmission link-OR kernel flag.
    Unlink Weight only (default 0). Image / Math / GROUP / unlinked-0
    / real-weight skipped. Call after the glass skip: a Value-0 Weight
    is not glass, so this walk can also emit PRUNE_SSS / EMISSION / ALPHA.
    """
    sock = _sock(principled_node, "Transmission Weight")
    if sock is None:
        sock = _sock(principled_node, "Transmission")
        if sock is None or not _is_float_sock(sock):
            return None
    if not getattr(sock, "is_linked", False):
        return None
    if not _proven_zero_scalar(sock):
        return None
    from_node, from_sock = _link_source(sock)
    return (principled_node, _socket_name(sock), PRUNE_TRANSMISSION,
            "Principled Transmission Weight linked to proven-zero "
            "(not glass; SVM-constant 0)",
            from_node, from_sock)


def _aov_name(node):
    for attr in ("aov_name", "name"):
        value = getattr(node, attr, None)
        if isinstance(value, str) and value and attr == "aov_name":
            return value
    # ShaderNodeOutputAOV.name is the AOV name on 4.x; node name may match.
    value = getattr(node, "name", "") or ""
    if value in ("AOV Output", "ShaderNodeOutputAOV"):
        return getattr(node, "aov_name", "") or value
    return value


def _iter_comp_trees(scene):
    pending = []
    if getattr(scene, "use_nodes", False):
        pending.append(getattr(scene, "node_tree", None))
    pending.append(getattr(scene, "compositing_node_group", None))
    seen = set()
    while pending:
        tree = pending.pop()
        if tree is None:
            continue
        ident = id(tree)
        if ident in seen:
            continue
        seen.add(ident)
        yield tree
        for node in getattr(tree, "nodes", ()) or ():
            if _node_type(node) != "GROUP":
                continue
            nested = getattr(node, "node_tree", None)
            if nested is not None:
                pending.append(nested)


def _used_compositor_aovs(scene):
    """(used_names, unknown_group). Same walk as PASS_PRUNE + AOV sockets."""
    used = set()
    unknown = False
    for tree in _iter_comp_trees(scene):
        for node in getattr(tree, "nodes", ()) or ():
            ntype = _node_type(node)
            if ntype == "GROUP" and getattr(node, "node_tree", None) is None:
                unknown = True
                continue
            if ntype != "R_LAYERS":
                continue
            for out in getattr(node, "outputs", ()) or ():
                if not getattr(out, "is_linked", False):
                    continue
                name = getattr(out, "name", "") or ""
                if name and name not in PASS_SOCKET_NAMES:
                    used.add(name)
    return used, unknown


def _classify_aovs(tree, scene, material, users):
    used, unknown = _used_compositor_aovs(scene)
    if unknown:
        return []
    records = []
    for node in getattr(tree, "nodes", ()) or ():
        ntype = _node_type(node)
        bl_id = getattr(node, "bl_idname", "")
        if ntype != "OUTPUT_AOV" and bl_id != "ShaderNodeOutputAOV":
            continue
        name = _aov_name(node)
        if not name or name in used:
            continue
        records.append(_record(
            material, node, "Color", PRUNE_AOV,
            "AOV Output %r is not read by any compositor R_LAYERS socket" % name,
            users, aov_name=name))
    return records


def classify_dead_closures(scene):
    """Return inventory records for local render-used materials.

    Each record has: material, node, socket, class, reason, users.
    class is one of PRUNE_ALPHA | PRUNE_VOLUME | PRUNE_MIX_TRANSPARENT |
    PRUNE_DISPLACE | PRUNE_SSS | PRUNE_EMISSION | PRUNE_TRANSMISSION |
    PRUNE_AOV | KEEP_REAL_CUTOUT | KEEP_GLASS | SKIP_GROUP | SKIP_LINKED.
    HERO / EXCLUDE-shared materials are skipped (no record).
    """
    records = []
    for material, users in iter_render_materials(scene):
        if _any_protected(scene, users):
            continue
        if _is_linked_id(material):
            records.append(_record(
                material, None, "", SKIP_LINKED,
                "linked material (no override write)", users))
            continue
        tree = getattr(material, "node_tree", None)
        if tree is None:
            continue
        if _tree_has_group(tree):
            records.append(_record(
                material, None, "", SKIP_GROUP,
                "GROUP node tree is unproven (not expanded)", users))
            continue
        if _tree_is_glass(tree):
            records.append(_record(
                material, None, "", KEEP_GLASS,
                "glass / refraction / principled transmission — never prune",
                users))
            continue
        outputs = _find_output_nodes(tree)
        saw_cutout = False
        if _tree_has_transparent_mix(tree):
            saw_cutout = True
            records.append(_record(
                material, None, "Fac", KEEP_REAL_CUTOUT,
                "HASHED/mix Transparent + surface with linked Fac (real cutout)",
                users))
        for output in outputs:
            surface = _sock(output, "Surface")
            reachable = _reachable_nodes(surface) if surface is not None else []
            principleds = [n for n in reachable if _node_type(n) == "BSDF_PRINCIPLED"]
            if not principleds:
                # No live output walk: still inspect tree principleds so
                # duck-typed tests that omit the Surface link classify.
                principleds = [n for n in getattr(tree, "nodes", ()) or ()
                               if _node_type(n) == "BSDF_PRINCIPLED"]
            for node in principleds:
                alpha = _sock(node, "Alpha")
                if alpha is not None and getattr(alpha, "is_linked", False):
                    from_node, from_sock = _link_source(alpha)
                    verdict = _classify_alpha_source(from_node, from_sock, tree)
                    if verdict is not None:
                        cls, reason, alpha_src = verdict
                        if not (cls == PRUNE_ALPHA and saw_cutout):
                            if cls == KEEP_REAL_CUTOUT:
                                saw_cutout = True
                            records.append(_record(
                                material, node, "Alpha", cls, reason, users,
                                alpha_src=alpha_src,
                                from_node=getattr(from_node, "name", "") if from_node else "",
                                from_socket=_socket_name(from_sock)))
                sss = _classify_sss(node)
                if sss is not None:
                    snode, ssock, cls, reason, from_node, from_sock = sss
                    records.append(_record(
                        material, snode, ssock, cls, reason, users,
                        from_node=getattr(from_node, "name", "") if from_node else "",
                        from_socket=_socket_name(from_sock)))
                emission = _classify_emission(node)
                if emission is not None:
                    enode, esock, cls, reason, from_node, from_sock = emission
                    records.append(_record(
                        material, enode, esock, cls, reason, users,
                        from_node=getattr(from_node, "name", "") if from_node else "",
                        from_socket=_socket_name(from_sock)))
                transmission = _classify_transmission(node)
                if transmission is not None:
                    tnode, tsock, cls, reason, from_node, from_sock = transmission
                    records.append(_record(
                        material, tnode, tsock, cls, reason, users,
                        from_node=getattr(from_node, "name", "") if from_node else "",
                        from_socket=_socket_name(from_sock)))
            vol = _classify_volume(output, tree)
            if vol is not None:
                vnode, vsock, cls, reason, from_node, from_sock = vol
                records.append(_record(
                    material, vnode, vsock, cls, reason, users,
                    from_node=getattr(from_node, "name", "") if from_node else "",
                    from_socket=_socket_name(from_sock)))
            for mix in _mix_nodes_feeding_surface(output, tree):
                hit = _classify_mix_transparent(mix)
                if hit is None:
                    continue
                mnode, msock, cls, reason, from_node, from_sock = hit
                records.append(_record(
                    material, mnode, msock, cls, reason, users,
                    from_node=getattr(from_node, "name", "") if from_node else "",
                    from_socket=_socket_name(from_sock)))
            disp = _classify_displace(output, tree)
            if disp is not None:
                dnode, dsock, cls, reason, from_node, from_sock = disp
                records.append(_record(
                    material, dnode, dsock, cls, reason, users,
                    from_node=getattr(from_node, "name", "") if from_node else "",
                    from_socket=_socket_name(from_sock)))
        records.extend(_classify_aovs(tree, scene, material, users))
    return records


def inventory_counts(records):
    counts = {cls: 0 for cls in ALL_CLASSES}
    for rec in records or ():
        cls = rec.get("class")
        if cls in counts:
            counts[cls] += 1
        elif cls:
            counts[cls] = 1
    return counts


def format_inventory(records):
    """Human table for a headless Classroom / loft pass. No time claim."""
    records = list(records or ())
    counts = inventory_counts(records)
    lines = [
        "DEAD_CLOSURE_PRUNE inventory (analyze only; no writes; no time claim)",
        "  PRUNE_ALPHA=%d  PRUNE_VOLUME=%d  PRUNE_MIX_TRANSPARENT=%d  "
        "PRUNE_DISPLACE=%d  PRUNE_SSS=%d  PRUNE_EMISSION=%d  "
        "PRUNE_TRANSMISSION=%d  PRUNE_AOV=%d  KEEP_REAL_CUTOUT=%d  "
        "KEEP_GLASS=%d  SKIP_GROUP=%d  SKIP_LINKED=%d"
        % (counts.get(PRUNE_ALPHA, 0), counts.get(PRUNE_VOLUME, 0),
           counts.get(PRUNE_MIX_TRANSPARENT, 0),
           counts.get(PRUNE_DISPLACE, 0),
           counts.get(PRUNE_SSS, 0), counts.get(PRUNE_EMISSION, 0),
           counts.get(PRUNE_TRANSMISSION, 0),
           counts.get(PRUNE_AOV, 0), counts.get(KEEP_REAL_CUTOUT, 0),
           counts.get(KEEP_GLASS, 0), counts.get(SKIP_GROUP, 0),
           counts.get(SKIP_LINKED, 0)),
        "  gate (official interiors): PRUNE_ALPHA + PRUNE_VOLUME >= 1 "
        "on a non-hero, non-glass material — not yet Auto",
    ]
    for rec in records:
        faces = rec.get("faces")
        face_s = (" faces=%s" % faces) if faces is not None else ""
        alpha_s = ""
        if rec.get("class") == PRUNE_ALPHA:
            alpha_s = "  alpha_src=%s" % (rec.get("alpha_src") or "")
        lines.append(
            "  %-16s  %-20s  %-8s  %-16s  %s  users=%s%s%s"
            % (rec.get("material", ""), rec.get("node", "") or "-",
               rec.get("socket", "") or "-", rec.get("class", ""),
               rec.get("reason", ""), ",".join(rec.get("users") or []),
               face_s, alpha_s))
    return "\n".join(lines)


def print_inventory(records):
    print(format_inventory(records))


def _find_material(scene, name):
    for obj in getattr(scene, "objects", ()) or ():
        for slot in getattr(obj, "material_slots", ()) or ():
            mat = getattr(slot, "material", None)
            if mat is not None and getattr(mat, "name", None) == name:
                return mat
    try:
        import bpy
        uid = None
        return bpy.data.materials.get(name) if isinstance(name, str) else None
    except Exception:
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
    remover = getattr(getattr(tree, "links", None), "remove", None)
    for link in links:
        from_node = getattr(link, "from_node", None)
        from_sock = getattr(link, "from_socket", None)
        if remover is not None:
            try:
                remover(link)
            except Exception:
                continue
        else:
            # Duck-typed socket: drop the link list and clear the flag.
            bucket = getattr(sock, "links", None)
            if bucket is not None:
                try:
                    bucket.remove(link)
                except (ValueError, AttributeError):
                    pass
            sock.is_linked = bool(bucket)
        removed.append((from_node, from_sock))
    if not getattr(sock, "is_linked", False):
        try:
            sock.is_linked = False
        except Exception:
            pass
    return removed


def apply_dead_closures(scene, jrnl, records=None, tag="speed"):
    """Unlink proven-dead sockets. Journal one NODE_UNLINK per write.

    Only PRUNE_* records are written. Not called by Make it Fast Auto.
    Never writes scene.cycles.* or use_transparent_shadow.
    """
    if records is None:
        records = classify_dead_closures(scene)
    applied = []
    for rec in records or ():
        if rec.get("class") not in PRUNE_CLASSES:
            continue
        mat = _find_material(scene, rec.get("material"))
        if mat is None or _is_linked_id(mat):
            continue
        tree = getattr(mat, "node_tree", None)
        if tree is None:
            continue
        node = _find_node(tree, rec.get("node"))
        if node is None:
            continue
        sock = _find_socket(getattr(node, "inputs", None), rec.get("socket"))
        if sock is None or not getattr(sock, "is_linked", False):
            continue
        removed = _unlink_socket(tree, sock)
        for from_node, from_sock in removed:
            payload = {
                "material": rec.get("material"),
                "node": rec.get("node"),
                "socket": rec.get("socket"),
                "from_node": getattr(from_node, "name", "") if from_node else rec.get("from_node", ""),
                "from_socket": _socket_name(from_sock) or rec.get("from_socket", ""),
            }
            if jrnl is not None:
                jrnl.record_action(ACTION_KIND, payload, tag)
            applied.append(payload)
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


def restore_node_unlink(payload, materials=None, scene=None):
    """Relink helper for tests and journal revert (name lookup)."""
    if not isinstance(payload, dict):
        return False
    name = payload.get("material")
    mat = None
    if isinstance(materials, dict):
        mat = materials.get(name)
    elif materials is not None:
        for item in materials:
            if getattr(item, "name", None) == name:
                mat = item
                break
    if mat is None and scene is not None:
        mat = _find_material(scene, name)
    if mat is None:
        mat = _find_material(None, name) if scene is None else None
        if mat is None:
            try:
                import bpy
                mat = bpy.data.materials.get(name) if isinstance(name, str) else None
            except Exception:
                mat = None
    return restore_node_unlink_on_material(mat, payload)


def revert_dead_closures(scene, jrnl):
    """Restore NODE_UNLINK entries recorded on jrnl. Returns relink count."""
    entries = list(getattr(jrnl, "entries", None) or ())
    kept = []
    count = 0
    for entry in entries:
        if isinstance(entry, dict) and entry.get("kind") == ACTION_KIND:
            payload = entry.get("payload") or {}
            if restore_node_unlink(payload, scene=scene):
                count += 1
                continue
        kept.append(entry)
    if hasattr(jrnl, "entries"):
        jrnl.entries = kept
    return count
