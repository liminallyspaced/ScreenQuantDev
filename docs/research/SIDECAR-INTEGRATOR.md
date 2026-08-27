# SIDECAR integrator — can SceneQuant ship a second path tracer?

Date: 2026-08-26
Product: SceneQuant is a free Python addon. Make it Fast is one click on
**stock Cycles RNA**. Nick asked whether a *second module* can recreate a
more efficient Cycles — still real ray-traced lighting, still scene-agnostic,
not EEVEE, not Draft, not Fast GI, not AI upscale.

This note answers four design questions with sources. It does **not**
implement a renderer, invent benches, or use a user GPU. Official blender.org
kitchen files are later measurement only, not the design target.

---

## Verdict

**Yes, as a native sidecar. No, as Python-only. No, by poking stock Cycles.**

An addon can register a second `bpy.types.RenderEngine` and ship a native
`.so` / `.pyd` / wheel the way BlendLuxCore and ProRender do. That engine
can be a **forked Cycles standalone** (Apache-2.0 C++ Scene + Session API)
with one new integrator. That is the only path that keeps real rays **and**
Cycles SVM/OSL materials without forking Blender.

An addon **cannot**:

- swap the integrator inside the user's CYCLES engine
- call "trace one ray + eval this shader" on the live Cycles kernel
- beat unidirectional PT from Python
- look like Cycles if it goes Hydra → MaterialX, or wraps LuxCore / RPR

Recommended module: **QuantTrace** (internal: SIDECAR). First vertical
slice is *not* ReSTIR. It is F12 of a cube + area light through the sidecar
that pixel-matches stock Cycles Combined. If that fails, the module is vapor.

Make it Fast stays on stock Cycles. QuantTrace is an explicit engine switch.
Never count sidecar times in the Auto claim.

---

## 1. What a Blender addon can actually replace

### 1.1 `bpy.types.RenderEngine` — capabilities and limits

Official API: https://docs.blender.org/api/current/bpy.types.RenderEngine.html

An addon subclasses `RenderEngine` and Blender will call it for F12 and
(optionally) the viewport. You get a depsgraph. You write linear float
pixels through `begin_result` / `update_result` / `end_result`. That is the
whole contract.

| You get | You do not get |
|---|---|
| `render(depsgraph)` for F12 / material preview | Cycles BVH, SVM, OSL, or kernel |
| `view_update` / `view_draw` + GPU texture blit | The EEVEE draw-manager path (`DrawEngineType` is **not** public; see devtalk "Expose DrawEngineType…", 2022) |
| `bake(...)` if you implement it | A live pointer into the running CYCLES session |
| Pass registration (`register_pass`, `add_pass`) | Automatic Cycles AOV / light-group / shadow-catcher semantics |
| `test_break`, `update_progress`, `update_stats` | Cycles tile scheduler or adaptive-sample buffers |
| Color-management blit (`bind_display_space_shader`) | Scene sync. You walk the depsgraph yourself |
| Flags: `bl_use_preview`, `bl_use_gpu_context`, `bl_use_postprocess`, `bl_use_eevee_viewport`, `bl_use_shading_nodes_custom`, `bl_use_materialx` | Permission to keep CYCLES selected while you replace its integrator |

Set `bl_use_shading_nodes_custom = False` if you want the Cycles/EEVEE
node UI to stay. That only keeps the *editor*. It does not give you SVM
eval. Cycles' own Python engine (`intern/cycles/blender/addon/engine.py`)
is a thin wrapper: it pointer-casts the depsgraph into `_cycles` and the
C++ `BlenderSession` does the real work. An addon cannot hook that.

Viewport: `view_draw` must be cheap (upload a texture). Real work lives
on a side thread started from `view_update`. Overlays stay Blender's.

**Limit that kills a Python integrator:** the render method is Python.
Walking meshes, evaluating node trees, and tracing rays in `bpy` is
orders of magnitude too slow for production PT. Devtalk on DrawEngine
is explicit: use Python as glue to another language.

### 1.2 Can an addon ship a native `.pyd` / `.so` integrator?

**Yes. That is the production pattern.**

