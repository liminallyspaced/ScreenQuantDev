# Headless acceptance tests. Run against the bad benchmark scene:
#   blender --background --factory-startup bench/bad_scene.blend \
#       --python-exit-code 1 --python tests/test_headless.py
# Must pass on Blender 4.5 LTS and 5.1.

import json
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness  # noqa: E402  (side effect: repo root on sys.path)
from _harness import check, finish, section  # noqa: E402

# Every operator this addon ships; registration must cover ALL of them
# (review P5: the old check covered 9 of 12 via always-True hasattr).
ALL_OPERATORS = (
    "analyze", "detect_vram", "autotune", "fit_budget", "make_it_fast",
    "probe_sample_knee", "verify_render", "dedup",
    "trim_offscreen", "quantize_textures", "draft_toggle", "cull_paranoid",
    "set_override", "revert_all", "revert_tag", "recover_journal",
    "purge_backups", "export_report",
)
ALL_PANELS = (
    "SCENEQUANT_PT_analyze", "SCENEQUANT_PT_speed", "SCENEQUANT_PT_budget",
    "SCENEQUANT_PT_levers", "SCENEQUANT_PT_tune", "SCENEQUANT_PT_safety",
    "SCENEQUANT_PT_object", "SCENEQUANT_PT_image",
)


def operator_registered(op_name):
    # bpy.ops attribute access never validates (hasattr is ALWAYS True);
    # get_rna_type() raises on unregistered idnames.
    try:
        getattr(bpy.ops.scenequant, op_name).get_rna_type()
    except Exception:
        return False
    return True


def get_report(scene):
    raw = scene.scenequant.last_report
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except ValueError:
        return {}


def finding_codes(report):
    return {f.get("code") for f in report.get("findings", [])}


def check_registration(scenequant, sq_journal, sq_operators, scene):
    section("registration")
    check(hasattr(scene, "scenequant"), "Scene.scenequant property group exists")
    check(hasattr(bpy.data.objects[0], "scenequant"),
          "Object.scenequant property group exists")
    check(hasattr(bpy.data.images[0], "scenequant"),
          "Image.scenequant override property group exists")
    declared = {cls.bl_idname.split(".", 1)[1] for cls in sq_operators.CLASSES}
    check(set(ALL_OPERATORS) == declared,
          f"operator inventory matches CLASSES ({sorted(declared ^ set(ALL_OPERATORS))})")
    for op_name in sorted(declared | set(ALL_OPERATORS)):
        check(operator_registered(op_name), f"operator scenequant.{op_name} registered")
    for panel_name in ALL_PANELS:
        check(hasattr(bpy.types, panel_name), f"panel {panel_name} registered")
    preflight_count = sum(1 for h in bpy.app.handlers.render_init
                          if h is scenequant._preflight_render_init)
    check(preflight_count == 1,
          f"preflight render_init handler present exactly once (got {preflight_count})")
    check(hasattr(scenequant._preflight_render_init, "_bpy_persistent"),
          "preflight handler is @persistent")
    check(sq_journal._on_save_post in bpy.app.handlers.save_post,
          "journal sidecar save_post handler present")


def check_unregistration(scenequant, sq_journal, scene):
    section("unregister")
    scenequant.unregister()
    check(all(not operator_registered(name) for name in ALL_OPERATORS),
          "all operators unregistered")
    check(all(not hasattr(bpy.types, name) for name in ALL_PANELS),
          "all panels unregistered")
    check(scenequant._preflight_render_init not in bpy.app.handlers.render_init,
          "preflight handler removed")
    check(sq_journal._on_save_post not in bpy.app.handlers.save_post,
          "save_post handler removed")
    check(not hasattr(scene, "scenequant"), "Scene property group removed")
    check(not hasattr(bpy.data.images[0], "scenequant"), "Image property group removed")


