# QuantTrace cube pixel-match — acceptance gate

Date: 2026-08-27 (7am PlugWalk)
Status: **gate PASS** + **F12 wire** (2026-08-27 1pm) — stock Cycles vs `SQ_QUANTTRACE` F12 Combined at 256²/128: Δmax=4.77e-7 < 1e-3 (MAE 3.57e-9). `quanttrace_is_tracer()` **1** when `QT_WITH_CYCLES`. Depsgraph still-life + TEX_IMAGE Principled now pass (see `native/quanttrace/SLICE2.md` 6pm). Locked cube remains the original fidelity gate.
Design parent: `docs/research/SIDECAR-INTEGRATOR.md` Slice 1.
Build order: `native/quanttrace/SLICE2.md`.

This is the first **honest** fidelity gate for QuantTrace. It does **not**
prove speed. It does **not** touch Make it Fast / Auto. It does **not** use
the user 2080. Pass means Combined pixels match stock Cycles on a locked
toy; fail means the sidecar is still vapor for any "looks like Cycles" claim.

---

## Scene (locked)

Build once in Blender (box: `/home/box/apps/blender-5.2.0-linux-x64`), save
as a local `.blend` **outside** the addon zip path (gitignored `*.blend`).

| Item | Exact |
|---|---|
| Mesh | One default cube (`bpy.ops.mesh.primitive_cube_add()`, location origin, scale 1) |
| Material | Stock Principled BSDF only — Base Color `(0.8, 0.8, 0.8)`, Roughness `0.5`, Metallic `0.0`, IOR `1.45`, Alpha `1.0`, no other sockets linked |
| Textures | **None** (no Image, Noise, or Attribute nodes) |
| Light | One Area light, size `1.0` m, energy `1000`, color white `(1,1,1)`, location `(4.07625, 1.00545, 5.90386)` (Blender startup-ish), rotation aimed at origin |
| Camera | One perspective camera, focal length `50` mm, sensor `36` mm, looking at cube (startup camera pose is fine if FOV covers the cube) |
| World | Solid Background Color black `(0,0,0)`, Strength `0` (no HDRI, no texture) |
| Resolution | `256 × 256` (small; fidelity not beauty) |
| Film | Transparent **off**; Exposure `1.0`; no cryptomatte / extra passes beyond Combined |
| Engine A | Stock **CYCLES** |
| Engine B | **SQ_QUANTTRACE** (only after `is_tracer=1` and uni-PT path exists) |

No linked libraries. No modifiers. No hair, volume, motion blur, light
linking, MNEE, portals, OSL, or Adaptive Subdivision.

---

## Render protocol (CPU-only)

Both engines, same machine, **CPU device only** (Cycles Render → Device →
CPU; QuantTrace CPU backend). No OptiX/CUDA. No user GPU. No denoise.
No adaptive sampling. Fixed sample count.

| Knob | Value |
|---|---|
| Samples | `128` (fixed; adaptive off) |
| Seed | `0` (document if QuantTrace RNG cannot match; then compare distributions, not bit-identical) |
| Filter | Gaussian, width `1.5` (pinned; Blender 5.2 factory is Blackman-Harris) |
| Sampling | Tabulated Sobol / Classic, seed `0`, scramble `1.0`, light threshold `0` (pinned; Blender 5.2 factory is AUTOMATIC blue-noise) |
| Clamp direct / indirect | `0` / `10` (Cycles factory-ish; keep identical on both) |
| Light tree / MIS | stock defaults, identical on both |
| Color management | Write **linear** Combined EXR (File → Output → OpenEXR, codec ZIP or None, Color Depth Float Full). View transform must **not** bake into the EXR (Raw / Standard linear float buffer). |
| Output | `cube_cycles_combined.exr` and `cube_quanttrace_combined.exr` |

Script both F12s headless when ready (`blender --background cube.blend
--python …`). Until the native kernel exists, **do not** invent QuantTrace
pixels.

---

## Pass criteria (metric choice)

**Primary metric: max absolute linear RGB delta** over all pixels and
channels (R, G, B; ignore A if Film opaque and both write 1.0).

\[
\Delta_{\max} = \max_{p \in P}\; \max_{c \in \{R,G,B\}} \lvert C^{\text{QT}}_{p,c} - C^{\text{CY}}_{p,c} \rvert
\]

