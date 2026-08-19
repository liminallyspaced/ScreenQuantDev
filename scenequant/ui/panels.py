# N-panel UI (VIEW_3D sidebar, tab "SceneQuant") plus a per-object override
# panel in Object properties and a per-image override panel in the Image
# editor. The pipeline panels are numbered: 1 Analyze, 2 Make it Fast, 3 Fit Budget,
# 4 Levers, 5 Tune, then Safety. draw() must never raise and never do heavy work: report
# and journal parses are cached per scene by string identity, the journal
# summary tolerates malformed entries, and no draw path may write files.

import json
import logging
import os
import time

import bpy

from .. import journal

logger = logging.getLogger("scenequant")

MAX_PANEL_FINDINGS = 3
FINDING_TEXT_LIMIT = 55
MAX_WARNING_ROWS = 3
SEVERITY_ICONS = {"critical": "CANCEL", "high": "ERROR", "medium": "INFO", "info": "DOT"}
SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "info": 3}

# One cache slot keyed on the raw string thrashes when two windows show two
# scenes: every redraw re-parsed the other scene's report. Key on scene name
# instead, with a small cap so long sessions cannot grow these unbounded.
MAX_CACHED_SCENES = 8
_report_cache = {}   # scene name -> (raw, parsed dict or None)
_journal_cache = {}  # scene name -> (raw, info dict)

# Scanning every object per redraw costs ~13 ms at 20k objects; the count only
# changes when objects are added/removed or an override is set.
PROTECTED_TTL_S = 0.5
_protected_cache = {"key": None, "count": 0, "time": 0.0}
# The sidecar lives on disk: stat it at most this often, not once per redraw.
SIDECAR_TTL_S = 2.0
_sidecar_cache = {"exists": False, "time": 0.0}


def _cached(cache, scene_name, raw, build):
    hit = cache.get(scene_name)
    if hit is not None and hit[0] == raw:
        return hit[1]
    value = build()
    if scene_name not in cache and len(cache) >= MAX_CACHED_SCENES:
        cache.clear()
    cache[scene_name] = (raw, value)
    return value


def parse_report(scene):
    """Cached, guarded parse of scene.scenequant.last_report; dict or None.

    Public because the render pre-flight check reads the same stored report and
    must not pay for a second parse.
    """
    raw = scene.scenequant.last_report
    if not raw:
        return None
    return _cached(_report_cache, scene.name, raw, lambda: _decode_report(raw))


def _decode_report(raw):
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def report_estimate_mb(scene):
    """Last Analyze's estimated total memory in MB, or None when no analysis is
    stored. This is what arms the render pre-flight check."""
    data = parse_report(scene)
    memory = data.get("memory") if isinstance(data, dict) else None
    total = memory.get("total_mb") if isinstance(memory, dict) else None
    if isinstance(total, bool) or not isinstance(total, (int, float)):
        return None
    return float(total)


def _load_journal(scene):
    """Journal.load for draw paths: never writes to the filesystem (a redraw
    that parks a corrupt copy beside the .blend would do so every frame)."""
    try:
        return journal.Journal.load(scene, preserve_corrupt=False)
    except TypeError:  # older journal without the flag
        return journal.Journal.load(scene)


def _journal_info(scene):
    """Cached journal summary: {'count', 'tags': [(tag, entries)], 'error',
    'quarantined'}. Never raises — a draw() that throws on a malformed entry
    locks the artist out of the Revert buttons below it."""
    raw = scene.scenequant.journal_data
    return _cached(_journal_cache, scene.name, raw, lambda: _build_journal_info(scene))


def _build_journal_info(scene):
    info = {"count": 0, "tags": [], "error": None, "quarantined": 0}
    try:
        jrnl = _load_journal(scene)
        info["error"] = jrnl.load_error
        counts = {}
        for entry in jrnl.entries:
            info["count"] += 1
            tag = entry.get("tag") if isinstance(entry, dict) else None
            if not isinstance(tag, str):
                # Unreadable entry: count it, never let it reach the layout.
                info["quarantined"] += 1
                continue
            counts[tag] = counts.get(tag, 0) + 1
        info["tags"] = list(counts.items())
    except Exception:
        logger.exception("SceneQuant could not summarize the journal for the panel")
        info["quarantined"] = max(info["quarantined"], info["count"])
        info["tags"] = []
    return info


