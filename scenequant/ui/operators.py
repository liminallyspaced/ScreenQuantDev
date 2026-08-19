# Operators: thin wrappers over analysis/planning/apply modules. Every scene
# write happens inside those modules via the Journal; operators load/save the
# journal, drive progress feedback, and report an honest outcome. All execute()
# paths must work in background mode (blender -b): no UI-only context state is
# required. Plan execution lives in apply/plan_apply; mutating operators run
# under a per-invocation run id so a mid-apply exception rolls back atomically.

import dataclasses
import json
import logging
import os
import uuid

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty

from .. import journal
from ..analysis import audit, coverage, dedup_scan, memory_model
from ..apply import knee_apply, objects_apply, plan_apply, settings_apply, speed_apply
from ..constants import BUDGET_HEADROOM, SEVERITY_ORDER
from ..planning import solver, speed_solver
from . import panels, report

logger = logging.getLogger("scenequant")

MB_PER_GB = 1024.0
TIER_NAME_LOSSLESS = "lossless"
TIER_NAME_PERCEPTUAL = "perceptual"
SEVERITY_RANK = {severity: rank for rank, severity in enumerate(SEVERITY_ORDER)}
DIALOG_TEXT_LIMIT = 64
MAX_PREVIEW_TARGET_ROWS = 8

PURGE_WARNING = (
    "Permanently deletes the backup datablocks SceneQuant kept for revert "
    "(original textures and meshes). Those changes become permanent and can "
    "no longer be reverted. Other unused data is not touched."
)

OVERRIDE_ITEMS = (
    ("AUTO", "Auto", "Optimize based on camera coverage analysis"),
    ("HERO", "Hero", "Never reduce this object's textures or ray visibility"),
    ("EXCLUDE", "Exclude", "Never touch this object at all"),
)


# ---------------------------------------------------------------- shared helpers

def _missing_camera(operator, scene):
    if scene.camera is None:
        operator.report({'ERROR'}, "No active scene camera; set one before running SceneQuant analysis")
        return True
    return False


def _missing_budget(operator, settings):
    if settings.vram_budget_gb <= 0.0:
        operator.report({'ERROR'}, "VRAM budget is 0; set it or run Detect VRAM first")
        return True
    return False


def _not_cycles(operator, scene):
    """Cycles-only operators must refuse EEVEE/Workbench scenes: the levers they
    write (and the savings the solver counts) do not exist there."""
    if scene.render.engine != "CYCLES":
        operator.report(
            {'ERROR'},
            f"SceneQuant v1 optimizes Cycles scenes; engine is {scene.render.engine}. "
            "Analyze, Dedup and Quantize still work on any engine.",
        )
        return True
    return False


class _CameraPollMixin:
    """Grays out coverage-dependent operators until a scene camera exists."""

    @classmethod
    def poll(cls, context):
        scene = getattr(context, "scene", None)
        if scene is None:
            return False
        if scene.camera is None:
            cls.poll_message_set("Needs an active scene camera (coverage analysis)")
            return False
        return True


class _OperatorUI:
    """Progress bar + WAIT cursor + status text around a synchronous operator
    body. Every surface is optional, so background mode degrades to nothing.
    Use as `with _OperatorUI(context, label) as update:` and hand `update`
    (signature: index, total, label) to analysis/apply progress hooks."""

    PROGRESS_MAX = 1000

    def __init__(self, context, label):
        self._wm = getattr(context, "window_manager", None)
        self._window = getattr(context, "window", None)
        self._workspace = getattr(context, "workspace", None)
        self._label = label

    def __enter__(self):
        self._call(self._wm, "progress_begin", 0, self.PROGRESS_MAX)
        self._call(self._window, "cursor_modal_set", 'WAIT')
        self.update(0, 1, self._label)
        return self.update

    def __exit__(self, *_exc):
        self._call(self._wm, "progress_end")
        self._call(self._window, "cursor_modal_restore")
        self._call(self._workspace, "status_text_set", None)
        return False

    def update(self, index, total, label):
        fraction = (index + 1) / total if total > 0 else 1.0
        self._call(self._wm, "progress_update",
                   int(min(fraction, 1.0) * self.PROGRESS_MAX))
        self._call(self._workspace, "status_text_set",
                   f"SceneQuant: {label} ({min(index + 1, max(total, 1))}/{max(total, 1)})")

    @staticmethod
    def _call(owner, method_name, *args):
        # UI feedback must never break the operator: a surface may be absent
        # (background mode) or refuse the call (render lock).
        if owner is None:
            return
        try:
            getattr(owner, method_name)(*args)
        except Exception:
            pass


def _clip(text, limit=DIALOG_TEXT_LIMIT):
    text = str(text)
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _depsgraph(context):
    # Works in UI and background sessions; bpy.context fallback for odd callers.
    getter = getattr(context, "evaluated_depsgraph_get", None)
    if getter is not None:
        return getter()
    return bpy.context.evaluated_depsgraph_get()


def _compute_coverage(scene, settings, progress=None):
    # compute_coverage filters to renderable geometry itself.
    return coverage.compute_coverage(
        scene,
        scene.objects,
        frame_samples=settings.coverage_frame_samples,
        quality_factor=settings.quality_factor,
        progress=progress,
    )


def _run_analysis(context, scene, settings, progress=None):
    """(coverage, memory estimate, detailed mesh scan, detailed image scan)."""
    cov = _compute_coverage(scene, settings, progress=progress)
    mem = memory_model.estimate_scene_memory(scene, _depsgraph(context))
    mesh_scan = dedup_scan.scan_meshes(scene)
    image_scan = dedup_scan.scan_images()
    return cov, mem, mesh_scan, image_scan


def _sorted_findings(findings):
    return sorted(findings, key=lambda f: (SEVERITY_RANK.get(f.severity, 9), -f.est_savings_mb))


def _per_image_targets(scene, cov):
    """Per-image quantize target from the shared sizing rule
    (UV-utilization-scaled, most demanding user wins). 0 = no coverage-tracked
    user resolved for the image. Both clamps are skipped: this is the raw need
    the report quotes, not a final size."""
    material_objects = {}
    for obj in scene.objects:
        for slot in getattr(obj, "material_slots", ()):
            if slot.material is not None:
                material_objects.setdefault(slot.material.name, []).append(obj.name)
    targets = {}
    for image_name, users in memory_model.images_used_by_render(scene).items():
        needed = 0
        for material_name, _node_name in users:
            for object_name in material_objects.get(material_name, ()):
                info = cov.get(object_name)
                if info is not None:
                    needed = max(needed, coverage.scaled_needed_px(
                        info.needed_texture_px,
                        getattr(info, "uv_utilization", 1.0)))
        targets[image_name] = needed
    return targets


def _journal_action_log(jrnl):
    """Per-tag entry counts, first-seen order. Malformed entries are ignored
    rather than raising: this feeds the stored report the Safety panel draws,
    and one bad entry must not take the whole UI down."""
    counts = {}
    for entry in jrnl.entries:
        tag = entry.get("tag") if isinstance(entry, dict) else None
        if isinstance(tag, str):
            counts[tag] = counts.get(tag, 0) + 1
    return [{"tag": tag, "entries": entries} for tag, entries in counts.items()]


def _scan_skip_entries(mesh_scan, image_scan):
    entries = []
    for source, scan in (("mesh scan", mesh_scan), ("image scan", image_scan)):
        for item in scan.get("skipped", ()):
            entries.append({"source": source, "name": str(item.get("name")),
                            "reason": str(item.get("reason"))})
    return entries


def _superseded_suffix(jrnl):
    """The revert counts include entries a later write superseded — those need
    no write of their own, so the number would otherwise look inflated."""
    superseded = getattr(jrnl, "last_superseded", 0) or 0
    return f" ({superseded} superseded)" if superseded else ""