| Engine | Pattern | Source |
|---|---|---|
| **BlendLuxCore** | Python `RenderEngine` + `pyluxcore` wheel (`pyluxcore.so` / `.pyd`). Addon exports depsgraph → LuxCore SDL, then the C++ core traces. | https://github.com/LuxCoreRender/BlendLuxCore ; wiki "BlendLuxCore Installation" (LuxCore = C++ core, BlendLuxCore = Python glue) |
| **Radeon ProRender** | Python addon + RPR SDK native libs; also a Hydra variant (`HydraRenderEngine`, `bl_delegate_id = "HdRprPlugin"`) | https://github.com/GPUOpen-LibrariesAndSDKs/RadeonProRenderBlenderAddon ; `src/hydrarpr/engine.py` |
| **MPR / custom GPU** | `RenderEngine` + `ctypes` loader for `libmpr_renderer` | https://github.com/AonoZan/MPR_viewport_renderer |
| **Historical Cycles** | Cycles itself used to ship as a binary addon wrapping `_cycles` | `intern/cycles/blender/CCL_api.h`, `python.cpp` |

Blender 4.2+ extensions (`blender_manifest.toml`) can declare
platform wheels. SceneQuant today is Python-only (`type = "add-on"`, no
wheels). Adding a native module means **per-Blender, per-OS, per-arch
wheels** and a CI matrix. LuxCore already lives this pain (fixed pyluxcore
pin, offline wheel fallback). That is the cost of admission, not a
blocker.

OptiX-from-an-addon is legal: the addon process is Blender, so it can
create an OptiX context on the same GPU Cycles would have used. It does
**not** share Cycles' OptiX GAS/IAS or shader binding table. You build
your own.

### 1.3 Does Cycles expose "trace one ray + eval shader"?

**No public C API. No public Python API. You must re-sync the whole scene.**

What exists:

1. **`CCL_api.h`** (`intern/cycles/blender/CCL_api.h`, Blender 5.2 tree on
   Fossies): `CCL_python_module_init`, `CCL_log_init`,
   `CCL_implicit_sharing_init`, texture-cache helpers. That is the entire
   *Blender-facing* C API. No ray, no `ShaderData`, no BVH query.

2. **`_cycles` CPython module** (`intern/cycles/blender/python.cpp`
   `PyMethodDef methods[]`):

   `init`, `exit`, `create`, `free`, `render`, `render_frame_finish`,
   `draw`, `bake`, `view_draw`, `sync`, `reset`, `osl_compile`,
   `available_devices`, `system_info`, `denoise`, `merge`,
   `debug_flags_*`, `enable_print_stats`, `get_device_types`,
   `set_device_override`, `maketx`.

   Plus module flags: `with_osl`, `with_path_guiding`, `with_embree`,
   `with_openimagedenoise`.

   Every render entry takes a **session pointer** created by
   `create_func` → `new BlenderSession(...)`. `sync` / `reset` /
   `render` pointer-cast `depsgraph.as_pointer()` into
   `blender::Depsgraph *` and call `BlenderSession::synchronize` /
   `render`. There is no `trace_ray`, no `eval_shader`, no
   `get_session_scene`.

3. **Standalone C++ API** (https://github.com/blender/cycles,
   `src/session/session.h`, `src/scene/scene.h`): `Session`, `Scene`,
   `Mesh`, `Shader`, `Light`, `Camera`, `Film`, `Integrator`. This **is**
   a real API. Developer docs say use it, not the XML toy:
   https://developer.blender.org/docs/features/cycles/standalone/

   It is **not** linked into a third-party addon. Stock Blender's Cycles
   is compiled *into* the Blender binary. An addon that wants this API
   ships its **own** `libcycles` (or a fork).

4. **Kernel** (`intern/cycles/kernel/integrator/*`): megakernel on CPU,
   wavefront microkernels on GPU. `ShaderData`, `kernel_path_*`,
   `svm_eval` are device-side. They are not a host ABI.

