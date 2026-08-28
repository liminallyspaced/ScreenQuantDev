<!-- Slice 2y: Principled Thin Wall BOOLEAN; version 0.0.26-slice2y -->
# QuantTrace native (`libquanttrace`)

**Cube Combined matches stock Cycles** (256²/128 Δmax 4.77e-7) **and**
`SQ_QUANTTRACE.render` F12 packs a still-life depsgraph (N meshes + N AREA)
and lands Combined. `quanttrace_is_tracer()` is **1** when built with
`-DQT_WITH_CYCLES=ON`. Native `0.0.26-slice2y`.

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

Kitchens / HDR worlds / linked Thin Wall (BOOLEAN) / Object·World Normal space / linked Strength / Object-with-pointer TEX_COORD / packed-only images still refuse with a named `QuantTraceSyncError`. Unlinked Thin Wall BOOLEAN is Slice 2y.

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

- Kitchen F12 / HDR world / Object·World Normal / linked Thin Wall BOOLEAN / linked Strength / packed-only
- ReSTIR / OptiX / Make it Fast / zip / store % claims
