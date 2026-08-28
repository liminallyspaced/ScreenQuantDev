/* QuantTrace native — version string only.
 * quanttrace_is_tracer() lives in session_bridge.cpp:
 *   stub (no QT_WITH_CYCLES) → 0
 *   Session path compiled in → 1 (F12 wired to uni-PT)
 */
#if defined(_WIN32)
#  define QT_EXPORT __declspec(dllexport)
#else
#  define QT_EXPORT __attribute__((visibility("default")))
#endif

static const char QT_VERSION[] = "0.0.22-slice2u";

QT_EXPORT const char *quanttrace_version(void)
{
    return QT_VERSION;
}