def _journal_skip_entries(jrnl):
    return [{"source": "journal", "name": f"{name}: {path}", "reason": reason}
            for name, path, reason in jrnl.skip_log]


def _report_payload(scene, grade_value, findings, mem, cov, mesh_scan,
                    image_scan, budget_mb, plan=None):
    jrnl = journal.Journal.load(scene)
    data = report.build_report_data(
        grade_value, findings, mem, plan,
        jrnl.entry_count(), budget_mb or None, bpy.app.version_string,
    )
    payload = dict(data) if isinstance(data, dict) else {}
    payload["journal_tags"] = _journal_action_log(jrnl)
    # Guaranteed JSON-safe keys the panels (and fit preview) read; these override
    # whatever shape build_report_data chose so the UI never depends on it.
    payload.update({
        "grade": grade_value,
        "findings": [dataclasses.asdict(f) for f in _sorted_findings(findings)],
        "memory": {
            "texture_mb": mem.texture_mb,
            "geometry_mb": mem.geometry_mb,
            "overhead_mb": mem.overhead_mb,
            "total_mb": mem.total_mb,
            "render_triangles": mem.render_triangles,
        },
        "caveats": list(mem.caveats),
        "est_before_mb": mem.total_mb,
        "budget_mb": budget_mb,
        "per_image_targets": _per_image_targets(scene, cov),
        "dedup": {
            "mesh_groups": [list(group) for group in mesh_scan["groups"]],
            "image_groups": [list(group) for group in image_scan["groups"]],
        },
        "skip_reasons": {"scan": _scan_skip_entries(mesh_scan, image_scan)},
    })
    return payload


def _load_report_dict(settings):
    try:
        data = json.loads(settings.last_report) if settings.last_report else {}
    except (ValueError, TypeError):
        data = {}
    return data if isinstance(data, dict) else {}


def _merge_apply_report(settings, jrnl, skip_entries):
    """Fold one apply run's skip reasons + fresh journal tags into the stored
    report, replacing the previous run's apply skips (last-operation semantics)."""
    data = _load_report_dict(settings)
    skips = data.get("skip_reasons")
    if not isinstance(skips, dict):
        skips = {}
    skips["apply"] = skip_entries
    data["skip_reasons"] = skips
    data["journal_tags"] = _journal_action_log(jrnl)
    settings.last_report = json.dumps(data)


def _store_speed_plan(settings, plan, jrnl, skip_entries):
    """Merge the last speed plan onto last_report without wiping the grade."""
    data = _load_report_dict(settings)
    data["speed_plan"] = plan
    skips = data.get("skip_reasons")
    if not isinstance(skips, dict):
        skips = {}
    skips["speed"] = skip_entries
    data["skip_reasons"] = skips
    data["journal_tags"] = _journal_action_log(jrnl)
    settings.last_report = json.dumps(data)


def _store_fit_estimates(settings, plan, jrnl, skip_entries, measured_after_mb):
    data = _load_report_dict(settings)
    data["est_before_mb"] = plan.get("est_before_mb", 0.0)
    data["est_after_mb"] = plan.get("est_after_mb", 0.0)
    if measured_after_mb is not None:
        data["est_after_measured_mb"] = measured_after_mb
    data["budget_mb"] = plan.get("budget_mb", 0.0)
    data["plan"] = plan
    skips = data.get("skip_reasons")
    if not isinstance(skips, dict):
        skips = {}
    skips["apply"] = skip_entries
    data["skip_reasons"] = skips
    data["journal_tags"] = _journal_action_log(jrnl)
    settings.last_report = json.dumps(data)


# ---------------------------------------------------------- atomic apply helpers

def _apply_plan_atomic(operator, context, scene, settings, plan, coverage_map,
                       ui_label):
    """Run plan actions under one run id: on any exception, revert exactly this
    invocation's journal entries, log the traceback, report one honest line.
    Returns (result_dict_or_None, jrnl)."""
    run_id = uuid.uuid4().hex
    jrnl = journal.Journal.load(scene)
    scoped = plan_apply.RunScopedJournal(jrnl, run_id)
    result = None
    try:
        with _OperatorUI(context, ui_label) as update:
            result = plan_apply.apply_plan(
                scene, settings, scoped, plan,
                coverage_map=coverage_map, progress=update)
    except Exception as error:
        reverted = jrnl.revert_run(run_id)
        logger.exception("%s failed; rolled back %d journaled changes",
                         ui_label, reverted)
        operator.report(
            {'ERROR'},
            f"{ui_label} failed ({error}); rolled back {reverted} changes")
    finally:
        jrnl.save(scene)
    return result, jrnl


def _report_apply_outcome(operator, settings, jrnl, result, prefix):
    """One honest line: outcomes, skip count with an example, refused writes."""
    skip_entries = list(result["skipped"]) + _journal_skip_entries(jrnl)
    _merge_apply_report(settings, jrnl, skip_entries)
    message = f"{prefix}: " + ("; ".join(result["outcomes"]) or "no changes")
    if skip_entries:
        example = skip_entries[0]
        operator.report(
            {'WARNING'},
            f"{message} — {len(skip_entries)} skipped, "
            f"e.g. {example['name']}: {example['reason']}")
    else:
        operator.report({'INFO'}, message)


# ------------------------------------------------------------- preview helpers

def _preview_ladder(context, scene, settings, update=None):
    """Read-only full ladder (budget 0 forces every applicable rung) for the
    standalone lever previews. Returns (Plan, coverage_map)."""
    progress = None
    if update is not None:
        progress = lambda i, t, l: update(i, t, f"coverage {l}")
    cov = {}
    if scene.camera is not None:
        cov = _compute_coverage(scene, settings, progress=progress)
    mem = memory_model.estimate_scene_memory(scene, _depsgraph(context))
    mesh_scan = dedup_scan.scan_meshes(scene)
    image_scan = dedup_scan.scan_images()
    plan = solver.build_plan(scene, cov, mem, mesh_scan["groups"],
                             image_scan["groups"], 0.0, settings)
    return plan, cov


def _parse_json(raw, expect):
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, expect) else None


def _draw_action_rows(layout, actions):
    for action in actions:
        icon = 'CHECKMARK' if action.get("visual_cost", 0) == 0 else 'INFO'
        label = action.get("label") or action.get("kind", "?")
        # A zero-saving rung (off-screen trim frees no memory — it is a
        # render-time win) states that in its own label; appending "(~0 MB)"
        # would contradict it and push the honest half past the clip limit.
        savings = action.get("est_savings_mb", 0.0) or 0.0
        if savings > 0:
            label = f"{label} (~{savings:.0f} MB)"
        layout.label(text=_clip(label), icon=icon)


MAX_DEDUP_EXAMPLES = 4


def _dedup_preview(mesh_scan, image_scan):
    """Counts only: the scans know what merges, but not what it frees — that
    needs the estimator, and the preview must stay cheap."""
    mesh_groups = mesh_scan["groups"]
    image_groups = image_scan["groups"]
    examples = [group[0] for group in (list(mesh_groups) + list(image_groups))
                if group][:MAX_DEDUP_EXAMPLES]
    return {
        "mesh_groups": len(mesh_groups),
        "meshes": sum(len(group) - 1 for group in mesh_groups),
        "image_groups": len(image_groups),
        "images": sum(len(group) - 1 for group in image_groups),
        "examples": [str(name) for name in examples],
        "skipped": len(mesh_scan.get("skipped", ())) + len(image_scan.get("skipped", ())),
    }


