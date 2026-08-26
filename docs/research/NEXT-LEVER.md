# Next lever (2026-08-26 4pm ET PlugWalk)

This note is the stop for a fifth Auto-off lever this hour. It records what
already shipped, the only official `.blend` DNA on the box, and why a new
write would be decorative.

Product rules still hold: Auto off until a measured pair. Journal + revert.
No zip. No time claim. Classroom 41% / loft 52% unchanged. No user GPU.
No QuantTrace. No `sample_clamp_direct`. No mesh `hide_render` for emit-0.
No Principled unlink-zero redo.

## Today's four levers (already on main, Auto off)

Shipped 2026-08-26 on `liminallyspaced/ScreenQuantDev` `0.3.3` unreleased.
None are called from `build_speed_plan`. Planner hooks exist as
manual-later (`clamp_indirect_actions`, `zero_energy_light_actions`,
`zero_shader_light_actions`, `zero_world_bg_actions`).

| Lever | Write | Classifier | Cycles leftover |
|---|---|---|---|
| **CLAMP_INDIRECT** | `sample_clamp_indirect` 0 → factory 10 | Integrator DNA only. CYCLES. hasattr-gated. User values > 0 stay. Never writes `sample_clamp_direct`. | 4.5/5.1 `intern/cycles/scene/integrator.cpp`: socket default 10.0f; kernel maps 0 → `FLT_MAX` else `value * 3.0f`. `APPLY_PERCEPTUAL_PATHS` MODE_MIN 5.0 only *lowers* a high clamp. |
| **ZERO_ENERGY_LIGHT** | `hide_render` on local Lights with RNA `energy == 0` | Object DNA. Skip portal / linked / animated / HERO. Never writes `Light.energy`. | 4.5 `object.cpp` `sync_object`: lights skip camera cull. `light.cpp` `sync_light`: `strength = color * energy * exp2(exposure)` — no energy-0 early-out. `Light::has_contribution` then false *after* the object exists. `hide_render` drops `DEG_OBJECT_ITER_FOR_RENDER_ENGINE`. |
| **ZERO_SHADER_LIGHT** | `hide_render` on noded Lights whose shader `emission_estimate` is proven 0 while RNA energy is not | Object + Light Output Surface. Strength ~0 / unlinked black / unconnected Surface. GROUP / Math / texture / Light Path unproven. Complementary to ZERO_ENERGY_LIGHT. Never unlinks. Never writes energy. | 4.5 `shader.cpp` `sync_lights`: tree only when `use_nodes`. `output_estimate_emission` then `Light::has_contribution` false on estimate 0. Same membership leftover as energy-0. |
| **ZERO_WORLD_BG** | `world.cycles.sampling_method` NONE | Noded World Surface proven-zero **and** a spatial tex still on Color. Volume unlinked. No portals. Complementary to WORLD_MIS_NONE (solid / nodeless). Never unlinks. | 4.5/5.1 `light.cpp` `test_enabled_lights`: `disable_mis = !(has_portal || shader->has_surface_spatial_varying)` — does **not** consult `emission_estimate`. Strength 0 + env tex still builds the importance map (`device_update_background` / `shade_background_pixels`). NONE makes `sample_as_light` false. |

General DNA. Never a file name. Tests: `tests/test_clamp_indirect.py`,
`test_zero_energy_lights.py`, `test_zero_shader_lights.py`,
`test_zero_world_bg.py`.

## BMW27 DNA (no bpy) — only official .blend on the box

File: `/workspace/scenequant/work/bench/BMW27.blend`  
`BLENDER-v273` · 3148419 bytes ·
sha256 `98306c8affc0a4513e6998a1c2813a66083264e7e28b5e853975555b55c308e4`  
Reader: `tools/_inventory_today_levers_dna.py` + `tools/blendfile.py`.
Blender binary not launched. Classroom / loft **not on this box** — those
counts are not invented.

Scene `Scene`, `r.engine=CYCLES`. 0 libraries.

### CLAMP_INDIRECT

- Scene IDP `cycles` group **exists**.
- Keys: device, bounce caps, samples / branched-path samples, caustics,
  film, debug BVH — **no** `sample_clamp_indirect`, **no**
  `sample_clamp_direct`.
- `sample_clamp_indirect == 0`? **UNKNOWN** (key missing). Missing is not 0.
  2.73 Cycles predates the socket. Classifier hasattr-gate → **fire=0**.

### ZERO_ENERGY_LIGHT / ZERO_SHADER_LIGHT

- `LA` blocks = **0**. Scene object type 10 (LAMP/LIGHT) = **0**.
- energy==0 lights = **0** (proven empty, not unread).
- use_nodes lights = **0**. Proven-zero shader lights = **0**.
- Shader Strength UNKNOWN does not apply: there is no light tree to eval.
- **ZERO_ENERGY_LIGHT=0**. **ZERO_SHADER_LIGHT=0**.

