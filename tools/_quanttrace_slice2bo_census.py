"""Slice 2bo census: Mix Shader Fac←MATH (Light Path nest) in loft.

Cite Cycles shader_nodes.h:
  MathNode: SOCKET_IN_FLOAT Value1/Value2/Value3, SOCKET_OUT_FLOAT Value,
            SOCKET_ENUM math_type (add/subtract/multiply/divide/power/
            minimum/maximum/greater_than/less_than/...), SOCKET_BOOLEAN use_clamp.
  LightPathNode: SOCKET_OUT_FLOAT Is * Ray (0..6) PLUS Ray Length, Ray Depth,
            Transparent Depth (float outs, not Is * Ray). Slice 2bn packed
            Is * Ray only; Ray Depth currently refused.

Do NOT evaluate Light Path at pack time (ray-state).
"""
from collections import Counter
import os
import sys
import bpy

def _maybe_open_blend():
    a = sys.argv
    extra = a[a.index("--") + 1 :] if "--" in a else []
    for cand in extra + a:
        if cand.endswith(".blend") and os.path.isfile(cand):
            print("CENSUS open", cand)
            bpy.ops.wm.open_mainfile(filepath=cand)
            return
    print("CENSUS no blend argv; using current file", bpy.data.filepath)

_maybe_open_blend()


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
        return (
            f"GLASS dist={getattr(node, 'distribution', None)} "
            f"ColorL={node.inputs['Color'].is_linked} Color={sock_def(node.inputs.get('Color'))} "
            f"RoughL={node.inputs['Roughness'].is_linked} Rough={sock_def(node.inputs.get('Roughness'))} "
            f"IORL={node.inputs['IOR'].is_linked} IOR={sock_def(node.inputs.get('IOR'))} "
            f"NormL={node.inputs['Normal'].is_linked}"
        )
    if t == "BSDF_TRANSPARENT":
        return (
            f"TRANSPARENT ColorL={node.inputs['Color'].is_linked} "
            f"Color={sock_def(node.inputs.get('Color'))}"
        )
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
        return f"GROUP {getattr(node, 'node_tree', None) and node.node_tree.name}"
    return t


def dump_math_input(inp, depth, indent):
    """Dump one Math Value input: unlinked float / VALUE / LIGHT_PATH / nested MATH."""
    name = getattr(inp, "name", "?")
    if not getattr(inp, "is_linked", False):
        print(f"{indent}{name}: UNLINKED def={sock_def(inp)}")
        return {"kind": "const", "value": sock_def(inp), "depth": depth}
    links = list(inp.links or [])
    if len(links) != 1:
        print(f"{indent}{name}: multi {len(links)}")
        return {"kind": "multi", "n": len(links), "depth": depth}
    fn, fs = peel(links[0].from_node, links[0].from_socket)
    ftype = getattr(fn, "type", None)
    fsname = getattr(fs, "name", None)
    if ftype == "LIGHT_PATH":
        print(f"{indent}{name}: LIGHT_PATH.{fsname}  (depth={depth})")
        return {"kind": "lightpath", "socket": fsname, "depth": depth}
    if ftype == "VALUE":
        print(f"{indent}{name}: VALUE def={sock_def(fn.outputs[0] if fn.outputs else None)}  (depth={depth})")
        return {"kind": "value", "value": sock_def(fn.outputs[0] if fn.outputs else None), "depth": depth}
    if ftype == "MATH":
        print(
            f"{indent}{name}: MATH op={getattr(fn, 'operation', None)} "
            f"clamp={getattr(fn, 'use_clamp', None)}  (depth={depth})"
        )
        dump_math_node(fn, depth + 1, indent + "  ")
        return {"kind": "math", "op": getattr(fn, "operation", None), "depth": depth}
    print(f"{indent}{name}: {ftype}.{fsname}  (depth={depth})  NOT in 2bo ABI")
    return {"kind": ftype, "socket": fsname, "depth": depth}


def dump_math_node(node, depth, indent):
    op = getattr(node, "operation", None)
    clamp = getattr(node, "use_clamp", None)
    print(f"{indent}MathNode op={op} clamp={clamp} nest_depth={depth}")
    # Blender 5 Math: Value, Value_001, Value_002 (or Value1/Value2/Value3)
    for inp in node.inputs:
        dump_math_input(inp, depth, indent)