def _sidecar_available():
    now = time.monotonic()
    if now - _sidecar_cache["time"] > SIDECAR_TTL_S:
        try:
            path = journal.sidecar_path()
            _sidecar_cache["exists"] = bool(path) and os.path.exists(path)
        except Exception:
            _sidecar_cache["exists"] = False
        _sidecar_cache["time"] = now
    return _sidecar_cache["exists"]


def invalidate_protected_cache():
    """Called by set_override: our own write changed the answer immediately."""
    _protected_cache["key"] = None


def _protected_count(scene):
    key = (scene.name, len(scene.objects))
    now = time.monotonic()
    if _protected_cache["key"] != key or now - _protected_cache["time"] > PROTECTED_TTL_S:
        _protected_cache["key"] = key
        _protected_cache["time"] = now
        _protected_cache["count"] = sum(
            1 for obj in scene.objects
            if getattr(getattr(obj, "scenequant", None), "override", "AUTO") != "AUTO")
    return _protected_cache["count"]


def _draw_guard(draw):
    """A draw() that raises spams the console every redraw and can hide the
    buttons below it; degrade to one visible row instead."""
    def wrapper(self, context):
        try:
            draw(self, context)
        except Exception:
            logger.exception("SceneQuant panel %s failed to draw",
                             getattr(self, "bl_idname", "?"))
            row = self.layout.row()
            row.alert = True
            row.label(text="Panel error (see the system console)", icon='ERROR')
    return wrapper


def _top_findings(data):
    findings = data.get("findings") if isinstance(data, dict) else None
    if not isinstance(findings, list):
        return []
    usable = [f for f in findings if isinstance(f, dict)]
    usable.sort(key=lambda f: SEVERITY_RANK.get(f.get("severity"), 9))
    return usable[:MAX_PANEL_FINDINGS]


def _clip(text):
    text = str(text)
    if len(text) <= FINDING_TEXT_LIMIT:
        return text
    return text[: FINDING_TEXT_LIMIT - 3] + "..."


def _wrap(text, limit=FINDING_TEXT_LIMIT, max_rows=MAX_WARNING_ROWS):
    """Greedy word wrap into label-sized rows: clipping the pre-flight warning
    to one row hid the half that says what to do about it."""
    rows = []
    current = ""
    for word in str(text).split():
        candidate = f"{current} {word}" if current else word
        if len(candidate) <= limit or not current:
            current = candidate
        else:
            rows.append(current)
            current = word
    if current:
        rows.append(current)
    if len(rows) > max_rows:
        rows = rows[:max_rows]
        rows[-1] = _clip(rows[-1] + " ...")
    return rows or [""]


def _operator_exists(idname):
    """True only for a registered operator: bpy.ops attribute access never
    validates (hasattr is always True), but get_rna_type() raises on fakes."""
    if not idname or "." not in idname:
        return False
    module_name, op_name = idname.split(".", 1)
    try:
        getattr(getattr(bpy.ops, module_name), op_name).get_rna_type()
    except Exception:
        return False
    return True


def _draw_estimates(layout, data):
    before = data.get("est_before_mb")
    after = data.get("est_after_mb")
    measured = data.get("est_after_measured_mb")
    if not isinstance(before, (int, float)):
        return
    if isinstance(after, (int, float)):
        text = f"Est: {before:.0f} MB -> {after:.0f} MB"
        if isinstance(measured, (int, float)):
            text += f" (measured {measured:.0f})"
        layout.label(text=text)
    else:
        layout.label(text=f"Est: {before:.0f} MB")


class SceneQuantPanelMixin:
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "SceneQuant"

    @classmethod
    def poll(cls, context):
        return context.scene is not None


