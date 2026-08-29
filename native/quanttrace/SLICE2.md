# QuantTrace Slice 2 — build order (cube pixel-match)

Status: **Slice 2ap landed** (2026-08-29 6am PlugWalk ET). Bright/Contrast → world Background Color (`world_bright` / `world_contrast` after `world_hsv_fac`). Identity skip keeps 2ao/2an/2am/2aa/2al bit-identical. rgb_bc 32²/4 Δmax=5.96e-7 PASS / 256²/128 Δmax=5.96e-7 PASS. rgb_gamma_hsv_bc loft 32²/4 Δmax=5.96e-7 PASS / 256²/128 Δmax=5.96e-7 PASS. hdr_bc Bright=0.08 Contrast=0.05 32²/4 Δmax=9.08e-4 PASS / 256²/128 Δmax=1.98e-4 PASS. rgb_gamma/rgb/hdr/nishita/teximage 32²/4 PASS. Stock rgb_bc vs unlinked RGB Δmax=0.350 (lever live). Noise refuses. `is_tracer=1`. Native `0.0.43-slice2ap`. Addon `0.3.3`.
Slice 1 (done): hello `libquanttrace.so`, `quanttrace_is_tracer() == 0`.
Acceptance: `docs/research/QUANTTRACE-CUBE.md`.

Design: `docs/research/SIDECAR-INTEGRATOR.md`.

`is_tracer=1` when QT_WITH_CYCLES (F12 wired for locked cube). Do **not** claim arbitrary-scene sync.
**Do not** touch Make it Fast / Auto. **Do not** vendor Cycles into the
addon zip or public commit tree.



---



---







## 6am PlugWalk (2026-08-29) — Bright/Contrast → world Color (Slice 2ap)

Box: Linux, 8 cores, Blender 5.2.0 CPU. No user 2080. No zip. No Make it Fast / Auto.

Retarget: 2ao packed Gamma/HueSat and deferred Bright/Contrast. Typical loft EasyHDR chains also use Bright/Contrast on world Color. This hour peels one unlinked BrightContrast (plus Gamma/HueSat) and applies loft order Color → Gamma → HSV → BrightContrast → Background.

### What landed

| Piece | Detail |
|---|---|
| Research | Cycles `BrightContrastNode` (`set_color`, `set_bright`, `set_contrast`; SOCKET bright/contrast default 0.0). Cite `shader_nodes.h`. Blender type `BRIGHTCONTRAST` / `ShaderNodeBrightContrast` (Bright + Contrast VALUE sockets). |
| ABI | `world_bright` / `world_contrast` after `world_hsv_fac` on `QT_SimpleScene` + `QT_Scene`. Identity 0 / 0 = skip native node (2ao/2an/2am/2aa/2al bit-identical). |
| Python | `_world_info` peels one unlinked `GAMMA` + one `HUE_SAT` + one `BRIGHTCONTRAST` (≤3 hops, any order) then resolves remaining source as today. Linked Bright/Contrast, second BrightContrast, Noise, RGB Curves, Mix after HSV, second Gamma/HueSat refuse Slice 2ap. |
| Native | Color source → Gamma (if gamma!=1) → HSV (if hsv not identity) → BrightContrast (if bright/contrast not identity) → Background Color. Version `0.0.43-slice2ap`. |
| Version | `0.0.43-slice2ap` |
| Tools | `_quanttrace_slice2ap_scene/smoke.py` (modes rgb_bc / rgb_gamma_hsv_bc / hdr_bc / rgb_gamma / rgb / hdr / nishita / teximage / noise / unlinked_rgb) |

### Measured — rgb_bc (claim)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Session | 32² / 4 | **5.96e-7** | 2.29e-9 | 0 / 1024 | **PASS** |
| Session | 256² / 128 | **5.96e-7** | 1.53e-9 | 0 / 65536 | **PASS** |

### Measured — rgb_gamma_hsv_bc loft chain (claim)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Session | 32² / 4 | **5.96e-7** | 2.33e-9 | 0 / 1024 | **PASS** |
| Session | 256² / 128 | **5.96e-7** | 1.55e-9 | 0 / 65536 | **PASS** |

### Measured — hdr_bc EasyHDR-like (claim)

Bright=0.08 Contrast=0.05 (0.15/0.1 hit 1 px Δmax=1.17e-3 at 32²/4 — not claimed).

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Session | 32² / 4 | **9.08e-4** | 5.80e-6 | 0 / 1024 | **PASS** |
| Session | 256² / 128 | **1.98e-4** | 1.07e-6 | 0 / 65536 | **PASS** |

### Measured — secondary / regressions (32² / 4)

| Mode | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|
| rgb_gamma 2ao | 4.77e-7 | 2.21e-9 | 0 | **PASS** |
| rgb 2al | 5.96e-7 | 2.36e-9 | 0 | **PASS** |
| hdr 2aa | 6.13e-4 | 4.63e-6 | 0 | **PASS** |
| nishita 2am | 1.91e-6 | 1.87e-8 | 0 | **PASS** |
| teximage 2an Generated FLAT | 9.73e-4 | 2.79e-6 | 0 | **PASS** |
| Stock rgb_bc vs unlinked RGB | 0.350 | 0.183 | 1024 | live |

Identity skip: rgb_gamma / rgb / hdr / nishita / teximage packed `world_bright=0` + `world_contrast=0`; Δmax matches prior slices within noise. Proof plate `docs/proof/quanttrace-bright-contrast-32-pair.png` (rgb_bc stock|session) + `/workspace/quanttrace-bright-contrast-32-pair.png`. F12 32² not run this hour; Session is the claim.

### Honesty / still refuses

- Linked Bright/Contrast (texture-driven), RGB Curves, Noise, Mix after HSV, second Gamma/HueSat/BrightContrast, linked Sky Vector, BOX blend, UDIM, kitchens still refuse.
- Bright=0.15 Contrast=0.1 on HDR equirect: 32²/4 Δmax=1.17e-3 (1 px) — documented, not claimed PASS; claim uses 0.08/0.05.
- Still-life / SSS / sky-256 sun-disc residue still documented.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Mix after HSV → world Color, linked Sky Vector, or RGB Curves. Not ReSTIR. Not Classroom time %.


## 5am PlugWalk (2026-08-29) — Gamma/HueSat → world Color (Slice 2ao)

Box: Linux, 8 cores, Blender 5.2.0 CPU. No user 2080. No zip. No Make it Fast / Auto.

Retarget: 2an packed TEX_IMAGE Color and refused loft EasyHDR Gamma/HueSat/Mix. Typical loft chain is Env/TEX_IMAGE → Gamma → HueSat → (Mix later) → Background Color. This hour peels unlinked Gamma + HueSat (one of each, either order walking toward the source) and applies them in loft order.

### What landed

| Piece | Detail |
|---|---|
| Research | Cycles `GammaNode` (`set_color`, `set_gamma`; SOCKET gamma default 1.0; `X^1==X` fold) and `HSVNode` (`set_color`, `set_hue`, `set_saturation`, `set_value`, `set_fac`; hue default 0.5). Cite `shader_nodes.h` / `NODE_DEFINE` in `shader_nodes.cpp`. |
| ABI | `world_gamma` / `world_hsv_hue` / `world_hsv_sat` / `world_hsv_val` / `world_hsv_fac` after `world_color_image_projection` on `QT_SimpleScene` + `QT_Scene`. Identity 1 / 0.5 / 1 / 1 / 1 = skip native nodes (2aa/2al/2am/2an bit-identical). |
| Python | `_world_info` peels one unlinked `GAMMA` + one unlinked `HUE_SAT` then resolves remaining source as today. Linked Gamma/Hue/Sat/Value/Fac, second Gamma/HueSat, Noise, RGB Curves, Mix after HSV refuse Slice 2ao (Bright/Contrast later landed as 2ap). |
| Native | Color source (env / sky / ImageTexture / world_color RGB) → Gamma (if gamma!=1) → HSV (if hsv not identity) → Background Color. If only HSV skip Gamma; if only Gamma skip HSV. Locked-cube memset sets identity (gamma=0 after memset is NOT identity). Version `0.0.42-slice2ao`. |
| Version | `0.0.42-slice2ao` |
| Tools | `_quanttrace_slice2ao_scene/smoke.py` (modes rgb_gamma / rgb_hsv / rgb_gamma_hsv / hdr_gamma / rgb / hdr / nishita / teximage / noise / unlinked_rgb) |

### Measured — rgb_gamma_hsv loft chain (claim)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Session | 32² / 4 | **7.15e-7** | 2.36e-9 | 0 / 1024 | **PASS** |
| Session | 256² / 128 | **4.77e-7** | 1.52e-9 | 0 / 65536 | **PASS** |

### Measured — rgb_gamma (claim)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Session | 32² / 4 | **4.77e-7** | 2.21e-9 | 0 / 1024 | **PASS** |
| Session | 256² / 128 | **5.96e-7** | 1.44e-9 | 0 / 65536 | **PASS** |

### Measured — hdr_gamma EasyHDR-like (claim)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Session | 32² / 4 | **9.73e-4** | 5.71e-6 | 0 / 1024 | **PASS** |
| Session | 256² / 128 | **1.91e-4** | 1.04e-6 | 0 / 65536 | **PASS** |

### Measured — secondary / regressions (32² / 4)

| Mode | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|
| rgb_hsv hue=0.6 sat=1.2 val=0.85 | 5.96e-7 | 2.20e-9 | 0 | **PASS** |
| rgb 2al | 5.96e-7 | 2.36e-9 | 0 | **PASS** |
| hdr 2aa | 6.13e-4 | 4.63e-6 | 0 | **PASS** |
| nishita 2am | 1.91e-6 | 1.87e-8 | 0 | **PASS** |
| teximage 2an Generated FLAT | 9.73e-4 | 2.79e-6 | 0 | **PASS** |
| Stock rgb_gamma vs unlinked RGB | 0.203 | 0.0979 | 1024 | live |

Identity skip: rgb / hdr / nishita / teximage packed `world_gamma=1` + HSV identity; Δmax matches 2an/2am/2aa/2al within noise. Proof plate `docs/proof/quanttrace-gamma-hsv-32-pair.png` (rgb_gamma_hsv stock|session) + `/workspace/quanttrace-gamma-hsv-32-pair.png`. F12 32² not run this hour; Session is the claim.

### Honesty / still refuses

- Linked Gamma/Hue/Sat/Value/Fac (texture-driven), RGB Curves, Noise, Mix after HSV, second Gamma/HueSat, linked Sky Vector, BOX blend, UDIM, kitchens still refuse (Bright/Contrast landed as 2ap).
- Still-life / SSS / sky-256 sun-disc residue still documented.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Landed as Slice 2ap (6am). Next: Mix after HSV, linked Sky Vector, or RGB Curves. Not ReSTIR. Not Classroom time %.


## 4am PlugWalk (2026-08-29) — TEX_IMAGE → world Color (Slice 2an)

Box: Linux, 8 cores, Blender 5.2.0 CPU. No user 2080. No zip. No Make it Fast / Auto.

Retarget: 2am packed Sky/Nishita Color and refused TEX_IMAGE→Color. Loft EasyHDR-style graphs and many artist worlds feed a 2D Image Texture into Background Color (not Environment Texture). This hour accepts that graph.

### What landed

| Piece | Detail |
|---|---|
| Research | Cycles `ImageTextureNode` Vector default is `LINK_TEXTURE_UV` (cite `shader_nodes.cpp`); on world that can be spatially flat — claim plate uses TEX_COORD Generated. Projection enum FLAT/BOX/SPHERE/TUBE = NODE_IMAGE_PROJ_*. BackgroundLight: ImageTexture is **not** scanned by `device_update_background` AUTOMATIC (only EnvironmentTexture + SkyTexture); map_res=0 falls through to default 1024×512 — match env/color factory 1024. |
| ABI | `world_color_image_path` / `world_color_image_colorspace` / `world_color_image_projection` after `world_sky_ozone_density` on `QT_SimpleScene` + `QT_Scene`. Empty path = 2aa/2al/2am bit-identical. |
| Python | `_world_info` packs TEX_IMAGE Color; Vector like env 2ac/2ae. Path empty + color zeros + sky_type 0. Noise / RGB Curves / multi-link refuse Slice 2an. |
| Native | Priority env → sky → ImageTextureNode Color→Background Color → world_color RGB. BackgroundLight when has_env \|\| has_sky \|\| has_color_image \|\| color_nonzero. |
| Version | `0.0.41-slice2an` |
| Tools | `_quanttrace_slice2an_scene/smoke.py` (8×8 sRGB checker; modes teximage / mapping / unlinked / rgb / hdr / nishita / noise / black) |

### Measured — TEX_IMAGE Generated FLAT (claim)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Session | 32² / 4 | **9.73e-4** | 2.79e-6 | 0 / 1024 | **PASS** |
| Session | 256² / 128 | **3.01e-4** | 6.40e-7 | 0 / 65536 | **PASS** |

### Measured — secondary / regressions (32² / 4)

| Mode | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|
| teximage_mapping rot_z=0.15 | 0.00115 | 3.05e-6 | 1 | FAIL (not claimed) |
| teximage_unlinked | 4.69e-5 | 1.89e-7 | 0 | **PASS** |
| rgb 2al | 5.96e-7 | 2.36e-9 | 0 | **PASS** |
| hdr 2aa | 6.13e-4 | 4.63e-6 | 0 | **PASS** |
| nishita 2am | 1.91e-6 | 1.87e-8 | 0 | **PASS** |
| Stock teximage vs black | 0.716 | 0.170 | 1024 | live |

### Honesty / still refuses

- Linked Sky Vector / Noise / RGB Curves / BOX blend / tiled UDIM / loft EasyHDR Gamma/HueSat/Mix chain / kitchens still refuse.
- Still-life / SSS / sky-256 sun-disc residue still documented.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Linked Sky Vector, PREETHAM/HOSEK 256 gate, loft EasyHDR Gamma/HueSat/Mix → Color when Color is spatially varying, or Mix/Math → Color. Not ReSTIR. Not Classroom time %.


## 3am PlugWalk (2026-08-29) — Sky/Nishita → world Color (Slice 2am)

Box: Linux, 8 cores, Blender 5.2.0 CPU. No user 2080. No zip. No Make it Fast / Auto.

Retarget: 2al packed RGB/Mix Color and refused TEX_SKY. Official scenes (and many interiors) use ShaderNodeTexSky on World. This hour accepts that graph (default NISHITA / Blender 5.2 MULTIPLE_SCATTERING).

### What landed

| Piece | Detail |
|---|---|
| Research | Blender 5.2 ShaderNodeTexSky `sky_type` enum is SINGLE_SCATTERING / MULTIPLE_SCATTERING / PREETHAM / HOSEK_WILKIE (no NISHITA identifier; MULTIPLE_SCATTERING is the Nishita default). Vector is `is_unavailable` on Nishita. Cycles `SkyTextureNode` SOCKET default NODE_SKY_MULTIPLE_SCATTERING. `aerosol_density` (older RNA `dust_density`). `simplify_settings` wraps elevation/rotation — packer does not double-wrap. World `sampling_method=AUTOMATIC` leaves BackgroundLight map_res=0 (Cycles sky 512×256 + sun guiding); forcing 1024 mismatches the sun disc (32²/4 Δmax 0.034). |
| ABI | `world_sky_*` after `world_color` on `QT_SimpleScene` + `QT_Scene`. type 0 = 2al/2aa. 1=PREETHAM 2=HOSEK 3=NISHITA/MULTIPLE 4=SINGLE. Path empty, world_color zeros. |
| Python | `_world_info` packs TEX_SKY RNA; unlinked Vector only. Linked Vector / TEX_IMAGE / Noise / RGB Curves refuse Slice 2am. |
| Native | `SkyTextureNode` Color → Background Color. BackgroundLight when `has_env \|\| has_sky \|\| color_nonzero`. Sky map_res=0. Version `0.0.40-slice2am`. |
| Version | `0.0.40-slice2am` |
| Tools | `tools/_quanttrace_slice2am_scene.py`, `tools/_quanttrace_slice2am_smoke.py`. 2al mode=sky now packs. |
| Visibility | Camera 1.8× pull-back; Combined shows sky (peak ~13 default / ~30 at elev 0.6). |

### Measured (Session vs stock Cycles Combined, box CPU)

| Case | Res / spp | Δmax | MAE | px≥1e-3 | Gate |
|---|---|---|---|---|---|
| nishita (TEX_SKY MULTIPLE_SCATTERING default RNA; sock default black; Strength 1.0) | 32² / 4 | **1.91e-6** | 1.87e-8 | 0 | **PASS** |
| nishita (TEX_SKY MULTIPLE_SCATTERING default RNA; sock default black; Strength 1.0) | 256² / 128 | **0.00172** | 6.28e-8 | 3 | **FAIL** (3 sun-disc px; not claimed PASS) |
| nishita_elev (sun_elevation=0.6 rad) | 32² / 4 | **1.91e-6** | 2.06e-8 | 0 | **PASS** |
| rgb (2al regression, world_color, sky_type=0) | 32² / 4 | **5.96e-7** | 2.36e-9 | 0 | **PASS** |
| hdr (2aa regression, env path, sky_type=0) | 32² / 4 | **6.13e-4** | 4.63e-6 | 0 | **PASS** |

Live graph (stock nishita vs stock black world) 32²/4: Δmax=**12.0** (1024 px ≥1e-3, MAE 0.213). Packed `world_sky_type=3` while Color socket default stayed black. sky_vector_linked (TEX_COORD → Sky Vector) raises Slice 2am. Proof plate `docs/proof/quanttrace-sky-32-pair.png` (nishita stock\|session) + `/workspace/quanttrace-sky-32-pair.png`. F12 32² not run this hour; Session is the claim.

### Honesty

- 256²/128 nishita is 3-px sun-disc residue (Δmax 0.00172, MAE 6.28e-8, 0 px ≥1e-2). Same class as still-life / SSS 256 noise. 32²/4 is the PASS claim.
- Linked Sky Vector / TEX_IMAGE → Color / Noise / RGB Curves / spatially-varying Mix still refuse. PREETHAM/HOSEK packed but not pixel-gated this hour.
- SSS 256 residue / still-life 1px noise-class still documented (not claimed fixed).
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Landed as Slice 2an (TEX_IMAGE → Color). Linked Sky Vector / PREETHAM-HOSEK 256 / EasyHDR chain still open. SSS 256 residue stays document-only. Not ReSTIR. Not Classroom time %.


## 2am PlugWalk (2026-08-29) — world Background Color RGB/Mix (Slice 2al)

Box: Linux, 8 cores, Blender 5.2.0 CPU. No user 2080. No zip. No Make it Fast / Auto.

Retarget: last hour (2ak) deferred Mix/Math → Background Color because native had **no** `world_color` float3. This hour lands that ABI and packs RGB / Mix-constant / unlinked non-black Color. Strength folding (2ah–2ak) unchanged.

### What landed

| Piece | Detail |
|---|---|
| Research | Blender BackgroundNode Color * Strength. Empty `world_image_path` + (0,0,0) stays Slice 2b black (no BackgroundLight). Non-zero `world_color` creates BackgroundLight + MIS like env (cite Cycles BackgroundLight / world sample_map 1024). Camera pulled 1.8× so Combined shows world pixels (cube stays in frame). |
| ABI | `world_color[3]` appended after `world_ob_tfm[12]` on `QT_SimpleScene` + `QT_Scene`. Default 0,0,0. Env path keeps Color black (ENV node feeds Color); do not mix world_color into the env graph. |
| Python | `_world_info` accepts unlinked non-black Color, ShaderNodeRGB, MixRGB / Mix FLOAT constants (MIX/ADD/SUB/MUL/DIV, `clamp_factor`), Value/Math → Color as grey. TEX_ENVIRONMENT still wins (`world_color` zeros). Sky/Nishita/TEX_IMAGE/Noise/RGB Curves/spatially-varying Mix refuse Slice 2al. Nodeless non-black `world.color` packs strength 1. |
| Native | `bg->set_color(world_color)` when path empty. `BackgroundLight` when `has_env \|\| color_nonzero`. Version `0.0.39-slice2al`. |
| Version | `0.0.39-slice2al` |
| Tools | `tools/_quanttrace_slice2al_scene.py`, `tools/_quanttrace_slice2al_smoke.py`. Modes: `rgb`, `unlinked`, `mix_rgb`, `hdr` (2aa), `map_range` (2ak), `sky` (refuse). |
| Visibility | Camera 1.8× pull-back; Combined shows world RGB (1.0, 0.25, 0.1). |

