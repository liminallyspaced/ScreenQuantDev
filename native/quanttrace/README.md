# QuantTrace native (`libquanttrace`)

**Cube Combined matches stock Cycles** (256²/128 Δmax 4.77e-7). This is **not a path tracer** F12 yet: `quanttrace_is_tracer()` is still `0` — `SQ_QUANTTRACE.render` is not wired.

Native sidecar for the `SQ_QUANTTRACE` Blender RenderEngine. Design:
`docs/research/SIDECAR-INTEGRATOR.md`. Make it Fast stays on stock Cycles;
this tree never feeds Auto clocks.

## Slices

| Slice | Status | What |
|---|---|---|
| **1 — hello lib** | done | Shared `libquanttrace` exporting `quanttrace_version()` and `quanttrace_is_tracer()` (`0`). |
| **2 — cube pixel-match** | **PASS** | 256²/128 stock vs Session Δmax **4.77e-7**. `is_tracer=0` (F12 not wired). |

Do not pretend this traces. Python `SQ_QUANTTRACE` keeps `kernel_ready` False and refuses F12.

## Build (Linux) — hello stub (default)

```bash
cd native/quanttrace
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
# produces build/libquanttrace.so
# ABI: is_tracer=0, session_probe=0, render_cube=-1
```

## Build (Linux) — Session path (`QT_WITH_CYCLES=ON`)

Needs a local `native/cycles-src` tree already built (gitignored; see `SLICE2.md`).
Default stays OFF so a no-Cycles checkout still builds the stub.

```bash
cmake -S native/quanttrace -B native/quanttrace/build \
  -DCMAKE_BUILD_TYPE=Release -DQT_WITH_CYCLES=ON
cmake --build native/quanttrace/build -j 8
env -u LD_LIBRARY_PATH python3 tools/_quanttrace_load_probe.py
# ABI: is_tracer=0, session_probe=1.
# Smoke (not the cube gate):
QUANTTRACE_CUBE_WIDTH=32 QUANTTRACE_CUBE_HEIGHT=32 QUANTTRACE_CUBE_SAMPLES=4 \
  env -u LD_LIBRARY_PATH python3 tools/_quanttrace_session_smoke.py
```

RPATH is baked; ctypes does not need `LD_LIBRARY_PATH`.

## Cycles standalone (gitignored tree)

See `SLICE2.md`. Working CPU binary after `make update` + cmake:

`native/cycles-src/build/bin/cycles --device CPU`

## ABI

```c
const char *quanttrace_version(void);   /* "0.0.1-hello" */
int quanttrace_is_tracer(void);         /* 0 until Combined exists */
int quanttrace_session_probe(void);     /* 0 stub / 1 if QT_WITH_CYCLES compiled in */
int quanttrace_render_cube(const char *exr_path); /* 0 writes linear RGBA zip EXR when path set */
/* env QUANTTRACE_CUBE_WIDTH/HEIGHT/SAMPLES default 256/256/128 */
```

## Out of scope until pixel-match

- `is_tracer=1`
- ReSTIR / OptiX / Make it Fast / zip / store % claims
