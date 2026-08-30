"""Slice 2bn census: Mix Shader + Light Path glass shapes in loft."""
from collections import Counter
import bpy

def peel(node, sock=None):
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

def find_output(nt):
    for n in nt.nodes:
        if getattr(n, "type", None) == "OUTPUT_MATERIAL":
            return n
    return None

def sock_def(sock):
    if sock is None:
        return None
    try:
        v = sock.default_value
        if hasattr(v, "__len__") and not isinstance(v, str):
            return tuple(float(x) for x in list(v)[:4])
        return float(v)
    except Exception:
        return repr(getattr(sock, "default_value", None))

def describe_closure(node):
    if node is None:
        return "None"
    t = getattr(node, "type", None)
    if t == "BSDF_GLASS":
        return (f"GLASS dist={getattr(node,'distribution',None)} "
                f"ColorL={node.inputs['Color'].is_linked} Color={sock_def(node.inputs.get('Color'))} "
                f"RoughL={node.inputs['Roughness'].is_linked} Rough={sock_def(node.inputs.get('Roughness'))} "
                f"IORL={node.inputs['IOR'].is_linked} IOR={sock_def(node.inputs.get('IOR'))} "
                f"NormL={node.inputs['Normal'].is_linked}")
    if t == "BSDF_TRANSPARENT":
        return (f"TRANSPARENT ColorL={node.inputs['Color'].is_linked} "
                f"Color={sock_def(node.inputs.get('Color'))}")
    if t == "BSDF_GLOSSY":
        return f"GLOSSY ColorL={node.inputs['Color'].is_linked} RoughL={node.inputs['Roughness'].is_linked}"
    if t == "BSDF_REFRACTION":
        return f"REFRACTION ColorL={node.inputs['Color'].is_linked}"
    if t == "BSDF_PRINCIPLED":
        return "PRINCIPLED"
    if t == "MIX_SHADER":
        return "MIX_SHADER(nested)"
    if t == "ADD_SHADER":
        return "ADD_SHADER"
    if t == "SUBSURFACE_SCATTERING":
        return "SSS"
    if t == "GROUP":
        return f"GROUP {getattr(node,'node_tree',None) and node.node_tree.name}"
    return t

def describe_fac(mix):
    fac = mix.inputs.get("Fac") or mix.inputs.get("Factor")
    if fac is None:
        # Blender 4+/5 may rename
        for inp in mix.inputs:
            if "Fac" in inp.name or inp.name == "Factor":
                fac = inp
                break
    if fac is None:
        return "NO_FAC"
    if not fac.is_linked:
        return f"UNLINKED def={sock_def(fac)}"
    links = list(fac.links)
    if len(links) != 1:
        return f"multi {len(links)}"
    fn, fs = peel(links[0].from_node, links[0].from_socket)
    return f"{getattr(fn,'type',None)}.{getattr(fs,'name',None)}"

def mix_shape(mix):
    # Blender 5: inputs Factor, Shader, Shader_001
    fac_desc = describe_fac(mix)
    sh0 = mix.inputs.get("Shader")
    sh1 = mix.inputs.get("Shader_001")
    c0 = c1 = None
    if sh0 and sh0.is_linked and sh0.links:
        c0, _ = peel(sh0.links[0].from_node)
    if sh1 and sh1.is_linked and sh1.links:
        c1, _ = peel(sh1.links[0].from_node)
    return fac_desc, describe_closure(c0), describe_closure(c1), getattr(c0,'type',None), getattr(c1,'type',None)

# Count Mix-root materials
shapes = Counter()
details = []
mat_seen = set()
for obj in bpy.data.objects:
    if obj.type != "MESH":
        continue
    for slot in obj.material_slots:
        mat = slot.material
        if mat is None or mat.node_tree is None:
            continue
        if mat.name in mat_seen:
            continue
        mat_seen.add(mat.name)
        out = find_output(mat.node_tree)
        if out is None:
            continue
        surf = out.inputs.get("Surface")
        if surf is None or not surf.is_linked:
            continue
        root, _ = peel(surf.links[0].from_node)
        if getattr(root, "type", None) != "MIX_SHADER":
            continue
        fac_d, d0, d1, t0, t1 = mix_shape(root)
        key = (fac_d, t0, t1)
        shapes[key] += 1
        details.append((obj.name, mat.name, fac_d, d0, d1))

print("=== Mix-root surface shapes (count by Fac, Shader0, Shader1 types) ===")
for k, v in shapes.most_common():
    print(f"  n={v} Fac={k[0]!r} Shader={k[1]} Shader_001={k[2]}")

print("\n=== Mix-root details ===")
for row in details:
    print(" ", row)

# Focus materials
for name in ("Realistic_Glass_01", "Material.001", "lente", "DA_GLASS_Refractive_PURE.001", "+luz_vidro1", "Neon"):
    print(f"\n=== DETAIL {name} ===")
    mat = bpy.data.materials.get(name)
    if mat is None:
        print("  NOT FOUND")
        continue
    out = find_output(mat.node_tree)
    root, _ = peel(out.inputs["Surface"].links[0].from_node)
    print(" root", root.type, root.name)
    if root.type == "MIX_SHADER":
        fac_d, d0, d1, t0, t1 = mix_shape(root)
        print("  Fac", fac_d)
        print("  Shader", d0)
        print("  Shader_001", d1)
        # if Shader is nested Mix, peel one hop
        sh0 = root.inputs.get("Shader")
        if sh0 and sh0.is_linked:
            n0, _ = peel(sh0.links[0].from_node)
            if getattr(n0, "type", None) == "MIX_SHADER":
                f2, a, b, ta, tb = mix_shape(n0)
                print("  INNER Mix hop Fac", f2)
                print("    Shader", a)
                print("    Shader_001", b)

# Classic shadow-glass candidates: Fac LightPath Is Shadow Ray + Glass + Transparent (either order)
classic = 0
near = []
for obj in bpy.data.objects:
    if obj.type != "MESH":
        continue
    for slot in obj.material_slots:
        mat = slot.material
        if mat is None or mat.node_tree is None:
            continue
        out = find_output(mat.node_tree)
        if not out:
            continue
        surf = out.inputs.get("Surface")
        if not surf or not surf.is_linked:
            continue
        root, _ = peel(surf.links[0].from_node)
        if getattr(root, "type", None) != "MIX_SHADER":
            continue
        fac_d, d0, d1, t0, t1 = mix_shape(root)
        types = {t0, t1}
        if "Is Shadow Ray" in str(fac_d) and types <= {"BSDF_GLASS", "BSDF_TRANSPARENT"} and len(types) == 2:
            classic += 1
            near.append((mat.name, "CLASSIC", fac_d, d0, d1))
        elif types & {"BSDF_GLASS", "BSDF_TRANSPARENT"}:
            near.append((mat.name, "NEAR", fac_d, t0, t1))

print("\n=== classic shadow-glass count", classic, "===")
for row in near:
    print(" ", row)
