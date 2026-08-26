# Next lever (2026-08-26 6pm ET PlugWalk)

## 6pm DNA inventory — official Classroom + loft on the box

Goal this hour: get official blender.org Classroom + loft onto the box
(user PC still offline) and DNA-inventory today's four Auto-off levers.
No GPU. No Blender render. No zip. Script:
`tools/_inventory_today_levers_dna.py` (blendfile.py, no bpy).

**Counts are real. UNKNOWN ≠ 0. FIRED=0 on all three official files.
Auto stays off. No time / MAE invented.**

### URLs / bytes / hashes (box `/workspace/scenequant/work/bench/`)

| File | Official URL | bytes | sha256 |
|---|---|---|---|
| Classroom | `https://download.blender.org/demo/test/classroom.zip` (official container; `classroom.blend` extracted, zip discarded) | zip 70279690 · blend **32045332** | blend `5c526ea3f280566e80253673c9955640527cd0f247ea41b1742620b5bc39f7a4` |
| loft | `https://download.blender.org/demo/cycles/loft.blend` | **561122088** | `96d31b9c0df55592bde4a82d875e05acece67201d5df9cac40ef9d164a7c1840` |
| BMW27 | already on box (4pm / 5pm) | **3148419** | `98306c8affc0a4513e6998a1c2813a66083264e7e28b5e853975555b55c308e4` |

Listed on `https://www.blender.org/download/demo-files/` (Cycles) and
`https://download.blender.org/demo/test/` / `…/demo/cycles/`. Classroom
has no unpacked `.blend` on the official host (HEAD 404); zip is the
official file. Linked Classroom assets (`assets/lamps/…`, 11 `LI`
blocks) were inside the zip and were not kept (No zip). Scene type-10
lights all resolved in `classroom.blend` (`energy_unread=0`).

### FIRED table (classifier; ducks only attach proven DNA)

| File | CLAMP_INDIRECT | ZERO_ENERGY_LIGHT | ZERO_SHADER_LIGHT | ZERO_WORLD_BG |
|---|---|---|---|---|
| Classroom (official, v279) | **0** (key **PRESENT**, value **3.0** ≠ 0) | **0** (4 lights, all energy **1.0**) | **0** (4 noded; Strength **UNKNOWN**, not proven 0) | **0** (Strength proven **0.0**; already `sampling_method=NONE`; **no** spatial tex) |
| loft (official, v292) | **UNKNOWN** (key missing → hasattr fire=0). Missing ≠ 0. | **0** (4 lights, energy 10 / 10 / 100 / 200) | **0** (`use_nodes=0`) | **0** (Strength **LINKED → UNKNOWN**, not 0; `sampling_method` **UNKNOWN** not NONE; spatial **True** `TEX_ENVIRONMENT`) |
| BMW27 (official, v273) | **UNKNOWN** (key missing → hasattr fire=0). Missing ≠ 0. | **0** (`LA`=0, type10=0) | **0** | **0** (Strength proven **1.0**; sampling key missing → UNKNOWN ≠ NONE) |

FIRED > 0 would still only *gate* a future Auto discussion — **do not**
turn Auto on without a timed pair. No Auto change this hour. Store
Classroom 41% / loft 52% unchanged.

Product rules still hold: Auto off until a measured pair. Journal + revert.
No zip. No time claim. No user GPU. No QuantTrace. No `sample_clamp_direct`.
No mesh `hide_render` for emit-0. No Principled unlink-zero redo.

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

## Classroom DNA (no bpy) — official Seux file

File: `/workspace/scenequant/work/bench/classroom.blend`  
`BLENDER-v279` · 32045332 bytes ·
sha256 `5c526ea3f280566e80253673c9955640527cd0f247ea41b1742620b5bc39f7a4`  
From official `classroom.zip` (70279690 bytes, 2019-06-13). Zip discarded.
Reader: `tools/_inventory_today_levers_dna.py` + `tools/blendfile.py`.
Blender binary not launched.

Scene `_mainScene`, `r.engine=CYCLES`. Scenes `_mainScene`,
`dustParticules`, `volumeLight`. **11 libraries** (linked assets not
kept on disk).

### CLAMP_INDIRECT

- Scene IDP `cycles` group **exists**.
- `sample_clamp_indirect` **PRESENT**, FLOAT **3.0**.
- `sample_clamp_direct` **PRESENT**, FLOAT **5.5** (never write this).
- `sample_clamp_indirect == 0`? **No** (proven 3.0). User value stays.
- **CLAMP_INDIRECT=0**.

### ZERO_ENERGY_LIGHT / ZERO_SHADER_LIGHT

- `LA` blocks = **6**. Scene object type 10 = **4**. energy_unread = **0**.
- Rows (all `energy_src=DNA`, `use_nodes=True`, `hide_render=False`,
  portal key missing → classifier treats missing portal as False):
  - `exterior_fillLight` AREA energy **1.0** shader UNKNOWN_OR_LIVE
  - `blackBoard_light` AREA energy **1.0** shader UNKNOWN_OR_LIVE
  - `coridor_ceilingLight` POINT energy **1.0** shader UNKNOWN_OR_LIVE
  - `sun` SUN energy **1.0** shader UNKNOWN_OR_LIVE
