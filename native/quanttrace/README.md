<!-- Slice 2d: random_id + POINT/SUN; version 0.0.5-slice2d -->
# QuantTrace native (`libquanttrace`)

**Cube Combined matches stock Cycles** (256²/128 Δmax 4.77e-7) **and**
`SQ_QUANTTRACE.render` F12 packs a still-life depsgraph (N meshes + N AREA)
and lands Combined. `quanttrace_is_tracer()` is **1** when built with
`-DQT_WITH_CYCLES=ON`. Native `0.0.4-multimesh`.

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

Kitchens / textured Principled / HDR worlds still refuse with a named reason.

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
# ABI: is_tracer=1, session_probe=1, version 0.0.4-multimesh
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
const char *quanttrace_version(void);   /* "0.0.4-multimesh" */
int quanttrace_is_tracer(void);         /* 1 when QT_WITH_CYCLES */
int quanttrace_render_scene_rgba(...);  /* depsgraph-fed QT_SimpleScene (1+1) */
int quanttrace_render_qt_scene_rgba(...); /* N mesh + N AREA QT_Scene */
int quanttrace_session_probe(void);     /* 0 stub / 1 if QT_WITH_CYCLES */
int quanttrace_render_cube(const char *exr_path);
int quanttrace_render_cube_rgba(float *out, int cap, int *w, int *h);
/* env QUANTTRACE_CUBE_WIDTH/HEIGHT/SAMPLES default 256/256/128 */
```

## Out of scope until shader / light-type expand

- Kitchen F12 / textured Principled / POINT/SUN/SPOT / HDR world
- ReSTIR / OptiX / Make it Fast / zip / store % claims
