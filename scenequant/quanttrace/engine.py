# QuantTrace RenderEngine — depsgraph-fed Session F12 when is_tracer==1.
#
# Slice 2b: native lib with QT_WITH_CYCLES returns is_tracer=1 and
# SQ_QUANTTRACE.render packs a simple depsgraph scene (one mesh +
# Principled + one AREA + camera + black world) into QT_SimpleScene and
# lands Combined via begin_result / end_result. Kitchens / multi-mesh /
# linked shaders refuse with a named reason.
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
SIMPLE_ONLY_MESSAGE = (
    "QuantTrace F12 currently syncs only simple scenes: one mesh with a "
    "constant Principled BSDF, one AREA light (no nodes), one camera, "
    "and a black/constant world. Multi-mesh / linked shaders / kitchens "
    "are not wired yet. Make it Fast stays on stock Cycles."
)
PANEL_NOTE = (
    "experimental — simple-scene uni-PT when native is_tracer=1; "
    "Make it Fast is the product"
)

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
    """F12 asked without a tracer kernel."""


class QuantTraceUnsupported(RuntimeError):
    """F12 asked on a scene QuantTrace cannot sync yet."""


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


def _scene_from_depsgraph(depsgraph):
    if depsgraph is None:
        return None
    scene = getattr(depsgraph, "scene", None)
    if scene is not None:
        return scene
    return getattr(depsgraph, "scene_eval", None)


def is_locked_cube_scene(scene):
    """True when the scene matches the QUANTTRACE-CUBE.md toy shape.

    One MESH, one AREA light, one CAMERA, black world strength ~0.
    Not a full DNA hash — enough to refuse kitchens loudly.
    """
    if scene is None:
        return False
    objs = list(getattr(scene, "objects", []) or [])
    meshes = [o for o in objs if getattr(o, "type", None) == "MESH"]
    lights = [o for o in objs if getattr(o, "type", None) == "LIGHT"]
    cams = [o for o in objs if getattr(o, "type", None) == "CAMERA"]
    if len(meshes) != 1 or len(lights) != 1 or len(cams) != 1:
        return False
    lamp = lights[0]
    data = getattr(lamp, "data", None)
    if data is None or getattr(data, "type", None) != "AREA":
        return False
    world = getattr(scene, "world", None)
    if world is None:
        return False
    # Prefer noded Background Strength; accept missing nodes as fail-closed.
    nt = getattr(world, "node_tree", None) if getattr(world, "use_nodes", False) else None
    if nt is not None:
        bg = None
        for node in getattr(nt, "nodes", []) or []:
            if getattr(node, "type", None) == "BACKGROUND":
                bg = node
                break
        if bg is not None:
            strength = bg.inputs["Strength"].default_value
            if abs(float(strength)) > 1e-6:
                return False
    return True


def _render_size(scene):
    scale = float(scene.render.resolution_percentage) / 100.0
    width = max(1, int(scene.render.resolution_x * scale))
    height = max(1, int(scene.render.resolution_y * scale))
    cycles = getattr(scene, "cycles", None)
    samples = int(getattr(cycles, "samples", 128) or 128)
    samples = max(1, min(samples, 8192))
    width = min(width, 8192)
    height = min(height, 8192)
    return width, height, samples


def _bind_render_scene_rgba(lib):
    from . import sync as qt_sync
    QT_SimpleScene = qt_sync.make_qt_simple_scene_type()
    lib.quanttrace_render_scene_rgba.argtypes = [
        ctypes.POINTER(QT_SimpleScene),
        ctypes.POINTER(ctypes.c_float),
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_int),
        ctypes.POINTER(ctypes.c_int),
    ]
    lib.quanttrace_render_scene_rgba.restype = ctypes.c_int
    return QT_SimpleScene


def _refuse_unsupported(engine, message):
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
            pass
    stats = getattr(engine, "update_stats", None)
    if callable(stats):
        try:
            stats("QuantTrace", message)
        except TypeError:
            pass
    print(f"[QuantTrace] {message}")
    raise QuantTraceUnsupported(message)