class _PreviewOperatorMixin:
    """invoke() builds a read-only preview from the solver ladder and reuses
    its coverage in execute(); direct execute() (background/tests) computes
    fresh. Subclasses set PREVIEW_KINDS and EMPTY_MESSAGE."""

    preview_json: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    PREVIEW_KINDS = ()
    EMPTY_MESSAGE = "Nothing to do"

    def invoke(self, context, event):
        scene = context.scene
        settings = scene.scenequant
        if self._invoke_blocked(context, scene, settings):
            return {'CANCELLED'}
        try:
            with _OperatorUI(context, "Building preview") as update:
                plan, cov = _preview_ladder(context, scene, settings, update)
        except Exception as error:
            logger.exception("%s preview failed", self.bl_label)
            self.report({'ERROR'}, f"Preview failed: {error}")
            return {'CANCELLED'}
        self._cov = cov or None
        actions = [dataclasses.asdict(a) for a in plan.actions
                   if a.kind in self.PREVIEW_KINDS]
        if not actions:
            self.report({'INFO'}, self.EMPTY_MESSAGE)
            return {'CANCELLED'}
        self.preview_json = json.dumps(actions)
        return context.window_manager.invoke_props_dialog(self, width=420)

    def _invoke_blocked(self, context, scene, settings):
        return False

    def draw(self, context):
        layout = self.layout
        actions = _parse_json(self.preview_json, list)
        if not actions:
            layout.label(text="Preview unavailable", icon='ERROR')
            return
        _draw_action_rows(layout, actions)

    def _preview_actions(self):
        """Previewed action dicts, or None when invoked directly."""
        return _parse_json(self.preview_json, list)


# --------------------------------------------------------------------- operators

class SCENEQUANT_OT_analyze(_CameraPollMixin, bpy.types.Operator):
    """Scan camera coverage, memory, duplicate data and render settings; store a graded report"""

    bl_idname = "scenequant.analyze"
    bl_label = "Analyze Scene"
    # No UNDO: analysis only stores its report, and an undo push snapshots the
    # whole scene on every click.
    bl_options = {'REGISTER'}

    def execute(self, context):
        scene = context.scene
        settings = scene.scenequant
        if _missing_camera(self, scene):
            return {'CANCELLED'}
        try:
            with _OperatorUI(context, "Analyzing scene") as update:
                cov, mem, mesh_scan, image_scan = _run_analysis(
                    context, scene, settings,
                    progress=lambda i, t, l: update(i, t, f"coverage {l}"))
                budget_mb = settings.vram_budget_gb * MB_PER_GB
                findings = audit.run_audit(
                    scene, cov, mem, mesh_scan["groups"], image_scan["groups"],
                    budget_mb)
                grade_value = audit.grade(findings)
                plan = None
                if budget_mb > 0.0:
                    # Read-only: gives the exported report a real plan section.
                    plan = dataclasses.asdict(solver.build_plan(
                        scene, cov, mem, mesh_scan["groups"],
                        image_scan["groups"], budget_mb, settings))
                payload = _report_payload(
                    scene, grade_value, findings, mem, cov, mesh_scan,
                    image_scan, budget_mb, plan=plan)
                settings.last_report = json.dumps(payload)
        except Exception as error:
            logger.exception("Analyze failed")
            self.report({'ERROR'}, f"Analyze failed: {error}")
            return {'CANCELLED'}
        if bpy.app.background:
            print(report.format_text(payload))
        ordered = _sorted_findings(findings)
        top = ordered[0].message if ordered else "no findings"
        self.report({'INFO'}, f"Grade {grade_value} - {top}")
        return {'FINISHED'}


class SCENEQUANT_OT_detect_vram(bpy.types.Operator):
    """Fill the VRAM budget with the card's physical memory; the planner subtracts headroom and what other applications hold"""

    bl_idname = "scenequant.detect_vram"
    bl_label = "Detect VRAM"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # The budget is PHYSICAL VRAM: headroom is applied once, downstream, by
        # the threshold helper. Writing an already-reduced number here cost the
        # artist a second 15% (72% of the card instead of 85%).
        total_mb = memory_model.detect_vram_mb()
        if total_mb is None:
            self.report({'ERROR'}, "Could not detect GPU VRAM (nvidia-smi unavailable); enter a budget manually")
            return {'CANCELLED'}
        context.scene.scenequant.vram_budget_gb = total_mb / MB_PER_GB
        margin = getattr(memory_model, "VRAM_OS_MARGIN_MB", 512)
        self.report(
            {'INFO'},
            f"{total_mb:,.0f} MB detected; the planner targets "
            f"min({BUDGET_HEADROOM:.0%}, total - in-use - {margin} MB)",
        )
        return {'FINISHED'}


class SCENEQUANT_OT_autotune(bpy.types.Operator):
    """Apply the enabled optimization tiers plus memory-aware persistent-data and denoiser policies"""

    bl_idname = "scenequant.autotune"
    bl_label = "Auto-Tune Settings"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        settings = scene.scenequant
        if _not_cycles(self, scene):
            return {'CANCELLED'}
        run_id = uuid.uuid4().hex
        jrnl = journal.Journal.load(scene)
        scoped = plan_apply.RunScopedJournal(jrnl, run_id)
        try:
            changes = []
            if settings.tier_lossless:
                changes.extend(settings_apply.apply_tier(scene, scoped, TIER_NAME_LOSSLESS))
            if settings.tier_perceptual:
                changes.extend(settings_apply.apply_tier(scene, scoped, TIER_NAME_PERCEPTUAL))
            mem = memory_model.estimate_scene_memory(scene, _depsgraph(context))
            vram_mb = settings.vram_budget_gb * MB_PER_GB
            persistent = settings_apply.maybe_enable_persistent_data(scene, scoped, mem, vram_mb)
            settings_apply.gpu_denoise_policy(scene, scoped, mem, vram_mb)
        except Exception as error:
            reverted = jrnl.revert_run(run_id)
            logger.exception("Auto-tune failed; rolled back %d changes", reverted)
            self.report({'ERROR'}, f"Auto-tune failed ({error}); rolled back {reverted} changes")
            return {'CANCELLED'}
        finally:
            jrnl.save(scene)
        _merge_apply_report(settings, jrnl, _journal_skip_entries(jrnl))
        suffix = "; persistent data enabled" if persistent else ""
        if jrnl.skip_log:
            self.report(
                {'WARNING'},
                f"Auto-tune applied {len(changes)} settings{suffix}; "
                f"{len(jrnl.skip_log)} writes refused (animated/driven or did not stick)")
        else:
            self.report({'INFO'}, f"Auto-tune applied {len(changes)} settings{suffix}")
        return {'FINISHED'}


