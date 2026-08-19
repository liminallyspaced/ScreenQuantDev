# PropertyGroups. Settings live on Scene, per-object overrides on Object,
# per-image overrides on Image (guards.image_keep_override reads them).
# Access is always RNA (scene.scenequant.xxx) — never dict style.

import bpy
from .constants import LAST_REPORT_MAXLEN
from bpy.props import (
    BoolProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)


class SceneQuantSettings(bpy.types.PropertyGroup):
    vram_budget_gb: FloatProperty(
        name="VRAM Budget (GB)",
        description=(
            "Physical GPU memory to plan against — the card's total, or your own "
            "ceiling; 0 means not set. Do NOT subtract a reserve yourself: the "
            "planner holds back headroom and what other applications are using. "
            "Use Detect to fill from nvidia-smi"
        ),
        default=0.0,
        min=0.0,
        max=128.0,
        precision=1,
    )
    quality_factor: FloatProperty(
        name="Quality Factor",
        description="Texel-density safety multiplier: 2.0 keeps ~2x more texture resolution than the camera strictly needs",
        default=2.0,
        min=1.0,
        max=8.0,
    )
    coverage_frame_samples: IntProperty(
        name="Frame Samples",
        description="How many frames across the frame range to sample for screen coverage",
        default=5,
        min=1,
        max=50,
    )
    tier_lossless: BoolProperty(
        name="Lossless",
        description="Apply zero-visual-risk settings (interface lock, persistent data policy, denoiser placement)",
        default=True,
    )
    tier_perceptual: BoolProperty(
        name="Perceptually Safe",
        description="Apply settings with negligible visual impact (adaptive sampling, scrambling distance, clamping, bounce caps)",
        default=True,
    )
    min_texture_size: IntProperty(
        name="Min Texture Size",
        description="Quantizer never downscales a texture below this edge length",
        default=256,
        min=64,
        max=4096,
    )
    trim_keep_reflections: BoolProperty(
        name="Keep Reflections",
        description="Trimmed off-screen objects stay visible to glossy/transmission rays so mirrors and glass remain correct (smaller speedup)",
        default=True,
    )
    draft_active: BoolProperty(
        name="Draft Mode Active",
        description="Set while draft render settings are applied",
        default=False,
    )
    preflight_enabled: BoolProperty(
        name="Pre-flight VRAM Check",
        description="Before each render, estimate memory against the VRAM budget (or detected VRAM) and warn when the render will not fit",
        default=True,
    )
    preflight_warning: StringProperty(
        name="Pre-flight Warning",
        description="Internal: last pre-flight over-budget warning; empty when the estimate fits",
        default="",
        options={"HIDDEN"},
    )
    journal_data: StringProperty(
        name="Journal Data",
        description="Internal: serialized optimization journal",
        default="",
        options={"HIDDEN"},
    )
    journal_quarantine: StringProperty(
        name="Journal Quarantine",
        description="Internal: journal data a load refused to interpret, kept so a save cannot clobber it",
        default="",
        options={"HIDDEN"},
    )
    last_report: StringProperty(
        name="Last Report",
        description="Internal: serialized last analysis report",
        default="",
        options={"HIDDEN"},
        maxlen=LAST_REPORT_MAXLEN,
    )
    speed_mode: EnumProperty(
        name="Mode",
        description="Auto applies the full stack in one click. Manual lets you pick what changes",
        items=(
            ("AUTO", "Auto", "One click: all safe speed levers plus a sample-knee probe"),
            ("MANUAL", "Manual", "Choose which classes to apply, then confirm the plan"),
        ),
        default="AUTO",
    )
    speed_probe_knee: BoolProperty(
        name="Probe sample knee",
        description="Render a cheap ladder and cap samples at the proven floor. Auto always does this",
        default=True,
    )
    speed_apply_dead: BoolProperty(
        name="Dead work",
        description="Hide/cull/trim off-screen and leftover passes",
        default=True,
    )
    speed_apply_paths: BoolProperty(
        name="Path settings",
        description="Bounces, clamp, light tree, caustics, world MIS, volumes",
        default=True,
    )


class SceneQuantObject(bpy.types.PropertyGroup):
    override: EnumProperty(
        name="SceneQuant Override",
        description="How SceneQuant may treat this object",
        items=(
            ("AUTO", "Auto", "Optimize based on camera coverage analysis"),
            ("HERO", "Hero", "Never reduce this object's textures or ray visibility"),
            ("EXCLUDE", "Exclude", "Never touch this object at all"),
        ),
        default="AUTO",
    )


class SceneQuantImage(bpy.types.PropertyGroup):
    override: EnumProperty(
        name="SceneQuant Override",
        description="How SceneQuant may treat this image",
        items=(
            ("AUTO", "Auto", "Quantize based on camera coverage analysis"),
            ("KEEP", "Keep", "Never downscale or replace this image"),
        ),
        default="AUTO",
    )


CLASSES = (SceneQuantSettings, SceneQuantObject, SceneQuantImage)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.scenequant = PointerProperty(type=SceneQuantSettings)
    bpy.types.Object.scenequant = PointerProperty(type=SceneQuantObject)
    bpy.types.Image.scenequant = PointerProperty(type=SceneQuantImage)


def unregister():
    del bpy.types.Image.scenequant
    del bpy.types.Object.scenequant
    del bpy.types.Scene.scenequant
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