**Consequence:** you cannot hang a better sampler off the user's already-
synced Cycles scene. `BlenderSync` (`intern/cycles/blender/sync.*`,
`object.cpp`, `shader.cpp`) is internal C++ that talks Blender DNA. To
get a Cycles `Scene` you either (a) compile a copy of that sync against
matching Blender headers — version-locked, effectively a Cycles-in-Blender
plugin — or (b) walk the depsgraph in your own exporter and populate the
standalone `Scene`. Both are a full re-sync. (b) is the addon-legal one.

Hacking `_cycles` session pointers from Python is undefined and will
break on the next Blender. Do not.

### 1.4 Hydra / USD render delegate vs custom engine

Blender ships `bpy.types.HydraRenderEngine`
(https://docs.blender.org/api/main/bpy.types.HydraRenderEngine.html).
You set `bl_delegate_id`, optionally `bl_use_materialx = True`, register
a USD plugin path, and Blender implements `update` / `render` /
`view_draw` for you. Materials go out as UsdPreviewSurface or MaterialX
(`nodes::materialx::export_to_materialx`, PR #111765 / #112864).
Principled maps; arbitrary Cycles node graphs do not. Manual USD export
notes the same caveat.

Cycles itself can *be* a Hydra delegate (`WITH_CYCLES_HYDRA_RENDER_DELEGATE`,
D14398; `src/hydra/` in blender/cycles). That is Cycles-as-backend for
usdview / Omniverse, **not** a way for an addon to inject an integrator
into the user's CYCLES engine.

| Path | Materials | Lights | Look like Cycles? | Addon-legal? |
|---|---|---|---|---|
| Custom `RenderEngine` + own tracer | You translate or lose | You translate or lose | Only if you reuse Cycles SVM | Yes (LuxCore proof) |
| Custom `RenderEngine` + **forked Cycles standalone** | SVM/OSL if you sync nodes | Cycles lights if you sync them | Yes, by construction | Yes, if you ship the `.so` |
| `HydraRenderEngine` + third-party Hd* | MaterialX / PreviewSurface, lossy | Hydra lights, lossy | No | Yes |
| `HydraRenderEngine` + HdCycles | Better, still USD-shaped | Better | Close, not identical | You would be bundling a second Cycles |
| Patch `intern/cycles` inside Blender | Perfect | Perfect | Perfect | **Blender fork. Out of scope.** |

**Pick custom RenderEngine + forked Cycles standalone.** Hydra is the
wrong fidelity trade for "still looks like Cycles."

---

## 2. What stock Cycles 4.5 and 5.1 already have

Do not rebuild these and call them a product. Same manuals in 4.5 LTS
and 5.1 unless noted:
https://docs.blender.org/manual/en/4.5/render/cycles/render_settings/sampling.html
https://docs.blender.org/manual/en/5.1/render/cycles/render_settings/sampling.html
https://docs.blender.org/manual/en/5.1/render/cycles/gpu_rendering.html

Release notes:
https://developer.blender.org/docs/release_notes/3.5/cycles/ (light tree)
https://developer.blender.org/docs/release_notes/4.5/cycles/
https://developer.blender.org/docs/release_notes/5.0/cycles/
https://developer.blender.org/docs/release_notes/5.1/cycles/

Kernel flags: `intern/cycles/kernel/features.h` (Fossies blender-5.1.2)
`KERNEL_FEATURE_MNEE`, `KERNEL_FEATURE_PATH_GUIDING`,
`KERNEL_FEATURE_LIGHT_TREE`.

| Feature | 4.5 | 5.1 | What it is | Source |
|---|---|---|---|---|
| **Unidirectional PT + NEE + MIS** | yes | yes | The integrator. Not bidirectional, not MLT | Manual "Sampling" |
| **Light tree** | yes (since 3.5) | yes | Many-light; modified Conty–Kulla 2018 (no adaptive split — one light per shade; min/max importance + distant lights) | `intern/cycles/kernel/light/tree.h`; 3.5 notes |
| **Path guiding** | **CPU only** | **CPU only** | OpenPGL (directional quadtrees / vMF). Surfaces (diffuse/glossy) + volumes. Training-sample cap | Manual; `_cycles.with_path_guiding`; D15286; GPU manual: "Path Guiding is not supported on any GPU" |
| **MNEE** | yes | yes | Manifold Next Event Estimation for *shadow* caustics (refractive casters → caustic lights). Newton walk on specular manifold. Slight bias from culling MIS/regularization | `intern/cycles/kernel/integrator/mnee.h`; Hanika et al. EG 2015; object flags `is_caustics_caster/receiver` |
| **Adaptive sampling** | yes | yes | Per-pixel stop on noise threshold; min samples | Manual; film aux buffers |
| **OIDN + OptiX denoise** | yes | yes | OIDN Quality High/Balanced/Fast; prefilter None/Fast/Accurate; GPU denoise toggle. 5.1: better textured transparency + roughness (PR#154988). 5.0: OptiX denoise origin flip (PR#145358) | Manual "Denoising"; 5.0/5.1 notes |
| **Scrambling distance** | yes | yes | Correlate pixel RNG to raise GPU occupancy. Artifacts; **incompatible with Blue-Noise** | Manual "Advanced" |
| **Blue-Noise / Owen-Sobol** | yes | yes | Pattern enum Automatic / Classic / Blue-Noise | Manual |
| **ReSTIR DI / GI / PT** | **no** | **no** | On hold. Structures missing; ReSTIR GI "not ready for production"; papers still moving | 2025-02-04 Render & Cycles meeting, https://devtalk.blender.org/t/2025-02-04-render-cycles-meeting/38862 ; Alaska, https://devtalk.blender.org/t/how-would-i-go-about-implementing-something-to-the-cycles-renderer/45399 ("No. You will need to modify Cycles code directly") |
| **Wavefront vs megakernel** | GPU wavefront / CPU megakernel | same | GPU: `IntegratorState` SoA, kernel graph (init → intersect → shade → shadow). CPU: one path per thread, microkernels called from a megakernel | https://developer.blender.org/docs/features/cycles/kernel_scheduling/ ; Sharybin GPC 2025 slides |
| **Light threshold** | yes | yes | Probabilistic tiny-light cull | Manual |
| **Filter Glossy, clamp, RR** | yes | yes | Biased noise knobs. Make it Fast already writes some of these | Light Paths manual |
| **Fast GI / AO replace** | yes | yes | **Not real PT.** Out of this module | Light Paths manual |
| **Portals** | yes | yes | Manual area-light portal sampling | Manual |
| **Light / shadow linking** | yes | yes | Stock | — |
| **Volumes** | biased ray march | **5.0 default = unbiased null scattering**; NanoVDB; optional `Render → Volume → Biased` | 5.0 notes PR#134460 / #132908 | |
| **Adaptive subdiv** | experimental, improved | **production** (PR#146723) | 4.5 / 5.0 notes | |
| **OSL custom cameras** | 4.5 CPU+OptiX | 5.0 UI/metadata | 4.5 / 5.0 notes | |
| **HIP RT default** | off / unstable in 4.5.0 | **on** (979af8dc5a) | 4.5 / 5.1 notes | |
| **Free lunch 5.1** | — | GPU ~5–10%, Windows CPU ~5–20% | 5.1 notes `4b34743b4e`, `1ebab9342b` — do not attribute to a knob | |

OpenPGL GPU ports (CUDA / SYCL / HIP / Metal) are **work in progress**
as of the 2025–2026 ASWF sandbox proposal
(https://github.com/AcademySoftwareFoundation/tac/issues/1218). Cycles
will not grow GPU guiding until that lands. That gap is real. It is also
not a SceneQuant RNA knob.

**What this means for "more efficient than stock Cycles":**

- Many-light: light tree is already there. Beating it means **visibility-
  aware** resampling (ReSTIR DI), not another tree.
- Interiors: GPU path guiding is the honest gap. CPU guiding exists and
  is unused on the OptiX claim.
- Occupancy: wavefront + scrambling already exist. Rebuilding a wavefront
  PT and calling it new is a lie.
- Denoise / adaptive / MNEE / portals / Fast GI: already shipped. Fast GI
  is also the look we refused.

---

## 3. Algorithms (2023–2026, plus the ones they rest on) that actually beat naive unidirectional PT

Filter: still **real rays**, usable on **interiors and exteriors**, not a
fake look (no EEVEE, no Draught, no 50% + AI upscale). "Looks like
Cycles" = same light transport if you turn the new sampler off or run it
unbiased.

No invented speedup numbers. Papers report their own scenes; those are
not SceneQuant benches.

| Method | Unbiased? | GPU-friendly? | Quality risk | Looks like Cycles? | Where it wins |
|---|---|---|---|---|---|
| **ReSTIR DI** (Bitterli et al., SIGGRAPH 2020, *Spatiotemporal reservoir resampling…*, TOG 39(4)) | Unbiased with GRIS weights + canonical samples; biased if you skip them | Yes (the point) | Correlation blotches, temporal lag, animated-seed conflict | Yes in unbiased mode — it *is* PT with a better light sampler | Exteriors / many lights / hard visibility. Interiors: only the *direct* term |
| **ReSTIR GI** (Ouyang et al., HPG 2021, CGF) | Usually **biased** (screen-space reuse, Jacobian shortcuts) | Yes | Glossy/reflection smears, world-space misses, splotches Cycles team called out | No, not at production stills | Indirect interiors at 1 spp realtime. Wrong product for F12 stills |
| **ReSTIR PT / GRIS** (Lin & Kettunen et al., SIGGRAPH 2022, *Generalized RIS*, TOG 41(4); https://graphics.cs.utah.edu/research/projects/gris/) | *Can* be unbiased (enough canonicals, M-cap, shift maps). Offline mode without temporal reuse exists | Yes, but shift mapping is the tax | Wrong reflections on metal, blotches — the reason Cycles put GI on hold | Only in the unbiased offline configuration | Both, if you pay the shift-map engineering. Not a first slice |
| **ReSTIR-PG** (Zeng et al., SIGGRAPH Asia 2025, NVIDIA; http://research.nvidia.com/labs/rtr/publication/zeng2025restirpg/) | Guiding from resampled paths; still PT | Yes (realtime paper) | Same family of correlation artifacts, faster recovery | Closer than raw ReSTIR GI | Interiors (guiding) + reuse. Research, not a library |
| **Practical path guiding** (Müller et al. EGSR 2017; Vorba/Herholz production course 2019; Rath et al. production papers; **OpenPGL**) | Unbiased if MIS'd with BSDF (Cycles does this) | **CPU mature. GPU WIP** (ASWF 2025–26) | Training time, first-sample noise, weak on specular caustics (Cycles manual says so) | **Already in Cycles CPU.** GPU port would still look like Cycles | Interiors (door / window / SDS). Exteriors: often a wash or a tax |
| **Many-light trees** (Conty Estevez & Kulla, HPG 2018) | Unbiased | Yes | Heuristic misses textured/visibility-heavy lights (Cycles manual lists this) | **Already in Cycles** | Many lights. Does **not** solve visibility the way ReSTIR DI does |
| **Neural Radiance Cache** (Müller, Rousselle, Novák, Keller, SIGGRAPH 2021; https://tom94.net/data/publications/mueller21realtime/mueller21realtime.pdf) | **Biased.** Residual PT (terminate into cache, keep a short unbiased prefix / residual) reduces but does not remove bias | Yes (tiny-cuda-nn, ~ms queries in the paper's setup) | Splotch, lag, "AI GI" look if residual is short; training during F12 | Only if residual is long enough that the cache is a variance reducer, not the picture | Interiors. Exteriors less | 
| **Neural / ReST control variates** (Müller et al. *Neural Control Variates*, TOG 2020; **ReSTCV**, SIGGRAPH 2026, https://hercier.github.io/restcv/) | Unbiased if the CV is a control, not a replacement | ReSTCV: yes, on top of ReSTIR. Neural CV: train-heavy | Extra reservoir state; color-noise win, not a new look | Yes if used as CV | Both, as a *layer on* ReSTIR — not a first slice |
| **Wavefront occupancy / SER** | N/A (scheduler, not a sampler) | Yes | None if you do not change the estimator | Cycles **already wavefront on GPU**. SER (OptiX shader-execution reorder) is a device trick, not a product | Occupancy-bound kernels. Rebuilding wavefront is not new |
| **MNEE / SMS** | MNEE: slight bias in Cycles' MIS cull. SMS: research | MNEE already GPU | Missed casters, large-light bias (Cycles comments) | **Already in Cycles** for shadow caustics | Glass caustics only |

**What actually beats naive uni-PT on *both* interiors and exteriors
without becoming a fake look:**

1. **ReSTIR DI (unbiased)** for the direct/many-light/visibility term.
   Exteriors pay. Interiors pay on the lamps you can see. Indirect is
   still uni-PT (or guiding).
2. **Path guiding (OpenPGL, MIS)** for the indirect term. Interiors pay.
   Exteriors usually do not. GPU is the missing piece, not the algorithm.
3. **Do not lead with ReSTIR GI, NRC, or Fast GI.** Those are the look
   risk. Cycles' own module said ReSTIR GI is not production-ready
   (Weizhen, Feb 2025 meeting notes). NRC is a cache picture unless the
   residual prefix is honest — and even then it is biased.

A production pair used in papers (NRC 2021 figure setup):
`PT + ReSTIR DI + (optional cache)`. For SceneQuant the cache is a later
Manual toggle, never the module's claim.

---

## 4. One architecture: QuantTrace (SIDECAR)

### Name

**QuantTrace** — SceneQuant module 2.
Internal / code: `SIDECAR`.
Engine id: `SQ_QUANTTRACE` (never `CYCLES`, never `BLENDER_EEVEE`).

Crazy: we ship a forked Cycles as an addon binary.
Shippable: LuxCore already proved the packaging. Cycles is Apache-2.0
and has a documented C++ Scene/Session API. We are not forking Blender.

### What it replaces vs what it keeps

| Keep (must) | Replace (the point) | Never touch |
|---|---|---|
| Real rays (closest + shadow). No raster GI | The **integrator kernel**: add ReSTIR DI (unbiased) on top of uni-PT + NEE | Stock CYCLES engine, `_cycles` session, user's OptiX GAS |
| Blender meshes / instances / camera / film / color management | Session + device that we own (our `libcycles` fork) | Make it Fast journal, Auto RNA writes |
| Cycles *materials* via SVM (OSL later). Principled first | Light *sampling* (ReSTIR DI vs stock light tree / discrete) | EEVEE, Draft, Fast GI, resolution%, AI upscale |
| Cycles *light types* (point/sun/spot/area/world/mesh emit) | GPU path guiding **if/when** OpenPGL GPU is real — not a SceneQuant rewrite of OpenPGL | Official kitchen as a design scene |
| Denoise as a *pass* (OIDN on our Combined, same as a user could) | — | Claiming Auto % from sidecar clocks |

Sync is **ours**: depsgraph walk → standalone `ccl::Scene`. We do not
call `BlenderSync`. First versions loud-skip hair, volumes, MNEE flags,
light linking, OSL, custom cameras, baking, motion blur. Skip means
"refuse the render with a reason," not silent wrong pixels.

### Why a Cycles fork and not LuxCore / RPR / from-scratch

LuxCore and RPR already ship. They do not look like Cycles. The whole
ask is "better Cycles, still Cycles materials/lights." From-scratch PT
reimplements SVM, closures, bump, attributes, and ten years of edge
cases. Forking `blender/cycles` (standalone target, Apache-2.0) reuses
SVM, film, devices, OIDN, Embree/OptiX backends, and the wavefront
graph. We add one integrator path and an exporter. GPL addon + Apache
lib is license-legal.

### Build order (weeks) — first vertical slice is not vapor

**Slice 0 (weeks 1–2) — prove the socket.**
`SQ_QUANTTRACE` `RenderEngine`. Native stub `.so` loaded via ctypes /
stable ABI. `render()` writes a flat color + camera-ray hit grayscale
from depsgraph meshes (Embree or the stock standalone uni-PT, no new
sampler). F12 a default cube. Combined lands in the Image Editor.
This is the "not vapor" gate. No ReSTIR. No kitchen files.

**Slice 1 (weeks 3–6) — look like Cycles on a toy.**
Exporter: camera, one mesh, Principled (base color / roughness / metal /
IOR / alpha), one area or point light, world Background color.
Run **stock unidirectional PT** from the forked standalone (no new
algorithm). Side-by-side linear EXR vs CYCLES on that toy. Gate:
MAE / HDR-FLIP on a locked spp, same seed if we can match the pattern,
else document the RNG difference. If this fails, stop. The module
cannot be "more efficient Cycles" if it is not Cycles-shaped.

**Slice 2 (weeks 7–10) — scene-agnostic enough to be a module.**
Instances, multiple materials, image textures, sun + world HDRI,
emission meshes. Loud skip list with tests: hair, volume, MNEE,
linking, OSL, motion, baking. Any `.blend` either renders or refuses
with a named reason. Still stock uni-PT. Still no kitchen claim.

**Slice 3 (weeks 11–16) — the first *new* sampler: ReSTIR DI only.**
Direct lighting reservoirs, spatial reuse, **no temporal reuse on
stills** (GRIS offline mode). Indirect stays uni-PT + stock light tree.
Unbiased weights on. Toggle: `QuantTrace → Integrator → ReSTIR DI`.
Default off until a later quality gate. CPU first (easier reservoirs),
then OptiX.

**Slice 4 (weeks 17–22) — GPU path + honesty.**
OptiX device in *our* Session. Occupancy is Cycles' wavefront, not a
press release. Optional: wire OpenPGL if we are on CPU; do not pretend
that is new. GPU guiding only if upstream OpenPGL GPU exists.

**Later, Manual-only, never the claim:** ReSTIR PT unbiased offline;
ReSTCV; NRC-with-long-residual. ReSTIR GI stays research.

Do not use the user's GPU for this research phase. Do not publish a
% vs Classroom. Kitchen files are a later measurement protocol, same
rules as Make it Fast (cold pair, linear EXR, HDR-FLIP, revert smoke
does not apply — this is an engine, not a journal write).

### Honest line: this is not possible from Python-only

> QuantTrace cannot exist as Python. `RenderEngine.render` can feed
> pixels and walk a depsgraph; it cannot run a production integrator.
> There is no Cycles API to trace one ray or eval a shader from an
> addon. A native `libquanttrace` (forked Cycles standalone + exporter
> + ReSTIR DI kernel) is mandatory. Without that `.so` / `.pyd` the
> module is a settings dump, and we already have one of those.

If we are not willing to own a C++/CUDA CI matrix, the answer to Nick
is **no**, and Make it Fast stays the product.

### How it sits next to Make it Fast (never pollute Auto)

```
SceneQuant
├── Make it Fast     stock CYCLES RNA + journal + Revert     AUTO claim
├── Fit to Budget    VRAM ladder                             not a speed claim
└── QuantTrace       engine SQ_QUANTTRACE, native sidecar    separate claim
```

Rules:

1. Auto never sets `scene.render.engine`. Auto never loads the `.so`.
2. QuantTrace is an operator / engine dropdown: **Render with
   QuantTrace**. User opts in. Missing binary → button disabled +
   reason, not a silent CYCLES fallback that we then time.
3. Planner `est_factor` and store plates (Classroom 41% / loft 52%)
   stay Make it Fast only. Sidecar clocks never enter that product.
4. Copy does not say "Cycles but faster" on the Auto button. QuantTrace
   copy: "experimental second engine, real rays, Cycles materials,
   different integrator."
5. Draft / Fast GI / res% stay off both claims.
6. If QuantTrace is slower than tuned CYCLES on a file — which it will
   be until ReSTIR DI lands and the exporter is not naive — we say so.

---

## What we are not doing

- Not a Blender fork, not a kernel-file replace inside `intern/cycles`.
- Not Hydra/MaterialX as the design target (lossy look).
- Not wrapping LuxCore/RPR and calling it Cycles.
- Not Python PT, not Draft, not EEVEE, not OIDN-as-the-product.
- Not rebuilding light tree, MNEE, adaptive, wavefront, or OIDN.
- Not shipping a zip, not committing a renderer, not inventing benches.
- Not using official kitchen files as the architecture fixture.

---

## Sources (primary)

**Blender / Cycles API and source**

- https://docs.blender.org/api/current/bpy.types.RenderEngine.html
- https://docs.blender.org/api/main/bpy.types.HydraRenderEngine.html
- `intern/cycles/blender/CCL_api.h`, `python.cpp`, `addon/engine.py`
  (Fossies blender-5.1.2 / 5.2.x)
- `intern/cycles/kernel/features.h`, `kernel/light/tree.h`,
  `kernel/integrator/mnee.h`
- https://developer.blender.org/docs/features/cycles/standalone/
- https://developer.blender.org/docs/features/cycles/kernel_scheduling/
- https://github.com/blender/cycles (`src/session/session.h`, `src/hydra/`)
- https://archive.blender.org/developer/differential/0014/0014398/ (HdCycles)
- https://devtalk.blender.org/t/expose-drawenginetype-as-python-module-for-custom-real-time-renderer/24261

**Manuals / release notes**

- Sampling 4.5 / 5.0 / 5.1 (path guiding CPU-only, light tree, adaptive,
  OIDN, scrambling)
- GPU Rendering 5.1 (no GPU path guiding)
- Light Paths 5.1 (MNEE lives under object caustic flags + NEE; Fast GI
  called out as approximation)
- https://developer.blender.org/docs/release_notes/3.5/cycles/
- https://developer.blender.org/docs/release_notes/4.5/cycles/
- https://developer.blender.org/docs/release_notes/5.0/cycles/
- https://developer.blender.org/docs/release_notes/5.1/cycles/

**Devtalk (ReSTIR hold)**

- https://devtalk.blender.org/t/2025-02-04-render-cycles-meeting/38862
- https://devtalk.blender.org/t/how-would-i-go-about-implementing-something-to-the-cycles-renderer/45399

**Existing addon engines**

- https://github.com/LuxCoreRender/BlendLuxCore
- https://wiki.luxcorerender.org/BlendLuxCore_Installation
- https://github.com/GPUOpen-LibrariesAndSDKs/RadeonProRenderBlenderAddon
- https://github.com/bnagirniak/RPRHydraRenderBlenderAddon (Hydra RPR)

**Papers / libraries**

- Bitterli et al. 2020. ReSTIR DI. ACM TOG 39(4).
- Ouyang et al. 2021. ReSTIR GI. HPG / CGF.
- Lin, Kettunen et al. 2022. GRIS / ReSTIR PT. ACM TOG 41(4).
  https://graphics.cs.utah.edu/research/projects/gris/
- Zeng et al. 2025. ReSTIR-PG. SIGGRAPH Asia.
  http://research.nvidia.com/labs/rtr/publication/zeng2025restirpg/
- ReSTCV 2026. https://hercier.github.io/restcv/
- Conty Estevez & Kulla 2018. Many lights + adaptive tree splitting. HPG.
- Müller et al. 2017. Practical Path Guiding. EGSR.
- OpenPGL: https://github.com/OpenPathGuidingLibrary/openpgl ;
  ASWF TAC #1218 (GPU ports WIP)
- Hanika, Kaplanyan, Dachsbacher 2015. MNEE. CGF.
- Müller et al. 2021. Real-time Neural Radiance Caching. SIGGRAPH.
  https://tom94.net/data/publications/mueller21realtime/mueller21realtime.pdf
- Müller et al. 2020. Neural Control Variates. TOG.
- Laine, Karras, Aila. Megakernels Considered Harmful (wavefront PT).
- Sharybin 2025. *Architecture of a unified CPU/GPU path tracer* (GPC).

**SceneQuant local**

- `work/docs/research/INTERNALS-LEVERS.md`, `NEXT-GROK-BRIEF.md`,
  `SPEED-PLAYBOOK.md` (ReSTIR already banned from the Auto claim;
  path guiding already noted CPU-only)
