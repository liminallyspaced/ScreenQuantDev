# Render-settings writes: auto-tune tiers, draft mode, and VRAM-headroom
# policies. Every scene write goes through journal.set_prop (hasattr-guarded),
# so version-missing properties are skipped safely and everything is revertible.
# Background-safe: only the passed scene is touched, never bpy.context.

from ..analysis import memory_model
from ..planning import presets

TIER_TAG = "tune"
DRAFT_TAG = "draft"

# Enable persistent data only when estimated memory + 20% fits in VRAM.
PERSISTENT_DATA_HEADROOM = 1.2
# GPU denoising costs extra VRAM; require 30% headroom before enabling.
GPU_DENOISE_HEADROOM = 1.3

_MISSING = object()

_TIERS = {
    "lossless": presets.TIER_LOSSLESS,
    "perceptual": presets.TIER_PERCEPTUAL,
}


def _full_path(owner_key, prop_name):
    if owner_key == "scene":
        return prop_name
    if owner_key in ("cycles", "render"):
        return owner_key + "." + prop_name
    raise ValueError("unknown preset owner_key: %r" % (owner_key,))


def _read_current(scene, rna_path):
    """Same walk journal.set_prop resolves; _MISSING if any hop is absent."""
    owner = scene
    parts = rna_path.split(".")
    for part in parts[:-1]:
        owner = getattr(owner, part, None)
        if owner is None:
            return _MISSING
    return getattr(owner, parts[-1], _MISSING)


def _describe(rna_path, old, new):
    if old is _MISSING:
        return "%s = %s" % (rna_path, new)
    return "%s: %s -> %s" % (rna_path, old, new)


def _apply_entries(scene, jrnl, entries, tag):
    """Write preset entries through the journal; describe only real changes."""
    changes = []
    for entry in entries:
        owner_key, prop_name, value, mode = entry[:4]
        options = entry[4] if len(entry) > 4 else {}
        rna_path = _full_path(owner_key, prop_name)
        if not _gate_holds(scene, options.get("requires")):
            continue
        current = _read_current(scene, rna_path)
        if mode == presets.MODE_MIN:
            # Never raise user values: cap only when current exceeds preset.
            if current is _MISSING or not isinstance(current, (int, float)):
                continue
            if current <= value:
                continue
        elif mode == presets.MODE_MAX:
            # Never lower user values. Whether 0 is a sentinel (automatic /
            # disabled) is a per-PROPERTY fact, not a property of the mode, so
            # every MODE_MAX entry must say which it is.
            if "skip_zero" not in options:
                raise ValueError(
                    "MODE_MAX preset %r must state skip_zero" % (rna_path,))
            if current is _MISSING or not isinstance(current, (int, float)):
                continue
            if current >= value:
                continue
            if options["skip_zero"] and current == 0:
                continue
        elif mode != presets.MODE_SET:
            raise ValueError("unknown preset mode: %r" % (mode,))
        if jrnl.set_prop(scene, rna_path, value, tag):
            changes.append(_describe(rna_path, current, value))
    return changes


def _gate_holds(scene, requires):
    """An entry's 'requires' RNA path must read truthy. A missing property is
    NOT a pass: the gated write only makes sense where the gate exists."""
    if requires is None:
        return True
    gate = _read_current(scene, requires)
    return gate is not _MISSING and bool(gate)


def apply_tier(scene, jrnl, tier_name):
    """Apply one auto-tune tier; returns descriptions of changes actually made."""
    tier = _TIERS.get(str(tier_name).lower())
    if tier is None:
        raise ValueError("unknown SceneQuant tier: %r" % (tier_name,))
    return _apply_entries(scene, jrnl, tier, TIER_TAG)


def apply_draft(scene, jrnl):
    """Apply draft-mode settings (tag 'draft'); returns change descriptions."""
    changes = _apply_entries(scene, jrnl, presets.DRAFT, DRAFT_TAG)
    # UI indicator only — deliberately not journaled, so revert_all does not
    # leave a stale "draft active" badge.
    scene.scenequant.draft_active = True
    return changes


def revert_draft(scene, jrnl):
    """Revert every 'draft'-tagged journal entry; returns reverted count."""
    count = jrnl.revert_tag(DRAFT_TAG)
    scene.scenequant.draft_active = False
    return count


def _usable_mb(vram_mb):
    """vram_mb is PHYSICAL VRAM; both policies below must weigh their headroom
    against the share a render may actually use, or they hand out memory the
    OS and other apps are already holding."""
    return memory_model.effective_budget_threshold_mb(vram_mb)


def maybe_enable_persistent_data(scene, jrnl, mem, vram_mb, tag=TIER_TAG):
    """Persistent data speeds up animations but costs memory: enable only with
    known VRAM and 20% headroom; force-disable when over budget. Returns the
    resulting policy state (True = persistent data on). tag defaults to 'tune'
    so Auto-Tune is unchanged; Make it Fast passes 'speed'."""
    usable = _usable_mb(vram_mb)
    if not usable:
        return False
    if mem.total_mb * PERSISTENT_DATA_HEADROOM < usable:
        jrnl.set_prop(scene, "render.use_persistent_data", True, tag)
        return True
    jrnl.set_prop(scene, "render.use_persistent_data", False, tag)
    return False


def gpu_denoise_policy(scene, jrnl, mem, vram_mb, tag=TIER_TAG):
    """OIDN GPU denoising is ~10-15x faster but needs extra VRAM: enable with
    comfortable headroom, disable when tight. No-op when VRAM is unknown.
    denoising_use_gpu is 4.2+ — set_prop guards absence."""
    usable = _usable_mb(vram_mb)
    if not usable:
        return None
    is_comfortable = mem.total_mb * GPU_DENOISE_HEADROOM < usable
    jrnl.set_prop(scene, "cycles.denoising_use_gpu", is_comfortable, tag)
    return None
