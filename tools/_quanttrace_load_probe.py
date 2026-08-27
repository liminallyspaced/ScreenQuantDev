# ctypes.CDLL probe for native/quanttrace/build/libquanttrace.so
#
# Proves the QT_WITH_CYCLES addon .so loads (version / is_tracer / session_probe).
# Does NOT call quanttrace_render_cube (that is session smoke / F12).
# RPATH is baked; do not require LD_LIBRARY_PATH.
#
#   python3 tools/_quanttrace_load_probe.py
#
# Exit 0 only if load succeeds, is_tracer==1, session_probe==1.

from __future__ import annotations

import ctypes
import os
import sys

def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(here)
    so = os.environ.get(
        "QUANTTRACE_LIB",
        os.path.join(root, "native", "quanttrace", "build", "libquanttrace.so"),
    )
    print("LD_LIBRARY_PATH=", repr(os.environ.get("LD_LIBRARY_PATH")))
    print("loading", so)
    if not os.path.isfile(so):
        print("missing", so)
        return 2
    lib = ctypes.CDLL(so)
    lib.quanttrace_version.restype = ctypes.c_char_p
    lib.quanttrace_is_tracer.restype = ctypes.c_int
    lib.quanttrace_session_probe.restype = ctypes.c_int
    ver = lib.quanttrace_version()
    version = ver.decode() if ver else None
    is_tracer = lib.quanttrace_is_tracer()
    session_probe = lib.quanttrace_session_probe()
    print("version=", version)
    print("is_tracer=", is_tracer)
    print("session_probe=", session_probe)
    if is_tracer != 1:
        print("FAIL is_tracer must be 1 for QT_WITH_CYCLES F12 wire")
        return 1
    if session_probe != 1:
        print("FAIL session_probe must be 1 for QT_WITH_CYCLES .so")
        return 1
    print("OK")
    return 0

if __name__ == "__main__":
    sys.exit(main())
