# QuantTrace Slice 2bm census: loft non-Principled surface / Realistic_Glass_01.
from collections import Counter
import bpy

SURFACE_BSDF = {
    "BSDF_PRINCIPLED", "BSDF_GLASS", "BSDF_GLOSSY", "BSDF_DIFFUSE",
    "BSDF_TRANSPARENT", "BSDF_REFRACTION", "BSDF_TRANSLUCENT",
    "BSDF_VELVET", "BSDF_TOON", "BSDF_HAIR", "BSDF_HAIR_PRINCIPLED",
    "BSDF_SHEEN", "EMISSION", "HOLDOUT", "VOLUME_SCATTER",
    "VOLUME_ABSORPTION", "PRINCIPLED_VOLUME", "SUBSURFACE_SCATTERING",
    "MIX_SHADER", "ADD_SHADER", "GROUP",
}


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


def describe_socket_default(sock):
    if sock is None:
        return None
    try:
        v = sock.default_value
        if hasattr(v, "__len__") and not isinstance(v, str):
            return tuple(float(x) for x in list(v)[:4])
        return float(v)
    except Exception:
        return repr(getattr(sock, "default_value", None))


def walk_surface(node, depth=0, seen=None, lines=None, max_depth=12):
    if lines is None:
        lines = []
    if seen is None:
        seen = set()
    if node is None or depth > max_depth:
        return lines
    nid = id(node)
    if nid in seen:
        lines.append(("  " * depth) + f"{node.type} {node.name} (cycle)")
        return lines
    seen.add(nid)
    extra = ""
    if getattr(node, "type", None) == "BSDF_GLASS":
        dist = getattr(node, "distribution", None)
        col = describe_socket_default(node.inputs.get("Color"))
        rough = describe_socket_default(node.inputs.get("Roughness"))
        ior = describe_socket_default(node.inputs.get("IOR"))
        extra = f" dist={dist} Color={col} Roughness={rough} IOR={ior}"
    elif getattr(node, "type", None) == "MIX_SHADER":
        fac = node.inputs.get("Fac")
        extra = f" Fac linked={getattr(fac,'is_linked',None)} def={describe_socket_default(fac)}"
    lines.append(("  " * depth) + f"{node.type} '{node.name}'{extra}")
    for inp in list(node.inputs or []):
        if not getattr(inp, "is_linked", False):
            continue
        links = list(inp.links or [])
        if len(links) != 1:
            lines.append(("  " * (depth + 1)) + f"←{inp.name} multi-link {len(links)}")
            continue
        fn, fs = peel(links[0].from_node, links[0].from_socket)
        sock_name = getattr(fs, "name", None)
        if getattr(fn, "type", None) in SURFACE_BSDF or getattr(fn, "type", None) in (
            "FRESNEL", "LAYER_WEIGHT", "MATH", "VALUE", "RGB", "REROUTE",
            "TEX_IMAGE", "NEW_GEOMETRY", "LIGHT_PATH", "INVERT", "MAP_RANGE",
        ):
            lines.append(("  " * (depth + 1)) + f"←{inp.name} from {getattr(fn,'type',None)}.{sock_name}")
            walk_surface(fn, depth + 2, seen, lines, max_depth)
        else:
            lines.append(
                ("  " * (depth + 1))
                + f"←{inp.name} from {getattr(fn,'type',None)}.{sock_name} (leaf)"
            )
            # still walk shader-ish
            if getattr(fn, "outputs", None) and any(
                getattr(o, "type", None) == "SHADER" for o in fn.outputs
            ):
                walk_surface(fn, depth + 2, seen, lines, max_depth)
    return lines


no_prin = []
surface_types = Counter()
glass_examples = []
prin_count = 0
mat_seen = set()

for obj in bpy.data.objects:
    if obj.type != "MESH":
        continue
    for slot in obj.material_slots:
        mat = slot.material
        if mat is None or not mat.use_nodes or mat.node_tree is None:
            continue
        if mat.name in mat_seen:
            continue
        mat_seen.add(mat.name)
        nt = mat.node_tree
        has_prin = any(getattr(n, "type", None) == "BSDF_PRINCIPLED" for n in nt.nodes)
        out = find_output(nt)
        surf_node = None
        if out is not None:
            surf = out.inputs.get("Surface")
            if surf is not None and surf.is_linked:
                links = list(surf.links)
                if links:
                    surf_node, _ = peel(links[0].from_node, links[0].from_socket)
        st = getattr(surf_node, "type", None) if surf_node else None
        surface_types[st] += 1
        if has_prin:
            prin_count += 1
        else:
            no_prin.append((obj.name, mat.name, st))
        if mat.name == "Realistic_Glass_01" or st == "BSDF_GLASS" or (
            st == "MIX_SHADER" and any(getattr(n, "type", None) == "BSDF_GLASS" for n in nt.nodes)
        ):
            glass_examples.append((obj.name, mat.name, st, has_prin))

