# Apply-layer data-safety regressions for the review's confirmed failure modes
# (P1: tex-swap honesty, edit-mode relink, cross-scene writes, dedup hash
# blind spots, purge fake-user, texture-limit subdiv guard).
#   blender -b --factory-startup --python-exit-code 1 --python tests/test_regression.py
# Builds its own fixtures; needs no .blend argument.

import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness  # noqa: E402  (side effect: repo root on sys.path)
from _harness import check, clear_default_scene, finish, section  # noqa: E402


def make_image(name, size=64):
    return bpy.data.images.new(name, size, size)


def make_textured_material(name, image):
    """(material, image node) with the node showing `image`."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    node = mat.node_tree.nodes.new("ShaderNodeTexImage")
    node.image = image
    return mat, node


def new_cube(name):
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name + "_mesh"
    return obj


def remove_object(obj, keep_mesh=False):
    mesh = obj.data if obj.type == "MESH" else None
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh is not None and not keep_mesh and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def set_edit_mode(obj, mode):
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.mode_set(mode=mode)


def test_tex_swap_deleted_material(journal, textures_apply):
    section("TEX_SWAP revert with a deleted material (review 1.1)")
    img = make_image("sq_del_mat_img")
    mat_a, node_a = make_textured_material("sq_del_mat_a", img)
    mat_b, node_b = make_textured_material("sq_del_mat_b", img)
    users = [(mat_a.name, node_a.name), (mat_b.name, node_b.name)]
    jrnl = journal.Journal()
    reason = textures_apply.quantize_image(img, 32, jrnl, users)
    check(reason is None and img.use_fake_user is True,
          f"quantize succeeded and protected the original ({reason})")
    replacement = node_a.image
    check(replacement is not img, "surviving node shows the replacement pre-revert")
    bpy.data.materials.remove(mat_b)
    count = jrnl.revert_all()
    check(count == 0 and jrnl.skipped_on_revert == 1,
          "revert with a missing material fails honestly")
    check(len(jrnl.entries) == 1, "failed TEX_SWAP entry retained")
    check(img.use_fake_user is True,
          "original fake-user NOT stripped on failure (data-loss fix)")
    # Two-phase revert: a failed revert must not have touched the scene at all
    # (the surviving material's node still shows the replacement, not a
    # half-restored mix).
    check(node_a.image is replacement,
          "failed revert left the surviving node untouched (all-or-nothing)")
    bpy.data.materials.remove(mat_a)


def test_tex_swap_renamed_original(journal, textures_apply):
    section("TEX_SWAP revert after renaming the original")
    img = make_image("sq_rename_img")
    mat, node = make_textured_material("sq_rename_mat", img)
    jrnl = journal.Journal()
    reason = textures_apply.quantize_image(img, 32, jrnl, [(mat.name, node.name)])
    check(reason is None, f"quantize succeeded ({reason})")
    img.name = "sq_renamed_original"
    count = jrnl.revert_all()
    check(count == 1 and node.image is img,
          "session_uid keeps the action revert rename-safe")
    check(img.use_fake_user is False and not jrnl.entries,
          "successful revert restores fake-user and consumes the entry")
    bpy.data.materials.remove(mat)


def test_data_relink(journal, objects_apply):
    section("DATA_RELINK apply + revert (review 1.2)")
    obj_a = new_cube("RelinkKeeper")
    obj_b = obj_a.copy()
    obj_b.data = obj_a.data.copy()
    obj_b.name = "RelinkDup"
    obj_b.data.name = "RelinkDup_mesh"
    bpy.context.scene.collection.objects.link(obj_b)
    keeper, dup = obj_a.data, obj_b.data

    jrnl = journal.Journal()
    result = objects_apply.relink_duplicate_meshes([[keeper.name, dup.name]], jrnl)
    check(result["merged"] == 1 and obj_b.data is keeper, "dedup relinks the dup")
    check(dup.use_fake_user is True, "backup mesh protected via fake-user")

    set_edit_mode(obj_b, 'EDIT')
    count = jrnl.revert_all()
    check(count == 0 and jrnl.skipped_on_revert == 1 and len(jrnl.entries) == 1,
          "Edit-Mode revert fails honestly and retains the entry")
    check(obj_b.data is keeper and dup.use_fake_user is True,
          "backup fake-user untouched by the failed Edit-Mode revert")
    set_edit_mode(obj_b, 'OBJECT')
    count = jrnl.revert_all()
    check(count == 1 and obj_b.data is dup and dup.use_fake_user is False,
          "revert restores obj.data identity after leaving Edit Mode")

    section("DATA_RELINK phantom-entry guard (Edit-Mode apply)")
    set_edit_mode(obj_b, 'EDIT')
    jrnl2 = journal.Journal()
    result = objects_apply.relink_duplicate_meshes([[keeper.name, dup.name]], jrnl2)
    check(result["merged"] == 0 and not jrnl2.entries,
          "Edit-Mode apply records no phantom DATA_RELINK")
    check((obj_b.name, "object in EDIT mode") in result["skipped"],
          "Edit-Mode apply skipped with a reason")
    set_edit_mode(obj_b, 'OBJECT')
    remove_object(obj_b)
    remove_object(obj_a)


def test_two_scene_isolation(journal, objects_apply, textures_apply, guards,
                             coverage_info):
    section("two-scene isolation (review 1.4)")
    scene = bpy.context.scene
    shared = new_cube("SharedCube")
    mod = shared.modifiers.new("Subsurf", "SUBSURF")
    mod.levels = 1
    mod.render_levels = 3
    scene_b = bpy.data.scenes.new("SceneB")
    scene_b.collection.objects.link(shared)

    offscreen = {shared.name: coverage_info(
        object_name=shared.name, max_coverage=0.0, in_frustum_ever=False,
        near_frustum_ever=False, min_camera_distance=100.0, needed_texture_px=64)}
    jrnl = journal.Journal()
    result = objects_apply.trim_offscreen(scene, offscreen, jrnl)
    check((shared.name, "used by other scenes") in result["skipped"],
          "trim skips the shared object with a reason")
    check(shared.visible_camera is True and not jrnl.entries,
          "shared object's ray visibility untouched from scene A")
    result = objects_apply.trim_subdiv(scene, offscreen, jrnl)
    check((shared.name, "used by other scenes") in result["skipped"]
          and mod.render_levels == 3,
          "subdiv trim skips the shared object with a reason")

    scene_b.collection.objects.unlink(shared)
    result = objects_apply.trim_offscreen(scene, offscreen, jrnl)
    check(shared.name in result["objects"] and shared.visible_camera is False,
          "unshared object trims normally (exact users_scene check)")
    jrnl.revert_all()
    check(shared.visible_camera is True, "trim reverts")

    section("cross-scene image guard")
    img = make_image("sq_cross_scene_img")
    mat, node = make_textured_material("sq_cross_scene_mat", img)
    only_b = new_cube("OnlyInB")
    only_b.data.materials.append(mat)
    # primitive_cube_add links into the ACTIVE collection, not the scene root.
    for coll in list(only_b.users_collection):
        coll.objects.unlink(only_b)
    scene_b.collection.objects.link(only_b)
    check(guards.used_outside_scene(img, scene) is True,
          "image reached only via scene B reads as outside scene A")
    check(guards.used_outside_scene(img, scene_b) is False,
          "same image reads as local to scene B")
    reason = textures_apply.quantize_image(
        img, 32, journal.Journal(), [(mat.name, node.name)], scene=scene)
    check(reason == "image used by other scenes",
          f"quantize from scene A refuses the shared image ({reason})")
    remove_object(only_b)
    bpy.data.materials.remove(mat)
    bpy.data.scenes.remove(scene_b)
    remove_object(shared)


def test_dedup_negatives(dedup_scan):
    section("dedup negatives (review 1.3)")
    scene = bpy.context.scene
    template = new_cube("DupTemplate")

    def variant(name):
        obj = template.copy()
        obj.data = template.data.copy()
        obj.name = name
        obj.data.name = name + "_mesh"
        scene.collection.objects.link(obj)
        return obj

    pair_a, pair_b = variant("DupA"), variant("DupB")
    smooth = variant("DupSmooth")
    smooth.data.polygons.foreach_set(
        "use_smooth", [True] * len(smooth.data.polygons))
    smooth.data.update()
    uv_renamed = variant("DupUV")
    uv_renamed.data.uv_layers[0].name = "RenamedMap"
    creased = variant("DupCrease")
    crease_attr = creased.data.attributes.new("crease_edge", 'FLOAT', 'EDGE')
    crease_attr.data[0].value = 1.0
    weighted = variant("DupWeight")
    group = weighted.vertex_groups.new(name="SQGroup")
    group.add([0, 1], 0.7, 'REPLACE')
    remove_object(template)

    scan = dedup_scan.scan_meshes(scene)
    merged = {name for grp in scan["groups"] for name in grp}
    identical = next((set(grp) for grp in scan["groups"]
                      if "DupA_mesh" in grp), set())
    check(identical == {"DupA_mesh", "DupB_mesh"},
          f"identical meshes still merge ({sorted(identical)})")
    for name, label in (("DupSmooth_mesh", "shade-smooth"),
                        ("DupUV_mesh", "renamed UV map"),
                        ("DupCrease_mesh", "edge crease"),
                        ("DupWeight_mesh", "vertex-group weights")):
        check(name not in merged, f"{label} difference blocks merging")
    for obj in (pair_a, pair_b, smooth, uv_renamed, creased, weighted):
        remove_object(obj)


def test_purge_backups(journal, textures_apply, operators):
    section("purge respects artist fake-user")
    scene = bpy.context.scene
    img_artist = make_image("sq_artist_img")
    img_artist.use_fake_user = True  # the artist protected this one
    img_plain = make_image("sq_plain_img")
    mat_a, node_a = make_textured_material("sq_purge_mat_a", img_artist)
    mat_p, node_p = make_textured_material("sq_purge_mat_p", img_plain)
    jrnl = journal.Journal.load(scene)
    check(textures_apply.quantize_image(
        img_artist, 32, jrnl, [(mat_a.name, node_a.name)]) is None,
        "artist-protected image quantized")
    check(textures_apply.quantize_image(
        img_plain, 32, jrnl, [(mat_p.name, node_p.name)]) is None,
        "plain image quantized")

    purged, artist_protected, skipped = operators._purge_scenequant_backups(scene, jrnl)
    check(purged == 1 and artist_protected == 1 and skipped == 0,
          f"purge: 1 purged, 1 artist-protected, 0 skipped "
          f"(got {purged}/{artist_protected}/{skipped})")
    check(bpy.data.images.get("sq_artist_img") is img_artist
          and img_artist.use_fake_user is True,
          "artist-set fake-user survives the purge")
    check(bpy.data.images.get("sq_plain_img") is None,
          "SceneQuant-protected backup purged")
    check(len(jrnl.entries) == 1, "artist-protected entry stays revertible")
    count = jrnl.revert_all()
    check(count == 1 and node_a.image is img_artist
          and img_artist.use_fake_user is True,
          "artist entry reverts and keeps the artist's fake-user")
    jrnl.save(scene)
    bpy.data.materials.remove(mat_a)
    bpy.data.materials.remove(mat_p)
    bpy.data.images.remove(img_artist)


def test_texture_limit(journal, textures_apply):
    section("apply_texture_limit subdiv guard")
    scene = bpy.context.scene
    render = scene.render
    render.use_simplify = False
    render.simplify_subdivision_render = 0  # the hand-set "killer 0"
    jrnl = journal.Journal()
    textures_apply.apply_texture_limit(scene, jrnl, "1024")
    check(render.use_simplify is True and render.simplify_subdivision_render == 6,
          "fresh Simplify enable pins the killer 0 to 6")
    jrnl.revert_all()
    check(render.use_simplify is False and render.simplify_subdivision_render == 0,
          "revert restores the pre-apply state")

    render.use_simplify = True  # deliberate artist configuration
    render.simplify_subdivision_render = 0
    jrnl = journal.Journal()
    textures_apply.apply_texture_limit(scene, jrnl, "1024")
    check(render.simplify_subdivision_render == 0,
          "pre-existing use_simplify + 0 stays 0 (artist's choice respected)")
    jrnl.revert_all()
    render.use_simplify = False
    render.simplify_subdivision_render = 6


def test_node_name_disambiguation(journal, textures_apply):
    section("node-name collision across group instances")
    # Two group trees each contain a TexImage node with the SAME name showing
    # DIFFERENT images: reassign/revert must touch only nodes showing the
    # expected image, never a name-twin (deleting the identity check merged
    # unrelated nodes and every suite stayed green — review finding).
    img_a, img_b = make_image("sq_deep_a"), make_image("sq_deep_b")
    mat = bpy.data.materials.new("sq_group_mat")
    mat.use_nodes = True
    twins = []
    for img in (img_a, img_b):
        tree = bpy.data.node_groups.new(f"sq_grp_{img.name}", "ShaderNodeTree")
        tex = tree.nodes.new("ShaderNodeTexImage")
        tex.name = "DeepTex"
        tex.image = img
        group_node = mat.node_tree.nodes.new("ShaderNodeGroup")
        group_node.node_tree = tree
        twins.append(tex)
    jrnl = journal.Journal()
    reason = textures_apply.quantize_image(img_a, 32, jrnl, [(mat.name, "DeepTex")])
    check(reason is None, f"quantize of the first twin succeeded ({reason})")
    check(twins[0].image is not img_a and twins[1].image is img_b,
          "only the node showing the expected image was reassigned")
    count = jrnl.revert_all()
    check(count == 1 and twins[0].image is img_a and twins[1].image is img_b,
          "revert restores exactly the swapped twin")
    bpy.data.materials.remove(mat)


def test_content_hash_negatives(dedup_scan):
    section("content hash beyond the fingerprint")
    # Pairs with IDENTICAL fingerprints (same topology, layer names, counts)
    # differing only in hashed DATA: only the content hash can tell them apart
    # (review: three of four dedup negatives were caught by the fingerprint
    # alone, leaving the hash layers unexercised).
    scene = bpy.context.scene
    base = new_cube("HashBase")

    def variant(name):
        obj = base.copy()
        obj.data = base.data.copy()
        obj.name = name
        obj.data.name = name + "_mesh"
        scene.collection.objects.link(obj)
        return obj

    uv_shifted = variant("HashUV")
    layer = uv_shifted.data.uv_layers[0]
    coords = [0.0] * (len(layer.data) * 2)
    layer.data.foreach_get("uv", coords)
    layer.data.foreach_set("uv", [c + 0.25 for c in coords])
    color_base = variant("HashColA")
    color_diff = variant("HashColB")
    for obj, value in ((color_base, 0.2), (color_diff, 0.8)):
        attr = obj.data.color_attributes.new("SQCol", 'FLOAT_COLOR', 'POINT')
        for item in attr.data:
            item.color = (value, value, value, 1.0)
    remove_object(base)

    scan = dedup_scan.scan_meshes(scene)
    merged = {name for grp in scan["groups"] for name in grp}
    check("HashUV_mesh" not in merged,
          "identical-fingerprint UV DATA difference blocks merging")
    check(not ({"HashColA_mesh", "HashColB_mesh"} <= merged),
          "identical-layout color DATA difference blocks merging")
    for obj in (uv_shifted, color_base, color_diff):
        remove_object(obj)


def test_image_channel_hash(dedup_scan):
    section("image hash sees every channel (stride aliasing regression)")
    # 512x512 RGBA = 1,048,576 floats: past MAX_HASHED_FLOATS, so subsampling
    # engages. The old float-stride sampled only channels {0, 2} here — two
    # images differing only in GREEN hashed identically and were merged.
    def packed(name, green):
        img = bpy.data.images.new(name, 512, 512, alpha=True)
        texel = [0.5, green, 0.25, 1.0]
        img.pixels.foreach_set(texel * (512 * 512))
        return img

    img_a = packed("sq_pack_a", 0.0)
    img_b = packed("sq_pack_b", 1.0)
    img_c = packed("sq_pack_c", 1.0)  # true duplicate of b
    scan = dedup_scan.scan_images()
    groups = [set(grp) for grp in scan["groups"]]
    check(not any({"sq_pack_a", "sq_pack_b"} <= grp for grp in groups),
          "green-channel-only difference blocks image merging")
    check(any({"sq_pack_b", "sq_pack_c"} <= grp for grp in groups),
          "genuinely identical channel-packed images still merge")
    for img in (img_a, img_b, img_c):
        bpy.data.images.remove(img)


def main():
    import scenequant
    from scenequant import journal
    from scenequant.analysis import dedup_scan
    from scenequant.analysis.coverage import CoverageInfo
    from scenequant.apply import guards, objects_apply, textures_apply
    from scenequant.ui import operators
    scenequant.register()
    clear_default_scene()

    test_tex_swap_deleted_material(journal, textures_apply)
    test_tex_swap_renamed_original(journal, textures_apply)
    test_data_relink(journal, objects_apply)
    test_two_scene_isolation(journal, objects_apply, textures_apply, guards,
                             CoverageInfo)
    test_dedup_negatives(dedup_scan)
    test_node_name_disambiguation(journal, textures_apply)
    test_content_hash_negatives(dedup_scan)
    test_image_channel_hash(dedup_scan)
    test_purge_backups(journal, textures_apply, operators)
    test_texture_limit(journal, textures_apply)
    finish()


main()
