<!-- Slice 2y: Principled Thin Wall BOOLEAN; version 0.0.26-slice2y -->
# QuantTrace native (`libquanttrace`)

**Current native:** `0.0.53-slice2az` — Gamma/HueSat → Principled Base Color (after pack caps). Addon still `0.3.3`.

**Cube Combined matches stock Cycles** (256²/128 Δmax 4.77e-7) **and**
`SQ_QUANTTRACE.render` F12 packs a still-life depsgraph (N meshes + N AREA)
and lands Combined. `quanttrace_is_tracer()` is **1** when built with
`-DQT_WITH_CYCLES=ON`. Native `0.0.53-slice2az` (Bevel → Principled.Normal).

Native sidecar for the `SQ_QUANTTRACE` Blender RenderEngine. Design:
`docs/research/SIDECAR-INTEGRATOR.md`. Make it Fast stays on stock Cycles;
this tree never feeds Auto clocks.

## Slices

| Slice | Status | What |
|---|---|---|
| **1 — hello lib** | done | Shared `libquanttrace` exporting `quanttrace_version()` / `quanttrace_is_tracer()`. |
| **2 — cube pixel-match + F12** | **PASS** | 256²/128 stock vs Session / F12 Δmax **4.77e-7**. `is_tracer=1` (QT_WITH_CYCLES). |
| **2b — depsgraph simple sync** | **PASS** | Stock vs depsgraph-fed Session 256²/128 Δmax **5.96e-7**. `QT_SimpleScene` + `sync.py`. Simple scenes only. |
| **2c — multi-mesh + multi-AREA** | **32/4 PASS, 256/128 1-px FAIL** | `QT_Scene` + `pack_scene`. Still-life 32²/4 Δmax **2.68e-6**. 256²/128 Δmax **0.00668** (1 silhouette pixel). Caps 32/16. |
| **2d — random_id + POINT/SUN** | **hard POINT PASS** | Hard POINT 256²/128 Δmax **1.2e-7**. SUN ABI only (strength not claimed then). Native `0.0.5-slice2d`. |
| **2e — soft POINT + SUN** | **PASS** | Soft POINT disk soft=0.25 256²/128 Δmax **1.19e-7**. SUN energy=200 256²/128 Δmax **3.81e-6**. `is_sphere=!use_soft_falloff`. Native `0.0.6-slice2e`. |
| **2f — textured Principled** | **PASS** | TEX_IMAGE Base Color + corner UVs. 8×8 sRGB checker 256²/128 Δmax **1.43e-6**. Native `0.0.7-slice2f`. |
| **2g — SPOT** | **PASS** | Hard SPOT (size=π/4, blend=0.15) 256²/128 Δmax **1.19e-7**; soft disk soft=0.25 256²/128 Δmax **1.19e-7**. Native `0.0.8-slice2g`. |
| **2h — Mapping/TEX_COORD** | **PASS** | Mapping VECTOR 256²/128 Δmax **1.67e-6**. Native `0.0.9-slice2h`. |
| **2i — Roughness/Metallic TEX_IMAGE** | **PASS** | Roughness 256²/128 Δmax **4.77e-7**; Metallic 256²/128 Δmax **5.36e-7**. Native `0.0.10-slice2i`. |
| **2j — Normal Map TEX_IMAGE** | **PASS** | Tangent Normal Map ← TEX_IMAGE. 16×16 Non-Color bump 32²/4 Δmax **3.58e-7**; 256²/128 Δmax **5.96e-7**. Native `0.0.11-slice2j`. |
| **2k — TEX_COORD Generated** | **PASS** | Generated 32²/4 Δmax **2.15e-6**; 256²/128 Δmax **2.56e-6**. Generated+Mapping 256²/128 Δmax **3.93e-6**. Native `0.0.12-slice2k`. |
| **2l — TEX_COORD Object** | **PASS** | Object 32²/4 Δmax **7.99e-6**; 256²/128 Δmax **4.35e-6**. Object+Mapping 256²/128 Δmax **6.56e-6**. Native `0.0.13-slice2l`. |
| **2m — TEX_COORD Camera** | **PASS** | Camera 32²/4 Δmax **1.79e-6**; 256²/128 Δmax **3.46e-6**. Camera+Mapping 256²/128 Δmax **5.96e-6**. Native `0.0.14-slice2m`. |
| **2n — TEX_COORD Window + Reflection** | **PASS** | Window 256²/128 Δmax **4.77e-7**; Reflection 256²/128 Δmax **5.96e-7**. Native `0.0.15-slice2n`. |
| **2o — IOR/Alpha TEX_IMAGE** | **PASS** | IOR 256²/128 Δmax **5.96e-7**; Alpha 256²/128 Δmax **6.80e-4**; Both 256²/128 Δmax **6.33e-4**. Native `0.0.16-slice2o`. |
| **2p — Transmission/Specular TEX_IMAGE** | **PASS** | Transmission 256²/128 Δmax **4.44e-6**; Specular 256²/128 Δmax **4.17e-7**; Both 256²/128 Δmax **7.23e-5**. Native `0.0.17-slice2p`. |
| **2q — Coat/Sheen/Emission Strength TEX_IMAGE** | **PASS** | Coat 256²/128 Δmax **3.58e-7**; Sheen 256²/128 Δmax **3.58e-7**; Emission Strength 256²/128 Δmax **9.54e-7**. Native `0.0.18-slice2q`. |
| **2r — Emission Color TEX_IMAGE** | **PASS** | Color 256²/128 Δmax **9.54e-7**. Native `0.0.19-slice2r`. |
| **2s — Coat/Sheen extras TEX_IMAGE** | **PASS** | CoatRough/IOR/Tint + SheenRough/Tint. Native `0.0.20-slice2s`. |
| **2t — Coat Normal Map TEX_IMAGE** | **PASS** | Coat Normal 256²/128 Δmax **3.58e-7**. Native `0.0.21-slice2t`. |
| **2u — Specular Tint / Thin Film / Subsurface TEX_IMAGE** | **32/4 PASS; SSSWeight 256 1-px FAIL** | SpecTint 256²/128 Δmax **4.77e-7**; FilmThick 256²/128 Δmax **4.77e-7**; SSSWeight 32²/4 Δmax **8.34e-7** PASS, 256²/128 Δmax **0.00164** (1 px). Native `0.0.22-slice2u`. |
| **2v — Subsurface IOR / Anisotropy / Diffuse Roughness TEX_IMAGE** | **32/4 PASS; SSSAniso 256 3-px FAIL** | SSSIOR 256²/128 Δmax **8.78e-4**; DiffuseRough 256²/128 Δmax **4.77e-7**; SSSAniso 32²/4 Δmax **2.74e-5** PASS, 256²/128 Δmax **0.0206** (3 px). Thin Wall BOOLEAN refused. Native `0.0.23-slice2v`. |
| **2w — Anisotropic / Rotation / Tangent TEX_IMAGE** | **PASS** | Aniso 256²/128 Δmax **1.09e-7**; AnisoRot 256²/128 Δmax **9.35e-6**; Tangent 256²/128 Δmax **5.09e-11**. Native `0.0.24-slice2w`. |
| **2x — Principled Bump TEX_IMAGE Height** | **PASS** | Bump 32²/4 Δmax **2.38e-7**; 256²/128 Δmax **4.77e-7**. Native `0.0.25-slice2x`. |
| **2y — Principled Thin Wall BOOLEAN** | **PASS** | Unlinked Thin Wall 0/1 + unlinked Transmission Weight. ThinWall 32²/4 Δmax **3.18e-12**; 256²/128 Δmax **2.32e-8**. True vs False 32²/4 Δmax **6.83e-5** (below 1e-3; glass vs black world). Linked Thin Wall still refuses. Native `0.0.26-slice2y`. |
| **2z — Normal Map Object/World space** | **PASS** | Object/World Normal space. Object 256²/128 Δmax **5.96e-7**. Native `0.0.27-slice2z`. |
| **2aa — HDR Environment Texture world** | **PASS** | Equirect HDR 32²/4 Δmax **6.13e-4**; 256²/128 Δmax **2.01e-4**. Native `0.0.28-slice2aa`. |
| **2ab — TEX_COORD Object-with-pointer** | **PASS** | Pointer 32²/4 Δmax **1.08e-5**; 256²/128 Δmax **4.41e-6**. Native `0.0.29-slice2ab`. |
| **2ac — Env Vector / Mapping** | **PASS** | Generated 32²/4 Δmax **6.13e-4**; Mapping rot_z=0.7 32²/4 Δmax **6.75e-4**; 256²/128 Δmax **2.04e-4**. 2aa unlinked regression PASS. Native `0.0.30-slice2ac`. |
| **2ad — BLENDER_OBJECT/BLENDER_WORLD Normal** | **PASS** | BLENDER_OBJECT 32²/4 Δmax **5.59e-9**; 256²/128 Δmax **7.45e-9**. BLENDER_WORLD 256²/128 Δmax **7.45e-9**. Object 2z 32²/4 Δmax **3.58e-7**. Native `0.0.31-slice2ad`. |
| **2ae — Env Object-with-pointer** | **PASS** | Pointer 32²/4 Δmax **6.74e-4**; 256²/128 Δmax **2.12e-4**. empty-ref 32²/4 Δmax **6.13e-4**. Native `0.0.32-slice2ae`. |
| **2af — packed-only images** | **PASS** | base_packed 32²/4 Δmax **1.01e-6**; 256²/128 Δmax **1.43e-6**. hdr_packed 32²/4 Δmax **6.13e-4**; 256²/128 Δmax **2.01e-4**. disk 32²/4 Δmax **1.01e-6**. Native `0.0.33-slice2af`. |
| **2ag — linked Mapping L/R/S** | **PASS** | combxyz 32²/4 Δmax **2.26e-6**; 256²/128 Δmax **1.67e-6**. combxyz_value 32²/4 Δmax **2.26e-6**. unlinked 2h 32²/4 Δmax **2.26e-6**. Native `0.0.34-slice2ag`. |
| **2ah — linked world Strength** | **PASS** | Value 0.7 32²/4 Δmax **4.25e-4**; 256²/128 Δmax **1.20e-4**. unlinked 2aa 32²/4 Δmax **6.13e-4**. 2ac Mapping 32²/4 Δmax **6.75e-4**. Native `0.0.35-slice2ah`. |
| **2ai — Math → world Strength** | **PASS** | math_mul 0.5×1.4 32²/4 Δmax **4.25e-4**; 256²/128 Δmax **1.20e-4**. math_add 32²/4 Δmax **4.25e-4**. value 2ah 32²/4 Δmax **4.25e-4**. unlinked 2aa 32²/4 Δmax **6.13e-4**. Native `0.0.36-slice2ai`. |
| **2aj — Mix → world Strength** | **PASS** | mix_float Fac 0.5 A 0.4 B 1.0 32²/4 Δmax **4.25e-4**; 256²/128 Δmax **1.20e-4**. mix_unlinked / mix_rgb / math_mul 2ai / value 2ah 32²/4 Δmax **4.25e-4**. unlinked 2aa 32²/4 Δmax **6.13e-4**. Native `0.0.37-slice2aj`. |
| **2ak — Map Range/Clamp → world Strength** | **PASS** | map_range Value 0.25 From 0..1 To 0.4..1.6 32²/4 Δmax **4.25e-4**; 256²/128 Δmax **1.20e-4**. clamp 32²/4 Δmax **4.25e-4**. mix_float / math_mul / value 32²/4 Δmax **4.25e-4**. unlinked 2aa Strength 1.0 32²/4 Δmax **6.13e-4**. Native `0.0.38-slice2ak`. |
| **2al — world Background Color RGB/Mix** | **PASS** | rgb (1.0, 0.25, 0.1) 32²/4 Δmax **5.96e-7**; 256²/128 Δmax **5.96e-7**. mix_rgb / unlinked 32²/4 Δmax **5.96e-7**. hdr 2aa 32²/4 Δmax **6.13e-4**. map_range 2ak 32²/4 Δmax **4.25e-4**. Native `0.0.39-slice2al`. |
| **2am — Sky/Nishita → world Color** | **32/4 PASS; 256 3-px FAIL** | nishita MULTIPLE_SCATTERING default RNA 32²/4 Δmax **1.91e-6**; 256²/128 Δmax **0.00172** (3 sun-disc px, MAE 6.28e-8) not claimed PASS. nishita_elev 0.6 rad 32²/4 Δmax **1.91e-6**. rgb 2al 32²/4 Δmax **5.96e-7**. hdr 2aa 32²/4 Δmax **6.13e-4**. Native `0.0.40-slice2am`. |
| **2an — TEX_IMAGE → world Color** | **PASS** | Generated FLAT 32²/4 Δmax **9.73e-4**; 256²/128 Δmax **3.01e-4**. Mapping rot_z=0.15 32²/4 Δmax **0.00115** (1 px) not claimed PASS. Unlinked / rgb / hdr / nishita 32²/4 PASS. Native `0.0.41-slice2an`. |
| **2ap — Bright/Contrast → world Color** | **PASS** | rgb_bc 32²/4 Δmax **5.96e-7**; 256²/128 Δmax **5.96e-7**. rgb_gamma_hsv_bc loft 32²/4 Δmax **5.96e-7**; 256²/128 Δmax **5.96e-7**. hdr_bc Bright=0.08 Contrast=0.05 32²/4 Δmax **9.08e-4**; 256²/128 Δmax **1.98e-4**. rgb_gamma/rgb/hdr/nishita/teximage 32²/4 PASS. Native `0.0.43-slice2ap`. |
| **2aq — Mix → world Color** | **PASS** | rgb_mix 32²/4 Δmax **5.96e-7**; 256²/128 Δmax **5.96e-7**. rgb_hsv_mix 32²/4 Δmax **7.15e-7**; 256²/128 Δmax **4.77e-7**. rgb_gamma_hsv_mix 32²/4 Δmax **7.15e-7**; 256²/128 Δmax **4.77e-7**. hdr_mix fac=0.25 32²/4 Δmax **4.88e-4**; 256²/128 Δmax **1.58e-4**. rgb_bc/rgb/hdr/nishita/teximage 32²/4 PASS. Native `0.0.44-slice2aq`. |
| **2ar — linked Sky Vector** | **PASS** | sky_map PREETHAM+Mapping rot_z=0.7 32²/4 Δmax **5.96e-7**; 256²/128 Δmax **4.77e-7**. sky_gen 32²/4 Δmax **9.54e-7**. preetham/nishita/rgb_mix/rgb/hdr/teximage 32²/4 PASS. Native `0.0.45-slice2ar`. |
| **2as — RGB Curves → world Color** | **PASS** | rgb_curves 32²/4 Δmax **5.96e-7**; 256²/128 Δmax **5.96e-7**. Native `0.0.46-slice2as`. |
| **2at — 3-deep Math → world Strength** | **PASS** | math_nest3 (0.5×1.4)/1+0=0.7 32²/4 Δmax **2.16e-4**; 256²/128 Δmax **1.21e-4**. math_mul 2ai 32²/4 Δmax **4.25e-4**. rgb_curves/rgb_mix/rgb/hdr/nishita/teximage 32²/4 PASS. Native `0.0.47-slice2at`. |
| **2au — TEX_ENVIRONMENT×0 → world Strength** | **env_mul0 PASS; add20 HDR-MIS FAIL** | env_mul0 32²/4 Δmax **3.58e-7**. env_mul0_add20 loft ops=20 32²/4 Δmax **6.17e-3** (16 px) FAIL / 256²/128 Δmax **2.34e-2** (70 px) FAIL — same as unlinked Strength 20. math_nest3/math_mul/hdr/rgb/rgb_mix/rgb_curves/nishita/teximage 32²/4 PASS. Native `0.0.48-slice2au`. |
| **2az — Bevel → Principled.Normal** | **PASS** | bevel 32²/4 Δmax **4.77e-6**; 256²/128 Δmax **2.26e-6**. loft-nest 32²/4 Δmax **1.06e-5**. Loft Bevel cleared; PACK_FAIL Roughness←ColorRamp. Native `0.0.53-slice2az`. |
| **2ax — Gamma/HueSat → Principled Base Color** | **PASS** | hsv 32²/4 Δmax **1.61e-6**; 256²/128 Δmax **8.94e-7**. gamma_hsv 32²/4 Δmax **8.94e-7**. tex 2f 32²/4 Δmax **1.01e-6**. Stock hsv vs tex Δmax **0.635**. Loft PACK_FAIL Mix on Base Color (`Cube` / `Metal_Sheet_2x2_uhwnbcqew`). Native `0.0.51-slice2ax`. |
| **2aw — mesh/light pack caps** | **PASS (pack)** | `QT_MAX_MESHES` **2048** / `QT_MAX_LIGHTS` **128** (was 32/16; heap pointers, validation only). Synthetic 64-cube pack wall **0.029s**; Session 32²/4 **0.072s** no Δmax. point/hdr 32²/4 regressions PASS. Loft count OK; still refuses Base Color non-TEX_IMAGE. Native `0.0.51-slice2ax`. |
| **2av — Mapping POINT → env Vector** | **PASS** | POINT loc=(0.15,0,0) rot_z=0.7 32²/4 Δmax **5.66e-4**; 256²/128 Δmax **8.00e-5**. Stock POINT vs VECTOR Δmax **0.098**. ctypes POINT=0 fix. Loft `_world_info` PACKS; `pack_scene` 1200 meshes refuse. Native `0.0.49-slice2av`. |
| **2ao — Gamma/HueSat → world Color** | **PASS** | rgb_gamma 32²/4 Δmax **4.77e-7**; 256²/128 Δmax **5.96e-7**. rgb_gamma_hsv loft 32²/4 Δmax **7.15e-7**; 256²/128 Δmax **4.77e-7**. rgb_hsv 32²/4 Δmax **5.96e-7**. hdr_gamma 32²/4 Δmax **9.73e-4**; 256²/128 Δmax **1.91e-4**. rgb/hdr/nishita/teximage 32²/4 PASS. Native `0.0.42-slice2ao`. |

