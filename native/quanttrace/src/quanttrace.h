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
 * Slice 2bc: Bump Height ← TEX_NOISE Color/Factor (bump_noise_* after
 *   bump_invert). enable=0 keeps 2x bit-identical. Vector unlinked
 *   Generated. Same RNA as 2bb Noise. use_color 1=Color 0=Factor.
 * Slice 2az: Principled.Normal ← Bevel (samples + unlinked Radius). Optional
 *   Bevel.Normal ← NormalMap and/or Bump. When bump_* + normal_* both set,
 *   NormalMap → Bump.Normal → (Bevel?) → Principled (loft Metal_Sheet shape).
 *   bevel_enable=0 keeps 2x/2j bit-identical.
 * Slice 2ba: ColorRamp (VALTORGB) -> Principled.Roughness. Official
 *   intern/cycles/blender/util.h colorramp_to_array uses RAMP_TABLE_SIZE+1
 *   = 257 (evaluate i/256). interpolate=false only for CONSTANT; LINEAR/
 *   EASE/CARDINAL/B_SPLINE pack interpolate=true then lerp the LUT.
 *   Fac unlinked float OR Fac <- TEX_IMAGE (reuse rough_image_*). n==0
 *   skips RGBRampNode -- 2az/2i bit-identical. Noise/Fresnel/GROUP Fac
 *   named refuse. Connect Color -> Roughness (NODE_CONVERT_CF).
 * Slice 2z: Principled Normal Map space OBJECT + WORLD (plus Coat Normal space).
 *   0=TANGENT (default, 2j/2t bit-identical), 1=OBJECT, 2=WORLD.
 * Slice 2ad: BLENDER_OBJECT=3 / BLENDER_WORLD=4 (Cycles NODE_NORMAL_MAP_BLENDER_*).
 *   SVM flips color.y/z vs Object/World ("strange blender convention").
 * Slice 2aa: Environment Texture world (empty path = Slice 2b black).
 * Slice 2al: world Background Color constant ABI (world_color float3).
 *   Empty path + (0,0,0) = Slice 2b black. RGB / Mix-constant / unlinked
 *   non-black Color pack here; TEX_ENVIRONMENT still wins (color stays 0).
 * Slice 2am: Sky Texture → world Background Color (world_sky_* after world_color).
 *   type 0 = 2al/2aa bit-identical. 1=PREETHAM 2=HOSEK 3=NISHITA/MULTIPLE
 *   4=SINGLE_SCATTERING (Blender 5.2 RNA). Path empty, world_color zeros.
 *   Mode 0: Vector unlinked (LINK_TEXTURE_GENERATED).
 * Slice 2ar: linked Sky Vector via world_tex_vector_mode + world_map_* +
 *   world_ob_* (TEX_COORD / Mapping, same as env 2ac/2ae). Mode 0 keeps
 *   2am bit-identical.
 * Slice 2as: ShaderNodeRGBCurve → world Background Color as packed LUT
 *   (world_curves / world_curves_n / min_x / max_x / fac / extrapolate after
 *   world_mix_clamp_result). n==0 / NULL skips native RGBCurvesNode —
 *   2ar/2aq/2al bit-identical. Official Cycles curvemapping_color_to_array
 *   (RAMP_TABLE_SIZE=256 → 257 entries; DNA cm[0]=R..cm[3]=I). Fac==0 also
 *   skips (Cycles folds). Chain: Color → RGBCurves → Gamma → HSV → BC →
 *   Mix → Background.
 * Slice 2at: 3-deep constant Math → world Strength (same world_strength float
 *   ABI; no new C fields). Fold max depth 3 (2ai was 2). Identity 0–2-deep
 *   graphs bit-identical. 4-deep Math still refuses.
 * Slice 2au: TEX_ENVIRONMENT×0 MULTIPLY now accepted (folds to 0.0; then
 *   outer DIV/ADD). Same world_strength float ABI; no new C fields.
 *   Non-zero tex Math / ADD/SUB/DIV/POWER with tex Color still refuse.
 * Slice 2av: Mapping vector_type POINT accepted on env/sky/teximage Vector
 *   (and mesh TEX_IMAGE). Same world_map_type int ABI; 0=POINT 2=VECTOR.
 *   Native already set_mapping_type. TEXTURE/NORMAL still refuse.
 * Slice 2aw: QT_MAX_MESHES 2048 / QT_MAX_LIGHTS 128 (was 32/16). Caps are
 *   validation only — QT_Scene.meshes/lights stay heap pointers.
 * Slice 2ax: Gamma + HueSat on Principled Base Color (base_gamma +
 *   base_hsv_* after tex_ob_tfm on QT_Mesh / QT_SimpleScene mesh section).
 *   Identity (gamma=1, hue=0.5, sat=1, val=1, fac=1) skips native nodes —
 *   2f TEX_IMAGE cubes stay bit-identical. Color → Gamma → HSV → Base Color
 *   (cite shader_nodes.h GammaNode/HSVNode; same as world 2ao). Mix on Base
 *   Color still refuses (named Slice 2ax).
 * Slice 2bd: ShaderNodeRGBCurve → Principled Base Color as packed LUT
 *   (base_curves / n / min_x / max_x / fac / extrapolate after last
 *   base_mix_*). n==0 / NULL / fac==0 skips native RGBCurvesNode —
 *   2ay/2ax/2f bit-identical. Official Cycles curvemapping_color_to_array
 *   (RAMP_TABLE_SIZE=256 → 257; DNA cm[0]=R..cm[3]=I). Native:
 *   Color → Gamma → HSV → Mix → RGBCurves → Principled Base Color
 *   (Curves closest to Principled — loft Concrete_Facade). Linked Fac /
 *   second Curves / Vector Curves / Float Curve refuse Slice 2bd.
 * Slice 2be: InvertNode → Principled.Roughness (rough_invert_enable /
 *   rough_invert_fac after last rough_ramp_noise_*). enable=0 skips
 *   InvertNode — 2ba/2bb/2i bit-identical. Cite shader_nodes.h InvertNode
 *   (set_fac; Color in-out). Fac unlinked; Color <- TEX_IMAGE or ColorRamp.
 *   Color → Roughness via NODE_CONVERT_CF (linear_rgb_to_gray). Linked Fac /
 *   nested Invert / GROUP / Mix / Noise Color refuse Slice 2be.
 * Slice 2bl: SeparateColorNode channel → Bump Height
 *   (bump_separate_enable / bump_separate_channel after bump_noise_*).
 * Slice 2bm: GlassBsdfNode (glass_bsdf_enable / glass_distribution
 *   after rough_separate_*). enable=0 keeps Principled bit-identical.
 *   enable=0 skips SeparateColorNode — 2bc/2x bit-identical.
 *   Cite SeparateColorNode set_color_type NODE_COMBSEP_COLOR_RGB;
 *   float channel → Height. Loft Sideboard: Blue ← TEX_IMAGE Color.
 * Slice 2bj: SeparateColorNode channel → Principled.Roughness
 *   (rough_separate_enable / rough_separate_channel after rough_invert_*).
 *   enable=0 skips SeparateColorNode — 2be/2ba/2bb/2i bit-identical.
 *   channel 0=Red 1=Green 2=Blue (RGB only). Color <- TEX_IMAGE Color.
 *   Cite SeparateColorNode set_color_type NODE_COMBSEP_COLOR_RGB;
 *   float channel → Roughness (no NODE_CONVERT_CF).
 * Slice 2bf: MixColorNode Factor ← FresnelNode (base_mix_fresnel_enable /
 *   base_mix_fresnel_ior after last base_mix_*). enable=0 keeps 2ay unlinked
 *   Fac bit-identical. Cite shader_nodes.h FresnelNode set_IOR; Normal
 *   unlinked LINK_NORMAL. MixColorNode Factor socket (not Fac). Linked
 *   Fresnel Normal/IOR, TEX_IMAGE/Noise/LayerWeight/GROUP/Geometry Fac refuse.
 * Slice 2bi: Normal Map Color ← Combine+InvertG Separate←TEX_IMAGE
 *   (normal_invert_g_* / coat_normal_invert_g_* after base_mix_curves_*).
 *   enable=0 keeps 2j bit-identical.
 * Slice 2bh: RGB Curves ← TEX_IMAGE on Mix A/B (base_mix_curves_* after
 *   last base_curves_*). n==0 / NULL / fac==0 skips mix-side RGBCurvesNode
 *   — 2bg/2ay/2bf/2bd bit-identical. Native: ImageTexture → RGBCurves →
 *   Mix A or B; other Mix input stays 2ay; then 2bd Curves-after-Mix if
 *   base_curves_n>0. Cite RGBCurvesNode set_curves/set_min_x/set_max_x/
 *   set_fac/set_extrapolate. MixColorNode Factor socket is Factor not Fac.
 *   Do not reuse base_curves_* (different graph position).
 * Slice 2an: ShaderNodeTexImage → world Background Color (world_color_image_*
 *   after world_sky_ozone_density). Empty path = 2aa/2al/2am bit-identical.
 *   Priority: env path → sky → color-image → world_color RGB. Vector via
 *   world_tex_vector_mode + world_map_* + world_ob_* (same as 2ac/2ae).
 * Slice 2ao: Gamma + Hue Saturation Value on world Background Color
 *   (world_gamma + world_hsv_* after world_color_image_projection).
 *   Identity (gamma=1, hue=0.5, sat=1, val=1, fac=1) skips native nodes —
 *   2aa/2al/2am/2an bit-identical. Non-identity wires ccl::GammaNode then
 *   ccl::HSVNode (loft order: Color source → Gamma → HSV → Background).
 *   If only HSV, skip Gamma. If only Gamma, skip HSV.
 * Slice 2ap: Bright/Contrast on world Background Color (world_bright /
 *   world_contrast after world_hsv_fac). Identity (bright=0, contrast=0)
 *   skips BrightContrastNode — 2ao/2an/2am/2aa/2al bit-identical. Loft
 *   order: Color → Gamma → HSV → BrightContrast → Background. Cite
 *   shader_nodes.h BrightContrastNode (set_bright, set_contrast).
 * Slice 2aq: Mix after world Color chain → Background Color (world_mix_*
 *   after world_contrast). type 0 = skip MixColorNode — 2ap/2ao/2an/2am/
 *   2aa/2al bit-identical. Chain → Mix (A or B) + constant other →
 *   Background. Cite shader_nodes.h MixColorNode (blend_type, fac, a, b,
 *   use_clamp, use_clamp_result). ShaderNodeMix data_type RGBA / MixRGB;
 *   MIX/ADD/SUBTRACT/MULTIPLY/DIVIDE only.
 * Slice 2ab: TEX_COORD Object-with-pointer (use_transform + ob_tfm).
 *   Empty Object ref (2l) stays use_transform=false / NODE_TEXCO_OBJECT.
 *   Pointer set → NODE_TEXCO_OBJECT_WITH_TRANSFORM + packed inverse of ob_tfm.
 *   Mesh-level: one Object reference per mesh. Do not invert twice.
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