| Result | Rule |
|---|---|
| **PASS** | \(\Delta_{\max} < 1 \times 10^{-3}\) at 128 spp on the locked scene |
| **FAIL** | \(\Delta_{\max} \ge 1 \times 10^{-3}\), or QuantTrace refuses / crashes / writes non-Combined junk |

### Why max-abs, not MAE

- **Max abs** catches a single wrong highlight, shadow acne spike, or
  material eval bug that MAE can wash out over 256² mostly-correct
  pixels.
- Linear EXR (not sRGB PNG) so a 1e-3 gate is in scene-referred radiance,
  not display space.
- MAE is recorded as a **secondary** diagnostic only:

\[
\mathrm{MAE} = \frac{1}{3|P|}\sum_{p}\sum_{c}\lvert C^{\text{QT}}_{p,c} - C^{\text{CY}}_{p,c} \rvert
\]

  Report MAE in the run log; **do not** pass on MAE alone. If RNG seeds
  cannot match, allow a re-run with higher spp (e.g. 512) and keep the
  same \(\Delta_{\max}\) gate, or document a small noise-floor exception
  with screenshots — never silently raise the threshold.

Reference compare (box Python + OpenEXR / numpy when wired):

```text
max_abs = abs(qt[:,:,:3] - cy[:,:,:3]).max()
mae     = abs(qt[:,:,:3] - cy[:,:,:3]).mean()
pass    = max_abs < 1e-3
```

---

## Out of scope (this gate)

- Make it Fast / Auto / any % time claim
- Classroom / loft / BMW27 / kitchen files
- ReSTIR, path guiding, OIDN, GPU
- Setting `quanttrace_is_tracer()` to `1` before uni-PT exists
- Shipping a zip or bumping a store claim

---

## Honesty

Native returns `is_tracer=1` with QT_WITH_CYCLES (F12 wired for locked cube). The cube Combined
pair at 256²/128 **is** a pass (Δmax 4.77e-7). That is not a speed claim
and not an `SQ_QUANTTRACE` F12.


## Slice 2e measured (2026-08-27 5pm ET)

Soft POINT (`shadow_soft_size=0.25`, `use_soft_falloff=True` → disk) stock vs Session,
Tabulated Sobol both sides:

| Res / spp | Δmax | MAE | Gate |
|---|---|---|---|
| 32² / 4 | 8.94e-8 | 1.63e-9 | PASS |
| 256² / 128 | 1.19e-7 | 1.00e-9 | PASS |

SUN (`energy=200`, `angle=0.0091803`, -Z→origin):

| Res / spp | Δmax | MAE | Gate |
|---|---|---|---|
| 32² / 4 | 3.81e-6 | 5.59e-9 | PASS |
| 256² / 128 | 3.81e-6 | 2.40e-9 | PASS |

Fix: pack `is_sphere = !use_soft_falloff` (was always true). Native `0.0.6-slice2e`.
Still-life 256² 1px noise-class residue unchanged. No Classroom/loft claims.



## Slice 2bd (2026-08-29)

RGB Curves → Principled Base Color gate PASS (32²/4 Δmax 8.34e-7; 256²/128 Δmax 4.77e-7). Native `0.0.57-slice2bd`. See `native/quanttrace/SLICE2.md`.

## Slice 2bc (2026-08-29)

Noise → Bump.Height → Principled.Normal gate PASS (32²/4 Δmax 4.65e-6; 256²/128 Δmax 6.32e-6). Native `0.0.56-slice2bc`. See `native/quanttrace/SLICE2.md`.

## Slice 2bb (2026-08-29)

Noise → ColorRamp.Fac → Principled.Roughness gate PASS (32²/4 Δmax 3.28e-5; 256²/128 Δmax 6.44e-6). Native `0.0.55-slice2bb`. See `native/quanttrace/SLICE2.md`.

## Slice 2ba (2026-08-29)

ColorRamp → Principled.Roughness gate PASS (32²/4 Δmax 4.77e-7; 256²/128 Δmax 7.15e-7). Native `0.0.54-slice2ba`. See `native/quanttrace/SLICE2.md`.

## Slice 2az (2026-08-29)

Bevel → Principled.Normal gate PASS (32²/4 Δmax 4.77e-6; 256²/128 Δmax 2.26e-6). Native `0.0.53-slice2az`. See `native/quanttrace/SLICE2.md`.
