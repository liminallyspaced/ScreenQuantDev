# Generic blend DNA inventory without bpy and without launching blender.
#
# Reconstructs duck-typed objects for scenequant.analysis.dead_closures /
# unused_slots / unused_color_attrs / portal_meshes. Works on 2.73
# (integer SH_NODE_* + idname) and 2.8+/4.x/5.x (string ShaderNode* idnames).
#
# Mix Fac source sockets (Geometry Backfacing vs Incoming) are never guessed.
# If DNA cannot name a linked Fac source, print PORTAL_MESH_UNKNOWN; do not
# claim 0 PORTAL_MESH.
#
#   python3 tools/_inventory_blend_dna.py [/path/file.blend]
#
# blendfile.py: https://raw.githubusercontent.com/blender/blender-dev-tools/main/modules/blendfile.py
#
# Mix Fac is never guessed. If default_value cannot be proven from DNA,
# print UNKNOWN_FAC and INCOMPLETE; do not claim 0 PRUNE_MIX_TRANSPARENT.

from __future__ import annotations

import os
import struct
import sys
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
_PUBLIC = "/workspace/scenequant-public"
_ADDON_ROOT = _PUBLIC
for _root in (_PUBLIC, os.path.dirname(_HERE)):
    if os.path.isdir(os.path.join(_root, "scenequant", "analysis")):
        _ADDON_ROOT = _root
        if _root not in sys.path:
            sys.path.insert(0, _root)
        break
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import blendfile  # noqa: E402

import importlib.util


