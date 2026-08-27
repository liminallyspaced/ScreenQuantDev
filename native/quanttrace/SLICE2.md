# QuantTrace Slice 2 — build order (cube pixel-match)

Status: **Slice 2d landed** (2026-08-27 4pm PlugWalk ET). Blender `random_id` parity + object-local tfm + AREA/POINT/SUN. Hard POINT 256²/128 Δmax=1.2e-7 PASS. Still-life 32²/4 PASS; 256² still 1px noise-class residue on off-center silhouettes. SUN ABI wired, strength parity not claimed. `is_tracer=1`.
Slice 1 (done): hello `libquanttrace.so`, `quanttrace_is_tracer() == 0`.
Acceptance: `docs/research/QUANTTRACE-CUBE.md`.
Design: `docs/research/SIDECAR-INTEGRATOR.md`.

`is_tracer=1` when QT_WITH_CYCLES (F12 wired for locked cube). Do **not** claim arbitrary-scene sync.
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

Soft POINT radius parity, SUN strength factor, textured Principled. Not ReSTIR. Not Classroom time %.