class SCENEQUANT_PT_analyze(SceneQuantPanelMixin, bpy.types.Panel):
    bl_idname = "SCENEQUANT_PT_analyze"
    bl_label = "1. Analyze"
    bl_order = 0

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        settings = scene.scenequant
        layout.prop(settings, "coverage_frame_samples")
        row = layout.row()
        row.scale_y = 1.4
        row.operator("scenequant.analyze", icon='VIEWZOOM')
        data = parse_report(scene)
        # Fit-without-Analyze stores estimates but no grade: that is not an
        # analysis, so the panel must not show a ghost "Grade: ?" state.
        if data is None or "grade" not in data:
            layout.label(text="Run Analyze to grade this scene")
            return
        layout.label(text=f"Grade: {data.get('grade', '?')}")
        for finding in _top_findings(data):
            icon = SEVERITY_ICONS.get(finding.get("severity"), 'DOT')
            row = layout.row(align=True)
            row.label(text=_clip(finding.get("message", "")), icon=icon)
            hint = finding.get("fix_hint") or ""
            if _operator_exists(hint):
                row.operator(hint, text="", icon='TOOL_SETTINGS')
        layout.operator("scenequant.export_report", icon='EXPORT')


class SCENEQUANT_PT_speed(SceneQuantPanelMixin, bpy.types.Panel):
    bl_idname = "SCENEQUANT_PT_speed"
    bl_label = "2. Make it Fast"
    bl_order = 1

    def draw(self, context):
        layout = self.layout
        settings = context.scene.scenequant
        row = layout.row(align=True)
        row.prop(settings, "speed_mode", expand=True)
        row = layout.row()
        row.scale_y = 1.8
        row.operator("scenequant.make_it_fast", text="Make it Fast")
        if settings.speed_mode == "MANUAL":
            box = layout.box()
            box.prop(settings, "speed_probe_knee")
            box.prop(settings, "speed_apply_dead")
            box.prop(settings, "speed_apply_paths")
            box.label(text="Then click Make it Fast to review the plan")
        row = layout.row(align=True)
        row.operator("scenequant.revert_all", text="Revert")
        row.operator("scenequant.probe_sample_knee", text="Knee")
        row.operator("scenequant.verify_render", text="Verify")
        data = parse_report(context.scene)
        plan = data.get("speed_plan") if isinstance(data, dict) else None
        if isinstance(plan, dict) and isinstance(plan.get("est_pct"), (int, float)):
            layout.label(text="Last: ~%.0f%% remaining time" % plan["est_pct"])
        verify = data.get("verify") if isinstance(data, dict) else None
        if isinstance(verify, dict) and "mean" in verify:
            layout.label(text="Verify Δ mean %.4f  max %.4f" % (
                float(verify["mean"]), float(verify.get("max") or 0.0)))


class SCENEQUANT_PT_budget(SceneQuantPanelMixin, bpy.types.Panel):
    bl_idname = "SCENEQUANT_PT_budget"
    bl_label = "3. Fit to Budget"
    bl_order = 2

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        settings = scene.scenequant
        row = layout.row(align=True)
        row.alert = settings.vram_budget_gb <= 0.0
        row.prop(settings, "vram_budget_gb")
        row.operator("scenequant.detect_vram", text="", icon='MEMORY')
        row = layout.row()
        row.scale_y = 1.2
        row.operator("scenequant.fit_budget")
        data = parse_report(scene)
        if data is not None:
            _draw_estimates(layout, data)
        layout.prop(settings, "preflight_enabled")
        if settings.preflight_enabled and report_estimate_mb(scene) is None:
            # The check compares the last Analyze estimate; without one there is
            # nothing to compare and the handler stays silent.
            layout.label(text="Run Analyze to arm the pre-flight check", icon='INFO')
        if settings.preflight_warning:
            box = layout.box()
            box.alert = True
            box.label(text="Pre-flight: over VRAM budget", icon='ERROR')
            for line in _wrap(settings.preflight_warning):
                box.label(text=line)


