/* QuantTrace native ABI.
 *
 * Slice 1: version + is_tracer (always 0 until a kernel exists).
 * Slice 2: optional Session probe / cube render entry. Probe==1 only means
 * the Cycles Session path was compiled in; it is NOT a tracer and does NOT
 * flip quanttrace_is_tracer(). Python SQ_QUANTTRACE still refuses F12.
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
QT_EXPORT int quanttrace_is_tracer(void);

/* 0 = Session path not compiled (stub). 1 = QT_WITH_CYCLES compiled in.
 * Never implies pixel-match or is_tracer=1.
 */
QT_EXPORT int quanttrace_session_probe(void);

/* Render the locked cube via ccl::Session once linked. Returns 0 on
 * success, -1 if the Session path is not compiled / Combined empty / EXR
 * write failed. exr_path may be NULL or empty (Combined stays in-memory).
 * When non-empty, writes linear RGBA float OpenEXR (zip).
 * QUANTTRACE_CUBE_WIDTH / HEIGHT / SAMPLES override locked 256 / 256 / 128
 * (QUANTTRACE-CUBE.md). Smoke this hour: 32 / 32 / 4.
 */
QT_EXPORT int quanttrace_render_cube(const char *exr_path);

#ifdef __cplusplus
}
#endif

#endif /* QUANTTRACE_H */
