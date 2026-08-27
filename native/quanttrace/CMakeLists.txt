cmake_minimum_required(VERSION 3.16)
project(quanttrace LANGUAGES C CXX)

# Slice 1: hello shared lib (ctypes load). NOT a path tracer.
# Slice 2: session_bridge.cpp is a stub unless QT_WITH_CYCLES=ON.
# quanttrace_is_tracer() stays 0 (hello.c) until cube Combined exists.

option(QT_WITH_CYCLES
  "Compile Session bridge against Cycles standalone headers (does not flip is_tracer)"
  OFF)
set(CYCLES_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../cycles-src"
    CACHE PATH "Cycles standalone source (gitignored, never vendored)")
set(CYCLES_BUILD "${CYCLES_ROOT}/build"
    CACHE PATH "Cycles cmake build dir")
set(CYCLES_LIBDIR "${CYCLES_ROOT}/lib/linux_x64"
    CACHE PATH "Precompiled Blender libs from make update")

add_library(quanttrace SHARED
  src/hello.c
  src/session_bridge.cpp
)

target_include_directories(quanttrace PRIVATE src)

set_target_properties(quanttrace PROPERTIES
  OUTPUT_NAME quanttrace
  C_STANDARD 99
  C_STANDARD_REQUIRED ON
  CXX_STANDARD 20
  CXX_STANDARD_REQUIRED ON
  C_VISIBILITY_PRESET default
  CXX_VISIBILITY_PRESET default
  POSITION_INDEPENDENT_CODE ON
)

if(QT_WITH_CYCLES)
  if(NOT EXISTS "${CYCLES_ROOT}/src/session/session.h")
    message(FATAL_ERROR
      "QT_WITH_CYCLES=ON but Cycles session.h missing at ${CYCLES_ROOT}. "
      "Shallow clone lives at native/cycles-src (gitignored).")
  endif()
  target_compile_definitions(quanttrace PRIVATE
    QT_WITH_CYCLES=1
    WITH_EMBREE
    EMBREE_MAJOR_VERSION=4
  )
  # Brace macros must not be stringified, and must not leak onto hello.c.
  # Matches cycles-src/build/compile_commands.json:
  #   -DCCL_NAMESPACE_BEGIN="namespace ccl {"
  set_property(SOURCE src/session_bridge.cpp APPEND PROPERTY COMPILE_OPTIONS
    "-DCCL_NAMESPACE_BEGIN=namespace ccl {"
    "-DCCL_NAMESPACE_END=}"
    -msse -msse2 -msse3 -mssse3 -msse4.1 -msse4.2
  )
  target_compile_definitions(quanttrace PRIVATE WITH_KERNEL_SSE42 WITH_KERNEL_AVX2 WITH_TBB WITH_OCIO WITH_PUGIXML)
  target_include_directories(quanttrace PRIVATE
    ${CYCLES_ROOT}/src
    ${CYCLES_ROOT}/third_party/cuew/include
    ${CYCLES_ROOT}/third_party/hipew/include
    ${CYCLES_ROOT}/third_party/sky/include
    ${CYCLES_ROOT}/third_party/mikktspace
    ${CYCLES_ROOT}/third_party/atomic
  )
  target_include_directories(quanttrace SYSTEM PRIVATE
    ${CYCLES_LIBDIR}/openimageio/include
    ${CYCLES_LIBDIR}/tbb/include
    ${CYCLES_LIBDIR}/embree/include
    ${CYCLES_LIBDIR}/pugixml/include
    ${CYCLES_LIBDIR}/zlib/include
    ${CYCLES_LIBDIR}/opencolorio/include
    ${CYCLES_LIBDIR}/openexr/include
    ${CYCLES_LIBDIR}/openexr/include/OpenEXR
    ${CYCLES_LIBDIR}/imath/include
    ${CYCLES_LIBDIR}/imath/include/Imath
  )
  if(EXISTS "${CYCLES_BUILD}/lib/libcycles_session.a")
    target_link_directories(quanttrace PRIVATE ${CYCLES_BUILD}/lib)
    # CPU-only tree has libcycles_kernel_cpu.a (no libcycles_kernel.a).
    target_link_directories(quanttrace PRIVATE
      ${CYCLES_LIBDIR}/openimageio/lib
      ${CYCLES_LIBDIR}/tbb/lib
      ${CYCLES_LIBDIR}/embree/lib
      ${CYCLES_LIBDIR}/opencolorio/lib
      ${CYCLES_LIBDIR}/openexr/lib
      ${CYCLES_LIBDIR}/imath/lib
    )
    target_link_libraries(quanttrace PRIVATE
      cycles_session cycles_scene cycles_device cycles_kernel_cpu
      cycles_bvh cycles_subd cycles_graph cycles_util cycles_integrator
      extern_sky extern_libc_compat
      OpenImageIO OpenImageIO_Util tbb embree4 OpenColorIO OpenEXR Imath
    )
    # Load still fails without the rest of Cycles' external_libs list.
    # 2026-08-27: ctypes.CDLL -> undefined ZSTD_getFrameContentSize.
    # Next: reuse cycles_external_libraries_append() (zstd, png, ...).
    # The working Session binary is cycles-src/build/bin/cycles, not this .so.
  else()
    message(WARNING
      "QT_WITH_CYCLES=ON: Cycles headers used, but libcycles_session.a not "
      "at ${CYCLES_BUILD}/lib yet. Configure will succeed; link will fail "
      "until native/cycles-src/build produces the static libs.")
  endif()
endif()

install(TARGETS quanttrace LIBRARY DESTINATION lib RUNTIME DESTINATION bin)