class SCENEQUANT_OT_fit_budget(_CameraPollMixin, bpy.types.Operator):
    """Build a savings ladder and apply it until the estimated memory fits the VRAM budget"""

    bl_idname = "scenequant.fit_budget"
    bl_label = "Fit to VRAM Budget"
    bl_options = {'REGISTER', 'UNDO'}

    plan_json: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def invoke(self, context, event):
        scene = context.scene
        settings = scene.scenequant
        if _missing_camera(self, scene) or _missing_budget(self, settings) \
                or _not_cycles(self, scene):
            return {'CANCELLED'}
        try:
            with _OperatorUI(context, "Building plan") as update:
                plan, cov = self._build_plan(context, scene, settings, update)
            self.plan_json = json.dumps(dataclasses.asdict(plan))
            self._cov = cov
        except Exception as error:
            logger.exception("Fit-to-budget planning failed")
            self.report({'ERROR'}, f"Could not build plan: {error}")
            return {'CANCELLED'}
        if not plan.actions:
            self.report(
                {'INFO'},
                f"Scene already fits: est {plan.est_before_mb:.0f} MB within {plan.budget_mb:.0f} MB budget",
            )
            return {'CANCELLED'}
        return context.window_manager.invoke_props_dialog(self, width=440)

    @staticmethod
    def _build_plan(context, scene, settings, update=None):
        progress = None
        if update is not None:
            progress = lambda i, t, l: update(i, t, f"coverage {l}")
        cov, mem, mesh_scan, image_scan = _run_analysis(
            context, scene, settings, progress=progress)
        plan = solver.build_plan(
            scene, cov, mem, mesh_scan["groups"], image_scan["groups"],
            settings.vram_budget_gb * MB_PER_GB, settings)
        return plan, cov

    def draw(self, context):
        layout = self.layout
        plan = _parse_json(self.plan_json, dict)
        if plan is None:
            layout.label(text="Plan unavailable", icon='ERROR')
            return
        layout.label(
            text=(
                f"Est {plan.get('est_before_mb', 0.0):.0f} MB -> {plan.get('est_after_mb', 0.0):.0f} MB"
                f" (budget {plan.get('budget_mb', 0.0):.0f} MB)"
            )
        )
        if not plan.get("fits", False):
            layout.label(
                text=f"Ladder exhausted: still {plan.get('shortfall_mb', 0.0):.0f} MB over threshold",
                icon='ERROR')
        _draw_action_rows(layout, plan.get("actions") or [])
        caveats = plan.get("caveats") or []
        for caveat in caveats[:4]:
            layout.label(text=_clip(caveat), icon='INFO')
        if len(caveats) > 4:
            layout.label(text=f"... {len(caveats) - 4} more caveats (see report)")

    def execute(self, context):
        scene = context.scene
        settings = scene.scenequant
        if _missing_camera(self, scene) or _missing_budget(self, settings) \
                or _not_cycles(self, scene):
            return {'CANCELLED'}
        plan = _parse_json(self.plan_json, dict)
        cov = getattr(self, "_cov", None)
        try:
            if plan is None:
                # Direct execute (background/tests): always plan from a fresh
                # analysis, never from a stale last_report.
                with _OperatorUI(context, "Building plan") as update:
                    built, cov = self._build_plan(context, scene, settings, update)
                plan = dataclasses.asdict(built)
        except Exception as error:
            logger.exception("Fit-to-budget planning failed")
            self.report({'ERROR'}, f"Could not build plan: {error}")
            return {'CANCELLED'}
        result, jrnl = _apply_plan_atomic(
            self, context, scene, settings, plan, cov, "Fit to budget")
        if result is None:
            return {'CANCELLED'}
        measured_after_mb = self._measured_after(context, scene)
        skip_entries = list(result["skipped"]) + _journal_skip_entries(jrnl)
        _store_fit_estimates(settings, plan, jrnl, skip_entries, measured_after_mb)
        self._report_honestly(plan, result, skip_entries, measured_after_mb)
        return {'FINISHED'}

    def _measured_after(self, context, scene):
        try:
            return memory_model.estimate_scene_memory(
                scene, _depsgraph(context)).total_mb
        except Exception:
            logger.exception("Post-apply re-estimate failed")
            return None

    def _report_honestly(self, plan, result, skip_entries, measured_after_mb):
        est_before = plan.get("est_before_mb", 0.0)
        est_after = plan.get("est_after_mb", 0.0)
        if not plan.get("fits", True):
            self.report(
                {'WARNING'},
                f"Plan does not reach the budget: {plan.get('shortfall_mb', 0.0):.0f} MB "
                "over the threshold after all rungs")
        planned_saving = est_before - est_after
        if measured_after_mb is not None and planned_saving > 0:
            achieved_saving = est_before - measured_after_mb
            if achieved_saving < 0.8 * planned_saving:
                self.report(
                    {'WARNING'},
                    f"Achieved {achieved_saving:.0f} MB of the planned "
                    f"{planned_saving:.0f} MB savings (under 80% — see skip reasons in the report)")
        measured = (f", measured {measured_after_mb:.0f} MB"
                    if measured_after_mb is not None else "")
        message = (
            f"Applied {result['applied']} plan actions; est {est_before:.0f} MB -> "
            f"{est_after:.0f} MB{measured} (budget {plan.get('budget_mb', 0.0):.0f} MB)"
        )
        if skip_entries:
            example = skip_entries[0]
            self.report({'WARNING'}, f"{message}; {len(skip_entries)} skipped, "
                                     f"e.g. {example['name']}: {example['reason']}")
        else:
            self.report({'INFO'}, message)


class SCENEQUANT_OT_dedup(bpy.types.Operator):
    """Share one datablock among identical meshes and images (weight sharing)"""

    bl_idname = "scenequant.dedup"
    bl_label = "Merge Duplicate Data"
    bl_options = {'REGISTER', 'UNDO'}

    EMPTY_MESSAGE = "No duplicate meshes or images found"

    preview_json: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def invoke(self, context, event):
        # Dedup needs neither coverage nor the solver: the duplicate scans ARE
        # the preview, and execute() re-scans anyway.
        try:
            with _OperatorUI(context, "Scanning for duplicates") as update:
                mesh_scan = dedup_scan.scan_meshes(context.scene)
                update(0, 2, "meshes")
                image_scan = dedup_scan.scan_images()
                update(1, 2, "images")
        except Exception as error:
            logger.exception("Dedup scan failed")
            self.report({'ERROR'}, f"Preview failed: {error}")
            return {'CANCELLED'}
        preview = _dedup_preview(mesh_scan, image_scan)
        if not preview["meshes"] and not preview["images"]:
            self.report({'INFO'}, self.EMPTY_MESSAGE)
            return {'CANCELLED'}
        self.preview_json = json.dumps(preview)
        return context.window_manager.invoke_props_dialog(self, width=420)

    def draw(self, context):
        layout = self.layout
        preview = _parse_json(self.preview_json, dict)
        if not preview:
            layout.label(text="Preview unavailable", icon='ERROR')
            return
        layout.label(
            text=(f"{preview['meshes']} duplicate mesh datablock(s) in "
                  f"{preview['mesh_groups']} group(s)"), icon='MESH_DATA')
        layout.label(
            text=(f"{preview['images']} duplicate image datablock(s) in "
                  f"{preview['image_groups']} group(s)"), icon='IMAGE_DATA')
        for name in preview["examples"]:
            layout.label(text=_clip(f"keep: {name}"), icon='DOT')
        if preview["skipped"]:
            layout.label(text=f"{preview['skipped']} item(s) skipped (see the report)",
                         icon='INFO')

    def execute(self, context):
        scene = context.scene
        settings = scene.scenequant
        actions = [{"kind": "DEDUP", "payload": {}}]
        result, jrnl = _apply_plan_atomic(
            self, context, scene, settings, {"actions": actions}, None,
            "Merge duplicates")
        if result is None:
            return {'CANCELLED'}
        _report_apply_outcome(self, settings, jrnl, result, "Dedup")
        return {'FINISHED'}


class SCENEQUANT_OT_trim_offscreen(_CameraPollMixin, _PreviewOperatorMixin, bpy.types.Operator):
    """Trim what the camera can't see: ray visibility off for off-screen objects (shadows kept), and render subdivision capped at viewport level on tiny/distant objects"""

    bl_idname = "scenequant.trim_offscreen"
    bl_label = "Trim Off-screen & Distant"
    bl_options = {'REGISTER', 'UNDO'}

    PREVIEW_KINDS = ("TRIM_OFFSCREEN", "SUBDIV_TRIM")
    EMPTY_MESSAGE = "Nothing to trim: every object is visible or already trimmed"

    def _invoke_blocked(self, context, scene, settings):
        return _missing_camera(self, scene) or _not_cycles(self, scene)

    def execute(self, context):
        scene = context.scene
        settings = scene.scenequant
        if _missing_camera(self, scene) or _not_cycles(self, scene):
            return {'CANCELLED'}
        actions = [{"kind": "TRIM_OFFSCREEN", "payload": {}},
                   {"kind": "SUBDIV_TRIM", "payload": {}}]
        result, jrnl = _apply_plan_atomic(
            self, context, scene, settings, {"actions": actions},
            getattr(self, "_cov", None), "Trim off-screen")
        if result is None:
            return {'CANCELLED'}
        _report_apply_outcome(self, settings, jrnl, result, "Trim")
        return {'FINISHED'}


