# QuantTrace RenderEngine stub — class contract + refuse path.
# Duck-typed engine hooks; no bpy, no GPU, no F12.
#   python3 tests/test_quanttrace.py

import importlib.util
import os
import sys

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
    check(engine.kernel_ready() is False, "kernel_ready is False (no native .so)")

    section("render refuses — not built")
    fake = FakeEngine()
    raised = None
    try:
        engine.refuse_render(fake, None)
    except engine.QuantTraceNotBuilt as exc:
        raised = exc
    check(raised is not None, "refuse_render raises QuantTraceNotBuilt")
    msg = str(raised).lower()
    check("not built" in msg, "exception mentions not built")
    check("cycles" in msg and "make it fast" in msg,
          "exception points at stock Cycles / Make it Fast")
    check("path-trace" in msg or "does not path-trace" in msg,
          "exception says it does not path-trace")
    check(any("not built" in str(item).lower() for item in fake.errors),
          "error_set got the not-built message")
    check(any("not built" in str(item).lower() for item in fake.reports),
          "report() got the not-built message")
    check(any("not built" in str(item).lower() for item in fake.stats),
          "update_stats got the not-built message")
    check(fake.progress == [1.0], "update_progress(1.0) on refuse")

    inst = cls()
    inst.error_set = fake.error_set
    inst.report = fake.report
    inst.update_stats = fake.update_stats
    inst.update_progress = fake.update_progress
    raised_render = None
    try:
        inst.render(None)
    except engine.QuantTraceNotBuilt as exc:
        raised_render = exc
    check(raised_render is not None, "SQ_QUANTTRACE.render raises QuantTraceNotBuilt")
    check("not built" in str(raised_render).lower(),
          "render() exception is the not-built path")

    section("stub does not pretend to path-trace")
    src = _read("scenequant/quanttrace/engine.py")
    check("begin_result" not in src, "engine.py has no begin_result")
    check("update_result" not in src, "engine.py has no update_result")
    check("end_result" not in src, "engine.py has no end_result")
    check("libquanttrace" not in src and "ctypes" not in src,
          "engine.py does not load a native .so")

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
