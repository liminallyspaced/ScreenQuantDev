/* QuantTrace native ABI.
 *
 * Slice 1: version + is_tracer.
 * Slice 2: Session cube Combined (pixel-match PASS) + F12 wire.
 * Slice 2b: depsgraph-fed simple scene (camera/mesh/Principled/area/world).
 * Slice 2c: multi-mesh + multi-AREA (constant Principled per mesh).
 * Slice 2f: optional TEX_IMAGE on Principled Base Color + corner UVs.
 * Slice 2g: SPOT (spot_size/spot_blend + soft radius / is_sphere).
 * Slice 2h: TEX_COORD UV + Mapping → TEX_IMAGE Vector.
 * Slice 2i: TEX_IMAGE → Principled Roughness / Metallic (same Vector rules).
 * Slice 2j: Normal Map (Tangent) + TEX_IMAGE → Principled Normal.
 * Slice 2k: TEX_COORD Generated (+ optional Mapping) → TEX_IMAGE Vector.
 * Slice 2l: TEX_COORD Object (+ optional Mapping) → TEX_IMAGE Vector.
 * Slice 2m: TEX_COORD Camera (+ optional Mapping) → TEX_IMAGE Vector.
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

/* Slice 2c caps — kitchens still refuse. */
#define QT_MAX_MESHES 32
#define QT_MAX_LIGHTS 16

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
  const float *uvs; /* ntris * 3 * 2 corner UVs; NULL if untextured */
  const char *image_path; /* TEX_IMAGE filepath; NULL/empty = constant base */
  const char *image_colorspace; /* OCIO name; NULL = node default */
  int tex_vector_mode;
  float map_location[3];
  float map_rotation[3];
  float map_scale[3];
  int map_type;
  /* Slice 2i: Roughness TEX_IMAGE (NULL/empty = constant roughness) */
  const char *rough_image_path;
  const char *rough_image_colorspace;
  int rough_tex_vector_mode;
  float rough_map_location[3];
  float rough_map_rotation[3];
  float rough_map_scale[3];
  int rough_map_type;
  /* Slice 2i: Metallic TEX_IMAGE (NULL/empty = constant metallic) */
  const char *metal_image_path;
  const char *metal_image_colorspace;
  int metal_tex_vector_mode;
  float metal_map_location[3];
  float metal_map_rotation[3];
  float metal_map_scale[3];
  int metal_map_type;
  /* Slice 2j: Normal Map Color ← TEX_IMAGE (NULL/empty = geometric Normal) */
  const char *normal_image_path;
  const char *normal_image_colorspace;
  int normal_tex_vector_mode;
  float normal_map_location[3];
  float normal_map_rotation[3];
  float normal_map_scale[3];
  int normal_map_type;
  float normal_strength; /* Normal Map Strength, default 1.0 */
} QT_SimpleScene;

QT_EXPORT int quanttrace_render_scene_rgba(const QT_SimpleScene *scene,
                                           float *out_rgba,
                                           int out_capacity,
                                           int *out_w,
                                           int *out_h);

/* Slice 2c: N meshes + N AREA lights (constant Principled per mesh).
 * Caps: QT_MAX_MESHES / QT_MAX_LIGHTS. AREA + POINT + SUN + SPOT.
 * HDR worlds still refuse on the Python packer.
 */