class SCENEQUANT_PT_levers(SceneQuantPanelMixin, bpy.types.Panel):
    bl_idname = "SCENEQUANT_PT_levers"
    bl_label = "4. Levers"
    bl_order = 3

    def draw(self, context):
        layout = self.layout
        scene = context.scene
        settings = scene.scenequant
        layout.operator("scenequant.dedup", icon='DUPLICATE')
        col = layout.column(align=True)
        col.prop(settings, "trim_keep_reflections")
        col.operator("scenequant.trim_offscreen", icon='CAMERA_DATA')
        col = layout.column(align=True)
        col.prop(settings, "quality_factor")
        col.prop(settings, "min_texture_size")
        col.operator("scenequant.quantize_textures", icon='TEXTURE')
        layout.operator("scenequant.draft_toggle", depress=settings.draft_active)
        layout.operator("scenequant.cull_paranoid")
        self._draw_protection(layout, scene)

    @staticmethod
    def _draw_protection(layout, scene):
        protected = _protected_count(scene)
        box = layout.box()
        box.label(text=f"{protected} protected object(s)", icon='LOCKED')
        row = box.row(align=True)
        row.operator("scenequant.set_override", text="Mark Hero").override = 'HERO'
        row.operator("scenequant.set_override", text="Mark Exclude").override = 'EXCLUDE'
        box.operator("scenequant.set_override", text="Clear Override").override = 'AUTO'


class SCENEQUANT_PT_tune(SceneQuantPanelMixin, bpy.types.Panel):
    bl_idname = "SCENEQUANT_PT_tune"
    bl_label = "5. Tune"
    bl_order = 4

    def draw(self, context):
        layout = self.layout
        settings = context.scene.scenequant
        row = layout.row(align=True)
        row.prop(settings, "tier_lossless", toggle=True)
        row.prop(settings, "tier_perceptual", toggle=True)
        layout.operator("scenequant.autotune")


class SCENEQUANT_PT_safety(SceneQuantPanelMixin, bpy.types.Panel):
    bl_idname = "SCENEQUANT_PT_safety"
    bl_label = "Safety"
    bl_order = 5

    @_draw_guard
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        info = _journal_info(scene)
        if info["error"]:
            row = layout.row()
            row.alert = True
            row.label(text=_clip(info["error"]), icon='ERROR')
        if info["quarantined"]:
            row = layout.row()
            row.alert = True
            row.label(
                text=_clip(f"journal unreadable ({info['quarantined']} entries quarantined)"),
                icon='ERROR')
        count = info["count"]
        suffix = "" if count == 1 else "s"
        layout.label(text=f"{count} change{suffix} recorded")
        for tag, entries in info["tags"]:
            row = layout.row(align=True)
            row.label(text=f"{tag} ({entries})")
            row.operator("scenequant.revert_tag", text="Revert").tag = tag
        col = layout.column(align=True)
        col.operator("scenequant.revert_all", icon='LOOP_BACK')
        col.operator("scenequant.purge_backups", icon='TRASH')
        if count == 0 and _sidecar_available():
            layout.operator("scenequant.recover_journal", icon='FILE_REFRESH')


class SCENEQUANT_PT_object(bpy.types.Panel):
    bl_idname = "SCENEQUANT_PT_object"
    bl_label = "SceneQuant"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "object"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return context.object is not None

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.prop(context.object.scenequant, "override")


class SCENEQUANT_PT_image(bpy.types.Panel):
    bl_idname = "SCENEQUANT_PT_image"
    bl_label = "SceneQuant"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "SceneQuant"

    @classmethod
    def poll(cls, context):
        space = getattr(context, "space_data", None)
        return getattr(space, "image", None) is not None

    def draw(self, context):
        layout = self.layout
        image = context.space_data.image
        layout.use_property_split = True
        layout.prop(image.scenequant, "override")
        if image.scenequant.override == 'KEEP':
            layout.label(text="Never downscaled or replaced", icon='LOCKED')


CLASSES = (
    SCENEQUANT_PT_analyze,
    SCENEQUANT_PT_speed,
    SCENEQUANT_PT_budget,
    SCENEQUANT_PT_levers,
    SCENEQUANT_PT_tune,
    SCENEQUANT_PT_safety,
    SCENEQUANT_PT_object,
    SCENEQUANT_PT_image,
)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
