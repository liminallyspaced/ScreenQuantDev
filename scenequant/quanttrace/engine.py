# QuantTrace RenderEngine stub.
#
# Slice 0 socket only: register SQ_QUANTTRACE so it appears in the Render
# Engine dropdown. render() does not path-trace and does not write pixels.
# Native Cycles-fork kernel is not built. Make it Fast stays on stock Cycles.
# Design: docs/research/SIDECAR-INTEGRATOR.md

ENGINE_ID = "SQ_QUANTTRACE"
ENGINE_LABEL = "QuantTrace (experimental)"
NOT_BUILT_MESSAGE = (
    "QuantTrace native Cycles-fork kernel is not built yet. "
    "This engine is an experimental stub and does not path-trace. "
    "Make it Fast stays on stock Cycles."
)
PANEL_NOTE = "experimental stub — native kernel TBD; Make it Fast is the product"

try:
    import bpy
    _RenderEngine = bpy.types.RenderEngine
    _Panel = bpy.types.Panel
except (ImportError, AttributeError):
    bpy = None
    _RenderEngine = object
    _Panel = object


class QuantTraceNotBuilt(RuntimeError):
    """F12 asked of the stub — no native kernel ships in this slice."""


def not_built_message():
    return NOT_BUILT_MESSAGE


def kernel_ready():
    """Always False until a native kernel ships. Tests assert this."""
    return False


def refuse_render(engine, depsgraph=None):
    """Shared refuse path for render() and unit tests (no bpy required).

    Reports the missing kernel, updates progress/stats when those hooks
    exist, and raises QuantTraceNotBuilt. Never writes a result buffer.
    """
    message = not_built_message()
    error_set = getattr(engine, "error_set", None)
    if callable(error_set):
        try:
            error_set(message)
        except TypeError:
            pass
    reporter = getattr(engine, "report", None)
    if callable(reporter):
        try:
            reporter({"ERROR"}, message)
        except TypeError:
            try:
                reporter(message)
            except Exception:
                pass
    stats = getattr(engine, "update_stats", None)
    if callable(stats):
        try:
            stats("QuantTrace", message)
        except TypeError:
            pass
    progress = getattr(engine, "update_progress", None)
    if callable(progress):
        try:
            progress(1.0)
        except TypeError:
            pass
    print(f"[QuantTrace] {message}")
    raise QuantTraceNotBuilt(message)


class SQ_QUANTTRACE(_RenderEngine):
    bl_idname = ENGINE_ID
    bl_label = ENGINE_LABEL
    bl_description = (
        "Experimental stub. Native Cycles-fork kernel is not built. "
        "Make it Fast stays on stock Cycles."
    )
    bl_use_preview = False
    bl_use_shading_nodes_custom = False
    bl_use_eevee_viewport = True
    bl_use_postprocess = False
    bl_use_gpu_context = False

    def render(self, depsgraph):
        refuse_render(self, depsgraph)


class SQ_PT_quanttrace_note(_Panel):
    bl_space_type = "PROPERTIES"
    bl_region_type = "WINDOW"
    bl_context = "render"
    bl_idname = "SQ_PT_QUANTTRACE_NOTE"
    bl_label = "QuantTrace"
    COMPAT_ENGINES = {ENGINE_ID}

    @classmethod
    def poll(cls, context):
        engine = getattr(
            getattr(getattr(context, "scene", None), "render", None),
            "engine",
            None,
        )
        return engine == ENGINE_ID

    def draw(self, context):
        self.layout.label(text=PANEL_NOTE)


CLASSES = (SQ_QUANTTRACE, SQ_PT_quanttrace_note)


def register():
    if bpy is None:
        raise RuntimeError("bpy is required to register QuantTrace")
    for cls in CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    if bpy is None:
        return
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
