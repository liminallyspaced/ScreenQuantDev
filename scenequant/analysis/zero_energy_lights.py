# ZERO_ENERGY_LIGHT: hide_render on local Lights whose RNA energy is 0.
#
# Scene-agnostic object-DNA lever. Classifier reads only object type,
# Light.energy, hide_render, library, portal flag, and animation_data.
# Same code for interior / exterior / product / vehicle — the write fires
# iff a render-visible local light is energy 0, never because of a file
# name or "interior" / chair counts.
#
# Cycles 4.5 intern/cycles/blender/object.cpp sync_object:
#   if (object_is_light(b_ob)) {
#     if (!show_lights) return nullptr;
#   } else if (culling.test(...)) {
#     return nullptr;   // meshes can be camera-culled; lights cannot
#   }
# Lights always become Cycles objects when show_lights. Camera cull never
# drops them.
#
# intern/cycles/blender/light.cpp sync_light:
#   const float3 strength = light_color * energy * exp2f(exposure);
#   light->set_strength(strength);
# No energy-0 early-out at Blender sync.
#
# intern/cycles/scene/light.cpp Light::has_contribution:
#   if (strength == zero_float3()) return false;
# LightManager::test_enabled_lights then sets
#   light->is_enabled = light->has_contribution(scene, object);
# Disabled lights are skipped in the sampling distribution / light tree.
# Path tracing already ignores them *after* they are Cycles objects.
#
# The leftover is membership: hide_render drops the object from
# DEG_OBJECT_ITER_FOR_RENDER_ENGINE (INTERNALS §2.1) so sync_light never
# runs and the object never enters scene->objects. Portal lights
# (Light.cycles.is_portal) are skipped — they do not emit; hiding one
# would drop a world-MIS rectangle. Linked / animated / HERO skipped.
#
# NOT in default Auto Make it Fast until a measured pair exists.
# zero_energy_light_actions is not called from build_speed_plan.
# No bpy.ops. Importable without Blender (duck-typed scene + lights).

SPEED_KIND = "ZERO_ENERGY_LIGHT"
PROP = "hide_render"


def classify_zero_energy_lights(scene):
    """Records for local render-visible Lights with energy 0.

    Empty list if the engine is not CYCLES, or no qualifying lights.
    """
    if getattr(getattr(scene, "render", None), "engine", "CYCLES") != "CYCLES":
        return []
    records = []
    for obj in getattr(scene, "objects", ()) or ():
        rec = _classify_one(obj)
        if rec is not None:
            records.append(rec)
    return records


def apply_zero_energy_lights(scene, jrnl, records=None):
    """hide_render True through the journal. Re-prove energy == 0.

    Never writes Light.energy. Never touches portals. Returns the
    applied records (empty if every gate failed).
    """
    if records is None:
        records = classify_zero_energy_lights(scene)
    if not records:
        return []
    applied = []
    for rec in records:
        obj = _get_object(scene, rec.get("object"))
        if obj is None:
            continue
        if _classify_one(obj) is None:
            continue
        if getattr(obj, PROP, False):
            continue
        ok = jrnl.set_prop(obj, PROP, True)
        if ok:
            applied.append(rec)
    return applied


def inventory_counts(records):
    n = len(records or [])
    return {
        "ZERO_ENERGY_LIGHT": n,
        "ENERGY_WRITES": 0,
    }


# ------------------------------------------------------------------ gates


def _classify_one(obj):
    if getattr(obj, "type", "") != "LIGHT":
        return None
    if getattr(obj, PROP, False):
        return None
    if _protected(obj) or _is_linked(obj):
        return None
    if _has_anim(obj) or _has_anim(getattr(obj, "data", None)):
        return None
    data = getattr(obj, "data", None)
    if data is None or not hasattr(data, "energy"):
        return None
    if _is_portal(data):
        return None
    energy = getattr(data, "energy", None)
    if not isinstance(energy, (int, float)) or energy != 0:
        return None
    name = getattr(obj, "name", None)
    if not name:
        return None
    return {
        "class": SPEED_KIND,
        "object": name,
        "prop": PROP,
        "from": False,
        "to": True,
        "energy": float(energy),
        "light_type": getattr(data, "type", "") or "",
    }


def _is_portal(data):
    cycles = getattr(data, "cycles", None)
    return bool(getattr(cycles, "is_portal", False))


def _protected(obj):
    return getattr(getattr(obj, "scenequant", None), "override", "AUTO") != "AUTO"


def _is_linked(obj):
    if getattr(obj, "library", None) is not None:
        return True
    data = getattr(obj, "data", None)
    return getattr(data, "library", None) is not None


def _has_anim(id_block):
    if id_block is None:
        return False
    ad = getattr(id_block, "animation_data", None)
    if ad is None:
        return False
    if getattr(ad, "action", None) is not None:
        return True
    tracks = getattr(ad, "nla_tracks", None) or ()
    if any(getattr(track, "strips", None) for track in tracks):
        return True
    drivers = getattr(ad, "drivers", None) or ()
    if drivers:
        return True
    return False


def _get_object(scene, name):
    if not name:
        return None
    objects = getattr(scene, "objects", None)
    getter = getattr(objects, "get", None)
    if getter is not None:
        try:
            return getter(name)
        except Exception:
            pass
    for obj in objects or ():
        if getattr(obj, "name", None) == name:
            return obj
    return None