- energy==0 lights = **0** (proven empty, not unread).
- use_nodes lights = **4**. Proven-zero shader lights = **0**.
- Shader Strength on those four is **UNKNOWN**, not 0 (no full node
  eval / readable default that proves 0).
- **ZERO_ENERGY_LIGHT=0**. **ZERO_SHADER_LIGHT=0**.

### ZERO_WORLD_BG

- World `World`, `use_nodes=1`, nodetree present. 2 `WO` blocks.
- Surface: `BACKGROUND` → `World Output.Surface`. Volume unlinked.
- Background Strength **unlinked**, default_value **proven 0.0**.
  Proven-zero? **Yes**.
- Color path: nodes `OUTPUT_WORLD`, `BACKGROUND` only — **no**
  TEX_ENVIRONMENT / TEX_SKY / TEX_IMAGE. Spatial? **False**.
- `sampling_method` **NONE** (IDP_INT). Already the write.
- Classifier needs proven-zero **and** spatial tex **and** not already
  NONE. Spatial false + already NONE → no fire.
- **ZERO_WORLD_BG=0**.

### FIRED

```
CLAMP_INDIRECT=0
ZERO_ENERGY_LIGHT=0
ZERO_SHADER_LIGHT=0
ZERO_WORLD_BG=0
```

Classroom does not pay any of today's four writes. Clamp is already 3.0.
World is already NONE with no env tex. Lights are live energy 1.0; shader
Strength on the four noded lamps is UNKNOWN, not a proven-zero hit.

## loft DNA (no bpy) — official Blender Studio Cycles file

File: `/workspace/scenequant/work/bench/loft.blend`  
`BLENDER-v292` · 561122088 bytes ·
sha256 `96d31b9c0df55592bde4a82d875e05acece67201d5df9cac40ef9d164a7c1840`  
Official `https://download.blender.org/demo/cycles/loft.blend`
(2021-04-30). Reader same. Blender binary not launched.

Scene `Scene`, `r.engine=CYCLES`. 18 libraries.

### CLAMP_INDIRECT

- Scene IDP `cycles` group **exists**.
- Keys: device, denoiser, use_denoising, use_adaptive_sampling,
  use_preview_denoising, preview_samples, samples, feature_set,
  preview_denoiser, progressive — **no** `sample_clamp_indirect`,
  **no** `sample_clamp_direct`.
- `sample_clamp_indirect == 0`? **UNKNOWN** (key missing). Missing is
  not 0. Do not guess a 4.x RNA default. Classifier hasattr-gate →
  **fire=0**.
- **CLAMP_INDIRECT fire=0**. DNA value remains **UNKNOWN**.

### ZERO_ENERGY_LIGHT / ZERO_SHADER_LIGHT

- `LA` blocks = **4**. Scene object type 10 = **4**. energy_unread = **0**.
- Rows:
  - `Area` AREA energy **10.0** use_nodes False portal IDP
  - `Area.002` AREA energy **10.0** use_nodes False portal IDP
  - `Area.001` AREA energy **100.0** use_nodes False portal key missing
  - `Area.003` AREA energy **200.0** use_nodes False portal key missing
- energy==0 lights = **0** (proven empty, not unread).
- use_nodes lights = **0**. Proven-zero shader lights = **0**.
- Shader Strength UNKNOWN does not apply: no noded light tree.
- **ZERO_ENERGY_LIGHT=0**. **ZERO_SHADER_LIGHT=0**.

### ZERO_WORLD_BG

- World `EasyHDR`, `use_nodes=1`, nodetree present. 1 `WO` block.
- Nodes: TEX_COORD, MAPPING, TEX_ENVIRONMENT, BACKGROUND, GAMMA,
  HUE_SAT, MIX_RGB, MATH×3, OUTPUT_WORLD.
- Background Strength **LINKED** → value **UNKNOWN**, proven-zero
  **False**. Linked Strength is not 0.
- Spatial? **True** (`TEX_ENVIRONMENT`).
- Volume unlinked.
- World IDP `cycles` group **missing**. `sampling_method` **UNKNOWN**
  (not NONE). Missing is not NONE.
- Classifier needs proven-zero Strength. Strength not proven 0 → no fire.
- **ZERO_WORLD_BG=0**.

### FIRED

```
CLAMP_INDIRECT=0   # DNA UNKNOWN (key missing), hasattr fire=0
ZERO_ENERGY_LIGHT=0
ZERO_SHADER_LIGHT=0
ZERO_WORLD_BG=0    # Strength UNKNOWN (linked), sampling UNKNOWN
```

loft does not pay any of today's four writes. Clamp socket is absent
(UNKNOWN). Lights are live 10–200 energy, nodeless. World is a live HDR
with linked Strength (UNKNOWN, not 0) so ZERO_WORLD_BG cannot fire even
though spatial tex is present and sampling_method is not proven NONE.

