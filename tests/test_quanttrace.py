# QuantTrace RenderEngine stub — class contract + refuse + native hello load.
# Duck-typed engine hooks; no bpy, no GPU, no F12.
#   python3 tests/test_quanttrace.py

import importlib.util
import os
import sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _harness  # noqa: E402
from _harness import PROJECT_ROOT, check, finish, section  # noqa: E402


def _load(rel):
    path = os.path.join(PROJECT_ROOT, *rel.split("/"))
    name = rel.replace("/", ".").removesuffix(".py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _read(rel):
    return open(os.path.join(PROJECT_ROOT, *rel.split("/")), encoding="utf-8").read()


class FakeEngine:
    """Harness mock: record report / stats / progress the way RenderEngine would."""

    def __init__(self):
        self.reports = []
        self.stats = []
        self.progress = []
        self.errors = []

    def report(self, rtype, message):
        self.reports.append((rtype, message))

    def update_stats(self, stats, info):
        self.stats.append((stats, info))

    def update_progress(self, value):
        self.progress.append(value)

    def error_set(self, message):
        self.errors.append(message)


class FakeCDLL:
    """ctypes.CDLL stand-in for hello / tracer ABI."""

    def __init__(self, version=b"0.0.1-hello", is_tracer=0, path="fake"):
        self._version = version
        self._is_tracer = is_tracer
        self._path = path
        self.quanttrace_version = mock.Mock(return_value=version)
        self.quanttrace_version.restype = None
        self.quanttrace_version.argtypes = None
        self.quanttrace_is_tracer = mock.Mock(return_value=is_tracer)
        self.quanttrace_is_tracer.restype = None
        self.quanttrace_is_tracer.argtypes = None


def main():
    engine = _load("scenequant/quanttrace/engine.py")

    section("engine class contract")
    check(hasattr(engine, "SQ_QUANTTRACE"), "SQ_QUANTTRACE class exists")
    cls = engine.SQ_QUANTTRACE
    check(getattr(cls, "bl_idname", None) == "SQ_QUANTTRACE",
          "bl_idname is SQ_QUANTTRACE")
    check(getattr(cls, "bl_label", None) == "QuantTrace (experimental)",
          "bl_label is QuantTrace (experimental)")
    label = str(getattr(cls, "bl_label", "")).lower()
    check("experimental" in label, "label marks experimental")
    check("fast" not in label and "faster" not in label and "quality" not in label,
          "label does not claim speed or quality")
    check(callable(getattr(cls, "render", None)), "render method exists")
    check(engine.ENGINE_ID == "SQ_QUANTTRACE", "ENGINE_ID constant")

    section("fallback — no native lib")
    engine._reset_native_probe_for_tests()
    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("QUANTTRACE_LIB", None)
        # Force every candidate path to miss; ignore a real build/ .so on disk.
        with mock.patch.object(engine, "_candidate_lib_paths",
                               return_value=iter(["/no/such/libquanttrace.so"])):
            engine._reset_native_probe_for_tests()
            check(engine.native_lib_loaded() is False, "native_lib_loaded False when missing")
            check(engine.kernel_ready() is False, "kernel_ready False when missing")
            msg = engine.not_built_message().lower()
            check("not built" in msg, "fallback message mentions not built")
            check("does not path-trace" in msg or "path-trace" in msg,
                  "fallback message says does not path-trace")
            check("make it fast" in msg, "fallback points at Make it Fast")
            fake = FakeEngine()
            raised = None
            try:
                engine.refuse_render(fake, None)
            except engine.QuantTraceNotBuilt as exc:
                raised = exc
            check(raised is not None, "refuse_render raises when lib missing")
            check("not built" in str(raised).lower(), "missing-lib exception: not built")
            check(any("not built" in str(item).lower() for item in fake.errors),
                  "error_set got fallback not-built message")

    section("hello loaded — is_tracer==0 still refuses")
    engine._reset_native_probe_for_tests()
    fake_lib = FakeCDLL(version=b"0.0.1-hello", is_tracer=0)
    hello_path = "/tmp/fake/libquanttrace.so"

    def fake_loader(path):
        check(path == hello_path, "loader called with QUANTTRACE_LIB path")
        return fake_lib

    with mock.patch.dict(os.environ, {"QUANTTRACE_LIB": hello_path}):
        with mock.patch.object(engine.os.path, "isfile", return_value=True):
            with mock.patch.object(engine, "_probe_native", wraps=None):
                # Drive probe with injected loader via public reset + direct call.
                pass
            engine._reset_native_probe_for_tests()
            loaded = engine._probe_native(loader=fake_loader)
            check(loaded is True, "probe loads hello via QUANTTRACE_LIB")
            check(engine.native_lib_loaded() is True, "native_lib_loaded True for hello")
            check(engine.native_version() == "0.0.1-hello", "native_version from hello")
            check(engine.native_is_tracer() is False, "is_tracer False for hello")
            check(engine.kernel_ready() is False,
                  "kernel_ready False while is_tracer==0")
            hello_msg = engine.not_built_message()
            hello_l = hello_msg.lower()
            check("native hello loaded" in hello_l, "message: native hello loaded")
            check("0.0.1-hello" in hello_msg, "message includes version")
            check("tracer not built" in hello_l, "message: tracer not built")
            check("does not path-trace" in hello_l, "hello path still refuses path-trace")
            check("make it fast" in hello_l, "hello path points at Make it Fast")
            fake2 = FakeEngine()
            raised2 = None
            try:
                engine.refuse_render(fake2, None)
            except engine.QuantTraceNotBuilt as exc:
                raised2 = exc
            check(raised2 is not None, "refuse_render raises with hello loaded")
            check("native hello loaded" in str(raised2).lower(),
                  "exception is hello-loaded refuse path")
            check(any("hello" in str(item).lower() for item in fake2.errors),
                  "error_set got hello-loaded message")

    section("is_tracer==1 → kernel_ready True")
    engine._reset_native_probe_for_tests()
    tracer_lib = FakeCDLL(version=b"0.1.0-tracer", is_tracer=1)
    tracer_path = "/tmp/fake/libquanttrace_tracer.so"

    def tracer_loader(path):
        return tracer_lib

    with mock.patch.dict(os.environ, {"QUANTTRACE_LIB": tracer_path}):
        with mock.patch.object(engine.os.path, "isfile", return_value=True):
            engine._reset_native_probe_for_tests()
            check(engine._probe_native(loader=tracer_loader) is True,
                  "probe loads tracer stub")
            check(engine.kernel_ready() is True,
                  "kernel_ready True when is_tracer==1")
            check(engine.native_is_tracer() is True, "native_is_tracer True")

    section("render refuses when kernel not ready")
    engine._reset_native_probe_for_tests()
    with mock.patch.object(engine, "_candidate_lib_paths",
                           return_value=iter(["/no/such/libquanttrace.so"])):
        engine._reset_native_probe_for_tests()
        check(engine.kernel_ready() is False, "kernel_ready False when lib missing")
        fake3 = FakeEngine()
        raised3 = None
        try:
            engine.refuse_render(fake3, None)
        except engine.QuantTraceNotBuilt as exc:
            raised3 = exc
        check(raised3 is not None, "refuse_render raises when lib missing")
        msg3 = str(raised3).lower()
        check("not built" in msg3, "missing-lib exception mentions not built")
        check("path-trace" in msg3, "missing-lib exception says no path-trace")
        check("make it fast" in msg3 and "cycles" in msg3,
              "missing-lib points at stock Cycles / Make it Fast")
        check(fake3.progress == [1.0], "update_progress(1.0) on refuse")

        inst = cls()
        inst.error_set = fake3.error_set
        inst.report = fake3.report
        inst.update_stats = fake3.update_stats
        inst.update_progress = fake3.update_progress
        fake3.errors.clear()
        fake3.reports.clear()
        fake3.stats.clear()
        fake3.progress.clear()
        raised_render = None
        try:
            inst.render(None)
        except engine.QuantTraceNotBuilt as exc:
            raised_render = exc
        check(raised_render is not None,
              "SQ_QUANTTRACE.render raises when kernel not ready")
        check("not built" in str(raised_render).lower(),
              "render() exception is the not-built path")

    section("F12 wire sources present")
    src = _read("scenequant/quanttrace/engine.py")
    check("begin_result" in src, "engine.py uses begin_result")
    check("end_result" in src, "engine.py uses end_result")
    check("render_locked_cube" in src, "engine.py has render_locked_cube")
    check("is_locked_cube_scene" in src, "engine.py gates on locked cube")
    check("quanttrace_render_cube_rgba" in src, "engine.py calls rgba ABI")
    check("ctypes" in src and "libquanttrace" in src,
          "engine.py ctypes-loads libquanttrace")
    check("quanttrace_is_tracer" in src, "engine.py consults quanttrace_is_tracer")
    check("kernel_ready" in src, "engine.py defines kernel_ready")
    check("Make it Fast stays on stock Cycles" in src or "Make it Fast" in src,
          "engine.py still points at Make it Fast")

    section("native sources present")
    check(os.path.isfile(os.path.join(PROJECT_ROOT, "native", "quanttrace", "src", "hello.c")),
          "native/quanttrace/src/hello.c exists")
    check(os.path.isfile(os.path.join(PROJECT_ROOT, "native", "quanttrace", "CMakeLists.txt")),
          "native/quanttrace/CMakeLists.txt exists")
    check(os.path.isfile(os.path.join(PROJECT_ROOT, "native", "quanttrace", "README.md")),
          "native/quanttrace/README.md exists")
    hello_c = _read("native/quanttrace/src/hello.c")
    check("quanttrace_version" in hello_c, "hello.c exports version")
    check("QT_EXPORT int quanttrace_is_tracer" not in hello_c
          and "quanttrace_is_tracer(void)" not in hello_c,
          "hello.c no longer exports is_tracer (session_bridge does)")
    check("0.0.2-cube-f12" in hello_c, "hello.c version string 0.0.2-cube-f12")
    readme = _read("native/quanttrace/README.md").lower()
    check("cube" in readme and "slice" in readme, "native README names cube slice")
    check("is_tracer" in readme, "native README documents is_tracer")

    section("cube gate pins in sources")
    cube_py = _read("tools/_quanttrace_cube_scene.py")
    check("TABULATED_SOBOL" in cube_py, "cube script pins TABULATED_SOBOL")
    check("light_sampling_threshold" in cube_py, "cube script pins light_sampling_threshold")
    bridge = _read("native/quanttrace/src/session_bridge.cpp")
    check("SAMPLING_PATTERN_TABULATED_SOBOL" in bridge, "Session pins TABULATED_SOBOL")
    check("transform_scale(1.0f, 1.0f, -1.0f)" in bridge, "Session uses blender_camera_matrix Z-flip")
    check("quanttrace_is_tracer" in bridge, "bridge owns is_tracer")
    check("return 1;" in bridge, "bridge is_tracer returns 1 for QT_WITH_CYCLES")
    check("quanttrace_render_cube_rgba" in bridge, "bridge exports rgba ABI")
    hdr = _read("native/quanttrace/src/quanttrace.h")
    check("quanttrace_render_cube_rgba" in hdr, "header declares rgba ABI")

    section("registration hooks")
    check(callable(engine.register), "engine.register exists")
    check(callable(engine.unregister), "engine.unregister exists")
    init_src = _read("scenequant/__init__.py")
    check("quanttrace" in init_src and "_MODULES" in init_src,
          "addon __init__.py imports quanttrace")
    check("quanttrace" in init_src.split("_MODULES")[1].split("\n")[0],
          "quanttrace is in _MODULES")
    pkg_src = _read("scenequant/quanttrace/__init__.py")
    check("engine.register" in pkg_src, "package register calls engine.register")
    check("engine.unregister" in pkg_src, "package unregister calls engine.unregister")

    section("locked-cube scene gate")
    class FakeInput:
        def __init__(self, value):
            self.default_value = value
    class FakeNode:
        def __init__(self, ntype, strength=0.0):
            self.type = ntype
            self.inputs = {"Strength": FakeInput(strength)}
    class FakeNodeTree:
        def __init__(self, strength=0.0):
            self.nodes = [FakeNode("BACKGROUND", strength)]
    class FakeWorld:
        def __init__(self, strength=0.0):
            self.use_nodes = True
            self.node_tree = FakeNodeTree(strength)
    class FakeData:
        def __init__(self, dtype):
            self.type = dtype
    class FakeObj:
        def __init__(self, otype, dtype=None):
            self.type = otype
            self.data = FakeData(dtype) if dtype else None
    class FakeScene:
        def __init__(self, objs, strength=0.0):
            self.objects = objs
            self.world = FakeWorld(strength)
    ok_scene = FakeScene([
        FakeObj("MESH"), FakeObj("LIGHT", "AREA"), FakeObj("CAMERA"),
    ], strength=0.0)
    check(engine.is_locked_cube_scene(ok_scene) is True, "locked cube shape accepted")
    bad = FakeScene([FakeObj("MESH"), FakeObj("MESH"), FakeObj("LIGHT", "AREA"),
                     FakeObj("CAMERA")])
    check(engine.is_locked_cube_scene(bad) is False, "two meshes refused")
    lit = FakeScene([FakeObj("MESH"), FakeObj("LIGHT", "AREA"), FakeObj("CAMERA")],
                    strength=1.0)
    check(engine.is_locked_cube_scene(lit) is False, "lit world refused")

    section("Make it Fast stays on stock Cycles")
    solver_src = _read("scenequant/planning/speed_solver.py")
    check("SQ_QUANTTRACE" not in solver_src and "QUANTTRACE" not in solver_src,
          "build_speed_plan is not switched to QuantTrace")
    apply_src = _read("scenequant/apply/speed_apply.py")
    check("SQ_QUANTTRACE" not in apply_src and "QUANTTRACE" not in apply_src,
          "speed_apply is not switched to QuantTrace")

    section("research brief present")
    brief = os.path.join(PROJECT_ROOT, "docs", "research", "SIDECAR-INTEGRATOR.md")
    check(os.path.isfile(brief), "docs/research/SIDECAR-INTEGRATOR.md exists")
    if os.path.isfile(brief):
        brief_txt = open(brief, encoding="utf-8").read()
        check("SQ_QUANTTRACE" in brief_txt, "brief names SQ_QUANTTRACE")
        check("Make it Fast stays on stock Cycles" in brief_txt,
              "brief keeps Make it Fast on stock Cycles")

    finish()


main()
