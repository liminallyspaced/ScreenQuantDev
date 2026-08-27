cmake_minimum_required(VERSION 3.16)
project(quanttrace LANGUAGES C)

# Slice 1: tiny shared lib proving addon ctypes load. NOT a path tracer.
# Slice 2 (future): cube pixel-match vs Cycles — not this CMakeLists.

add_library(quanttrace SHARED src/hello.c)

set_target_properties(quanttrace PROPERTIES
  OUTPUT_NAME quanttrace
  C_STANDARD 99
  C_STANDARD_REQUIRED ON
  C_VISIBILITY_PRESET default
  POSITION_INDEPENDENT_CODE ON
)

# Linux/macOS: libquanttrace.so / libquanttrace.dylib
# Windows: quanttrace.dll
install(TARGETS quanttrace LIBRARY DESTINATION lib RUNTIME DESTINATION bin)
