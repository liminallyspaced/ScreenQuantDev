# Duplicate mesh/image detection (the "weight sharing" scan). Strictly read-only:
# nothing here writes to a datablock — relinking lives in apply/objects_apply.py.

import hashlib
import os

import bpy
import numpy as np

from .. import compat

SKIP_IMAGE_SOURCES = ("TILED", "SEQUENCE", "MOVIE")
# Render Result / Viewer Node buffers are not scene assets and expose no pixels.
NON_PIXEL_IMAGE_TYPES = ("RENDER_RESULT", "COMPOSITING")
MAX_HASHED_FLOATS = 1_000_000   # subsample stride cap: sha1 sees at most ~1M floats
# foreach_get must materialize the FULL float buffer before subsampling
# (4K RGBA = 256 MB transient); 4K is the ceiling low-RAM machines can afford.
MAX_PIXEL_HASH_EDGE_PX = 4096

# foreach_get accessor per attribute data_type: (element property, values per
# element, buffer dtype). BYTE_COLOR uses color_srgb so the hash sees the bytes
# Cycles samples. Types absent here (new in a future Blender) abort the hash so
# the mesh is skipped loudly instead of merged on partial evidence.
_ATTRIBUTE_ACCESSORS = {
    "FLOAT": ("value", 1, np.float32),
    "FLOAT2": ("vector", 2, np.float32),
    "FLOAT_VECTOR": ("vector", 3, np.float32),
    "FLOAT_COLOR": ("color", 4, np.float32),
    "BYTE_COLOR": ("color_srgb", 4, np.float32),
    "INT": ("value", 1, np.int32),
    "INT8": ("value", 1, np.int32),
    "INT32_2D": ("value", 2, np.int32),
    "BOOLEAN": ("value", 1, np.bool_),
    "QUATERNION": ("value", 4, np.float32),
    "FLOAT4X4": ("value", 16, np.float32),
}


# ------------------------------------------------------------------- meshes

def mesh_fingerprint(mesh):
    """Cheap prefilter key: exact element counts, material slot names, UV layer
    names, texture space, and the full attribute layout. A layout difference
    alone (extra crease layer, renamed UV map, added color layer) must prevent
    merging. Dot-prefixed attributes are UI state (selection/hide) —
    render-irrelevant."""
    materials = tuple(mat.name if mat is not None else "" for mat in mesh.materials)
    uv_names = tuple(layer.name for layer in mesh.uv_layers)
    attributes = tuple(sorted(
        (attr.name, attr.domain, attr.data_type)
        for attr in getattr(mesh, "attributes", ())
        if not attr.name.startswith(".")
    ))
    return (len(mesh.vertices), len(mesh.edges), len(mesh.loops),
            len(mesh.polygons), materials, uv_names, attributes,
            _texspace_key(mesh))


def _texspace_key(mesh):
    # Generated texture coordinates are mapped through the texture space, so
    # two geometrically identical meshes with different manual texspace render
    # differently anywhere Generated coords are used. Auto texspace derives
    # from the bounding box and therefore matches for identical geometry.
    if not getattr(mesh, "use_auto_texspace", True):
        return (tuple(mesh.texspace_location), tuple(mesh.texspace_size))
    return "auto"


