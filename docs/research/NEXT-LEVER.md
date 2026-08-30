# Next lever (2026-08-30 2pm ET PlugWalk)

## 2pm — Aggressive CAMERA_CULL + distance cull (independent object sets)

Build-order #1 locally: enable Cycles **distance cull** alongside camera cull
under the existing Aggressive `CAMERA_CULL` kind (no new kind name).

**Cycles semantics (`intern/cycles/blender/object_cull.cpp`):** scene flags are
independent, but **both object flags on the same name → AND** (keep nearby
off-frustum objects for reflections). Camera-only and distance-only object
flags give independent cull. OR-on-same-object is wrong and would regress the
Classroom cull slice of the 41% plate.

```
return (camera_culled && distance_culled)           // both object flags → AND
    || (camera_culled && !use_distance_cull_)       // camera-only object
    || (distance_culled && !use_camera_cull_);      // distance-only object
```

**Writes (journaled, speed tag):**
- Scene: `render.use_simplify`, `cycles.use_camera_cull`, and
  `cycles.use_distance_cull` whenever distance RNA exists;
  `cycles.distance_cull_margin` only when missing/None/0 →
  `max(50.0, camera.data.clip_end)` when camera+clip_end finite, else `50.0`.
  Never lower a positive user margin. Existing camera margin + simplify high
  caps unchanged.
- `payload["objects"]` (camera-only set): `object.cycles.use_camera_cull=True`
  only. Never `use_distance_cull` on these names.
- `payload["distance_objects"]` (distance-only set): tiny/scatter with
  `min_camera_distance` ≥ the margin that will be written; same protections;
  **disjoint** from the camera set; `object.cycles.use_distance_cull=True`
  only.
- If distance RNA is missing, camera cull alone still succeeds and
  `distance_objects` is ignored.

**Protections unchanged:** lights / volumes / cameras / heroes / emitters /
shadow-catchers stay out; linked scatter is allowed. Preserve Look and
Balanced still withhold `CAMERA_CULL`.

Authoritative report: `docs/research/PLUGWALK-2026-08-30-14.md` §1.

No store claim change (Classroom **41%** / loft **52%**). No zip. No
`blender_manifest.toml` bump (stays **0.3.5**). Branch
`plugwalk/distance-cull-aggressive`.

---

# Next lever (2026-08-26 7pm ET PlugWalk)

## 7pm — clean demo bill (docs only; no 5th leftover lever)

Nick: cuts for ALL scenes including clean official demos. Stop shipping
leftover-state levers that miss the kitchen. This hour hunted ONE new
general structural lever that fires on Classroom **or** loft. None found
that is not already a shipped Auto-off classifier.

**Honesty:** leftover-zero levers (CLAMP_INDIRECT, ZERO_ENERGY_LIGHT,
ZERO_SHADER_LIGHT, ZERO_WORLD_BG) still FIRED=0 on official Classroom,
loft, and BMW27. Unbuilt L1.10 `PRUNE_NORMALMAP` FIRED=0 (loft has 83
live tangent maps; Strength is 1.0 / 0.14–0.5, not 0). Identity-Hook,
empty volume, light-linking, motion-BVH, and proven-zero Bump/Bevel/SSS/
Emission/Transmission/Volume all miss. Do not invent a decorative 5th
leftover write.

No new classifier. No Auto change. No zip. No time claim. No user 2080.
QuantTrace stays research-only.

Official files (DNA only so far, plus one Classroom CPU classify):

| File | bytes | sha256 | method |
|---|---|---|---|
| Classroom | 32045332 | `5c526ea3f280566e80253673c9955640527cd0f247ea41b1742620b5bc39f7a4` | DNA `tools/_inventory_blend_dna.py` + Blender 5.2.0 CPU `--background --python` classify (no F12) |
| loft | 561122088 | `96d31b9c0df55592bde4a82d875e05acece67201d5df9cac40ef9d164a7c1840` | DNA only (535 MB; no F12) |
| BMW27 | 3148419 | `98306c8affc0a4513e6998a1c2813a66083264e7e28b5e853975555b55c308e4` | DNA only |

### What clean demos pay for (live structure, not leftover zeros)

Classroom (Seux, `BLENDER-v279`, live 5.2 `_mainScene`):

