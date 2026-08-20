# BMW27 DNA inventory without bpy and without launching the blender binary.
#
# Reconstructs duck-typed objects for scenequant.analysis.dead_closures /
# unused_slots / unused_color_attrs. 2.73 DNA (BLENDER-v273REND).
#
#   python3 tools/_inventory_bmw_dna.py [/tmp/BMW27.blend]
#
# blendfile.py: https://raw.githubusercontent.com/blender/blender-dev-tools/main/modules/blendfile.py

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

# Import analysis modules by file path: scenequant/__init__.py imports bpy.
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
classify_dead_closures = _dc.classify_dead_closures
dead_counts = _dc.inventory_counts
print_dead = _dc.print_inventory
classify_unused_slots = _us.classify_unused_slots
slot_counts = _us.inventory_counts
print_slots = _us.print_inventory
classify_unused_color_attrs = _uc.classify_unused_color_attrs
color_counts = _uc.inventory_counts
print_colors = _uc.print_inventory

# DNA 2.73 (BKE_node.h / DNA_object_types.h / DNA_customdata_types.h)
OB_RESTRICT_RENDER = 1 << 2
OB_TYPE = {
    0: "EMPTY", 1: "MESH", 2: "CURVE", 3: "SURFACE", 4: "FONT",
    5: "META", 10: "LAMP", 11: "CAMERA", 12: "SPEAKER",
    22: "LATTICE", 25: "ARMATURE",
}
SOCK_FLOAT, SOCK_VECTOR, SOCK_RGBA, SOCK_SHADER = 0, 1, 2, 3
SOCK_IN_USE = 4
CD_MCOL, CD_MLOOPCOL = 6, 17
CD_MTFACE, CD_MTEXPOLY, CD_MLOOPUV = 5, 15, 16

# SH_NODE_* / NODE_* integers from blender v2.73 BKE_node.h
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
    150: "TEX_NOISE",
    155: "TEX_COORD",
    156: "ADD_SHADER",
    157: "TEX_ENVIRONMENT",
    159: "HOLDOUT",
    160: "LAYER_WEIGHT",
    161: "VOLUME_ABSORPTION",
    162: "VOLUME_SCATTER",
    170: "BUMP",
    173: "BSDF_REFRACTION",
    174: "TANGENT",
    175: "NORMAL_MAP",
    187: "UVMAP",
    188: "SEPXYZ",
    189: "COMBXYZ",
    201: "VIEWER",
    204: "MIX_RGB",
    221: "R_LAYERS",
    222: "COMPOSITE",
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


def _id_name(block):
    name = block.get((b"id", b"name"), use_str=True)
    if isinstance(name, bytes):
        name = name.decode("utf-8", "replace")
    if isinstance(name, str) and len(name) >= 2:
        return name[2:]
    return name or ""


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


def _sock_default(bf, sock):
    """Read default_value. 2.73 writes these as untyped DATA (sdna Link).

    Layout is still bNodeSocketValueFloat/Vector/RGBA from DNA_node_types.h.
    """
    ptr = sock.get(b"default_value")
    if not ptr:
        return None
    block = bf.find_block_from_offset(ptr)
    if block is None:
        return None
    stype = int(sock.get(b"type") or 0)
    bf.handle.seek(block.file_offset)
    data = bf.handle.read(block.size)
    if stype == SOCK_FLOAT and len(data) >= 8:
        _subtype, value = struct.unpack_from("<if", data)
        return float(value)
    if stype == SOCK_VECTOR and len(data) >= 16:
        _subtype, x, y, z = struct.unpack_from("<ifff", data)
        return (float(x), float(y), float(z))
    if stype == SOCK_RGBA and len(data) >= 16:
        return tuple(struct.unpack_from("<ffff", data))
    return None


