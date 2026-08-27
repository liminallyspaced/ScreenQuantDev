# QuantTrace RenderEngine stub + native hello load plumbing.
#
# Slice 0/1 socket only: register SQ_QUANTTRACE; optionally ctypes-load
# libquanttrace (hello). render() does not path-trace and does not write
# pixels. kernel_ready is False until quanttrace_is_tracer() == 1.
# Make it Fast stays on stock Cycles.
# Design: docs/research/SIDECAR-INTEGRATOR.md

from __future__ import annotations

import ctypes
import os

ENGINE_ID = "SQ_QUANTTRACE"
ENGINE_LABEL = "QuantTrace (experimental)"
NOT_BUILT_MESSAGE = (
    "QuantTrace native Cycles-fork kernel is not built yet. "
    "This engine is an experimental stub and does not path-trace. "
    "Make it Fast stays on stock Cycles."
)
HELLO_LOADED_MESSAGE = (
    "QuantTrace native hello loaded (v{version}); tracer not built. "
    "This engine does not path-trace. "
    "Make it Fast stays on stock Cycles."
)
PANEL_NOTE = "experimental stub — native hello / kernel TBD; Make it Fast is the product"

try:
    import bpy
    _RenderEngine = bpy.types.RenderEngine
    _Panel = bpy.types.Panel
except (ImportError, AttributeError):
    bpy = None
    _RenderEngine = object
    _Panel = object

# Native probe cache (reset via _reset_native_probe_for_tests).
_native_probed = False
_native_lib = None
_native_version = None
_native_is_tracer = False
_native_path = None


class QuantTraceNotBuilt(RuntimeError):
    """F12 asked of the stub — no tracer kernel ships in this slice."""


def _repo_root_from_engine():
    # scenequant/quanttrace/engine.py -> repo root (addon-adjacent native/)
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(os.path.dirname(here))


def _candidate_lib_paths():
    env = os.environ.get("QUANTTRACE_LIB")
    if env:
        yield env
    root = _repo_root_from_engine()
    build = os.path.join(root, "native", "quanttrace", "build")
    names = (
        "libquanttrace.so",
        "libquanttrace.dylib",
        "quanttrace.dll",
        "libquanttrace.dll",
    )
    for name in names:
        yield os.path.join(build, name)
        for cfg in ("Release", "Debug", "RelWithDebInfo", "MinSizeRel"):
            yield os.path.join(build, cfg, name)


def _reset_native_probe_for_tests():
    """Clear ctypes probe cache so unit tests can force load/fallback paths."""
    global _native_probed, _native_lib, _native_version, _native_is_tracer
    global _native_path
    _native_probed = False
    _native_lib = None
    _native_version = None
    _native_is_tracer = False
    _native_path = None


def _probe_native(loader=None):
    """Try ctypes load of libquanttrace. Idempotent until reset.

    loader: optional callable(path) -> CDLL-like; defaults to ctypes.CDLL.
    Returns True if a library was loaded.
    """
    global _native_probed, _native_lib, _native_version, _native_is_tracer
    global _native_path
    if _native_probed:
        return _native_lib is not None
    _native_probed = True
    load = loader if loader is not None else ctypes.CDLL
    for path in _candidate_lib_paths():
        if not path or not os.path.isfile(path):
            continue
        try:
            lib = load(path)
        except OSError:
            continue
        try:
            lib.quanttrace_version.restype = ctypes.c_char_p
            lib.quanttrace_version.argtypes = []
            lib.quanttrace_is_tracer.restype = ctypes.c_int
            lib.quanttrace_is_tracer.argtypes = []
            raw = lib.quanttrace_version()
            if isinstance(raw, bytes):
                version = raw.decode("utf-8", errors="replace")
            else:
                version = str(raw) if raw is not None else "unknown"
            is_tracer = int(lib.quanttrace_is_tracer()) == 1
        except (AttributeError, TypeError, ValueError, OSError):
            continue
        _native_lib = lib
        _native_version = version
        _native_is_tracer = is_tracer
        _native_path = path
        return True
    return False


def native_lib_loaded():
    _probe_native()
    return _native_lib is not None


def native_version():
    _probe_native()
    return _native_version


def native_is_tracer():
    _probe_native()
    return bool(_native_is_tracer)


def native_lib_path():
    _probe_native()
    return _native_path


def not_built_message():
    if native_lib_loaded() and not native_is_tracer():
        return HELLO_LOADED_MESSAGE.format(version=native_version() or "unknown")
    return NOT_BUILT_MESSAGE


def kernel_ready():
    """True only when native lib is loaded and quanttrace_is_tracer() == 1."""
    return native_lib_loaded() and native_is_tracer()


def refuse_render(engine, depsgraph=None):
    """Shared refuse path for render() and unit tests (no bpy required).

    Reports the missing/incomplete kernel, updates progress/stats when those
    hooks exist, and raises QuantTraceNotBuilt. Never writes a result buffer.
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
        "Experimental stub. Native Cycles-fork kernel / tracer not built. "
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