| Bill | Count / proof | Already a lever? |
|---|---|---|
| Sample overkill | 300 spp, adaptive off → knee 128 | **Auto** (most of the 41%) |
| Linked scatter (chairs/desks/lamps) | 11 `LI` (assets not kept on box); 56 instance collections | **Auto CAMERA_CULL** (Cycles flags, not hide_render) |
| Enclosed GI | `max_bounces=8` already; leftover is per-sample PT | settings stack; next cut is GPU path guiding / QuantTrace, not Auto RNA |
| Window mesh lights | `MESH_EMIT_BACKFACE=2` (`dayLight_portal` on hallWindow / windows). Live 5.2 `SHADOW_SKIP_OK=1` | **shipped Auto-off** `MESH_EMIT_SHADOW_SKIP` |
| Live Bump | 16, Height linked, Strength 0.006–0.2 (none 0) | not a prune — the picture |
| Real glass | `KEEP_GLASS=1` frostedGlass | never prune |
| Live Hook deform | 48, force **1.0**, all have an object (Cylinder.* → Cube.*) | not identity; do not disable |
| Live Subsurf | 12 local (`renderLevels` 1–3; thumbtack 3) | **Auto SUBDIV_TRIM** (coverage-gated) |
| Live lamps | sun 1.0 / corridor POINT 60 / blackboard AREA 0.79 / fill AREA 1963 (5.2 physical units) | not energy-0 |
| World | Strength proven 0, `sampling_method=NONE`, no env tex; `world.cycles.max_bounces=1024` | already the ZERO_WORLD / WORLD_MIS write; 1024 is RNA leftover, not a new structural class (world is not sampled) |
| Clamp | `sample_clamp_indirect=3.0` (user value stays) | CLAMP_INDIRECT fire=0 |
| Volumes / Normal Map / Principled / light linking / motion | 0 / 0 / 0 / 0 / False | nothing to write |

loft (Blender Studio, `BLENDER-v292`):

| Bill | Count / proof | Already a lever? |
|---|---|---|
| Paths + dicing + denoise + plant cutouts | R4/R6 recipe | **Auto** (the 52%) |
| False-transparent JPEG Alpha | **PRUNE_ALPHA=7** (Carpet Low Grey + six bed mats; packed JPEG `Baxter marilyn-Dirt 2.jpg`) | **shipped Auto-off** `DEAD_CLOSURE_PRUNE` / L1. Auto-gate (PRUNE_ALPHA+VOLUME≥1 on a non-hero official interior) **is met on loft**, still 0 on Classroom. Unmeasured. Do not re-implement. |
| Unused-slot attr union | UNIQUE_UNUSED_SLOTS=21077 / EXTRA_ATTR_APPLY=4865 / 15 shaders | **shipped Auto-off** `UNUSED_SLOTS` |
| Real plant cutouts | KEEP_REAL_CUTOUT=5 | keep |
| Real glass + glass volume | KEEP_GLASS=8; `Realistic_Glass_01` Volume linked, scatter density 0.05 / absorb 1.0 | keep; PRUNE_VOLUME=0 |
| Live tangent Normal Maps | **83** (Strength 1.0×75, 0.18×3, 0.5×2, 0.34 / 0.2 / 0.14; **2 linked, none proven 0**) | L1.10 `PRUNE_NORMALMAP` **FIRED=0**. MikkT is the PBR bill. Cannot unlink live maps. |
| Live Bump / Bevel / AO | 49 Bump (Strength 0.008–0.5); 3 Bevel (0.02 / 0.05); 1 AO Distance 1.0 | PRUNE_BUMP=0 PRUNE_BEVEL=0; AO skip (feeds Color) |
| Live area lights | 10 / 10 / 100 / 200, nodeless | ZERO_ENERGY=0 ZERO_SHADER=0 |
| Live HDR | EasyHDR, Strength LINKED, `TEX_ENVIRONMENT` | ZERO_WORLD_BG=0 (not proven 0) |
| Principled dumps | 176; SSS unlinked 174×0 + 2 live; Transmission 172×0 + 4 live; Alpha linked 8 (the 7 JPEG + 1 cutout) | PRUNE_SSS/EMISSION/TRANSMISSION=0 (need a *link* to proven 0) |
| Clamp key | missing in 2.92 IDP → UNKNOWN, hasattr fire=0 | not 0 |

BMW27: leftover-zeros 0; unique unused slots 0; 25 live Subsurf (existing TRIM); 1 Normal Map Strength 0.01 (live). The 79% was 1225 spp.

### Already-shipped Auto-off that *do* fire on the kitchen

Do not re-implement. Document only.

