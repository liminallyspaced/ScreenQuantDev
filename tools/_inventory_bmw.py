# Headless BMW27 inventory: DEAD_CLOSURE_PRUNE + UNUSED_SLOTS.
# Analyze only. No render. No GPU device set.
#
#   blender -b --factory-startup BMW27.blend --python-exit-code 1 \
#     --python /workspace/scenequant/work/tools/_inventory_bmw.py
#
# sys.path prefers the public tree, then this work tree.

import os
import sys

import bpy

_HERE = os.path.dirname(os.path.abspath(__file__))
_WORK_ROOT = os.path.dirname(_HERE)
_PUBLIC = "/workspace/scenequant-public"
for _root in (_PUBLIC, _WORK_ROOT):
    if os.path.isdir(os.path.join(_root, "scenequant")):
        if _root not in sys.path:
            sys.path.insert(0, _root)
        break

from scenequant.analysis.dead_closures import (
    classify_dead_closures,
    inventory_counts as dead_counts,
    print_inventory as print_dead,
)
from scenequant.analysis.unused_slots import (
    classify_unused_slots,
    inventory_counts as slot_counts,
    print_inventory as print_slots,
)


def main():
    scene = bpy.context.scene
    print("BMW27 inventory scene=%r file=%r" % (
        getattr(scene, "name", ""), bpy.data.filepath))
    print("blender=%s" % bpy.app.version_string)

    dead = classify_dead_closures(scene)
    print_dead(dead)
    counts = dead_counts(dead)
    print("DEAD_COUNTS %s" % counts)

    slots = classify_unused_slots(scene)
    print_slots(slots)
    print("SLOT_COUNTS %s" % slot_counts(slots))


if __name__ == "__main__":
    main()
