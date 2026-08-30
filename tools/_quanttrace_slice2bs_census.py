"""Slice 2bs census: Mix.004 leftover in loft Realistic_Glass_01 after 2bp.

Cite Cycles shader_nodes.h / shader_nodes.cpp:
  MixClosureNode: SOCKET_IN_FLOAT Fac, SOCKET_IN_CLOSURE Closure1/Closure2,
                  SOCKET_OUT_CLOSURE Closure
  AddClosureNode: SOCKET_IN_CLOSURE Closure1/Closure2, SOCKET_OUT_CLOSURE Closure
  GlassBsdfNode: Color/Roughness/IOR/Normal/Distribution
  TransparentBsdfNode: Color
  RefractionBsdfNode: Color/Roughness/IOR/Normal/Distribution
  GlossyBsdfNode: Color/Roughness/Normal/Distribution
  SubsurfaceScatteringNode: Color/Scale/Radius/IOR/Roughness/Anisotropy
  RGBRampNode: Fac in, Color/Alpha out (ramp LUT)

Do NOT invent the graph — print Mix.004 Fac/Shader/Shader_001 fully.
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


def describe_closure(node, depth=0):
    if node is None:
        return "None"
    t = getattr(node, "type", None)
    indent = "  " * depth
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
        return (
            f"GLOSSY dist={getattr(node, 'distribution', None)} "
            f"ColorL={node.inputs['Color'].is_linked} Color={sock_def(node.inputs.get('Color'))} "
            f"RoughL={node.inputs['Roughness'].is_linked} Rough={sock_def(node.inputs.get('Roughness'))} "
            f"NormL={node.inputs['Normal'].is_linked}"
        )
    if t == "BSDF_REFRACTION":
        return (
            f"REFRACTION dist={getattr(node, 'distribution', None)} "
            f"ColorL={node.inputs['Color'].is_linked} Color={sock_def(node.inputs.get('Color'))} "
            f"RoughL={node.inputs['Roughness'].is_linked} "
            f"IORL={node.inputs['IOR'].is_linked} IOR={sock_def(node.inputs.get('IOR'))}"
        )
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
    ftype = getattr(fn, "type", None)
    fsname = getattr(fs, "name", None)
    if ftype == "MATH":
        return f"MATH.{fsname} op={getattr(fn, 'operation', None)} clamp={getattr(fn, 'use_clamp', None)}"
    if ftype == "LIGHT_PATH":
        return f"LIGHT_PATH.{fsname}"
    if ftype == "VALUE":
        return f"VALUE def={sock_def(fn.outputs[0] if fn.outputs else None)}"
    return f"{ftype}.{fsname} op={getattr(fn, 'operation', None)}"


def dump_math_input(inp, depth, indent):
    name = getattr(inp, "name", "?")
    if not getattr(inp, "is_linked", False):
        print(f"{indent}{name}: UNLINKED def={sock_def(inp)}")
        return
    links = list(inp.links or [])
    if len(links) != 1:
        print(f"{indent}{name}: multi {len(links)}")
        return
    fn, fs = peel(links[0].from_node, links[0].from_socket)
    ftype = getattr(fn, "type", None)
    fsname = getattr(fs, "name", None)
    if ftype == "LIGHT_PATH":
        print(f"{indent}{name}: LIGHT_PATH.{fsname}  (depth={depth})")
        return
    if ftype == "VALUE":
        print(f"{indent}{name}: VALUE def={sock_def(fn.outputs[0] if fn.outputs else None)}")
        return
    if ftype == "MATH":
        print(f"{indent}{name}: MATH op={getattr(fn, 'operation', None)} clamp={getattr(fn, 'use_clamp', None)}")
        dump_math_node(fn, depth + 1, indent + "  ")
        return
    print(f"{indent}{name}: {ftype}.{fsname}")


def dump_math_node(node, depth, indent):
    print(f"{indent}MathNode op={getattr(node, 'operation', None)} clamp={getattr(node, 'use_clamp', None)} nest_depth={depth}")
    for inp in node.inputs:
        dump_math_input(inp, depth, indent)


def mix_shape(mix):
    fac_desc = describe_fac_deep(mix)
    sh0 = mix.inputs.get("Shader")
    sh1 = mix.inputs.get("Shader_001")
    c0 = c1 = None
    if sh0 and sh0.is_linked and sh0.links:
        c0, _ = peel(sh0.links[0].from_node)
    if sh1 and sh1.is_linked and sh1.links:
        c1, _ = peel(sh1.links[0].from_node)
    return fac_desc, describe_closure(c0), describe_closure(c1), getattr(c0, "type", None), getattr(c1, "type", None), c0, c1


def dump_mix_full(mix, label, indent=""):
    fac_d, d0, d1, t0, t1, c0, c1 = mix_shape(mix)
    print(f"{indent}{label} Mix name={mix.name}")
    print(f"{indent}  Fac: {fac_d}")
    fac = mix.inputs.get("Fac") or mix.inputs.get("Factor")
    if fac and fac.is_linked:
        links = list(fac.links)
        fn, fs = peel(links[0].from_node, links[0].from_socket)
        if getattr(fn, "type", None) == "MATH":
            dump_math_node(fn, 0, indent + "    ")
        elif getattr(fn, "type", None) == "LIGHT_PATH":
            print(f"{indent}    LightPath sock={getattr(fs,'name',None)}")
    print(f"{indent}  Shader: type={t0} {d0}")
    print(f"{indent}  Shader_001: type={t1} {d1}")
    return t0, t1, c0, c1


print("=== Cite Cycles shader_nodes.h ===")
print("  MixClosureNode: Fac / Closure1 / Closure2 → Closure")
print("  GlassBsdfNode: Color Roughness IOR Normal Distribution")
print("  TransparentBsdfNode: Color")
print("  AddClosureNode: Closure1 / Closure2")
print("  LightPathNode: Is * Ray")
print("  MathNode: Value1/Value2, math_type, use_clamp")
print()

# Nested Mix census across loft
nested_shapes = Counter()
nested_mats = []
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
        fac_d, d0, d1, t0, t1, c0, c1 = mix_shape(root)
        has_nested = "MIX_SHADER" in {t0, t1}
        if has_nested:
            key = (fac_d, t0, t1)
            nested_shapes[key] += 1
            nested_mats.append((obj.name, mat.name, fac_d, t0, t1, d0, d1))

print("=== Mix-root with nested MIX_SHADER n=%d shapes ===" % sum(nested_shapes.values()))
for k, v in nested_shapes.most_common():
    print(f"  n={v} Fac={k[0]!r} Shader={k[1]} Shader_001={k[2]}")

print("\n=== Nested Mix materials ===")
for row in nested_mats:
    print(" ", row)

print("\n=== DETAIL Realistic_Glass_01 FULL outer+inner ===")
mat = bpy.data.materials.get("Realistic_Glass_01")
if mat is None:
    print("  NOT FOUND — listing glass-like mats:")
    for m in bpy.data.materials:
        if "glass" in m.name.lower() or "Glass" in m.name:
            print("   ", m.name)
else:
    out = find_output(mat.node_tree)
    root, _ = peel(out.inputs["Surface"].links[0].from_node)
    print(" root", root.type, root.name)
    t0, t1, c0, c1 = dump_mix_full(root, "OUTER", "")
    for label, node in (("Shader", c0), ("Shader_001", c1)):
        if node is not None and getattr(node, "type", None) == "MIX_SHADER":
            print(f"\n--- INNER on {label} ---")
            it0, it1, ic0, ic1 = dump_mix_full(node, "INNER", "  ")
            # If still nested, print one more level
            for ilabel, inode in (("Shader", ic0), ("Shader_001", ic1)):
                if inode is not None and getattr(inode, "type", None) == "MIX_SHADER":
                    print(f"\n--- INNER2 on INNER.{ilabel} ---")
                    dump_mix_full(inode, "INNER2", "    ")
                elif inode is not None and getattr(inode, "type", None) == "ADD_SHADER":
                    print(f"  INNER.{ilabel} is ADD_SHADER — dumping sides")
                    for side in ("Shader", "Shader_001"):
                        s = inode.inputs.get(side)
                        if s and s.is_linked:
                            n2, _ = peel(s.links[0].from_node)
                            print(f"    Add.{side}: {describe_closure(n2)}")

print("\n=== All MIX_SHADER in Realistic_Glass_01 node tree ===")
if mat is not None:
    for n in mat.node_tree.nodes:
        if getattr(n, "type", None) == "MIX_SHADER":
            print(f"  node={n.name}")
            dump_mix_full(n, n.name, "    ")


def dump_node_inputs(node, indent=""):
    if node is None:
        print(f"{indent}None")
        return
    print(f"{indent}node name={node.name} type={getattr(node, 'type', None)}")
    for inp in node.inputs:
        if getattr(inp, "is_linked", False):
            links = list(inp.links or [])
            if len(links) != 1:
                print(f"{indent}  {inp.name}: LINKED n={len(links)}")
                continue
            fn, fs = peel(links[0].from_node, links[0].from_socket)
            print(
                f"{indent}  {inp.name}: LINKED from {getattr(fn, 'type', None)}."
                f"{getattr(fn, 'name', None)} sock={getattr(fs, 'name', None)}"
            )
        else:
            print(f"{indent}  {inp.name}: UNLINKED def={sock_def(inp)}")


def dump_colorramp(node, indent=""):
    print(f"{indent}RGBRampNode name={node.name} type={getattr(node, 'type', None)}")
    cmap = getattr(node, "color_ramp", None)
    if cmap is None:
        print(f"{indent}  color_ramp=None")
        return
    print(f"{indent}  interpolation={getattr(cmap, 'interpolation', None)}")
    print(f"{indent}  hue_interpolation={getattr(cmap, 'hue_interpolation', None)}")
    print(f"{indent}  color_mode={getattr(cmap, 'color_mode', None)}")
    els = list(getattr(cmap, "elements", []) or [])
    print(f"{indent}  n_stops={len(els)}")
    for i, el in enumerate(els):
        pos = float(getattr(el, "position", 0.0))
        col = tuple(float(x) for x in list(el.color)[:4])
        print(f"{indent}  stop[{i}] pos={pos} color={col}")
    fac = node.inputs.get("Fac") or node.inputs.get("Factor")
    if fac is None:
        print(f"{indent}  Fac socket missing")
        return
    if not fac.is_linked:
        print(f"{indent}  Fac UNLINKED def={sock_def(fac)}")
        return
    links = list(fac.links or [])
    if len(links) != 1:
        print(f"{indent}  Fac multi {len(links)}")
        return
    fn, fs = peel(links[0].from_node, links[0].from_socket)
    print(
        f"{indent}  Fac ← {getattr(fn, 'type', None)}.{getattr(fn, 'name', None)} "
        f"sock={getattr(fs, 'name', None)}"
    )
    dump_node_inputs(fn, indent + "    ")


def dump_add_full(node, indent=""):
    print(f"{indent}AddClosureNode name={node.name}")
    for side in ("Shader", "Shader_001"):
        s = node.inputs.get(side)
        if s is None:
            print(f"{indent}  {side}: MISSING")
            continue
        if not s.is_linked:
            print(f"{indent}  {side}: UNLINKED")
            continue
        n2, _ = peel(s.links[0].from_node)
        print(f"{indent}  {side}: {describe_closure(n2, 0)}")
        dump_node_inputs(n2, indent + "    ")
        if getattr(n2, "type", None) == "ADD_SHADER":
            dump_add_full(n2, indent + "    ")
        if getattr(n2, "type", None) == "MIX_SHADER":
            dump_mix_full(n2, f"Add.{side} MIX", indent + "    ")


print("\n=== Slice 2bs ColorRamp.002 Fac MATH dump ===")
print("Cite MixClosureNode Fac/Closure1/Closure2; RGBRampNode Fac; AddClosureNode Closure1/2;")
print("GlassBsdfNode Color/Roughness/IOR; TransparentBsdfNode Color;")
print("RefractionBsdfNode Color/Roughness/IOR; GlossyBsdfNode Color/Roughness;")
print("SubsurfaceScatteringNode Color/Scale/Radius")
mat = bpy.data.materials.get("Realistic_Glass_01")
if mat is None:
    print("Realistic_Glass_01 NOT FOUND")
else:
    mix004 = mat.node_tree.nodes.get("Mix Shader.004")
    if mix004 is None:
        print("Mix Shader.004 not found by name; MIX_SHADER list:")
        for n in mat.node_tree.nodes:
            if getattr(n, "type", None) == "MIX_SHADER":
                print(" ", n.name)
    else:
        print("FOUND Mix Shader.004")
        dump_node_inputs(mix004, "")
        dump_mix_full(mix004, "MIX.004", "")
        fac = mix004.inputs.get("Fac") or mix004.inputs.get("Factor")
        if fac and fac.is_linked:
            fn, fs = peel(fac.links[0].from_node, fac.links[0].from_socket)
            print(f"\n--- Mix.004 Fac node {getattr(fn,'type',None)} {getattr(fn,'name',None)} ---")
            if getattr(fn, "type", None) in ("VALTORGB", "COLORRAMP", "RGBRAMP"):
                dump_colorramp(fn, "  ")
            else:
                dump_node_inputs(fn, "  ")
        for side in ("Shader", "Shader_001"):
            s = mix004.inputs.get(side)
            if s and s.is_linked:
                n2, _ = peel(s.links[0].from_node)
                print(f"\n--- Mix.004.{side} type={getattr(n2,'type',None)} name={getattr(n2,'name',None)} ---")
                dump_node_inputs(n2, "  ")
                if getattr(n2, "type", None) == "ADD_SHADER":
                    dump_add_full(n2, "  ")
                if getattr(n2, "type", None) == "MIX_SHADER":
                    dump_mix_full(n2, f"Mix.004.{side}", "  ")
                if getattr(n2, "type", None) == "BSDF_GLASS":
                    print("  Glass Color/Rough/IOR linked?",
                          n2.inputs["Color"].is_linked,
                          n2.inputs["Roughness"].is_linked,
                          n2.inputs["IOR"].is_linked)
                if getattr(n2, "type", None) == "BSDF_TRANSPARENT":
                    print("  Transparent Color linked?", n2.inputs["Color"].is_linked)


print("\n=== Slice 2bs ColorRamp.002 Fac graph (MATH / NEW_GEOMETRY / HueSat) ===")
print("Cite RGBRampNode Fac; MathNode Value1/Value2; GeometryNode Backfacing;")
print("HSVNode Color/Hue/Sat/Value/Fac; LightPathNode Is * Ray")

def dump_any(node, sock=None, indent="", depth=0):
    if node is None:
        print(f"{indent}None")
        return
    t = getattr(node, "type", None)
    print(f"{indent}type={t} name={getattr(node,'name',None)} sock={getattr(sock,'name',None)} depth={depth}")
    if t == "MATH":
        print(f"{indent}  op={getattr(node,'operation',None)} clamp={getattr(node,'use_clamp',None)}")
        for inp in node.inputs:
            if getattr(inp, "is_linked", False):
                links = list(inp.links or [])
                if len(links) != 1:
                    print(f"{indent}  {inp.name}: multi {len(links)}")
                    continue
                fn, fs = peel(links[0].from_node, links[0].from_socket)
                print(f"{indent}  {inp.name}: LINKED")
                dump_any(fn, fs, indent + "    ", depth + 1)
            else:
                print(f"{indent}  {inp.name}: UNLINKED def={sock_def(inp)}")
        return
    if t in ("HUE_SAT", "HUE_SATURATION"):
        for name in ("Hue", "Saturation", "Value", "Fac", "Factor", "Color"):
            inp = node.inputs.get(name) if hasattr(node.inputs, "get") else None
            if inp is None:
                continue
            if getattr(inp, "is_linked", False):
                links = list(inp.links or [])
                fn, fs = peel(links[0].from_node, links[0].from_socket) if links else (None, None)
                print(f"{indent}  {name}: LINKED from {getattr(fn,'type',None)}.{getattr(fn,'name',None)} sock={getattr(fs,'name',None)}")
                if fn is not None and depth < 6:
                    dump_any(fn, fs, indent + "    ", depth + 1)
            else:
                print(f"{indent}  {name}: UNLINKED def={sock_def(inp)}")
        print(f"{indent}  outputs={[getattr(o,'name',None) for o in node.outputs]}")
        return
    if t in ("NEW_GEOMETRY", "GEOMETRY"):
        print(f"{indent}  outputs={[getattr(o,'name',None) for o in node.outputs]}")
        print(f"{indent}  using sock={getattr(sock,'name',None)}")
        return
    if t == "LIGHT_PATH":
        print(f"{indent}  using sock={getattr(sock,'name',None)}")
        print(f"{indent}  outputs={[getattr(o,'name',None) for o in node.outputs]}")
        return
    if t == "VALUE":
        print(f"{indent}  VALUE def={sock_def(node.outputs[0] if node.outputs else None)}")
        return
    dump_node_inputs(node, indent + "  ")

mat = bpy.data.materials.get("Realistic_Glass_01")
if mat is None:
    print("Realistic_Glass_01 NOT FOUND")
else:
    ramp = None
    for n in mat.node_tree.nodes:
        if getattr(n, "type", None) in ("VALTORGB", "COLORRAMP", "RGBRAMP") and n.name == "ColorRamp.002":
            ramp = n
            break
    if ramp is None:
        print("ColorRamp.002 not found; VALTORGB list:")
        for n in mat.node_tree.nodes:
            if getattr(n, "type", None) in ("VALTORGB", "COLORRAMP", "RGBRAMP"):
                print(" ", n.name)
                dump_colorramp(n, "    ")
    else:
        dump_colorramp(ramp, "")
        fac = ramp.inputs.get("Fac") or ramp.inputs.get("Factor")
        if fac and fac.is_linked:
            fn, fs = peel(fac.links[0].from_node, fac.links[0].from_socket)
            print("\n--- ColorRamp.002 Fac source ---")
            dump_any(fn, fs, "", 0)

print("\n=== Slice 2bs dry pack probe (first PACK_FAIL) ===")
try:
    import os, sys
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.insert(0, root)
    import scenequant
    try:
        scenequant.register()
    except Exception:
        pass
    from scenequant.quanttrace import sync as qt_sync
    scene = bpy.context.scene
    packed = qt_sync.pack_scene(scene, depsgraph=bpy.context.evaluated_depsgraph_get())
    print("PACK_OK n_meshes", len(packed["meshes"]))
except Exception as e:
    print("PACK_FAIL", type(e).__name__, str(e))