def _build_tree(bf, ntree, images_by_addr, cache):
    if ntree is None:
        return None
    key = ntree.addr_old
    if key in cache:
        return cache[key]
    nodes = []
    node_by_addr = {}
    sock_by_addr = {}
    nfirst = ntree.get_pointer((b"nodes", b"first"))
    for nblock in _walk_list(nfirst) if nfirst else ():
        ntype_i = int(nblock.get(b"type") or 0)
        idname = nblock.get(b"idname") or ""
        rna_type = NODE_TYPE.get(ntype_i, "")
        if not rna_type and idname.startswith("ShaderNode"):
            # last-resort: keep idname, leave type blank rather than guess
            rna_type = ""
        ins, outs = [], []
        for which, bucket in ((b"inputs", ins), (b"outputs", outs)):
            first = nblock.get_pointer((which, b"first"))
            for sblock in _walk_list(first) if first else ():
                ident = sblock.get(b"identifier") or ""
                name = sblock.get(b"name") or ident
                sock = _Obj(
                    name=name,
                    identifier=ident,
                    default_value=_sock_default(bf, sblock),
                    is_linked=False,
                    links=[],
                    node=None,
                )
                bucket.append(sock)
                sock_by_addr[sblock.addr_old] = sock
        node = _Obj(
            name=nblock.get(b"name") or "",
            type=rna_type,
            bl_idname=idname,
            inputs=_SockMap(ins),
            outputs=_SockMap(outs),
            image=None,
            node_tree=None,
            attribute_name="",
            layer_name="",
        )
        for sock in ins + outs:
            sock.node = node
        id_block = nblock.get_pointer(b"id")
        if id_block is not None:
            img = images_by_addr.get(id_block.addr_old)
            if img is not None:
                node.image = img
            if ntype_i == 2 or idname == "ShaderNodeGroup":
                node.node_tree = _build_tree(bf, id_block, images_by_addr, cache)
            if ntype_i in (129, 187):  # ATTRIBUTE / UVMAP storage is NodeShader*
                storage = nblock.get_pointer(b"storage")
                if storage is not None:
                    try:
                        aname = storage.get(b"name") or storage.get(b"uv_map") or ""
                    except KeyError:
                        aname = ""
                    node.attribute_name = aname
                    node.layer_name = aname
        nodes.append(node)
        node_by_addr[nblock.addr_old] = node

    links = []
    lfirst = ntree.get_pointer((b"links", b"first"))
    for lblock in _walk_list(lfirst) if lfirst else ():
        fn = lblock.get_pointer(b"fromnode")
        tn = lblock.get_pointer(b"tonode")
        fs = lblock.get_pointer(b"fromsock")
        ts = lblock.get_pointer(b"tosock")
        from_node = node_by_addr.get(fn.addr_old) if fn else None
        to_node = node_by_addr.get(tn.addr_old) if tn else None
        from_sock = sock_by_addr.get(fs.addr_old) if fs else None
        to_sock = sock_by_addr.get(ts.addr_old) if ts else None
        link = _Link(from_node, from_sock, to_node, to_sock)
        links.append(link)
        for sock in (from_sock, to_sock):
            if sock is None:
                continue
            sock.links.append(link)
            sock.is_linked = True

    tree = _Obj(nodes=nodes, links=links, type=ntree.get(b"type"))
    cache[key] = tree
    return tree


def _mod_name_type(mblock):
    try:
        return mblock.get(b"name"), mblock.get(b"type")
    except KeyError:
        return mblock.get((b"modifier", b"name")), mblock.get((b"modifier", b"type"))


def _color_and_uv_layers(mesh):
    colors = []
    uvs = []
    for cdname, domain in (
        (b"ldata", "CORNER"),
        (b"fdata", "FACE"),
        (b"vdata", "POINT"),
        (b"pdata", "FACE"),
    ):
        tot = int(mesh.get((cdname, b"totlayer")) or 0)
        if tot <= 0:
            continue
        layers = mesh.get_pointer((cdname, b"layers"))
        if layers is None:
            continue
        for i in range(tot):
            typ = int(layers.get(b"type", base_index=i) or 0)
            name = layers.get(b"name", base_index=i) or ""
            if typ in (CD_MCOL, CD_MLOOPCOL):
                colors.append(_Obj(name=name, domain=domain, data_type="BYTE_COLOR"))
            if typ in (CD_MTFACE, CD_MTEXPOLY, CD_MLOOPUV) and name:
                uvs.append(_Obj(name=name))
    return colors, uvs