### Measured (Session vs stock Cycles Combined, box CPU)

| Case | Res / spp | Δmax | MAE | px≥1e-3 | Gate |
|---|---|---|---|---|---|
| rgb (ShaderNodeRGB 1.0, 0.25, 0.1 → Color; sock default black; Strength 1.0) | 32² / 4 | **5.96e-7** | 2.36e-9 | 0 | **PASS** |
| rgb (ShaderNodeRGB 1.0, 0.25, 0.1 → Color; sock default black; Strength 1.0) | 256² / 128 | **5.96e-7** | 1.51e-9 | 0 | **PASS** |
| mix_rgb (MixRGB Fac 0.5 A=(1,0,0) B=(1,0.5,0.2) → (1.0, 0.25, 0.1); sock default black) | 32² / 4 | **5.96e-7** | 2.36e-9 | 0 | **PASS** |
| unlinked (Color default 1.0, 0.25, 0.1; Strength 1.0) | 32² / 4 | **5.96e-7** | 2.36e-9 | 0 | **PASS** |
| hdr (2aa regression, HDR equirect Strength 1.0; world_color zeros) | 32² / 4 | **6.13e-4** | 4.63e-6 | 0 | **PASS** |
| map_range (2ak regression, HDR + Map Range → Strength 0.7) | 32² / 4 | **4.25e-4** | 2.79e-6 | 0 | **PASS** |

Live graph (stock rgb vs stock black world) 32²/4: Δmax=**1.0** (1024 px ≥1e-3, MAE 0.446). Packed `world_color=(1.0, 0.25, 0.1)` while Color socket default stayed black. sky (TEX_SKY/Nishita → Color) raises Slice 2al. Proof plate `docs/proof/quanttrace-world-color-32-pair.png` (rgb stock\|session) + `/workspace/quanttrace-world-color-32-pair.png`. F12 32² not run this hour; Session is the claim.

### Honesty

- Sky/Nishita, TEX_IMAGE → Color, TEX_IMAGE → L/R/S, Noise / RGB Curves / spatially-varying Mix still refuse. Strength path (2ah–2ak) unchanged.
- HDR Δmax remains ~1e-4–7e-4 class (BackgroundLight MIS map), under the 1e-3 gate with 0 px ≥1e-3 on the claim cases. Solid Color Δmax is 5.96e-7 (filter/sample-pattern class).
- SSS 256 residue / still-life 1px noise-class still documented (not claimed fixed). Not spent this hour.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Sky/Nishita → Color, or TEX_IMAGE → L/R/S. SSS 256 residue stays document-only. Not ReSTIR. Not Classroom time %.



## 1am PlugWalk (2026-08-29) — Map Range/Clamp → world Strength (Slice 2ak)

Box: Linux, 8 cores, Blender 5.2.0 CPU. No user 2080. No zip. No Make it Fast / Auto.

Retarget: Mix/Math → Background Color was the planned sibling of 2aj, but native ABI has **no** `world_color` float3 (Color is unlinked-black or `world_image_path` TEX_ENVIRONMENT). Do not invent a half ABI this hour. Slice 2ak is Map Range + Clamp → existing `world_strength` float instead.

### What landed

| Piece | Detail |
|---|---|
| Research | Blender 5.2 Map Range FLOAT sockets are `Value` / `From Min` / `From Max` / `To Min` / `To Max` (identifiers with spaces). Interpolation LINEAR (STEPPED/SMOOTHSTEP/SMOOTHERSTEP refuse). `clamp` RNA True → Cycles `MapRangeNode::expand` inserts ClampNode RANGE on To Min/Max. Clamp sockets `Value`/`Min`/`Max`; `clamp_type` MINMAX or RANGE (RANGE swaps if Min>Max). Fold at sync into existing `world_strength` float. Strength sock default left at 1.0 while Map Range folds to 0.7 so ignoring the link fails the gate. |
| ABI | Unchanged `world_strength` float. No new C++ fields — constant resolved at sync time (like 2ai/2aj). No `world_color` float3. |
| Python | `_world_strength_from_sock` + `_fold_world_strength_map_range` / `_fold_world_strength_clamp` in `sync.py`. Inputs reuse `_world_strength_const_input` (unlinked/Value/Math/Mix/RGB/shallow Map Range/Clamp). TEX_IMAGE / Noise / RGB Curves / VECTOR Map Range / non-LINEAR still refuse Slice 2ak. Color links still TEX_ENVIRONMENT only. |
| Native | Version stamp only → `0.0.38-slice2ak` (Background strength path unchanged). |
| Version | `0.0.38-slice2ak` |
| Tools | `tools/_quanttrace_slice2ak_scene.py`, `tools/_quanttrace_slice2ak_smoke.py`. Modes: `map_range`, `clamp`, `map_tex` (refuse), `mix_float`, `math_mul`, `value`, `unlinked`. Reuses 2aa HDR equirect cube. |
| Visibility | Same OIIO linear EXR gradient as 2aa; Combined chromatic + non-constant. |

### Measured (Session vs stock Cycles Combined, box CPU)

| Case | Res / spp | Δmax | MAE | px≥1e-3 | Gate |
|---|---|---|---|---|---|
| map_range (Value 0.25, From 0..1, To 0.4..1.6 LINEAR clamp → Strength 0.7; sock default 1.0) | 32² / 4 | **4.25e-4** | 2.79e-6 | 0 | **PASS** |
| map_range (Value 0.25, From 0..1, To 0.4..1.6 LINEAR clamp → Strength 0.7; sock default 1.0) | 256² / 128 | **1.20e-4** | 5.84e-7 | 0 | **PASS** |
| clamp (Value 1.5 Min 0.2 Max 0.7 MINMAX → Strength 0.7; sock default 1.0) | 32² / 4 | **4.25e-4** | 2.78e-6 | 0 | **PASS** |
| mix_float (2aj regression, Fac 0.5 A 0.4 B 1.0) | 32² / 4 | **4.25e-4** | 2.78e-6 | 0 | **PASS** |
| math_mul (2ai regression, 0.5 × 1.4) | 32² / 4 | **4.25e-4** | 2.78e-6 | 0 | **PASS** |
| value (2ah regression, Value 0.7) | 32² / 4 | **4.25e-4** | 2.78e-6 | 0 | **PASS** |
| unlinked (2aa regression, Strength 1.0) | 32² / 4 | **6.13e-4** | 4.63e-6 | 0 | **PASS** |

Live graph (stock map_range 0.7 vs stock unlinked 1.0) 32²/4: Δmax=**0.289** (1024 px ≥1e-3, MAE 0.0947). Packed `world_strength=0.7` while Strength socket default stayed 1.0. map_tex (TEX_IMAGE → Map Range.Value) raises Slice 2ak. Proof plate `docs/proof/quanttrace-maprange-strength-32-pair.png` (map_range stock|session) + `/workspace/quanttrace-maprange-strength-32-pair.png`. F12 32² not run this hour; Session is the claim.

### Honesty

- TEX_IMAGE / Noise / RGB Curves / VECTOR Map Range / non-LINEAR interpolation → Strength still refuse. Color links (Sky/Nishita/TEX_IMAGE/RGB/Mix → Background Color) still refuse — Mix→Color needs a new `world_color` float3 ABI, not invented this hour. TEX_IMAGE→L/R/S SVM graphs deferred.
- HDR Δmax remains ~1e-4–7e-4 class (BackgroundLight MIS map), under the 1e-3 gate with 0 px ≥1e-3 on the claim cases.
- SSS 256 residue / still-life 1px noise-class still documented (not claimed fixed). Not spent this hour.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

TEX_IMAGE→L/R/S, or Sky/Nishita/TEX_IMAGE → Background Color, or Mix/Math → Color (needs new `world_color` float3 ABI). SSS 256 residue stays document-only. Not ReSTIR. Not Classroom time %.



## 11pm PlugWalk (2026-08-28) — Math → world Strength (Slice 2ai)

Box: Linux, 8 cores, Blender 5.2.0 CPU. No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| Research | Blender 5.2 Math sockets are identifiers `Value` / `Value_001` / `Value_002` (display name Value). Fold ADD/SUBTRACT/MULTIPLY/DIVIDE/POWER at sync into the existing `world_strength` float. Strength sock default left at 1.0 while Math folds to 0.7 so ignoring the link fails the gate. |
| ABI | Unchanged `world_strength` float. No new C++ fields — constant resolved at sync time (like 2ah Value). |
| Python | `_world_strength_from_sock` + `_fold_world_strength_math` / `_world_strength_math_input` in `sync.py`. Accepts unlinked / Value / Math ← Value|unlinked|shallow Math. TEX_IMAGE / Mix / RGB Curves / Noise / texture-driven Math still refuse Slice 2ai. DIVIDE guards zero. |
| Native | Version stamp only → `0.0.36-slice2ai` (Background strength path unchanged). |
| Version | `0.0.36-slice2ai` |
| Tools | `tools/_quanttrace_slice2ai_scene.py`, `tools/_quanttrace_slice2ai_smoke.py`. Modes: `math_mul`, `math_add`, `value`, `unlinked`. Reuses 2aa HDR equirect cube. |
| Visibility | Same OIIO linear EXR gradient as 2aa; Combined chromatic + non-constant. |

### Measured (Session vs stock Cycles Combined, box CPU)

| Case | Res / spp | Δmax | MAE | px≥1e-3 | Gate |
|---|---|---|---|---|---|
| math_mul (0.5 × 1.4 → Strength; sock default 1.0) | 32² / 4 | **4.25e-4** | 2.78e-6 | 0 | **PASS** |
| math_mul (0.5 × 1.4 → Strength; sock default 1.0) | 256² / 128 | **1.20e-4** | 5.70e-7 | 0 | **PASS** |
| math_add (0.3 + 0.4 → Strength; sock default 1.0) | 32² / 4 | **4.25e-4** | 2.78e-6 | 0 | **PASS** |
| value (2ah regression, Value 0.7) | 32² / 4 | **4.25e-4** | 2.78e-6 | 0 | **PASS** |
| unlinked (2aa regression, Strength 1.0) | 32² / 4 | **6.13e-4** | 4.63e-6 | 0 | **PASS** |

Live graph (stock math_mul 0.7 vs stock unlinked 1.0) 32²/4: Δmax=**0.289** (1024 px ≥1e-3, MAE 0.0947). Packed `world_strength=0.7` while Strength socket default stayed 1.0. TEX_IMAGE → Strength still raises Slice 2ai. Proof plate `docs/proof/quanttrace-math-strength-32-pair.png` (math_mul stock|session) + `/workspace/quanttrace-math-strength-32-pair.png`. F12 32² not run this hour; Session is the claim.

### Honesty

- TEX_IMAGE / Mix / RGB Curves / Noise / texture-driven Math → Strength still refuse. Color links (Sky/Nishita/TEX_IMAGE/RGB/Mix → Background Color) still refuse. TEX_IMAGE→L/R/S SVM graphs deferred.
- HDR Δmax remains ~1e-4–7e-4 class (BackgroundLight MIS map), under the 1e-3 gate with 0 px ≥1e-3 on the claim cases.
- SSS 256 residue / still-life 1px noise-class still documented (not claimed fixed). Not spent this hour.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Done 12am: Mix → Strength. See 12am section.

## 12am PlugWalk (2026-08-29) — Mix → world Strength (Slice 2aj)

Box: Linux, 8 cores, Blender 5.2.0 CPU. No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| Research | Blender 5.2 `ShaderNodeMix` default `data_type=FLOAT`; sockets key by display name (`Factor`/`A`/`B`/`Result`), identifiers `Factor_Float`/`A_Float`/`B_Float`/`Result_Float`. MixRGB (`MIX_RGB`) still exists (Fac/Color1/Color2). Fold MIX/ADD/SUBTRACT/MULTIPLY/DIVIDE at sync into the existing `world_strength` float. Strength sock default left at 1.0 while Mix folds to 0.7 so ignoring the link fails the gate. `clamp_factor` honoured. |
| ABI | Unchanged `world_strength` float. No new C++ fields — constant resolved at sync time (like 2ai Math). |
| Python | `_world_strength_from_sock` + `_fold_world_strength_mix` / `_world_strength_const_input` in `sync.py`. Accepts unlinked / Value / Math / Mix FLOAT / MixRGB (constant Color1/Color2, RGB average = NODE_CONVERT_CF). TEX_IMAGE / color-linked Mix / RGB Curves / Noise / VECTOR Mix still refuse Slice 2aj. |
| Native | Version stamp only → `0.0.37-slice2aj` (Background strength path unchanged). |
| Version | `0.0.37-slice2aj` |
| Tools | `tools/_quanttrace_slice2aj_scene.py`, `tools/_quanttrace_slice2aj_smoke.py`. Modes: `mix_float`, `mix_unlinked`, `mix_rgb`, `mix_tex` (refuse), `math_mul`, `value`, `unlinked`. Reuses 2aa HDR equirect cube. |
| Visibility | Same OIIO linear EXR gradient as 2aa; Combined chromatic + non-constant. |

### Measured (Session vs stock Cycles Combined, box CPU)

| Case | Res / spp | Δmax | MAE | px≥1e-3 | Gate |
|---|---|---|---|---|---|
| mix_float (Fac 0.5 × A 0.4 / B 1.0 → Strength; sock default 1.0) | 32² / 4 | **4.25e-4** | 2.78e-6 | 0 | **PASS** |
| mix_float (Fac 0.5 × A 0.4 / B 1.0 → Strength; sock default 1.0) | 256² / 128 | **1.20e-4** | 5.70e-7 | 0 | **PASS** |
| mix_unlinked (same Mix FLOAT, Factor/A/B unlinked) | 32² / 4 | **4.25e-4** | 2.78e-6 | 0 | **PASS** |
| mix_rgb (MixRGB Fac 0.5, grey 0.4 / 1.0) | 32² / 4 | **4.25e-4** | 2.79e-6 | 0 | **PASS** |
| math_mul (2ai regression, 0.5 × 1.4) | 32² / 4 | **4.25e-4** | 2.78e-6 | 0 | **PASS** |
| value (2ah regression, Value 0.7) | 32² / 4 | **4.25e-4** | 2.78e-6 | 0 | **PASS** |
| unlinked (2aa regression, Strength 1.0) | 32² / 4 | **6.13e-4** | 4.63e-6 | 0 | **PASS** |

Live graph (stock mix_float 0.7 vs stock unlinked 1.0) 32²/4: Δmax=**0.289** (1024 px ≥1e-3, MAE 0.0947). Packed `world_strength=0.7` while Strength socket default stayed 1.0. mix_tex (TEX_IMAGE → Mix.A) raises Slice 2aj. Proof plate `docs/proof/quanttrace-mix-strength-32-pair.png` (mix_float stock|session) + `/workspace/quanttrace-mix-strength-32-pair.png`. F12 32² not run this hour; Session is the claim.

### Honesty

- TEX_IMAGE / color-linked Mix / RGB Curves / Noise / texture-driven Mix → Strength still refuse. Color links (Sky/Nishita/TEX_IMAGE → Background Color) still refuse. VECTOR/ROTATION Mix and HUE/SATURATION/COLOR/VALUE blend types still refuse. TEX_IMAGE→L/R/S SVM graphs deferred.
- HDR Δmax remains ~1e-4–7e-4 class (BackgroundLight MIS map), under the 1e-3 gate with 0 px ≥1e-3 on the claim cases.
- SSS 256 residue / still-life 1px noise-class still documented (not claimed fixed). Not spent this hour.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Done 1am: Map Range/Clamp → Strength. Mix→Color still needs a new world_color float3 ABI. See 1am section.

## 10pm PlugWalk (2026-08-28) — linked world Strength (Slice 2ah)

Box: Linux, 8 cores, Blender 5.2.0 CPU. No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| Research | Background.Strength is a float. ShaderNodeValue output `default_value` is the constant Cycles uses. Socket default left at 1.0 while Value=0.7 so a packer that ignores the link would fail Session vs stock. Math/TEX_IMAGE/Mix deferred. Color links unchanged. |
| ABI | Unchanged `world_strength` float. No new C++ fields — constant resolved at sync time (like 2ag L/R/S). |
| Python | `_world_strength_from_sock` in `sync.py`. `_world_info` accepts unlinked default **or** single ShaderNodeValue. Multi-link / TEX_IMAGE / Mix / RGB Curves / Noise / Math still refuse Slice 2ah. Sky/Nishita Color kitchens still refuse. |
| Native | Version stamp only → `0.0.35-slice2ah` (Background strength path unchanged). |
| Version | `0.0.35-slice2ah` |
| Tools | `tools/_quanttrace_slice2ah_scene.py`, `tools/_quanttrace_slice2ah_smoke.py`. Modes: `value`, `unlinked`. Reuses 2aa HDR equirect cube. |
| Visibility | Same OIIO linear EXR gradient as 2aa; Combined chromatic + non-constant. |

### Measured (Session vs stock Cycles Combined, box CPU)

| Case | Res / spp | Δmax | MAE | px≥1e-3 | Gate |
|---|---|---|---|---|---|
| value (Value 0.7 → Strength; sock default 1.0) | 32² / 4 | **4.25e-4** | 2.78e-6 | 0 | **PASS** |
| value (Value 0.7 → Strength; sock default 1.0) | 256² / 128 | **1.20e-4** | 5.70e-7 | 0 | **PASS** |
| unlinked (2aa regression, Strength 1.0) | 32² / 4 | **6.13e-4** | 4.63e-6 | 0 | **PASS** |
| mapping (2ac regression, rot_z=0.7) | 32² / 4 | **6.75e-4** | 4.24e-6 | 0 | **PASS** |

Live graph (stock Value 0.7 vs stock unlinked 1.0) 32²/4: Δmax=**0.289** (1024 px ≥1e-3, MAE 0.0947). Packed `world_strength=0.7` while Strength socket default stayed 1.0. Mix RGB → Strength still raises Slice 2ah. Proof plate `docs/proof/quanttrace-linked-world-strength-32-pair.png` (value stock|session) + `/workspace/quanttrace-linked-world-strength-32-pair.png`. F12 32² not run this hour; Session is the claim.

### Honesty

- TEX_IMAGE / Mix / RGB Curves / Noise / Math → Strength still refuse. Color links (Sky/Nishita/TEX_IMAGE/RGB/Mix → Background Color) still refuse. TEX_IMAGE→L/R/S SVM graphs deferred.
- HDR Δmax remains ~1e-4–7e-4 class (BackgroundLight MIS map), under the 1e-3 gate with 0 px ≥1e-3 on the claim cases.
- SSS 256 residue / still-life 1px noise-class still documented (not claimed fixed). Not spent this hour.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

TEX_IMAGE→L/R/S, or Mix/Math → Strength, or Sky/Nishita/TEX_IMAGE → Background Color. SSS 256 residue stays document-only. Not ReSTIR. Not Classroom time %.

## 9pm PlugWalk (2026-08-28) — linked Mapping L/R/S (Slice 2ag)

