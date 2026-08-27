# Session Combined EXR smoke for libquanttrace.so (QT_WITH_CYCLES).
#
# Proves Session::start/wait + OIIO write via ctypes.
# Locked defaults remain 256/256/128 (QUANTTRACE-CUBE.md). This probe
# sets QUANTTRACE_CUBE_WIDTH/HEIGHT/SAMPLES to 32/32/4.
# After F12 wire: is_tracer must be 1 when QT_WITH_CYCLES is compiled in.
# RPATH is baked; do not require LD_LIBRARY_PATH.
#
#   python3 tools/_quanttrace_session_smoke.py
#
# Exit 0 only if load + is_tracer==1 + session_probe==1 + render_cube==0
# and the EXR exists, size>0, and starts with OpenEXR magic.

from __future__ import annotations

import ctypes
import os
import sys
import tempfile
import time

EXR_MAGIC = b"v/1\x01"


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
    lib.quanttrace_render_cube.argtypes = [ctypes.c_char_p]
    lib.quanttrace_render_cube.restype = ctypes.c_int
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

    width = os.environ.get("QUANTTRACE_CUBE_WIDTH", "32")
    height = os.environ.get("QUANTTRACE_CUBE_HEIGHT", "32")
    samples = os.environ.get("QUANTTRACE_CUBE_SAMPLES", "4")
    os.environ["QUANTTRACE_CUBE_WIDTH"] = width
    os.environ["QUANTTRACE_CUBE_HEIGHT"] = height
    os.environ["QUANTTRACE_CUBE_SAMPLES"] = samples
    print("smoke env", width, "x", height, samples, "spp")

    forced = os.environ.get("QUANTTRACE_CUBE_EXR", "").strip()
    if forced:
        exr_path = forced
        parent = os.path.dirname(os.path.abspath(exr_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
    else:
        fd, exr_path = tempfile.mkstemp(prefix="qt_session_smoke_", suffix=".exr")
        os.close(fd)
        os.unlink(exr_path)
    print("exr_path", exr_path)
    t0 = time.perf_counter()
    rc = lib.quanttrace_render_cube(exr_path.encode())
    wall = time.perf_counter() - t0
    print("render_cube rc=", rc)
    print("wall_s=", round(wall, 3))
    if rc != 0:
        print("FAIL render_cube expected 0")
        return 1
    if not os.path.isfile(exr_path):
        print("FAIL missing EXR", exr_path)
        return 1
    size = os.path.getsize(exr_path)
    print("exr_bytes=", size)
    if size <= 0:
        print("FAIL EXR size 0")
        return 1
    with open(exr_path, "rb") as f:
        magic = f.read(4)
    print("exr_magic=", magic)
    if magic != EXR_MAGIC:
        print("FAIL not OpenEXR magic", magic)
        return 1
    print("OK (Combined RGB min/max is on native stderr above)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
