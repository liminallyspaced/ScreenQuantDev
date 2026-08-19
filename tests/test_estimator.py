# Estimator/solver/report honesty regressions (review P2): world textures in
# the estimate, instanced geometry, resolution-aware overhead, phantom subdiv
# savings, plan fits/shortfall fields, the coupled half-precision behaviors
# (the 5.2-alpha canary runs exactly this suite), and plan rendering in reports.
#   blender -b --factory-startup --python-exit-code 1 --python tests/test_estimator.py
# Builds its own fixtures; needs no .blend argument.

import dataclasses
import os
import sys
import tempfile

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness  # noqa: E402  (side effect: repo root on sys.path)
from _harness import check, clear_default_scene, finish, section  # noqa: E402


def depsgraph():
    return bpy.context.evaluated_depsgraph_get()


def new_cube(name):
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name + "_mesh"
    return obj


def remove_object(obj):
    mesh = obj.data if obj.type == "MESH" else None
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh is not None and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def offscreen_coverage(coverage_info, name):
    return {name: coverage_info(
        object_name=name, max_coverage=0.0, in_frustum_ever=False,
        near_frustum_ever=False, min_camera_distance=100.0, needed_texture_px=64)}


def test_world_env(scene, memory_model):
    section("world environment texture in the estimate")
    img = bpy.data.images.new("sq_env_img", 256, 128)
    world = bpy.data.worlds.new("SQWorld")
    world.use_nodes = True
    env = world.node_tree.nodes.new("ShaderNodeTexEnvironment")
    env.image = img
    scene.world = world
    mem = memory_model.estimate_scene_memory(scene, depsgraph())
    check(img.name in mem.per_image_mb and mem.per_image_mb[img.name] > 0.0,
          "world HDRI counted in per_image_mb")
    check(img.name not in memory_model.images_used_by_render(scene),
          "legacy material users map still excludes world images (TEX_SWAP safety)")
    scene.world = None
    bpy.data.worlds.remove(world)
    bpy.data.images.remove(img)


def test_instanced(scene, memory_model):
    section("instanced geometry counted")
    mem = memory_model.estimate_scene_memory(scene, depsgraph())
    check(not any("(instanced)" in name for name in mem.per_object_geo_mb),
          "no instanced entries before the fixture exists")
    src = new_cube("InstSrc")
    col = bpy.data.collections.new("InstCol")
    for coll in list(src.users_collection):
        coll.objects.unlink(src)
    col.objects.link(src)
    empty = bpy.data.objects.new("InstEmpty", None)
    empty.instance_type = 'COLLECTION'
    empty.instance_collection = col
    scene.collection.objects.link(empty)
    mem = memory_model.estimate_scene_memory(scene, depsgraph())
    label = "InstSrc (instanced)"
    check(label in mem.per_object_geo_mb and mem.per_object_geo_mb[label] > 0.0,
          "collection-instance geometry counted once as '(instanced)'")
    check(mem.render_triangles > 0, "instanced triangles counted")
    bpy.data.objects.remove(empty, do_unlink=True)
    remove_object(src)
    bpy.data.collections.remove(col)


def test_overhead(scene, memory_model):
    section("overhead scales with output resolution")
    render = scene.render
    old = (render.resolution_x, render.resolution_y, render.resolution_percentage)
    render.resolution_percentage = 100
    render.resolution_x, render.resolution_y = 1280, 720
    at_720p = memory_model.overhead_mb(scene)
    render.resolution_x, render.resolution_y = 3840, 2160
    at_4k = memory_model.overhead_mb(scene)
    # A bare `>` passes for any epsilon (a flat-constant regression stayed
    # green): pin the documented 1080p+denoise calibration point and demand a
    # real resolution slope.
    check(at_4k > at_720p * 1.3,
          f"4K overhead exceeds 720p by a real margin ({at_4k:.0f} vs {at_720p:.0f} MB)")
    cycles = scene.cycles
    was_denoising_cal = cycles.use_denoising
    cycles.use_denoising = True
    render.resolution_x, render.resolution_y = 1920, 1080
    at_1080p = memory_model.overhead_mb(scene)
    check(abs(at_1080p - 500.0) < 25.0,
          f"1080p+denoise calibration point holds (~500 MB, got {at_1080p:.1f})")
    cycles.use_denoising = was_denoising_cal
    cycles = scene.cycles
    was_denoising = cycles.use_denoising
    cycles.use_denoising = False
    no_denoise = memory_model.overhead_mb(scene)
    cycles.use_denoising = True
    with_denoise = memory_model.overhead_mb(scene)
    check(with_denoise > no_denoise,
          f"denoiser buffers priced in ({with_denoise:.0f} vs {no_denoise:.0f} MB)")
    cycles.use_denoising = was_denoising
    render.resolution_x, render.resolution_y, render.resolution_percentage = old


