/* QuantTrace native ABI.
 *
 * Slice 1: version + is_tracer.
 * Slice 2: Session cube Combined (pixel-match PASS) + F12 wire.
 * Slice 2b: depsgraph-fed simple scene (camera/mesh/Principled/area/world).
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

/* 0 = stub / no Session. 1 = QT_WITH_CYCLES + F12 path. */
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

/* Depsgraph-fed simple scene (Slice 2b).
 *
 * One triangle mesh + one Principled surface + one AREA light + camera +
 * black/constant world. Matrices are Blender matrix_world first-3-rows
 * (12 floats: r0c0..r0c3, r1c0..r1c3, r2c0..r2c3). Camera gets
 * blender_camera_matrix Z-flip inside the native path.
 *
 * verts: nverts * 3 floats (object-local).
 * tris:  ntris * 3 ints (CCW outward).
 * Returns 0 on success, -1 on failure / unsupported.
 */
typedef struct QT_SimpleScene {
  int width;
  int height;
  int samples;
  int nverts;
  int ntris;
  const float *verts; /* nverts * 3 */
  const int *tris;    /* ntris * 3 */
  float mesh_tfm[12]; /* object matrix_world 3x4 */
  float cam_tfm[12];  /* camera matrix_world 3x4 (pre Z-flip) */
  float cam_fov;      /* radians */
  float cam_sensor_w; /* metres */
  float cam_sensor_h; /* metres */
  float cam_near;
  float cam_far;
  float light_tfm[12]; /* area light matrix_world 3x4 (emit -Z) */
  float light_sizeu;
  float light_sizev;
  float light_strength[3]; /* color * energy * exp2(exposure) */
  float base_color[3];
  float roughness;
  float metallic;
  float ior;
  float alpha;
  float world_strength; /* Background Strength; Color black */
  const char *exr_path; /* optional; NULL/empty skips file write */
} QT_SimpleScene;

QT_EXPORT int quanttrace_render_scene_rgba(const QT_SimpleScene *scene,
                                           float *out_rgba,
                                           int out_capacity,
                                           int *out_w,
                                           int *out_h);

#ifdef __cplusplus
}
#endif

#endif /* QUANTTRACE_H */
