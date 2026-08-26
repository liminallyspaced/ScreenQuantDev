# DNA inventory of today's Auto-off levers (no bpy, no Blender launch).
#
# Levers: CLAMP_INDIRECT, ZERO_ENERGY_LIGHT, ZERO_SHADER_LIGHT, ZERO_WORLD_BG.
# Same code for any .blend. Missing DNA is UNKNOWN, never guessed as 0.
#
#   python3 tools/_inventory_today_levers_dna.py [/path/file.blend]
#
# Official kitchen on this box: /workspace/scenequant/work/bench/BMW27.blend
# Classroom / loft are not on the box — this script will not invent those counts.

from __future__ import annotations

import hashlib
import os
import struct
import sys

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
import _inventory_blend_dna as dna  # noqa: E402

import importlib.util


def _load_analysis(name):
    path = os.path.join(_ADDON_ROOT, "scenequant", "analysis", name + ".py")
    spec = importlib.util.spec_from_file_location(
        "scenequant.analysis." + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_ci = _load_analysis("clamp_indirect")
_zel = _load_analysis("zero_energy_lights")
_zsl = _load_analysis("zero_shader_lights")
_zwb = _load_analysis("zero_world_bg")

IDP_STRING, IDP_INT, IDP_FLOAT = 0, 1, 2
IDP_ARRAY, IDP_GROUP, IDP_DOUBLE = 5, 6, 8
OB_LAMP = 10
# 2.73 Lamp.type: 0 LOCAL, 1 SUN, 2 SPOT, 3 HEMI, 4 AREA
LAMP_TYPE = {0: "POINT", 1: "SUN", 2: "SPOT", 3: "HEMI", 4: "AREA"}

# World.cycles.sampling_method (Cycles 4.x RNA). Unknown ints stay UNKNOWN.
SAMPLING_METHOD = {0: "NONE", 1: "AUTOMATIC", 2: "MANUAL"}


def _file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _idp_children(prop):
    return list(dna._idp_children(prop) or ())


def _idp_name(prop):
    return dna._idp_name(prop)


def _idp_number(prop):
    """INT / FLOAT / DOUBLE. FLOAT is IEEE bits in data.val. None if unproven."""
    if prop is None:
        return None, "MISSING"
    try:
        typ = int(prop.get(b"type") or -1)
    except (KeyError, NotImplementedError, AssertionError, TypeError):
        return None, "UNREAD"
    if typ == IDP_INT:
        val = dna._idp_int(prop)
        if val is None:
            return None, "UNREAD"
        return float(val), "INT"
    if typ == IDP_FLOAT:
        try:
            raw = prop.get((b"data", b"val"))
        except (KeyError, NotImplementedError, AssertionError):
            return None, "UNREAD"
        if raw is None:
            return None, "UNREAD"
        try:
            bits = int(raw) & 0xFFFFFFFF
            return float(struct.unpack("<f", struct.pack("<I", bits))[0]), "FLOAT"
        except (TypeError, ValueError, struct.error):
            return None, "UNREAD"
    if typ == IDP_DOUBLE:
        try:
            ptr = prop.get((b"data", b"pointer"))
        except (KeyError, NotImplementedError, AssertionError):
            ptr = None
        if not ptr:
            # some trees store double bits across val/val2
            try:
                lo = int(prop.get((b"data", b"val")) or 0) & 0xFFFFFFFF
                hi = int(prop.get((b"data", b"val2")) or 0) & 0xFFFFFFFF
                return float(struct.unpack("<d", struct.pack("<II", lo, hi))[0]), "DOUBLE"
            except (KeyError, NotImplementedError, AssertionError, TypeError, struct.error):
                return None, "UNREAD"
        return None, "UNREAD"
    return None, "TYPE_%s" % typ


def _idp_group(root, *names):
    cur = root
    for name in names:
        if cur is None:
            return None
        found = None
        for child in _idp_children(cur):
            if _idp_name(child) == name:
                found = child
                break
        cur = found
    return cur


def _idp_keys(group):
    return [_idp_name(c) for c in _idp_children(group)]


def _engine(sc):
    raw = dna._safe_get(sc, (b"r", b"engine"))
    if raw is None:
        return "UNKNOWN"
    text = dna._as_str(raw).strip("\x00").strip()
    return text or "UNKNOWN"


def _anim_duck(block):
    """animation_data duck. Missing adt → None (classifier: not animated)."""
    adt = dna._safe_pointer(block, b"adt")
    if adt is None:
        return None
    action = dna._safe_pointer(adt, b"action")
    nla_first = dna._safe_pointer(adt, (b"nla_tracks", b"first"))
    tracks = []
    if nla_first is not None:
        tracks.append(dna._Obj(strips=[True]))
    return dna._Obj(
        action=dna._Obj(name="action") if action is not None else None,
        nla_tracks=tracks,
        drivers=(),
    )


def _read_lamp(bf, data):
    """Lamp/Light DNA → duck + honesty flags. energy/use_nodes UNKNOWN if missing."""
    info = {
        "energy": None,
        "energy_src": "MISSING",
        "use_nodes": None,
        "use_nodes_src": "MISSING",
        "light_type": "",
        "is_portal": False,
        "portal_src": "MISSING",
        "has_tree": False,
        "tree": None,
    }
    if data is None:
        return info
    if dna._has_field(data, b"energy"):
        raw = dna._safe_get(data, b"energy")
        if isinstance(raw, (int, float)):
            info["energy"] = float(raw)
            info["energy_src"] = "DNA"
        else:
            info["energy_src"] = "UNREAD"
    if dna._has_field(data, b"use_nodes"):
        raw = dna._safe_get(data, b"use_nodes")
        if raw is None:
            info["use_nodes_src"] = "UNREAD"
        else:
            info["use_nodes"] = bool(raw)
            info["use_nodes_src"] = "DNA"
    if dna._has_field(data, b"type"):
        raw = dna._safe_get(data, b"type")
        if isinstance(raw, (int, float)):
            info["light_type"] = LAMP_TYPE.get(int(raw), "TYPE_%s" % int(raw))
        elif raw:
            info["light_type"] = dna._as_str(raw)
    # Cycles portal is IDP Lamp.cycles.is_portal (later files). Missing ≠ False
    # for apply, but classifier treats missing is_portal as False. Report src.
    cycles = _idp_group(dna._safe_pointer(data, (b"id", b"properties")), "cycles")
    if cycles is not None:
        portal = None
        for child in _idp_children(cycles):
            if _idp_name(child) == "is_portal":
                portal = dna._idp_int(child)
                break
        if portal is None:
            info["portal_src"] = "KEY_MISSING"
            info["is_portal"] = False
        else:
            info["is_portal"] = bool(portal)
            info["portal_src"] = "IDP"
    ntree = dna._safe_pointer(data, b"nodetree")
    info["has_tree"] = ntree is not None
    return info


def _background_strength(tree):
    """Return (value_or_None, src, proven_zero).

    Unlinked Strength default is DNA. Linked Strength is not evaluated here
    beyond the classifier's one-hop Value rule — if we cannot prove 0, src
    is UNKNOWN (never report 0).
    """
    if tree is None:
        return None, "NO_TREE", False
    output = None
    for node in tree.nodes:
        ntype = getattr(node, "type", "") or ""
        bl_id = getattr(node, "bl_idname", "") or ""
        if ntype == "OUTPUT_WORLD" or bl_id == "ShaderNodeOutputWorld":
            output = node
            break
    if output is None:
        return None, "NO_OUTPUT", False
    surf = output.inputs.get("Surface")
    if surf is None:
        return None, "NO_SURFACE", False
    if not getattr(surf, "is_linked", False):
        return 0.0, "UNLINKED_SURFACE", True
    if not surf.links:
        return None, "SURFACE_LINK_UNNAMED", False
    src_node = surf.links[0].from_node
    if src_node is None:
        return None, "SURFACE_FROM_UNKNOWN", False
    ntype = getattr(src_node, "type", "") or ""
    bl_id = getattr(src_node, "bl_idname", "") or ""
    if ntype not in ("BACKGROUND", "EMISSION") and bl_id not in (
            "ShaderNodeBackground", "ShaderNodeEmission"):
        return None, "SURFACE_NOT_BACKGROUND", False
    strength = src_node.inputs.get("Strength")
    if strength is None:
        return None, "NO_STRENGTH_SOCK", False
    if getattr(strength, "is_linked", False):
        # Classifier may still prove a one-hop Value 0. Do not claim 0 here
        # without that proof.
        return None, "STRENGTH_LINKED", False
    val = getattr(strength, "default_value", None)
    if not isinstance(val, (int, float)):
        return None, "STRENGTH_DEFAULT_UNREAD", False
    return float(val), "UNLINKED_DEFAULT", abs(float(val)) <= 1e-4


def _color_spatial(tree):
    """True / False / None. None = unproven (GROUP / unnamed)."""
    if tree is None:
        return False, "NO_TREE"
    types = []
    unknown = 0
    for node in tree.nodes:
        ntype = getattr(node, "type", "") or ""
        bl_id = getattr(node, "bl_idname", "") or ""
        label = ntype or bl_id or ""
        types.append(label)
        if not ntype and not bl_id:
            unknown += 1
    spatial = {
        "TEX_ENVIRONMENT", "TEX_SKY", "TEX_IMAGE", "TEX_NOISE", "TEX_WAVE",
        "TEX_MUSGRAVE", "TEX_VORONOI", "TEX_MAGIC", "TEX_GRADIENT",
        "TEX_CHECKER", "TEX_BRICK", "TEX_WHITE_NOISE", "TEX_GABOR",
        "TEX_POINTDENSITY", "TEX_IES",
        "ShaderNodeTexEnvironment", "ShaderNodeTexSky", "ShaderNodeTexImage",
        "ShaderNodeTexNoise", "ShaderNodeTexWave", "ShaderNodeTexMusgrave",
        "ShaderNodeTexVoronoi", "ShaderNodeTexMagic", "ShaderNodeTexGradient",
        "ShaderNodeTexChecker", "ShaderNodeTexBrick", "ShaderNodeTexWhiteNoise",
        "ShaderNodeTexGabor", "ShaderNodeTexPointDensity", "ShaderNodeTexIES",
    }
    hit = [t for t in types if t in spatial]
    if unknown:
        return None, "UNKNOWN_NODE_TYPES=%d types=%s" % (unknown, types)
    if hit:
        return True, "SPATIAL %s" % hit
    return False, "NO_SPATIAL types=%s" % types


def _volume_linked(tree):
    if tree is None:
        return False
    for node in tree.nodes:
        ntype = getattr(node, "type", "") or ""
        bl_id = getattr(node, "bl_idname", "") or ""
        if ntype == "OUTPUT_WORLD" or bl_id == "ShaderNodeOutputWorld":
            vol = node.inputs.get("Volume")
            return bool(vol is not None and getattr(vol, "is_linked", False))
    return False


def _sampling_method(world_block):
    cycles = _idp_group(
        dna._safe_pointer(world_block, (b"id", b"properties")), "cycles")
    if cycles is None:
        return None, "CYCLES_GROUP_MISSING"
    keys = _idp_keys(cycles)
    if "sampling_method" not in keys:
        return None, "KEY_MISSING keys=%s" % keys
    prop = None
    for child in _idp_children(cycles):
        if _idp_name(child) == "sampling_method":
            prop = child
            break
    try:
        typ = int(prop.get(b"type") or -1)
    except (KeyError, NotImplementedError, AssertionError, TypeError):
        return None, "UNREAD"
    if typ == IDP_INT:
        val = dna._idp_int(prop)
        if val is None:
            return None, "UNREAD"
        return SAMPLING_METHOD.get(val, "INT_%s" % val), "IDP_INT"
    if typ == IDP_STRING:
        return None, "STRING_UNPARSED"
    return None, "TYPE_%s" % typ


def build(bf):
    images_by_addr = {}
    for im in bf.find_blocks_from_code(b"IM"):
        path = dna._image_filepath(im)
        images_by_addr[im.addr_old] = dna._Obj(
            name=dna._id_name(im),
            filepath=path,
            filepath_raw=path,
            channels=None,
            file_format="",
            alpha_mode="",
        )

    stats = {
        "n_bad_links": 0,
        "n_links": 0,
        "n_bad_links_world": 0,
        "n_bad_links_light": 0,
        "n_links_world": 0,
        "n_links_light": 0,
    }
    tree_cache = {}

    sc, scene_names = dna._pick_scene(bf)
    engine = _engine(sc) if sc is not None else "UNKNOWN"

    # --- CLAMP_INDIRECT ---
    clamp = {
        "engine": engine,
        "key": "MISSING",
        "value": None,
        "value_src": "MISSING",
        "direct_key": "MISSING",
        "direct_value": None,
        "cycles_keys": [],
    }
    if sc is not None:
        root = dna._safe_pointer(sc, (b"id", b"properties"))
        cycles = _idp_group(root, "cycles")
        if cycles is None:
            clamp["key"] = "CYCLES_GROUP_MISSING"
            clamp["value_src"] = "CYCLES_GROUP_MISSING"
        else:
            clamp["cycles_keys"] = _idp_keys(cycles)
            if "sample_clamp_indirect" in clamp["cycles_keys"]:
                prop = None
                for child in _idp_children(cycles):
                    if _idp_name(child) == "sample_clamp_indirect":
                        prop = child
                        break
                val, src = _idp_number(prop)
                clamp["key"] = "PRESENT"
                clamp["value"] = val
                clamp["value_src"] = src
            else:
                clamp["key"] = "KEY_MISSING"
                clamp["value_src"] = "KEY_MISSING"
            if "sample_clamp_direct" in clamp["cycles_keys"]:
                clamp["direct_key"] = "PRESENT"
                prop = None
                for child in _idp_children(cycles):
                    if _idp_name(child) == "sample_clamp_direct":
                        prop = child
                        break
                clamp["direct_value"], _src = _idp_number(prop)
            else:
                clamp["direct_key"] = "KEY_MISSING"

    # --- Lights ---
    la_blocks = list(bf.find_blocks_from_code(b"LA"))
    lights = []
    n_type10 = 0
    n_energy0 = 0
    n_energy_unread = 0
    n_use_nodes = 0
    n_shader_zero = 0
    n_shader_unknown = 0
    objects = []
    if sc is not None:
        for ob in dna._iter_scene_objects(sc):
            ob_type_i = int(dna._safe_get(ob, b"type") or 0)
            if ob_type_i != OB_LAMP:
                continue
            n_type10 += 1
            data = dna._safe_pointer(ob, b"data")
            info = _read_lamp(bf, data)
            tree = None
            if info["has_tree"]:
                tree = dna._build_tree(
                    bf, dna._safe_pointer(data, b"nodetree"),
                    images_by_addr, tree_cache, stats, kind="light")
            hide = dna._hide_render(ob)
            if info["energy"] == 0:
                n_energy0 += 1
            elif info["energy"] is None:
                n_energy_unread += 1
            if info["use_nodes"] is True:
                n_use_nodes += 1
            light_data = dna._Obj(
                name=dna._id_name(data) if data is not None else "",
                energy=info["energy"] if info["energy"] is not None else None,
                type=info["light_type"],
                use_nodes=bool(info["use_nodes"]) if info["use_nodes"] is not None else False,
                node_tree=tree,
                library=dna._lib_wrapper(data) if data is not None else None,
                animation_data=_anim_duck(data) if data is not None else None,
                cycles=dna._Obj(is_portal=info["is_portal"]),
            )
            # Only expose energy attr when DNA proved it (hasattr gate).
            if info["energy"] is None:
                del light_data.__dict__["energy"]
            if info["use_nodes"] is None:
                del light_data.__dict__["use_nodes"]
            obj = dna._Obj(
                name=dna._id_name(ob),
                type="LIGHT",
                hide_render=hide,
                library=dna._lib_wrapper(ob),
                override_library=dna._override_wrapper(ob),
                data=light_data,
                animation_data=_anim_duck(ob),
                scenequant=dna._Obj(override="AUTO"),
            )
            objects.append(obj)
            shader_state = "N/A"
            if info["use_nodes"] is True and tree is not None:
                proven = _zsl._shader_emission_zero(tree)
                if proven is True:
                    shader_state = "PROVEN_ZERO"
                    n_shader_zero += 1
                else:
                    shader_state = "UNKNOWN_OR_LIVE"
                    n_shader_unknown += 1
            elif info["use_nodes"] is True and tree is None:
                shader_state = "USE_NODES_NO_TREE"
                n_shader_unknown += 1
            elif info["use_nodes"] is None and info["has_tree"]:
                shader_state = "USE_NODES_UNKNOWN"
                n_shader_unknown += 1
            lights.append({
                "object": obj.name,
                "energy": info["energy"],
                "energy_src": info["energy_src"],
                "use_nodes": info["use_nodes"],
                "use_nodes_src": info["use_nodes_src"],
                "hide_render": hide,
                "light_type": info["light_type"],
                "portal_src": info["portal_src"],
                "shader": shader_state,
            })

    # --- World ---
    worlds = list(bf.find_blocks_from_code(b"WO"))
    world_block = None
    if sc is not None:
        world_block = dna._safe_pointer(sc, b"world")
    if world_block is None and worlds:
        world_block = worlds[0]
    world_info = {
        "name": dna._id_name(world_block) if world_block is not None else "",
        "use_nodes": None,
        "use_nodes_src": "MISSING",
        "has_tree": False,
        "strength": None,
        "strength_src": "NO_WORLD",
        "strength_zero": False,
        "spatial": None,
        "spatial_src": "NO_WORLD",
        "volume_linked": False,
        "sampling_method": None,
        "sampling_src": "NO_WORLD",
        "node_types": [],
    }
    world_duck = None
    if world_block is not None:
        if dna._has_field(world_block, b"use_nodes"):
            raw = dna._safe_get(world_block, b"use_nodes")
            if raw is None:
                world_info["use_nodes_src"] = "UNREAD"
            else:
                world_info["use_nodes"] = bool(raw)
                world_info["use_nodes_src"] = "DNA"
        ntree = dna._safe_pointer(world_block, b"nodetree")
        tree = None
        if ntree is not None:
            world_info["has_tree"] = True
            tree = dna._build_tree(
                bf, ntree, images_by_addr, tree_cache, stats, kind="world")
            world_info["node_types"] = [
                getattr(n, "type", "") or getattr(n, "bl_idname", "")
                for n in (tree.nodes if tree else [])
            ]
        sval, ssrc, szero = _background_strength(tree)
        world_info["strength"] = sval
        world_info["strength_src"] = ssrc
        world_info["strength_zero"] = szero
        spat, spat_src = _color_spatial(tree)
        world_info["spatial"] = spat
        world_info["spatial_src"] = spat_src
        world_info["volume_linked"] = _volume_linked(tree)
        smeth, ssrc2 = _sampling_method(world_block)
        world_info["sampling_method"] = smeth
        world_info["sampling_src"] = ssrc2
        wcycles_kw = {}
        if smeth is not None:
            wcycles_kw["sampling_method"] = smeth
        world_duck = dna._Obj(
            name=world_info["name"],
            use_nodes=bool(world_info["use_nodes"]),
            node_tree=tree,
            library=dna._lib_wrapper(world_block),
            animation_data=_anim_duck(world_block),
            scenequant=dna._Obj(override="AUTO"),
            cycles=dna._Obj(**wcycles_kw) if wcycles_kw else dna._Obj(),
        )
        if world_info["use_nodes"] is None:
            del world_duck.__dict__["use_nodes"]

    # Classifier ducks: only attach sample_clamp_indirect when DNA proved it.
    cycles_kw = {}
    if clamp["key"] == "PRESENT" and clamp["value"] is not None:
        cycles_kw["sample_clamp_indirect"] = clamp["value"]
    scene = dna._Obj(
        name=dna._id_name(sc) if sc is not None else "",
        render=dna._Obj(engine=engine if engine != "UNKNOWN" else "CYCLES"),
        cycles=dna._Obj(**cycles_kw),
        objects=objects,
        world=world_duck,
    )

    clamp_recs = _ci.classify_clamp_indirect(scene)
    zel_recs = _zel.classify_zero_energy_lights(scene)
    zsl_recs = _zsl.classify_zero_shader_lights(scene)
    zwb_recs = _zwb.classify_zero_world_bg(scene)

    return {
        "scene": scene.name,
        "scene_names": scene_names,
        "engine": engine,
        "clamp": clamp,
        "la_blocks": len(la_blocks),
        "n_type10": n_type10,
        "n_energy0": n_energy0,
        "n_energy_unread": n_energy_unread,
        "n_use_nodes": n_use_nodes,
        "n_shader_zero": n_shader_zero,
        "n_shader_unknown": n_shader_unknown,
        "lights": lights,
        "world": world_info,
        "n_worlds": len(worlds),
        "n_libs": len(bf.find_blocks_from_code(b"LI")),
        "link_stats": {
            "world_bad": stats.get("n_bad_links_world", 0),
            "light_bad": stats.get("n_bad_links_light", 0),
        },
        "fire": {
            "CLAMP_INDIRECT": len(clamp_recs),
            "ZERO_ENERGY_LIGHT": len(zel_recs),
            "ZERO_SHADER_LIGHT": len(zsl_recs),
            "ZERO_WORLD_BG": len(zwb_recs),
        },
        "clamp_recs": clamp_recs,
        "zel_recs": zel_recs,
        "zsl_recs": zsl_recs,
        "zwb_recs": zwb_recs,
    }


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    default = "/workspace/scenequant/work/bench/BMW27.blend"
    path = argv[0] if argv else default
    print("TODAY_LEVERS DNA inventory file=%r" % path)
    print("reader=blendfile.py (no bpy, blender binary not launched)")
    print("levers=CLAMP_INDIRECT,ZERO_ENERGY_LIGHT,ZERO_SHADER_LIGHT,ZERO_WORLD_BG")
    if not os.path.isfile(path):
        print("MISSING_FILE %r — do not invent counts" % path)
        return 2
    st = os.stat(path)
    print("file_bytes=%d sha256=%s" % (st.st_size, _file_sha256(path)))
    bf = blendfile.open_blend(path)
    try:
        print("blend_header %s version=%s ptr=%s le=%s" % (
            dna._blend_header_label(bf), bf.header.version,
            bf.header.pointer_size, bf.header.is_little_endian))
        proof = build(bf)
    finally:
        bf.close()

    print("SCENE %s engine=%s scenes=%s libraries=%d" % (
        proof["scene"], proof["engine"], proof["scene_names"], proof["n_libs"]))

    clamp = proof["clamp"]
    print("CLAMP_INDIRECT_DNA key=%s value=%s value_src=%s engine=%s" % (
        clamp["key"], clamp["value"], clamp["value_src"], clamp["engine"]))
    print("CLAMP_INDIRECT_DNA sample_clamp_direct key=%s value=%s" % (
        clamp["direct_key"], clamp["direct_value"]))
    print("CLAMP_INDIRECT_DNA cycles_keys=%s" % clamp["cycles_keys"])
    if clamp["key"] != "PRESENT":
        print("CLAMP_INDIRECT_DNA honesty: missing key is UNKNOWN, not 0. "
              "2.73 Cycles IDP predates sample_clamp_indirect. "
              "Classifier hasattr-gate → fire=0.")
    print("CLAMP_INDIRECT fire=%d" % proof["fire"]["CLAMP_INDIRECT"])

    print("LIGHTS LA_blocks=%d scene_type10=%d energy0=%d energy_unread=%d "
          "use_nodes=%d" % (
              proof["la_blocks"], proof["n_type10"], proof["n_energy0"],
              proof["n_energy_unread"], proof["n_use_nodes"]))
    print("LIGHTS shader_zero=%d shader_unknown=%d light_bad_links=%d" % (
        proof["n_shader_zero"], proof["n_shader_unknown"],
        proof["link_stats"]["light_bad"]))
    print("LIGHTS rows=%s" % proof["lights"])
    if proof["n_energy_unread"]:
        print("ZERO_ENERGY_LIGHT honesty: %d light(s) energy UNREAD — "
              "those are not counted as energy==0." % proof["n_energy_unread"])
    if proof["n_shader_unknown"]:
        print("ZERO_SHADER_LIGHT honesty: shader Strength not proven 0 "
              "without full node eval / readable default → UNKNOWN, not 0.")
    print("ZERO_ENERGY_LIGHT fire=%d" % proof["fire"]["ZERO_ENERGY_LIGHT"])
    print("ZERO_SHADER_LIGHT fire=%d" % proof["fire"]["ZERO_SHADER_LIGHT"])

    w = proof["world"]
    print("WORLD name=%r n_worlds=%d use_nodes=%s use_nodes_src=%s ntree=%s" % (
        w["name"], proof["n_worlds"], w["use_nodes"], w["use_nodes_src"],
        w["has_tree"]))
    print("WORLD strength=%s src=%s proven_zero=%s" % (
        w["strength"], w["strength_src"], w["strength_zero"]))
    print("WORLD spatial=%s src=%s" % (w["spatial"], w["spatial_src"]))
    print("WORLD volume_linked=%s sampling_method=%s sampling_src=%s" % (
        w["volume_linked"], w["sampling_method"], w["sampling_src"]))
    print("WORLD node_types=%s world_bad_links=%d" % (
        w["node_types"], proof["link_stats"]["world_bad"]))
    if w["strength_src"] in ("STRENGTH_LINKED", "STRENGTH_DEFAULT_UNREAD",
                             "SURFACE_FROM_UNKNOWN", "NO_STRENGTH_SOCK"):
        print("WORLD honesty: Background Strength not proven 0 → UNKNOWN, not 0.")
    if w["sampling_src"].startswith("KEY_MISSING") or w["sampling_src"].endswith("MISSING"):
        print("WORLD honesty: sampling_method missing is UNKNOWN, not NONE.")
    print("ZERO_WORLD_BG fire=%d" % proof["fire"]["ZERO_WORLD_BG"])

    print("FIRED %s" % proof["fire"])
    print("CLASSROOM/LOFT not on this box; counts not invented.")
    print("STORE Classroom 41% / loft 52% unchanged.")
    print("Auto off. No time claim.")
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
