/* QuantTrace native hello — slice 1 load plumbing only.
 * NOT a path tracer. quanttrace_is_tracer() returns 0 until a real kernel ships.
 */

#if defined(_WIN32)
#  define QT_EXPORT __declspec(dllexport)
#else
#  define QT_EXPORT __attribute__((visibility("default")))
#endif

static const char QT_VERSION[] = "0.0.1-hello";

QT_EXPORT const char *quanttrace_version(void)
{
    return QT_VERSION;
}

QT_EXPORT int quanttrace_is_tracer(void)
{
    return 0;
}