class SCENEQUANT_OT_quantize_textures(_CameraPollMixin, _PreviewOperatorMixin, bpy.types.Operator):
    """Downscale texture copies to what the camera actually needs; originals kept for revert"""

    bl_idname = "scenequant.quantize_textures"
    bl_label = "Quantize Textures"
    bl_options = {'REGISTER', 'UNDO'}

    PREVIEW_KINDS = ("QUANTIZE",)
    EMPTY_MESSAGE = "Nothing to quantize: textures already match camera needs"

    def _invoke_blocked(self, context, scene, settings):
        return _missing_camera(self, scene)

    def draw(self, context):
        layout = self.layout
        actions = _parse_json(self.preview_json, list)
        if not actions:
            layout.label(text="Preview unavailable", icon='ERROR')
            return
        _draw_action_rows(layout, actions)
        targets = actions[0].get("payload") or {}
        rows = sorted(targets.items())[:MAX_PREVIEW_TARGET_ROWS]
        for name, target in rows:
            image = bpy.data.images.get(name)
            before = max(image.size[0], image.size[1]) if image is not None else 0
            layout.label(text=_clip(f"{name}: {before} -> {int(target)} px"), icon='TEXTURE')
        if len(targets) > MAX_PREVIEW_TARGET_ROWS:
            layout.label(text=f"... +{len(targets) - MAX_PREVIEW_TARGET_ROWS} more images")

    def execute(self, context):
        scene = context.scene
        settings = scene.scenequant
        if _missing_camera(self, scene):
            return {'CANCELLED'}
        previewed = self._preview_actions()
        if previewed:
            # Apply exactly the previewed targets.
            actions = [{"kind": "QUANTIZE", "payload": previewed[0].get("payload") or {}}]
        else:
            # Direct execute: coverage-driven full pass inside plan_apply.
            actions = [{"kind": "QUANTIZE", "payload": {}}]
        result, jrnl = _apply_plan_atomic(
            self, context, scene, settings, {"actions": actions},
            getattr(self, "_cov", None), "Quantize textures")
        if result is None:
            return {'CANCELLED'}
        _report_apply_outcome(self, settings, jrnl, result, "Quantize")
        return {'FINISHED'}


class SCENEQUANT_OT_draft_toggle(bpy.types.Operator):
    """Toggle fast draft render settings (reduced resolution, bounces and texture limit)"""

    bl_idname = "scenequant.draft_toggle"
    bl_label = "Draft Mode"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        settings = scene.scenequant
        if _not_cycles(self, scene):
            return {'CANCELLED'}
        run_id = uuid.uuid4().hex
        jrnl = journal.Journal.load(scene)
        try:
            if settings.draft_active:
                count = settings_apply.revert_draft(scene, jrnl)
                outcome = f"Draft mode off; {count} settings restored"
            else:
                scoped = plan_apply.RunScopedJournal(jrnl, run_id)
                changes = settings_apply.apply_draft(scene, scoped)
                outcome = f"Draft mode on; {len(changes)} settings applied"
        except Exception as error:
            reverted = jrnl.revert_run(run_id)
            logger.exception("Draft toggle failed; rolled back %d changes", reverted)
            self.report({'ERROR'}, f"Draft toggle failed ({error}); rolled back {reverted} changes")
            return {'CANCELLED'}
        finally:
            jrnl.save(scene)
        self.report({'INFO'}, outcome)
        return {'FINISHED'}


class SCENEQUANT_OT_cull_paranoid(_CameraPollMixin, bpy.types.Operator):
    """Enable Cycles camera culling for never-visible non-emissive objects (removes their shadows and reflections)"""

    bl_idname = "scenequant.cull_paranoid"
    bl_label = "Enable Camera Cull (opt-in)"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(
            self,
            event,
            title="Enable Camera Cull",
            message=(
                "Culled objects vanish from renders entirely, including their shadows "
                "and reflections. Apply to never-visible objects?"
            ),
            icon='QUESTION',
        )

    def execute(self, context):
        scene = context.scene
        settings = scene.scenequant
        if _missing_camera(self, scene) or _not_cycles(self, scene):
            return {'CANCELLED'}
        run_id = uuid.uuid4().hex
        jrnl = journal.Journal.load(scene)
        scoped = plan_apply.RunScopedJournal(jrnl, run_id)
        try:
            with _OperatorUI(context, "Camera cull"):
                result = objects_apply.enable_paranoid_cull(scene, scoped)
        except Exception as error:
            reverted = jrnl.revert_run(run_id)
            logger.exception("Camera cull failed; rolled back %d changes", reverted)
            self.report({'ERROR'}, f"Camera cull failed ({error}); rolled back {reverted} changes")
            return {'CANCELLED'}
        finally:
            jrnl.save(scene)
        skipped = result.get("skipped", [])
        message = f"Camera cull enabled on {result.get('culled', 0)} objects"
        if skipped:
            name, reason = skipped[0]
            self.report({'WARNING'},
                        f"{message}; {len(skipped)} skipped, e.g. {name}: {reason}")
        else:
            self.report({'INFO'}, message)
        return {'FINISHED'}


class SCENEQUANT_OT_set_override(bpy.types.Operator):
    """Set the SceneQuant protection override on all selected objects"""

    bl_idname = "scenequant.set_override"
    bl_label = "Set Protection Override"
    bl_options = {'REGISTER', 'UNDO'}

    override: EnumProperty(items=OVERRIDE_ITEMS, default="AUTO",
                           options={'SKIP_SAVE'})

    @classmethod
    def poll(cls, context):
        if not getattr(context, "selected_objects", None):
            cls.poll_message_set("Select objects first")
            return False
        return True

    def execute(self, context):
        changed = 0
        for obj in getattr(context, "selected_objects", ()):
            overrides = getattr(obj, "scenequant", None)
            if overrides is None:
                continue
            if overrides.override != self.override:
                overrides.override = self.override
                changed += 1
        if changed:
            panels.invalidate_protected_cache()
        verb = "cleared" if self.override == "AUTO" else f"marked {self.override}"
        self.report({'INFO'}, f"{changed} object(s) {verb}")
        return {'FINISHED'}


class SCENEQUANT_OT_revert_all(bpy.types.Operator):
    """Undo every change SceneQuant has recorded, restoring original data and settings"""

    bl_idname = "scenequant.revert_all"
    bl_label = "Revert All Changes"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        count = journal.Journal.load(context.scene).entry_count()
        return context.window_manager.invoke_confirm(
            self,
            event,
            title="Revert All Changes",
            message=f"Undo all {count} recorded SceneQuant changes?",
            confirm_text="Revert",
            icon='QUESTION',
        )

    def execute(self, context):
        scene = context.scene
        settings = scene.scenequant
        jrnl = journal.Journal.load(scene)
        try:
            count = jrnl.revert_all()
        except Exception as error:
            logger.exception("Revert all failed")
            self.report({'ERROR'}, f"Revert failed: {error}")
            return {'CANCELLED'}
        finally:
            jrnl.save(scene)
        settings.draft_active = False
        reverted = f"Reverted {count} changes{_superseded_suffix(jrnl)}"
        skipped = jrnl.skipped_on_revert
        if skipped:
            # Failed entries stay in the journal, so a later attempt (e.g. after
            # leaving Edit Mode) can still restore them.
            self.report(
                {'WARNING'},
                f"{reverted}; {skipped} entries could not be "
                "restored and remain in the journal (missing datablocks, Edit "
                "Mode, or writes that did not stick)",
            )
        else:
            self.report({'INFO'}, reverted)
        return {'FINISHED'}