## BMW27 DNA (no bpy) — still on the box

File: `/workspace/scenequant/work/bench/BMW27.blend`  
`BLENDER-v273` · 3148419 bytes ·
sha256 `98306c8affc0a4513e6998a1c2813a66083264e7e28b5e853975555b55c308e4`  
Re-ran 6pm: same as 4pm / 5pm.

Scene `Scene`, `r.engine=CYCLES`. 0 libraries.

- CLAMP_INDIRECT: key **MISSING** → UNKNOWN, not 0. hasattr → fire=0.
- Lights: `LA`=0, type10=0. ZERO_ENERGY_LIGHT=0 ZERO_SHADER_LIGHT=0.
- World `World`, Strength unlinked **proven 1.0**, Color RGB (no env
  tex), `sampling_method` key missing → UNKNOWN ≠ NONE.
  ZERO_WORLD_BG=0.

```
CLAMP_INDIRECT=0
ZERO_ENERGY_LIGHT=0
ZERO_SHADER_LIGHT=0
ZERO_WORLD_BG=0
```

BMW27 does not pay any of today's four writes. The BMW 79% store
footnote was 1225 spp overkill, not these levers.

## Why no 5th this hour

A fifth lever this hour would need (1) a new Cycles leftover that is not
already a shipped classifier, (2) a general DNA write with journal/revert
tests, (3) at least a proven official-file *hole* so Auto-off is not
decorative. (3) is now readable and is a miss on all four classifiers.

1. **All three official files miss all four writes.** Classroom clamp is
   already 3.0. Classroom world is already NONE with no spatial tex.
   loft / BMW27 clamp keys are missing (UNKNOWN, not 0). No energy-0
   lights. No proven-zero shader lights. loft world Strength is linked
   (UNKNOWN). A fifth write cannot be justified as "the four missed
   this hole" — they did not miss a fireable hole; the files do not
   present one.
2. **Classroom shader Strength UNKNOWN is not a fifth lever.** The four
   noded Classroom lamps are UNKNOWN_OR_LIVE. Expanding the one-hop
   Strength proof is still ZERO_SHADER_LIGHT, not a new class. Do not
   invent proven-0 from UNKNOWN.
3. **loft linked Strength + env tex is not a fifth lever.** That is
   exactly ZERO_WORLD_BG's precondition except Strength is not proven 0.
   Do not guess a linked Strength. Do not write NONE on a live HDR.
4. **Remaining INTERNALS leftovers are the wrong class tonight.**
   - Light linking / shadow linking: policy-heavy, quality-risky, explicit
     Manual-later (`INTERNALS` §2.5).
   - Instance-from-duplicate: not a Classroom/loft closer (`INTERNALS` §2.4).
   - Mesh emit-0 `hide_render`: forbidden this hour (mesh lights still
     contribute; that is a different bill than Lamp energy 0).
   - `sample_clamp_direct`: forbidden (Classroom already has 5.5; Cycles
     socket default is 0 = disabled; writing it is a quality hit).
   - QuantTrace / sidecar integrator: research-only. Not an Auto lever.
5. **Leftover P1 RNA knobs are settings dumps, not a new structural
   class.** `adaptive_min_samples`, `world.cycles.max_bounces`,
   `transparent_max_bounces`, `volume_step_rate`, tile size, motion-BVH
   skip. `INTERNALS` §1 already called the RNA stack finished.
6. **emission_sampling NONE on dim mesh lights** (NEXT-GROK-BRIEF P1-I)
   still needs strength×area DNA. Classroom MESH_EMIT_BACKFACE=2 was
   already inventoried as mesh lights, not Lamp energy 0. Do not
   implement from tonight's four-lever miss.

## Next hour

1. Do **not** turn Auto on. All four FIRED=0 on official Classroom,
   loft, and BMW27. No timed pair this hour.
2. Classroom clamp 3.0 and Classroom world NONE are already the writes.
   loft clamp UNKNOWN stays UNKNOWN until a 4.x resave proves the RNA.
3. Classroom's four noded lamps stay UNKNOWN_OR_LIVE until a deeper
   (still ZERO_SHADER_LIGHT) Strength proof exists. Do not invent 0.
4. loft EasyHDR Strength stays UNKNOWN (linked). Do not write NONE.
5. Do **not** invent a fifth write until an official inventory shows a
   hole the four classifiers do not already own, with a Cycles cite.

Inventory command (box, no GPU):

```
python3 /workspace/scenequant-public/tools/_inventory_today_levers_dna.py \
  /workspace/scenequant/work/bench/classroom.blend
python3 /workspace/scenequant-public/tools/_inventory_today_levers_dna.py \
  /workspace/scenequant/work/bench/loft.blend
python3 /workspace/scenequant-public/tools/_inventory_today_levers_dna.py \
  /workspace/scenequant/work/bench/BMW27.blend
```