def test_solver_subdiv(scene, memory_model, solver, coverage_info):
    """Returns (plan asdict with actions, matching MemoryEstimate) for the
    report test."""
    section("solver: no phantom subdiv savings for show_render=False")
    obj = new_cube("SubdivCube")
    mod = obj.modifiers.new("Subsurf", "SUBSURF")
    mod.levels = 1
    mod.render_levels = 3
    mod.show_render = False
    cov = offscreen_coverage(coverage_info, obj.name)
    settings = scene.scenequant
    check(memory_model.extra_render_subdiv_levels(obj) == 0,
          "estimator counts 0 extra levels for show_render=False")
    mem = memory_model.estimate_scene_memory(scene, depsgraph())
    plan = solver.build_plan(scene, cov, mem, [], [], 1.0, settings)
    check(not any(a.kind == "SUBDIV_TRIM" for a in plan.actions),
          "solver books no subdiv savings for a render-disabled modifier")

    mod.show_render = True
    mem = memory_model.estimate_scene_memory(scene, depsgraph())
    plan = solver.build_plan(scene, cov, mem, [], [], 1.0, settings)
    trims = [a for a in plan.actions if a.kind == "SUBDIV_TRIM"]
    check(len(trims) == 1 and trims[0].est_savings_mb > 0.0,
          "render-enabled modifier books real subdiv savings")

    section("plan fits/shortfall fields")
    check(plan.fits is False and plan.shortfall_mb > 0.0,
          f"1 MB budget: fits False with shortfall ({plan.shortfall_mb:.0f} MB)")
    huge = solver.build_plan(scene, cov, mem, [], [], 10_000_000.0, settings)
    check(huge.fits is True and huge.shortfall_mb == 0.0,
          "huge budget: fits True with zero shortfall")
    plan_dict = dataclasses.asdict(plan)
    for key in ("actions", "est_before_mb", "est_after_mb", "budget_mb",
                "fits", "shortfall_mb", "caveats"):
        check(key in plan_dict, f"stored plan JSON carries '{key}'")
    # journal_data == "" was vacuous (nothing in this suite ever saves a
    # journal): snapshot the scene properties the ladder plans against and
    # prove build_plan wrote none of them.
    watched = ("render.use_simplify", "cycles.samples", "cycles.texture_limit_render",
               "render.use_persistent_data", "cycles.max_bounces")
    snapshot = [scene.path_resolve(path) for path in watched]
    solver.build_plan(scene, cov, mem, [], [], 1.0, settings)
    after_snapshot = [scene.path_resolve(path) for path in watched]
    check(snapshot == after_snapshot,
          "solver stayed pure (planned scene properties untouched)")
    remove_object(obj)
    return plan_dict, mem


def test_half_precision_coupling(scene, memory_model, solver, compat):
    section("coupled half-precision behaviors (5.2 canary)")
    supports = compat.supports_half_precision()
    check(supports == (bpy.app.version < (5, 2, 0)),
          f"supports_half_precision gate matches version ({bpy.app.version_string})")
    # Guard the RNA half of the gate too (the version comparison alone is
    # self-referential): where support is claimed, the property must exist.
    has_rna = "use_half_precision" in bpy.types.Image.bl_rna.properties
    check((not supports) or has_rna,
          "supports_half_precision implies the Image RNA property exists")
    img = bpy.data.images.new("sq_float_img", 64, 64, float_buffer=True)
    check(img.is_float, "float image fixture is float")
    if hasattr(img, "use_half_precision"):
        img.use_half_precision = False  # RNA default is True: pin the baseline
    full_mb = memory_model.image_mb(img)
    if hasattr(img, "use_half_precision"):
        img.use_half_precision = True
        half_mb = memory_model.image_mb(img)
        if supports:
            check(abs(half_mb - full_mb / 2.0) < 1e-9,
                  "supported: use_half_precision halves image_mb")
        else:
            check(half_mb == full_mb,
                  "unsupported: image_mb ignores the inert flag")
        img.use_half_precision = False
    else:
        check(not supports, "missing use_half_precision property implies unsupported")

    mat = bpy.data.materials.new("sq_float_mat")
    mat.use_nodes = True
    mat.node_tree.nodes.new("ShaderNodeTexImage").image = img
    obj = new_cube("FloatCube")
    obj.data.materials.append(mat)
    mem = memory_model.estimate_scene_memory(scene, depsgraph())
    plan = solver.build_plan(scene, {}, mem, [], [], 1.0, scene.scenequant)
    offered = any(a.kind == "HALF_FLOAT" for a in plan.actions)
    check(offered == supports,
          f"HALF_FLOAT rung offered iff supported (offered={offered})")
    remove_object(obj)
    bpy.data.materials.remove(mat)
    bpy.data.images.remove(img)


def test_report_plan(plan_dict, mem, report):
    section("report renders a real plan (text + HTML)")
    data = report.build_report_data(
        "B", [], mem, plan_dict, 3, 8192.0, bpy.app.version_string)
    text = report.format_text(data)
    check("Plan:" in text, "text report has a plan section")
    check("SUBDIV_TRIM" in text, "text plan lists the solver action")
    check("OVER BUDGET" in text and "over the headroom threshold" in text,
          "text plan reports the honest over-budget verdict + shortfall")
    html_path = os.path.join(tempfile.mkdtemp(prefix="sq_report_"), "report.html")
    report.write_html(html_path, data)
    with open(html_path, "r", encoding="utf-8") as handle:
        html_text = handle.read()
    check("Optimization Plan" in html_text, "HTML report has a plan section")
    check("SUBDIV_TRIM" in html_text and "over budget" in html_text,
          "HTML plan lists actions and the verdict")
    no_plan = report.build_report_data(
        "B", [], mem, None, 0, None, bpy.app.version_string)
    check("Plan:" not in report.format_text(no_plan),
          "plan-less report omits the plan section")


def main():
    import scenequant
    from scenequant import compat
    from scenequant.analysis import memory_model
    from scenequant.analysis.coverage import CoverageInfo
    from scenequant.planning import solver
    from scenequant.ui import report
    scenequant.register()
    clear_default_scene()
    scene = bpy.context.scene

    test_world_env(scene, memory_model)
    test_instanced(scene, memory_model)
    test_overhead(scene, memory_model)
    plan_dict, mem = test_solver_subdiv(scene, memory_model, solver, CoverageInfo)
    test_half_precision_coupling(scene, memory_model, solver, compat)
    test_report_plan(plan_dict, mem, report)
    finish()


main()
