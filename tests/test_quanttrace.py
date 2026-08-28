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
    check("quanttrace_render_cube_rgba" in src or "quanttrace_render_scene_rgba" in src,
          "engine.py calls rgba/scene ABI")
    check("render_simple_scene" in src, "engine.py has render_simple_scene")
    check("pack_simple_scene" in src or "qt_sync" in src,
          "engine.py uses depsgraph sync packer")
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
    check("0.0.21-slice2t" in hello_c, "hello.c version string 0.0.21-slice2t")
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
    check(engine.is_locked_cube_scene(bad) is False, "locked-cube gate still refuses two meshes")
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

    section("depsgraph sync module")
    sync = _load("scenequant/quanttrace/sync.py")
    check(callable(sync.pack_simple_scene), "sync.pack_simple_scene exists")
    check(callable(sync.can_sync_simple), "sync.can_sync_simple exists")
    check(callable(sync.make_qt_simple_scene_type), "sync.make_qt_simple_scene_type exists")
    check(callable(sync.pack_scene), "sync.pack_scene exists")
    check(callable(sync.can_sync_scene), "sync.can_sync_scene exists")
    check(callable(sync.make_qt_scene_types), "sync.make_qt_scene_types exists")
    check(callable(sync.to_ctypes_scene), "sync.to_ctypes_scene exists")
    check(sync.QT_MAX_MESHES == 32, "QT_MAX_MESHES is 32")
    check(sync.QT_MAX_LIGHTS == 16, "QT_MAX_LIGHTS is 16")
    check(issubclass(sync.QuantTraceSyncError, RuntimeError), "QuantTraceSyncError is RuntimeError")
    hdr = _read("native/quanttrace/src/quanttrace.h")
    check("QT_SimpleScene" in hdr, "header declares QT_SimpleScene")
    check("QT_Scene" in hdr, "header declares QT_Scene")
    check("QT_Mesh" in hdr, "header declares QT_Mesh")
    check("quanttrace_render_scene_rgba" in hdr, "header declares render_scene_rgba")
    check("quanttrace_render_qt_scene_rgba" in hdr, "header declares render_qt_scene_rgba")
    bridge = _read("native/quanttrace/src/session_bridge.cpp")
    check("quanttrace_render_scene_rgba" in bridge, "bridge exports render_scene_rgba")
    check("quanttrace_render_qt_scene_rgba" in bridge, "bridge exports render_qt_scene_rgba")
    check("build_qt_scene" in bridge, "bridge has build_qt_scene")
    check("build_simple_scene" in bridge, "bridge keeps build_simple_scene wrapper")
    check("fill_locked_cube_desc" in bridge, "locked cube still fills via desc")
    src_e = _read("scenequant/quanttrace/engine.py")
    check("pack_scene" in src_e, "engine.py packs via pack_scene")
    check("quanttrace_render_qt_scene_rgba" in src_e, "engine.py calls qt_scene ABI")
    tools = _read("tools/_quanttrace_multimesh_scene.py")
    check("build_still_life" in tools, "still-life builder exists")
    smoke = _read("tools/_quanttrace_multimesh_smoke.py")
    check("pack_scene" in smoke and "render_qt_scene_rgba" in smoke,
          "still-life smoke packs QT_Scene")

    section("Slice 2f textured Principled ABI")
    hdr = _read("native/quanttrace/src/quanttrace.h")
    check("image_path" in hdr, "QT_Mesh has image_path")
    check("image_colorspace" in hdr, "QT_Mesh has image_colorspace")
    bridge = _read("native/quanttrace/src/session_bridge.cpp")
    check("ImageTextureNode" in bridge, "bridge builds ImageTextureNode")
    check("ATTR_STD_UV" in bridge, "bridge writes ATTR_STD_UV")
    sync_src = _read("scenequant/quanttrace/sync.py")
    check("_tex_image_from_base_color" in sync_src, "sync allows TEX_IMAGE Base Color")
    check("_mesh_corner_uvs" in sync_src, "sync packs corner UVs")
    check(callable(sync._tex_image_from_base_color), "sync._tex_image_from_base_color")
    check(callable(sync._mesh_corner_uvs), "sync._mesh_corner_uvs")
    check(callable(sync._principled_from_material), "sync._principled_from_material")

    class _Sock:
        def __init__(self, value, linked=False, links=None):
            self.default_value = value
            self.is_linked = linked
            self.links = links or []
    class _Inputs(dict):
        def get(self, k, default=None):
            return dict.get(self, k, default)
    class _FromSock:
        name = "Color"
    class _Link:
        def __init__(self, node):
            self.from_node = node
            self.from_socket = _FromSock()
    class _ImgCS:
        name = "Linear Rec.709"
    class _Img:
        def __init__(self, path):
            self.filepath = path
            self.colorspace_settings = _ImgCS()
            self.filepath_from_user = lambda: path
    class _Tex:
        def __init__(self, path):
            self.type = "TEX_IMAGE"
            self.image = _Img(path)
            self.inputs = _Inputs(Vector=_Sock((0, 0, 0), linked=False))
    tmp_img = "/tmp/qt_test_checker_missing.exr"
    # missing file must refuse
    tex_missing = _Tex(tmp_img)
    class _Bsdf:
        def __init__(self, tex):
            self.type = "BSDF_PRINCIPLED"
            self.inputs = _Inputs({
                "Base Color": _Sock((0.8, 0.8, 0.8, 1), linked=True,
                                   links=[_Link(tex)]),
                "Roughness": _Sock(0.5),
                "Metallic": _Sock(0.0),
                "IOR": _Sock(1.45),
                "Alpha": _Sock(1.0),
            })
    class _Tree:
        def __init__(self, tex):
            self.nodes = [_Bsdf(tex)]
    class _Mat:
        def __init__(self, tex):
            self.use_nodes = True
            self.node_tree = _Tree(tex)
    raised = None
    try:
        sync._principled_from_material(_Mat(tex_missing))
    except sync.QuantTraceSyncError as exc:
        raised = exc
    check(raised is not None, "missing image filepath refuses")
    check("filepath" in str(raised).lower() or "disk" in str(raised).lower(),
          "refuse names missing disk filepath")

    # other linked socket still refuses
    class _BsdfRough:
        type = "BSDF_PRINCIPLED"
        inputs = _Inputs({
            "Base Color": _Sock((0.8, 0.8, 0.8, 1)),
            "Roughness": _Sock(0.5, linked=True, links=["x"]),
            "Metallic": _Sock(0.0),
            "IOR": _Sock(1.45),
            "Alpha": _Sock(1.0),
        })
    class _TreeR:
        nodes = [_BsdfRough()]
    class _MatR:
        use_nodes = True
        node_tree = _TreeR()
    raised_r = None
    try:
        sync._principled_from_material(_MatR())
    except sync.QuantTraceSyncError as exc:
        raised_r = exc
    check(raised_r is not None, "linked Roughness still refuses")

    tex_tools = _read("tools/_quanttrace_tex_scene.py")
    check("ShaderNodeTexImage" in tex_tools, "tex scene wires Image Texture")
    smoke = _read("tools/_quanttrace_tex_smoke.py")
    check("pack_scene" in smoke and "render_qt_scene_rgba" in smoke,
          "tex smoke packs QT_Scene")

    section("Slice 2j Normal Map TEX_IMAGE ABI")
    hdr = _read("native/quanttrace/src/quanttrace.h")
    check("normal_image_path" in hdr, "QT_Mesh has normal_image_path")
    check("normal_strength" in hdr, "QT_Mesh has normal_strength")
    bridge = _read("native/quanttrace/src/session_bridge.cpp")
    check("NormalMapNode" in bridge, "bridge builds NormalMapNode")
    check("NODE_NORMAL_MAP_TANGENT" in bridge, "bridge pins Tangent space")
    hello = _read("native/quanttrace/src/hello.c")
    check("0.0.21-slice2t" in hello, "hello version is 0.0.21-slice2t")
    sync_src = _read("scenequant/quanttrace/sync.py")
    check("_normal_map_from_sock" in sync_src, "sync parses Normal Map")
    check(callable(sync._normal_map_from_sock), "sync._normal_map_from_sock")
    ntools = _read("tools/_quanttrace_normal_scene.py")
    check("ShaderNodeNormalMap" in ntools, "normal scene wires Normal Map")
    nsmoke = _read("tools/_quanttrace_normal_smoke.py")
    check("pack_scene" in nsmoke and "render_qt_scene_rgba" in nsmoke,
          "normal smoke packs QT_Scene")

    class _Bump:
        type = "BUMP"
    class _FromN:
        name = "Normal"
    class _NLink:
        from_node = _Bump()
        from_socket = _FromN()
    class _BsdfN:
        type = "BSDF_PRINCIPLED"
        inputs = _Inputs({
            "Base Color": _Sock((0.8, 0.8, 0.8, 1)),
            "Roughness": _Sock(0.5),
            "Metallic": _Sock(0.0),
            "IOR": _Sock(1.45),
            "Alpha": _Sock(1.0),
            "Normal": _Sock((0, 0, 1), linked=True, links=[_NLink()]),
        })
    class _TreeN:
        nodes = [_BsdfN()]
    class _MatN:
        use_nodes = True
        node_tree = _TreeN()
    raised_n = None
    try:
        sync._principled_from_material(_MatN())
    except sync.QuantTraceSyncError as exc:
        raised_n = exc
    check(raised_n is not None, "linked Bump → Normal refuses")
    check("bump" in str(raised_n).lower() or "normal map" in str(raised_n).lower(),
          "refuse names Bump / Normal Map")

    section("Slice 2k Generated TEX_COORD ABI")
    hdr = _read("native/quanttrace/src/quanttrace.h")
    check("QT_TEX_VECTOR_TEXCOORD_GENERATED" in hdr, "header has GENERATED mode 3")
    check("QT_TEX_VECTOR_MAPPING_GENERATED" in hdr, "header has MAPPING_GENERATED mode 4")
    bridge = _read("native/quanttrace/src/session_bridge.cpp")
    check("ATTR_STD_GENERATED" in bridge, "bridge fills ATTR_STD_GENERATED")
    check('output("Generated")' in bridge or "output(coord_sock)" in bridge,
          "bridge connects Generated socket")
    hello = _read("native/quanttrace/src/hello.c")
    check("0.0.21-slice2t" in hello, "hello version is 0.0.21-slice2t")
    sync_src = _read("scenequant/quanttrace/sync.py")
    check("_tex_coord_space_from_vector_link" in sync_src, "sync parses Generated")
    check("Generated" in sync_src, "sync names Generated")
    gtools = _read("tools/_quanttrace_generated_scene.py")
    check("Generated" in gtools, "generated scene wires Generated")
    gsmoke = _read("tools/_quanttrace_generated_smoke.py")
    check("pack_scene" in gsmoke and "render_qt_scene_rgba" in gsmoke,
          "generated smoke packs QT_Scene")

    section("Slice 2m Camera TEX_COORD ABI")
    hdr = _read("native/quanttrace/src/quanttrace.h")
    check("QT_TEX_VECTOR_TEXCOORD_CAMERA" in hdr, "header has CAMERA mode 7")
    check("QT_TEX_VECTOR_MAPPING_CAMERA" in hdr, "header has MAPPING_CAMERA mode 8")
    bridge = _read("native/quanttrace/src/session_bridge.cpp")
    check("tex_mode_is_camera" in bridge, "bridge has camera mode helper")
    check('"Camera"' in bridge, "bridge names Camera socket")
    hello = _read("native/quanttrace/src/hello.c")
    check("0.0.21-slice2t" in hello, "hello version is 0.0.21-slice2t")
    sync_src = _read("scenequant/quanttrace/sync.py")
    check("Camera" in sync_src, "sync names Camera")
    ctools = _read("tools/_quanttrace_camera_scene.py")
    check("Camera" in ctools, "camera scene wires Camera")
    csmoke = _read("tools/_quanttrace_camera_smoke.py")
    check("pack_scene" in csmoke and "render_qt_scene_rgba" in csmoke,
          "camera smoke packs QT_Scene")

    section("Slice 2n Window/Reflection TEX_COORD ABI")
    hdr = _read("native/quanttrace/src/quanttrace.h")
    check("QT_TEX_VECTOR_TEXCOORD_WINDOW" in hdr, "header has WINDOW mode 9")
    check("QT_TEX_VECTOR_MAPPING_WINDOW" in hdr, "header has MAPPING_WINDOW mode 10")
    check("QT_TEX_VECTOR_TEXCOORD_REFLECTION" in hdr, "header has REFLECTION mode 11")
    check("QT_TEX_VECTOR_MAPPING_REFLECTION" in hdr, "header has MAPPING_REFLECTION mode 12")
    bridge = _read("native/quanttrace/src/session_bridge.cpp")
    check("tex_mode_is_window" in bridge, "bridge has window mode helper")
    check("tex_mode_is_reflection" in bridge, "bridge has reflection mode helper")
    check('"Window"' in bridge, "bridge names Window socket")
    check('"Reflection"' in bridge, "bridge names Reflection socket")
    hello = _read("native/quanttrace/src/hello.c")
    check("0.0.21-slice2t" in hello, "hello version is 0.0.21-slice2t")
    sync_src = _read("scenequant/quanttrace/sync.py")
    check("Window" in sync_src and "Reflection" in sync_src, "sync names Window/Reflection")
    check("tex_vector_mode = 9" in sync_src, "sync assigns Window texcoord mode 9")
    check("tex_vector_mode = 10" in sync_src, "sync assigns Window mapping mode 10")
    check("tex_vector_mode = 11" in sync_src, "sync assigns Reflection texcoord mode 11")
    check("tex_vector_mode = 12" in sync_src, "sync assigns Reflection mapping mode 12")
    wtools = _read("tools/_quanttrace_window_scene.py")
    check("Window" in wtools, "window scene wires Window")
    wsmoke = _read("tools/_quanttrace_window_smoke.py")
    check("pack_scene" in wsmoke and "render_qt_scene_rgba" in wsmoke,
          "window smoke packs QT_Scene")
    rtools = _read("tools/_quanttrace_reflection_scene.py")
    check("Reflection" in rtools, "reflection scene wires Reflection")
    rsmoke = _read("tools/_quanttrace_reflection_smoke.py")
    check("pack_scene" in rsmoke and "render_qt_scene_rgba" in rsmoke,
          "reflection smoke packs QT_Scene")

    section("Slice 2o IOR/Alpha TEX_IMAGE ABI")
    hdr = _read("native/quanttrace/src/quanttrace.h")
    check("ior_image_path" in hdr, "QT_Mesh has ior_image_path")
    check("alpha_image_path" in hdr, "QT_Mesh has alpha_image_path")
    bridge = _read("native/quanttrace/src/session_bridge.cpp")
    check('bsdf->input("IOR")' in bridge, "bridge connects IOR TEX_IMAGE")
    check('bsdf->input("Alpha")' in bridge, "bridge connects Alpha TEX_IMAGE")
    hello = _read("native/quanttrace/src/hello.c")
    check("0.0.21-slice2t" in hello, "hello version is 0.0.21-slice2t")
    sync_src = _read("scenequant/quanttrace/sync.py")
    check('("IOR", ("IOR",), "ior")' in sync_src, "sync accepts IOR TEX_IMAGE")
    check('("Alpha", ("Alpha",), "alpha")' in sync_src, "sync accepts Alpha TEX_IMAGE")
    check("ior_image_path" in sync_src and "alpha_image_path" in sync_src,
          "sync packs ior_/alpha_ TEX_IMAGE fields")
    itools = _read("tools/_quanttrace_ioralpha_scene.py")
    check("IOR" in itools and "Alpha" in itools, "ioralpha scene wires IOR/Alpha")
    ismoke = _read("tools/_quanttrace_ioralpha_smoke.py")
    check("pack_scene" in ismoke and "render_qt_scene_rgba" in ismoke,
          "ioralpha smoke packs QT_Scene")


    section("Slice 2p Transmission/Specular TEX_IMAGE ABI")
    hdr = _read("native/quanttrace/src/quanttrace.h")
    check("trans_image_path" in hdr, "QT_Mesh has trans_image_path")
    check("spec_image_path" in hdr, "QT_Mesh has spec_image_path")
    bridge = _read("native/quanttrace/src/session_bridge.cpp")
    check('bsdf->input("Transmission Weight")' in bridge,
          "bridge connects Transmission Weight TEX_IMAGE")
    check('bsdf->input("Specular IOR Level")' in bridge,
          "bridge connects Specular IOR Level TEX_IMAGE")
    hello = _read("native/quanttrace/src/hello.c")
    check("0.0.21-slice2t" in hello, "hello version is 0.0.21-slice2t")
    sync_src = _read("scenequant/quanttrace/sync.py")
    check("Transmission Weight" in sync_src, "sync accepts Transmission Weight")
    check("Specular IOR Level" in sync_src, "sync accepts Specular IOR Level")
    check("trans_image_path" in sync_src and "spec_image_path" in sync_src,
          "sync packs trans_/spec_ TEX_IMAGE fields")
    ttools = _read("tools/_quanttrace_transspec_scene.py")
    check("Transmission" in ttools and "Specular" in ttools,
          "transspec scene wires Transmission/Specular")
    tsmoke = _read("tools/_quanttrace_transspec_smoke.py")
    check("pack_scene" in tsmoke and "render_qt_scene_rgba" in tsmoke,
          "transspec smoke packs QT_Scene")

    class _BsdfCoat:
        type = "BSDF_PRINCIPLED"
        inputs = _Inputs({
            "Base Color": _Sock((0.8, 0.8, 0.8, 1)),
            "Roughness": _Sock(0.5),
            "Metallic": _Sock(0.0),
            "IOR": _Sock(1.45),
            "Alpha": _Sock(1.0),
            "Coat Normal": _Sock((0,0,1), linked=True, links=["x"]),
        })
    class _TreeC:
        nodes = [_BsdfCoat()]
    class _MatC:
        use_nodes = True
        node_tree = _TreeC()
    raised_c = None
    try:
        sync._principled_from_material(_MatC())
    except sync.QuantTraceSyncError as exc:
        raised_c = exc
    check(raised_c is not None, "non-Normal-Map Coat Normal still refuses")
    check("coat" in str(raised_c).lower(), "refuse names Coat Normal")

    section("Slice 2q Coat/Sheen/Emission Strength TEX_IMAGE ABI")
    hdr = _read("native/quanttrace/src/quanttrace.h")
    check("coat_image_path" in hdr, "QT_Mesh has coat_image_path")
    check("sheen_image_path" in hdr, "QT_Mesh has sheen_image_path")
    check("emit_str_image_path" in hdr, "QT_Mesh has emit_str_image_path")
    bridge = _read("native/quanttrace/src/session_bridge.cpp")
    check('bsdf->input("Coat Weight")' in bridge, "bridge connects Coat Weight TEX_IMAGE")
    check('bsdf->input("Sheen Weight")' in bridge, "bridge connects Sheen Weight TEX_IMAGE")
    check('bsdf->input("Emission Strength")' in bridge,
          "bridge connects Emission Strength TEX_IMAGE")
    hello = _read("native/quanttrace/src/hello.c")
    check("0.0.21-slice2t" in hello, "hello version is 0.0.21-slice2t")
    sync_src = _read("scenequant/quanttrace/sync.py")
    check("Coat Weight" in sync_src, "sync accepts Coat Weight")
    check("Sheen Weight" in sync_src, "sync accepts Sheen Weight")
    check("Emission Strength" in sync_src, "sync accepts Emission Strength")
    check("coat_image_path" in sync_src and "sheen_image_path" in sync_src
          and "emit_str_image_path" in sync_src,
          "sync packs coat_/sheen_/emit_str_ TEX_IMAGE fields")
    qtools = _read("tools/_quanttrace_coatsheen_scene.py")
    check("Coat" in qtools and "Sheen" in qtools and "Emission" in qtools,
          "coatsheen scene wires Coat/Sheen/Emission")
    qsmoke = _read("tools/_quanttrace_coatsheen_smoke.py")
    check("pack_scene" in qsmoke and "render_qt_scene_rgba" in qsmoke,
          "coatsheen smoke packs QT_Scene")

    class _BsdfEmitColor:
        type = "BSDF_PRINCIPLED"
        inputs = _Inputs({
            "Base Color": _Sock((0.8, 0.8, 0.8, 1)),
            "Roughness": _Sock(0.5),
            "Metallic": _Sock(0.0),
            "IOR": _Sock(1.45),
            "Alpha": _Sock(1.0),
            "Emission Color": _Sock((1, 1, 1, 1), linked=True, links=["x"]),
        })
    class _TreeE:
        nodes = [_BsdfEmitColor()]
    class _MatE:
        use_nodes = True
        node_tree = _TreeE()
    # Slice 2r accepted Emission Color TEX_IMAGE; a non-TEX_IMAGE link still
    # refuses inside _tex_image_from_sock (not a Coat-Roughness-style gate).
    raised_e = None
    try:
        sync._principled_from_material(_MatE())
    except sync.QuantTraceSyncError as exc:
        raised_e = exc
    check(raised_e is not None, "Emission Color non-TEX_IMAGE link refuses")


    section("Slice 2s Coat/Sheen extra TEX_IMAGE ABI")
    hdr = _read("native/quanttrace/src/quanttrace.h")
    check("coat_rough_image_path" in hdr, "QT_Mesh has coat_rough_image_path")
    check("coat_ior_image_path" in hdr, "QT_Mesh has coat_ior_image_path")
    check("coat_tint_image_path" in hdr, "QT_Mesh has coat_tint_image_path")
    check("sheen_rough_image_path" in hdr, "QT_Mesh has sheen_rough_image_path")
    check("sheen_tint_image_path" in hdr, "QT_Mesh has sheen_tint_image_path")
    bridge = _read("native/quanttrace/src/session_bridge.cpp")
    check('bsdf->input("Coat Roughness")' in bridge, "bridge connects Coat Roughness")
    check('bsdf->input("Coat IOR")' in bridge, "bridge connects Coat IOR")
    check('bsdf->input("Coat Tint")' in bridge, "bridge connects Coat Tint")
    check('bsdf->input("Sheen Roughness")' in bridge, "bridge connects Sheen Roughness")
    check('bsdf->input("Sheen Tint")' in bridge, "bridge connects Sheen Tint")
    check("set_coat_weight(1.0f)" in bridge, "bridge pins coat weight when extras map")
    check("set_sheen_weight(1.0f)" in bridge, "bridge pins sheen weight when extras map")
    hello = _read("native/quanttrace/src/hello.c")
    check("0.0.21-slice2t" in hello, "hello version is 0.0.21-slice2t")
    sync_src = _read("scenequant/quanttrace/sync.py")
    check("Coat Roughness" in sync_src, "sync accepts Coat Roughness")
    check("Coat IOR" in sync_src, "sync accepts Coat IOR")
    check("Coat Tint" in sync_src, "sync accepts Coat Tint")
    check("Sheen Roughness" in sync_src, "sync accepts Sheen Roughness")
    check("Sheen Tint" in sync_src, "sync accepts Sheen Tint")
    check("coat_rough_image_path" in sync_src and "sheen_tint_image_path" in sync_src,
          "sync packs coat_rough_/sheen_tint_ TEX_IMAGE fields")
    xtools = _read("tools/_quanttrace_coatextra_scene.py")
    check("CoatRough" in xtools and "SheenTint" in xtools, "coatextra scene wires extras")
    xsmoke = _read("tools/_quanttrace_coatextra_smoke.py")
    check("pack_scene" in xsmoke and "render_qt_scene_rgba" in xsmoke,
          "coatextra smoke packs QT_Scene")

    section("Slice 2t Coat Normal Map TEX_IMAGE ABI")
    hdr = _read("native/quanttrace/src/quanttrace.h")
    check("coat_normal_image_path" in hdr, "QT_Mesh has coat_normal_image_path")
    check("coat_normal_strength" in hdr, "QT_Mesh has coat_normal_strength")
    bridge = _read("native/quanttrace/src/session_bridge.cpp")
    check('bsdf->input("Coat Normal")' in bridge, "bridge connects Coat Normal")
    check("coat_normal_strength" in bridge, "bridge uses coat_normal_strength")
    hello = _read("native/quanttrace/src/hello.c")
    check("0.0.21-slice2t" in hello, "hello version is 0.0.21-slice2t")
    sync_src = _read("scenequant/quanttrace/sync.py")
    check("Coat Normal" in sync_src, "sync accepts Coat Normal")
    check("coat_normal_image_path" in sync_src, "sync packs coat_normal_ TEX_IMAGE fields")
    check('prefix="coat_normal_"' in sync_src, "sync uses coat_normal_ prefix")
    ctools = _read("tools/_quanttrace_coatnormal_scene.py")
    check("Coat Normal" in ctools and "ShaderNodeNormalMap" in ctools,
          "coatnormal scene wires Normal Map → Coat Normal")
    csmoke = _read("tools/_quanttrace_coatnormal_smoke.py")
    check("pack_scene" in csmoke and "render_qt_scene_rgba" in csmoke,
          "coatnormal smoke packs QT_Scene")

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