### ZERO_WORLD_BG

- World `WOWorld`, `use_nodes=1`, nodetree present.
- Surface: `RGB` → `Background.Color` → `World Output.Surface`.
- Volume unlinked.
- Background Strength **unlinked**, default_value **proven 1.0**
  (`bNodeSocketValueFloat` layout `<if` → subtype 0, value 1.0).
  Proven-zero? **No**.
- Color path is RGB `(~0.369, ~0.438, 0.5)` — **no** TEX_ENVIRONMENT /
  TEX_SKY / TEX_IMAGE. Spatial? **False** (WORLD_MIS_NONE territory if
  the 4.x RNA existed).
- World IDP `cycles` group exists and is **empty**. `sampling_method`
  **UNKNOWN** (key missing, not NONE).
- **ZERO_WORLD_BG=0**.

### FIRED (classifier, ducks only attach proven DNA)

```
CLAMP_INDIRECT=0
ZERO_ENERGY_LIGHT=0
ZERO_SHADER_LIGHT=0
ZERO_WORLD_BG=0
```

BMW27 does not pay any of today's four writes. The BMW 79% store footnote
was 1225 spp overkill, not these levers.

## Why no 5th this hour

A fifth lever this hour would need (1) a new Cycles leftover that is not
already a shipped classifier, (2) a general DNA write with journal/revert
tests, (3) at least a proven official-file *hole* so Auto-off is not
decorative. None of those three are available on this box this hour.

1. **Only official file on the box is a miss for all four.** BMW27 has
   zero lights, a live Strength-1.0 RGB world, and no clamp socket. A
   fifth write cannot be justified from this file.
2. **Classroom / loft are not on the box.** Do not invent those counts.
   The interior leftover after the sample knee is still Shade Shadow /
   transparent retrace (`INTERNALS-LEVERS` §0, §2.3). That hole was
   already attacked by PRUNE_ALPHA / VOLUME / MIX / SSS / EMISSION /
   TRANSMISSION / BUMP / BEVEL. Re-doing Principled unlink-zero is
   forbidden this hour.
3. **Remaining INTERNALS leftovers are the wrong class tonight.**
   - Light linking / shadow linking: policy-heavy, quality-risky, explicit
     Manual-later (`INTERNALS` §2.5).
   - Instance-from-duplicate: not a Classroom/loft closer (`INTERNALS` §2.4).
   - Mesh emit-0 `hide_render`: forbidden this hour (mesh lights still
     contribute; that is a different bill than Lamp energy 0).
   - `sample_clamp_direct`: forbidden (Cycles socket default is 0 =
     disabled; writing it is a quality hit).
   - QuantTrace / sidecar integrator: research-only
     (`docs/research/SIDECAR-INTEGRATOR.md` on the work tree). Not an
     Auto lever. Forbidden this hour.
4. **Leftover P1 RNA knobs are settings dumps, not a new structural
   class.** `adaptive_min_samples`, `world.cycles.max_bounces`,
   `transparent_max_bounces`, `volume_step_rate`, tile size, motion-BVH
   skip. `INTERNALS` §1 already called the RNA stack finished. Shipping
   another integrator float without an official DNA hit repeats
   CLAMP_INDIRECT's shape without new evidence.
5. **emission_sampling NONE on dim mesh lights** (NEXT-GROK-BRIEF P1-I)
   is the closest structural cousin. It is not hide_render-on-meshes
   (forbidden), and it needs strength×area DNA plus a loft/Classroom
   inventory we do not have. Do not implement from BMW27 (0 mesh-emit
   cards in the earlier PORTAL_MESH walk).

## Next hour (when Classroom / loft are readable)

1. Run `tools/_inventory_today_levers_dna.py` on official Classroom and
   loft. Print the same UNKNOWN-vs-0 honesty. Do not apply.
2. If either file has `sample_clamp_indirect == 0` (key present), that
   is the CLAMP_INDIRECT official hit — still Auto off until a pair on
   top of the current stack.
3. If either file has energy-0 or proven-zero shader lights, same: count,
   then a timed pair. Portals stay.
4. If a noded world is Strength-0 + env tex with `sampling_method !=
   NONE`, that is ZERO_WORLD_BG's official hit.
5. Do **not** invent a fifth write until one of those inventories shows
   a hole the four classifiers do not already own, with a Cycles cite.

Inventory command (box, no GPU):

```
python3 /workspace/scenequant-public/tools/_inventory_today_levers_dna.py   /workspace/scenequant/work/bench/BMW27.blend
```