/* Slice 2aw pack caps — validation only (QT_Scene.meshes/lights are
 * heap pointers from ctypes; not fixed C arrays / stack / BSS).
 * 2048 meshes covers loft (~1200) with headroom; 128 lights ditto.
 */
#define QT_MAX_MESHES 2048
#define QT_MAX_LIGHTS 128

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
  float world_strength; /* Background Strength; Color = world_color when path empty */
  /* Slice 2aa: Environment Texture world (NULL/empty path = Slice 2b black) */
  const char *world_image_path;
  const char *world_image_colorspace;
  int world_projection; /* 0=EQUIRECTANGULAR, 1=MIRROR_BALL */
  /* Slice 2ac: Environment Texture Vector (0=unlinked LINK_POSITION) */
  int world_tex_vector_mode; /* QT_TEX_VECTOR_* (Generated/Mapping focus) */
  float world_map_location[3];
  float world_map_rotation[3];
  float world_map_scale[3];
  int world_map_type;
  /* Slice 2ae: Env TEX_COORD Object-with-pointer (world-level; 0 = 2ac empty-ref) */
  int world_ob_use_transform; /* 0 = empty Object (bit-identical 2ac). 1 = pointer */
  float world_ob_tfm[12];     /* Blender matrix_world first 3 rows; ignore if 0 */
  float world_color[3]; /* Slice 2al: Background Color RGB when world_image_path empty. Default 0,0,0 = Slice 2b black. */
  /* Slice 2am: Sky Texture (0=none → 2al/2aa). Path empty, color stays 0. */
  int world_sky_type;  /* 0=none, 1=PREETHAM, 2=HOSEK, 3=NISHITA/MULTIPLE, 4=SINGLE */
  float world_sky_sun_direction[3];
  float world_sky_turbidity, world_sky_ground_albedo;
  int world_sky_sun_disc;
  float world_sky_sun_size, world_sky_sun_intensity, world_sky_sun_elevation, world_sky_sun_rotation;
  float world_sky_altitude, world_sky_air_density, world_sky_aerosol_density, world_sky_ozone_density;
  /* Slice 2an: Image Texture → Background Color (NULL/empty = not 2an) */
  const char *world_color_image_path;
  const char *world_color_image_colorspace; /* OCIO name; empty = node default */
  int world_color_image_projection; /* 0=FLAT, 1=BOX, 2=SPHERE, 3=TUBE */
  /* Slice 2ao: Gamma + HSV on world Color. Identity skips native nodes. */
  float world_gamma;     /* 1.0 = skip GammaNode */
  float world_hsv_hue;   /* 0.5 = identity */
  float world_hsv_sat;   /* 1.0 = identity */
  float world_hsv_val;   /* 1.0 = identity */
  float world_hsv_fac;   /* 1.0 = identity */
  /* Slice 2ap: Bright/Contrast on world Color. Identity skips native node. */
  float world_bright;    /* 0.0 = identity */
  float world_contrast;  /* 0.0 = identity */
  /* Slice 2aq: Mix after Color chain. type 0 = skip MixColorNode. */
  int world_mix_type; /* 0=none 1=MIX 2=ADD 3=SUBTRACT 4=MULTIPLY 5=DIVIDE */
  float world_mix_fac; /* unlinked Factor; default 0.5 when type!=0 */
  float world_mix_other[3]; /* constant RGB on non-chain side */
  int world_mix_chain_is_a; /* 1 = chain→A other→B; 0 = chain→B other→A */
  int world_mix_clamp_factor; /* MixColorNode use_clamp */
  int world_mix_clamp_result; /* MixColorNode use_clamp_result */
  /* Slice 2as: RGB Curves LUT (NULL / n==0 = skip RGBCurvesNode). */
  const float *world_curves; /* n * 3 RGB floats; NULL / n==0 = skip */
  int world_curves_n;
  float world_curves_min_x;  /* default 0 */
  float world_curves_max_x;  /* default 1 */
  float world_curves_fac;    /* default 1 */
  int world_curves_extrapolate; /* default 1 */
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
  int normal_space; /* QT_NORMAL_MAP_*: 0=TANGENT..4=BLENDER_WORLD */
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
  /* Slice 2bk: Specular Tint RGB (Cycles default 1,1,1). Constant Mix folds
   * here (Python-only). Mix chain fallback when mix_type!=0 and no TEX_IMAGE. */
  float specular_tint[3];
  /* Slice 2bk: MixColorNode → Specular Tint (subset of base_mix_*; no fresnel/curves).
   * type 0 = skip Mix — 2u TEX_IMAGE / constant bit-identical. */
  int spec_tint_mix_type;
  float spec_tint_mix_fac;
  float spec_tint_mix_other[3];
  int spec_tint_mix_chain_is_a;
  int spec_tint_mix_clamp_factor;
  int spec_tint_mix_clamp_result;
  const char *spec_tint_mix_b_image_path;
  const char *spec_tint_mix_b_image_colorspace;
  /* Slice 2bk: Gamma + HueSat on Specular Tint chain (before Mix). Identity
   * (gamma=1, hue=0.5, sat=1, val=1, fac=1) skips — 2u bit-identical. */
  float spec_tint_gamma;
  float spec_tint_hsv_hue;
  float spec_tint_hsv_sat;
  float spec_tint_hsv_val;
  float spec_tint_hsv_fac;
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
  /* Slice 2bc: NoiseTextureNode → Bump Height. enable=0 keeps 2x
   * bit-identical (TEX_IMAGE Height). Vector unlinked Generated.
   * Pack Blender 5.2 RNA Cycles uses (same as rough_ramp_noise_*).
   * use_color 1 = Color, 0 = Factor (NODE_CONVERT_CF if Color). */
  int bump_noise_enable;
  int bump_noise_dimensions;
  int bump_noise_type;
  int bump_noise_normalize;
  float bump_noise_w;
  float bump_noise_scale;
  float bump_noise_detail;
  float bump_noise_roughness;
  float bump_noise_lacunarity;
  float bump_noise_offset;
  float bump_noise_gain;
  float bump_noise_distortion;
  int bump_noise_use_color;
  /* Slice 2bl: SeparateColorNode channel → Bump Height.
   * enable=0 skips SeparateColorNode — 2bc/2x bit-identical.
   * channel 0=Red 1=Green 2=Blue (loft Sideboard Blue).
   * Cite SeparateColorNode set_color_type NODE_COMBSEP_COLOR_RGB;
   * float channel → Height (no NODE_CONVERT_CF). */
  int bump_separate_enable;
  int bump_separate_channel;
  /* Slice 2y: Principled Thin Wall BOOLEAN + unlinked Transmission Weight.
   * thin_wall: 0/1 from unlinked BOOLEAN RNA default_value.
   * transmission_weight: unlinked Transmission Weight RNA default (0 if missing).
   * Linked Thin Wall still refuses (BOOLEAN, not TEX_IMAGE).
   * trans_image_path still wins when set (Slice 2p); do not also set the constant. */
  int thin_wall;
  float transmission_weight;
  /* Slice 2ab: TEX_COORD Object pointer (mesh-level). 0 = 2l empty-ref. */
  int tex_ob_use_transform; /* 0 = empty Object (bit-identical 2l). 1 = pointer */
  float tex_ob_tfm[12];     /* Blender matrix_world first 3 rows; ignore if 0 */
  /* Slice 2ax: Gamma + HSV on Principled Base Color. Identity skips nodes. */
  float base_gamma;     /* default 1.0; skip GammaNode when ==1 */
  float base_hsv_hue;   /* default 0.5 */
  float base_hsv_sat;   /* default 1.0 */
  float base_hsv_val;   /* default 1.0 */
  float base_hsv_fac;   /* default 1.0; skip HSVNode when identity */
  /* Slice 2ay: MixColorNode on Principled Base Color (mesh analog of world 2aq).
   * type 0 = skip Mix (2ax/2f bit-identical). 1=MIX 2=ADD 3=SUB 4=MUL 5=DIV.
   * Empty base_mix_b_image_path = constant other (base_mix_other).
   * Nonempty B path = second ImageTextureNode (same Vector as primary); ignore other. */
  int base_mix_type;
  float base_mix_fac;
  float base_mix_other[3];
  int base_mix_chain_is_a; /* 1 = chain→A other/B-image→B; 0 = reverse */
  int base_mix_clamp_factor;
  int base_mix_clamp_result;
  const char *base_mix_b_image_path;
  const char *base_mix_b_image_colorspace;
  /* Slice 2bf: FresnelNode → MixColorNode Factor. enable=0 = unlinked Fac
   * (2ay bit-identical). IOR unlinked float (Blender 5.2 RNA 1.45).
   * Normal unlinked (LINK_NORMAL geometric). */
  int base_mix_fresnel_enable;
  float base_mix_fresnel_ior;
  /* Slice 2bd: RGB Curves LUT → Principled Base Color (mesh analog of world 2as).
   * NULL / n==0 / fac==0 skips RGBCurvesNode — 2ay/2ax/2f bit-identical.
   * Official Cycles curvemapping_color_to_array (RAMP_TABLE_SIZE=256 → 257). */
  const float *base_curves; /* n * 3 RGB floats; NULL / n==0 = skip */
  int base_curves_n;
  float base_curves_min_x;  /* default 0 */
  float base_curves_max_x;  /* default 1 */
  float base_curves_fac;    /* default 1 */
  int base_curves_extrapolate; /* default 1 */
  /* Slice 2bh: RGB Curves LUT on Mix A or B (not base_curves_* after Mix).
   * NULL / n==0 / fac==0 skips mix-side RGBCurvesNode — 2bg/2ay/2bf/2bd
   * bit-identical. Official Cycles curvemapping_color_to_array (257).
   * on_a 1 = wrap Mix A; 0 = wrap Mix B. One LUT only. */
  const float *base_mix_curves; /* n * 3 RGB floats; NULL / n==0 = skip */
  int base_mix_curves_n;
  float base_mix_curves_min_x;  /* default 0 */
  float base_mix_curves_max_x;  /* default 1 */
  float base_mix_curves_fac;    /* default 1 */
  int base_mix_curves_extrapolate; /* default 1 */
  int base_mix_curves_on_a; /* 1 = Mix A, 0 = Mix B; unused when n==0 */
  /* Slice 2bi: Normal Map Color <- Combine RGB with Invert on Green of
   * SeparateColor <- TEX_IMAGE (DirectX Y-flip). enable=0 skips
   * Separate/Invert/Combine — 2j TEX_IMAGE Color bit-identical.
   * Cite SeparateColorNode / InvertNode / CombineColorNode (RGB mode).
   * Fac unlinked float (Cycles InvertNode default 1.0). */
  int normal_invert_g_enable;
  float normal_invert_g_fac;
  int coat_normal_invert_g_enable;
  float coat_normal_invert_g_fac;
  /* Slice 2az: Bevel → Principled.Normal (0 = off, bit-identical 2ay/2x/2j).
   * samples default 4; radius unlinked float (Blender 5.2 RNA 0.05).
   * Nested Normal via bump_* / normal_* (NormalMap → Bump.Normal OK). */
  int bevel_enable;
  int bevel_samples;
  float bevel_radius;
  /* Slice 2ba: ColorRamp -> Principled.Roughness. n==0 / NULL = skip
   * (2az/2i bit-identical). n * 3 RGB + n alpha. interpolate 1=lerp
   * 0=CONSTANT. Fac unlinked (rough_ramp_fac) unless rough_image_path
   * nonempty (then Fac <- existing 2i TEX_IMAGE). */
  const float *rough_ramp;
  const float *rough_ramp_alpha;
  int rough_ramp_n;
  int rough_ramp_interpolate;
  float rough_ramp_fac;
  /* Slice 2bb: NoiseTextureNode -> RGBRampNode Fac. enable=0 keeps 2ba
   * bit-identical (unlinked Fac float or TEX_IMAGE Color).
   * Vector unlinked Generated (LINK_TEXTURE_GENERATED). Pack Blender 5.2
   * RNA that Cycles uses: dimensions 1..4, type NodeNoiseType, normalize,
   * W/Scale/Detail/Roughness/Lacunarity/Offset/Gain/Distortion unlinked.
   * use_color 0 = Fac, 1 = Color (NODE_CONVERT_CF). */
  int rough_ramp_noise_enable;
  int rough_ramp_noise_dimensions;
  int rough_ramp_noise_type;
  int rough_ramp_noise_normalize;
  float rough_ramp_noise_w;
  float rough_ramp_noise_scale;
  float rough_ramp_noise_detail;
  float rough_ramp_noise_roughness;
  float rough_ramp_noise_lacunarity;
  float rough_ramp_noise_offset;
  float rough_ramp_noise_gain;
  float rough_ramp_noise_distortion;
  int rough_ramp_noise_use_color;
  /* Slice 2be: InvertNode -> Principled.Roughness. enable=0 skips InvertNode
   * (2ba/2bb/2i bit-identical). Fac unlinked float (Cycles default 1.0).
   * Color source is existing 2i TEX_IMAGE or 2ba ColorRamp. */
  int rough_invert_enable;
  float rough_invert_fac;
  /* Slice 2bj: SeparateColorNode channel -> Principled.Roughness.
   * enable=0 skips SeparateColorNode — 2be/2ba/2bb/2i bit-identical.
   * channel 0=Red 1=Green 2=Blue (RGB mode only). Color <- TEX_IMAGE Color
   * (or Python-folded constant). Cite SeparateColorNode set_color_type
   * NODE_COMBSEP_COLOR_RGB; float channel -> Roughness (no CF convert). */
  int rough_separate_enable;
  int rough_separate_channel;
  /* Slice 2bm: GlassBsdfNode surface (pure Glass → Material Output).
   * enable=0 keeps Principled path bit-identical (all prior slices).
   * distribution: 0=Beckmann 1=GGX 2=Multi-GGX (ClosureType glass IDs).
   * Color/Roughness/IOR reuse base_color / roughness / ior.
   * Cite Cycles shader_nodes.h GlassBsdfNode. */
  int glass_bsdf_enable;
  int glass_distribution;
  /* Slice 2bn: MixClosureNode + optional LightPathNode Fac
   * (mix_shader_* after glass_*). enable=0 keeps 2bm Glass->Output
   * bit-identical. Classic artist glass: Mix Fac=Light Path Is Shadow
   * Ray (or unlinked float), Closure1/2 = Glass + Transparent.
   * Cite MixClosureNode, LightPathNode, GlassBsdfNode,
   * TransparentBsdfNode. Do not evaluate Light Path at pack time. */
  int mix_shader_enable;
  float mix_shader_fac;
  int mix_shader_lightpath_enable;
  int mix_shader_lightpath_output; /* QT_LIGHTPATH_* */
  int mix_closure1_kind; /* 0=Glass 1=Transparent 2=NestedMix (Slice 2bp) */
  int mix_closure2_kind; /* 0=Glass 1=Transparent 2=NestedMix (Slice 2bp) */
  float mix_transparent_color[3];
  /* Slice 2bo: Mix Fac ← MATH Light Path nest (after mix_transparent_color).
   * enable=0 keeps 2bn bit-identical (unlinked Fac or single LightPath).
   * Binary Math tree, max nest 2 (root + one inner on A and/or B).
   * kind 0=unlinked float/Value 1=LightPath 2=nested Math.
   * Cite MathNode Value1/Value2/Value + LightPathNode Ray Depth (float). */
  int mix_shader_math_enable;
  int mix_shader_math_op;
  int mix_shader_math_a_kind;
  float mix_shader_math_a_const;
  int mix_shader_math_a_lightpath;
  int mix_shader_math_a_op;
  int mix_shader_math_a1_kind;
  float mix_shader_math_a1_const;
  int mix_shader_math_a1_lightpath;
  int mix_shader_math_a2_kind;
  float mix_shader_math_a2_const;
  int mix_shader_math_a2_lightpath;
  int mix_shader_math_b_kind;
  float mix_shader_math_b_const;
  int mix_shader_math_b_lightpath;
  int mix_shader_math_b_op;
  int mix_shader_math_b1_kind;
  float mix_shader_math_b1_const;
  int mix_shader_math_b1_lightpath;
  int mix_shader_math_b2_kind;
  float mix_shader_math_b2_const;
  int mix_shader_math_b2_lightpath;
  /* Slice 2bp: one nested MixClosure hop (after mix_shader_math_*).
   * mix_closure*_kind 2 = NestedMix on that outer side.
   * When kinds stay 0/1, bit-identical to Slice 2bo.
   * Nested Fac: unlinked float or LightPath (not MATH this turn).
   * Nested leaves: Glass+Transparent only (kinds 0/1).
   * Cite MixClosureNode nesting; GlassBsdfNode; TransparentBsdfNode. */
  float mix_nested_fac;
  int mix_nested_lightpath_enable;
  int mix_nested_lightpath_output; /* QT_LIGHTPATH_* */
  int mix_nested_closure1_kind; /* 0=Glass 1=Transparent */
  int mix_nested_closure2_kind; /* 0=Glass 1=Transparent */
} QT_SimpleScene;