def mesh_content_hash(mesh):
    """sha1 over every render-relevant mesh buffer: geometry, face splits,
    per-face material and smooth flags, all UV layers with names, all generic
    attributes (creases, sharp edges/faces, color layers), deform weights.
    Cost discipline: only ever called on fingerprint-matched candidates."""
    vert_count = len(mesh.vertices)
    loop_count = len(mesh.loops)
    poly_count = len(mesh.polygons)
    digest = hashlib.sha1()
    header = "%d/%d/%d/%d" % (vert_count, loop_count, poly_count, len(mesh.uv_layers))
    digest.update(header.encode("utf-8"))

    coords = np.empty(3 * vert_count, dtype=np.float32)
    mesh.vertices.foreach_get("co", coords)
    digest.update(coords.tobytes())

    loop_verts = np.empty(loop_count, dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", loop_verts)
    digest.update(loop_verts.tobytes())

    # Identical vertex/loop buffers can still differ in face splits or per-face
    # material assignment — merging those would change the render.
    poly_sizes = np.empty(poly_count, dtype=np.int32)
    mesh.polygons.foreach_get("loop_total", poly_sizes)
    digest.update(poly_sizes.tobytes())
    poly_materials = np.empty(poly_count, dtype=np.int32)
    mesh.polygons.foreach_get("material_index", poly_materials)
    digest.update(poly_materials.tobytes())

    digest.update(_face_smooth_bytes(mesh, poly_count))
    _hash_uv_layers(digest, mesh, loop_count)
    _hash_attributes(digest, mesh)
    digest.update(_deform_weight_bytes(mesh))
    return digest.hexdigest()


def _face_smooth_bytes(mesh, poly_count):
    # Shade-smooth state. Probe-verified on 4.5.5 and 5.1.2: polygon use_smooth
    # exists on both and mirrors the sharp_face attribute, which can be absent
    # on all-smooth meshes — so hash the flags directly (guarded for future RNA
    # drift; a missing property degrades identically for every candidate).
    try:
        flags = np.empty(poly_count, dtype=np.bool_)
        mesh.polygons.foreach_get("use_smooth", flags)
        return flags.tobytes()
    except (AttributeError, RuntimeError, TypeError):
        return b""


def _hash_uv_layers(digest, mesh, loop_count):
    # Every layer WITH its name: shaders address UV maps by name, so a rename
    # alone changes the render. active_render decides the default map.
    for layer in mesh.uv_layers:
        tag = "uv:%s:%d" % (layer.name, bool(getattr(layer, "active_render", False)))
        digest.update(tag.encode("utf-8"))
        uvs = np.empty(2 * loop_count, dtype=np.float32)
        layer.data.foreach_get("uv", uvs)
        digest.update(uvs.tobytes())


def _hash_attributes(digest, mesh):
    # All non-internal attributes: creases, sharp edges/faces, every color
    # layer (not just the active one), generic geometry-nodes data. Unknown
    # data types raise so _confirm_by_hash skips the mesh with a reason.
    for attr in sorted(getattr(mesh, "attributes", ()), key=lambda a: a.name):
        if attr.name.startswith("."):
            continue
        tag = "attr:%s:%s:%s" % (attr.name, attr.domain, attr.data_type)
        digest.update(tag.encode("utf-8"))
        if attr.data_type == "STRING":
            for element in attr.data:
                digest.update(element.value.encode("utf-8") + b"\x00")
            continue
        spec = _ATTRIBUTE_ACCESSORS.get(attr.data_type)
        if spec is None:
            raise ValueError(
                "unsupported attribute type %s (%s)" % (attr.data_type, attr.name))
        prop, width, dtype = spec
        values = np.empty(width * len(attr.data), dtype=dtype)
        attr.data.foreach_get(prop, values)
        digest.update(values.tobytes())


def _deform_weight_bytes(mesh):
    # Deform weights live on the mesh (group index + weight per vertex); the
    # index->name table lives on Object.vertex_groups, which relink never
    # touches — identical weight layers merge safely under any name table.
    # No foreach_get for ragged per-vertex group lists; Python loop, candidates only.
    indices = []
    weights = []
    for vert in mesh.vertices:
        if not vert.groups:
            continue
        for entry in sorted(vert.groups, key=lambda item: item.group):
            indices.append(vert.index)
            indices.append(entry.group)
            weights.append(entry.weight)
    if not indices:
        return b""
    return (np.asarray(indices, dtype=np.int32).tobytes()
            + np.asarray(weights, dtype=np.float32).tobytes())


def find_duplicate_meshes(scene):
    """Contract API: groups of mesh names, keeper (most users) first."""
    return scan_meshes(scene)["groups"]


def scan_meshes(scene):
    """Full mesh scan: {'groups': keeper-first name groups, 'skipped': [{name, reason}]}."""
    meshes, skipped = _collect_scene_meshes(scene)
    by_fingerprint = {}
    for mesh in meshes:
        by_fingerprint.setdefault(mesh_fingerprint(mesh), []).append(mesh)
    groups = []
    for candidates in by_fingerprint.values():
        if len(candidates) >= 2:
            groups.extend(_confirm_by_hash(candidates, skipped))
    groups.sort(key=lambda group: group[0])
    return {"groups": groups, "skipped": skipped}


def _collect_scene_meshes(scene):
    meshes = []
    skipped = []
    seen = set()
    for obj in scene.objects:
        if obj.type != "MESH" or obj.data is None:
            continue
        mesh = obj.data
        pointer = mesh.as_pointer()
        if pointer in seen:
            continue
        seen.add(pointer)
        if compat.is_linked(mesh):
            skipped.append({"name": mesh.name, "reason": "library-linked datablock"})
        elif mesh.shape_keys is not None:
            skipped.append({"name": mesh.name, "reason": "has shape keys"})
        elif getattr(mesh, "has_custom_normals", False):
            # Custom split normals are loop data the hash does not cover.
            skipped.append({"name": mesh.name, "reason": "has custom split normals"})
        else:
            meshes.append(mesh)
    return meshes, skipped


def _confirm_by_hash(candidates, skipped):
    by_hash = {}
    for mesh in candidates:
        try:
            content = mesh_content_hash(mesh)
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            skipped.append({"name": mesh.name, "reason": "content hash failed: %s" % exc})
            continue
        by_hash.setdefault(content, []).append(mesh)
    return [_keeper_first(same) for same in by_hash.values() if len(same) >= 2]


def _keeper_first(datablocks):
    ordered = sorted(datablocks, key=lambda block: (-block.users, block.name))
    return [block.name for block in ordered]


# ------------------------------------------------------------------- images

def image_content_hash(image):
    """sha1 of (shape, colorspace, strided pixel subsample); None = unhashable."""
    if compat.is_linked(image) or image.source in SKIP_IMAGE_SOURCES:
        return None
    if getattr(image, "type", "IMAGE") in NON_PIXEL_IMAGE_TYPES:
        return None
    width, height = image.size[0], image.size[1]
    if width == 0 or height == 0:
        return None
    channels = image.channels or 4
    total = width * height * channels
    had_data = image.has_data
    try:
        buffer = np.empty(total, dtype=np.float32)
        image.pixels.foreach_get(buffer)
    except (MemoryError, RuntimeError, TypeError, ValueError):
        return None
    # Stride over TEXELS, hashing all channels of each sampled one. A stride
    # over raw floats aliases against the 4-float interleave whenever the two
    # share a factor: a 4096x4096 RGBA image took stride 68, which is divisible
    # by 4, so sha1 saw the RED channel only — two textures differing solely in
    # their green/blue/alpha packing hashed identically and were merged.
    texel_stride = max(1, -(-total // MAX_HASHED_FLOATS))
    digest = hashlib.sha1()
    header = "%dx%dx%d:%s:%s" % (width, height, channels,
                                 image.colorspace_settings.name,
                                 getattr(image, "alpha_mode", ""))
    digest.update(header.encode("utf-8"))
    digest.update(buffer.reshape(width * height, channels)[::texel_stride].tobytes())
    _free_pixels_if_loaded_here(image, had_data)
    return digest.hexdigest()


def _free_pixels_if_loaded_here(image, had_data):
    # Hashing may have pulled a large file buffer into RAM; drop it again.
    # Generated/painted images report has_data True beforehand, so unsaved
    # pixels are never freed. Runtime cache only — not a datablock write.
    if had_data or image.source != "FILE":
        return
    try:
        image.buffers_free()
    except (AttributeError, RuntimeError):
        pass


def find_duplicate_images():
    """Contract API: groups of image names, keeper (most users) first."""
    return scan_images()["groups"]


def scan_images():
    """Full image scan: {'groups': keeper-first name groups, 'skipped': [{name, reason}]}."""
    file_backed, in_memory, skipped = _partition_images()
    groups = _fast_path_groups(file_backed)
    grouped = {name for group in groups for name in group}
    pool = [image for image in file_backed if image.name not in grouped] + in_memory
    pool = _drop_oversized(pool, skipped)
    groups.extend(_hash_groups(pool, skipped))
    groups.sort(key=lambda group: group[0])
    return {"groups": groups, "skipped": skipped}


def _partition_images():
    """Split bpy.data.images into path-groupable vs pixel-hashable, with skips."""
    file_backed = []
    in_memory = []
    skipped = []
    for image in bpy.data.images:
        if compat.is_linked(image):
            skipped.append({"name": image.name, "reason": "library-linked datablock"})
        elif image.source in SKIP_IMAGE_SOURCES:
            skipped.append({"name": image.name, "reason": "source %s" % image.source})
        elif getattr(image, "type", "IMAGE") in NON_PIXEL_IMAGE_TYPES:
            skipped.append({"name": image.name, "reason": "internal render buffer"})
        elif _is_file_backed(image):
            file_backed.append(image)
        elif image.size[0] == 0 or image.size[1] == 0:
            skipped.append({"name": image.name, "reason": "no pixel data"})
        else:
            in_memory.append(image)
    return file_backed, in_memory, skipped


def _is_file_backed(image):
    # Packed images render from the packed buffer, not the file on disk, so
    # they take the content-hash path even when a filepath is still set.
    return (
        image.source == "FILE"
        and bool(image.filepath)
        and image.packed_file is None
    )


def _fast_path_groups(file_backed):
    # Same resolved path + size + colorspace = same texture on disk. No pixel
    # loads happen here, regardless of image resolution.
    by_key = {}
    for image in file_backed:
        path = os.path.normcase(os.path.abspath(bpy.path.abspath(image.filepath)))
        key = (path, image.size[0], image.size[1],
               image.colorspace_settings.name, getattr(image, "alpha_mode", ""))
        by_key.setdefault(key, []).append(image)
    return [_keeper_first(same) for same in by_key.values() if len(same) >= 2]


def _drop_oversized(images, skipped):
    kept = []
    for image in images:
        if max(image.size[0], image.size[1]) > MAX_PIXEL_HASH_EDGE_PX:
            skipped.append({
                "name": image.name,
                "reason": "long edge over %d px — pixel hash skipped" % MAX_PIXEL_HASH_EDGE_PX,
            })
        else:
            kept.append(image)
    return kept


def _hash_groups(pool, skipped):
    # Size+colorspace prefilter keeps singletons from ever loading pixels.
    by_size = {}
    for image in pool:
        key = (image.size[0], image.size[1], image.colorspace_settings.name)
        by_size.setdefault(key, []).append(image)
    groups = []
    for candidates in by_size.values():
        if len(candidates) < 2:
            continue
        by_hash = {}
        for image in candidates:
            content = image_content_hash(image)
            if content is None:
                skipped.append({"name": image.name, "reason": "pixels not hashable"})
                continue
            by_hash.setdefault(content, []).append(image)
        groups.extend(_keeper_first(same) for same in by_hash.values() if len(same) >= 2)
    return groups
