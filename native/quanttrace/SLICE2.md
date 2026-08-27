# QuantTrace Slice 2 — build order (cube pixel-match)

Status: **plan only** (2026-08-27 7am PlugWalk).
Slice 1 (done): hello `libquanttrace.so`, `quanttrace_is_tracer() == 0`.
Acceptance: `docs/research/QUANTTRACE-CUBE.md`.
Design: `docs/research/SIDECAR-INTEGRATOR.md`.

**Do not** set `is_tracer=1` until stock uni-PT produces Combined pixels.
**Do not** touch Make it Fast / Auto. **Do not** vendor Cycles into the
addon zip or public commit tree.

---

## Upstream (cite)

- Cycles standalone (Apache-2.0): https://github.com/blender/cycles  
  (official mirror of https://projects.blender.org/blender/cycles)
- Standalone C++ API docs:
  https://developer.blender.org/docs/features/cycles/standalone/
- Key headers (upstream names): `src/session/session.h`, `src/scene/scene.h`
  (`Session`, `Scene`, `Mesh`, `Shader`, `Light`, `Camera`, `Film`,
  `Integrator`)

License: Apache-2.0 library + GPL addon glue is the intended split
(same packaging class as BlendLuxCore’s native core). Confirm NOTICE /
LICENSE copy when the fork lands.

---

## Ordered steps

1. **Fork / clone Cycles standalone (Apache-2.0)**  
   Shallow clone preferred. Working trees **outside** the shipped addon
   path, gitignored:
   - Preferred: `/workspace/scenequant-public/native/cycles-src`
   - Alt: `/workspace/quanttrace-cycles`  
   Do **not** `git add` the full Cycles tree into
   `liminallyspaced/ScreenQuantDev`. Build artifacts stay local.

2. **Build standalone Scene + Session**  
   Follow upstream `BUILDING.md` (`make update` / CMake). Target CPU
   first. Confirm a `cycles` CLI or a minimal C++ harness can
   `Session::start` / wait / read Combined buffer on an XML or API-built
   scene. No Blender link yet.

3. **Export the locked cube into `ccl::Scene`**  
   Depsgraph (or a one-shot Python exporter) → one mesh, one Principled
   SVM graph (base color / roughness / metal / IOR / alpha only), one
   area light, one camera, black world. Match
   `QUANTTRACE-CUBE.md`. Loud-fail on unsupported nodes.

4. **Run stock unidirectional PT (no new sampler)**  
   Integrator = upstream uni-PT + NEE + MIS. Fixed 128 spp, CPU, seed
   documented. Write linear Combined float buffer (and EXR for the gate).

5. **Wire `is_tracer=1` only after pixels exist**  
   Native ABI still exports `quanttrace_version` /
   `quanttrace_is_tracer`. Flip to `1` when Session render path is real.
   Python `SQ_QUANTTRACE` may then `begin_result` / `end_result` Combined.
   Until then keep `0` and refuse F12 (current hello behavior).

6. **Pixel-match vs stock Cycles Combined**  
   Same `.blend`, CPU, 128 spp, linear EXR pair. Gate:
   \(\Delta_{\max} < 10^{-3}\) per `QUANTTRACE-CUBE.md`. Log MAE as
   diagnostic. Fail → stop; do not claim Cycles-shaped lighting.

---

## Explicit non-goals this slice

- ReSTIR / path guiding / OIDN / OptiX
- Kitchen / Classroom / loft benches or time %
- `is_tracer=1` without a kernel
- Vendoring all of Cycles into the public addon commit
- Make it Fast RNA writes

---

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

Honest note: `make update` would pull large precompiled `lib/` deps shared with Blender and may not fit casually. This hour stops at the shallow source clone + markdown plans. No build, no `is_tracer=1`, no pixel match yet.