QT_EXPORT int quanttrace_render_scene_rgba(const QT_SimpleScene *scene,
                                           float *out_rgba,
                                           int out_capacity,
                                           int *out_w,
                                           int *out_h);

/* Slice 2c: N meshes + N AREA lights (constant Principled per mesh).
 * Caps: QT_MAX_MESHES / QT_MAX_LIGHTS (Slice 2aw: 2048/128; heap pointers).
 * AREA + POINT + SUN + SPOT.
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
  int normal_space; /* QT_NORMAL_MAP_*: 0=TANGENT..4=BLENDER_WORLD */
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
  /* Slice 2bk: Specular Tint RGB (Cycles default 1,1,1). Constant Mix folds
   * here (Python-only). Mix chain fallback when mix_type!=0 and no TEX_IMAGE. */
  float specular_tint[3];
  /* Slice 2bk: MixColorNode → Specular Tint (subset of base_mix_*; no fresnel/curves).
   * type 0 = skip Mix — 2u TEX_IMAGE / constant bit-identical. */
  int spec_tint_mix_type;
  float spec_tint_mix_fac;
  float spec_tint_mix_other[3];
  int spec_tint_mix_chain_is_a;
  int spec_tint_mix_clamp_factor;
  int spec_tint_mix_clamp_result;
  const char *spec_tint_mix_b_image_path;
  const char *spec_tint_mix_b_image_colorspace;
  /* Slice 2bk: Gamma + HueSat on Specular Tint chain (before Mix). Identity
   * (gamma=1, hue=0.5, sat=1, val=1, fac=1) skips — 2u bit-identical. */
  float spec_tint_gamma;
  float spec_tint_hsv_hue;
  float spec_tint_hsv_sat;
  float spec_tint_hsv_val;
  float spec_tint_hsv_fac;
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
  /* Slice 2bc: NoiseTextureNode → Bump Height. enable=0 keeps 2x
   * bit-identical (TEX_IMAGE Height). Vector unlinked Generated.
   * Pack Blender 5.2 RNA Cycles uses (same as rough_ramp_noise_*).
   * use_color 1 = Color, 0 = Factor (NODE_CONVERT_CF if Color). */
  int bump_noise_enable;
  int bump_noise_dimensions;
  int bump_noise_type;
  int bump_noise_normalize;
  float bump_noise_w;
  float bump_noise_scale;
  float bump_noise_detail;
  float bump_noise_roughness;
  float bump_noise_lacunarity;
  float bump_noise_offset;
  float bump_noise_gain;
  float bump_noise_distortion;
  int bump_noise_use_color;
  /* Slice 2bl: SeparateColorNode channel → Bump Height.
   * enable=0 skips SeparateColorNode — 2bc/2x bit-identical.
   * channel 0=Red 1=Green 2=Blue (loft Sideboard Blue).
   * Cite SeparateColorNode set_color_type NODE_COMBSEP_COLOR_RGB;
   * float channel → Height (no NODE_CONVERT_CF). */
  int bump_separate_enable;
  int bump_separate_channel;
  /* Slice 2y: Principled Thin Wall BOOLEAN + unlinked Transmission Weight. */
  int thin_wall;
  float transmission_weight;
  /* Slice 2ab: TEX_COORD Object pointer (mesh-level). 0 = 2l empty-ref. */
  int tex_ob_use_transform; /* 0 = empty Object (bit-identical 2l). 1 = pointer */
  float tex_ob_tfm[12];     /* Blender matrix_world first 3 rows; ignore if 0 */
  /* Slice 2ax: Gamma + HSV on Principled Base Color. Identity skips nodes. */
  float base_gamma;     /* default 1.0; skip GammaNode when ==1 */
  float base_hsv_hue;   /* default 0.5 */
  float base_hsv_sat;   /* default 1.0 */
  float base_hsv_val;   /* default 1.0 */
  float base_hsv_fac;   /* default 1.0; skip HSVNode when identity */
  /* Slice 2ay: MixColorNode on Principled Base Color (mesh analog of world 2aq).
   * type 0 = skip. Empty B path = constant other; nonempty = second TEX_IMAGE. */
  int base_mix_type;
  float base_mix_fac;
  float base_mix_other[3];
  int base_mix_chain_is_a;
  int base_mix_clamp_factor;
  int base_mix_clamp_result;
  const char *base_mix_b_image_path;
  const char *base_mix_b_image_colorspace;
  /* Slice 2bf: FresnelNode → MixColorNode Factor. enable=0 = unlinked Fac
   * (2ay bit-identical). IOR unlinked float (Blender 5.2 RNA 1.45).
   * Normal unlinked (LINK_NORMAL geometric). */
  int base_mix_fresnel_enable;
  float base_mix_fresnel_ior;
  /* Slice 2bd: RGB Curves LUT → Principled Base Color (mesh analog of world 2as).
   * NULL / n==0 / fac==0 skips RGBCurvesNode — 2ay/2ax/2f bit-identical.
   * Official Cycles curvemapping_color_to_array (RAMP_TABLE_SIZE=256 → 257). */
  const float *base_curves; /* n * 3 RGB floats; NULL / n==0 = skip */
  int base_curves_n;
  float base_curves_min_x;  /* default 0 */
  float base_curves_max_x;  /* default 1 */
  float base_curves_fac;    /* default 1 */
  int base_curves_extrapolate; /* default 1 */
  /* Slice 2bh: RGB Curves LUT on Mix A or B (not base_curves_* after Mix).
   * NULL / n==0 / fac==0 skips mix-side RGBCurvesNode — 2bg/2ay/2bf/2bd
   * bit-identical. Official Cycles curvemapping_color_to_array (257).
   * on_a 1 = wrap Mix A; 0 = wrap Mix B. One LUT only. */
  const float *base_mix_curves; /* n * 3 RGB floats; NULL / n==0 = skip */
  int base_mix_curves_n;
  float base_mix_curves_min_x;  /* default 0 */
  float base_mix_curves_max_x;  /* default 1 */
  float base_mix_curves_fac;    /* default 1 */
  int base_mix_curves_extrapolate; /* default 1 */
  int base_mix_curves_on_a; /* 1 = Mix A, 0 = Mix B; unused when n==0 */
  /* Slice 2bi: Normal Map Color <- Combine RGB with Invert on Green of
   * SeparateColor <- TEX_IMAGE (DirectX Y-flip). enable=0 skips
   * Separate/Invert/Combine — 2j TEX_IMAGE Color bit-identical.
   * Cite SeparateColorNode / InvertNode / CombineColorNode (RGB mode).
   * Fac unlinked float (Cycles InvertNode default 1.0). */
  int normal_invert_g_enable;
  float normal_invert_g_fac;
  int coat_normal_invert_g_enable;
  float coat_normal_invert_g_fac;
  /* Slice 2az: Bevel → Principled.Normal (0 = off, bit-identical 2ay/2x/2j).
   * samples default 4; radius unlinked float (Blender 5.2 RNA 0.05).
   * Nested Normal via bump_* / normal_* (NormalMap → Bump.Normal OK). */
  int bevel_enable;
  int bevel_samples;
  float bevel_radius;
  /* Slice 2ba: ColorRamp -> Principled.Roughness (same layout as QT_SimpleScene). */
  const float *rough_ramp;
  const float *rough_ramp_alpha;
  int rough_ramp_n;
  int rough_ramp_interpolate;
  float rough_ramp_fac;
  /* Slice 2bb: NoiseTextureNode -> RGBRampNode Fac. enable=0 keeps 2ba
   * bit-identical (unlinked Fac float or TEX_IMAGE Color).
   * Vector unlinked Generated (LINK_TEXTURE_GENERATED). Pack Blender 5.2
   * RNA that Cycles uses: dimensions 1..4, type NodeNoiseType, normalize,
   * W/Scale/Detail/Roughness/Lacunarity/Offset/Gain/Distortion unlinked.
   * use_color 0 = Fac, 1 = Color (NODE_CONVERT_CF). */
  int rough_ramp_noise_enable;
  int rough_ramp_noise_dimensions;
  int rough_ramp_noise_type;
  int rough_ramp_noise_normalize;
  float rough_ramp_noise_w;
  float rough_ramp_noise_scale;
  float rough_ramp_noise_detail;
  float rough_ramp_noise_roughness;
  float rough_ramp_noise_lacunarity;
  float rough_ramp_noise_offset;
  float rough_ramp_noise_gain;
  float rough_ramp_noise_distortion;
  int rough_ramp_noise_use_color;
  /* Slice 2be: InvertNode -> Principled.Roughness. enable=0 skips InvertNode
   * (2ba/2bb/2i bit-identical). Fac unlinked float (Cycles default 1.0).
   * Color source is existing 2i TEX_IMAGE or 2ba ColorRamp. */
  int rough_invert_enable;
  float rough_invert_fac;
  /* Slice 2bj: SeparateColorNode channel -> Principled.Roughness.
   * enable=0 skips SeparateColorNode — 2be/2ba/2bb/2i bit-identical.
   * channel 0=Red 1=Green 2=Blue (RGB mode only). Color <- TEX_IMAGE Color
   * (or Python-folded constant). Cite SeparateColorNode set_color_type
   * NODE_COMBSEP_COLOR_RGB; float channel -> Roughness (no CF convert). */
  int rough_separate_enable;
  int rough_separate_channel;
  /* Slice 2bm: GlassBsdfNode surface (pure Glass → Material Output).
   * enable=0 keeps Principled path bit-identical (all prior slices).
   * distribution: 0=Beckmann 1=GGX 2=Multi-GGX (ClosureType glass IDs).
   * Color/Roughness/IOR reuse base_color / roughness / ior.
   * Cite Cycles shader_nodes.h GlassBsdfNode. */
  int glass_bsdf_enable;
  int glass_distribution;
  /* Slice 2bn: MixClosureNode + optional LightPathNode Fac
   * (mix_shader_* after glass_*). enable=0 keeps 2bm Glass->Output
   * bit-identical. Classic artist glass: Mix Fac=Light Path Is Shadow
   * Ray (or unlinked float), Closure1/2 = Glass + Transparent.
   * Cite MixClosureNode, LightPathNode, GlassBsdfNode,
   * TransparentBsdfNode. Do not evaluate Light Path at pack time. */
  int mix_shader_enable;
  float mix_shader_fac;
  int mix_shader_lightpath_enable;
  int mix_shader_lightpath_output; /* QT_LIGHTPATH_* */
  int mix_closure1_kind; /* 0=Glass 1=Transparent 2=NestedMix (Slice 2bp) */
  int mix_closure2_kind; /* 0=Glass 1=Transparent 2=NestedMix (Slice 2bp) */
  float mix_transparent_color[3];
  /* Slice 2bo: Mix Fac ← MATH Light Path nest (after mix_transparent_color).
   * enable=0 keeps 2bn bit-identical. Same layout as QT_SimpleScene. */
  int mix_shader_math_enable;
  int mix_shader_math_op;
  int mix_shader_math_a_kind;
  float mix_shader_math_a_const;
  int mix_shader_math_a_lightpath;
  int mix_shader_math_a_op;
  int mix_shader_math_a1_kind;
  float mix_shader_math_a1_const;
  int mix_shader_math_a1_lightpath;
  int mix_shader_math_a2_kind;
  float mix_shader_math_a2_const;
  int mix_shader_math_a2_lightpath;
  int mix_shader_math_b_kind;
  float mix_shader_math_b_const;
  int mix_shader_math_b_lightpath;
  int mix_shader_math_b_op;
  int mix_shader_math_b1_kind;
  float mix_shader_math_b1_const;
  int mix_shader_math_b1_lightpath;
  int mix_shader_math_b2_kind;
  float mix_shader_math_b2_const;
  int mix_shader_math_b2_lightpath;
  /* Slice 2bp: one nested MixClosure hop (same layout as QT_SimpleScene). */
  float mix_nested_fac;
  int mix_nested_lightpath_enable;
  int mix_nested_lightpath_output;
  int mix_nested_closure1_kind;
  int mix_nested_closure2_kind;
} QT_Mesh;