class SCENEQUANT_OT_revert_tag(bpy.types.Operator):
    """Revert only the changes recorded under one journal tag"""

    bl_idname = "scenequant.revert_tag"
    bl_label = "Revert Tag"
    bl_options = {'REGISTER', 'UNDO'}

    tag: StringProperty(options={'SKIP_SAVE'})

    def execute(self, context):
        scene = context.scene
        if not self.tag:
            self.report({'ERROR'}, "No journal tag given")
            return {'CANCELLED'}
        jrnl = journal.Journal.load(scene)
        try:
            count = jrnl.revert_tag(self.tag)
        except Exception as error:
            logger.exception("Revert tag %r failed", self.tag)
            self.report({'ERROR'}, f"Revert '{self.tag}' failed: {error}")
            return {'CANCELLED'}
        finally:
            jrnl.save(scene)
        if self.tag == settings_apply.DRAFT_TAG:
            scene.scenequant.draft_active = False
        reverted = f"Reverted {count} '{self.tag}' changes{_superseded_suffix(jrnl)}"
        skipped = jrnl.skipped_on_revert
        if skipped:
            self.report(
                {'WARNING'},
                f"{reverted}; {skipped} entries could not be restored and "
                "remain in the journal",
            )
        else:
            self.report({'INFO'}, reverted)
        return {'FINISHED'}


class SCENEQUANT_OT_recover_journal(bpy.types.Operator):
    """Restore this scene's journal from the crash-recovery sidecar file saved beside the .blend"""

    bl_idname = "scenequant.recover_journal"
    bl_label = "Recover Journal"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        count = journal.recover_from_sidecar(scene)
        if count == 0:
            self.report({'WARNING'}, "No recoverable journal found in the sidecar for this scene")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Recovered {count} journal entries from the sidecar")
        return {'FINISHED'}


# kind -> (payload key naming the backup, payload flag, bpy.data collection)
BACKUP_ENTRY_KINDS = {
    "TEX_SWAP": ("orig_image", "orig_had_fake_user", "images"),
    "DATA_RELINK": ("old_mesh", "old_had_fake_user", "meshes"),
}


def _purge_scenequant_backups(scene, jrnl):
    """Delete ONLY the fake-user backups SceneQuant itself protected.

    Entries whose payload records the ARTIST had fake_user set are kept intact
    (the backup was artist-protected data before SceneQuant touched it) and
    stay revertible. Purged entries are dropped (their revert path is gone);
    remaining entries stay revertible. A malformed payload is left alone and
    counted as skipped rather than raising mid-loop.

    The journal is rewritten and saved in a finally, dropping exactly the
    entries whose backups are already gone: a failure partway through can never
    leave the journal claiming a deleted backup still exists.
    Returns (purged, artist_protected, skipped).
    """
    purged_ids = set()
    purged = 0
    artist_protected = 0
    skipped = 0
    try:
        for entry in list(jrnl.entries):
            outcome = _purge_backup_entry(entry)
            if outcome == "purged":
                purged_ids.add(id(entry))
                purged += 1
            elif outcome == "artist":
                artist_protected += 1
            elif outcome == "skipped":
                skipped += 1
    finally:
        jrnl.entries = [e for e in jrnl.entries if id(e) not in purged_ids]
        jrnl.save(scene)
    return purged, artist_protected, skipped


def _purge_backup_entry(entry):
    """Classify one journal entry and delete its backup when SceneQuant owns
    it: 'purged' | 'artist' | 'skipped' | 'keep'."""
    if not isinstance(entry, dict) or entry.get("t") != "action":
        return "keep"
    spec = BACKUP_ENTRY_KINDS.get(entry.get("kind"))
    if spec is None:
        return "keep"
    name_key, artist_key, collection_name = spec
    payload = entry.get("payload")
    if not isinstance(payload, dict):
        logger.warning("Purge skipped a %s entry: payload is not a dict", entry.get("kind"))
        return "skipped"
    if payload.get(artist_key, False):
        return "artist"
    name = payload.get(name_key)
    if not isinstance(name, str):
        logger.warning("Purge skipped a %s entry: payload has no %s",
                       entry.get("kind"), name_key)
        return "skipped"
    collection = getattr(bpy.data, collection_name)
    backup = collection.get(name)
    if backup is not None:
        backup.use_fake_user = False
        if backup.users == 0:
            collection.remove(backup)
    return "purged"


class SCENEQUANT_OT_purge_backups(bpy.types.Operator):
    """Permanently delete the backup datablocks SceneQuant kept for revert; those changes can no longer be reverted"""

    bl_idname = "scenequant.purge_backups"
    bl_label = "Purge Backups (permanent)"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(
            self,
            event,
            title="Purge Backups",
            message=PURGE_WARNING,
            confirm_text="Purge",
            icon='WARNING',
        )

    def execute(self, context):
        scene = context.scene
        jrnl = journal.Journal.load(scene)
        try:
            count, artist_protected, skipped = _purge_scenequant_backups(scene, jrnl)
        except Exception as error:
            logger.exception("Purge backups failed")
            self.report({'ERROR'}, f"Purge failed: {error}")
            return {'CANCELLED'}
        suffix = (f"; {artist_protected} artist-protected backup(s) kept revertible"
                  if artist_protected else "")
        if skipped:
            suffix += f"; {skipped} unreadable entry(ies) left untouched"
        if count == 0:
            self.report({'INFO'}, f"No SceneQuant backups to purge{suffix}")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Purged {count} SceneQuant backup datablocks; "
                              f"those changes are now permanent{suffix}")
        return {'FINISHED'}


class SCENEQUANT_OT_export_report(bpy.types.Operator):
    """Write the last analysis as a self-contained HTML report and open it"""

    bl_idname = "scenequant.export_report"
    bl_label = "Export Report"
    bl_options = {'REGISTER'}

    filepath: StringProperty(
        name="File Path",
        subtype='FILE_PATH',
        default="//scenequant_report.html",
    )
    check_existing: BoolProperty(
        name="Check Existing",
        description="Prompt before overwriting an existing file",
        default=True,
        options={'HIDDEN'},
    )

    def invoke(self, context, event):
        if not context.scene.scenequant.last_report:
            self.report({'ERROR'}, "No analysis to export; run Analyze first")
            return {'CANCELLED'}
        if not bpy.data.filepath and self.filepath.startswith("//"):
            # Unsaved .blend: '//' would resolve to the process CWD.
            self.filepath = os.path.join(
                os.path.expanduser("~"), "scenequant_report.html")
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        raw = context.scene.scenequant.last_report
        if not raw:
            self.report({'ERROR'}, "No analysis to export; run Analyze first")
            return {'CANCELLED'}
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            self.report({'ERROR'}, "Stored report is corrupt; run Analyze again")
            return {'CANCELLED'}
        filepath = self.filepath or "//scenequant_report.html"
        if not bpy.data.filepath and filepath.startswith("//"):
            # invoke() rewrites this to the home directory; a scripted execute()
            # would silently drop the report in Blender's working directory.
            self.report({'ERROR'}, "Save the .blend first, or pass an absolute "
                                   "filepath: '//' has nowhere to resolve to")
            return {'CANCELLED'}
        path = bpy.path.abspath(filepath)
        try:
            report.write_html(path, data)
        except OSError as error:
            self.report({'ERROR'}, f"Could not write report: {error}")
            return {'CANCELLED'}
        self.report({'INFO'}, f"Report written to {path}")
        self._open_in_browser(path)
        return {'FINISHED'}

    @staticmethod
    def _open_in_browser(path):
        if bpy.app.background:
            return
        try:
            from pathlib import Path
            bpy.ops.wm.url_open(url=Path(path).resolve().as_uri())
        except Exception:
            pass  # the file is written either way


TIER_BADGES = {0: "T0", 1: "T1", 2: "T2", 3: "T3"}
COVERAGE_KINDS = {"TRIM_OFFSCREEN", "SUBDIV_TRIM", "MICRO_EMITTERS",
                  "CAMERA_CULL", "HAIR_RIBBONS", "HIDE_OFFSCREEN_INSTANCES",
                  "OFFSCREEN_DICING"}
