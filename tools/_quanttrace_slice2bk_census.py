# QuantTrace Slice 2bk census: loft Mix → Principled.Specular Tint.
from collections import Counter
import bpy

def peel(node, sock):
    for _ in range(64):
        if node is None or getattr(node, "type", None) != "REROUTE":
            return node, sock
        if not node.inputs or not node.inputs[0].is_linked:
            return node, sock
        links = list(node.inputs[0].links or [])
        if len(links) != 1:
            return node, sock
        node = links[0].from_node
        sock = links[0].from_socket
    return node, sock

def mix_rgba_socks(node):
    fac = a = b = None
    for s in node.inputs:
        ident = getattr(s, "identifier", s.name)
        if ident in ("Factor_Float", "Fac") or (s.name in ("Factor", "Fac") and getattr(s, "type", None) == "VALUE"):
            fac = fac or s
        if ident == "A_Color":
            a = s
        if ident == "B_Color":
            b = s
    if a is None or b is None:
        # MixRGB fallback
        inputs = list(node.inputs)
        if len(inputs) >= 3:
            fac = fac or inputs[0]
            a = a or inputs[1]
            b = b or inputs[2]
    return fac, a, b

def side_desc(sock):
    if sock is None:
        return ("missing",)
    if not sock.is_linked:
        dv = sock.default_value
        if hasattr(dv, "__len__") and not isinstance(dv, (str, bytes)):
            return ("const", tuple(round(float(dv[i]), 4) for i in range(3)))
        return ("const", dv)
    links = list(sock.links)
    fn, fs = peel(links[0].from_node, links[0].from_socket)
    chain = [getattr(fn, "type", None)]
    cur = fn
    for _ in range(4):
        if getattr(cur, "type", None) in ("HUE_SAT", "GAMMA", "CURVE_RGB"):
            cin = cur.inputs.get("Color")
            if cin and cin.is_linked:
                cur = peel(cin.links[0].from_node, cin.links[0].from_socket)[0]
                chain.append(getattr(cur, "type", None))
                continue
        break
    return (tuple(chain), getattr(fs, "name", None))

blend = Counter()
shape = Counter()
examples = []
for obj in bpy.data.objects:
    if obj.type != "MESH":
        continue
    for slot in obj.material_slots:
        mat = slot.material
        if mat is None or not mat.use_nodes:
            continue
        for n in mat.node_tree.nodes:
            if n.type != "BSDF_PRINCIPLED":
                continue
            st = n.inputs.get("Specular Tint")
            if st is None or not st.is_linked:
                continue
            fn, fs = peel(st.links[0].from_node, st.links[0].from_socket)
            if getattr(fn, "type", None) not in ("MIX", "MIX_RGB"):
                continue
            bt = str(getattr(fn, "blend_type", "MIX") or "MIX")
            dt = str(getattr(fn, "data_type", "") or "")
            blend[(bt, dt)] += 1
            fac, a, b = mix_rgba_socks(fn)
            fac_l = bool(fac and fac.is_linked)
            fac_src = "unlinked"
            if fac_l:
                fnode, _ = peel(fac.links[0].from_node, fac.links[0].from_socket)
                fac_src = getattr(fnode, "type", None)
            ad, bd = side_desc(a), side_desc(b)
            key = (ad[0] if isinstance(ad[0], str) else ad[0], bd[0] if isinstance(bd[0], str) else bd[0], fac_src, bt)
            shape[key] += 1
            examples.append((obj.name, mat.name, bt, fac_src, float(fac.default_value) if fac and not fac_l else None, ad, bd,
                             bool(getattr(fn, "clamp_factor", False))))

print("MIX→Specular Tint count", sum(blend.values()))
print("blend", dict(blend))
print("shapes", dict(shape))
for e in examples:
    print(" ex", e)