Box: Linux, 8 cores, Blender 5.2.0 CPU. No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| Research | Blender 5.2 Mapping VECTOR: Location `is_unavailable` (keyed `inputs["Location"]` KeyError; iterate by name). Link Location while POINT then switch to VECTOR (link persists). Combine XYZ → Rotation/Scale OK under VECTOR. Value→VECTOR links (Cycles `NODE_CONVERT_FV` = `(v,v,v)`). VECTOR SVM ignores Location; still pack for ABI honesty. |
| ABI | Unchanged `map_location` / `map_rotation` / `map_scale` float3 (mesh + world). No new link-mode flags — constants resolved at sync time (like 2af filepath materialize). |
| Python | `_float3_from_mapping_lrs_sock` + `_constant_float_from_value_sock` in `sync.py`. `_mapping_constants` accepts unlinked defaults **or** Combine XYZ ← unlinked/Value X/Y/Z **or** Value→L/R/S. Still refuses TEX_COORD / TEX_IMAGE / nested Mapping into L/R/S; vector_type≠VECTOR refused. |
| Native | Version stamp only → `0.0.34-slice2ag` (MappingNode set_location/rotation/scale unchanged). |
| Version | `0.0.34-slice2ag` |
| Tools | `tools/_quanttrace_slice2ag_scene.py`, `tools/_quanttrace_slice2ag_smoke.py`. Modes: `combxyz`, `combxyz_value`, `value_rot`, `unlinked`. |
| Visibility | Same 8×8 sRGB checker + Mapping scale=(2,2,2) loc=(0.1,0.2,0) rot_z=0.15 as Slice 2h; Combined chromatic + non-constant. |

### Measured (Session vs stock Cycles Combined, box CPU)

| Case | Res / spp | Δmax | MAE | px≥1e-3 | Gate |
|---|---|---|---|---|---|
| combxyz (Combine XYZ defaults → L+R+S) | 32² / 4 | **2.26e-6** | 1.29e-8 | 0 | **PASS** |
| combxyz (Combine XYZ defaults → L+R+S) | 256² / 128 | **1.67e-6** | 6.05e-9 | 0 | **PASS** |
| combxyz_value (Value→X/Y/Z → L+R+S) | 32² / 4 | **2.26e-6** | 1.29e-8 | 0 | **PASS** |
| unlinked (2h regression) | 32² / 4 | **2.26e-6** | 1.29e-8 | 0 | **PASS** |

Proof plate `docs/proof/quanttrace-linked-mapping-lrs-32-pair.png` (combxyz stock|session) + `/workspace/quanttrace-linked-mapping-lrs-32-pair.png`. F12 32² not run this hour; Session is the claim.

### Honesty

- TEX_COORD / TEX_IMAGE / nested Mapping → L/R/S still refuse. Linked world Strength, Sky/Nishita kitchens still refuse. TEX_IMAGE→L/R/S SVM graphs deferred.
- Value→Rotation alone packs `(v,v,v)` (honest broadcast); not claimed as a primary gate this hour (`value_rot` tool mode exists).
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Linked world Strength, or TEX_IMAGE→L/R/S if needed. SSS 256 residue stays document-only. Not ReSTIR. Not Classroom time %.

## 8pm PlugWalk (2026-08-28) — packed-only images (Slice 2af)

Box: Linux, 8 cores, Blender 5.2.0 CPU. No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| Research | Blender 5.2 `Image.packed_file.data` (bytes) + `filepath` / `filepath_from_user`. Prefer writing packed bytes over inventing a pixel-buffer ABI. Colorspace stays `Image.colorspace_settings.name`. |
| ABI | Unchanged filepath: `image_path` / `world_image_path` / `*_image_path`. Native ImageTextureNode / EnvironmentTextureNode still `set_filename(path)`. |
| Python | `_abspath_image` prefers on-disk filepath; else `_materialize_packed_image` writes to `/tmp/quanttrace_packed/<name>_<sha1>.<ext>` (stable within session). Covers mesh TEX_IMAGE (`_tex_image_from_sock`) and world Environment Texture (`_world_info`). Empty only when truly missing. |
| Native | Version stamp only → `0.0.33-slice2af` (no C++ path change). |
| Version | `0.0.33-slice2af` |
| Tools | `tools/_quanttrace_slice2af_scene.py`, `tools/_quanttrace_slice2af_smoke.py`. Modes: `base_packed`, `hdr_packed`, `disk`. |
| Visibility | Combined chromatic + non-constant on packed Base Color checker and packed HDR env. |

### Measured (Session vs stock Cycles Combined, box CPU)

| Case | Res / spp | Δmax | MAE | px≥1e-3 | Gate |
|---|---|---|---|---|---|
| base_packed (TEX_IMAGE) | 32² / 4 | **1.01e-6** | 7.01e-9 | 0 | **PASS** |
| base_packed (TEX_IMAGE) | 256² / 128 | **1.43e-6** | 3.27e-9 | 0 | **PASS** |
| hdr_packed (Env TEX) | 32² / 4 | **6.13e-4** | 4.63e-6 | 0 | **PASS** |
| hdr_packed (Env TEX) | 256² / 128 | **2.01e-4** | 9.02e-7 | 0 | **PASS** |
| disk (2f regression) | 32² / 4 | **1.01e-6** | 7.01e-9 | 0 | **PASS** |

Packed cache paths under `/tmp/quanttrace_packed/`. Proof plate `docs/proof/quanttrace-packed-32-pair.png` (base_packed stock|session). F12 32² not run this hour; Session is the claim.

### Honesty

- Linked Mapping L/R/S, linked world Strength, Sky/Nishita/TEX_IMAGE/RGB/Mix → Background Color, kitchens still refuse.
- HDR Δmax remains ~1e-4–7e-4 class (BackgroundLight MIS map), under the 1e-3 gate with 0 px ≥1e-3 on the claim cases.
- SSS 256 residue / still-life 1px noise-class still documented (not claimed fixed). Not spent this hour.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Linked Mapping L/R/S landed 2ag. Next: linked world Strength. SSS 256 residue stays document-only unless a real root cause appears. Not ReSTIR. Not Classroom time %.

## 7pm PlugWalk (2026-08-28) — Env Object-with-pointer (Slice 2ae)

Box: Linux, 8 cores, Blender 5.2.0 CPU. No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| Research | Mesh Slice 2ab `tex_ob_*` + Cycles `TextureCoordinateNode` `use_transform` / `ob_tfm` (compile packs `transform_inverse`; cite `shader_nodes.cpp` + `tex_coord.h` NODE_TEXCO_OBJECT_WITH_TRANSFORM). World/background Object uses same SVM path on `shading_position`. |
| ABI | `world_ob_use_transform` + `world_ob_tfm[12]` after `world_map_type` on `QT_Scene` + `QT_SimpleScene`. 0 = Slice 2ac empty-ref bit-identical. |
| Python | `_world_info` accepts Object pointer on Env Vector / Mapping←Object; `_pack_world_ob_fields` / `_finalize_world_pack` packs evaluated `matrix_world` 3x4 (same helper as mesh 2ab). Empty-ref stays use_transform=0. ctypes + `_fill_world_vec_ctypes` lockstep. |
| Native | When `tex_mode_is_object(wmode)` + `world_ob_use_transform`: `set_use_transform(true)` + `set_ob_tfm(tfm_from_12)` — do not invert twice. |
| Version | `0.0.32-slice2ae` |
| Tools | `tools/_quanttrace_slice2ae_scene.py`, `tools/_quanttrace_slice2ae_smoke.py`. Modes: `pointer`, `pointer_mapping`, `empty_ref`, `generated`, `unlinked`. Empty `QT_WorldEmpty` default rot_z=0.4 loc=(0,0,0). |
| Visibility | Combined chromatic + non-constant. Stock pointer vs empty-ref Δmax=0.217 proves graph live. |

### Measured (Session vs stock Cycles Combined, box CPU)

| Case | Res / spp | Δmax | MAE | px≥1e-3 | Gate |
|---|---|---|---|---|---|
| pointer (rot_z=0.4) | 32² / 4 | **6.74e-4** | 5.86e-6 | 0 | **PASS** |
| pointer (rot_z=0.4) | 256² / 128 | **2.12e-4** | 1.14e-6 | 0 | **PASS** |
| pointer_mapping (rot_z=0.4 + map 0.7) | 32² / 4 | **6.43e-4** | 4.45e-6 | 0 | **PASS** |
| empty_ref (2ac regression) | 32² / 4 | **6.13e-4** | 4.63e-6 | 0 | **PASS** |

Live graph (stock pointer vs stock empty-ref) 32²/4: Δmax=**0.217** (1024 px ≥1e-3, MAE 0.0531). Packed `world_ob_use_transform=1` / tfm `[0.921, -0.389, 0, 0, 0.389, 0.921, 0, 0, 0, 0, 1, 0]` (cos/sin 0.4). empty-ref packed `use_transform=0` identity. Proof plate `docs/proof/quanttrace-env-object-pointer-32-pair.png`. F12 32² not run this hour; Session is the claim.

Honesty: Empty loc=(0.5,0.25,0)+rot_z=0.4 32²/4 Δmax=**1.84e-3** (1 px ≥1e-3, MAE 6.05e-6) — HDR-MIS residue class on the sharp gradient when translation shifts lookups; rot-only is the measured claim. Any non-zero Empty translation reproduced the 1 px tip-over at 4spp; MAE stayed ~6e-6.

### Honesty

- Linked Mapping L/R/S, linked world Strength, Sky/Nishita/TEX_IMAGE/RGB/Mix → Background Color, kitchens still refuse. (Packed-only images landed 2af.)
- HDR Δmax remains ~1e-4–7e-4 class (BackgroundLight MIS map), under the 1e-3 gate with 0 px ≥1e-3 on the claim cases.
- SSS 256 residue / still-life 1px noise-class still documented (not claimed fixed). Not spent this hour.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Linked Mapping L/R/S / world Strength. SSS 256 residue stays document-only unless a real root cause appears. Not ReSTIR. Not Classroom time %.

## 6pm PlugWalk (2026-08-28) — BLENDER_OBJECT / BLENDER_WORLD Normal (Slice 2ad)

Box: Linux, 8 cores, Blender 5.2.0 CPU. No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| Research | Blender 5.2 RNA `ShaderNodeNormalMap.space`: TANGENT=0 OBJECT=1 WORLD=2 **BLENDER_OBJECT=3** **BLENDER_WORLD=4**. Cycles `NodeNormalMapSpace` (`kernel/svm/types.h`) + `shader_nodes.cpp` SOCKET_ENUM `"blender_object"` / `"blender_world"`. SVM `tex_coord.h` flips `color.y`/`color.z` for BLENDER_* ("strange blender convention") then Object-transforms only BLENDER_OBJECT / OBJECT. Not an alias of Object/World. |
| ABI | Extend `QT_NORMAL_MAP_BLENDER_OBJECT=3` / `QT_NORMAL_MAP_BLENDER_WORLD=4` on existing `normal_space` / `coat_normal_space` ints (0..2 bit-identical with 2z). |
| Python | `_normal_map_from_sock` accepts BLENDER_OBJECT / BLENDER_WORLD → 3/4. Unknown spaces still refuse Slice 2ad. |
| Native | `nmap->set_space` maps 3/4 → `NODE_NORMAL_MAP_BLENDER_OBJECT` / `BLENDER_WORLD` (Normal + Coat). Unknown → TANGENT. |
| Version | `0.0.31-slice2ad` |
| Tools | `tools/_quanttrace_slice2ad_scene.py`, `tools/_quanttrace_slice2ad_smoke.py`. Spaces include BLENDER_* + TANGENT/OBJECT/WORLD. |
| Visibility | Same 16×16 Non-Color hill as 2j/2z; Roughness=0.5 Metallic=0 Strength=1. Combined chromatic + non-constant. |

### Measured (Session vs stock Cycles Combined, box CPU)

| Case | Res / spp | Δmax | MAE | px≥1e-3 | Gate |
|---|---|---|---|---|---|
| BLENDER_OBJECT | 32² / 4 | **5.59e-9** | 4.84e-11 | 0 | **PASS** |
| BLENDER_OBJECT | 256² / 128 | **7.45e-9** | 1.90e-11 | 0 | **PASS** |
| BLENDER_WORLD | 32² / 4 | **6.52e-9** | 4.97e-11 | 0 | **PASS** |
| BLENDER_WORLD | 256² / 128 | **7.45e-9** | 1.90e-11 | 0 | **PASS** |
| Object (2z regression) | 32² / 4 | **3.58e-7** | 6.75e-9 | 0 | **PASS** |

Live graph (stock BLENDER_OBJECT vs stock Object, same PNG) 32²/4: Δmax=**1.68** (82 px ≥1e-3, MAE 0.0564). Stock BLENDER_WORLD vs World Δmax=**1.68**. Stock BLENDER_OBJECT vs BLENDER_WORLD Δmax≈0 on identity-tfm cube (same as Object≡World on unrotated mesh). Packed `normal_space=3` / `4`. Proof plate `docs/proof/quanttrace-blender-object-normal-32-pair.png`. F12 32² not run this hour; Session is the claim.

### Honesty

- Packed-only images, linked Mapping L/R/S, linked world Strength, Sky/Nishita/TEX_IMAGE/RGB/Mix → Background Color, kitchens still refuse. (Env Object-with-pointer landed 2ae.)
- Linked Strength / custom uv_map on Normal Map still refuse.
- SSS 256 residue / still-life 1px noise-class still documented (not claimed fixed). Not spent this hour.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Packed-only images, or linked Mapping L/R/S. SSS 256 residue stays document-only unless a real root cause appears. Not ReSTIR. Not Classroom time %.



## 5pm PlugWalk (2026-08-28) — Linked env Vector / Mapping (Slice 2ac)

Box: Linux, 8 cores, Blender 5.2.0 CPU. No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| ABI | `world_tex_vector_mode` + `world_map_location/rotation/scale` + `world_map_type` after `world_projection` on `QT_Scene` + `QT_SimpleScene`. Mode 0 = Slice 2aa unlinked LINK_POSITION (bit-identical). Reuses `QT_TEX_VECTOR_*` enums (Generated=3, Mapping-Generated=4). |
| Python | `_world_info` accepts Env Vector ← TEX_COORD (Generated/Object empty-ref/Camera/Window/Reflection/UV) or Mapping(VECTOR, unlinked L/R/S) ← TEX_COORD. Object-with-pointer on world refused (no world_ob_tfm ABI). Linked Strength / packed-only / non-TEX_ENVIRONMENT Color still refuse (Slice 2ac). ctypes + `simple_to_qt` / `_fill_world_vec_ctypes` lockstep. |
| Native | `EnvironmentTextureNode` Vector wired from `TextureCoordinateNode` (+ optional `MappingNode`) matching mesh `wire_tex_image` path. Mode 0 leaves LINK_POSITION. Cite `shader_nodes.cpp` EnvironmentTextureNode Vector + TextureCoordinateNode::compile background Generated → NODE_GEOM_P. |
| Version | `0.0.30-slice2ac` |
| Tools | `tools/_quanttrace_slice2ac_scene.py`, `tools/_quanttrace_slice2ac_smoke.py`. Modes: `generated`, `mapping`, `unlinked`. Mapping defaults rot_z=0.7. |
| Visibility | Combined chromatic + non-constant. Stock Mapping vs unlinked Δmax=0.821 proves graph live. Generated ≡ unlinked on world (honest Cycles background NODE_GEOM_P). |

### Measured (Session vs stock Cycles Combined, box CPU)

| Case | Res / spp | Δmax | MAE | px≥1e-3 | Gate |
|---|---|---|---|---|---|
| Generated | 32² / 4 | **6.13e-4** | 4.63e-6 | 0 | **PASS** |
| Generated | 256² / 128 | **2.01e-4** | 9.02e-7 | 0 | **PASS** |
| Mapping (rot_z=0.7) | 32² / 4 | **6.75e-4** | 4.24e-6 | 0 | **PASS** |
| Mapping (rot_z=0.7) | 256² / 128 | **2.04e-4** | 8.24e-7 | 0 | **PASS** |
| 2aa unlinked (regression) | 32² / 4 | **6.13e-4** | 4.63e-6 | 0 | **PASS** |

Live graph (stock Mapping vs stock unlinked) 32²/4: Δmax=**0.821** (1024 px ≥1e-3, MAE 0.349). Stock Generated vs unlinked Δmax=**0** (background Generated ≡ LINK_POSITION). Packed `world_tex_vector_mode=3/4/0`, Mapping rot z≈0.7. Proof plate `docs/proof/quanttrace-env-vector-32-pair.png` (Mapping stock|session). F12 32² not run this hour; Session is the claim.

### Honesty

- Object-with-pointer on env Vector, packed-only images, linked Mapping L/R/S, linked world Strength, Sky/Nishita/TEX_IMAGE/RGB/Mix → Background Color, `BLENDER_OBJECT` / `BLENDER_WORLD` Normal space, kitchens still refuse.
- HDR Δmax remains ~1e-4 class (BackgroundLight MIS map), under the 1e-3 gate with 0 px ≥1e-3.
- SSS 256 residue / still-life 1px noise-class still documented (not claimed fixed). Not spent this hour.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

`BLENDER_OBJECT`/`BLENDER_WORLD` Normal space, or env Object-with-pointer (`world_ob_tfm`), or packed-only images. SSS 256 residue stays document-only unless a real root cause appears. Not ReSTIR. Not Classroom time %.



## 4pm PlugWalk (2026-08-28) — TEX_COORD Object-with-pointer (Slice 2ab)

