# QuantTrace Slice 2 — build order (cube pixel-match)

Status: **Session Combined EXR write + 32x32/4spp smoke** (2026-08-27 9:15am PlugWalk ET). `is_tracer` still 0. Smoke Combined is opaque-film black (A=1). Cube dmax gate unmet.
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