DEAD_KINDS = {
    "TRIM_OFFSCREEN", "HIDE_OFFSCREEN_INSTANCES", "SUBDIV_TRIM",
    "ADAPTIVE_SUBDIV_CAP", "MICRO_EMITTERS", "CAMERA_CULL",
    "HAIR_RIBBONS", "CRYPTO_PRUNE", "PASS_PRUNE", "OFFSCREEN_DICING",
    "OPAQUE_CUTOUT_SHADOWS",
}
PATH_KINDS = {
    "APPLY_PERCEPTUAL_PATHS", "LIGHT_TREE", "CAUSTICS_OFF",
    "PATH_GUIDING_OFF", "WORLD_MIS_NONE", "VOLUME_BOUNCES_ZERO",
    "HOMOGENEOUS_VOLUME", "LIGHT_SAMPLING_THRESHOLD",
    "TRANSPARENT_SHADOW_CAP",
}


def _filter_manual_plan(plan, settings):
    """Drop dead/path actions when Manual has those boxes unchecked."""
    if getattr(settings, "speed_mode", "AUTO") != "MANUAL":
        return plan
    drop = set()
    if not getattr(settings, "speed_apply_dead", True):
        drop |= DEAD_KINDS
    if not getattr(settings, "speed_apply_paths", True):
        drop |= PATH_KINDS
    if not drop:
        return plan
    plan = dict(plan)
    plan["actions"] = [
        a for a in (plan.get("actions") or []) if a.get("kind") not in drop
    ]
    return plan


class SCENEQUANT_OT_make_it_fast(bpy.types.Operator):
    """Cut Cycles wall-clock time with free and perceptual levers; journaled and revertible"""

    bl_idname = "scenequant.make_it_fast"
    bl_label = "Make it Fast"
    bl_options = {'REGISTER', 'UNDO'}

    plan_json: StringProperty(options={'HIDDEN', 'SKIP_SAVE'})

    def _auto_analyze(self, context):
        """Step 1 of the one-button path. Read-only grade + coverage report."""
        scene = context.scene
        if scene.camera is None:
            return
        try:
            bpy.ops.scenequant.analyze('EXEC_DEFAULT')
        except Exception:
            logger.exception("Make it Fast: analyze step failed")

    def _auto_fit_if_over(self, context):
        """Step 3: VRAM ladder only when the analyze estimate is over budget.
        Never fires Draft / Quantize / Tune as their own buttons.
        """
        scene = context.scene
        settings = scene.scenequant
        if scene.camera is None:
            return
        budget_gb = float(getattr(settings, "vram_budget_gb", 0.0) or 0.0)
        if budget_gb <= 0.0:
            return
        total = None
        raw = getattr(settings, "last_report", "") or ""
        if raw:
            try:
                mem = (json.loads(raw) or {}).get("memory") or {}
                total = mem.get("total_mb")
            except Exception:
                total = None
        if not isinstance(total, (int, float)) or total <= budget_gb * MB_PER_GB:
            return
        try:
            bpy.ops.scenequant.fit_budget('EXEC_DEFAULT')
        except Exception:
            logger.exception("Make it Fast: fit_budget step failed")

    def invoke(self, context, event):
        scene = context.scene
        settings = scene.scenequant
        if _not_cycles(self, scene):
            return {'CANCELLED'}
        if getattr(settings, "speed_mode", "AUTO") == "AUTO":
            self._auto_analyze(context)
        try:
            with _OperatorUI(context, "Building speed plan") as update:
                plan, cov, mem = self._build_plan(context, scene, settings, update)
            self.plan_json = json.dumps(speed_solver.plan_to_dict(plan))
            self._cov = cov
            self._mem = mem
        except Exception as error:
            logger.exception("Make it Fast planning failed")
            self.report({'ERROR'}, f"Could not build speed plan: {error}")
            return {'CANCELLED'}
        if not plan.actions:
            self.report(
                {'INFO'},
                "Make it Fast: scene already at the sample knee / no dead work "
                "(low-double-digit gains only)",
            )
            return {'CANCELLED'}
        if getattr(settings, "speed_mode", "AUTO") == "AUTO":
            return self.execute(context)
        return context.window_manager.invoke_props_dialog(self, width=460)

    @staticmethod
    def _build_plan(context, scene, settings, update=None):
        progress = None
        if update is not None:
            progress = lambda i, t, l: update(i, t, f"coverage {l}")
        if float(getattr(settings, "vram_budget_gb", 0.0) or 0.0) <= 0.0:
            detected = memory_model.detect_vram_mb()
            if detected:
                settings.vram_budget_gb = detected / MB_PER_GB
        cov = {}
        if scene.camera is not None:
            cov = _compute_coverage(scene, settings, progress=progress)
        mem = memory_model.estimate_scene_memory(scene, _depsgraph(context))
        plan = speed_solver.build_speed_plan(scene, cov, mem, settings)
        return plan, cov, mem

    def draw(self, context):
        layout = self.layout
        plan = _parse_json(self.plan_json, dict)
        if plan is None:
            layout.label(text="Plan unavailable", icon='ERROR')
            return
        remaining = plan.get("est_pct", 100.0)
        layout.label(text=f"Estimated remaining time: ~{remaining:.0f}%")
        for action in plan.get("actions") or []:
            badge = TIER_BADGES.get(action.get("tier"), "?")
            label = action.get("label") or action.get("kind", "?")
            icon = 'CHECKMARK' if action.get("visual_cost", 0) == 0 else 'INFO'
            layout.label(text=_clip(f"{badge}  {label}"), icon=icon)
        caveats = plan.get("caveats") or []
        for caveat in caveats[:3]:
            layout.label(text=_clip(caveat), icon='INFO')
        if len(caveats) > 3:
            layout.label(text=f"... {len(caveats) - 3} more caveats")

    def execute(self, context):
        scene = context.scene
        settings = scene.scenequant
        if _not_cycles(self, scene):
            return {'CANCELLED'}
        plan = _parse_json(self.plan_json, dict)
        cov = getattr(self, "_cov", None)
        mem = getattr(self, "_mem", None)
        try:
            if plan is None:
                with _OperatorUI(context, "Building speed plan") as update:
                    built, cov, mem = self._build_plan(
                        context, scene, settings, update)
                plan = speed_solver.plan_to_dict(built)
        except Exception as error:
            logger.exception("Make it Fast planning failed")
            self.report({'ERROR'}, f"Could not build speed plan: {error}")
            return {'CANCELLED'}
        if scene.camera is None:
            # Settings-only: drop coverage-dependent levers rather than fail.
            kept = [a for a in (plan.get("actions") or [])
                    if a.get("kind") not in COVERAGE_KINDS]
            plan = dict(plan)
            plan["actions"] = kept
        plan = _filter_manual_plan(plan, settings)
        already_adaptive = bool(getattr(
            getattr(scene, "cycles", None), "use_adaptive_sampling", False))
        result, jrnl = self._apply_atomic(context, scene, settings, plan, cov, mem)
        if result is None:
            return {'CANCELLED'}
        do_knee = (
            getattr(settings, "speed_mode", "AUTO") == "AUTO"
            or getattr(settings, "speed_probe_knee", True)
        )
        knee = knee_apply.auto_knee(
            scene, already_adaptive=already_adaptive) if do_knee else {
            "applied": False, "reason": "sample knee off in Manual",
        }
        skip_entries = list(result["skipped"]) + _journal_skip_entries(jrnl)
        remaining = plan.get("est_pct", 100.0)
        message = (
            f"Make it Fast: ~{remaining:.0f}% estimated remaining time, "
            f"{result['applied']} changes"
        )
        if knee.get("applied"):
            message += ", samples → %s" % knee.get("knee")
        elif knee.get("reason"):
            skip_entries.append({
                "name": "SAMPLE_KNEE",
                "reason": knee["reason"],
            })
        _store_speed_plan(settings, plan, jrnl, skip_entries)
        if skip_entries:
            example = skip_entries[0]
            self.report(
                {'WARNING'},
                f"{message} — {len(skip_entries)} skipped, "
                f"e.g. {example['name']}: {example['reason']}")
        else:
            self.report({'INFO'}, message)
        if getattr(settings, "speed_mode", "AUTO") == "AUTO":
            self._auto_fit_if_over(context)
        return {'FINISHED'}

    def _apply_atomic(self, context, scene, settings, plan, cov, mem):
        run_id = uuid.uuid4().hex
        jrnl = journal.Journal.load(scene)
        scoped = plan_apply.RunScopedJournal(jrnl, run_id)
        result = None
        try:
            with _OperatorUI(context, "Make it Fast") as update:
                result = speed_apply.apply_speed_plan(
                    scene, settings, scoped, plan,
                    coverage_map=cov, progress=update, mem=mem)
        except Exception as error:
            reverted = jrnl.revert_run(run_id)
            logger.exception("Make it Fast failed; rolled back %d journaled changes",
                             reverted)
            self.report(
                {'ERROR'},
                f"Make it Fast failed ({error}); rolled back {reverted} changes")
        finally:
            jrnl.save(scene)
        return result, jrnl