/* Light kinds for QT_Light.kind */
#define QT_LIGHT_AREA  0
#define QT_LIGHT_POINT 1
#define QT_LIGHT_SUN   2
#define QT_LIGHT_SPOT  3

/* Slice 2bn/2bo: LightPathNode float outputs.
 * 0..6 Is * Ray (2bn). 7..9 Ray Length / Ray Depth / Transparent Depth (2bo).
 * Ray Depth is a float out, not Is * Ray (cite shader_nodes.cpp LightPathNode). */
#define QT_LIGHTPATH_CAMERA_RAY        0
#define QT_LIGHTPATH_SHADOW_RAY        1
#define QT_LIGHTPATH_DIFFUSE_RAY       2
#define QT_LIGHTPATH_GLOSSY_RAY        3
#define QT_LIGHTPATH_SINGULAR_RAY      4
#define QT_LIGHTPATH_REFLECTION_RAY    5
#define QT_LIGHTPATH_TRANSMISSION_RAY  6
#define QT_LIGHTPATH_RAY_LENGTH          7
#define QT_LIGHTPATH_RAY_DEPTH           8
#define QT_LIGHTPATH_TRANSPARENT_DEPTH   9

/* Slice 2bo: Math input kind (Fac MATH tree). */
#define QT_MATH_IN_CONST      0
#define QT_MATH_IN_LIGHTPATH  1
#define QT_MATH_IN_NEST       2

