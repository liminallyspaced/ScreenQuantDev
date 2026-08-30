# QuantTrace Slice 2bh census: loft Mix -> Base Color Curves on a Mix side.
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

def dump_sock(sock, depth=0, max_depth=8):
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
                     "interpolation", "projection", "extension", "vector_type", "operation"):
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
        for inp in list(getattr(fn, "inputs", []) or []):
            lines.append(dump_sock(inp, depth + 2, max_depth))
    return "\n".join(lines)

def mix_socks(fn):
    fac = None
    a = None
    b = None
    for nm in ("Factor_Float", "Factor", "Fac"):
        fac = fn.inputs.get(nm)
        if fac is not None:
            break
    for nm in ("A_Color", "A"):
        a = fn.inputs.get(nm)
        if a is not None:
            break
    for nm in ("B_Color", "B"):
        b = fn.inputs.get(nm)
        if b is not None:
            break
    return fac, a, b

def classify_side(sock):
    if sock is None:
        return ("none", None, None)
    if not sock.is_linked:
        dv = getattr(sock, "default_value", None)
        try:
            if hasattr(dv, "__len__") and not isinstance(dv, (str, bytes)):
                rgb = tuple(round(float(x), 6) for x in list(dv)[:3])
            else:
                v = round(float(dv), 6) if dv is not None else None
                rgb = (v, v, v)
        except Exception:
            rgb = repr(dv)
        return ("const", rgb, None)
    links = list(sock.links or [])
    if len(links) != 1:
        return ("multi", len(links), None)
    fn, fs = peel_reroute(links[0].from_node, links[0].from_socket)
    ntype = getattr(fn, "type", None)
    if ntype == "CURVE_RGB":
        cin = None
        inputs = getattr(fn, "inputs", None)
        if inputs is not None:
            cin = inputs.get("Color")
        cin_kind = "none"
        cin_detail = None
        if cin is not None and cin.is_linked:
            cl = list(cin.links or [])
            if cl:
                cn, cs = peel_reroute(cl[0].from_node, cl[0].from_socket)
                cin_kind = getattr(cn, "type", None)
                if cin_kind == "TEX_IMAGE":
                    img = getattr(cn, "image", None)
                    csname = getattr(getattr(img, "colorspace_settings", None), "name", None) if img else None
                    packed = bool(getattr(img, "packed_file", None)) if img else False
                    cin_detail = (getattr(img, "name", None), csname, packed, getattr(img, "filepath", None), getattr(cs, "name", None))
                else:
                    cin_detail = getattr(cn, "name", None)
        elif cin is not None:
            dv = getattr(cin, "default_value", None)
            try:
                cin_kind = "const"
                cin_detail = tuple(round(float(x), 6) for x in list(dv)[:3])
            except Exception:
                cin_kind = "const"
                cin_detail = repr(dv)
        fac = None
        if inputs is not None:
            fac = inputs.get("Fac") or inputs.get("Factor")
        fac_l = bool(getattr(fac, "is_linked", False)) if fac is not None else None
        fac_v = None
        if fac is not None and not fac_l:
            try:
                fac_v = float(fac.default_value)
            except Exception:
                fac_v = repr(getattr(fac, "default_value", None))
        return ("CURVE_RGB", {"cin": cin_kind, "cin_detail": cin_detail, "fac_linked": fac_l, "fac": fac_v, "out": getattr(fs, "name", None)}, fn)
    if ntype == "TEX_IMAGE":
        img = getattr(fn, "image", None)
        csname = getattr(getattr(img, "colorspace_settings", None), "name", None) if img else None
        packed = bool(getattr(img, "packed_file", None)) if img else False
        return ("TEX_IMAGE", (getattr(img, "name", None), csname, packed, getattr(img, "filepath", None), getattr(fs, "name", None)), fn)
    if ntype in ("MIX", "MIX_RGB"):
        return ("MIX", (getattr(fn, "blend_type", None), getattr(fn, "data_type", None)), fn)
    return (str(ntype), getattr(fn, "name", None), fn)

print("=== TARGET Object003.015 / Carpet Soft Rug Dark Grey Pattern 2 ===")
obj = bpy.data.objects.get("Object003.015")
print("object", obj, "type", getattr(obj, "type", None))
mat = None
if obj is not None:
    mats = list(obj.material_slots)
    print("slots", [(s.name, s.material.name if s.material else None) for s in mats])
    for s in mats:
        if s.material and "Carpet Soft Rug" in s.material.name:
            mat = s.material
            break
