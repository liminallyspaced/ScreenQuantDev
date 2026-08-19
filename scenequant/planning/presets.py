# Tuner tier definitions + draft mode values. Data-only module.
#
# Entry shape: (owner_key, prop_name, value, mode[, options])
#   owner_key in {'cycles', 'render', 'scene'} — resolved by apply.settings_apply
#     against a Scene: 'cycles' -> scene.cycles.<prop>, 'render' -> scene.render.<prop>,
#     'scene' -> scene.<prop>.
#   mode 'set'  -> write value as-is.
#   mode 'min'  -> write min(current, value); never raises user values
#                  (samples / bounce caps / clamp strengths).
#   mode 'max'  -> write max(current, value); never lowers user values. This is
#                  the cap-at-the-cheapest-allowed rule: the tier's value is
#                  approached from the EXPENSIVE side and stopped there, so an
#                  artist already cheaper than the cap is never moved past it.
#   options (a dict, REQUIRED on every 'max' entry so the reader never has to
#     guess) may carry:
#     'skip_zero': whether 0 is this property's "automatic/disabled" sentinel
#       rather than a real value. It is per-property, NOT a mode-wide rule.
#     'requires': an RNA path that must read truthy for the write to happen.
# Every write goes through journal.set_prop, which is hasattr-guarded AND
# enum-guarded: entries for version-dependent properties (or enum items a
# version lacks — invalid items raise TypeError, which set_prop catches) are
# simply skipped where absent.

from .. import compat

MODE_SET = "set"
MODE_MIN = "min"
MODE_MAX = "max"

OWNER_KEYS = ("cycles", "render", "scene")


# Zero-visual-risk settings. Persistent-data and GPU-denoiser placement need a
# VRAM headroom check, so they live in settings_apply policy functions instead.
TIER_LOSSLESS = (
    ("render", "use_lock_interface", True, MODE_SET),
)


# Negligible-visual-impact settings.
TIER_PERCEPTUAL = (
    ("cycles", "use_adaptive_sampling", True, MODE_SET),
    # Cap at the cheapest allowed threshold: MODE_MAX raises the factory 0.010
    # to the intended 0.015 (a perceptually-safe speedup) and stops there, so a
    # user already above 0.015 keeps their looser value. A deliberately
    # stricter (lower) threshold IS raised to the cap — that is this tier's
    # stated trade — and the write is journaled. 0.0 means "automatic" for this
    # property, so skip_zero leaves it alone. The entry must follow the
    # use_adaptive_sampling write above, which is what makes its gate hold.
    ("cycles", "adaptive_threshold", 0.015, MODE_MAX,
     {"skip_zero": True, "requires": "cycles.use_adaptive_sampling"}),
    ("cycles", "samples", 1024, MODE_MIN),
    # Firefly clamp cap: never loosens a stricter (lower) user clamp and never
    # introduces clamping over a deliberate 0.0 (= disabled). Factory default
    # is 10.0 on 4.5.5/5.1.2, so stock scenes still get the 10 -> 5 cap.
    ("cycles", "sample_clamp_indirect", 5.0, MODE_MIN),
    # Same cap-at-the-cheapest-allowed rule. MODE_SET moved artists BOTH ways:
    # it dragged a deliberate 3.0 DOWN to 1.0, which renders SLOWER — the exact
    # opposite of this tier's purpose. MODE_MAX only ever raises. 0.0 is a real
    # value here (glossy filtering off), not an automatic sentinel, so
    # skip_zero is False and 0.0 is raised to the cap like any other value.
    ("cycles", "blur_glossy", 1.0, MODE_MAX, {"skip_zero": False}),
    # auto_scrambling_distance is inert unless the pattern is TABULATED_SOBOL
    # (4.5's default AUTOMATIC resolves to blue-noise; 5.1 already defaults to
    # TABULATED_SOBOL, making the pattern write a no-op there). The pair is
    # journaled together and enum-guarded, so it degrades to a safe skip on
    # versions without the pattern. Probe-confirmed on 4.5.5 and 5.1.2; the
    # 'use_auto_scrambling_distance' spelling exists on no supported version.
    ("cycles", "sampling_pattern", "TABULATED_SOBOL", MODE_SET),
    ("cycles", "auto_scrambling_distance", True, MODE_SET),
    ("cycles", "use_light_tree", True, MODE_SET),
    # debug_use_spatial_splits deliberately NOT set: it trades longer BVH build
    # and MORE memory for slightly faster traversal — wrong default for the
    # VRAM-limited hardware this addon targets (measured slower on bench scene).
    ("cycles", "max_bounces", 8, MODE_MIN),
    ("cycles", "diffuse_bounces", 3, MODE_MIN),
    ("cycles", "glossy_bounces", 4, MODE_MIN),
    ("cycles", "transmission_bounces", 6, MODE_MIN),
    ("cycles", "transparent_max_bounces", 8, MODE_MIN),
)


# volume_step_rate keeps its ray-marching semantics only pre-5.0 (5.0+ default
# volume algorithm is unbiased null-scattering; the prop is inert there).
_DRAFT_VERSIONED = () if compat.BLENDER_5 else (
    ("cycles", "volume_step_rate", 2.0, MODE_SET),
)

DRAFT = (
    # Invariant #4: use_simplify True MUST ship with explicit render caps.
    # Factory default for simplify_subdivision_render is 6 (4.5.5/5.1.2,
    # probe-confirmed), but a hand-set 0 would silently flatten all subsurf in
    # final renders the moment Simplify turns on — write the caps we mean,
    # never inherit whatever state Simplify was left in.
    ("render", "use_simplify", True, MODE_SET),
    ("render", "simplify_subdivision", 1, MODE_SET),
    ("render", "simplify_subdivision_render", 2, MODE_SET),
    # Same class: factory render default is 1.0, but a hand-set 0.0 would
    # DELETE all child particles from renders; 0.5 is a deliberate, visible
    # draft reduction instead.
    ("render", "simplify_child_particles", 0.5, MODE_SET),
    ("render", "simplify_child_particles_render", 0.5, MODE_SET),
    ("cycles", "texture_limit_render", "512", MODE_SET),
    ("render", "resolution_percentage", 50, MODE_MIN),
    ("cycles", "use_fast_gi", True, MODE_SET),
    ("cycles", "fast_gi_method", "REPLACE", MODE_SET),
    ("cycles", "ao_bounces_render", 1, MODE_SET),
    ("cycles", "caustics_reflective", False, MODE_SET),
    ("cycles", "caustics_refractive", False, MODE_SET),
    # Draft clamp: MODE_MIN keeps a stricter user clamp and a deliberate 0.0.
    ("cycles", "sample_clamp_indirect", 3.0, MODE_MIN),
    ("cycles", "diffuse_bounces", 2, MODE_MIN),
    ("cycles", "glossy_bounces", 3, MODE_MIN),
) + _DRAFT_VERSIONED