typedef struct QT_Mesh {
  int nverts;
  int ntris;
  const float *verts; /* nverts * 3 */
  const int *tris;    /* ntris * 3 */
  float tfm[12];      /* object matrix_world 3x4 */
  float base_color[3];
  float roughness;
  float metallic;
  float ior;
  float alpha;
  const char *name; /* Blender object name for random_id; may be NULL */
  const float *uvs; /* ntris * 3 * 2 corner UVs; NULL if untextured */
  const char *image_path; /* TEX_IMAGE filepath; NULL/empty = constant base */
  const char *image_colorspace; /* OCIO name from Image.colorspace_settings */
  /* Slice 2h: Base Color TEX_IMAGE Vector graph */
  int tex_vector_mode; /* QT_TEX_VECTOR_* */
  float map_location[3];
  float map_rotation[3];
  float map_scale[3];
  int map_type; /* NODE_MAPPING_TYPE_*: 0 POINT, 1 TEXTURE, 2 VECTOR, 3 NORMAL */
  /* Slice 2i: Roughness TEX_IMAGE */
  const char *rough_image_path;
  const char *rough_image_colorspace;
  int rough_tex_vector_mode;
  float rough_map_location[3];
  float rough_map_rotation[3];
  float rough_map_scale[3];
  int rough_map_type;
  /* Slice 2i: Metallic TEX_IMAGE */
  const char *metal_image_path;
  const char *metal_image_colorspace;
  int metal_tex_vector_mode;
  float metal_map_location[3];
  float metal_map_rotation[3];
  float metal_map_scale[3];
  int metal_map_type;
  /* Slice 2j: Normal Map Color ← TEX_IMAGE */
  const char *normal_image_path;
  const char *normal_image_colorspace;
  int normal_tex_vector_mode;
  float normal_map_location[3];
  float normal_map_rotation[3];
  float normal_map_scale[3];
  int normal_map_type;
  float normal_strength; /* Normal Map Strength, default 1.0 */
} QT_Mesh;

/* Light kinds for QT_Light.kind */
#define QT_LIGHT_AREA  0
#define QT_LIGHT_POINT 1
#define QT_LIGHT_SUN   2
#define QT_LIGHT_SPOT  3

/* TEX_IMAGE Vector graph (Slice 2h) */
#define QT_TEX_VECTOR_UNLINKED              0 /* default UV via unlinked Vector */
#define QT_TEX_VECTOR_TEXCOORD              1 /* TEX_COORD UV → TEX_IMAGE Vector */
#define QT_TEX_VECTOR_MAPPING               2 /* TEX_COORD UV → Mapping → TEX_IMAGE */
#define QT_TEX_VECTOR_TEXCOORD_GENERATED    3 /* TEX_COORD Generated → TEX_IMAGE */
#define QT_TEX_VECTOR_MAPPING_GENERATED     4 /* TEX_COORD Generated → Mapping → TEX_IMAGE */
#define QT_TEX_VECTOR_TEXCOORD_OBJECT       5 /* TEX_COORD Object → TEX_IMAGE Vector */
#define QT_TEX_VECTOR_MAPPING_OBJECT        6 /* TEX_COORD Object → Mapping → TEX_IMAGE */
#define QT_TEX_VECTOR_TEXCOORD_CAMERA       7 /* TEX_COORD Camera → TEX_IMAGE Vector */
#define QT_TEX_VECTOR_MAPPING_CAMERA        8 /* TEX_COORD Camera → Mapping → TEX_IMAGE */


typedef struct QT_Light {
  float tfm[12]; /* object matrix_world 3x4 (AREA/SPOT emit -Z; SUN dir -Z) */
  float sizeu;   /* AREA sizeu; POINT unused; SUN unused; SPOT unused */
  float sizev;   /* AREA sizev */
  float strength[3]; /* color * energy * exp2(exposure) */
  const char *name; /* Blender object name for random_id; may be NULL */
  int kind;      /* QT_LIGHT_AREA / POINT / SUN / SPOT */
  float radius;  /* POINT/SPOT soft radius (shadow_soft_size) */
  float angle;   /* SUN angular diameter; SPOT spot_size (radians) */
  int is_sphere; /* POINT/SPOT: is_sphere = !use_soft_falloff (1=sphere, 0=disk) */
  float smooth;  /* SPOT spot_blend (0..1); unused otherwise */
} QT_Light;

typedef struct QT_Scene {
  int width;
  int height;
  int samples;
  int nmeshes;
  int nlights;
  const QT_Mesh *meshes;
  const QT_Light *lights;
  float cam_tfm[12];
  float cam_fov;
  float cam_sensor_w;
  float cam_sensor_h;
  float cam_near;
  float cam_far;
  float world_strength;
  const char *exr_path;
} QT_Scene;

QT_EXPORT int quanttrace_render_qt_scene_rgba(const QT_Scene *scene,
                                              float *out_rgba,
                                              int out_capacity,
                                              int *out_w,
                                              int *out_h);

#ifdef __cplusplus
}
#endif

#endif /* QUANTTRACE_H */
