# Shared machinery for the SceneQuant headless suites. Importing this module
# puts the repo root on sys.path, so suites work from any checkout location
# (review P5: no hardcoded machine paths — everything derives from __file__).

import os
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(TESTS_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

FAILURES = []


def check(condition, label):
    status = "ok" if condition else "FAIL"
    print(f"  [{status}] {label}")
    if not condition:
        FAILURES.append(label)
    return bool(condition)


def section(title):
    print(f"\n== {title} ==")


def finish():
    """Print the verdict and exit nonzero on any failure (--python-exit-code)."""
    print(f"\n{'ALL TESTS PASSED' if not FAILURES else f'{len(FAILURES)} FAILURES:'}")
    for failure in FAILURES:
        print(f"  - {failure}")
    if FAILURES:
        raise SystemExit(1)


def clear_default_scene():
    """Remove factory-startup objects (Cube/Light/Camera) so identical-geometry
    fixtures never collide with the default cube in dedup scans."""
    import bpy
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
