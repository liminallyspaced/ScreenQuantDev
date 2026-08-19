# Shared constants: single source of truth for values that used to drift as
# per-module copies. Modules that historically exported one of these keep a
# re-export (e.g. memory_model.BYTES_PER_TRIANGLE) so existing imports work
# until every consumer migrates here. Pure data — importable without bpy.

# Fraction of PHYSICAL VRAM a render may use, the rest staying for OS/display.
# Applied in exactly one place — memory_model.effective_budget_threshold_mb —
# which the solver, the audit and the render pre-flight all call. Never
# multiply a budget by it directly: every caller doing its own reserve is what
# left artists rendering inside 72% of their card.
BUDGET_HEADROOM = 0.85

# Below this frame-area fraction, render-only subdivision levels cannot be
# seen; each extra level still multiplies triangle count by 4.
SUBDIV_COVERAGE = 0.05

# Calibrated against measured Cycles peaks on bench scenes.
BYTES_PER_TRIANGLE = 120

# Replacement for the killer simplify_subdivision_render = 0 default, which
# silently flattens all subsurf at render time (matches the viewport-cap default).
SAFE_SUBDIV_RENDER = 6

# Caps the 4**extra_levels render-subdivision multiplier.
MAX_EXTRA_SUBDIV_LEVELS = 6

# Ranking order for audit findings and report rendering.
SEVERITY_ORDER = ("critical", "high", "medium", "info")

# Recursion cap for node-group walks (pathological/cyclic nesting guard).
NODE_GROUP_MAX_DEPTH = 8

# Object types that can contribute renderable geometry (material slots exist
# on all of them; consumers still hasattr-guard per-type RNA).
GEOMETRY_TYPES = frozenset(
    {"MESH", "CURVE", "SURFACE", "META", "FONT", "CURVES", "POINTCLOUD", "VOLUME"}
)

# SceneQuantSettings.last_report StringProperty maxlen. Blender default is 1024,
# which truncates Analyze JSON so json.loads fails and Make it Fast wipes the grade.
LAST_REPORT_MAXLEN = 1_048_576

