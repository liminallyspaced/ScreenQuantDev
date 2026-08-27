# QuantTrace native (`libquanttrace`)

**This is NOT a path tracer yet.**

Native sidecar for the `SQ_QUANTTRACE` Blender RenderEngine. Design:
`docs/research/SIDECAR-INTEGRATOR.md`. Make it Fast stays on stock Cycles;
this tree never feeds Auto clocks.

## Slices

| Slice | Status | What |
|---|---|---|
| **1 — hello lib** | **this directory** | Shared `libquanttrace` / `quanttrace.dll` exporting `quanttrace_version()` and `quanttrace_is_tracer()` (returns `0`). Proves ctypes load from the Python stub. No rays, no pixels, no `begin_result`. |
| **2 — cube pixel-match** | future | Real integrator path vs stock Cycles Combined on a locked cube + area light. Gate before any ReSTIR claim. |

Do not pretend slice 1 traces. `quanttrace_is_tracer() == 0` until a kernel exists; the Python engine keeps `kernel_ready` False and refuses F12.

## Build (Linux)

```bash
cd native/quanttrace
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build
# produces build/libquanttrace.so
```

Requires `cmake`, a C compiler (`gcc` / `clang`), and `make` (or Ninja).

Override load path from the addon with env `QUANTTRACE_LIB=/abs/path/to/libquanttrace.so`.

## ABI (slice 1)

```c
const char *quanttrace_version(void);  /* e.g. "0.0.1-hello" */
int quanttrace_is_tracer(void);        /* 0 until a real tracer ships */
```

## Out of scope this hour

- Path tracing / pixel writes
- Cycles fork / OptiX / Embree
- Wheels / CI matrix
- Make it Fast / Auto