/* Slice 2bb: NodeNoiseType (kernel/svm/types.h order). */
#define QT_NOISE_MULTIFRACTAL           0
#define QT_NOISE_FBM                    1
#define QT_NOISE_HYBRID_MULTIFRACTAL    2
#define QT_NOISE_RIDGED_MULTIFRACTAL    3
#define QT_NOISE_HETERO_TERRAIN         4

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

/* Slice 2z/2ad: Normal Map space (ShaderNodeNormalMap.space / Cycles NodeNormalMapSpace) */
#define QT_NORMAL_MAP_TANGENT         0
#define QT_NORMAL_MAP_OBJECT          1
#define QT_NORMAL_MAP_WORLD           2
#define QT_NORMAL_MAP_BLENDER_OBJECT  3
#define QT_NORMAL_MAP_BLENDER_WORLD   4


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
  /* Slice 2aa: Environment Texture world (NULL/empty path = Slice 2b black) */
  const char *world_image_path;
  const char *world_image_colorspace;
  int world_projection; /* 0=EQUIRECTANGULAR, 1=MIRROR_BALL */
  /* Slice 2ac: Environment Texture Vector (0=unlinked LINK_POSITION) */
  int world_tex_vector_mode; /* QT_TEX_VECTOR_* */
  float world_map_location[3];
  float world_map_rotation[3];
  float world_map_scale[3];
  int world_map_type;
  /* Slice 2ae: Env TEX_COORD Object-with-pointer (world-level; 0 = 2ac empty-ref) */
  int world_ob_use_transform; /* 0 = empty Object (bit-identical 2ac). 1 = pointer */
  float world_ob_tfm[12];     /* Blender matrix_world first 3 rows; ignore if 0 */
  float world_color[3]; /* Slice 2al: Background Color RGB when world_image_path empty. Default 0,0,0 = Slice 2b black. */
  /* Slice 2am: Sky Texture (0=none → 2al/2aa). Path empty, color stays 0. */
  int world_sky_type;  /* 0=none, 1=PREETHAM, 2=HOSEK, 3=NISHITA/MULTIPLE, 4=SINGLE */
  float world_sky_sun_direction[3];
  float world_sky_turbidity, world_sky_ground_albedo;
  int world_sky_sun_disc;
  float world_sky_sun_size, world_sky_sun_intensity, world_sky_sun_elevation, world_sky_sun_rotation;
  float world_sky_altitude, world_sky_air_density, world_sky_aerosol_density, world_sky_ozone_density;
  /* Slice 2an: Image Texture → Background Color (NULL/empty = not 2an) */
  const char *world_color_image_path;
  const char *world_color_image_colorspace; /* OCIO name; empty = node default */
  int world_color_image_projection; /* 0=FLAT, 1=BOX, 2=SPHERE, 3=TUBE */
  /* Slice 2ao: Gamma + HSV on world Color. Identity skips native nodes. */
  float world_gamma;     /* 1.0 = skip GammaNode */
  float world_hsv_hue;   /* 0.5 = identity */
  float world_hsv_sat;   /* 1.0 = identity */
  float world_hsv_val;   /* 1.0 = identity */
  float world_hsv_fac;   /* 1.0 = identity */
  /* Slice 2ap: Bright/Contrast on world Color. Identity skips native node. */
  float world_bright;    /* 0.0 = identity */
  float world_contrast;  /* 0.0 = identity */
  /* Slice 2aq: Mix after Color chain. type 0 = skip MixColorNode. */
  int world_mix_type; /* 0=none 1=MIX 2=ADD 3=SUBTRACT 4=MULTIPLY 5=DIVIDE */
  float world_mix_fac; /* unlinked Factor; default 0.5 when type!=0 */
  float world_mix_other[3]; /* constant RGB on non-chain side */
  int world_mix_chain_is_a; /* 1 = chain→A other→B; 0 = chain→B other→A */
  int world_mix_clamp_factor; /* MixColorNode use_clamp */
  int world_mix_clamp_result; /* MixColorNode use_clamp_result */
  /* Slice 2as: RGB Curves LUT (NULL / n==0 = skip RGBCurvesNode). */
  const float *world_curves; /* n * 3 RGB floats; NULL / n==0 = skip */
  int world_curves_n;
  float world_curves_min_x;  /* default 0 */
  float world_curves_max_x;  /* default 1 */
  float world_curves_fac;    /* default 1 */
  int world_curves_extrapolate; /* default 1 */
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
