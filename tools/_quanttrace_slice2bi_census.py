# QuantTrace Slice 2bi census: loft Plane.002 / Rope Normal Map Color (not TEX_IMAGE).
from collections import Counter
import bpy

def peel_reroute(node, sock):
    for _ in range(64):
        if node is None or getattr(node, "type", None) != "REROUTE":
            return node, sock
        inputs = getattr(node, "inputs", None)
        if inputs is None or len(inputs) < 1:
            return node, sock
        rin = inputs[0]
        if not getattr(rin, "is_linked", False):
            return node, sock
        links = list(rin.links or [])
        if len(links) != 1:
            return node, sock
        node = links[0].from_node
        sock = links[0].from_socket
    return node, sock

def dump_sock(sock, depth=0, max_depth=10):
    if sock is None:
        return "None"
    indent = "  " * depth
    linked = bool(sock.is_linked)
    dv = getattr(sock, "default_value", None)
    try:
        if hasattr(dv, "__len__") and not isinstance(dv, (str, bytes)):
            dv_s = tuple(round(float(x), 6) for x in list(dv)[:4])
        else:
            dv_s = round(float(dv), 6) if dv is not None else None
    except Exception:
        dv_s = repr(dv)
    lines = ["%ssock=%r type=%s linked=%s default=%s" % (indent, sock.name, sock.type, linked, dv_s)]
    if not linked or depth >= max_depth:
        return "\n".join(lines)
    for i, ln in enumerate(list(sock.links or [])):
        fn, fs = peel_reroute(ln.from_node, ln.from_socket)
        ntype = getattr(fn, "type", None)
        nname = getattr(fn, "name", None)
        nbl = getattr(fn, "bl_idname", None)
        lines.append("%s  link[%d] node=%r type=%s bl=%s out=%r" % (indent, i, nname, ntype, nbl, getattr(fs, "name", None)))
        for attr in ("blend_type", "data_type", "clamp_factor", "clamp_result", "use_clamp",
                     "interpolation", "projection", "extension", "vector_type", "operation",
                     "space", "uv_map", "invert", "color_space", "mode"):
            if hasattr(fn, attr):
                lines.append("%s    .%s=%r" % (indent, attr, getattr(fn, attr)))
        img = getattr(fn, "image", None)
        if img is not None:
            cs = getattr(getattr(img, "colorspace_settings", None), "name", None)
            packed = bool(getattr(img, "packed_file", None))
            lines.append("%s    image=%r cs=%r packed=%s filepath=%r" % (indent, img.name, cs, packed, getattr(img, "filepath", None)))
        mapping = getattr(fn, "mapping", None)
        if mapping is not None:
            lines.append("%s    mapping.extend=%r clip_min=%s clip_max=%s" % (
                indent, getattr(mapping, "extend", None),
                getattr(mapping, "clip_min_x", None), getattr(mapping, "clip_max_x", None)))
            curves = list(getattr(mapping, "curves", None) or [])
            for ci, cm in enumerate(curves[:4]):
                pts = []
                for p in list(getattr(cm, "points", None) or []):
                    loc = getattr(p, "location", None)
                    try:
                        pts.append((round(float(loc[0]), 6), round(float(loc[1]), 6)))
                    except Exception:
                        pts.append(repr(loc))
                lines.append("%s    curve[%d] pts=%s" % (indent, ci, pts))
        cr = getattr(fn, "color_ramp", None)
        if cr is not None:
            elems = []
            for e in list(getattr(cr, "elements", None) or []):
                try:
                    elems.append((round(float(e.position), 6),
                                  tuple(round(float(x), 6) for x in list(e.color)[:4])))
                except Exception:
                    elems.append(repr(e))
            lines.append("%s    color_ramp.interp=%r color_mode=%r elems=%s" % (
                indent, getattr(cr, "interpolation", None), getattr(cr, "color_mode", None), elems))
        for inp in list(getattr(fn, "inputs", []) or []):
            lines.append(dump_sock(inp, depth + 2, max_depth))
    return "\n".join(lines)

