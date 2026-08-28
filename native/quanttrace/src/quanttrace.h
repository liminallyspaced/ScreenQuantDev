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
 * Slice 2n: TEX_COORD Window + Reflection (+ optional Mapping) → TEX_IMAGE Vector.
 * Slice 2o: TEX_IMAGE → Principled IOR / Alpha (same Vector rules).
 * Slice 2p: TEX_IMAGE → Principled Transmission Weight / Specular IOR Level.
 * Slice 2q: TEX_IMAGE → Principled Coat Weight / Sheen Weight / Emission Strength.
 * Slice 2r: TEX_IMAGE → Principled Emission Color (legacy Emission).
 * Slice 2s: TEX_IMAGE → Principled Coat Roughness/IOR/Tint + Sheen Roughness/Tint.
 * Slice 2t: Normal Map (Tangent) + TEX_IMAGE → Principled Coat Normal.
 * Slice 2u: TEX_IMAGE → Principled Specular Tint / Thin Film Thickness+IOR /
 *   Subsurface Weight / Radius / Scale.
 * Slice 2v: TEX_IMAGE → Principled Subsurface IOR / Subsurface Anisotropy /
 *   Diffuse Roughness. Thin Wall is BOOLEAN in Blender 5.2 — ABI reserved,
 *   packer refuses TEX_IMAGE (not a float socket).
 * Slice 2w: TEX_IMAGE → Principled Anisotropic / Rotation / Tangent.
 * Slice 2x: Principled.Normal ← Bump ← TEX_IMAGE Height (parallel bump_* ABI;
 *   not reuse of normal_image_path). Strength/Distance unlinked floats
 *   (Blender 5.2 RNA 1.0 / 0.001). invert RNA 0/1. use_object_space false.
 *   If both bump_* and normal_* paths are set, Bump wins; packer fills one.
 * Slice 2z: Principled Normal Map space OBJECT + WORLD (plus Coat Normal space).
 *   0=TANGENT (default, 2j/2t bit-identical), 1=OBJECT, 2=WORLD.
 *   BLENDER_OBJECT / BLENDER_WORLD still refuse.
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
  int normal_space; /* QT_NORMAL_MAP_*: 0=TANGENT, 1=OBJECT, 2=WORLD */
  /* Slice 2o: IOR TEX_IMAGE (NULL/empty = constant ior) */
  const char *ior_image_path;
  const char *ior_image_colorspace;
  int ior_tex_vector_mode;
  float ior_map_location[3];
  float ior_map_rotation[3];
  float ior_map_scale[3];
  int ior_map_type;
  /* Slice 2o: Alpha TEX_IMAGE (NULL/empty = constant alpha) */
  const char *alpha_image_path;
  const char *alpha_image_colorspace;
  int alpha_tex_vector_mode;
  float alpha_map_location[3];
  float alpha_map_rotation[3];
  float alpha_map_scale[3];
  int alpha_map_type;
  /* Slice 2p: Transmission Weight TEX_IMAGE (NULL/empty = constant 0) */
  const char *trans_image_path;
  const char *trans_image_colorspace;
  int trans_tex_vector_mode;
  float trans_map_location[3];
  float trans_map_rotation[3];
  float trans_map_scale[3];
  int trans_map_type;
  /* Slice 2p: Specular IOR Level TEX_IMAGE (NULL/empty = constant 0.5) */
  const char *spec_image_path;
  const char *spec_image_colorspace;
  int spec_tex_vector_mode;
  float spec_map_location[3];
  float spec_map_rotation[3];
  float spec_map_scale[3];
  int spec_map_type;
  /* Slice 2q: Coat Weight TEX_IMAGE (NULL/empty = constant 0) */
  const char *coat_image_path;
  const char *coat_image_colorspace;
  int coat_tex_vector_mode;
  float coat_map_location[3];
  float coat_map_rotation[3];
  float coat_map_scale[3];
  int coat_map_type;
  /* Slice 2q: Sheen Weight TEX_IMAGE (NULL/empty = constant 0) */
  const char *sheen_image_path;
  const char *sheen_image_colorspace;
  int sheen_tex_vector_mode;
  float sheen_map_location[3];
  float sheen_map_rotation[3];
  float sheen_map_scale[3];
  int sheen_map_type;
  /* Slice 2q: Emission Strength TEX_IMAGE (NULL/empty = constant 0) */
  const char *emit_str_image_path;
  const char *emit_str_image_colorspace;
  int emit_str_tex_vector_mode;
  float emit_str_map_location[3];
  float emit_str_map_rotation[3];
  float emit_str_map_scale[3];
  int emit_str_map_type;
  /* Slice 2r: Emission Color TEX_IMAGE (NULL/empty = Cycles default 1,1,1 unlinked) */
  const char *emit_color_image_path;
  const char *emit_color_image_colorspace;
  int emit_color_tex_vector_mode;
  float emit_color_map_location[3];
  float emit_color_map_rotation[3];
  float emit_color_map_scale[3];
  int emit_color_map_type;
  /* Slice 2s: Coat Roughness TEX_IMAGE (NULL/empty = constant 0.03) */
  const char *coat_rough_image_path;
  const char *coat_rough_image_colorspace;
  int coat_rough_tex_vector_mode;
  float coat_rough_map_location[3];
  float coat_rough_map_rotation[3];
  float coat_rough_map_scale[3];
  int coat_rough_map_type;
  /* Slice 2s: Coat IOR TEX_IMAGE (NULL/empty = constant 1.5) */
  const char *coat_ior_image_path;
  const char *coat_ior_image_colorspace;
  int coat_ior_tex_vector_mode;
  float coat_ior_map_location[3];
  float coat_ior_map_rotation[3];
  float coat_ior_map_scale[3];
  int coat_ior_map_type;
  /* Slice 2s: Coat Tint TEX_IMAGE (NULL/empty = Cycles default 1,1,1) */
  const char *coat_tint_image_path;
  const char *coat_tint_image_colorspace;
  int coat_tint_tex_vector_mode;
  float coat_tint_map_location[3];
  float coat_tint_map_rotation[3];
  float coat_tint_map_scale[3];
  int coat_tint_map_type;
  /* Slice 2s: Sheen Roughness TEX_IMAGE (NULL/empty = constant 0.5) */
  const char *sheen_rough_image_path;
  const char *sheen_rough_image_colorspace;
  int sheen_rough_tex_vector_mode;
  float sheen_rough_map_location[3];
  float sheen_rough_map_rotation[3];
  float sheen_rough_map_scale[3];
  int sheen_rough_map_type;
  /* Slice 2s: Sheen Tint TEX_IMAGE (NULL/empty = Cycles default 1,1,1) */
  const char *sheen_tint_image_path;
  const char *sheen_tint_image_colorspace;
  int sheen_tint_tex_vector_mode;
  float sheen_tint_map_location[3];
  float sheen_tint_map_rotation[3];
  float sheen_tint_map_scale[3];
  int sheen_tint_map_type;
  /* Slice 2t: Coat Normal Map Color ← TEX_IMAGE (NULL/empty = geometric Coat Normal) */
  const char *coat_normal_image_path;
  const char *coat_normal_image_colorspace;
  int coat_normal_tex_vector_mode;
  float coat_normal_map_location[3];
  float coat_normal_map_rotation[3];
  float coat_normal_map_scale[3];
  int coat_normal_map_type;
  float coat_normal_strength; /* Coat Normal Map Strength, default 1.0 */
  int coat_normal_space; /* QT_NORMAL_MAP_*: same encoding */
  /* Slice 2u: Specular Tint TEX_IMAGE (NULL/empty = Cycles default 1,1,1) */
  const char *spec_tint_image_path;
  const char *spec_tint_image_colorspace;
  int spec_tint_tex_vector_mode;
  float spec_tint_map_location[3];
  float spec_tint_map_rotation[3];
  float spec_tint_map_scale[3];
  int spec_tint_map_type;
  /* Slice 2u: Thin Film Thickness TEX_IMAGE (NULL/empty = constant 0) */
  const char *film_thick_image_path;
  const char *film_thick_image_colorspace;
  int film_thick_tex_vector_mode;
  float film_thick_map_location[3];
  float film_thick_map_rotation[3];
  float film_thick_map_scale[3];
  int film_thick_map_type;
  /* Slice 2u: Thin Film IOR TEX_IMAGE (NULL/empty = constant 1.33) */
  const char *film_ior_image_path;
  const char *film_ior_image_colorspace;
  int film_ior_tex_vector_mode;
  float film_ior_map_location[3];
  float film_ior_map_rotation[3];
  float film_ior_map_scale[3];
  int film_ior_map_type;
  /* Slice 2u: Subsurface Weight TEX_IMAGE (NULL/empty = constant 0) */
  const char *sss_weight_image_path;
  const char *sss_weight_image_colorspace;
  int sss_weight_tex_vector_mode;
  float sss_weight_map_location[3];
  float sss_weight_map_rotation[3];
  float sss_weight_map_scale[3];
  int sss_weight_map_type;
  /* Slice 2u: Subsurface Radius TEX_IMAGE (NULL/empty = constant 1,0.2,0.1) */
  const char *sss_radius_image_path;
  const char *sss_radius_image_colorspace;
  int sss_radius_tex_vector_mode;
  float sss_radius_map_location[3];
  float sss_radius_map_rotation[3];
  float sss_radius_map_scale[3];
  int sss_radius_map_type;
  /* Slice 2u: Subsurface Scale TEX_IMAGE (NULL/empty = constant 0.005) */
  const char *sss_scale_image_path;
  const char *sss_scale_image_colorspace;
  int sss_scale_tex_vector_mode;
  float sss_scale_map_location[3];
  float sss_scale_map_rotation[3];
  float sss_scale_map_scale[3];
  int sss_scale_map_type;
  /* Slice 2v: Subsurface IOR TEX_IMAGE (NULL/empty = constant 1.4) */
  const char *sss_ior_image_path;
  const char *sss_ior_image_colorspace;
  int sss_ior_tex_vector_mode;
  float sss_ior_map_location[3];
  float sss_ior_map_rotation[3];
  float sss_ior_map_scale[3];
  int sss_ior_map_type;
  /* Slice 2v: Subsurface Anisotropy TEX_IMAGE (NULL/empty = constant 0) */
  const char *sss_aniso_image_path;
  const char *sss_aniso_image_colorspace;
  int sss_aniso_tex_vector_mode;
  float sss_aniso_map_location[3];
  float sss_aniso_map_rotation[3];
  float sss_aniso_map_scale[3];
  int sss_aniso_map_type;
  /* Slice 2v: Thin Wall TEX_IMAGE reserved (BOOLEAN in 5.2; packer refuses) */
  const char *thin_wall_image_path;
  const char *thin_wall_image_colorspace;
  int thin_wall_tex_vector_mode;
  float thin_wall_map_location[3];
  float thin_wall_map_rotation[3];
  float thin_wall_map_scale[3];
  int thin_wall_map_type;
  /* Slice 2v: Diffuse Roughness TEX_IMAGE (NULL/empty = constant 0) */
  const char *diffuse_rough_image_path;
  const char *diffuse_rough_image_colorspace;
  int diffuse_rough_tex_vector_mode;
  float diffuse_rough_map_location[3];
  float diffuse_rough_map_rotation[3];
  float diffuse_rough_map_scale[3];
  int diffuse_rough_map_type;
  /* Slice 2w: Anisotropic TEX_IMAGE (NULL/empty = constant 0) */
  const char *aniso_image_path;
  const char *aniso_image_colorspace;
  int aniso_tex_vector_mode;
  float aniso_map_location[3];
  float aniso_map_rotation[3];
  float aniso_map_scale[3];
  int aniso_map_type;
  /* Slice 2w: Anisotropic Rotation TEX_IMAGE (NULL/empty = constant 0) */
  const char *aniso_rot_image_path;
  const char *aniso_rot_image_colorspace;
  int aniso_rot_tex_vector_mode;
  float aniso_rot_map_location[3];
  float aniso_rot_map_rotation[3];
  float aniso_rot_map_scale[3];
  int aniso_rot_map_type;
  /* Slice 2w: Tangent TEX_IMAGE (NULL/empty = LINK_TANGENT default) */
  const char *tangent_image_path;
  const char *tangent_image_colorspace;
  int tangent_tex_vector_mode;
  float tangent_map_location[3];
  float tangent_map_rotation[3];
  float tangent_map_scale[3];
  int tangent_map_type;
  /* Slice 2x: Bump Height ← TEX_IMAGE (NULL/empty = geometric Normal).
   * Strength/Distance unlinked floats (Blender 5.2 RNA: 1.0 / 0.001).
   * invert RNA 0/1. use_object_space always false (no Blender 5.2 RNA). */
  const char *bump_image_path;
  const char *bump_image_colorspace;
  int bump_tex_vector_mode;
  float bump_map_location[3];
  float bump_map_rotation[3];
  float bump_map_scale[3];
  int bump_map_type;
  float bump_strength;
  float bump_distance;
  int bump_invert;
  /* Slice 2y: Principled Thin Wall BOOLEAN + unlinked Transmission Weight.
   * thin_wall: 0/1 from unlinked BOOLEAN RNA default_value.
   * transmission_weight: unlinked Transmission Weight RNA default (0 if missing).
   * Linked Thin Wall still refuses (BOOLEAN, not TEX_IMAGE).
   * trans_image_path still wins when set (Slice 2p); do not also set the constant. */
  int thin_wall;
  float transmission_weight;
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
  int normal_space; /* QT_NORMAL_MAP_*: 0=TANGENT, 1=OBJECT, 2=WORLD */
  /* Slice 2o: IOR TEX_IMAGE */
  const char *ior_image_path;
  const char *ior_image_colorspace;
  int ior_tex_vector_mode;
  float ior_map_location[3];
  float ior_map_rotation[3];
  float ior_map_scale[3];
  int ior_map_type;
  /* Slice 2o: Alpha TEX_IMAGE */
  const char *alpha_image_path;
  const char *alpha_image_colorspace;
  int alpha_tex_vector_mode;
  float alpha_map_location[3];
  float alpha_map_rotation[3];
  float alpha_map_scale[3];
  int alpha_map_type;
  /* Slice 2p: Transmission Weight TEX_IMAGE */
  const char *trans_image_path;
  const char *trans_image_colorspace;
  int trans_tex_vector_mode;
  float trans_map_location[3];
  float trans_map_rotation[3];
  float trans_map_scale[3];
  int trans_map_type;
  /* Slice 2p: Specular IOR Level TEX_IMAGE */
  const char *spec_image_path;
  const char *spec_image_colorspace;
  int spec_tex_vector_mode;
  float spec_map_location[3];
  float spec_map_rotation[3];
  float spec_map_scale[3];
  int spec_map_type;
  /* Slice 2q: Coat Weight TEX_IMAGE */
  const char *coat_image_path;
  const char *coat_image_colorspace;
  int coat_tex_vector_mode;
  float coat_map_location[3];
  float coat_map_rotation[3];
  float coat_map_scale[3];
  int coat_map_type;
  /* Slice 2q: Sheen Weight TEX_IMAGE */
  const char *sheen_image_path;
  const char *sheen_image_colorspace;
  int sheen_tex_vector_mode;
  float sheen_map_location[3];
  float sheen_map_rotation[3];
  float sheen_map_scale[3];
  int sheen_map_type;
  /* Slice 2q: Emission Strength TEX_IMAGE */
  const char *emit_str_image_path;
  const char *emit_str_image_colorspace;
  int emit_str_tex_vector_mode;
  float emit_str_map_location[3];
  float emit_str_map_rotation[3];
  float emit_str_map_scale[3];
  int emit_str_map_type;
  /* Slice 2r: Emission Color TEX_IMAGE */
  const char *emit_color_image_path;
  const char *emit_color_image_colorspace;
  int emit_color_tex_vector_mode;
  float emit_color_map_location[3];
  float emit_color_map_rotation[3];
  float emit_color_map_scale[3];
  int emit_color_map_type;
  /* Slice 2s: Coat Roughness TEX_IMAGE (NULL/empty = constant 0.03) */
  const char *coat_rough_image_path;
  const char *coat_rough_image_colorspace;
  int coat_rough_tex_vector_mode;
  float coat_rough_map_location[3];
  float coat_rough_map_rotation[3];
  float coat_rough_map_scale[3];
  int coat_rough_map_type;
  /* Slice 2s: Coat IOR TEX_IMAGE (NULL/empty = constant 1.5) */
  const char *coat_ior_image_path;
  const char *coat_ior_image_colorspace;
  int coat_ior_tex_vector_mode;
  float coat_ior_map_location[3];
  float coat_ior_map_rotation[3];
  float coat_ior_map_scale[3];
  int coat_ior_map_type;
  /* Slice 2s: Coat Tint TEX_IMAGE (NULL/empty = Cycles default 1,1,1) */
  const char *coat_tint_image_path;
  const char *coat_tint_image_colorspace;
  int coat_tint_tex_vector_mode;
  float coat_tint_map_location[3];
  float coat_tint_map_rotation[3];
  float coat_tint_map_scale[3];
  int coat_tint_map_type;
  /* Slice 2s: Sheen Roughness TEX_IMAGE (NULL/empty = constant 0.5) */
  const char *sheen_rough_image_path;
  const char *sheen_rough_image_colorspace;
  int sheen_rough_tex_vector_mode;
  float sheen_rough_map_location[3];
  float sheen_rough_map_rotation[3];
  float sheen_rough_map_scale[3];
  int sheen_rough_map_type;
  /* Slice 2s: Sheen Tint TEX_IMAGE (NULL/empty = Cycles default 1,1,1) */
  const char *sheen_tint_image_path;
  const char *sheen_tint_image_colorspace;
  int sheen_tint_tex_vector_mode;
  float sheen_tint_map_location[3];
  float sheen_tint_map_rotation[3];
  float sheen_tint_map_scale[3];
  int sheen_tint_map_type;
  /* Slice 2t: Coat Normal Map Color ← TEX_IMAGE (NULL/empty = geometric Coat Normal) */
  const char *coat_normal_image_path;
  const char *coat_normal_image_colorspace;
  int coat_normal_tex_vector_mode;
  float coat_normal_map_location[3];
  float coat_normal_map_rotation[3];
  float coat_normal_map_scale[3];
  int coat_normal_map_type;
  float coat_normal_strength; /* Coat Normal Map Strength, default 1.0 */
  int coat_normal_space; /* QT_NORMAL_MAP_*: same encoding */
  /* Slice 2u: Specular Tint TEX_IMAGE (NULL/empty = Cycles default 1,1,1) */
  const char *spec_tint_image_path;
  const char *spec_tint_image_colorspace;
  int spec_tint_tex_vector_mode;
  float spec_tint_map_location[3];
  float spec_tint_map_rotation[3];
  float spec_tint_map_scale[3];
  int spec_tint_map_type;
  /* Slice 2u: Thin Film Thickness TEX_IMAGE (NULL/empty = constant 0) */
  const char *film_thick_image_path;
  const char *film_thick_image_colorspace;
  int film_thick_tex_vector_mode;
  float film_thick_map_location[3];
  float film_thick_map_rotation[3];
  float film_thick_map_scale[3];
  int film_thick_map_type;
  /* Slice 2u: Thin Film IOR TEX_IMAGE (NULL/empty = constant 1.33) */
  const char *film_ior_image_path;
  const char *film_ior_image_colorspace;
  int film_ior_tex_vector_mode;
  float film_ior_map_location[3];
  float film_ior_map_rotation[3];
  float film_ior_map_scale[3];
  int film_ior_map_type;
  /* Slice 2u: Subsurface Weight TEX_IMAGE (NULL/empty = constant 0) */
  const char *sss_weight_image_path;
  const char *sss_weight_image_colorspace;
  int sss_weight_tex_vector_mode;
  float sss_weight_map_location[3];
  float sss_weight_map_rotation[3];
  float sss_weight_map_scale[3];
  int sss_weight_map_type;
  /* Slice 2u: Subsurface Radius TEX_IMAGE (NULL/empty = constant 1,0.2,0.1) */
  const char *sss_radius_image_path;
  const char *sss_radius_image_colorspace;
  int sss_radius_tex_vector_mode;
  float sss_radius_map_location[3];
  float sss_radius_map_rotation[3];
  float sss_radius_map_scale[3];
  int sss_radius_map_type;
  /* Slice 2u: Subsurface Scale TEX_IMAGE (NULL/empty = constant 0.005) */
  const char *sss_scale_image_path;
  const char *sss_scale_image_colorspace;
  int sss_scale_tex_vector_mode;
  float sss_scale_map_location[3];
  float sss_scale_map_rotation[3];
  float sss_scale_map_scale[3];
  int sss_scale_map_type;
  /* Slice 2v: Subsurface IOR TEX_IMAGE (NULL/empty = constant 1.4) */
  const char *sss_ior_image_path;
  const char *sss_ior_image_colorspace;
  int sss_ior_tex_vector_mode;
  float sss_ior_map_location[3];
  float sss_ior_map_rotation[3];
  float sss_ior_map_scale[3];
  int sss_ior_map_type;
  /* Slice 2v: Subsurface Anisotropy TEX_IMAGE (NULL/empty = constant 0) */
  const char *sss_aniso_image_path;
  const char *sss_aniso_image_colorspace;
  int sss_aniso_tex_vector_mode;
  float sss_aniso_map_location[3];
  float sss_aniso_map_rotation[3];
  float sss_aniso_map_scale[3];
  int sss_aniso_map_type;
  /* Slice 2v: Thin Wall TEX_IMAGE reserved (BOOLEAN in 5.2; packer refuses) */
  const char *thin_wall_image_path;
  const char *thin_wall_image_colorspace;
  int thin_wall_tex_vector_mode;
  float thin_wall_map_location[3];
  float thin_wall_map_rotation[3];
  float thin_wall_map_scale[3];
  int thin_wall_map_type;
  /* Slice 2v: Diffuse Roughness TEX_IMAGE (NULL/empty = constant 0) */
  const char *diffuse_rough_image_path;
  const char *diffuse_rough_image_colorspace;
  int diffuse_rough_tex_vector_mode;
  float diffuse_rough_map_location[3];
  float diffuse_rough_map_rotation[3];
  float diffuse_rough_map_scale[3];
  int diffuse_rough_map_type;
  /* Slice 2w: Anisotropic TEX_IMAGE (NULL/empty = constant 0) */
  const char *aniso_image_path;
  const char *aniso_image_colorspace;
  int aniso_tex_vector_mode;
  float aniso_map_location[3];
  float aniso_map_rotation[3];
  float aniso_map_scale[3];
  int aniso_map_type;
  /* Slice 2w: Anisotropic Rotation TEX_IMAGE (NULL/empty = constant 0) */
  const char *aniso_rot_image_path;
  const char *aniso_rot_image_colorspace;
  int aniso_rot_tex_vector_mode;
  float aniso_rot_map_location[3];
  float aniso_rot_map_rotation[3];
  float aniso_rot_map_scale[3];
  int aniso_rot_map_type;
  /* Slice 2w: Tangent TEX_IMAGE (NULL/empty = LINK_TANGENT default) */
  const char *tangent_image_path;
  const char *tangent_image_colorspace;
  int tangent_tex_vector_mode;
  float tangent_map_location[3];
  float tangent_map_rotation[3];
  float tangent_map_scale[3];
  int tangent_map_type;
  /* Slice 2x: Bump Height ← TEX_IMAGE (NULL/empty = geometric Normal).
   * Strength/Distance unlinked floats (Blender 5.2 RNA: 1.0 / 0.001).
   * invert RNA 0/1. use_object_space always false (no Blender 5.2 RNA). */
  const char *bump_image_path;
  const char *bump_image_colorspace;
  int bump_tex_vector_mode;
  float bump_map_location[3];
  float bump_map_rotation[3];
  float bump_map_scale[3];
  int bump_map_type;
  float bump_strength;
  float bump_distance;
  int bump_invert;
  /* Slice 2y: Principled Thin Wall BOOLEAN + unlinked Transmission Weight. */
  int thin_wall;
  float transmission_weight;
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
#define QT_TEX_VECTOR_TEXCOORD_WINDOW       9 /* TEX_COORD Window → TEX_IMAGE Vector */
#define QT_TEX_VECTOR_MAPPING_WINDOW       10 /* TEX_COORD Window → Mapping → TEX_IMAGE */
#define QT_TEX_VECTOR_TEXCOORD_REFLECTION  11 /* TEX_COORD Reflection → TEX_IMAGE Vector */
#define QT_TEX_VECTOR_MAPPING_REFLECTION   12 /* TEX_COORD Reflection → Mapping → TEX_IMAGE */

/* Slice 2z: Normal Map space (ShaderNodeNormalMap.space) */
#define QT_NORMAL_MAP_TANGENT 0
#define QT_NORMAL_MAP_OBJECT  1
#define QT_NORMAL_MAP_WORLD   2


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