if mat is None:
    mat = bpy.data.materials.get("Carpet Soft Rug Dark Grey Pattern 2")
print("mat", mat, "use_nodes", getattr(mat, "use_nodes", None))
if mat and mat.node_tree:
    nt = mat.node_tree
    print("nodes:")
    for n in nt.nodes:
        print(" ", n.name, n.type, n.bl_idname)
    for n in nt.nodes:
        if n.type == "BSDF_PRINCIPLED":
            print("\n--- Principled", n.name, "---")
            bc = n.inputs.get("Base Color")
            print(dump_sock(bc, 0, 9))

print("\n=== CENSUS Mix->Base Color Curves-on-side ===")
counts = Counter()
side_counts = Counter()
details = []
both_curves_tex = 0
one_curves_tex = 0
curves_other = 0
for mat in bpy.data.materials:
    if not mat.use_nodes or mat.node_tree is None:
        continue
    nt = mat.node_tree
    for n in nt.nodes:
        if n.type != "BSDF_PRINCIPLED":
            continue
        bc = n.inputs.get("Base Color")
        if bc is None or not bc.is_linked:
            continue
        links = list(bc.links or [])
        if len(links) != 1:
            continue
        fn, fs = peel_reroute(links[0].from_node, links[0].from_socket)
        if getattr(fn, "type", None) not in ("MIX", "MIX_RGB"):
            continue
        fac, a, b = mix_socks(fn)
        ka, da, _ = classify_side(a)
        kb, db, _ = classify_side(b)
        a_curves_tex = ka == "CURVE_RGB" and isinstance(da, dict) and da.get("cin") == "TEX_IMAGE"
        b_curves_tex = kb == "CURVE_RGB" and isinstance(da if False else db, dict) and db.get("cin") == "TEX_IMAGE"
        a_curves_other = ka == "CURVE_RGB" and not a_curves_tex
        b_curves_other = kb == "CURVE_RGB" and not b_curves_tex
        if a_curves_tex or b_curves_tex:
            if a_curves_tex and b_curves_tex:
                both_curves_tex += 1
                side_counts["both_curves_tex"] += 1
            else:
                one_curves_tex += 1
                side_counts["one_curves_tex"] += 1
                if a_curves_tex:
                    side_counts["curves_tex_on_A"] += 1
                    side_counts["other_B=" + kb] += 1
                else:
                    side_counts["curves_tex_on_B"] += 1
                    side_counts["other_A=" + ka] += 1
        elif a_curves_other or b_curves_other:
            curves_other += 1
            side_counts["curves_other"] += 1
            if a_curves_other:
                side_counts["curves_other_A_cin=" + str((da or {}).get("cin") if isinstance(da, dict) else da)] += 1
            if b_curves_other:
                side_counts["curves_other_B_cin=" + str((db or {}).get("cin") if isinstance(db, dict) else db)] += 1
        key = (ka, kb)
        counts[key] += 1
        if a_curves_tex or b_curves_tex or a_curves_other or b_curves_other:
            fac_l = bool(getattr(fac, "is_linked", False)) if fac is not None else None
            ftype = None
            if fac is not None and fac.is_linked:
                fl = list(fac.links or [])
                if fl:
                    fnode, fsock = peel_reroute(fl[0].from_node, fl[0].from_socket)
                    ftype = getattr(fnode, "type", None)
            details.append((
                mat.name,
                getattr(fn, "name", None),
                getattr(fn, "blend_type", None),
                getattr(fn, "clamp_factor", None),
                getattr(fn, "clamp_result", None),
                fac_l, ftype,
                ka, da if not isinstance(da, dict) else {k: da[k] for k in ("cin", "cin_detail", "fac_linked", "fac")},
                kb, db if not isinstance(db, dict) else {k: db[k] for k in ("cin", "cin_detail", "fac_linked", "fac")},
            ))

print("Mix A/B type pairs (top):")
for k, v in counts.most_common(30):
    print(" ", k, v)
print("side_counts", dict(side_counts))
print("one_curves_tex", one_curves_tex, "both_curves_tex", both_curves_tex, "curves_other", curves_other)
print("\ncurves-on-mix-side details:")
for d in details:
    print(" ", d)
print("DONE")