| Lever | Classroom | loft | BMW27 | Auto | Blocked on |
|---|---|---|---|---|---|
| PRUNE_ALPHA (JPEG / no-alpha Principled Alpha unlink) | 0 | **7** | 0 | off | timed GPU pair on top of current stack + HDR-FLIP |
| UNUSED_SLOTS extra-attr pop | 0 | **4865** apply of 21077 | 0 | off | separate VRAM/attr pair, not a % claim |
| MESH_EMIT_SHADOW_SKIP | **2** cards; live 5.2 `SHADOW_SKIP_OK=1` | 0 | 0 | off | HDR-FLIP on Classroom **and** loft |
| CAMERA_CULL linked scatter | fires (Auto) | fires | — | **on** | already in the 41% |
| Sample knee | 300→128 | 512→256 pad | 1225→128 | **on** | already the store plates |

PRUNE_MIX / DISPLACE / SSS / EMISSION / TRANSMISSION / BUMP / BEVEL / VOLUME / AOV = **0** on both interiors (DNA). Classroom live 5.2 agrees.

### Leftover-zero four (6pm) — still miss the kitchen

```
Classroom  CLAMP_INDIRECT=0 ZERO_ENERGY_LIGHT=0 ZERO_SHADER_LIGHT=0 ZERO_WORLD_BG=0
loft       CLAMP_INDIRECT=0 ZERO_ENERGY_LIGHT=0 ZERO_SHADER_LIGHT=0 ZERO_WORLD_BG=0
BMW27      CLAMP_INDIRECT=0 ZERO_ENERGY_LIGHT=0 ZERO_SHADER_LIGHT=0 ZERO_WORLD_BG=0
```

Classroom live 5.2: clamp 3.0, four lamps energy ≠ 0, world already NONE, classifiers return `[]`.

### Unbuilt candidates checked this hour (all miss)

1. **L1.10 PRUNE_NORMALMAP** (Cycles `NormalMapNode::attributes` always requests MikkT; Strength 0 still compiles). loft 83 / Classroom 0 / BMW27 1. Strength proven-0 = **0**. Default Strength is 1.0 — do not unlink Strength. Parked until a file with Strength 0 exists.
2. **Identity Hook / dead deform.** Classroom 48 Hooks, force 1.0, object present. loft type-1/19/33 are live Subsurf/Particle/Solidify. Not a no-op.
3. **Empty volume.** Classroom volume sockets 0, `VO` blocks 0. loft volume is live glass. `volumeLight` / `dustParticules` are other scenes, not `_mainScene` leftovers.
4. **Light linking / shadow linking.** 2.79/2.92 DNA has no fields. Live 5.2 Classroom `light_linking` sets = 0. Policy-heavy (`INTERNALS` §2.5). Manual-later.
5. **Motion BVH skip.** Live 5.2 Classroom `use_motion_blur=False`.
6. **emission_sampling NONE on dim mesh lights.** 170 Classroom mats `AUTO`; only the two portal cards emit. Do not NONE a live window lamp.
7. **world.max_bounces 1024** (Classroom live). RNA dump; world Strength 0 + NONE so it is not sampled. Not a new structural class.
8. **Instance-from-duplicate** on loft 1184 unique meshes. `INTERNALS` §2.4: will not close Classroom/loft; VRAM DEDUP is forbidden on the speed plan.
9. **QuantTrace.** Research-only. Never Auto.

### Why no new lever this hour

A new write needed (1) a Cycles leftover the shipped classifiers do not own, (2) general DNA / live classify, (3) FIRED>0 on Classroom or loft. (3) failed for every *new* class. The fires that exist are PRUNE_ALPHA=7, UNUSED_SLOTS extra-attr=4865, MESH_EMIT_BACKFACE=2 — all already coded, Auto off, waiting on a GPU pair Nick has not freed.

Shipping another leftover-state classifier that the official kitchen cannot trip is the thing Nick asked to stop.

### Next

1. Do **not** turn Auto on for PRUNE_ALPHA / UNUSED_SLOTS / MESH_EMIT_SHADOW_SKIP / today's four zeros.
2. First GPU pair when the 2080 is free: loft Make it Fast vs same + journaled PRUNE_ALPHA (7 JPEG unlinks) only. Persistent off. HDR-FLIP. Do not re-claim 52%.
3. Do **not** implement L1.10 until an official (or any) inventory shows Strength proven 0.
4. Interior gap after the knee is enclosed GI + live transparent windows + linked chairs. That is QuantTrace / GPU guiding / already-Auto cull — not a fifth energy-0 hide.

Classroom 41% / loft 52% unchanged.

---

# Next lever (2026-08-26 6pm ET PlugWalk) — kept below


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