print("=== loft materials census Slice 2bm ===")
print("materials_seen", len(mat_seen), "with_principled", prin_count, "no_principled", len(no_prin))
print("surface_root_types", dict(surface_types))
print("--- no Principled (obj, mat, surface_root) ---")
for row in no_prin[:40]:
    print(" ", row)
print("no_principled_total", len(no_prin))
print("--- glass-ish examples ---")
for row in glass_examples[:20]:
    print(" ", row)

# Detailed Realistic_Glass_01
print("--- Realistic_Glass_01 Material Output ← Surface graph ---")
found = False
for obj in bpy.data.objects:
    if obj.type != "MESH":
        continue
    for slot in obj.material_slots:
        mat = slot.material
        if mat is None or mat.name != "Realistic_Glass_01":
            continue
        found = True
        print(f"object={obj.name!r} material={mat.name!r}")
        out = find_output(mat.node_tree)
        if out is None:
            print("  NO Material Output")
            continue
        surf = out.inputs.get("Surface")
        if surf is None or not surf.is_linked:
            print("  Surface unlinked")
            continue
        fn, fs = peel(surf.links[0].from_node, surf.links[0].from_socket)
        for line in walk_surface(fn):
            print(line)
        # also dump all node types in tree
        types = Counter(getattr(n, "type", None) for n in mat.node_tree.nodes)
        print("node_type_counts", dict(types))
        # Glass sockets linked?
        for n in mat.node_tree.nodes:
            if getattr(n, "type", None) != "BSDF_GLASS":
                continue
            print(
                "GLASS",
                n.name,
                "distribution",
                getattr(n, "distribution", None),
            )
            for inp in n.inputs:
                print(
                    "  in",
                    inp.name,
                    "linked",
                    inp.is_linked,
                    "def",
                    describe_socket_default(inp),
                )
        break
    if found:
        break
if not found:
    print("Realistic_Glass_01 NOT FOUND")

# Count all Glass BSDF materials and their surface shapes
print("--- all BSDF_GLASS materials surface shapes ---")
glass_shapes = Counter()
for mat in bpy.data.materials:
    if not mat.use_nodes or mat.node_tree is None:
        continue
    glasses = [n for n in mat.node_tree.nodes if getattr(n, "type", None) == "BSDF_GLASS"]
    if not glasses:
        continue
    out = find_output(mat.node_tree)
    st = None
    if out and out.inputs.get("Surface") and out.inputs["Surface"].is_linked:
        fn, _ = peel(out.inputs["Surface"].links[0].from_node)
        st = getattr(fn, "type", None)
    has_prin = any(getattr(n, "type", None) == "BSDF_PRINCIPLED" for n in mat.node_tree.nodes)
    glass_shapes[(st, len(glasses), has_prin)] += 1
    # print one-line summary
    g0 = glasses[0]
    print(
        " glass_mat",
        mat.name,
        "surface",
        st,
        "n_glass",
        len(glasses),
        "has_prin",
        has_prin,
        "dist",
        getattr(g0, "distribution", None),
        "Color",
        describe_socket_default(g0.inputs.get("Color")),
        "Rough",
        describe_socket_default(g0.inputs.get("Roughness")),
        "IOR",
        describe_socket_default(g0.inputs.get("IOR")),
        "ColorLinked",
        g0.inputs.get("Color").is_linked if g0.inputs.get("Color") else None,
        "RoughLinked",
        g0.inputs.get("Roughness").is_linked if g0.inputs.get("Roughness") else None,
        "IORLinked",
        g0.inputs.get("IOR").is_linked if g0.inputs.get("IOR") else None,
        "NormalLinked",
        g0.inputs.get("Normal").is_linked if g0.inputs.get("Normal") else None,
    )
print("glass_shapes", dict(glass_shapes))