def describe_fac_deep(mix):
    fac = mix.inputs.get("Fac") or mix.inputs.get("Factor")
    if fac is None:
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
    return f"{getattr(fn, 'type', None)}.{getattr(fs, 'name', None)} op={getattr(fn, 'operation', None)}"


def mix_shape(mix):
    fac_desc = describe_fac_deep(mix)
    sh0 = mix.inputs.get("Shader")
    sh1 = mix.inputs.get("Shader_001")
    c0 = c1 = None
    if sh0 and sh0.is_linked and sh0.links:
        c0, _ = peel(sh0.links[0].from_node)
    if sh1 and sh1.is_linked and sh1.links:
        c1, _ = peel(sh1.links[0].from_node)
    return fac_desc, describe_closure(c0), describe_closure(c1), getattr(c0, "type", None), getattr(c1, "type", None)


print("=== Cite Cycles shader_nodes.h ===")
print("  MathNode: Value1/Value2/Value3 in, Value out, math_type, use_clamp")
print("  LightPathNode: Is * Ray 0..6 PLUS Ray Length / Ray Depth / Transparent Depth")
print("  MixClosureNode: Fac / Closure1 / Closure2")
print()

shapes = Counter()
math_root = []
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
        if "MATH" in str(fac_d):
            math_root.append((obj.name, mat.name, fac_d, d0, d1, t0, t1))

print("=== Mix-root surface shapes (count by Fac, Shader0, Shader1 types) ===")
for k, v in shapes.most_common():
    print(f"  n={v} Fac={k[0]!r} Shader={k[1]} Shader_001={k[2]}")

print(f"\n=== Mix-root Fac←MATH materials n={len(math_root)} ===")
for row in math_root:
    print(" ", row)

print("\n=== DETAIL Realistic_Glass_01 Surface graph ===")
mat = bpy.data.materials.get("Realistic_Glass_01")
if mat is None:
    print("  NOT FOUND")
else:
    out = find_output(mat.node_tree)
    root, _ = peel(out.inputs["Surface"].links[0].from_node)
    print(" root", root.type, root.name)
    if root.type == "MIX_SHADER":
        fac_d, d0, d1, t0, t1 = mix_shape(root)
        print("  Fac", fac_d)
        print("  Shader", d0)
        print("  Shader_001", d1)
        fac = root.inputs.get("Fac") or root.inputs.get("Factor")
        if fac and fac.is_linked:
            links = list(fac.links)
            fn, fs = peel(links[0].from_node, links[0].from_socket)
            print(f"  Fac peeled type={getattr(fn,'type',None)} sock={getattr(fs,'name',None)}")
            if getattr(fn, "type", None) == "MATH":
                dump_math_node(fn, 0, "    ")
        sh0 = root.inputs.get("Shader")
        sh1 = root.inputs.get("Shader_001")
        for label, sh in (("Shader", sh0), ("Shader_001", sh1)):
            if sh and sh.is_linked:
                n0, _ = peel(sh.links[0].from_node)
                print(f"  {label} hop type={getattr(n0,'type',None)}")
                if getattr(n0, "type", None) == "MIX_SHADER":
                    f2, a, b, ta, tb = mix_shape(n0)
                    print("    INNER Mix hop Fac", f2)
                    print("      Shader", a)
                    print("      Shader_001", b)

print("\n=== DETAIL other Mix Fac←MATH materials (Fac graph only) ===")
for obj_name, mat_name, fac_d, d0, d1, t0, t1 in math_root:
    if mat_name == "Realistic_Glass_01":
        continue
    mat = bpy.data.materials.get(mat_name)
    if mat is None:
        continue
    print(f"\n  --- {obj_name} / {mat_name} ---")
    print(f"    Fac={fac_d} Shader={t0} Shader_001={t1}")
    out = find_output(mat.node_tree)
    root, _ = peel(out.inputs["Surface"].links[0].from_node)
    fac = root.inputs.get("Fac") or root.inputs.get("Factor")
    if fac and fac.is_linked:
        links = list(fac.links)
        fn, fs = peel(links[0].from_node, links[0].from_socket)
        if getattr(fn, "type", None) == "MATH":
            dump_math_node(fn, 0, "    ")