def classify_color_source(sock):
    if sock is None:
        return ("none", None)
    if not sock.is_linked:
        dv = getattr(sock, "default_value", None)
        try:
            rgb = tuple(round(float(x), 6) for x in list(dv)[:3])
        except Exception:
            rgb = repr(dv)
        return ("const", rgb)
    links = list(sock.links or [])
    if len(links) != 1:
        return ("multi", len(links))
    fn, fs = peel_reroute(links[0].from_node, links[0].from_socket)
    ntype = getattr(fn, "type", None)
    detail = {
        "name": getattr(fn, "name", None),
        "out": getattr(fs, "name", None),
        "bl": getattr(fn, "bl_idname", None),
    }
    if ntype == "TEX_IMAGE":
        img = getattr(fn, "image", None)
        detail["image"] = getattr(img, "name", None) if img else None
        detail["cs"] = getattr(getattr(img, "colorspace_settings", None), "name", None) if img else None
        detail["packed"] = bool(getattr(img, "packed_file", None)) if img else False
        return ("TEX_IMAGE", detail)
    if ntype == "INVERT":
        cin = None
        fac = None
        inputs = getattr(fn, "inputs", None)
        if inputs is not None:
            cin = inputs.get("Color")
            fac = inputs.get("Fac") or inputs.get("Factor")
        cin_kind = "none"
        if cin is not None and cin.is_linked:
            cl = list(cin.links or [])
            if cl:
                cn, cs = peel_reroute(cl[0].from_node, cl[0].from_socket)
                cin_kind = getattr(cn, "type", None)
                detail["cin_name"] = getattr(cn, "name", None)
                detail["cin_out"] = getattr(cs, "name", None)
                if cin_kind == "TEX_IMAGE":
                    img = getattr(cn, "image", None)
                    detail["cin_image"] = getattr(img, "name", None) if img else None
                    detail["cin_cs"] = getattr(getattr(img, "colorspace_settings", None), "name", None) if img else None
        elif cin is not None:
            cin_kind = "const"
        detail["cin"] = cin_kind
        detail["fac_linked"] = bool(getattr(fac, "is_linked", False)) if fac is not None else None
        if fac is not None and not detail["fac_linked"]:
            try:
                detail["fac"] = float(fac.default_value)
            except Exception:
                detail["fac"] = repr(getattr(fac, "default_value", None))
        return ("INVERT", detail)
    if ntype in ("MIX", "MIX_RGB"):
        detail["blend_type"] = getattr(fn, "blend_type", None)
        detail["data_type"] = getattr(fn, "data_type", None)
        return ("MIX", detail)
    if ntype == "VALTORGB":
        return ("VALTORGB", detail)
    if ntype == "CURVE_RGB":
        return ("CURVE_RGB", detail)
    if ntype == "TEX_NOISE":
        return ("TEX_NOISE", detail)
    if ntype == "GROUP":
        detail["node_tree"] = getattr(getattr(fn, "node_tree", None), "name", None)
        return ("GROUP", detail)
    if ntype in ("SEPRGB", "SEPARATE_COLOR", "SEPXYZ"):
        return (str(ntype), detail)
    if ntype == "MATH":
        detail["operation"] = getattr(fn, "operation", None)
        return ("MATH", detail)
    if ntype == "BUMP":
        return ("BUMP", detail)
    return (str(ntype), detail)

print("=== TARGET Plane.002 / Rope ===")
obj = bpy.data.objects.get("Plane.002")
print("object", obj, "type", getattr(obj, "type", None))
mat = None
if obj is not None:
    mats = list(obj.material_slots)
    print("slots", [(s.name, s.material.name if s.material else None) for s in mats])
    for s in mats:
        if s.material and s.material.name == "Rope":
            mat = s.material
            break
    if mat is None and mats:
        mat = mats[0].material
if mat is None:
    mat = bpy.data.materials.get("Rope")
print("mat", mat, "use_nodes", getattr(mat, "use_nodes", None))
if mat and mat.node_tree:
    nt = mat.node_tree
    print("nodes:")
    for n in nt.nodes:
        print(" ", n.name, n.type, n.bl_idname)
    for n in nt.nodes:
        if n.type == "BSDF_PRINCIPLED":
            print("\n--- Principled", n.name, "---")
            for sock_name in ("Normal", "Base Color", "Roughness", "Metallic"):
                sock = n.inputs.get(sock_name)
                print("\n###", sock_name)
                print(dump_sock(sock, 0, 10))
            # Focus Normal Map Color
            normal = n.inputs.get("Normal")
            if normal and normal.is_linked:
                links = list(normal.links or [])
                if links:
                    fn, fs = peel_reroute(links[0].from_node, links[0].from_socket)
                    print("\n=== Normal Map node detail ===")
                    print("node", getattr(fn, "name", None), "type", getattr(fn, "type", None),
                          "space", getattr(fn, "space", None), "uv_map", repr(getattr(fn, "uv_map", None)))
                    if getattr(fn, "type", None) == "NORMAL_MAP":
                        color = fn.inputs.get("Color")
                        strength = fn.inputs.get("Strength")
                        print("Strength linked", getattr(strength, "is_linked", None),
                              "default", getattr(strength, "default_value", None))
                        kind, detail = classify_color_source(color)
                        print("Color source KIND:", kind, "DETAIL:", detail)
                        print("Color dump:")
                        print(dump_sock(color, 0, 10))

print("\n=== CENSUS loft Normal Map Color sources (not TEX_IMAGE) ===")
counts = Counter()
not_tex = Counter()
details = []
for mat in bpy.data.materials:
    if not mat.use_nodes or mat.node_tree is None:
        continue
    for n in mat.node_tree.nodes:
        if n.type != "BSDF_PRINCIPLED":
            continue
        for label in ("Normal", "Coat Normal"):
            sock = n.inputs.get(label)
            if sock is None or not sock.is_linked:
                continue
            links = list(sock.links or [])
            if len(links) != 1:
                continue
            fn, fs = peel_reroute(links[0].from_node, links[0].from_socket)
            if getattr(fn, "type", None) != "NORMAL_MAP":
                counts[("not_NORMAL_MAP", getattr(fn, "type", None), label)] += 1
                continue
            color = fn.inputs.get("Color")
            kind, detail = classify_color_source(color)
            counts[(kind, label)] += 1
            if kind != "TEX_IMAGE":
                not_tex[kind] += 1
                details.append((mat.name, label, kind, detail,
                                getattr(fn, "space", None),
                                repr(getattr(fn, "uv_map", "") or ""),
                                bool(getattr(fn.inputs.get("Strength"), "is_linked", False)) if fn.inputs.get("Strength") else None,
                                float(fn.inputs.get("Strength").default_value) if fn.inputs.get("Strength") and not fn.inputs.get("Strength").is_linked else None))

print("Normal Map Color kinds:")
for k, v in counts.most_common(40):
    print(" ", k, v)
print("not_TEX_IMAGE by type:", dict(not_tex))
print("\nnot-TEX_IMAGE details:")
for d in details:
    print(" ", d)
print("DONE")