Kitchens / linked Thin Wall (BOOLEAN) / TEX_IMAGE → world Strength still refuse with a named `QuantTraceSyncError`. Map Range FLOAT LINEAR / Clamp → world Strength is Slice 2ak. Mix FLOAT / MixRGB constant → world Strength is Slice 2aj. Math → world Strength is Slice 2ai. Linked world Strength (Value node) is Slice 2ah. Linked Mapping L/R/S (Combine XYZ / Value) is Slice 2ag. Packed-only images are Slice 2af. Unlinked Thin Wall BOOLEAN is Slice 2y. World Color RGB/Mix is Slice 2al. Sky/Nishita (unlinked Vector) is Slice 2am. TEX_IMAGE→Color is Slice 2an. Gamma/HueSat on world Color is Slice 2ao. Bright/Contrast on world Color is Slice 2ap. Mix after Color chain is Slice 2aq. Linked Sky Vector (PREETHAM/HOSEK) is Slice 2ar. RGB Curves → Color is Slice 2as. 3-deep Math → Strength is Slice 2at. TEX_ENVIRONMENT×0 MULTIPLY → Strength is Slice 2au. Noise / 4-deep Math / non-zero tex Math / Mapping TEXTURE/NORMAL still refuse. Mapping POINT is Slice 2av. Loft world packs; mesh count cap raised (2aw 2048/128). Base Color Gamma/HueSat is Slice 2ax; Mix→Base Color still refuses. Other loft shader refuses may remain.