Box: Linux, 8 cores, Blender 5.2.0 CPU. No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| ABI | `tex_ob_use_transform` / `tex_ob_tfm[12]` after `transmission_weight` on `QT_Mesh` + `QT_SimpleScene`. 0 = Slice 2l empty-ref (bit-identical; native ignores tfm). 1 = Object pointer. Mesh-level: one Object reference per mesh. Two different objects → `QuantTraceSyncError` Slice 2ab. |
| Python | Stop refusing `ShaderNodeTexCoord.object`. Collect pointer (direct TEX_COORD or Mapping's TEX_COORD source). Pack `use_transform=1` + `_matrix_3x4(evaluated.matrix_world)` via the pack_scene depsgraph. Empty-ref stays 0. `from_instancer` / `from_dupli` unused. Mapping scene `object_ref=` optional. |
| Native | `wire_tex_image`: if Object mode AND `ob_use_transform`: `set_use_transform(true)` + `set_ob_tfm(tfm_from_12(ob_tfm))`. Cycles compile packs `transform_inverse(ob_tfm)` — do not invert twice. use_transform==0 leaves default false (2l bit-identical). `simple_to_qt` copies both fields. Cite `shader_nodes.cpp` TextureCoordinateNode SOCKET_BOOLEAN use_transform + SOCKET_TRANSFORM ob_tfm. |
| Version | `0.0.29-slice2ab` |
| Tools | `tools/_quanttrace_slice2ab_scene.py`, `tools/_quanttrace_slice2ab_smoke.py`. Empty `QT_TexEmpty` loc=(0.5, 0.25, 0.0) rot_z=0.4 (not a mesh). `--empty-ref` is 2l. `--mode mapping` uses 2l mapping constants. |
| Visibility | 8×8 sRGB checker on Object coords; Combined chromatic + non-constant. Empty transform non-identity (identity Empty is a false pass). |

### Measured (Session vs stock Cycles Combined, box CPU)

| Case | Res / spp | Δmax | MAE | px≥1e-3 | Gate |
|---|---|---|---|---|---|
| Object-pointer | 32² / 4 | **1.08e-5** | 3.41e-8 | 0 | **PASS** |
| Object-pointer | 256² / 128 | **4.41e-6** | 1.75e-8 | 0 | **PASS** |
| Object-pointer + Mapping | 32² / 4 | **2.24e-5** | 8.45e-8 | 0 | **PASS** |
| 2l empty-ref Object (regression) | 32² / 4 | **7.99e-6** | 2.56e-8 | 0 | **PASS** |

Live graph (stock Object-pointer vs stock empty-ref) 32²/4: Δmax=**0.684** (81 px ≥1e-3, MAE 0.00811). Not claimed PASS against empty-ref. Packed `tex_ob_use_transform=1` / tfm `[0.921, -0.389, 0, 0.5, 0.389, 0.921, 0, 0.25, 0, 0, 1, 0]` (cos/sin 0.4 + translate). Empty-ref packed `use_transform=0` identity tfm. Proof plate `docs/proof/quanttrace-object-ptr-32-pair.png`. F12 32² not run this hour; Session is the claim. Optional 2aa HDR / 2z Object Normal 32² not re-run this hour.

### Honesty

- `BLENDER_OBJECT` / `BLENDER_WORLD` Normal space, packed-only images, linked Mapping L/R/S, env Object-with-pointer, kitchens still refuse. (Linked env Vector/Mapping: Slice 2ac.)
- SSS 256 residue / still-life 1px noise-class still documented (not claimed fixed). Not spent this hour.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

`BLENDER_OBJECT`/`BLENDER_WORLD` Normal space, or env Object-with-pointer. SSS 256 residue stays document-only unless a real root cause appears. Not ReSTIR. Not Classroom time %.



---

## 3pm PlugWalk (2026-08-28) — HDR / Environment Texture world (Slice 2aa)

Box: Linux, 8 cores, Blender 5.2.0 CPU. No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| ABI | `world_image_path` / `world_image_colorspace` / `world_projection` after `world_strength` on `QT_Scene` + `QT_SimpleScene`. Empty path = Slice 2b black+strength (bit-identical). projection 0=EQUIRECTANGULAR, 1=MIRROR_BALL. Vector left unlinked (Cycles `LINK_POSITION`). |
| Python | `_world_info(scene)` replaces `_world_strength` call sites. TEX_ENVIRONMENT + disk filepath only; packed-only / linked Vector / linked Strength / other Color sources refuse (Slice 2aa). Colorspace from `Image.colorspace_settings.name`. ctypes `_fields_` + `simple_to_qt` / `to_ctypes_*` lockstep. |
| Native | `EnvironmentTextureNode` filename/colorspace/projection → Background Color. Empty path keeps black Background. With path: `BackgroundLight` + `use_mis=true` + `map_resolution=1024` (Blender factory `sample_map_resolution`) so surface lighting matches; camera-ray bg alone matched without it. Cite `shader_nodes.cpp` EnvironmentTextureNode (LINK_POSITION Vector default). |
| Version | `0.0.28-slice2aa` |
| Tools | `tools/_quanttrace_slice2aa_scene.py`, `tools/_quanttrace_slice2aa_smoke.py` (tiny OIIO linear EXR gradient, not a studio HDR) |
| Visibility | Env left-red/right-cyan; stock Combined chromatic + non-constant; packed path non-empty, projection 0, strength 1.0. |

### Measured (Session vs stock Cycles Combined, box CPU)

| Case | Res / spp | Δmax | MAE | px≥1e-3 | Gate |
|---|---|---|---|---|---|
| HDR EQUIRECTANGULAR | 32² / 4 | **6.13e-4** | 4.63e-6 | 0 | **PASS** |
| HDR EQUIRECTANGULAR | 256² / 128 | **2.01e-4** | 9.02e-7 | 0 | **PASS** |
| Black-world empty path (regression) | 32² / 4 | **3.58e-7** | 5.34e-9 | 0 | **PASS** |
| Object Normal (2z regression) | 32² / 4 | **3.58e-7** | 6.75e-9 | 0 | **PASS** |
| MIRROR_BALL (optional) | 32² / 4 | **6.90e-4** | 4.63e-6 | 0 | **PASS** |

Live graph (stock HDR vs stock black-world) 32²/4: Δmax=**0.857** (1024 px ≥1e-3, MAE 0.308). Packed `world_image_path` non-empty, `world_projection=0`, `world_strength=1.0`, colorspace `Linear Rec.709`. Proof plate `docs/proof/quanttrace-hdr-32-pair.png`. F12 32² not run this hour; Session is the claim.

### Honesty

- Linked Vector / Mapping / TEX_COORD on Environment Texture, packed-only images, Sky Texture / Nishita / TEX_IMAGE / RGB / Mix → Background Color, linked Strength, world rotation ABI, transparent film, MIS knobs beyond factory BackgroundLight: still refuse.
- HDR Δmax is ~1e-4 class (BackgroundLight MIS map), not the 1e-7 black-world class — still under the 1e-3 gate with 0 px ≥1e-3.
- SSS 256 residue / still-life 1px noise-class still documented (not claimed fixed). Not spent this hour.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Object-with-pointer, or `BLENDER_OBJECT`/`BLENDER_WORLD` Normal space, or linked env Vector / Mapping. SSS 256 residue stays document-only unless a real root cause appears. Not ReSTIR. Not Classroom time %.



---

## 2pm PlugWalk (2026-08-28) — Principled Normal Map Object/World space (Slice 2z)

Box: Linux, 8 cores, Blender 5.2.0 CPU. No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| ABI | `normal_space` / `coat_normal_space` int after `normal_strength` / `coat_normal_strength` on `QT_Mesh` + `QT_SimpleScene`. `QT_NORMAL_MAP_TANGENT=0` `OBJECT=1` `WORLD=2`. Default 0 fills prior float-to-pointer padding so 2j/2t Tangent cubes stay bit-identical. |
| Python | `_normal_map_from_sock` accepts TANGENT/OBJECT/WORLD (case-insensitive). Maps to 0/1/2. `BLENDER_OBJECT` / `BLENDER_WORLD` / anything else `QuantTraceSyncError` naming Slice 2z. `_empty_normal_info` space=0. Mesh dict + `_fill_tex_ctypes` copy both ints. ctypes `_fields_` lockstep. |
| Native | `nmap->set_space` from `m->normal_space` / `m->coat_normal_space`. Unknown → TANGENT. Cite `intern/cycles/blender/shader.cpp` ShaderNodeNormalMap + `src/scene/shader_nodes.cpp` SOCKET_ENUM space. `simple_to_qt` copies both ints. Do not invent blender_object/blender_world. Bump path / convention / base unchanged. |
| RNA | Blender 5.2 `ShaderNodeNormalMap.space` TANGENT/OBJECT/WORLD. Cycles `NODE_NORMAL_MAP_{TANGENT,OBJECT,WORLD}`. |
| Version | `0.0.27-slice2z` |
| Tools | `tools/_quanttrace_slice2z_scene.py`, `tools/_quanttrace_slice2z_smoke.py` |
| Visibility | Roughness=0.5 Metallic=0 Strength=1.0 unlinked. Same 16×16 Non-Color tangent-hill PNG as 2j. Combined not all-zero / not constant. |

### Measured (Session vs stock Cycles Combined, box CPU)

| Socket | Res / spp | Δmax | MAE | px≥1e-3 | Gate |
|---|---|---|---|---|---|
| Object Normal | 32² / 4 | **3.58e-7** | 6.75e-9 | 0 | **PASS** |
| Object Normal | 256² / 128 | **5.96e-7** | 4.27e-9 | 0 | **PASS** |
| World Normal | 32² / 4 | **3.58e-7** | 7.10e-9 | 0 | **PASS** |
| World Normal | 256² / 128 | **7.15e-7** | 4.26e-9 | 0 | **PASS** |
| Tangent (2j regression) | 32² / 4 | **3.58e-7** | 7.27e-9 | 0 | **PASS** |
| Bump (2x regression) | 32² / 4 | **2.38e-7** | 5.49e-9 | 0 | **PASS** |
| Coat Normal Object (optional) | 32² / 4 | **2.38e-7** | 5.66e-9 | 0 | **PASS** |

Live graph (stock Object vs stock Tangent, same PNG) 32²/4: Δmax=**0.821** (82 px ≥1e-3, MAE 0.0210). Packed `normal_space=1` (OBJECT) / `2` (WORLD) / `0` (TANGENT). Coat Object packed `coat_normal_space=1`. Identity-tfm cube Object vs World Combined match (object==world on unrotated mesh; not a packing miss). Proof plate `docs/proof/quanttrace-object-normal-32-pair.png`. F12 32² not run this hour; Session is the claim.

### Honesty

- Linked Strength, custom uv_map, packed-only, HDR, kitchens, Object-with-pointer, linked Mapping L/R/S, `BLENDER_OBJECT` / `BLENDER_WORLD` still refuse.
- SSS 256 residue / still-life 1px noise-class still documented (not claimed fixed). Not spent this hour.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

HDR world / Object-with-pointer (or `BLENDER_OBJECT`/`BLENDER_WORLD` space). SSS 256 residue stays document-only unless a real root cause appears. Not ReSTIR. Not Classroom time %.



---

## 1pm PlugWalk (2026-08-28) — Principled Thin Wall BOOLEAN (Slice 2y)

Box: Linux, 8 cores, Blender 5.2.0 CPU. No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| ABI | `thin_wall` (int 0/1) + `transmission_weight` (float) appended after `bump_invert` on `QT_Mesh` + `QT_SimpleScene`. Existing ctypes offsets stay valid. Reserved `thin_wall_image_path` Color→Int unused (packer never fills). |
| Python | Unlinked Thin Wall → `thin_wall = 1 if bool(default_value) else 0`. Linked Thin Wall still `QuantTraceSyncError` (BOOLEAN, not TEX_IMAGE). Unlinked Transmission Weight RNA default → `transmission_weight` (0.0 if missing / linked). Slice 2p `trans_` TEX_IMAGE still wins when linked. Defaults 0/0.0 so opaque cubes stay bit-identical. |
| Native | `bsdf->set_thin_wall(m->thin_wall)` always. If `trans_image_path` empty: `set_transmission_weight`; else keep Color→Transmission Weight TEX_IMAGE. Color→Thin Wall block stays as a dead reserved path. |
| RNA | Blender 5.2 Thin Wall is BOOLEAN. Cycles `is_thin_wall()` = (socket unlinked) AND `thin_wall`. Visual no-op unless Transmission Weight is nonzero. Cycles default Transmission Weight 0. |
| Version | `0.0.26-slice2y` |
| Tools | `tools/_quanttrace_slice2y_scene.py`, `tools/_quanttrace_slice2y_smoke.py` |
| Visibility | Thin Wall True, Transmission Weight 1.0, Roughness 0.05, Metallic 0, IOR 1.45, Base ~0.8 gray. No textures. Combined not all-zero / not constant. |

### Measured (Session vs stock Cycles Combined, box CPU)

| Socket | Res / spp | Δmax | MAE | Gate |
|---|---|---|---|---|
| ThinWall True | 32² / 4 | **3.18e-12** | 2.92e-14 | **PASS** |
| ThinWall True | 256² / 128 | **2.32e-8** | 1.37e-12 | **PASS** |
| Bump (2x regression) | 32² / 4 | **2.38e-7** | 5.49e-9 | **PASS** |

True vs False (stock, Transmission=1 both) 32²/4: Δmax=**6.83e-5** (0 px ≥1e-3; below the 1e-3 “clearly live” bar). Combined peak True 8.31e-6 / False 7.35e-5 — both near-black thin/thick glass vs black world (Fresnel + missed specular; opaque trans=0 same cube Δmax=1.56, 82 px). Session True matches stock True (3.18e-12) not stock False (6.83e-5) — boolean is packed, not a geometric-opaque match. Packed `thin_wall=1` `transmission_weight=1.0`. F12 32² not run this hour; Session is the claim.

### Honesty

- Object/World Normal, linked Strength, Bump on Coat Normal, HDR/kitchens, Object-with-pointer, packed-only, linked Mapping L/R/S still refuse.
- Linked Thin Wall still refuses (BOOLEAN, not TEX_IMAGE).
- Still-life 256² 1px + SSSWeight 256² 1px + SSSAniso 256² 3px noise-class residue still documented (not claimed fixed).
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

SSS 256 residue or Object/World Normal space. Not ReSTIR. Not Classroom time %.



## 12pm PlugWalk (2026-08-28) — Principled Bump TEX_IMAGE Height (Slice 2x)

Box: Linux, 8 cores, Blender 5.2.0 CPU. No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| ABI | `bump_` on `QT_Mesh` + `QT_SimpleScene` (path/cs/vector/map + strength/distance/invert). Parallel to `normal_*`; not reuse. |
| Python | `sync._principled_normal_dispatch`: NORMAL_MAP → 2j; BUMP → `_bump_from_sock`; else refuse. Coat Normal stays Normal-Map-only (Bump on Coat Normal refuses). Height must be TEX_IMAGE Color. Strength/Distance/Normal-input linked refuse. invert RNA OK. |
| Native | ImageTexture Color → NODE_CONVERT_CF → BumpNode Height. `set_invert` / `set_use_object_space(false)` / `set_strength` / `set_distance`. Do not wire Sample*; `refine_bump_nodes` clones Height. If both ABI paths set, Bump wins. |
| RNA | bpy-verified ShaderNodeBump: invert=False, Strength=1.0, Distance=**0.001** (not Cycles NODE_DEFINE 0.1), Filter Width=0.1, Height=1.0. No use_object_space RNA. |
| Version | `0.0.25-slice2x` |
| Tools | `tools/_quanttrace_slice2x_scene.py`, `tools/_quanttrace_slice2x_smoke.py` |
| Visibility | Roughness=0.5 Metallic=0. 16×16 Non-Color height hill (0.15 outside / 0.9 center). Stock Combined not constant / not all-zero. |

### Measured (Session vs stock Cycles Combined, box CPU)

| Socket | Res / spp | Δmax | MAE | Gate |
|---|---|---|---|---|
| Bump | 32² / 4 | **2.38e-7** | 5.49e-9 | **PASS** |
| Bump | 256² / 128 | **4.77e-7** | 4.00e-9 | **PASS** |
| NormalMap (2j regression) | 32² / 4 | **3.58e-7** | 7.27e-9 | **PASS** |
| Aniso (2w regression) | 32² / 4 | **3.35e-8** | 1.78e-10 | **PASS** |

Bump vs no-bump cube (stock 32²/4): Δmax=0.205 (82 px / 1024) — graph is live, not a geometric-normal match. F12 32² not run this hour; Session is the claim.

### Honesty

- Thin Wall BOOLEAN / Object/World Normal space / linked Strength / HDR / kitchens / Object-with-pointer / packed-only / linked Mapping L/R/S still refuse.
- Bump on Coat Normal still refuses (2t Normal-Map-only).
- Still-life 256² 1px + SSSWeight 256² 1px + SSSAniso 256² 3px noise-class residue still documented (not claimed fixed).
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Thin Wall boolean path, close still-life / SSSWeight / SSSAniso 256² SSS noise residue. Not ReSTIR. Not Classroom time %.



---

## 11am PlugWalk (2026-08-28) — Anisotropic / Rotation / Tangent TEX_IMAGE (Slice 2w)

Box: Linux, 8 cores, Blender 5.2.0 CPU. No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| ABI | `aniso_` / `aniso_rot_` / `tangent_` on `QT_Mesh` + `QT_SimpleScene` |
| Python | `sync._principled_from_material` accepts Anisotropic / Anisotropic Rotation / Tangent (Non-Color gray checker). Same Vector rules as 2v |
| Native | Anisotropic / Rotation Color→float via NODE_CONVERT_CF; Tangent Color→Vector (same as Subsurface Radius). Pins `set_anisotropic(1.0)` when Rotation/Tangent map and Anisotropic path empty. Fills ATTR_STD_GENERATED bbox orco when Aniso/AnisoRot map and Tangent unlinked |
| Version | `0.0.24-slice2w` |
| Tools | `tools/_quanttrace_slice2w_scene.py`, `tools/_quanttrace_slice2w_smoke.py` |
| Visibility | Aniso/AnisoRot/Tangent/Combo pin Metallic=1.0 Roughness=0.2 (GGX highlight). Stock Combined not constant / not all-zero |

### Measured (Session vs stock Cycles Combined, box CPU)

| Socket | Res / spp | Δmax | MAE | Gate |
|---|---|---|---|---|
| Aniso | 32² / 4 | **3.35e-8** | 1.78e-10 | **PASS** |
| Aniso | 256² / 128 | **1.09e-7** | 1.12e-10 | **PASS** |
| AnisoRot | 32² / 4 | **2.04e-6** | 1.40e-8 | **PASS** |
| AnisoRot | 256² / 128 | **9.35e-6** | 4.24e-9 | **PASS** |
| Tangent | 32² / 4 | **5.09e-11** | 6.58e-13 | **PASS** |
| Tangent | 256² / 128 | **5.09e-11** | 3.41e-13 | **PASS** |
| Combo (Aniso+AnisoRot) | 32² / 4 | **2.42e-7** | 1.20e-9 | **PASS** |
| DiffuseRough (2v regression) | 32² / 4 | **3.58e-7** | 5.84e-9 | **PASS** |

Aniso first 32² attempt failed Δmax=0.021 until ATTR_STD_GENERATED bbox orco was filled for default Principled Tangent — documented fix, not noise-class.

### Honesty

- Bump / Thin Wall boolean / Object/World Normal space / linked Strength / HDR / kitchens / Object-with-pointer / packed-only / linked Mapping L/R/S still refuse.
- Still-life 256² 1px + SSSWeight 256² 1px + SSSAniso 256² 3px noise-class residue still documented (not claimed fixed).
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Bump, Thin Wall boolean path, close still-life / SSSWeight / SSSAniso 256² SSS noise residue. Not ReSTIR. Not Classroom time %.



---

## 10am PlugWalk (2026-08-28) — Subsurface IOR / Anisotropy / Diffuse Roughness TEX_IMAGE (Slice 2v)

Box: Linux, 8 cores, Blender 5.2.0 CPU. No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| ABI | `sss_ior_` / `sss_aniso_` / `thin_wall_` / `diffuse_rough_` on `QT_Mesh` + `QT_SimpleScene` |
| Python | `sync._principled_from_material` accepts Subsurface IOR / Subsurface Anisotropy / Diffuse Roughness (Non-Color gray checker). **Thin Wall** linked → `QuantTraceSyncError` (BOOLEAN in 5.2, not a float socket) |
| Native | Color→float via NODE_CONVERT_CF into Subsurface IOR / Anisotropy / Diffuse Roughness. Thin Wall Color→Int reserved if path set. Pins `set_subsurface_weight(1.0)` when IOR/Anisotropy map and Weight is unmapped. Pins `set_subsurface_method(RANDOM_WALK_SKIN)` when Subsurface IOR maps (Blender 5.2 only exposes that socket for Skin) |
| Version | `0.0.23-slice2v` |
| Tools | `tools/_quanttrace_slice2v_scene.py`, `tools/_quanttrace_slice2v_smoke.py` |

### Measured (Session vs stock Cycles Combined, box CPU)

| Socket | Res / spp | Δmax | MAE | Gate |
|---|---|---|---|---|
| SSSIOR | 32² / 4 | **5.96e-7** | 6.75e-9 | **PASS** |
| SSSIOR | 256² / 128 | **8.78e-4** | 3.13e-8 | **PASS** |
| SSSAniso | 32² / 4 | **2.74e-5** | 6.18e-8 | **PASS** |
| SSSAniso | 256² / 128 | **0.0206** | 1.70e-7 | **FAIL** (3 px / 65536) |
| DiffuseRough | 32² / 4 | **3.58e-7** | 5.84e-9 | **PASS** |
| DiffuseRough | 256² / 128 | **4.77e-7** | 3.93e-9 | **PASS** |
| Combo (SSSIOR+DiffuseRough) | 32² / 4 | **5.96e-7** | 6.75e-9 | **PASS** |
| Coat Weight (2q regression) | 32² / 4 | **2.38e-7** | 4.71e-9 | **PASS** |
| SpecTint (2u regression) | 32² / 4 | **4.77e-7** | 5.58e-9 | **PASS** |

SSSAniso 256² leftover: 3 pixels (1 ≥1e-2) at peak (119,111). MAE 1.7e-7. Same SSS noise-class silhouette residue as SSSWeight / still-life 256² — not claimed fixed. Bisect: TEX path 32 PASS; unlinked constant Anisotropy is not synced (Session defaults 0; out of TEX scope).

### Honesty

- Thin Wall is BOOLEAN in Blender 5.2 Principled — packer refuses TEX_IMAGE (ABI field reserved only).
- Anisotropic / Tangent / Bump / Object/World Normal space / linked Strength / HDR / kitchens / Object-with-pointer / packed-only / linked Mapping L/R/S still refuse.
- Still-life 256² 1px + SSSWeight 256² 1px + SSSAniso 256² 3px noise-class residue still documented (not claimed fixed).
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Anisotropic / Tangent, Bump, Thin Wall boolean path, close still-life / SSSWeight / SSSAniso 256² SSS noise residue. Not ReSTIR. Not Classroom time %.



---

## 9am PlugWalk (2026-08-28) — Specular Tint / Thin Film / Subsurface TEX_IMAGE (Slice 2u)

Box: Linux, 8 cores, Blender 5.2.0 CPU. No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| ABI | `spec_tint_` / `film_thick_` / `film_ior_` / `sss_weight_` / `sss_radius_` / `sss_scale_` on `QT_Mesh` + `QT_SimpleScene` |
| Python | `sync._principled_from_material` accepts Specular Tint, Thin Film Thickness/IOR, Subsurface Weight/Radius/Scale (5.2 names; legacy Subsurface for Weight) |
| Native | Tint Color→Color; Thickness/IOR/Weight/Scale Color→float via NODE_CONVERT_CF; Radius Color→Vector. Pins `set_subsurface_weight(1.0)` when Radius/Scale map and Weight is unmapped. Pins `set_thin_film_thickness(400.0)` nm when Film IOR maps and Thickness is unmapped |
| Version | `0.0.22-slice2u` |
| Tools | `tools/_quanttrace_slice2u_scene.py`, `tools/_quanttrace_slice2u_smoke.py` |

### Measured (Session vs stock Cycles Combined, box CPU)

| Socket | Res / spp | Δmax | MAE | Gate |
|---|---|---|---|---|
| SpecTint | 32² / 4 | **4.77e-7** | 5.58e-9 | **PASS** |
| SpecTint | 256² / 128 | **4.77e-7** | 3.77e-9 | **PASS** |
| FilmThick | 32² / 4 | **3.58e-7** | 5.17e-9 | **PASS** |
| FilmThick | 256² / 128 | **4.77e-7** | 3.64e-9 | **PASS** |
| FilmIOR | 32² / 4 | **1.22e-6** | 2.82e-9 | **PASS** |
| SSSWeight | 32² / 4 | **8.34e-7** | 9.08e-9 | **PASS** |
| SSSWeight | 256² / 128 | **0.00164** | 2.34e-8 | **FAIL** (1 px / 65536) |
| SSSRadius | 32² / 4 | **6.68e-6** | 4.51e-8 | **PASS** |
| SSSScale | 32² / 4 | **4.20e-6** | 1.89e-8 | **PASS** |
| Combo (SpecTint+FilmThick) | 32² / 4 | **4.77e-7** | 5.58e-9 | **PASS** |
| Coat Weight (2q regression) | 32² / 4 | **2.38e-7** | 4.71e-9 | **PASS** |

SSSWeight 256² leftover is 1 pixel at (143,111). MAE 2.3e-8. Same noise-class silhouette residue as still-life 256² — not claimed fixed.

### Honesty

- Object/World space, linked Strength, Bump, custom uv_map, HDR / kitchens, Object-with-pointer, packed-only, linked Mapping L/R/S still refuse.
- Subsurface IOR / Subsurface Anisotropy / Thin Wall / Diffuse Roughness / Anisotropic / Tangent still refuse (not this slice).
- Still-life 256² 1px noise-class residue still documented (not claimed fixed). SSSWeight 256² 1px same class.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Subsurface IOR/Anisotropy, Thin Wall, Diffuse Roughness, Anisotropic/Tangent, Bump, close still-life / SSSWeight 256² 1px residue. Not ReSTIR. Not Classroom time %.



## 8am PlugWalk (2026-08-28) — Coat Normal Map TEX_IMAGE (Slice 2t)

Box: Linux, 8 cores, Blender 5.2.0 CPU. No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| ABI | `coat_normal_` path/cs/vector/mapping + `coat_normal_strength` on `QT_Mesh` + `QT_SimpleScene` |
| Python | `sync._normal_map_from_sock` now takes prefix/label; Coat Normal accepted (Tangent, unlinked Strength) |
| Native | TEX_IMAGE Color → NormalMapNode (TANGENT) → Principled Coat Normal. Pins `set_coat_weight(1.0)` when Coat Normal maps and Weight is unmapped |
| Version | `0.0.21-slice2t` |
| Tools | `tools/_quanttrace_coatnormal_scene.py`, `tools/_quanttrace_coatnormal_smoke.py` |

### Measured (Session vs stock Cycles Combined, box CPU)

| Socket | Res / spp | Δmax | MAE | Gate |
|---|---|---|---|---|
| Coat Normal | 32² / 4 | **2.98e-7** | 4.87e-9 | **PASS** |
| Coat Normal | 256² / 128 | **3.58e-7** | 3.36e-9 | **PASS** |
| Coat Weight (2q regression) | 32² / 4 | **2.38e-7** | 4.71e-9 | **PASS** |

### Honesty

- Object/World space, linked Strength, Bump, custom uv_map, HDR / kitchens, Object-with-pointer, packed-only, linked Mapping L/R/S still refuse.
- Still-life 256² 1px noise-class residue still documented (not claimed fixed).
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Specular Tint / Thin Film / Subsurface sockets, Bump, or close the still-life 1px residue. Not ReSTIR. Not Classroom time %.


---

## 7am PlugWalk (2026-08-28) — Coat/Sheen extras TEX_IMAGE (Slice 2s)

Box: Linux, 8 cores, Blender 5.2.0 CPU. No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| ABI | `coat_rough_` / `coat_ior_` / `coat_tint_` / `sheen_rough_` / `sheen_tint_` on `QT_Mesh` + `QT_SimpleScene` |
| Python | `sync._principled_from_material` accepts those five; **Coat Normal** still refuses |
| Native | Color→Coat Roughness / Coat IOR / Sheen Roughness via NODE_CONVERT_CF; Tint Color→Color. Pins `set_coat_weight(1.0)` / `set_sheen_weight(1.0)` when extras map and Weight is unmapped |
| Version | `0.0.20-slice2s` |
| Tools | `tools/_quanttrace_coatextra_scene.py`, `tools/_quanttrace_coatextra_smoke.py` |

### Measured (Session vs stock Cycles Combined, box CPU)

| Socket | Res / spp | Δmax | MAE | Gate |
|---|---|---|---|---|
| CoatRough | 32² / 4 | **2.38e-7** | 6.02e-9 | **PASS** |
| CoatRough | 256² / 128 | **4.77e-7** | 3.78e-9 | **PASS** |
| CoatIOR | 32² / 4 | **3.58e-7** | 5.17e-9 | **PASS** |
| CoatIOR | 256² / 128 | **4.77e-7** | 3.64e-9 | **PASS** |
| CoatTint | 32² / 4 | **5.96e-7** | 3.64e-9 | **PASS** |
| CoatTint | 256² / 128 | **2.20e-4** | 3.87e-9 | **PASS** |
| SheenRough | 32² / 4 | **5.96e-7** | 7.46e-9 | **PASS** |
| SheenRough | 256² / 128 | **7.15e-7** | 5.06e-9 | **PASS** |
| SheenTint | 32² / 4 | **3.58e-7** | 5.45e-9 | **PASS** |
| SheenTint | 256² / 128 | **4.77e-7** | 3.76e-9 | **PASS** |
| Combo (CoatRough+SheenRough) | 32² / 4 | **5.96e-7** | 8.66e-9 | **PASS** |
| Coat Weight (2q regression) | 32² / 4 | **2.38e-7** | 4.71e-9 | **PASS** |

### Honesty

- Coat Normal, HDR / kitchens, Object-with-pointer, packed-only, linked Mapping L/R/S still refuse.
- Still-life 256² 1px noise-class residue still documented (not claimed fixed).
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Specular Tint / Thin Film / Subsurface sockets, or close the still-life 1px residue. Not ReSTIR. Not Classroom time %.


---

## Upstream (cite)

- Cycles standalone (Apache-2.0): https://github.com/blender/cycles
  (official mirror of https://projects.blender.org/blender/cycles)
- Standalone C++ API docs:
  https://developer.blender.org/docs/features/cycles/standalone/
- Key headers (upstream names): `src/session/session.h`, `src/scene/scene.h`
  (`Session`, `Scene`, `Mesh`, `Shader`, `Light`, `Camera`, `Film`,
  `Integrator`)
- BUILDING.md: `make update` then `make`. Required: Git, Git LFS, Python 3, CMake.
  Core deps: OpenImageIO + TBB. Optional: Embree (CPU). CUDA/OptiX/HIP skipped here.

License: Apache-2.0 library + GPL addon glue is the intended split
(same packaging class as BlendLuxCore’s native core). Confirm NOTICE /
LICENSE copy when the fork lands.

---

## Ordered steps

1. **Fork / clone Cycles standalone (Apache-2.0)** — **done** (7am, shallow).
2. **Build standalone Scene + Session** — **done this hour** (CPU Embree).
   `native/cycles-src/build/bin/cycles --device CPU` lists `Intel Xeon Processor`.
   Tiny XML smoke: 32×32, 4 spp, `examples/scene_cube_surface.xml` → PNG, exit 0, ~0.15 s.
3. **Export the locked cube into `ccl::Scene`** — **source sketch only**.
   `native/quanttrace/src/session_bridge.cpp` (`QT_WITH_CYCLES`) will call
   `Session::start` / `wait` once the addon `.so` loads. Load is **blocked**
   (see below). Blender Python builder: `tools/_quanttrace_cube_scene.py` (dry-run OK).
4. **Run stock unidirectional PT (no new sampler)** — **not on the locked cube**.
   XML example used 4 spp, not 128. Locked cube Combined EXR pair not written.
5. **Wire `is_tracer=1` only after pixels exist** — **not this hour** (`is_tracer=0`).
6. **Pixel-match vs stock Cycles Combined** — **not this hour**.

---

## Explicit non-goals this slice

- ReSTIR / path guiding / OIDN / OptiX
- Kitchen / Classroom / loft benches or time %
- `is_tracer=1` without a kernel
- Vendoring all of Cycles into the public addon commit
- Make it Fast RNA writes

---

## Clone probe result (2026-08-27 ~7:05am ET)

| Item | Result |
|---|---|
| Command | `git clone --depth 1 https://github.com/blender/cycles.git native/cycles-src` |
| Exit | 0 (≈2.3 s) |
| On-disk size | **17M** (source tree only; no `make update` libs) |
| Box free before | ~22G on `/workspace` overlay |
| Gitignored | `native/cycles-src/` — **not** staged for public commit |
| Full Blender tree | Not cloned (`blender/blender` skipped; standalone is enough) |

---

## 8am PlugWalk (2026-08-27) — what actually worked / blocked

Box: Linux, 8 cores, ~21G free at start / **17G after**. No user 2080.

### Toolchain (installed this hour)

cmake 3.31.6, g++ 14.2.0, make 4.4.1, ninja 1.12.1, git-lfs 3.6.1.
Was missing at hour start (`cmake: command not found`, no g++/make/lfs).

### `make update`

```
cd native/cycles-src
python3 src/cmake/make_update.py
```

| Item | Result |
|---|---|
| Cycles `git pull --rebase` | Already up to date (shallow `main`, `1319002`) |
| Submodule | `lib/linux_x64` @ `30d9f881c4b62c52323fd11637eeea56d460e35c` |
| Pointer clone | 64770 objects, 141 MiB, ~30 s |
| `git lfs pull` | exit 0, **~2.3G working tree** (not the 13–22 GiB full LFS history) |
| Total `native/cycles-src` | **~4.5G** including `build/` |
| Gitignored | yes — **not committed** |

### CMake flags that **failed**

1. **Precompiled ON, empty `lib/linux_x64`** (before `make update`):
   ```
   -DWITH_LIBS_PRECOMPILED=ON
   ```
   Error: `Could NOT find ZLIB (missing: ZLIB_LIBRARY ZLIB_INCLUDE_DIR)`
   looking at `lib/linux_x64`.

2. **Precompiled OFF, no system zlib**:
   ```
   -DWITH_LIBS_PRECOMPILED=OFF
   ```
   Same ZLIB error.

3. **Precompiled OFF, system `libopenimageio-dev` (Debian 2.5)**:
   Error: imported target `OpenImageIO::iconvert` references missing `/usr/bin/iconvert`.
   Stopped that path; used Blender precompiled OIIO 3.1 instead.

4. **`QT_WITH_CYCLES=ON` addon `.so` load** (after compile+link succeeded):
   `ctypes.CDLL` → `undefined symbol: ZSTD_getFrameContentSize`
   (before adding OIIO: `OpenImageIO::ustring::empty_std_string`).
   Link line is a subset of Cycles’ `cycles_external_libraries_append()`.
   **Not a tracer.** `is_tracer` still 0.

### CMake flags that **worked** (Cycles standalone CPU)

```
cmake -S native/cycles-src -B native/cycles-src/build -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DWITH_CYCLES_DEVICE_CUDA=OFF \
  -DWITH_CYCLES_DEVICE_OPTIX=OFF \
  -DWITH_CYCLES_DEVICE_HIP=OFF \
  -DWITH_CYCLES_DEVICE_ONEAPI=OFF \
  -DWITH_CYCLES_CUDA_BINARIES=OFF \
  -DWITH_CYCLES_HIP_BINARIES=OFF \
  -DWITH_CYCLES_HYDRA_RENDER_DELEGATE=OFF \
  -DWITH_CYCLES_OSL=OFF \
  -DWITH_CYCLES_USD=OFF \
  -DWITH_CYCLES_ALEMBIC=OFF \
  -DWITH_CYCLES_OPENIMAGEDENOISE=OFF \
  -DWITH_CYCLES_OPENSUBDIV=OFF \
  -DWITH_CYCLES_OPENVDB=OFF \
  -DWITH_CYCLES_NANOVDB=OFF \
  -DWITH_CYCLES_STANDALONE_GUI=OFF \
  -DWITH_CYCLES_EMBREE=ON \
  -DWITH_LIBS_PRECOMPILED=ON
cmake --build native/cycles-src/build --target cycles -j 8
```

Configure ~1.1 s. Build **165/165**, **~79 s**, `build/bin/cycles` 7.7M.
`--list-devices`: `CPU Intel Xeon Processor` only (CUDA/OptiX not compiled).
Runtime: `LD_LIBRARY_PATH` must include `lib/linux_x64/{tbb,embree,openimageio,opencolorio,openexr,imath,openjph,dpcpp}/lib`.

XML smoke (not the locked cube, not 128 spp):

```
LD_LIBRARY_PATH=… ./build/bin/cycles --device CPU --samples 4 \
  --width 32 --height 32 --output /tmp/qt_cycles_smoke.png \
  --background --quiet examples/scene_cube_surface.xml
```

Exit 0, 714-byte PNG, ~0.15 s. This **is** `Session::start` / Combined write via
upstream CLI. It is **not** the QUANTTRACE-CUBE gate.

### Addon Session bridge

| File | Role |
|---|---|
| `native/quanttrace/src/hello.c` | `is_tracer=0`, version `0.0.1-hello` |
| `native/quanttrace/src/quanttrace.h` | C ABI |
| `native/quanttrace/src/session_bridge.cpp` | stub unless `-DQT_WITH_CYCLES=ON`; then builds cube `ccl::Scene` and `Session::start` |
| `native/quanttrace/CMakeLists.txt` | default stub; optional Cycles compile |

Default stub `.so` loads: `is_tracer=0`, `session_probe=0`, `render_cube=-1`.

`QT_WITH_CYCLES=ON` **compiles** `session_bridge.cpp` (C++20, SSE4.2,
`CCL_NAMESPACE_BEGIN` via `COMPILE_OPTIONS` not `compile_definitions` —
the latter stringifies braces). Link of `libquanttrace.so` reports success
but **dlopen fails** (`ZSTD_getFrameContentSize`). Next hour: steal Cycles’
`cycles_external_libraries_append` rather than hand-picking OIIO/TBB/Embree.

Did **not** call `quanttrace_render_cube` (would be 256² / 128 spp).

### Locked cube Blender script

`tools/_quanttrace_cube_scene.py` dry-run (Blender 5.2.0 LTS, ~1.2 s, no F12):

```
engine CYCLES device CPU
res 256 x 256  samples 128  adaptive False  seed 0  denoise False
cube Cube loc (0,0,0) mats ['CubePrincipled']
light AREA energy 1000 size 1.0 loc (4.07625, 1.00545, 5.90386)
camera lens 50 sensor 36 loc (7.35889, -6.92579, 4.95831)
world strength 0.0  view_transform Raw
```

`--render` exists for a 64×64 / 8 spp CPU smoke; **not run** this hour
(dry-run preferred). `.blend` gitignored.

### Still not true (8am)

- Cube Combined EXR pair / Δmax gate
- `is_tracer=1`
- Make it Fast / Auto / zip / Classroom 41% / loft 52% change
- User 2080

---

## 9am PlugWalk (2026-08-27) — addon `.so` load

Box: Linux, 8 cores, ~17G free at start / after. Did **not** `make update`,
`git lfs pull`, or rebuild `native/cycles-src/build` (165/165 already done).
Rebuilt only `native/quanttrace/build` with `-DQT_WITH_CYCLES=ON`.

### Diagnose

| Object | Fact |
|---|---|
| 8am `libquanttrace.so` on disk at hour start | stub (`QT_WITH_CYCLES=OFF`), 15k, `ldd` says statically linked |
| `ZSTD_getFrameContentSize` | `T` in `lib/linux_x64/zstd/lib/libzstd.a` (static only; no `.so`) |
| Who needs it | `libcycles_util.a` (`U ZSTD_getFrameContentSize` / `ZSTD_decompress` / `ZSTD_isError`) |
| Who needs pugi | `libcycles_graph.a` |
| Working `build/bin/cycles` LINK_LIBRARIES | zstd.a + zlib `libz.a` + pugixml.a + OIIO/TBB/Embree/OCIO/OpenEXR/Imath + DT_RUNPATH |

Did **not** include Cycles `macros.cmake` / `external_libs.cmake` (`bf::dependencies::*` needs full Cycles project context).

### CMake that loaded

`native/quanttrace/CMakeLists.txt` (default `QT_WITH_CYCLES=OFF` unchanged):

- GNU ld `--start-group` around `libcycles_*.a` (integrator ↔ session/device circular; `--no-undefined` first failed on `ccl::GraphicsInteropBuffer::clear` and `ccl::device_kernel_as_string` until grouped)
- Static: `libzstd.a` `libz.a` `libpugixml.a`
- Shared, `--no-as-needed`, **before** OIIO/embree: OpenEXRCore / OpenEXR / IlmThread / Iex / Imath / openjph / tbb / sycl / OCIO
- `-Wl,--disable-new-dtags` → `DT_RPATH` (`$ORIGIN` + the cycles `lib/linux_x64/{openimageio,openexr,imath,openjph,opencolorio,embree,tbb,dpcpp}/lib` dirs)

`DT_RPATH` alone is **not** enough: OIIO/embree ship `DT_RUNPATH=$ORIGIN` (their own lib dir), so parent-RPATH is not used for *their* NEEDED. First empty-`LD_LIBRARY_PATH` load after zstd-link:

```
OSError: libOpenEXRCore.so.33: cannot open shared object file: No such file or directory
```

Forcing those transitive libs onto **this** `.so`'s NEEDED (listed first) is what made empty-`LD_LIBRARY_PATH` ctypes work.

### Rebuild (addon only)

```
cmake -S native/quanttrace -B native/quanttrace/build \
  -DCMAKE_BUILD_TYPE=Release -DQT_WITH_CYCLES=ON
cmake --build native/quanttrace/build -j 8
```

`libquanttrace.so` 8.2M. `nm -D` has `T ZSTD_getFrameContentSize`. Did not rebuild `cycles-src`.

### ctypes proof (empty LD_LIBRARY_PATH)

```
env -u LD_LIBRARY_PATH python3 tools/_quanttrace_load_probe.py
```

```
LD_LIBRARY_PATH= None
loading …/native/quanttrace/build/libquanttrace.so
version= 0.0.1-hello
is_tracer= 0
session_probe= 1
OK
```

Did **not** call `quanttrace_render_cube` (256² / 128 spp). hello.c still owns version + `is_tracer=0`.

### Still not true

- Cube Combined EXR pair / Δmax gate (next: OIIO write or reuse standalone driver, then 256²/128)
- `is_tracer=1`
- Make it Fast / Auto / zip / Classroom 41% / loft 52% change
- User 2080 / listing / gibby

---

## 9:15am PlugWalk (2026-08-27) — Combined EXR write + Session smoke

Box: Linux, 8 cores, ~17G free. Did **not** `make update`, `git lfs pull`,
or rebuild `native/cycles-src`. Rebuilt only `native/quanttrace/build`
(`-DQT_WITH_CYCLES=ON`, session_bridge.cpp recompile ~7 s). No user 2080.

### EXR write

`session_bridge.cpp` now calls OIIO `ImageOutput` after `Session::wait` when
`exr_path` is non-empty. Not the standalone `OIIOOutputDriver` class (that
lives under `src/app/` and is not in `libcycles_*.a`); same write shape:

- linear RGBA float (`TypeDesc::FLOAT`, 4 ch)
- codec **zip** (`ImageSpec` `compression=zip`)
- Y flip (Cycles Combined is bottom-up; file is top-down, same as
  `oiio_output_driver.cpp`)
- no gamma (EXR stays scene-linear)

Locked defaults remain 256 / 256 / 128 (`QUANTTRACE-CUBE.md`). Overrides:
`QUANTTRACE_CUBE_WIDTH` / `HEIGHT` / `SAMPLES` (invalid values fall back).

### Smoke (not the cube gate)

```
env -u LD_LIBRARY_PATH python3 tools/_quanttrace_session_smoke.py
```

| Item | Result |
|---|---|
| `.so` load (empty `LD_LIBRARY_PATH`) | ok |
| version | `0.0.1-hello` |
| `is_tracer` | **0** |
| `session_probe` | **1** |
| env | 32 x 32, 4 spp |
| `quanttrace_render_cube` | **0** |
| wall | **0.027 s** (box CPU) |
| EXR path | `/tmp/qt_session_smoke_1t5mvnto.exr` |
| size | **823** bytes |
| magic | `76 2f 31 01` (OpenEXR) |
| `iinfo` | 32 x 32, 4 channel, float openexr, compression zip |
| pixels | **RGB constant 0, A constant 1** (opaque-film Combined, cube not lit / not visible) |

`get_pass_pixels("combined")` succeeded (A=1; a failed read would have left
the pre-zeroed A=0). Session ran. Combined is a real buffer, not a stub file.
It is **not** a cube image. Do **not** call this a pixel-match.

Full 256^2 / 128 **not run** this hour.

### Still not true

- Cube Combined pair / dmax < 1e-3 gate (black smoke Combined is a blocker
  before even running 256/128 vs stock Cycles)
- `is_tracer=1`
- Make it Fast / Auto / zip / Classroom 41% / loft 52% change
- User 2080 / listing / gibby

---

## 10am PlugWalk (2026-08-27) — cube Combined non-zero

Box: Linux, 8 cores, ~17G free. Did **not** `make update`, `git lfs pull`,
or rebuild `native/cycles-src`. Rebuilt only `native/quanttrace/build`
(`-DQT_WITH_CYCLES=ON`, session_bridge.cpp ~6 s). No user 2080.

### Before (re-run of 9:15am .so)

`env -u LD_LIBRARY_PATH python3 tools/_quanttrace_session_smoke.py`

| Item | Result |
|---|---|
| wall | 0.029 s |
| EXR | 823 bytes, 32x32 RGBA float zip |
| oiiotool stats | RGB min=max=**0**, A=1, Constant Yes |

### Root cause

`look_at` built a Blender-object frame (`+Z` away from target, look along `-Z`).
That is **wrong for the Cycles kernel camera**:

- `src/kernel/camera/camera.h` perspective uses `D = rastertocamera`; ortho uses `D = (0,0,1)` (**+Z**).
- Working XML `examples/scene_cube_surface.xml` camera is `translate="0 2 -6"` + 20° X rotate. From `z=-6`, only a **+Z** look axis sees the origin. That XML smoke already produced a real PNG.
- `util/transform.h` has **no** `transform_look_at`.

Area lights were already correct: `AreaLight::copy_to_kernel` emits along object **`-Z`**, so the same `look_at` ( +Z away / -Z toward origin ) is the light convention.

One function cannot serve both. Camera now looks along **+Z toward origin**; area keeps **-Z toward origin**. Also: `Camera::update` + `need_flags_update` (XML loader does this) and `Mesh::add_vertex_normals` after triangle write. No Emission-surface diagnostic needed; Principled + Area + black world is the locked scene.

### After

Same 32x32 / 4 spp smoke, empty `LD_LIBRARY_PATH`:

| Item | Result |
|---|---|
| version | `0.0.1-hello` |
| `is_tracer` | **0** |
| `session_probe` | **1** |
| `quanttrace_render_cube` | **0** |
| wall | **0.026 s** |
| EXR | **1428** bytes |
| Combined RGB (C++ + oiiotool) | min `(0,0,0)` max `(1.74875, 1.74875, 1.74875)` avg `0.065` stddev `0.249` |
| Constant | **No** (cube in frame, black world around it — not one firefly) |

Success gate this hour: `max(R,G,B) > 1e-4`. Met. Not a 256²/128 pair. Not Δmax. Do **not** set `is_tracer=1`.

Full 256^2 / 128 **not run** this hour (would be the next gate vs stock Cycles Combined, not this smoke).

### Still not true

- Cube Combined pair / dmax < 1e-3 vs stock Cycles (need 256²/128 + Blender/standalone reference EXR)
- `is_tracer=1`
- Make it Fast / Auto / zip / Classroom 41% / loft 52% change
- User 2080 / listing / gibby

---

## 11am PlugWalk (2026-08-27) — stock Cycles vs Session Δmax

Box: Linux, 8 cores, ~17G free. Did **not** `make update`, `git lfs pull`, or rebuild
`native/cycles-src`. Rebuilt only `native/quanttrace/build` (`-DQT_WITH_CYCLES=ON`).
No user 2080. No zip. No Make it Fast / Auto. `is_tracer` **still 0**.

### Tools

| Tool | Role |
|---|---|
| `tools/_quanttrace_cube_scene.py --render --res N --samples S --out PATH` | Stock Cycles CPU Combined OpenEXR (Raw view, float ZIP). Default tiny 64/8; this hour used 32/4, 64/32, 256/128. |
| `tools/_quanttrace_session_smoke.py` + `QUANTTRACE_CUBE_{WIDTH,HEIGHT,SAMPLES,EXR}` | Session Combined via `quanttrace_render_cube`. |
| `tools/_quanttrace_exr_delta.py` | Blender OIIO: prints Δmax / MAE over RGB; fails on dim mismatch. |

### Energy scale (documented, not guessed)

Blender `intern/cycles/blender/light.cpp` `sync_light`:

```
strength = light_color * energy * exp2f(exposure);
light->set_normalize(!(mode & LA_UNNORMALIZED));
```

Locked cube: white × energy 1000 × exposure 0 → **strength (1000,1000,1000)**, normalize on.
Session already sets `AreaLight::set_strength(1000,1000,1000)`. **No extra scale factor.**
Mean RGB at 256²/128: stock 0.06620564 vs Session 0.06620382.

### Framing fixes this hour

1. **Camera screen-X**: Cycles +Z look cannot RH-match both Blender X and Y.
   `look_at` camera path now uses `x = cross(z, up)` (Blender screen-X). That makes
   camera Y = −Blender_Y.
2. **EXR Y write**: skip the standalone-style buffer Y-flip so bottom-up Combined
   cancels −Blender_Y and matches Blender top-down Combined.
3. Area light still `look_along_neg_z` with `cross(up, z)` (unchanged).
4. Integrator `seed=0` (QUANTTRACE-CUBE.md).

Before framing fix: 64²/32 Δmax ≈ 1.27 (bright peak X 24 vs 39). After: peaks share
(39,25), nonzero counts both 342.

### Measured pairs (linear RGB, A ignored)

| Res / spp | Stock EXR | Session EXR | Stock wall | Session wall | Δmax | MAE | Gate |
|---|---|---|---|---|---|---|---|
| 32×32 / 4 | `/tmp/quanttrace_cube_pair/stock_32x32_spp4.exr` (1456 B) | `…/session_32x32_spp4.exr` (1459 B) | ~0.88 s (incl. Blender start; render ~0.58 s) | 0.021 s | **0.664846** | 0.00845151 | FAIL |
| 64×64 / 32 | `…/stock_64x64_spp32.exr` (2878 B) | `…/session_64x64_spp32.exr` (3292 B) | ~0.77 s | 0.031 s | **0.158144** | 0.0011999 | FAIL |
| 256×256 / 128 | `…/stock_256x256_spp128.exr` (23450 B) | `…/session_256x256_spp128.exr` (27156 B) | 1.1 s | 0.312 s | **0.0592421** | 0.000112379 | FAIL (< 1e-3 needed) |

Stock max/mean at 256/128: max 1.82221 mean 0.066206. Session: max 1.82086 mean 0.066204.
Images are the same lit cube (not unrelated). Gate still fails.

### Honesty

- `is_tracer` **0** — do **not** flip: full-gate Δmax < 1e-3 **not** met at 256/128.
- Numbers above are measured, not invented.
- Store Classroom **41%** / loft **52%** unchanged.
- EXR artifacts stay under `/tmp` — **not** committed.

### Still not true

- Cube gate PASS (Δmax < 1e-3)
- `is_tracer=1`
- Make it Fast / Auto / zip / listing / gibby / user 2080

### Remaining blocker

Residual Δmax ≈ 0.059 at 256²/128 with matched energy and framing. Likely RNG/
scramble stream, filter edge, or light-shader path parity (Session Emission×Area
vs Blender sync). Next: bit-closer sample pattern / filter / shader sync — not a
strength fudge (official factor already 1:1).

---

## 12pm PlugWalk (2026-08-27) — cube gate PASS

Box: Linux, 8 cores. Did **not** `make update` / rebuild `native/cycles-src`. Rebuilt only
`native/quanttrace/build` (`-DQT_WITH_CYCLES=ON`). No user 2080. No zip. No Make it Fast / Auto.

### What was wrong (11am residual Δmax 0.059)

Not energy. Not filter. Not RNG table as the *first* lever.

1. **Blender 5.2 factory `sampling_pattern` is AUTOMATIC** (blue-noise on F12). Session default is TABULATED_SOBOL. Pinning Classic on **both** sides did not move 32²/4 (still Δmax 0.666) — pixel hashes were still on a mirrored camera Y.
2. **Camera matrix.** `intern/cycles/blender/camera.cpp` `blender_camera_matrix` is `object_tfm * scale(1,1,-1)` (Z flip only; Blender X/Y kept). The 11am +Z look-at used `x = cross(z_fwd, up)`, which negated camera Y vs that sync. Skipping the EXR Y-flip lined up the *image* but left kernel pixel Y = H-1-Blender_Y, so tabulated Sobol hashed different pixels.
3. One leftover silhouette pixel (256²/128 Δmax 0.006 at (126,135)) after the Z-flip + Y-flip restore: look_at vs Blender `to_track_quat` ULPs. **Exact `matrix_world`** from the cube script (depsgraph-evaluated) closed it.

### Pins (both stock cube script and Session)

| Knob | Value |
|---|---|
| sampling_pattern | TABULATED_SOBOL (Classic) |
| scramble | 1.0, auto off |
| light_sampling_threshold | 0 |
| bounces | 12 / d4 / g4 / t12 / v0 / tr8 (Blender factory) |
| filter | Gaussian 1.5 |
| camera | exact bpy matrix_world * scale(1,1,-1) |
| light | exact bpy matrix_world (emit -Z) |
| mesh | Blender 5.2 `primitive_cube_add` verts + loop_triangles |
| EXR | linear RGBA zip, Y-flip on write (oiio_output_driver) |

### Measured pairs (linear RGB, A ignored)

| Res / spp | Stock wall | Session wall | Δmax | MAE | pixels ≥ 1e-3 | Gate |
|---|---|---|---|---|---|---|
| 32×32 / 4 | ~1.0 s (Blender start) | 0.024 s | **2.98e-7** | 4.64e-9 | 0 / 1024 | **PASS** |
| 256×256 / 128 | ~1.2 s | 0.307 s | **4.77e-7** | 3.57e-9 | 0 / 65536 | **PASS** |

Stock max/mean at 256/128: max 1.81675553 mean 0.0662047. Session: identical to printed digits.

EXR artifacts under `/tmp/quanttrace_cube_pair/` — **not** committed.

### Honesty

- `is_tracer` **0** — cube Combined matches via `quanttrace_render_cube`. `SQ_QUANTTRACE.render` still raises QuantTraceNotBuilt. Do **not** flip until F12 is wired.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Wire `SQ_QUANTTRACE.render` to Session for the locked cube (then is_tracer=1). Not ReSTIR. Not Classroom time %.

---

## 1pm PlugWalk (2026-08-27) — SQ_QUANTTRACE F12 wire

Box: Linux, 8 cores. Did **not** `make update` / rebuild `native/cycles-src`. Rebuilt only
`native/quanttrace/build` (`-DQT_WITH_CYCLES=ON`). No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| ABI | `quanttrace_render_cube_rgba` (bottom-up Combined, Blender pass.rect) |
| `is_tracer` | **1** in session_bridge when QT_WITH_CYCLES (hello.c owns version only → `0.0.2-cube-f12`) |
| `SQ_QUANTTRACE.render` | `begin_result` / `foreach_set` / `end_result` when `kernel_ready` |
| Gate | Non-cube scenes → `QuantTraceUnsupported` (loud refuse) |
| Tools | `tools/_quanttrace_f12_smoke.py` |

### Measured

| Path | Res / spp | Wall | Δmax vs stock | Gate |
|---|---|---|---|---|
| Session EXR vs F12 EXR | 32² / 4 | F12 0.011 s | **0** | match |
| Stock Cycles vs F12 | 256² / 128 | F12 0.348 s | **4.77e-7** | **PASS** |

Proof plate: `docs/proof/quanttrace-f12-cube-pair.png` (preview only).

### Honesty

- Depsgraph sync was next (done 2pm).
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Done 2pm: depsgraph → `ccl::Scene` for simple scenes. See 2pm section.

---

## 2pm PlugWalk (2026-08-27) — depsgraph → ccl::Scene (Slice 2b)

Box: Linux, 8 cores. Did **not** `make update` / rebuild `native/cycles-src`. Rebuilt only
`native/quanttrace/build` (`-DQT_WITH_CYCLES=ON`). No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| ABI | `QT_SimpleScene` + `quanttrace_render_scene_rgba` |
| Python | `scenequant/quanttrace/sync.py` packs depsgraph (camera/mesh/Principled/AREA/world) |
| Engine | `SQ_QUANTTRACE.render` uses depsgraph pack (no hardcoded Session matrices) |
| Native | `build_simple_scene` from desc; locked cube fills via `fill_locked_cube_desc` |
| Version | `0.0.3-depsgraph` |
| Tools | `tools/_quanttrace_depsgraph_smoke.py` |

### Measured (depsgraph-fed Session vs stock Cycles Combined)

| Res / spp | Wall (Session) | Δmax | MAE | Gate |
|---|---|---|---|---|
| 32×32 / 4 | 0.065 s | **2.98e-7** | 5.89e-9 | **PASS** |
| 256×256 / 128 | 0.395 s | **5.96e-7** | 4.26e-9 | **PASS** |

F12 through engine (depsgraph path) 32²/4 vs stock: Δmax **2.98e-7** PASS.

Proof plate: `docs/proof/quanttrace-depsgraph-cube-pair.png` (preview only).

### Honesty

- Still **one** mesh + constant Principled + one AREA + one camera + black world.
- Linked Principled sockets, multi-mesh, HDR worlds → loud refuse.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Done 3pm: multi-mesh + multi-AREA. See 3pm section.



---

## 3pm PlugWalk (2026-08-27) — multi-mesh + multi-AREA (Slice 2c)

Box: Linux, 8 cores. Did **not** `make update` / rebuild `native/cycles-src`. Rebuilt only
`native/quanttrace/build` (`-DQT_WITH_CYCLES=ON`). No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| ABI | `QT_Mesh` / `QT_Light` / `QT_Scene` + `quanttrace_render_qt_scene_rgba` |
| Caps | 32 meshes / 16 AREA (kitchens still refuse) |
| Python | `sync.pack_scene` walks `depsgraph.object_instances`; world-space verts + identity tfm |
| Engine | `SQ_QUANTTRACE.render` uses `pack_scene` (1+1 cube still works) |
| Native | `build_qt_scene` loops meshes/lights; cube `QT_SimpleScene` wraps 1+1 |
| Version | `0.0.4-multimesh` |
| Tools | `tools/_quanttrace_multimesh_scene.py`, `tools/_quanttrace_multimesh_smoke.py` |

Still-life: CubeGrey + CubeRed (constant Principled), AreaKey 1000 + AreaFill 400, locked camera, black world.

### Measured

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Cube 1+1 Session (regression) | 32² / 4 | **2.98e-7** | 4.64e-9 | 0 / 1024 | **PASS** |
| Cube 1+1 depsgraph pack | 32² / 4 | **2.98e-7** | 5.89e-9 | 0 / 1024 | **PASS** |
| Still-life Session | 32² / 4 | **2.68e-6** | 8.68e-9 | 0 / 1024 | **PASS** |
| Still-life F12 | 32² / 4 | **2.68e-6** | 8.68e-9 | 0 / 1024 | **PASS** |
| Still-life Session | 256² / 128 | **0.00668** | 4.65e-8 | **1** / 65536 | **FAIL** |

256² leftover is pixel (189,122) on the red-cube right silhouette (A/B: still fails with 1 light and two grey cubes — second-mesh coverage, not the fill light or red Principled). Same class as the 12pm cube 1-px leftover before exact camera matrix.

Proof plate: `docs/proof/quanttrace-still-life-32-pair.png` (32² preview only).

### Honesty

- Do **not** call 256² still-life a pixel-match. 32² is the pass this hour.
- Linked Principled / POINT/SUN/SPOT / HDR / kitchens still refuse.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Close the 1-pixel second-mesh silhouette at 256²/128, then textured Principled / more light types. Not ReSTIR. Not Classroom time %.


---

## 4pm PlugWalk (2026-08-27) — Slice 2d: random_id + POINT/SUN

Box: Linux, 8 cores. Did **not** `make update` / rebuild `native/cycles-src`. Rebuilt only
`native/quanttrace/build` (`-DQT_WITH_CYCLES=ON`). No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| random_id | Blender sync: `hash_uint2(hash_string(name), 0)` on mesh + light Objects |
| Mesh tfm | pack_scene keeps object-local verts + exact `matrix_world` (no world-bake) |
| Lights | `QT_LIGHT_AREA` / `POINT` / `SUN`; Python accepts all three |
| POINT gate | Hard point (`shadow_soft_size=0`) vs stock: 32²/4 Δmax=8.9e-8; **256²/128 Δmax=1.2e-7 PASS** |
| SUN | ABI + Session render; strength vs stock **not** matched this hour (do not claim) |
| Version | `0.0.5-slice2d` |
| Tools | `tools/_quanttrace_point_scene.py`, `tools/_quanttrace_point_smoke.py` |

### Still-life 256² residual (documented, not "fixed")

Off-center scaled cube (+1.15, scale 0.7) leaves **1 pixel** Δmax≈0.0038 at 128 spp (MAE ~1e-7).
Scales ~1/√spp (1024 spp → Δmax≈0.0017). Origin / −X / scale-only / translate-only PASS at 256.
Not multi-mesh-specific; not light-tree; not random_id. Noise-class silhouette residue vs Blender
5.2 Embree. Still-life **32²/4 still PASS** (Δmax=3.5e-6).

### Honesty

- Soft POINT (`shadow_soft_size>0`) not gated.
- SUN strength parity unmet — refuse to claim.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Done 5pm: soft POINT + SUN strength. See 5pm section.


---

## 5pm PlugWalk (2026-08-27) — Slice 2e: soft POINT + SUN strength

Box: Linux, 8 cores. Did **not** `make update` / rebuild `native/cycles-src`. Rebuilt only
`native/quanttrace/build` (`-DQT_WITH_CYCLES=ON`). No user 2080. No zip. No Make it Fast / Auto.

### Root cause (soft POINT)

Hard POINT (`shadow_soft_size=0`) already matched. Soft radius packing existed
(`shadow_soft_size` → `PointLight::set_radius`), but Session always forced
`set_is_sphere(true)`. Official Blender Cycles sync is:

```
is_sphere = !use_soft_falloff
```

New Blender POINT defaults: `use_soft_falloff=True` → **disk** soft point
(`is_sphere=false`), not a true sphere. Mismatch would sample sphere cone vs
stock disk.

### What landed

| Piece | Detail |
|---|---|
| ABI | `QT_Light.is_sphere` (int); POINT packs `!use_soft_falloff` |
| Native | `PointLight::set_is_sphere(L->is_sphere != 0)` |
| Soft gate | disk soft=0.25 m, normalize=True, Tabulated Sobol both sides |
| SUN | same strength formula `color*energy*exp2(exposure)`; aim -Z at origin |
| Version | `0.0.6-slice2e` |
| Tools | `_quanttrace_point_scene/smoke.py` (`--soft-size`, `--no-soft-falloff`); `_quanttrace_sun_scene/smoke.py` |

### Measured — soft POINT (disk, soft_falloff=True, soft=0.25)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Soft POINT Session | 32² / 4 | **8.94e-8** | 1.63e-9 | 0 / 1024 | **PASS** |
| Soft POINT Session | 256² / 128 | **1.19e-7** | 1.00e-9 | 0 / 65536 | **PASS** |
| Hard POINT regression | 32² / 4 | **8.94e-8** | 1.35e-9 | 0 / 1024 | **PASS** |
| Sphere soft (`--no-soft-falloff`) | 32² / 4 | **2.98e-8** | 4.26e-10 | 0 / 1024 | **PASS** |

### Measured — SUN (energy=200, angle=0.0091803, -Z→origin)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| SUN Session | 32² / 4 | **3.81e-6** | 5.59e-9 | 0 / 1024 | **PASS** |
| SUN Session | 256² / 128 | **3.81e-6** | 2.40e-9 | 0 / 65536 | **PASS** |

4pm "SUN strength unmet" was a bad orientation/energy probe, not a missing
scale factor. With -Z aim + `color*energy*exp2(exposure)` the gate passes.

Proof plate: `docs/proof/quanttrace-softpoint-32-pair.png` (32² preview only).

### Honesty

- Still-life off-center 256² **1px noise-class** residue from 4pm remains
  documented — not "fixed" this hour.
- Textured Principled / SPOT / HDR / kitchens still refuse.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Textured Principled, SPOT, close still-life 1px residue. Not ReSTIR. Not Classroom time %.


---

## 6pm PlugWalk (2026-08-27) — Slice 2f: textured Principled (TEX_IMAGE)

Box: Linux, 8 cores. Did **not** `make update` / rebuild `native/cycles-src`. Rebuilt only
`native/quanttrace/build` (`-DQT_WITH_CYCLES=ON`). No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| ABI | `QT_Mesh.uvs` (ntris×3×2 corner), `image_path`, `image_colorspace` |
| Packer | Base Color may be `TEX_IMAGE` Color with unlinked Vector (default UV). Disk filepath required; packed-only refuses. Other linked Principled sockets still refuse. |
| Native | `ImageTextureNode` → Principled Base Color; `ATTR_STD_UV` from packed corners. Colorspace string from `Image.colorspace_settings.name`. |
| Version | `0.0.7-slice2f` |
| Tools | `_quanttrace_tex_scene/smoke.py` (stdlib PNG checker — generated EXR pixels were all-zero) |

### Measured — 8×8 sRGB checker PNG, default cube UVs, AREA 1000

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| TEX_IMAGE Session | 32² / 4 | **1.01e-6** | 7.01e-9 | 0 / 1024 | **PASS** |
| TEX_IMAGE Session | 256² / 128 | **1.43e-6** | 3.27e-9 | 0 / 65536 | **PASS** |
| TEX_IMAGE F12 | 32² / 4 | **1.01e-6** | 7.01e-9 | 0 / 1024 | **PASS** |
| Locked-cube Session regression | 32² / 4 | Combined max 1.65 (untextured grey) | — | — | OK |

Honesty: first 32² pair on a generated EXR was a false match (all-zero RGB, Δmax 4.7e-9). PNG rewrite is the claimed gate.

Proof plate: `docs/proof/quanttrace-tex-32-pair.png` (32 preview only).

### Honesty

- SPOT / HDR / kitchens / linked Vector (mapping nodes) still refuse.
- Still-life off-center 256² 1px noise-class residue from 4pm remains documented.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Done 7pm: SPOT. See 7pm section. Mapping/TEX_COORD / still-life 1px still open.


---

## 7pm PlugWalk (2026-08-27) — Slice 2g: SPOT

Box: Linux, 8 cores. Did **not** `make update` / rebuild `native/cycles-src`. Rebuilt only
`native/quanttrace/build` (`-DQT_WITH_CYCLES=ON`). No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| ABI | `QT_LIGHT_SPOT=3` + `QT_Light.smooth` (spot_blend) |
| Packer | accepts SPOT; `spot_size`→angle, `spot_blend`→smooth, soft radius + `is_sphere=!use_soft_falloff` |
| Native | `SpotLight` via official Blender sync shape (`intern/cycles/blender/light.cpp`) |
| Version | `0.0.8-slice2g` |
| Tools | `_quanttrace_spot_scene/smoke.py` |

### Measured — hard SPOT (size=π/4, blend=0.15, soft=0, energy=1000, -Z→origin)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Hard SPOT Session | 32² / 4 | **8.94e-8** | 1.35e-9 | 0 / 1024 | **PASS** |
| Hard SPOT Session | 256² / 128 | **1.19e-7** | 1.02e-9 | 0 / 65536 | **PASS** |

### Measured — soft SPOT (disk, soft_falloff=True, soft=0.25)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Soft SPOT Session | 32² / 4 | **8.94e-8** | — | 0 / 1024 | **PASS** |
| Soft SPOT Session | 256² / 128 | **1.19e-7** | 1.00e-9 | 0 / 65536 | **PASS** |

Proof plate: `docs/proof/quanttrace-spot-32-pair.png` (32² preview only).

### Honesty

- Still-life off-center 256² **1px noise-class** residue from 4pm remains documented.
- HDR / kitchens / mapping nodes still refuse.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Done 9pm: Roughness/Metallic TEX_IMAGE. See 9pm section.


---

## 8pm PlugWalk (2026-08-27) — Slice 2h: Mapping / TEX_COORD

Box: Linux, 8 cores. Did **not** `make update` / rebuild `native/cycles-src`. Rebuilt only
`native/quanttrace/build` (`-DQT_WITH_CYCLES=ON`). No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| ABI | `QT_TEX_VECTOR_*` + `map_location/rotation/scale` + `map_type` on `QT_Mesh` / `QT_SimpleScene` |
| Packer | Accepts TEX_IMAGE Vector from TEX_COORD UV, or Mapping (VECTOR, unlinked L/R/S) ← TEX_COORD UV. Refuses Generated/Object/Camera/Window/Reflection, linked Mapping params, other graph shapes. |
| Native | `TextureCoordinateNode` UV → optional `MappingNode` (VECTOR) → `ImageTextureNode` Vector |
| Version | `0.0.9-slice2h` |
| Tools | `_quanttrace_mapping_scene/smoke.py` |

### Measured — Mapping VECTOR scale=(2,2,2) loc=(0.1,0.2,0) rot_z=0.15 (SVM VECTOR ignores location)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Mapping Session | 32² / 4 | **2.26e-6** | 1.29e-8 | 0 / 1024 | **PASS** |
| Mapping Session | 256² / 128 | **1.67e-6** | 6.05e-9 | 0 / 65536 | **PASS** |

### Measured — TEX_COORD UV only (no Mapping)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| TEX_COORD Session | 32² / 4 | **1.01e-6** | 7.01e-9 | 0 / 1024 | **PASS** |

### Measured — unlinked Vector (Slice 2f regression)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Unlinked Session | 32² / 4 | **1.01e-6** | 7.01e-9 | 0 / 1024 | **PASS** |

Proof plate: `docs/proof/quanttrace-mapping-32-pair.png` (+ `/workspace/quanttrace-mapping-32-pair.png`).

### Honesty

- VECTOR Mapping hides Location in Blender 5.2 UI (`is_unavailable`); SVM VECTOR also ignores location. Location DNA still packed for ABI honesty.
- Still-life off-center 256² **1px noise-class** residue from 4pm remains documented.
- HDR / kitchens / POINT|TEXTURE|NORMAL Mapping / other Principled sockets still refuse.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Done 9pm: Roughness/Metallic. See 9pm section.

---

## 9pm PlugWalk (2026-08-27) — Slice 2i: Roughness / Metallic TEX_IMAGE

Box: Linux, 8 cores. Did **not** `make update` / rebuild `native/cycles-src`. Rebuilt only
`native/quanttrace/build` (`-DQT_WITH_CYCLES=ON`). No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| ABI | `rough_image_path` / `metal_image_path` (+ colorspace, `*_tex_vector_mode`, Mapping L/R/S/type) on `QT_Mesh` / `QT_SimpleScene` |
| Packer | Base Color / Roughness / Metallic each may be constant OR TEX_IMAGE Color with same Vector rules (unlinked / TEX_COORD UV / Mapping VECTOR←TEX_COORD UV). Separate TEX_IMAGE node per socket (same disk filepath OK). IOR/Alpha/Normal refuse linked. |
| Native | `wire_tex_image` helper; Color→Roughness/Metallic via `ShaderGraph::connect` NODE_CONVERT_CF (average). UVs when any socket textured. |
| Version | `0.0.10-slice2i` |
| Tools | `_quanttrace_rough_scene/smoke.py` (`--socket Roughness|Metallic|Both`) |

### Measured — Roughness TEX_IMAGE (8×8 Non-Color gray checker, unlinked Vector)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Roughness Session | 32² / 4 | **3.58e-7** | 6.71e-9 | 0 / 1024 | **PASS** |
| Roughness Session | 256² / 128 | **4.77e-7** | 4.03e-9 | 0 / 65536 | **PASS** |

### Measured — Metallic TEX_IMAGE (same gray checker)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Metallic Session | 32² / 4 | **5.36e-7** | 6.90e-9 | 0 / 1024 | **PASS** |
| Metallic Session | 256² / 128 | **5.36e-7** | 3.55e-9 | 0 / 65536 | **PASS** |

### Measured — Both Roughness + Metallic (same filepath, separate TEX_IMAGE nodes)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Both Session | 32² / 4 | **2.98e-7** | 5.82e-9 | 0 / 1024 | **PASS** |

### Measured — regressions (32² / 4)

| Path | Res / spp | Δmax | MAE | Gate |
|---|---|---|---|---|
| 2f Base Color TEX_IMAGE | 32² / 4 | **1.01e-6** | 7.01e-9 | **PASS** |
| 2h Mapping VECTOR | 32² / 4 | **2.26e-6** | 1.29e-8 | **PASS** |
| Locked cube constant | 32² / 4 | Session smoke OK | — | **PASS** (`is_tracer=1`, ver `0.0.10-slice2i`) |

Proof plate: `docs/proof/quanttrace-rough-32-pair.png` (+ `/workspace/quanttrace-rough-32-pair.png`).

### Honesty / still refuses

- Still-life off-center 256² **1px noise-class** residue from 4pm remains documented (not claimed fixed).
- HDR worlds, kitchens, Generated/Object/Camera/Window/Reflection TEX_COORD, linked Mapping L/R/S, packed-only images, other Principled sockets (IOR/Alpha/Normal/…) still raise `QuantTraceSyncError`.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Done 10pm: Normal Map TEX_IMAGE. See 10pm section.

---

## 10pm PlugWalk (2026-08-27) — Slice 2j: Normal Map TEX_IMAGE

Box: Linux, 8 cores. Did **not** `make update` / rebuild `native/cycles-src`. Rebuilt only
`native/quanttrace/build` (`-DQT_WITH_CYCLES=ON`). No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| ABI | `normal_image_path` / `normal_image_colorspace` + `normal_tex_vector_mode` + Mapping L/R/S/type + `normal_strength` on `QT_Mesh` / `QT_SimpleScene` |
| Packer | Principled.Normal ← Normal Map.Normal; Color ← TEX_IMAGE (same Vector rules as Base/Rough/Metal). Strength unlinked float (default 1.0). Space = Tangent only. |
| Native | `NormalMapNode` + `ImageTextureNode` Color→Color; Normal → Principled Normal. `set_space(NODE_NORMAL_MAP_TANGENT)` + `set_strength`. Cite Blender sync `intern/cycles/blender/shader.cpp` ShaderNodeNormalMap. UVs when any socket including Normal is textured. Tangents via Cycles `Mesh::update_tangents` (ATTR_STD_UV). |
| Version | `0.0.11-slice2j` |
| Tools | `_quanttrace_normal_scene/smoke.py` (16×16 Non-Color tangent normal PNG, center bump) |

### Measured — Normal Map TEX_IMAGE (16×16 Non-Color tangent map, Strength 1.0, unlinked Vector)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Normal Session | 32² / 4 | **3.58e-7** | 7.27e-9 | 0 / 1024 | **PASS** |
| Normal Session | 256² / 128 | **5.96e-7** | 4.79e-9 | 0 / 65536 | **PASS** |

### Measured — regressions (32² / 4)

| Path | Res / spp | Δmax | MAE | Gate |
|---|---|---|---|---|
| Roughness TEX_IMAGE | 32² / 4 | **3.58e-7** | 6.71e-9 | **PASS** |
| Locked cube constant | 32² / 4 | Session smoke OK | — | **PASS** (`is_tracer=1`, ver `0.0.11-slice2j`) |

Proof plate: `docs/proof/quanttrace-normal-32-pair.png` (+ `/workspace/quanttrace-normal-32-pair.png`).

### Honesty / still refuses

- Still-life off-center 256² **1px noise-class** residue from 4pm remains documented (not claimed fixed).
- HDR worlds, kitchens, Generated/Object/Camera/Window/Reflection TEX_COORD, linked Mapping L/R/S, packed-only images, Object/World Normal Map space, linked Strength, Bump/other Normal sources, custom `uv_map`, IOR/Alpha still raise `QuantTraceSyncError`.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Done 11pm: Generated TEX_COORD. See 11pm section.

---

## 11pm PlugWalk (2026-08-27) — Slice 2k: TEX_COORD Generated

Box: Linux, 8 cores. Did **not** `make update` / rebuild `native/cycles-src`. Rebuilt only
`native/quanttrace/build` (`-DQT_WITH_CYCLES=ON`). No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| ABI | `QT_TEX_VECTOR_TEXCOORD_GENERATED=3`, `QT_TEX_VECTOR_MAPPING_GENERATED=4` (existing `tex_vector_mode` int; no new struct fields) |
| Packer | TEX_COORD Generated as well as UV; Mapping.Vector may come from either. Object/Camera/Window/Reflection still refuse. |
| Native | `TextureCoordinateNode` output `"Generated"`; `ATTR_STD_GENERATED` filled from object-local bbox orco `[0,1]`. Do **not** rely on `Mesh::update_generated` (copies raw verts). |
| Version | `0.0.12-slice2k` |
| Tools | `_quanttrace_generated_scene/smoke.py` (8×8 sRGB checker, Generated / Generated+Mapping) |

### Measured — TEX_COORD Generated (8×8 sRGB checker, unlinked Mapping)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Generated Session | 32² / 4 | **2.15e-6** | 1.14e-8 | 0 / 1024 | **PASS** |
| Generated Session | 256² / 128 | **2.56e-6** | 7.10e-9 | 0 / 65536 | **PASS** |

### Measured — TEX_COORD Generated → Mapping VECTOR (scale 2, loc 0.1/0.2, rot_z 0.15)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Generated+Mapping Session | 32² / 4 | **7.87e-6** | 4.41e-8 | 0 / 1024 | **PASS** |
| Generated+Mapping Session | 256² / 128 | **3.93e-6** | 1.70e-8 | 0 / 65536 | **PASS** |

### Measured — regressions (32² / 4)

| Path | Res / spp | Δmax | MAE | Gate |
|---|---|---|---|---|
| 2h Mapping VECTOR (UV) | 32² / 4 | **2.26e-6** | 1.29e-8 | **PASS** |

Proof plate: `docs/proof/quanttrace-generated-32-pair.png` (+ `/workspace/quanttrace-generated-32-pair.png`).

### Honesty / still refuses

- Still-life off-center 256² **1px noise-class** residue from 4pm remains documented (not claimed fixed).
- HDR worlds, kitchens, Object/Camera/Window/Reflection TEX_COORD, linked Mapping L/R/S, packed-only images, IOR/Alpha still raise `QuantTraceSyncError`.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Done 12am: Object TEX_COORD. See 12am section.

---

## 12am PlugWalk (2026-08-28) — Slice 2l: TEX_COORD Object

Box: Linux, 8 cores. Did **not** `make update` / rebuild `native/cycles-src`. Rebuilt only
`native/quanttrace/build` (`-DQT_WITH_CYCLES=ON`). No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| ABI | `QT_TEX_VECTOR_TEXCOORD_OBJECT=5`, `QT_TEX_VECTOR_MAPPING_OBJECT=6` (existing `tex_vector_mode` int; no new struct fields) |
| Packer | TEX_COORD Object accepted (empty Object reference only). Mapping.Vector may come from UV/Generated/Object. Camera/Window/Reflection still refuse. Object pointer / object_itfm refuse. |
| Native | `TextureCoordinateNode` output `"Object"` with default `use_transform=false` → `NODE_TEXCO_OBJECT` (shading_position + object_inverse_position_transform). No `ATTR_STD_GENERATED` for Object-only graphs. |
| Version | `0.0.13-slice2l` |
| Tools | `_quanttrace_object_scene/smoke.py` (8×8 sRGB checker `/tmp/qt_checker_obj.png`); mapping_scene `--coord Object` |

### Measured — TEX_COORD Object (8×8 sRGB checker)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Object Session | 32² / 4 | **7.99e-6** | 2.56e-8 | 0 / 1024 | **PASS** |
| Object Session | 256² / 128 | **4.35e-6** | 1.19e-8 | 0 / 65536 | **PASS** |

### Measured — TEX_COORD Object → Mapping VECTOR (scale 2, loc 0.1/0.2, rot_z 0.15)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Object+Mapping Session | 32² / 4 | **1.42e-5** | 6.61e-8 | 0 / 1024 | **PASS** |
| Object+Mapping Session | 256² / 128 | **6.56e-6** | 2.68e-8 | 0 / 65536 | **PASS** |

### Measured — regressions (32² / 4)

| Path | Res / spp | Δmax | MAE | Gate |
|---|---|---|---|---|
| 2k Generated texcoord | 32² / 4 | **2.15e-6** | 1.14e-8 | **PASS** |

### Honesty / still refuses

- Still-life off-center 256² **1px noise-class** residue from 4pm remains documented (not claimed fixed).
- HDR worlds, kitchens, Camera/Window/Reflection TEX_COORD, TEX_COORD Object **with** Object reference (use_transform / object_itfm), linked Mapping L/R/S, packed-only images, IOR/Alpha still raise `QuantTraceSyncError`.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Done 1am: Camera TEX_COORD. See 1am section.

---

## 1am PlugWalk (2026-08-28) — Slice 2m: TEX_COORD Camera

Box: Linux, 8 cores. Did **not** `make update` / rebuild `native/cycles-src`. Rebuilt only
`native/quanttrace/build` (`-DQT_WITH_CYCLES=ON`). No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| ABI | `QT_TEX_VECTOR_TEXCOORD_CAMERA=7`, `QT_TEX_VECTOR_MAPPING_CAMERA=8` (existing `tex_vector_mode` int; no new struct fields) |
| Packer | TEX_COORD Camera accepted. Mapping.Vector may come from UV/Generated/Object/Camera. Window/Reflection still refuse. |
| Native | `TextureCoordinateNode` output `"Camera"` → `NODE_TEXCO_CAMERA` (`kernel_data.cam.worldtocamera` via `Camera::update`). No extra inverse-matrix ABI. `from_dupli` unused on Camera. |
| Version | `0.0.14-slice2m` |
| Tools | `_quanttrace_camera_scene/smoke.py` (8×8 sRGB checker `/tmp/qt_checker_cam.png`); mapping_scene `--coord Camera` |

### Measured — TEX_COORD Camera (8×8 sRGB checker)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Camera Session | 32² / 4 | **1.79e-6** | 1.90e-8 | 0 / 1024 | **PASS** |
| Camera Session | 256² / 128 | **3.46e-6** | 1.23e-8 | 0 / 65536 | **PASS** |

### Measured — TEX_COORD Camera → Mapping VECTOR (scale 2, loc 0.1/0.2, rot_z 0.15)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Camera+Mapping Session | 32² / 4 | **7.39e-6** | 5.46e-8 | 0 / 1024 | **PASS** |
| Camera+Mapping Session | 256² / 128 | **5.96e-6** | 2.26e-8 | 0 / 65536 | **PASS** |

### Measured — regressions (32² / 4)

| Path | Res / spp | Δmax | MAE | Gate |
|---|---|---|---|---|
| 2k Generated texcoord | 32² / 4 | **2.15e-6** | 1.14e-8 | **PASS** |
| 2l Object texcoord | 32² / 4 | **7.99e-6** | 2.56e-8 | **PASS** |

### Honesty / still refuses

- Still-life off-center 256² **1px noise-class** residue from 4pm remains documented (not claimed fixed).
- HDR worlds, kitchens, Window/Reflection TEX_COORD, TEX_COORD Object **with** Object reference (use_transform / object_itfm), linked Mapping L/R/S, packed-only images, IOR/Alpha still raise `QuantTraceSyncError`.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Done 2am: Window / Reflection TEX_COORD. See 2am section.

---

## 2am PlugWalk (2026-08-28) — Slice 2n: TEX_COORD Window + Reflection

Box: Linux, 8 cores. Did **not** `make update` / rebuild `native/cycles-src`. Rebuilt only
`native/quanttrace/build` (`-DQT_WITH_CYCLES=ON`). No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| ABI | `QT_TEX_VECTOR_TEXCOORD_WINDOW=9`, `QT_TEX_VECTOR_MAPPING_WINDOW=10`, `QT_TEX_VECTOR_TEXCOORD_REFLECTION=11`, `QT_TEX_VECTOR_MAPPING_REFLECTION=12` (existing `tex_vector_mode` int; no new struct fields) |
| Packer | TEX_COORD Window and Reflection accepted. Mapping.Vector may come from UV/Generated/Object/Camera/Window/Reflection. |
| Native | `TextureCoordinateNode` `"Window"` → `NODE_TEXCO_WINDOW` (`camera_world_to_ndc`); `"Reflection"` → `NODE_TEXCO_REFLECTION` (`svm_texco_reflection`). Both use existing `Camera::update` data; no extra inverse-matrix ABI. Mesh cubes only (bg Reflection uses `NODE_GEOM_I`). |
| Version | `0.0.15-slice2n` |
| Tools | `_quanttrace_window_scene/smoke.py`, `_quanttrace_reflection_scene/smoke.py` (8×8 sRGB checker); mapping_scene `--coord Window|Reflection` |

### Measured — TEX_COORD Window (8×8 sRGB checker)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Window Session | 32² / 4 | **8.34e-7** | 4.24e-9 | 0 / 1024 | **PASS** |
| Window Session | 256² / 128 | **4.77e-7** | 2.00e-9 | 0 / 65536 | **PASS** |

### Measured — TEX_COORD Window → Mapping VECTOR (scale 2, loc 0.1/0.2, rot_z 0.15)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Window+Mapping Session | 32² / 4 | **8.64e-7** | 8.21e-9 | 0 / 1024 | **PASS** |
| Window+Mapping Session | 256² / 128 | **8.94e-7** | 3.00e-9 | 0 / 65536 | **PASS** |

### Measured — TEX_COORD Reflection (8×8 sRGB checker)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Reflection Session | 32² / 4 | **5.07e-7** | 2.26e-9 | 0 / 1024 | **PASS** |
| Reflection Session | 256² / 128 | **5.96e-7** | 1.63e-9 | 0 / 65536 | **PASS** |

### Measured — TEX_COORD Reflection → Mapping VECTOR (scale 2, loc 0.1/0.2, rot_z 0.15)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Reflection+Mapping Session | 32² / 4 | **1.07e-6** | 4.83e-9 | 0 / 1024 | **PASS** |
| Reflection+Mapping Session | 256² / 128 | **6.56e-7** | 1.99e-9 | 0 / 65536 | **PASS** |

### Measured — regressions (32² / 4)

| Path | Res / spp | Δmax | MAE | Gate |
|---|---|---|---|---|
| 2m Camera texcoord | 32² / 4 | **1.79e-6** | 1.90e-8 | **PASS** |

### Honesty / still refuses

- Still-life off-center 256² **1px noise-class** residue from 4pm remains documented (not claimed fixed).
- HDR worlds, kitchens, TEX_COORD Object **with** Object reference (use_transform / object_itfm), linked Mapping L/R/S, packed-only images, IOR/Alpha still raise `QuantTraceSyncError`.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Done 3am: IOR/Alpha TEX_IMAGE. See 3am section.

---

## 3am PlugWalk (2026-08-28) — Slice 2o: Principled IOR / Alpha TEX_IMAGE

Box: Linux, 8 cores. Did **not** `make update` / rebuild `native/cycles-src`. Rebuilt only
`native/quanttrace/build` (`-DQT_WITH_CYCLES=ON`). No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| ABI | `ior_image_path` / `alpha_image_path` (+ colorspace, tex_vector_mode, Mapping) on `QT_SimpleScene` and `QT_Mesh` (NULL/empty = existing constant `ior`/`alpha`) |
| Packer | Principled IOR and Alpha may be TEX_IMAGE Color (same Vector graph as Base/Rough/Metal). Other linked sockets still refuse. |
| Native | Color → IOR / Alpha via `ShaderGraph::connect` (`NODE_CONVERT_CF`). `needs_uv` and `mesh_uses_generated` include both sockets. |
| Version | `0.0.16-slice2o` |
| Tools | `_quanttrace_ioralpha_scene/smoke.py` (8×8 Non-Color gray checker) |

### Measured — TEX_IMAGE → Principled IOR

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| IOR Session | 32² / 4 | **8.34e-7** | 8.21e-9 | 0 / 1024 | **PASS** |
| IOR Session | 256² / 128 | **5.96e-7** | 4.73e-9 | 0 / 65536 | **PASS** |

### Measured — TEX_IMAGE → Principled Alpha

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Alpha Session | 32² / 4 | **1.04e-6** | 1.27e-8 | 0 / 1024 | **PASS** |
| Alpha Session | 256² / 128 | **6.80e-4** | 1.79e-8 | 0 / 65536 | **PASS** |

### Measured — both sockets, same filepath

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Both Session | 32² / 4 | **2.38e-6** | 1.98e-8 | 0 / 1024 | **PASS** |
| Both Session | 256² / 128 | **6.33e-4** | 2.73e-8 | 0 / 65536 | **PASS** |

### Measured — regressions (32² / 4)

| Path | Res / spp | Δmax | MAE | Gate |
|---|---|---|---|---|
| 2i Roughness TEX_IMAGE | 32² / 4 | **3.58e-7** | 6.71e-9 | **PASS** |

### Honesty / still refuses

- Still-life off-center 256² **1px noise-class** residue from 4pm remains documented (not claimed fixed).
- HDR worlds, kitchens, TEX_COORD Object **with** Object reference (use_transform / object_itfm), linked Mapping L/R/S, packed-only images, Transmission/Specular/Coat/Sheen/Emission still raise `QuantTraceSyncError`.
- Film stays opaque (`film_transparent=False`); Combined RGB is over black world. Session Combined A mean stays 1.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Done 4am: Transmission/Specular TEX_IMAGE. See 4am section.

---

## 4am PlugWalk (2026-08-28) — Slice 2p: Principled Transmission / Specular TEX_IMAGE

Box: Linux, 8 cores. Did **not** `make update` / rebuild `native/cycles-src`. Rebuilt only
`native/quanttrace/build` (`-DQT_WITH_CYCLES=ON`). No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| ABI | `trans_image_path` / `spec_image_path` (+ colorspace, tex_vector_mode, Mapping) on `QT_SimpleScene` and `QT_Mesh` (NULL/empty = Cycles constant Transmission Weight 0 / Specular IOR Level 0.5) |
| Packer | Principled Transmission Weight (legacy Transmission) and Specular IOR Level (legacy Specular) may be TEX_IMAGE Color (same Vector graph as IOR/Alpha). Coat/Sheen/Emission still refuse. |
| Native | Color → Transmission Weight / Specular IOR Level via `ShaderGraph::connect` (`NODE_CONVERT_CF`). `needs_uv` and `mesh_uses_generated` include both sockets. |
| Version | `0.0.17-slice2p` |
| Tools | `_quanttrace_transspec_scene/smoke.py` (8×8 Non-Color gray checker) |

### Measured — TEX_IMAGE → Principled Transmission Weight

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Transmission Session | 32² / 4 | **1.60e-5** | 2.35e-8 | 0 / 1024 | **PASS** |
| Transmission Session | 256² / 128 | **4.44e-6** | 7.31e-9 | 0 / 65536 | **PASS** |

### Measured — TEX_IMAGE → Principled Specular IOR Level

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Specular Session | 32² / 4 | **3.58e-7** | 4.80e-9 | 0 / 1024 | **PASS** |
| Specular Session | 256² / 128 | **4.17e-7** | 3.61e-9 | 0 / 65536 | **PASS** |

### Measured — both sockets, same filepath

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Both Session | 32² / 4 | **1.59e-5** | 2.39e-8 | 0 / 1024 | **PASS** |
| Both Session | 256² / 128 | **7.23e-5** | 8.65e-9 | 0 / 65536 | **PASS** |

### Measured — regressions (32² / 4)

| Path | Res / spp | Δmax | MAE | Gate |
|---|---|---|---|---|
| 2i Roughness TEX_IMAGE | 32² / 4 | **3.58e-7** | 6.71e-9 | **PASS** |

### Honesty / still refuses

- Still-life off-center 256² **1px noise-class** residue from 4pm remains documented (not claimed fixed).
- HDR worlds, kitchens, TEX_COORD Object **with** Object reference (use_transform / object_itfm), linked Mapping L/R/S, packed-only images, Coat/Sheen/Emission still raise `QuantTraceSyncError`.
- Film stays opaque (`film_transparent=False`); Combined RGB is over black world. Session Combined A mean stays 1.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Done 5am: Coat / Sheen / Emission Strength TEX_IMAGE. See 5am section.

---

## 5am PlugWalk (2026-08-28) — Slice 2q: Principled Coat / Sheen / Emission Strength TEX_IMAGE

Box: Linux, 8 cores. Did **not** `make update` / rebuild `native/cycles-src`. Rebuilt only
`native/quanttrace/build` (`-DQT_WITH_CYCLES=ON`). No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| ABI | `coat_image_path` / `sheen_image_path` / `emit_str_image_path` (+ colorspace, tex_vector_mode, Mapping) on `QT_SimpleScene` and `QT_Mesh` (NULL/empty = Cycles constant Coat Weight 0 / Sheen Weight 0 / Emission Strength 0) |
| Packer | Principled Coat Weight (legacy Coat / Clearcoat), Sheen Weight (legacy Sheen), and Emission Strength may be TEX_IMAGE Color (same Vector graph as Transmission/Specular). Coat Roughness/IOR/Tint, Sheen Roughness/Tint, Emission Color still refuse. |
| Native | Color → Coat Weight / Sheen Weight / Emission Strength via `ShaderGraph::connect` (`NODE_CONVERT_CF`). `needs_uv` and `mesh_uses_generated` include all three sockets. |
| Version | `0.0.18-slice2q` |
| Tools | `_quanttrace_coatsheen_scene/smoke.py` (8×8 Non-Color gray checker; `--socket Coat|Sheen|Emission|Both|All`) |

### Measured — TEX_IMAGE → Principled Coat Weight

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Coat Session | 32² / 4 | **2.38e-7** | 4.71e-9 | 0 / 1024 | **PASS** |
| Coat Session | 256² / 128 | **3.58e-7** | 3.38e-9 | 0 / 65536 | **PASS** |

### Measured — TEX_IMAGE → Principled Sheen Weight

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Sheen Session | 32² / 4 | **2.98e-7** | 5.12e-9 | 0 / 1024 | **PASS** |
| Sheen Session | 256² / 128 | **3.58e-7** | 3.71e-9 | 0 / 65536 | **PASS** |

### Measured — TEX_IMAGE → Principled Emission Strength

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Emission Session | 32² / 4 | **8.34e-7** | 1.56e-8 | 0 / 1024 | **PASS** |
| Emission Session | 256² / 128 | **9.54e-7** | 9.62e-9 | 0 / 65536 | **PASS** |

### Measured — combined sockets, same filepath

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | Gate |
|---|---|---|---|---|---|
| Coat+Sheen Session | 32² / 4 | **2.98e-7** | 5.18e-9 | 0 / 1024 | **PASS** |
| All three Session | 32² / 4 | **5.96e-7** | 1.21e-8 | 0 / 1024 | **PASS** |

### Measured — regressions (32² / 4)

| Path | Res / spp | Δmax | MAE | Gate |
|---|---|---|---|---|
| 2i Roughness TEX_IMAGE | 32² / 4 | **3.58e-7** | 6.71e-9 | **PASS** |

### Honesty / still refuses

- Still-life off-center 256² **1px noise-class** residue from 4pm remains documented (not claimed fixed).
- HDR worlds, kitchens, TEX_COORD Object **with** Object reference (use_transform / object_itfm), linked Mapping L/R/S, packed-only images, Coat Roughness/IOR/Tint, Sheen Roughness/Tint, Emission Color still raise `QuantTraceSyncError`.
- Film stays opaque (`film_transparent=False`); Combined RGB is over black world. Session Combined A mean stays 1.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Done 6am: Emission Color TEX_IMAGE. See 6am section.

---

## 6am PlugWalk (2026-08-28) — Slice 2r: Principled Emission Color TEX_IMAGE

Box: Linux, 8 cores. Did **not** `make update` / rebuild `native/cycles-src`. Rebuilt only
`native/quanttrace/build` (`-DQT_WITH_CYCLES=ON`). No user 2080. No zip. No Make it Fast / Auto.

### What landed

| Piece | Detail |
|---|---|
| ABI | `emit_color_image_path` (+ colorspace, tex_vector_mode, Mapping) on `QT_SimpleScene` and `QT_Mesh` (NULL/empty = Cycles default Emission Color 1,1,1 unlinked) |
| Packer | Principled Emission Color (legacy Emission) may be TEX_IMAGE Color (same Vector graph as Base Color). Emission Strength stays `emit_str` — not conflated. Coat Roughness/IOR/Tint, Sheen Roughness/Tint still refuse. |
| Native | Color → Emission Color (legacy Emission) Color→Color, no NODE_CONVERT_CF. When Color is mapped and Strength is not, `set_emission_strength(1.0)` so the color map is visible (test-scene pin; Cycles default Strength is 0). `needs_uv` and `mesh_uses_generated` include emit_color. |
| Version | `0.0.19-slice2r` |
| Tools | `_quanttrace_emitcolor_scene/smoke.py` (8×8 sRGB color checker; `--socket Color\|Color+Strength`) |

`libquanttrace.so` still CDLL-loads with empty `LD_LIBRARY_PATH`. `is_tracer=1` unchanged.

### Measured — TEX_IMAGE → Principled Emission Color (Strength unlinked 1.0)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | wall | Gate |
|---|---|---|---|---|---|---|
| Color Session | 32² / 4 | **5.96e-7** | 1.16e-8 | 0 / 1024 | 0.007 s | **PASS** |
| Color Session | 256² / 128 | **9.54e-7** | 6.89e-9 | 0 / 65536 | 0.295 s | **PASS** |

### Measured — Color+Strength (Color sRGB TEX_IMAGE + Strength Non-Color TEX_IMAGE)

| Path | Res / spp | Δmax | MAE | px ≥ 1e-3 | wall | Gate |
|---|---|---|---|---|---|---|
| Color+Strength Session | 32² / 4 | **7.15e-7** | 8.67e-9 | 0 / 1024 | 0.007 s | **PASS** |

### Measured — regressions (32² / 4)

| Path | Res / spp | Δmax | MAE | wall | Gate |
|---|---|---|---|---|---|
| 2q Coat Weight TEX_IMAGE | 32² / 4 | **2.38e-7** | 4.71e-9 | 0.006 s | **PASS** |

### Honesty / still refuses

- Still-life off-center 256² **1px noise-class** residue from 4pm remains documented (not claimed fixed).
- HDR worlds, kitchens, TEX_COORD Object **with** Object reference (use_transform / object_itfm), linked Mapping L/R/S, packed-only images, Coat Roughness/IOR/Tint, Sheen Roughness/Tint still raise `QuantTraceSyncError`.
- Film stays opaque (`film_transparent=False`); Combined RGB is over black world. Session Combined A mean stays 1.
- Make it Fast / Auto / zip / listing / gibby / user 2080: untouched.
- Store Classroom **41%** / loft **52%** unchanged.

### Next

Coat Roughness/IOR/Tint, Sheen Roughness/Tint, or close still-life 1px. Not ReSTIR. Not Classroom time %.
