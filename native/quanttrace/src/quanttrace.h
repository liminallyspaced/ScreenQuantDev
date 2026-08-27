/* QuantTrace native ABI.
 *
 * Slice 1: version + is_tracer.
 * Slice 2: Session cube Combined (pixel-match PASS) + F12 wire.
 *   is_tracer==1 only when QT_WITH_CYCLES is compiled in and
 *   SQ_QUANTTRACE.render can land Combined in the Image Editor.
 * Make it Fast stays on stock Cycles.
 */
#ifndef QUANTTRACE_H
#define QUANTTRACE_H

#ifdef __cplusplus
extern "C" {
#endif

#if defined(_WIN32)
#  define QT_EXPORT __declspec(dllexport)
#else
#  define QT_EXPORT __attribute__((visibility("default")))
#endif

QT_EXPORT const char *quanttrace_version(void);

/* 0 = stub / no Session. 1 = QT_WITH_CYCLES + locked-cube F12 path. */
QT_EXPORT int quanttrace_is_tracer(void);

/* 0 = Session path not compiled (stub). 1 = QT_WITH_CYCLES compiled in. */
QT_EXPORT int quanttrace_session_probe(void);

/* Render the locked cube via ccl::Session. Returns 0 on success, -1 on
 * failure. exr_path may be NULL/empty (Combined stays in-memory).
 * When non-empty, writes linear RGBA float OpenEXR (zip), top-down.
 * QUANTTRACE_CUBE_WIDTH / HEIGHT / SAMPLES override locked 256 / 256 / 128.
 */
QT_EXPORT int quanttrace_render_cube(const char *exr_path);

/* Same Session path; fills out_rgba with bottom-up linear RGBA float
 * (Blender RenderPass.rect / Image.pixels convention). out_capacity is
 * float count (must be >= w*h*4). Writes *out_w / *out_h. Returns 0.
 */
QT_EXPORT int quanttrace_render_cube_rgba(float *out_rgba,
                                          int out_capacity,
                                          int *out_w,
                                          int *out_h);

#ifdef __cplusplus
}
#endif

#endif /* QUANTTRACE_H */
