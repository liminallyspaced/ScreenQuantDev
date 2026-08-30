# QuantTrace Slice 2bl census: loft SEPARATE_COLOR → Bump.Height.
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

channels = Counter()
color_src = Counter()
modes = Counter()
examples = []
for obj in bpy.data.objects:
    if obj.type != "MESH":
        continue
    for slot in obj.material_slots:
        mat = slot.material
        if mat is None or not mat.use_nodes:
            continue
        for n in mat.node_tree.nodes:
            if n.type != "BUMP":
                continue
            height = n.inputs.get("Height")
            if height is None or not height.is_linked:
                continue
            links = list(height.links)
            if len(links) != 1:
                continue
            fn, fs = peel(links[0].from_node, links[0].from_socket)
            if getattr(fn, "type", None) not in ("SEPARATE_COLOR", "SEPRGB"):
                continue
            channels[getattr(fs, "name", None)] += 1
            modes[getattr(fn, "mode", None)] += 1
            cin = fn.inputs.get("Color") if fn.inputs else None
            cn = None
            if cin is None or not cin.is_linked:
                color_src[("unlinked", None)] += 1
            else:
                cl = list(cin.links)
                cn, cs = peel(cl[0].from_node, cl[0].from_socket)
                color_src[(getattr(cn, "type", None), getattr(cs, "name", None))] += 1
            examples.append(
                (obj.name, mat.name, getattr(fs, "name", None),
                 getattr(fn, "mode", None),
                 getattr(cn, "type", None) if cin and cin.is_linked else None)
            )

print("SEPARATE→Bump.Height count", sum(channels.values()))
print("channels", dict(channels))
print("modes", dict(modes))
print("Color sources", dict(color_src))
for e in examples[:20]:
    print(" ex", e)
