# QuantTrace native (`libquanttrace`)

**This is NOT a path tracer yet.** `quanttrace_is_tracer()` is still `0`.

Native sidecar for the `SQ_QUANTTRACE` Blender RenderEngine. Design:
`docs/research/SIDECAR-INTEGRATOR.md`. Make it Fast stays on stock Cycles;
this tree never feeds Auto clocks.

## Slices

| Slice | Status | What |
|---|---|---|
| **1 — hello lib** | done | Shared `libquanttrace` exporting `quanttrace_version()` and `quanttrace_is_tracer()` (`0`). |
| **2 — cube pixel-match** | in progress | Cycles standalone CPU Session **works** (`build/bin/cycles`). Addon `.so` Session path **compiles** (`QT_WITH_CYCLES=ON`) but **does not load** (missing zstd / full external lib list). Pixel-match not run. |

Do not pretend this traces. Python `SQ_QUANTTRACE` keeps `kernel_ready` False and refuses F12.

## Build (Linux) — hello stub (default)

```bash
cd native/quanttrace
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
# produces build/libquanttrace.so
# ABI: is_tracer=0, session_probe=0, render_cube=-1
```

## Cycles standalone (gitignored tree)

See `SLICE2.md`. Working CPU binary after `make update` + cmake:

`native/cycles-src/build/bin/cycles --device CPU`

## ABI

```c
const char *quanttrace_version(void);   /* "0.0.1-hello" */
int quanttrace_is_tracer(void);         /* 0 until Combined exists */
int quanttrace_session_probe(void);     /* 0 stub / 1 if QT_WITH_CYCLES compiled in */
int quanttrace_render_cube(const char *exr_path); /* -1 until Session .so loads */
```

## Out of scope until pixel-match

- `is_tracer=1`
- ReSTIR / OptiX / Make it Fast / zip / store % claims