class SCENEQUANT_OT_probe_sample_knee(bpy.types.Operator):
    """Find the lowest sample count where a further doubling no longer changes the image"""

    bl_idname = "scenequant.probe_sample_knee"
    bl_label = "Probe Sample Knee"
    bl_options = {'REGISTER'}

    def execute(self, context):
        from ..analysis import sample_probe
        scene = context.scene
        if _not_cycles(self, scene):
            return {'CANCELLED'}
        if scene.camera is None:
            self.report({'ERROR'}, "Probe Sample Knee needs a scene camera")
            return {'CANCELLED'}
        jrnl = journal.Journal.load(scene)
        probe_id = uuid.uuid4().hex
        scoped = plan_apply.RunScopedJournal(jrnl, probe_id)
        knee = None
        rungs = []
        try:
            render_at = knee_apply.make_blender_renderer(scene, scoped)
            knee, ladder = sample_probe.run_knee_ladder(
                render_at, eps=sample_probe.AUTO_EPS)
            rungs = sorted(ladder.keys())
        except Exception as error:
            reverted = jrnl.revert_run(probe_id)
            logger.exception("Probe Sample Knee failed; rolled back %d writes", reverted)
            jrnl.save(scene)
            self.report(
                {'ERROR'},
                "Probe failed (%s); rolled back %d changes" % (error, reverted))
            return {'CANCELLED'}
        jrnl.revert_run(probe_id)
        apply_id = uuid.uuid4().hex
        apply_scoped = plan_apply.RunScopedJournal(jrnl, apply_id)
        try:
            result = knee_apply.apply_knee(
                scene, apply_scoped, knee,
                probe_scale=knee_apply.PROBE_SCALE,
                eps=sample_probe.AUTO_EPS)
        except Exception as error:
            reverted = jrnl.revert_run(apply_id)
            logger.exception("Probe knee apply failed; rolled back %d writes", reverted)
            jrnl.save(scene)
            self.report(
                {'ERROR'},
                "Knee apply failed (%s); rolled back %d changes" % (error, reverted))
            return {'CANCELLED'}
        jrnl.save(scene)
        rung_txt = ",".join(str(n) for n in rungs) or "-"
        if result["applied"]:
            self.report(
                {'INFO'},
                "Sample knee %s (rungs %s) — %s" % (
                    result["knee"], rung_txt, result["reason"]))
        else:
            self.report(
                {'INFO'},
                "Sample knee %s (rungs %s) — %s" % (
                    result["knee"], rung_txt, result["reason"] or "no samples write"))
        return {'FINISHED'}


class SCENEQUANT_OT_verify_render(bpy.types.Operator):
    """Compare two rendered buffers (mean/max linear RGB delta)"""

    bl_idname = "scenequant.verify_render"
    bl_label = "Verify Render"
    bl_options = {'REGISTER'}

    image_a: StringProperty(name="Image A", default="")
    image_b: StringProperty(name="Image B", default="")

    def execute(self, context):
        from ..analysis import sample_probe
        name_a, name_b = self.image_a.strip(), self.image_b.strip()
        img_a = bpy.data.images.get(name_a) if name_a else None
        img_b = bpy.data.images.get(name_b) if name_b else None
        if img_a is None or img_b is None:
            img_a, img_b = _two_verify_images(name_a, name_b)
        if img_a is None or img_b is None:
            self.report(
                {'ERROR'},
                "Verify needs two images in bpy.data (name them Image A / Image B, "
                "or keep two rendered images loaded)")
            return {'CANCELLED'}
        try:
            buf_a = _image_rgb_buffer(img_a)
            buf_b = _image_rgb_buffer(img_b)
            mean, peak = sample_probe.verify_delta(buf_a, buf_b)
        except Exception as error:
            self.report({'ERROR'}, "Verify failed: %s" % error)
            return {'CANCELLED'}
        _store_verify(context.scene.scenequant, img_a.name, img_b.name, mean, peak)
        self.report(
            {'INFO'},
            "Verify %s vs %s: mean Δ %.4f, max Δ %.4f" % (
                img_a.name, img_b.name, mean, peak))
        return {'FINISHED'}


def _two_verify_images(name_a, name_b):
    named = []
    for name in (name_a, name_b):
        img = bpy.data.images.get(name) if name else None
        named.append(img)
    if named[0] is not None and named[1] is not None:
        return named[0], named[1]
    candidates = []
    for img in bpy.data.images:
        if img.name in ("Render Result", "Viewer Node"):
            continue
        size = getattr(img, "size", (0, 0))
        if size[0] and size[1] and getattr(img, "pixels", None):
            candidates.append(img)
    if named[0] is None and len(candidates) >= 1:
        named[0] = candidates[0]
    if named[1] is None:
        for img in candidates:
            if img is not named[0]:
                named[1] = img
                break
    return named[0], named[1]


def _image_rgb_buffer(image):
    import numpy as np
    width, height = image.size
    pixels = np.array(image.pixels[:], dtype=np.float32)
    if width < 1 or height < 1 or pixels.size == 0:
        raise ValueError("%s has no pixels" % image.name)
    channels = max(1, pixels.size // (width * height))
    return pixels.reshape(height, width, channels)


def _store_verify(settings, name_a, name_b, mean, peak):
    payload = {}
    raw = getattr(settings, "last_report", "") or ""
    if raw:
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {}
    if not isinstance(payload, dict):
        payload = {}
    payload["verify"] = {
        "a": name_a, "b": name_b, "mean": mean, "max": peak,
    }
    settings.last_report = json.dumps(payload)


CLASSES = (
    SCENEQUANT_OT_analyze,
    SCENEQUANT_OT_detect_vram,
    SCENEQUANT_OT_autotune,
    SCENEQUANT_OT_fit_budget,
    SCENEQUANT_OT_make_it_fast,
    SCENEQUANT_OT_probe_sample_knee,
    SCENEQUANT_OT_verify_render,
    SCENEQUANT_OT_dedup,
    SCENEQUANT_OT_trim_offscreen,
    SCENEQUANT_OT_quantize_textures,
    SCENEQUANT_OT_draft_toggle,
    SCENEQUANT_OT_cull_paranoid,
    SCENEQUANT_OT_set_override,
    SCENEQUANT_OT_revert_all,
    SCENEQUANT_OT_revert_tag,
    SCENEQUANT_OT_recover_journal,
    SCENEQUANT_OT_purge_backups,
    SCENEQUANT_OT_export_report,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
