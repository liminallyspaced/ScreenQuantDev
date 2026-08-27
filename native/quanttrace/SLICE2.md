# QuantTrace Slice 2 — build order (cube pixel-match)

Status: **Cycles standalone CPU Session works; addon .so Session path not loaded** (2026-08-27 8am PlugWalk ET).
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

### Still not true

- Cube Combined EXR pair / Δmax gate
- `is_tracer=1`
- Make it Fast / Auto / zip / Classroom 41% / loft 52% change
- User 2080