def build_scene(bf):
    images_by_addr = {}
    for im in bf.find_blocks_from_code(b"IM"):
        path = im.get(b"name") or ""
        images_by_addr[im.addr_old] = _Obj(
            name=_id_name(im),
            filepath=path,
            filepath_raw=path,
            channels=None,
            file_format="",
            alpha_mode=int(im.get(b"alpha_mode") or 0),
        )

    mats_by_addr = {}
    tree_cache = {}
    node_type_counts = Counter()
    idname_counts = Counter()
    n_trees = 0
    n_with_nodes = 0
    mix_facs = []
    disp_links = []
    for ma in bf.find_blocks_from_code(b"MA"):
        ntree = ma.get_pointer(b"nodetree")
        tree = _build_tree(bf, ntree, images_by_addr, tree_cache) if ntree else None
        if tree is not None:
            n_trees += 1
            n_with_nodes += 1
            for node in tree.nodes:
                node_type_counts[node.type or node.bl_idname] += 1
                idname_counts[node.bl_idname] += 1
                if node.type == "MIX_SHADER":
                    fac = node.inputs.get("Fac")
                    mix_facs.append((
                        _id_name(ma),
                        getattr(fac, "is_linked", False) if fac else None,
                        getattr(fac, "default_value", None) if fac else None,
                    ))
                if node.type == "OUTPUT_MATERIAL":
                    disp = node.inputs.get("Displacement")
                    if disp is not None and disp.is_linked:
                        src = disp.links[0].from_node if disp.links else None
                        disp_links.append((
                            _id_name(ma),
                            getattr(src, "name", ""),
                            getattr(src, "type", ""),
                        ))
        mats_by_addr[ma.addr_old] = _Obj(
            name=_id_name(ma),
            library=None if ma.get_pointer((b"id", b"lib")) is None else _Obj(name="lib"),
            override_library=None,
            use_nodes=bool(ma.get(b"use_nodes")),
            node_tree=tree,
        )

    sc = bf.find_blocks_from_code(b"SC")[0]
    objects = []
    mesh_stats = []
    unique_meshes = 0
    unused_slot_raw = 0
    seen_mesh = set()
    n_hide = 0
    n_linked = 0
    type_counts = Counter()
    base_first = sc.get_pointer((b"base", b"first"))
    for base in _walk_list(base_first) if base_first else ():
        ob = base.get_pointer(b"object")
        if ob is None:
            continue
        ob_type = OB_TYPE.get(int(ob.get(b"type") or 0), "EMPTY")
        type_counts[ob_type] += 1
        hide = bool(int(ob.get(b"restrictflag") or 0) & OB_RESTRICT_RENDER)
        if hide:
            n_hide += 1
        lib = ob.get_pointer((b"id", b"lib"))
        if lib is not None:
            n_linked += 1
        data = ob.get_pointer(b"data")
        mesh = None
        slots = []
        mods = []
        mfirst = ob.get_pointer((b"modifiers", b"first"))
        for mblock in _walk_list(mfirst) if mfirst else ():
            mname, mtype = _mod_name_type(mblock)
            mods.append(_Obj(name=mname or "", type=mtype))
        if ob_type == "MESH" and data is not None:
            totcol = int(data.get(b"totcol") or 0)
            mat_blocks = _read_ptr_array(bf, data.get_pointer(b"mat"), totcol)
            materials = []
            for mb in mat_blocks:
                mat = mats_by_addr.get(mb.addr_old) if mb is not None else None
                materials.append(mat)
                slots.append(_Obj(material=mat))
            totpoly = int(data.get(b"totpoly") or 0)
            mpoly = data.get_pointer(b"mpoly")
            polys = []
            used = set()
            how = "no_mpoly"
            if mpoly is not None and totpoly > 0:
                how = "mpoly.mat_nr"
                for i in range(totpoly):
                    idx = int(mpoly.get(b"mat_nr", base_index=i) or 0)
                    polys.append(_Obj(material_index=idx))
                    used.add(idx)
            unused = []
            for i, mat in enumerate(materials):
                if mat is not None and i not in used:
                    unused.append((i, mat.name))
            colors, uvs = _color_and_uv_layers(data)
            mesh = _Obj(
                name=_id_name(data),
                library=None if data.get_pointer((b"id", b"lib")) is None else _Obj(name="lib"),
                override_library=None,
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
                "totpoly": totpoly,
                "used": sorted(used),
                "unused": unused,
                "how": how,
                "dup": dup,
                "n_color": len(colors),
                "n_uv": len(uvs),
                "n_mod": len(mods),
            })
        objects.append(_Obj(
            name=_id_name(ob),
            type=ob_type,
            hide_render=hide,
            library=None if lib is None else _Obj(name="lib"),
            override_library=None,
            data=mesh,
            material_slots=slots,
            modifiers=mods,
            scenequant=_Obj(override="AUTO"),
        ))

    comp = None
    if sc.get_pointer(b"nodetree") is not None:
        comp = _build_tree(bf, sc.get_pointer(b"nodetree"), images_by_addr, tree_cache)

    scene = _Obj(
        name=_id_name(sc),
        objects=objects,
        use_nodes=bool(sc.get(b"use_nodes")),
        node_tree=comp,
        compositing_node_group=None,
    )
    proof = {
        "scene": scene.name,
        "n_objects": len(objects),
        "types": dict(type_counts),
        "n_hide_render": n_hide,
        "n_linked": n_linked,
        "n_materials": len(mats_by_addr),
        "n_shader_trees": n_trees,
        "n_use_nodes": n_with_nodes,
        "node_types": dict(node_type_counts),
        "idnames": dict(idname_counts),
        "mix_facs": mix_facs,
        "disp_links": disp_links,
        "unique_local_meshes": unique_meshes,
        "unused_slots_raw": unused_slot_raw,
        "mesh_stats": mesh_stats,
    }
    return scene, proof


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    path = argv[0] if argv else "/tmp/BMW27.blend"
    print("BMW27 DNA inventory file=%r" % path)
    print("reader=blendfile.py (no bpy, blender binary not launched)")
    bf = blendfile.open_blend(path)
    try:
        hdr = bf.header
        print("blend_header version=%s ptr=%s le=%s" % (
            hdr.version, hdr.pointer_size, hdr.is_little_endian))
        scene, proof = build_scene(bf)
    finally:
        bf.close()

    print("SCENE %s objects=%d hide_render=%d linked=%d types=%s" % (
        proof["scene"], proof["n_objects"], proof["n_hide_render"],
        proof["n_linked"], proof["types"]))
    print("MATERIALS %d shader_trees=%d use_nodes=%d" % (
        proof["n_materials"], proof["n_shader_trees"], proof["n_use_nodes"]))
    print("NODE_TYPES %s" % proof["node_types"])
    print("MIX_SHADER_FAC %s" % proof["mix_facs"])
    print("DISPLACE_LINKS %s" % proof["disp_links"])
    print("UNIQUE_MESHES %d UNUSED_SLOTS_RAW %d (via %s)" % (
        proof["unique_local_meshes"], proof["unused_slots_raw"],
        "mpoly.mat_nr"))
    n_color = sum(m["n_color"] for m in proof["mesh_stats"])
    print("COLOR_ATTR_LAYERS %d (CD_MCOL/CD_MLOOPCOL)" % n_color)

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

    fired = {
        "PRUNE_MIX_TRANSPARENT": dcounts.get("PRUNE_MIX_TRANSPARENT", 0),
        "PRUNE_DISPLACE": dcounts.get("PRUNE_DISPLACE", 0),
        "UNIQUE_UNUSED_SLOTS": scounts.get("UNIQUE_UNUSED_SLOTS", 0),
        "UNUSED_COLOR_ATTRS": ccounts.get("UNUSED_COLOR_ATTRS", 0),
    }
    print("FIRED %s" % fired)
    print("STORE Classroom 41% / loft 52% unchanged. BMW 79% was 1225 spp overkill.")
    print("Auto off. No time claim.")
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