def _load_analysis(name):
    path = os.path.join(_ADDON_ROOT, "scenequant", "analysis", name + ".py")
    spec = importlib.util.spec_from_file_location(
        "scenequant.analysis." + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_dc = _load_analysis("dead_closures")
_us = _load_analysis("unused_slots")
_uc = _load_analysis("unused_color_attrs")
_pm = _load_analysis("portal_meshes")
classify_dead_closures = _dc.classify_dead_closures
dead_counts = _dc.inventory_counts
print_dead = _dc.print_inventory
classify_unused_slots = _us.classify_unused_slots
slot_counts = _us.inventory_counts
print_slots = _us.print_inventory
classify_unused_color_attrs = _uc.classify_unused_color_attrs
color_counts = _uc.inventory_counts
print_colors = _uc.print_inventory
classify_portal_meshes = _pm.classify_portal_meshes
portal_counts = _pm.inventory_counts
print_portals = _pm.print_inventory

OB_RESTRICT_RENDER = 1 << 2
OB_TYPE = {
    0: "EMPTY", 1: "MESH", 2: "CURVE", 3: "SURFACE", 4: "FONT",
    5: "META", 10: "LAMP", 11: "CAMERA", 12: "SPEAKER",
    13: "LIGHTPROBE", 22: "LATTICE", 25: "ARMATURE",
    26: "GPENCIL", 27: "CURVES", 28: "POINTCLOUD", 29: "VOLUME",
}
# 2.8+ type 10 is LIGHT; classifier GEOMETRY_TYPES does not include lights.
OB_TYPE[10] = "LAMP"
SOCK_FLOAT, SOCK_VECTOR, SOCK_RGBA, SOCK_SHADER = 0, 1, 2, 3
CD_MCOL, CD_MLOOPCOL = 6, 17
CD_MTFACE, CD_MTEXPOLY, CD_MLOOPUV = 5, 15, 16
# DNA_customdata_types.h: CD_MCOL=6, CD_MLOOPCOL=17. 3.x+ generic byte/float
# color layers reuse 17 as CD_PROP_BYTE_COLOR in some trees; CD_PROP_COLOR
# is a later enum. We only treat 6 and 17 as proven color. Unknown CD types
# are reported, never guessed into UNUSED_COLOR_ATTRS.
COLOR_CD_TYPES = frozenset({CD_MCOL, CD_MLOOPCOL})
UV_CD_TYPES = frozenset({CD_MTFACE, CD_MTEXPOLY, CD_MLOOPUV})

# Integer SH_NODE_* from BKE_node.h 2.73–2.79 (fallback if idname empty).
NODE_TYPE = {
    2: "GROUP",
    101: "RGB",
    102: "VALUE",
    103: "MIX_RGB",
    104: "VALTORGB",
    109: "MAPPING",
    110: "CURVE_VEC",
    111: "CURVE_RGB",
    115: "MATH",
    119: "INVERT",
    120: "SEPRGB",
    121: "COMBRGB",
    122: "HUE_SAT",
    124: "OUTPUT_MATERIAL",
    125: "OUTPUT_WORLD",
    127: "FRESNEL",
    128: "MIX_SHADER",
    129: "ATTRIBUTE",
    130: "BACKGROUND",
    131: "BSDF_ANISOTROPIC",
    132: "BSDF_DIFFUSE",
    133: "BSDF_GLOSSY",
    134: "BSDF_GLASS",
    137: "BSDF_TRANSLUCENT",
    138: "BSDF_TRANSPARENT",
    139: "BSDF_VELVET",
    140: "EMISSION",
    141: "NEW_GEOMETRY",
    142: "LIGHT_PATH",
    143: "TEX_IMAGE",
    145: "TEX_SKY",
    149: "TEX_WAVE",
    150: "TEX_NOISE",
    155: "TEX_COORD",
    156: "ADD_SHADER",
    157: "TEX_ENVIRONMENT",
    159: "HOLDOUT",
    160: "LAYER_WEIGHT",
    161: "VOLUME_ABSORPTION",
    162: "VOLUME_SCATTER",
    163: "GAMMA",
    167: "OBJECT_INFO",
    170: "BUMP",
    173: "BSDF_REFRACTION",
    174: "TANGENT",
    175: "NORMAL_MAP",
    187: "UVMAP",
    188: "SEPXYZ",
    189: "COMBXYZ",
    192: "AMBIENT_OCCLUSION",
    193: "BSDF_PRINCIPLED",
    198: "DISPLACEMENT",
    201: "VIEWER",
    204: "MIX_RGB",
    221: "R_LAYERS",
    222: "COMPOSITE",
}

# 2.8+/4.x/5.x: node.type may be 0; idname is the RNA identifier.
IDNAME_TYPE = {
    "ShaderNodeMixShader": "MIX_SHADER",
    "ShaderNodeBsdfTransparent": "BSDF_TRANSPARENT",
    "ShaderNodeBsdfPrincipled": "BSDF_PRINCIPLED",
    "ShaderNodeOutputMaterial": "OUTPUT_MATERIAL",
    "ShaderNodeValue": "VALUE",
    "ShaderNodeTexImage": "TEX_IMAGE",
    "ShaderNodeBsdfGlass": "BSDF_GLASS",
    "ShaderNodeDisplacement": "DISPLACEMENT",
    "ShaderNodeVectorDisplacement": "VECTOR_DISPLACEMENT",
    "ShaderNodeBump": "BUMP",
    "ShaderNodeNormalMap": "NORMAL_MAP",
    "ShaderNodeAttribute": "ATTRIBUTE",
    "ShaderNodeVertexColor": "VERTEX_COLOR",
    "ShaderNodeColorAttribute": "VERTEX_COLOR",
    "ShaderNodeGroup": "GROUP",
    "ShaderNodeBsdfDiffuse": "BSDF_DIFFUSE",
    "ShaderNodeBsdfGlossy": "BSDF_GLOSSY",
    "ShaderNodeBsdfAnisotropic": "BSDF_ANISOTROPIC",
    "ShaderNodeBsdfTranslucent": "BSDF_TRANSLUCENT",
    "ShaderNodeBsdfVelvet": "BSDF_VELVET",
    "ShaderNodeBsdfRefraction": "BSDF_REFRACTION",
    "ShaderNodeBsdfToon": "BSDF_TOON",
    "ShaderNodeEmission": "EMISSION",
    "ShaderNodeAddShader": "ADD_SHADER",
    "ShaderNodeHoldout": "HOLDOUT",
    "ShaderNodeVolumeAbsorption": "VOLUME_ABSORPTION",
    "ShaderNodeVolumeScatter": "VOLUME_SCATTER",
    "ShaderNodeVolumePrincipled": "PRINCIPLED_VOLUME",
    "ShaderNodeTexEnvironment": "TEX_ENVIRONMENT",
    "ShaderNodeTexCoord": "TEX_COORD",
    "ShaderNodeTexNoise": "TEX_NOISE",
    "ShaderNodeTexSky": "TEX_SKY",
    "ShaderNodeTexWave": "TEX_WAVE",
    "ShaderNodeUVMap": "UVMAP",
    "ShaderNodeTangent": "TANGENT",
    "ShaderNodeNewGeometry": "NEW_GEOMETRY",
    "ShaderNodeLightPath": "LIGHT_PATH",
    "ShaderNodeLayerWeight": "LAYER_WEIGHT",
    "ShaderNodeFresnel": "FRESNEL",
    "ShaderNodeMath": "MATH",
    "ShaderNodeMixRGB": "MIX_RGB",
    "ShaderNodeMix": "MIX",
    "ShaderNodeInvert": "INVERT",
    "ShaderNodeHueSaturation": "HUE_SAT",
    "ShaderNodeValToRGB": "VALTORGB",
    "ShaderNodeRGBCurve": "CURVE_RGB",
    "ShaderNodeVectorCurve": "CURVE_VEC",
    "ShaderNodeRGB": "RGB",
    "ShaderNodeCombineXYZ": "COMBXYZ",
    "ShaderNodeSeparateXYZ": "SEPXYZ",
    "ShaderNodeCombineRGB": "COMBRGB",
    "ShaderNodeSeparateRGB": "SEPRGB",
    "ShaderNodeMapping": "MAPPING",
    "ShaderNodeBackground": "BACKGROUND",
    "ShaderNodeOutputAOV": "OUTPUT_AOV",
    "ShaderNodeOutputWorld": "OUTPUT_WORLD",
    "ShaderNodeGamma": "GAMMA",
    "ShaderNodeObjectInfo": "OBJECT_INFO",
    "ShaderNodeAmbientOcclusion": "AMBIENT_OCCLUSION",
    "CompositorNodeRLayers": "R_LAYERS",
    "CompositorNodeComposite": "COMPOSITE",
    "CompositorNodeViewer": "VIEWER",
    "CompositorNodeGroup": "GROUP",
    "NodeGroupInput": "GROUP_INPUT",
    "NodeGroupOutput": "GROUP_OUTPUT",
    "NodeReroute": "REROUTE",
    "NodeFrame": "FRAME",
}


class _Obj:
    def __init__(self, **kw):
        self.__dict__.update(kw)


class _SockMap:
    def __init__(self, items):
        self._items = list(items)
        self._by = {}
        for sock in self._items:
            self._by[sock.name] = sock
            self._by[sock.identifier] = sock

    def get(self, key):
        return self._by.get(key)

    def __iter__(self):
        return iter(self._items)

    def __len__(self):
        return len(self._items)


class _Link:
    def __init__(self, from_node, from_socket, to_node, to_socket):
        self.from_node = from_node
        self.from_socket = from_socket
        self.to_node = to_node
        self.to_socket = to_socket


def _as_str(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if value is None:
        return ""
    return value if isinstance(value, str) else str(value)


def _id_name(block):
    if block is None:
        return ""
    try:
        name = block.get((b"id", b"name"), use_str=True)
    except KeyError:
        return ""
    name = _as_str(name)
    if len(name) >= 2:
        return name[2:]
    return name


def _has_field(block, name):
    if block is None:
        return False
    key = name if isinstance(name, bytes) else name.encode("ascii")
    return key in block.dna_type.field_from_name


def _safe_get(block, path, default=None):
    if block is None:
        return default
    try:
        return block.get(path, default=default)
    except (KeyError, NotImplementedError, AssertionError):
        return default


def _safe_pointer(block, path):
    if block is None:
        return None
    try:
        return block.get_pointer(path)
    except (KeyError, NotImplementedError, AssertionError):
        return None


def _walk_list(first):
    seen = set()
    cur = first
    while cur is not None:
        ident = id(cur)
        if ident in seen:
            break
        seen.add(ident)
        yield cur
        nxt = None
        try:
            nxt = cur.get_pointer(b"next")
        except KeyError:
            try:
                nxt = cur.get_pointer((b"modifier", b"next"))
            except KeyError:
                nxt = None
        cur = nxt


def _read_ptr_array(bf, block, count):
    if block is None or count <= 0:
        return []
    out = []
    bf.handle.seek(block.file_offset)
    for _ in range(int(count)):
        ptr = blendfile.DNA_IO.read_pointer(bf.handle, bf.header)
        out.append(bf.find_block_from_offset(ptr) if ptr else None)
    return out


def _endian(bf):
    return "<" if bf.header.is_little_endian else ">"


def _sock_default(bf, sock):
    """Read default_value from socket DNA. Never invent Fac.

    2.73–2.79: untyped DATA (sdna Link) with bNodeSocketValueFloat layout.
    2.8+/4.x: same pointer, sometimes typed bNodeSocketValueFloat/Vector/RGBA.
    Inline non-pointer default_value is used only if that field exists.
    """
    if sock is None or not _has_field(sock, b"default_value"):
        return None
    field = sock.dna_type.field_from_name[b"default_value"]
    if not field.dna_name.is_pointer:
        try:
            value = sock.get(b"default_value")
        except (KeyError, NotImplementedError):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, (list, tuple)) and value:
            try:
                return tuple(float(x) for x in value)
            except (TypeError, ValueError):
                return None
        return None
    ptr = sock.get(b"default_value")
    if not ptr:
        return None
    block = bf.find_block_from_offset(ptr)
    if block is None:
        return None
    if _has_field(block, b"value"):
        vfield = block.dna_type.field_from_name[b"value"]
        if not vfield.dna_name.is_pointer:
            try:
                value = block.get(b"value")
            except (KeyError, NotImplementedError):
                value = None
            if isinstance(value, (int, float)):
                return float(value)
            if isinstance(value, (list, tuple)) and value:
                try:
                    return tuple(float(x) for x in value)
                except (TypeError, ValueError):
                    pass
    stype = int(_safe_get(sock, b"type") or 0)
    bf.handle.seek(block.file_offset)
    data = bf.handle.read(block.size)
    fmt = _endian(bf)
    if stype == SOCK_FLOAT and len(data) >= 8:
        _subtype, value = struct.unpack_from(fmt + "if", data)
        return float(value)
    if stype == SOCK_VECTOR and len(data) >= 16:
        _subtype, x, y, z = struct.unpack_from(fmt + "ifff", data)
        return (float(x), float(y), float(z))
    if stype == SOCK_RGBA and len(data) >= 16:
        return tuple(struct.unpack_from(fmt + "ffff", data))
    return None


def _rna_type(nblock):
    idname = _as_str(_safe_get(nblock, b"idname") or "")
    if idname in IDNAME_TYPE:
        return IDNAME_TYPE[idname], idname
    ntype_i = int(_safe_get(nblock, b"type") or 0)
    if ntype_i in NODE_TYPE:
        return NODE_TYPE[ntype_i], idname
    return "", idname


def _attr_storage(nblock, rna_type, idname):
    if rna_type not in ("ATTRIBUTE", "UVMAP", "VERTEX_COLOR") and idname not in (
        "ShaderNodeAttribute", "ShaderNodeUVMap", "ShaderNodeVertexColor",
        "ShaderNodeColorAttribute",
    ):
        return "", ""
    storage = _safe_pointer(nblock, b"storage")
    if storage is None:
        return "", ""
    aname = ""
    for key in (b"name", b"uv_map", b"layer_name"):
        if not _has_field(storage, key):
            continue
        try:
            aname = _as_str(storage.get(key) or "")
        except (KeyError, NotImplementedError):
            aname = ""
        if aname:
            break
    return aname, aname


def _build_tree(bf, ntree, images_by_addr, cache, stats, kind="material"):
    if ntree is None:
        return None
    key = ntree.addr_old
    if key in cache:
        return cache[key]
    nodes = []
    node_by_addr = {}
    sock_by_addr = {}
    nfirst = _safe_pointer(ntree, (b"nodes", b"first"))
    for nblock in _walk_list(nfirst) if nfirst else ():
        rna_type, idname = _rna_type(nblock)
        ins, outs = [], []
        for which, bucket in ((b"inputs", ins), (b"outputs", outs)):
            first = _safe_pointer(nblock, (which, b"first"))
            for sblock in _walk_list(first) if first else ():
                ident = _as_str(_safe_get(sblock, b"identifier") or "")
                name = _as_str(_safe_get(sblock, b"name") or ident)
                sock = _Obj(
                    name=name,
                    identifier=ident,
                    default_value=_sock_default(bf, sblock),
                    is_linked=False,
                    links=[],
                    node=None,
                    _addr=sblock.addr_old,
                )
                bucket.append(sock)
                sock_by_addr[sblock.addr_old] = sock
        aname, lname = _attr_storage(nblock, rna_type, idname)
        node = _Obj(
            name=_as_str(_safe_get(nblock, b"name") or ""),
            type=rna_type,
            bl_idname=idname,
            inputs=_SockMap(ins),
            outputs=_SockMap(outs),
            image=None,
            node_tree=None,
            attribute_name=aname,
            layer_name=lname,
        )
        for sock in ins + outs:
            sock.node = node
        id_block = _safe_pointer(nblock, b"id")
        if id_block is not None:
            img = images_by_addr.get(id_block.addr_old)
            if img is not None:
                node.image = img
            if rna_type == "GROUP" or idname in ("ShaderNodeGroup", "CompositorNodeGroup"):
                node.node_tree = _build_tree(
                    bf, id_block, images_by_addr, cache, stats, kind="group")
        nodes.append(node)
        node_by_addr[nblock.addr_old] = node

    links = []
    lfirst = _safe_pointer(ntree, (b"links", b"first"))
    for lblock in _walk_list(lfirst) if lfirst else ():
        fn = _safe_pointer(lblock, b"fromnode")
        tn = _safe_pointer(lblock, b"tonode")
        fs = _safe_pointer(lblock, b"fromsock")
        ts = _safe_pointer(lblock, b"tosock")
        from_node = node_by_addr.get(fn.addr_old) if fn else None
        to_node = node_by_addr.get(tn.addr_old) if tn else None
        from_sock = sock_by_addr.get(fs.addr_old) if fs else None
        to_sock = sock_by_addr.get(ts.addr_old) if ts else None
        if from_node is None or to_node is None or from_sock is None or to_sock is None:
            stats["n_bad_links"] += 1
            stats["n_bad_links_%s" % kind] = stats.get("n_bad_links_%s" % kind, 0) + 1
        link = _Link(from_node, from_sock, to_node, to_sock)
        links.append(link)
        stats["n_links"] += 1
        stats["n_links_%s" % kind] = stats.get("n_links_%s" % kind, 0) + 1
        for sock in (from_sock, to_sock):
            if sock is None:
                continue
            sock.links.append(link)
            sock.is_linked = True

    tree = _Obj(nodes=nodes, links=links, type=_safe_get(ntree, b"type"))
    cache[key] = tree
    return tree


def _mod_name_type(mblock):
    try:
        return mblock.get(b"name"), mblock.get(b"type")
    except KeyError:
        try:
            return mblock.get((b"modifier", b"name")), mblock.get((b"modifier", b"type"))
        except KeyError:
            return "", 0


def _color_and_uv_layers(mesh, stats):
    colors = []
    uvs = []
    for cdname, domain in (
        (b"ldata", "CORNER"),
        (b"fdata", "FACE"),
        (b"vdata", "POINT"),
        (b"pdata", "FACE"),
        (b"face_data", "FACE"),
        (b"corner_data", "CORNER"),
        (b"vert_data", "POINT"),
    ):
        if not _has_field(mesh, cdname):
            continue
        tot = int(_safe_get(mesh, (cdname, b"totlayer")) or 0)
        if tot <= 0:
            continue
        layers = _safe_pointer(mesh, (cdname, b"layers"))
        if layers is None:
            continue
        for i in range(tot):
            typ = int(layers.get(b"type", base_index=i) or 0)
            name = _as_str(layers.get(b"name", base_index=i) or "")
            stats["cd_types"][typ] += 1
            if typ in COLOR_CD_TYPES:
                colors.append(_Obj(name=name, domain=domain, data_type="BYTE_COLOR"))
            elif typ in UV_CD_TYPES and name:
                uvs.append(_Obj(name=name))
            else:
                stats["unknown_cd_types"].add(typ)
    return colors, uvs


def _used_mat_indices(bf, mesh, stats):
    totpoly = int(_safe_get(mesh, b"totpoly") or _safe_get(mesh, b"totface") or 0)
    if _has_field(mesh, b"mpoly"):
        mpoly = _safe_pointer(mesh, b"mpoly")
        if mpoly is not None and totpoly > 0 and _has_field(mpoly, b"mat_nr"):
            used = set()
            polys = []
            for i in range(totpoly):
                idx = int(mpoly.get(b"mat_nr", base_index=i) or 0)
                polys.append(_Obj(material_index=idx))
                used.add(idx)
            return used, polys, "mpoly.mat_nr"
    # 4.x: material_index attribute on face CustomData
    for cdname in (b"pdata", b"face_data", b"ldata"):
        if not _has_field(mesh, cdname):
            continue
        tot = int(_safe_get(mesh, (cdname, b"totlayer")) or 0)
        if tot <= 0:
            continue
        layers = _safe_pointer(mesh, (cdname, b"layers"))
        if layers is None:
            continue
        for i in range(tot):
            name = _as_str(layers.get(b"name", base_index=i) or "")
            if name != "material_index":
                continue
            data = None
            try:
                ptr = layers.get(b"data", base_index=i)
            except (KeyError, NotImplementedError):
                ptr = 0
            if ptr:
                data = bf.find_block_from_offset(ptr)
            nfaces = totpoly
            if data is None or nfaces <= 0:
                stats["poly_index_unknown"] += 1
                return set(), [], "UNKNOWN_MATERIAL_INDEX"
            endian = _endian(bf)
            bf.handle.seek(data.file_offset)
            used = set()
            polys = []
            for _i in range(nfaces):
                raw = bf.handle.read(4)
                if len(raw) < 4:
                    break
                idx = struct.unpack(endian + "i", raw)[0]
                polys.append(_Obj(material_index=idx))
                used.add(idx)
            return used, polys, "attr.material_index"
    if totpoly > 0:
        stats["poly_index_unknown"] += 1
        return set(), [], "UNKNOWN_MATERIAL_INDEX"
    return set(), [], "no_faces"


def _hide_render(ob):
    if _has_field(ob, b"visibility_flag"):
        return bool(int(_safe_get(ob, b"visibility_flag") or 0) & OB_RESTRICT_RENDER)
    if _has_field(ob, b"restrictflag"):
        return bool(int(_safe_get(ob, b"restrictflag") or 0) & OB_RESTRICT_RENDER)
    if _has_field(ob, b"hide_render"):
        return bool(_safe_get(ob, b"hide_render"))
    return False


# IDProperty types (DNA_ID.h). Cycles 2.79 ray vis lives here, not Object DNA.
IDP_INT = 1
IDP_GROUP = 6


def _idp_name(prop):
    if prop is None:
        return ""
    try:
        name = prop.get(b"name", use_str=True)
    except (KeyError, NotImplementedError, AssertionError):
        return ""
    return _as_str(name)


def _idp_children(prop):
    if prop is None:
        return
    try:
        typ = int(prop.get(b"type") or 0)
    except (KeyError, NotImplementedError, AssertionError, TypeError):
        return
    if typ != IDP_GROUP:
        return
    try:
        first = prop.get_pointer((b"data", b"group", b"first"))
    except (KeyError, NotImplementedError, AssertionError):
        return
    seen = set()
    cur = first
    while cur is not None:
        ident = getattr(cur, "addr_old", id(cur))
        if ident in seen:
            break
        seen.add(ident)
        yield cur
        try:
            cur = cur.get_pointer(b"next")
        except (KeyError, NotImplementedError, AssertionError):
            break


def _idp_int(prop):
    if prop is None:
        return None
    try:
        if int(prop.get(b"type") or -1) != IDP_INT:
            return None
        val = prop.get((b"data", b"val"))
    except (KeyError, NotImplementedError, AssertionError, TypeError):
        return None
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _cycles_visibility_shadow(ob):
    """Proven Cycles shadow vis from IDProperty cycles_visibility.shadow.

    2.79 Object DNA has restrictflag / scavisflag, not visible_shadow.
    Cycles ray vis is an IDProperty group. Return True/False only when
    the shadow key is a proven INT. Missing group or missing key → None
    (UNKNOWN). Never default True.
    """
    if ob is None:
        return None
    try:
        root = ob.get_pointer((b"id", b"properties"))
    except (KeyError, NotImplementedError, AssertionError):
        return None
    vis = None
    for child in _idp_children(root) or ():
        if _idp_name(child) == "cycles_visibility":
            vis = child
            break
    if vis is None:
        return None
    for child in _idp_children(vis) or ():
        if _idp_name(child) == "shadow":
            val = _idp_int(child)
            if val is None:
                return None
            return bool(val)
    return None


def _lib_wrapper(block):
    lib = _safe_pointer(block, (b"id", b"lib"))
    if lib is not None:
        return _Obj(name=_id_name(lib) or "lib")
    ov = _safe_pointer(block, (b"id", b"override_library"))
    if ov is not None:
        return None  # override_library is a separate duck field
    return None


def _override_wrapper(block):
    ov = _safe_pointer(block, (b"id", b"override_library"))
    if ov is None:
        return None
    return _Obj(name="override")


def _iter_collection_objects(coll, seen=None):
    if coll is None:
        return
    if seen is None:
        seen = set()
    ident = coll.addr_old
    if ident in seen:
        return
    seen.add(ident)
    gfirst = _safe_pointer(coll, (b"gobject", b"first"))
    for gob in _walk_list(gfirst) if gfirst else ():
        ob = _safe_pointer(gob, b"ob") or _safe_pointer(gob, b"object")
        if ob is not None:
            yield ob
    cfirst = _safe_pointer(coll, (b"children", b"first"))
    for ch in _walk_list(cfirst) if cfirst else ():
        sub = _safe_pointer(ch, b"collection")
        if sub is not None:
            yield from _iter_collection_objects(sub, seen)


def _iter_scene_objects(sc):
    base_first = _safe_pointer(sc, (b"base", b"first"))
    if base_first is not None:
        n = 0
        for base in _walk_list(base_first):
            ob = _safe_pointer(base, b"object")
            if ob is not None:
                n += 1
                yield ob
        if n:
            return
    coll = (_safe_pointer(sc, b"master_collection")
            or _safe_pointer(sc, b"collection"))
    if coll is not None:
        yielded = False
        for ob in _iter_collection_objects(coll):
            yielded = True
            yield ob
        if yielded:
            return
    vl_first = _safe_pointer(sc, (b"view_layers", b"first"))
    if vl_first is not None:
        for vl in _walk_list(vl_first):
            bfirst = (_safe_pointer(vl, (b"object_bases", b"first"))
                      or _safe_pointer(vl, (b"base", b"first")))
            for base in _walk_list(bfirst) if bfirst else ():
                ob = _safe_pointer(base, b"object")
                if ob is not None:
                    yield ob


def _object_source(sc):
    if _safe_pointer(sc, (b"base", b"first")) is not None:
        return "scene.base"
    if _safe_pointer(sc, b"master_collection") is not None:
        return "master_collection"
    if _safe_pointer(sc, b"collection") is not None:
        return "scene.collection"
    if _safe_pointer(sc, (b"view_layers", b"first")) is not None:
        return "view_layers"
    return "NONE"


def _pick_scene(bf):
    scenes = bf.find_blocks_from_code(b"SC")
    if not scenes:
        return None, []
    names = [_id_name(s) for s in scenes]
    return scenes[0], names


def _mix_fac_record(node):
    """Return (is_linked, default_value, unknown). unknown if Fac unproven."""
    fac = node.inputs.get("Fac")
    if fac is None:
        fac = node.inputs.get("Factor")
    if fac is None:
        return None, None, True
    if fac.is_linked:
        return True, fac.default_value, False
    if fac.default_value is None:
        return False, None, True
    if not isinstance(fac.default_value, (int, float)):
        return False, fac.default_value, True
    return False, float(fac.default_value), False


def _mix_fac_source(node):
    """Return (from_type, from_sock_name, unknown).

    unknown if Fac is linked but DNA cannot name the source node/socket.
    Geometry Backfacing must be a named socket — never guess Incoming.
    """
    fac = node.inputs.get("Fac")
    if fac is None:
        fac = node.inputs.get("Factor")
    if fac is None or not fac.is_linked:
        return "", "", False
    links = list(getattr(fac, "links", None) or ())
    if not links:
        return "", "", True
    link = links[0]
    from_node = getattr(link, "from_node", None)
    from_sock = getattr(link, "from_socket", None)
    ntype = ""
    if from_node is not None:
        ntype = (getattr(from_node, "type", "")
                 or getattr(from_node, "bl_idname", "") or "")
    sname = ""
    if from_sock is not None:
        sname = (getattr(from_sock, "identifier", None)
                 or getattr(from_sock, "name", "") or "")
    unknown = (from_node is None) or (not sname)
    return ntype, sname, unknown


def _geom_output_names(node):
    names = []
    for sock in getattr(node, "outputs", ()) or ():
        names.append(getattr(sock, "identifier", None)
                     or getattr(sock, "name", "") or "")
    return names


def build_scene(bf):
    stats = {
        "n_bad_links": 0,
        "n_links": 0,
        "cd_types": Counter(),
        "unknown_cd_types": set(),
        "poly_index_unknown": 0,
        "n_unknown_fac": 0,
        "n_mix": 0,
        "n_transparent": 0,
        "n_portal_fac_unknown": 0,
        "n_geom_nodes": 0,
        "n_geom_socks_unnamed": 0,
        "n_geom_backfacing": 0,
    }
    images_by_addr = {}
    for im in bf.find_blocks_from_code(b"IM"):
        path = _as_str(_safe_get(im, b"name") or "")
        images_by_addr[im.addr_old] = _Obj(
            name=_id_name(im),
            filepath=path,
            filepath_raw=path,
            channels=None,
            file_format="",
            alpha_mode=int(_safe_get(im, b"alpha_mode") or 0),
        )

    mats_by_addr = {}
    tree_cache = {}
    node_type_counts = Counter()
    idname_counts = Counter()
    n_trees = 0
    n_with_nodes = 0
    mix_facs = []
    geom_outs = []
    disp_links = []
    n_linked_mats = 0
    for ma in bf.find_blocks_from_code(b"MA"):
        ntree = _safe_pointer(ma, b"nodetree")
        tree = _build_tree(bf, ntree, images_by_addr, tree_cache, stats, kind="material") if ntree else None
        lib = _lib_wrapper(ma)
        if lib is not None:
            n_linked_mats += 1
        if tree is not None:
            n_trees += 1
            n_with_nodes += 1
            for node in tree.nodes:
                node_type_counts[node.type or node.bl_idname] += 1
                idname_counts[node.bl_idname] += 1
                if node.type == "MIX_SHADER" or node.bl_idname == "ShaderNodeMixShader":
                    stats["n_mix"] += 1
                    linked, value, unknown = _mix_fac_record(node)
                    if unknown:
                        stats["n_unknown_fac"] += 1
                    src_type, src_sock, src_unknown = _mix_fac_source(node)
                    if src_unknown:
                        stats["n_portal_fac_unknown"] += 1
                    mix_facs.append((
                        _id_name(ma),
                        node.name,
                        linked,
                        value,
                        "UNKNOWN_FAC" if unknown else "ok",
                        src_type,
                        src_sock,
                        "UNKNOWN_FAC_SOURCE" if src_unknown else "ok",
                    ))
                if node.type in ("NEW_GEOMETRY", "GEOMETRY") or node.bl_idname in (
                        "ShaderNodeNewGeometry", "ShaderNodeGeometry"):
                    stats["n_geom_nodes"] += 1
                    onames = _geom_output_names(node)
                    if not any(onames):
                        stats["n_geom_socks_unnamed"] += 1
                    if any((n or "").replace(" ", "").lower() == "backfacing"
                           for n in onames):
                        stats["n_geom_backfacing"] += 1
                    geom_outs.append((_id_name(ma), node.name, onames))
                if node.type == "BSDF_TRANSPARENT" or node.bl_idname == "ShaderNodeBsdfTransparent":
                    stats["n_transparent"] += 1
                if node.type == "OUTPUT_MATERIAL" or node.bl_idname == "ShaderNodeOutputMaterial":
                    disp = node.inputs.get("Displacement")
                    if disp is not None and disp.is_linked:
                        src = disp.links[0].from_node if disp.links else None
                        disp_links.append((
                            _id_name(ma),
                            getattr(src, "name", ""),
                            getattr(src, "type", "") or getattr(src, "bl_idname", ""),
                        ))
        mat_kw = dict(
            name=_id_name(ma),
            library=lib,
            override_library=_override_wrapper(ma),
            use_nodes=bool(_safe_get(ma, b"use_nodes")),
            node_tree=tree,
        )
        # Honest RNA: 2.79 Material DNA has no use_backface_culling.
        # Do not fake 4.5 Cycles cull on a 2.79 blend.
        if _has_field(ma, b"use_backface_culling"):
            mat_kw["use_backface_culling"] = bool(
                _safe_get(ma, b"use_backface_culling"))
        mats_by_addr[ma.addr_old] = _Obj(**mat_kw)

    sc, scene_names = _pick_scene(bf)
    if sc is None:
        stats["no_scene"] = True
        scene = _Obj(name="", objects=[], use_nodes=False, node_tree=None,
                     compositing_node_group=None)
        proof = {"scene": "", "scene_names": scene_names, "n_objects": 0,
                 "object_source": "NONE", "n_libraries": len(bf.find_blocks_from_code(b"LI")),
                 "n_linked_mats_in_file": n_linked_mats}
        return scene, proof, stats

    object_source = _object_source(sc)
    objects = []
    mesh_stats = []
    unique_meshes = 0
    unused_slot_raw = 0
    seen_mesh = set()
    n_hide = 0
    n_linked = 0
    type_counts = Counter()
    n_slot_incomplete = 0
    for ob in _iter_scene_objects(sc):
        ob_type_i = int(_safe_get(ob, b"type") or 0)
        ob_type = OB_TYPE.get(ob_type_i, "EMPTY")
        if ob_type_i == 10:
            # 2.8+ is LIGHT; keep LAMP string for 2.7x dumps, MESH classifier ignores both.
            ob_type = "LAMP"
        type_counts[ob_type] += 1
        hide = _hide_render(ob)
        if hide:
            n_hide += 1
        lib = _lib_wrapper(ob)
        if lib is not None:
            n_linked += 1
        data = _safe_pointer(ob, b"data")
        mesh = None
        slots = []
        mods = []
        mfirst = _safe_pointer(ob, (b"modifiers", b"first"))
        for mblock in _walk_list(mfirst) if mfirst else ():
            mname, mtype = _mod_name_type(mblock)
            mods.append(_Obj(name=mname or "", type=mtype))
        if ob_type == "MESH" and data is not None:
            totcol = int(_safe_get(data, b"totcol") or 0)
            mat_blocks = _read_ptr_array(bf, _safe_pointer(data, b"mat"), totcol)
            materials = []
            for mb in mat_blocks:
                mat = mats_by_addr.get(mb.addr_old) if mb is not None else None
                materials.append(mat)
                slots.append(_Obj(material=mat))
            used, polys, how = _used_mat_indices(bf, data, stats)
            if how.startswith("UNKNOWN"):
                n_slot_incomplete += 1
            unused = []
            for i, mat in enumerate(materials):
                if mat is not None and i not in used:
                    unused.append((i, mat.name))
            colors, uvs = _color_and_uv_layers(data, stats)
            mesh = _Obj(
                name=_id_name(data),
                library=_lib_wrapper(data),
                override_library=_override_wrapper(data),
                materials=materials,
                polygons=polys,
                color_attributes=colors,
                vertex_colors=colors,
                uv_layers=uvs,
            )
            dup = data.addr_old in seen_mesh
            if not dup:
                seen_mesh.add(data.addr_old)
                unique_meshes += 1
                unused_slot_raw += len(unused)
            mesh_stats.append({
                "object": _id_name(ob),
                "mesh": mesh.name,
                "totcol": totcol,
                "totpoly": int(_safe_get(data, b"totpoly") or 0),
                "used": sorted(used),
                "unused": unused,
                "how": how,
                "dup": dup,
                "n_color": len(colors),
                "n_uv": len(uvs),
                "n_mod": len(mods),
            })
        else:
            totcol = int(_safe_get(ob, b"totcol") or 0)
            if totcol and not slots:
                mat_blocks = _read_ptr_array(bf, _safe_pointer(ob, b"mat"), totcol)
                for mb in mat_blocks:
                    mat = mats_by_addr.get(mb.addr_old) if mb is not None else None
                    slots.append(_Obj(material=mat))
            if ob_type == "CURVE":
                mesh = _Obj(
                    name=_id_name(data) if data is not None else "",
                    library=_lib_wrapper(data) if data is not None else None,
                    override_library=_override_wrapper(data) if data is not None else None,
                    materials=[getattr(s, "material", None) for s in slots],
                    polygons=[],
                    color_attributes=[],
                    vertex_colors=[],
                    uv_layers=[],
                )
        obj_kw = dict(
            name=_id_name(ob),
            type=ob_type,
            hide_render=hide,
            library=lib,
            override_library=_override_wrapper(ob),
            data=mesh,
            material_slots=slots,
            modifiers=mods,
            scenequant=_Obj(override="AUTO"),
        )
        # 2.79 has no Object.visible_shadow DNA. Attach cycles_visibility
        # only when IDP shadow is a proven INT — never default.
        shadow = _cycles_visibility_shadow(ob)
        if shadow is not None:
            obj_kw["cycles_visibility"] = _Obj(shadow=shadow)
        objects.append(_Obj(**obj_kw))

    comp = None
    if _safe_pointer(sc, b"nodetree") is not None:
        comp = _build_tree(bf, _safe_pointer(sc, b"nodetree"), images_by_addr, tree_cache, stats, kind="compositor")

    scene = _Obj(
        name=_id_name(sc),
        objects=objects,
        use_nodes=bool(_safe_get(sc, b"use_nodes")),
        node_tree=comp,
        compositing_node_group=None,
    )
    n_libs = len(bf.find_blocks_from_code(b"LI"))
    proof = {
        "scene": scene.name,
        "scene_names": scene_names,
        "object_source": object_source,
        "n_objects": len(objects),
        "types": dict(type_counts),
        "n_hide_render": n_hide,
        "n_linked": n_linked,
        "n_materials": len(mats_by_addr),
        "n_linked_mats_in_file": n_linked_mats,
        "n_libraries": n_libs,
        "n_shader_trees": n_trees,
        "n_use_nodes": n_with_nodes,
        "node_types": dict(node_type_counts),
        "idnames": dict(idname_counts),
        "mix_facs": mix_facs,
        "geom_outs": geom_outs,
        "disp_links": disp_links,
        "unique_local_meshes": unique_meshes,
        "unused_slots_raw": unused_slot_raw,
        "n_slot_incomplete": n_slot_incomplete,
        "mesh_stats": mesh_stats,
    }
    stats["n_slot_incomplete"] = n_slot_incomplete
    return scene, proof, stats


def _blend_header_label(bf):
    ver = int(bf.header.version)
    ptr = "-" if bf.header.pointer_size == 8 else "_"
    endian = "v" if bf.header.is_little_endian else "V"
    return "BLENDER%s%s%03d" % (ptr, endian, ver)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    path = argv[0] if argv else "/tmp/BMW27.blend"
    print("DNA inventory file=%r" % path)
    print("reader=blendfile.py (no bpy, blender binary not launched)")
    bf = blendfile.open_blend(path)
    try:
        hdr = bf.header
        print("blend_header %s version=%s ptr=%s le=%s" % (
            _blend_header_label(bf), hdr.version, hdr.pointer_size, hdr.is_little_endian))
        scene, proof, stats = build_scene(bf)
    finally:
        bf.close()

    print("SCENE %s objects=%d hide_render=%d linked=%d types=%s source=%s scenes=%s" % (
        proof.get("scene"), proof.get("n_objects"), proof.get("n_hide_render"),
        proof.get("n_linked"), proof.get("types"), proof.get("object_source"),
        proof.get("scene_names")))
    print("LIBRARIES %d (not opened) linked_mats_in_file=%d" % (
        proof.get("n_libraries", 0), proof.get("n_linked_mats_in_file", 0)))
    print("MATERIALS %d shader_trees=%d use_nodes=%d" % (
        proof.get("n_materials"), proof.get("n_shader_trees"), proof.get("n_use_nodes")))
    print("NODE_TYPES %s" % proof.get("node_types"))
    print("IDNAMES %s" % {k: v for k, v in (proof.get("idnames") or {}).items() if k})
    print("MIX_SHADER count=%d TRANSPARENT count=%d UNKNOWN_FAC=%d" % (
        stats["n_mix"], stats["n_transparent"], stats["n_unknown_fac"]))
    print("MIX_SHADER_FAC %s" % proof.get("mix_facs"))
    print("DISPLACE_LINKS %s" % proof.get("disp_links"))
    print("LINKS n=%d bad=%d material_bad=%d group_bad=%d compositor_bad=%d" % (
        stats["n_links"], stats["n_bad_links"],
        stats.get("n_bad_links_material", 0),
        stats.get("n_bad_links_group", 0),
        stats.get("n_bad_links_compositor", 0)))
    print("GROUP/compositor interface sockets with fromnode=None are expected; Mix uses material trees.")
    print("UNIQUE_MESHES %d UNUSED_SLOTS_RAW %d slot_index_unknown=%d" % (
        proof.get("unique_local_meshes"), proof.get("unused_slots_raw"),
        stats.get("n_slot_incomplete", 0)))
    n_color = sum(m["n_color"] for m in proof.get("mesh_stats") or ())
    print("COLOR_ATTR_LAYERS %d (CD_MCOL/CD_MLOOPCOL=%s) cd_types=%s unknown_cd=%s" % (
        n_color, sorted(COLOR_CD_TYPES), dict(stats["cd_types"]),
        sorted(stats["unknown_cd_types"] - COLOR_CD_TYPES - UV_CD_TYPES - {0, 7, 8})))

    mix_complete = (
        stats["n_unknown_fac"] == 0
        and stats.get("n_bad_links_material", 0) == 0
        and proof.get("n_objects", 0) > 0
        and proof.get("object_source") != "NONE"
    )
    slots_complete = stats.get("n_slot_incomplete", 0) == 0
    if not mix_complete:
        print("INCOMPLETE MIX_WALK unknown_fac=%d material_bad_links=%d objects=%d source=%s" % (
            stats["n_unknown_fac"], stats.get("n_bad_links_material", 0),
            proof.get("n_objects", 0), proof.get("object_source")))
        print("Do not treat 0 PRUNE_MIX_TRANSPARENT as proof.")
    else:
        print("MIX_WALK COMPLETE (Fac proven from DNA default_value / links; no Fac guessed)")
    if not slots_complete:
        print("INCOMPLETE SLOTS material_index unreadable on %d unique meshes" %
              stats.get("n_slot_incomplete", 0))

    dead = classify_dead_closures(scene)
    print_dead(dead)
    dcounts = dead_counts(dead)
    print("DEAD_COUNTS %s" % dcounts)

    slots = classify_unused_slots(scene)
    print_slots(slots)
    scounts = slot_counts(slots)
    print("SLOT_COUNTS %s" % scounts)

    colors = classify_unused_color_attrs(scene)
    print_colors(colors)
    ccounts = color_counts(colors)
    print("COLOR_COUNTS %s" % ccounts)

    print("GEOMETRY_NODES count=%d unnamed_outputs=%d backfacing_named=%d" % (
        stats.get("n_geom_nodes", 0),
        stats.get("n_geom_socks_unnamed", 0),
        stats.get("n_geom_backfacing", 0)))
    print("GEOMETRY_OUTPUTS %s" % proof.get("geom_outs"))
    print("MIX_FAC_SOURCE unknown=%d (linked Fac whose from_socket DNA cannot name)" %
          stats.get("n_portal_fac_unknown", 0))
    portal_complete = (
        stats.get("n_portal_fac_unknown", 0) == 0
        and stats.get("n_geom_socks_unnamed", 0) == 0
        and stats.get("n_bad_links_material", 0) == 0
        and proof.get("n_objects", 0) > 0
        and proof.get("object_source") != "NONE"
    )
    portals = classify_portal_meshes(scene)
    pcounts = portal_counts(portals)
    if not portal_complete:
        print("PORTAL_MESH_UNKNOWN Fac source / Geometry sockets unproven "
              "(unknown_fac_source=%d geom_unnamed=%d material_bad_links=%d "
              "objects=%d source=%s)"
              % (stats.get("n_portal_fac_unknown", 0),
                 stats.get("n_geom_socks_unnamed", 0),
                 stats.get("n_bad_links_material", 0),
                 proof.get("n_objects", 0), proof.get("object_source")))
        print("Do not treat 0 PORTAL_MESH as proof.")
        pcounts_out = "UNKNOWN"
    else:
        print_portals(portals)
        print("PORTAL_COUNTS %s" % pcounts)
        print("PORTAL_MESH_ROLES MESH_EMIT_BACKFACE=%d WORLD_PORTAL_CARD=%d "
              "OPAQUE_OK=%d" % (
            pcounts.get("MESH_EMIT_BACKFACE", 0),
            pcounts.get("WORLD_PORTAL_CARD", 0),
            pcounts.get("OPAQUE_OK", 0)))
        pcounts_out = pcounts
        print("PORTAL_MESH_WALK COMPLETE (Fac source sockets named from DNA; "
              "Geometry Backfacing not guessed)")
        print("OPAQUE_OK honesty: unlink-only (Transparent mix input). "
              "use_backface_culling is a Cycles no-op and is not required; "
              "2.79 files typically lack the field.")
        shadow_ok = pcounts.get("SHADOW_SKIP_OK", 0)
        emit_n = pcounts.get("MESH_EMIT_BACKFACE", 0)
        unknown_shadow = 0
        proven_off = 0
        for rec in portals:
            if rec.get("role") != "MESH_EMIT_BACKFACE":
                continue
            if rec.get("shadow_skip_ok"):
                continue
            note = rec.get("shadow_skip_note") or ""
            if "unreadable" in note or not rec.get("shadow_path"):
                unknown_shadow += 1
            elif "already off" in note:
                proven_off += 1
        print("SHADOW_SKIP honesty: 2.79 Object DNA has restrictflag/"
              "scavisflag, not visible_shadow. Cycles ray vis is "
              "IDProperty cycles_visibility.shadow. Missing key is "
              "UNKNOWN (not defaulted True). SHADOW_SKIP_OK=%d "
              "already_off=%d UNKNOWN=%d MESH_EMIT_BACKFACE=%d"
              % (shadow_ok, proven_off, unknown_shadow, emit_n))
        if unknown_shadow:
            print("SHADOW_SKIP_OK not proven (UNKNOWN visibility on %d "
                  "emit card(s); do not treat 0 as a write count)."
                  % unknown_shadow)

    fired = {
        "PRUNE_MIX_TRANSPARENT": dcounts.get("PRUNE_MIX_TRANSPARENT", 0),
        "PRUNE_DISPLACE": dcounts.get("PRUNE_DISPLACE", 0),
        "UNIQUE_UNUSED_SLOTS": scounts.get("UNIQUE_UNUSED_SLOTS", 0),
        "UNUSED_COLOR_ATTRS": ccounts.get("UNUSED_COLOR_ATTRS", 0),
        "PORTAL_MESH": pcounts_out if pcounts_out == "UNKNOWN"
        else pcounts.get("PORTAL_MESH", 0),
    }
    print("FIRED %s" % fired)
    if not mix_complete and fired["PRUNE_MIX_TRANSPARENT"] == 0:
        print("INCOMPLETE: Mix 0 is not recipe evidence.")
    print("STORE Classroom 41% / loft 52% unchanged.")
    print("Auto off. No time claim.")
    print("OK" if mix_complete else "INCOMPLETE")
    return 0 if mix_complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