def main():
    import scenequant
    from scenequant import journal as sq_journal
    from scenequant.ui import operators as sq_operators
    scenequant.register()
    scene = bpy.context.scene

    check_registration(scenequant, sq_journal, sq_operators, scene)

    section("analyze")
    hero = bpy.data.objects["Hero"]
    hero.scenequant.override = "HERO"
    result = bpy.ops.scenequant.analyze()
    check(result == {"FINISHED"}, "analyze returns FINISHED")
    report = get_report(scene)
    check(bool(report), "analysis report stored on scene")
    codes = finding_codes(report)
    print(f"  finding codes: {sorted(codes)}")
    check("FIXED_SAMPLING" in codes, "audit flags fixed sampling (adaptive off)")
    check("DUP_MESH_DATA" in codes, "audit flags duplicate mesh data")
    check("DUP_IMAGE_DATA" in codes, "audit flags duplicate image data")
    check("OFFSCREEN_RENDERED" in codes, "audit flags off-screen render-enabled objects")
    check("grade" in report, "report includes a grade")
    check(isinstance(report.get("per_image_targets"), dict),
          "report payload carries per_image_targets")
    check(isinstance(report.get("skip_reasons"), dict),
          "report payload carries skip_reasons")
    check(isinstance(report.get("memory", {}).get("overhead_mb"), (int, float)),
          "report payload carries the runtime overhead estimate")

    section("dedup")
    far_objects = [o for o in scene.objects if o.name.startswith("Far_") or o.name == "FarTemplate"]
    distinct_before = {o.data.name for o in far_objects}
    check(len(distinct_before) == 30, f"before dedup: 30 distinct far meshes (got {len(distinct_before)})")
    result = bpy.ops.scenequant.dedup()
    check(result == {"FINISHED"}, "dedup returns FINISHED")
    distinct_after = {o.data.name for o in far_objects}
    check(len(distinct_after) == 1, f"after dedup: far objects share one mesh (got {len(distinct_after)})")
    mid_images = set()
    for i in range(10):
        mat = bpy.data.materials[f"MidMat_{i}"]
        for node in mat.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image:
                mid_images.add(node.image.name)
    check(len(mid_images) == 1, f"after dedup: mid materials share one image (got {len(mid_images)})")

    section("trim offscreen")
    result = bpy.ops.scenequant.trim_offscreen()
    check(result == {"FINISHED"}, "trim returns FINISHED")
    off = bpy.data.objects["Offscreen_0"]
    check(off.visible_camera is False, "offscreen object camera visibility off")
    check(off.visible_diffuse is False, "offscreen object diffuse visibility off")
    check(off.visible_shadow is True, "offscreen object still casts shadows (correctness)")
    check(hero.visible_camera is True, "hero object untouched by trim")
    far_mod = bpy.data.objects["Far_1"].modifiers["Subsurf"]
    check(far_mod.render_levels == far_mod.levels,
          f"low-coverage subdiv capped at viewport level (render_levels {far_mod.render_levels})")
    hero_mod = hero.modifiers["Subsurf"]
    check(hero_mod.render_levels == 3, "hero subdiv render levels untouched")

    section("quantize textures")
    # FILE-source regression rig: a real image file on disk must NEVER be
    # aliased by the downscaled copy (data-loss guard).
    import tempfile
    src_path = os.path.join(tempfile.gettempdir(), "sq_test_src.png")
    tmp_img = bpy.data.images.new("sq_tmp_writer", 1024, 1024)
    tmp_img.filepath_raw = src_path
    tmp_img.file_format = "PNG"
    tmp_img.save()
    bpy.data.images.remove(tmp_img)
    with open(src_path, "rb") as fh:
        src_bytes_before = fh.read()
    file_img = bpy.data.images.load(src_path)
    file_mat = bpy.data.materials.new("FileMat")
    file_mat.use_nodes = True
    tex_node = file_mat.node_tree.nodes.new("ShaderNodeTexImage")
    tex_node.image = file_img
    file_mat.node_tree.links.new(
        tex_node.outputs["Color"],
        file_mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
    bpy.ops.mesh.primitive_plane_add(size=0.5, location=(6.0, 6.0, 0.5))
    file_obj = bpy.context.active_object
    file_obj.name = "FilePlane"
    file_obj.data.materials.append(file_mat)

    hero_img = bpy.data.images["hero_4k"]
    hero_size_before = tuple(hero_img.size)
    result = bpy.ops.scenequant.quantize_textures()
    check(result == {"FINISHED"}, "quantize returns FINISHED")
    check(tuple(hero_img.size) == hero_size_before, "HERO-override image not downscaled")
    mid_mat = bpy.data.materials["MidMat_5"]
    mid_nodes = [n for n in mid_mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image]
    check(bool(mid_nodes), "mid material still has an image node")
    if mid_nodes:
        img = mid_nodes[0].image
        long_edge = max(img.size[0], img.size[1])
        check(long_edge < 2048, f"mid texture downscaled (long edge now {long_edge})")
    far_mat = bpy.data.materials["FarMat_0"]
    far_nodes = [n for n in far_mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image]
    if far_nodes:
        far_edge = max(far_nodes[0].image.size[0], far_nodes[0].image.size[1])
        # 1024, not 512: the icosphere UV bbox spans ~0.47 of the UV square, so
        # the atlas correction (needed / sqrt(uv_utilization)) honestly doubles
        # the coverage-only target for the closest far object.
        check(far_edge <= 1024, f"far-ring texture downscaled (long edge now {far_edge})")
    quantized_file = tex_node.image
    check(quantized_file is not file_img, "FILE-source image was quantized via a copy")
    check(quantized_file.packed_file is not None, "quantized copy is packed into the .blend")
    check(quantized_file.filepath == "", "quantized copy does not alias the source file path")
    check(file_img.filepath != "", "original FILE image keeps its filepath")
    try:
        bpy.ops.image.save_all_modified()
    except RuntimeError as exc:
        print(f"  note: save_all_modified raised ({exc}); byte check still valid")
    with open(src_path, "rb") as fh:
        src_bytes_after = fh.read()
    check(src_bytes_after == src_bytes_before,
          "source file on disk is byte-identical after Save All Modified")

    section("autotune")
    cycles = scene.cycles
    # Doctor the scene PAST every cap so the clamps are actually exercised
    # (review P5: the old <=12 bounce assertion was a tautology on this scene).
    cycles.max_bounces = 32
    cycles.diffuse_bounces = 10
    cycles.samples = 4096
    cycles.glossy_bounces = 2  # stricter than the 4-cap: must never be raised
    cycles.transmission_bounces = 20
    cycles.sample_clamp_indirect = 10.0
    cycles.blur_glossy = 0.0  # deliberate sharp: MODE_MAX must raise to the tier floor
    cycles.adaptive_threshold = 0.005  # stricter than the tier's 0.015 cheap-floor
    result = bpy.ops.scenequant.autotune()
    check(result == {"FINISHED"}, "autotune returns FINISHED")
    check(cycles.use_adaptive_sampling is True, "adaptive sampling enabled")
    check(cycles.samples == 1024, f"sample cap enforced 4096 -> 1024 (got {cycles.samples})")
    check(cycles.max_bounces == 8, f"max bounces capped 32 -> 8 (got {cycles.max_bounces})")
    check(cycles.diffuse_bounces == 3, f"diffuse bounces capped 10 -> 3 (got {cycles.diffuse_bounces})")
    check(cycles.glossy_bounces == 2, "stricter user bounce value never raised")
    check(cycles.transmission_bounces == 6,
          f"transmission bounces capped 20 -> 6 (got {cycles.transmission_bounces})")
    check(abs(cycles.sample_clamp_indirect - 5.0) < 1e-6,
          f"indirect clamp tightened 10 -> 5 (got {cycles.sample_clamp_indirect:.1f})")
    check(abs(cycles.blur_glossy - 1.0) < 1e-6,
          f"blur_glossy raised to the tier floor (got {cycles.blur_glossy:.2f})")
    check(abs(cycles.adaptive_threshold - 0.015) < 1e-6,
          f"adaptive threshold raised to the cheap-floor (got {cycles.adaptive_threshold:.4f})")
    check(cycles.sampling_pattern == "TABULATED_SOBOL",
          "scrambling distance paired with tabulated sobol pattern")
    check(cycles.auto_scrambling_distance is True, "auto scrambling distance enabled")

    section("revert")
    journal_len = sq_journal.Journal.load(scene).entry_count()
    check(journal_len > 0, f"journal has entries before revert (got {journal_len})")
    result = bpy.ops.scenequant.revert_all()
    check(result == {"FINISHED"}, "revert returns FINISHED")
    distinct_reverted = {o.data.name for o in far_objects}
    check(len(distinct_reverted) == 30, f"revert restores distinct far meshes (got {len(distinct_reverted)})")
    check(off.visible_camera is True, "revert restores offscreen camera visibility")
    far_mod = bpy.data.objects["Far_1"].modifiers["Subsurf"]
    check(far_mod.render_levels == 2, f"revert restores subdiv render levels (got {far_mod.render_levels})")
    check(cycles.use_adaptive_sampling is False, "revert restores fixed sampling")
    check(cycles.max_bounces == 32, "revert restores the doctored bounce count")
    check(cycles.samples == 4096, "revert restores the doctored sample count")
    mid_nodes = [n for n in mid_mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image]
    if mid_nodes:
        img = mid_nodes[0].image
        check(img.name == "mid_tex_5", f"revert restores original mid image datablock (got {img.name})")
        check(max(img.size[0], img.size[1]) == 2048,
              f"revert restores mid texture resolution (got {max(img.size[0], img.size[1])})")
    journal_after = sq_journal.Journal.load(scene)
    check(journal_after.entry_count() == 0, "journal empty after revert")
    check(scene.scenequant.journal_data == "", "empty journal stored as empty string")

    section("make it Fast")
    samples_before = scene.cycles.samples
    bounces_before = scene.cycles.max_bounces
    simplify_before = scene.render.use_simplify
    result = bpy.ops.scenequant.make_it_fast()
    check(result == {"FINISHED"}, "make_it_fast returns FINISHED")
    check(scene.cycles.samples <= samples_before,
          f"make_it_fast never raises samples ({samples_before} -> {scene.cycles.samples})")
    check(scene.cycles.max_bounces <= bounces_before,
          f"make_it_fast never raises max_bounces ({bounces_before} -> {scene.cycles.max_bounces})")
    check(scene.render.use_simplify == simplify_before
          or not scene.render.use_simplify,
          "make_it_fast does not turn Simplify on")
    speed_report = get_report(scene)
    check(isinstance(speed_report.get("speed_plan"), dict),
          "make_it_fast stores speed_plan without requiring a new Analyze")

    check_unregistration(scenequant, sq_journal, scene)
    finish()


main()