def render_simple_scene(engine, depsgraph):
    """Pack depsgraph → QT_SimpleScene and write Combined into the result."""
    from . import sync as qt_sync

    scene = _scene_from_depsgraph(depsgraph)
    try:
        packed = qt_sync.pack_simple_scene(scene, depsgraph=depsgraph)
    except qt_sync.QuantTraceSyncError as exc:
        _refuse_unsupported(
            engine,
            f"{SIMPLE_ONLY_MESSAGE} ({exc})",
        )
        return

    if not kernel_ready() or _native_lib is None:
        refuse_render(engine, depsgraph)
        return

    lib = _native_lib
    QT_SimpleScene = _bind_render_scene_rgba(lib)
    desc = qt_sync.to_ctypes(packed, QT_SimpleScene)
    width = int(packed["width"])
    height = int(packed["height"])
    samples = int(packed["samples"])
    nfloat = width * height * 4
    buf = (ctypes.c_float * nfloat)()
    out_w = ctypes.c_int(0)
    out_h = ctypes.c_int(0)

    stats = getattr(engine, "update_stats", None)
    if callable(stats):
        try:
            stats(
                "QuantTrace",
                f"depsgraph simple uni-PT {width}x{height} {samples} spp "
                f"v{native_version() or '?'} "
                f"({packed['nverts'] if 'nverts' in packed else len(packed['verts']) // 3}v/"
                f"{len(packed['tris']) // 3}t)",
            )
        except TypeError:
            pass
    progress = getattr(engine, "update_progress", None)
    if callable(progress):
        try:
            progress(0.05)
        except TypeError:
            pass

    rc = lib.quanttrace_render_scene_rgba(
        ctypes.byref(desc), buf, nfloat, ctypes.byref(out_w), ctypes.byref(out_h)
    )
    if rc != 0 or out_w.value != width or out_h.value != height:
        message = (
            f"QuantTrace Session render failed (rc={rc}, "
            f"size={out_w.value}x{out_h.value}, expected {width}x{height})."
        )
        error_set = getattr(engine, "error_set", None)
        if callable(error_set):
            try:
                error_set(message)
            except TypeError:
                pass
        print(f"[QuantTrace] {message}")
        raise QuantTraceNotBuilt(message)

    begin = getattr(engine, "begin_result", None)
    end = getattr(engine, "end_result", None)
    if not callable(begin) or not callable(end):
        raise QuantTraceNotBuilt("RenderEngine begin_result/end_result missing")

    result = begin(0, 0, width, height)
    try:
        layer = result.layers[0]
        combined = None
        try:
            combined = layer.passes["Combined"]
        except (KeyError, TypeError, AttributeError):
            passes = list(getattr(layer, "passes", []) or [])
            combined = passes[0] if passes else None
        if combined is None:
            raise QuantTraceNotBuilt("no Combined pass on render result")
        flat = [float(buf[i]) for i in range(nfloat)]
        try:
            combined.rect.foreach_set(flat)
        except (AttributeError, TypeError):
            combined.rect = [
                (flat[i], flat[i + 1], flat[i + 2], flat[i + 3])
                for i in range(0, nfloat, 4)
            ]
    finally:
        end(result)

    if callable(progress):
        try:
            progress(1.0)
        except TypeError:
            pass
    if callable(stats):
        try:
            stats("QuantTrace", f"done {width}x{height} {samples} spp")
        except TypeError:
            pass
    print(
        f"[QuantTrace] F12 depsgraph simple Combined "
        f"{width}x{height} {samples} spp v{native_version() or '?'}"
    )


# Back-compat alias used by older tests / docs.
def render_locked_cube(engine, depsgraph):
    return render_simple_scene(engine, depsgraph)


class SQ_QUANTTRACE(_RenderEngine):
    bl_idname = ENGINE_ID
    bl_label = ENGINE_LABEL
    bl_description = (
        "Experimental QuantTrace. Simple-scene uni-PT when native is_tracer=1. "
        "Make it Fast stays on stock Cycles."
    )
    bl_use_preview = False
    bl_use_shading_nodes_custom = False
    bl_use_eevee_viewport = True
    bl_use_postprocess = False
    bl_use_gpu_context = False

    def update_render_passes(self, scene=None, renderlayer=None):
        # Ensure Combined exists for custom engines on all Blender 4/5 builds.
        register = getattr(self, "register_pass", None)
        if callable(register) and scene is not None and renderlayer is not None:
            try:
                register(scene, renderlayer, "Combined", 4, "RGBA", "COLOR")
            except TypeError:
                pass

    def render(self, depsgraph):
        if not kernel_ready():
            refuse_render(self, depsgraph)
            return
        render_simple_scene(self, depsgraph)


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
        if kernel_ready():
            self.layout.label(
                text=f"native v{native_version() or '?'} — simple-scene F12 ready"
            )
        elif native_lib_loaded():
            self.layout.label(text=f"native v{native_version() or '?'} — tracer off")
        else:
            self.layout.label(text="native lib not loaded")


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
