# CLAMP_INDIRECT: enable Cycles factory sample_clamp_indirect when left at 0.
#
# Scene-agnostic integrator-state lever. Classifier reads only
# scene.render.engine + scene.cycles.sample_clamp_indirect. Same code
# for interior / exterior / product / vehicle / volume — the write fires
# iff clamp-indirect is disabled (0), never because of a file name.
#
# Cycles 4.5/5.1 intern/cycles/scene/integrator.cpp:
#   SOCKET_FLOAT(sample_clamp_indirect, "Sample Clamp Indirect", 10.0f);
#   SOCKET_FLOAT(sample_clamp_direct,   "Sample Clamp Direct",   0.0f);
#   kintegrator->sample_clamp_indirect =
#       (sample_clamp_indirect == 0.0f) ? FLT_MAX
#                                       : sample_clamp_indirect * 3.0f;
# 0 is a sentinel (no clamp). Non-zero is Cycles' own factory 10, then
# multiplied by 3 in the kernel. Direct clamp stays 0 (never write it).
# APPLY_PERCEPTUAL_PATHS MODE_MIN 5.0 only *lowers* a high clamp; it
# cannot enable a disabled one. This lever is the 0 → 10 enable.
#
# User values already > 0 are left alone. Missing attr = skip.
# Non-Cycles engine = skip.
#
# NOT in default Auto Make it Fast until a measured pair exists.
# clamp_indirect_actions is not called from build_speed_plan.
# No bpy.ops. Importable without Blender (duck-typed scene + cycles).

CLAMP_INDIRECT_VALUE = 10.0
SPEED_KIND = "CLAMP_INDIRECT"
PROP = "sample_clamp_indirect"
DIRECT_PROP = "sample_clamp_direct"


def classify_clamp_indirect(scene):
    """Records when integrator clamp-indirect is disabled (0).

    Empty list if the attr is missing, the engine is not CYCLES, the
    value is already non-zero, or the value is not a number.
    """
    if getattr(getattr(scene, "render", None), "engine", "CYCLES") != "CYCLES":
        return []
    cycles = getattr(scene, "cycles", None)
    if cycles is None or not hasattr(cycles, PROP):
        return []
    current = getattr(cycles, PROP, None)
    if not isinstance(current, (int, float)):
        return []
    if current != 0:
        return []
    return [{
        "class": SPEED_KIND,
        "prop": PROP,
        "from": float(current),
        "to": CLAMP_INDIRECT_VALUE,
    }]


def apply_clamp_indirect(scene, jrnl, records=None, target=None):
    """Write 0 → factory 10 through the journal. Re-prove current == 0.

    Never writes sample_clamp_direct. Returns the applied records
    (empty if the gate failed or set_prop did not stick).
    """
    if records is None:
        records = classify_clamp_indirect(scene)
    if not records:
        return []
    cycles = getattr(scene, "cycles", None)
    if cycles is None or not hasattr(cycles, PROP):
        return []
    current = getattr(cycles, PROP, None)
    if current != 0:
        return []
    value = CLAMP_INDIRECT_VALUE if target is None else float(target)
    if value <= 0:
        return []
    ok = jrnl.set_prop(scene, "cycles.%s" % PROP, value)
    if not ok:
        return []
    return list(records)


def inventory_counts(records):
    n = len(records or [])
    return {
        "CLAMP_INDIRECT": n,
        "CLAMP_DIRECT_WRITES": 0,
    }
