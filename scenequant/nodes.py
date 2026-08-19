# THE single node-tree walker. Every module that needs image nodes or an
# image -> users map must build on these functions; no other module may
# implement its own walk (the four earlier per-module walkers drifted apart
# on TEX_ENVIRONMENT and world handling). Headless-safe: scene passed in.

import bpy

from .constants import GEOMETRY_TYPES, NODE_GROUP_MAX_DEPTH

IMAGE_NODE_IDNAMES = ("ShaderNodeTexImage", "ShaderNodeTexEnvironment")


def iter_tree_image_nodes(tree, max_depth=NODE_GROUP_MAX_DEPTH):
    """Yield (image, node) for every Image and Environment Texture node.

    Recurses into node groups with a visited set (each group tree walked once,
    so reused groups do not repeat) and a depth cap against cyclic nesting.
    Tolerates tree=None.
    """
    yield from _walk_tree(tree, set(), 0, max_depth)


def _walk_tree(tree, visited, depth, max_depth):
    if tree is None or depth > max_depth or tree in visited:
        return
    visited.add(tree)
    for node in tree.nodes:
        if node.bl_idname in IMAGE_NODE_IDNAMES:
            if node.image is not None:
                yield node.image, node
        elif node.type == "GROUP" and node.node_tree is not None:
            yield from _walk_tree(node.node_tree, visited, depth + 1, max_depth)


def iter_render_image_nodes(scene):
    """Yield (image, node, owner) for the whole render-enabled scene.

    Walks the materials of every renderable-geometry object (GEOMETRY_TYPES)
    with hide_render False, then scene.world's tree. owner is the Material or
    World datablock the node lives under; each material is walked once.
    """
    seen_materials = set()
    for obj in scene.objects:
        if obj.type not in GEOMETRY_TYPES or obj.hide_render:
            continue
        for slot in getattr(obj, "material_slots", ()):
            material = slot.material
            if material is None or material in seen_materials:
                continue
            seen_materials.add(material)
            for image, node in iter_tree_image_nodes(getattr(material, "node_tree", None)):
                yield image, node, material
    world = scene.world
    if world is not None:
        for image, node in iter_tree_image_nodes(getattr(world, "node_tree", None)):
            yield image, node, world


def material_image_users(scene):
    """LEGACY journal shape: {image_name: [(material_name, node_name), ...]}.

    Materials only — TEX_SWAP revert resolves these pairs via
    bpy.data.materials, so world/environment images must NEVER appear here
    (use all_render_images for the complete picture).
    """
    users = {}
    for image, node, owner in iter_render_image_nodes(scene):
        if not isinstance(owner, bpy.types.Material):
            continue
        pairs = users.setdefault(image.name, [])
        pair = (owner.name, node.name)
        if pair not in pairs:
            pairs.append(pair)
    return users


def all_render_images(scene):
    """Every render-referenced image, world/environment textures included.

    Returns {image_name: {"world": bool, "owners": [(kind, owner_name,
    node_name), ...]}} with kind 'MATERIAL' or 'WORLD'. Name-keyed: check
    image_name_collisions() before trusting a name to identify one datablock.
    """
    images = {}
    for image, node, owner in iter_render_image_nodes(scene):
        entry = images.setdefault(image.name, {"world": False, "owners": []})
        is_world = isinstance(owner, bpy.types.World)
        entry["world"] = entry["world"] or is_world
        owner_entry = ("WORLD" if is_world else "MATERIAL", owner.name, node.name)
        if owner_entry not in entry["owners"]:
            entry["owners"].append(owner_entry)
    return images


def image_name_collisions():
    """Image names borne by more than one datablock (local vs linked libraries
    each have their own name namespace, so bpy.data.images can hold several).
    Name-keyed maps are ambiguous for these names; consumers that act by name
    (quantize, dedup, per-image savings) must skip them honestly.
    """
    seen = set()
    collisions = set()
    for image in bpy.data.images:
        if image.name in seen:
            collisions.add(image.name)
        else:
            seen.add(image.name)
    return collisions