## Build (Linux) — hello stub (default)

```bash
cd native/quanttrace
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
# ABI: is_tracer=0, session_probe=0, render_cube=-1
```

## Build (Linux) — Session + F12 (`QT_WITH_CYCLES=ON`)

Needs a local `native/cycles-src` tree already built (gitignored; see `SLICE2.md`).

```bash
cmake -S native/quanttrace -B native/quanttrace/build \
  -DCMAKE_BUILD_TYPE=Release -DQT_WITH_CYCLES=ON
cmake --build native/quanttrace/build -j 8
env -u LD_LIBRARY_PATH python3 tools/_quanttrace_load_probe.py
# ABI: is_tracer=1, session_probe=1, version 0.0.26-slice2y
QUANTTRACE_CUBE_WIDTH=32 QUANTTRACE_CUBE_HEIGHT=32 QUANTTRACE_CUBE_SAMPLES=4 \
  env -u LD_LIBRARY_PATH python3 tools/_quanttrace_session_smoke.py
blender --background --python tools/_quanttrace_f12_smoke.py -- \
  --res 32 --samples 4 --out /tmp/qt_f12.exr
```

RPATH is baked; ctypes does not need `LD_LIBRARY_PATH`.

## Cycles standalone (gitignored tree)

See `SLICE2.md`. Working CPU binary after `make update` + cmake:

`native/cycles-src/build/bin/cycles --device CPU`

## ABI

```c
const char *quanttrace_version(void);   /* "0.0.12-slice2k" */
int quanttrace_is_tracer(void);         /* 1 when QT_WITH_CYCLES */
int quanttrace_render_scene_rgba(...);  /* depsgraph-fed QT_SimpleScene (1+1) */
int quanttrace_render_qt_scene_rgba(...); /* N mesh + N AREA QT_Scene */
int quanttrace_session_probe(void);     /* 0 stub / 1 if QT_WITH_CYCLES */
int quanttrace_render_cube(const char *exr_path);
int quanttrace_render_cube_rgba(float *out, int cap, int *w, int *h);
/* env QUANTTRACE_CUBE_WIDTH/HEIGHT/SAMPLES default 256/256/128 */
```

## Out of scope until shader / light-type expand

- Kitchen F12 / linked Thin Wall BOOLEAN / linked Strength / env Object-with-pointer / packed-only
- ReSTIR / OptiX / Make it Fast / zip / store % claims
