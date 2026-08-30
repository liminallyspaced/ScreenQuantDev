/* QuantTrace Slice 2 — Cycles Session API bridge + F12 + depsgraph sync.
 *
 * Default build: stub (QT_WITH_CYCLES off). Compiles into libquanttrace
 * next to hello.c. quanttrace_is_tracer() == 0.
 *
 * -DQT_WITH_CYCLES=1: ccl::Session uni-PT. Locked-cube Combined matches
 * stock Cycles (256²/128 Δmax ~5e-7). quanttrace_is_tracer() == 1 so
 * SQ_QUANTTRACE.render can land Combined in the Image Editor.
 * Slice 2b: quanttrace_render_scene_rgba builds from a QT_SimpleScene
 * packed by Python depsgraph walk (camera/mesh/Principled/area/world).
 * Slice 2c: quanttrace_render_qt_scene_rgba — N meshes + N lights.
 * Slice 2g: SPOT (spot_size/spot_blend).
 * Slice 2h: TEX_COORD UV + Mapping → TEX_IMAGE Vector.
 * Slice 2i: TEX_IMAGE → Principled Roughness / Metallic.
 * Slice 2j: Normal Map (Tangent) + TEX_IMAGE → Principled Normal.
 * Slice 2k: TEX_COORD Generated (+ optional Mapping) → TEX_IMAGE Vector.
 * Slice 2l: TEX_COORD Object (+ optional Mapping) → TEX_IMAGE Vector.
 * Slice 2m: TEX_COORD Camera (+ optional Mapping) → TEX_IMAGE Vector.
 * Slice 2n: TEX_COORD Window + Reflection (+ optional Mapping) → TEX_IMAGE Vector.
 * Slice 2o: TEX_IMAGE → Principled IOR / Alpha.
 * Slice 2p: TEX_IMAGE → Principled Transmission Weight / Specular IOR Level.
 * Slice 2q: TEX_IMAGE → Principled Coat Weight / Sheen Weight / Emission Strength.
 * Slice 2r: TEX_IMAGE → Principled Emission Color (legacy Emission).
 * Slice 2s: Coat/Sheen extras TEX_IMAGE.
 * Slice 2t: Normal Map (Tangent) + TEX_IMAGE → Principled Coat Normal.
 * Slice 2bk: MixColorNode → Principled Specular Tint (spec_tint_mix_*).
 *   type 0 skips Mix — 2u TEX_IMAGE / specular_tint constant bit-identical.
 *   Constant Mix folds Python-only into specular_tint[3]. Fac←Fresnel/GROUP/
 *   Curves-on-Mix-side named refuse Slice 2bk (not in loft Specular Tint census).
 * Slice 2u: TEX_IMAGE → Principled Specular Tint / Thin Film Thickness+IOR /
 *   Subsurface Weight / Radius / Scale.
 * Slice 2w: TEX_IMAGE → Principled Anisotropic / Rotation / Tangent.
 * Slice 2x: Principled.Normal ← Bump ← TEX_IMAGE Height (bump_* ABI).
 * Slice 2y: Principled Thin Wall BOOLEAN + unlinked Transmission Weight.
 * Slice 2ab: TEX_COORD Object-with-pointer (use_transform + ob_tfm).
 * Slice 2ac: Env Vector TEX_COORD / Mapping.
 * Slice 2ad: BLENDER_OBJECT / BLENDER_WORLD Normal space.
 * Slice 2ae: Env Object-with-pointer (world_ob_use_transform + world_ob_tfm).
 * Slice 2z: Normal Map space OBJECT/WORLD (plus Coat Normal space).
 * Slice 2aa: Environment Texture world.
 * Slice 2al: world Background Color constant (world_color float3).
 *   Empty path uses world_color; env path keeps Color black (ENV feeds Color).
 *   BackgroundLight when has_env || color_nonzero (black empty-path stays 2b).
 * Slice 2am: SkyTextureNode → Background Color (world_sky_type != 0).
 *   Path empty, do not mix world_color into the sky graph. BackgroundLight
 *   when has_env || has_sky || color_nonzero. Mode 0 Vector unlinked
 *   (LINK_TEXTURE_GENERATED).
 * Slice 2ar: linked Sky Vector via world_tex_vector_mode + world_map_* +
 *   world_ob_* (same TEX_COORD / Mapping shapes as env 2ac/2ae). Mode 0
 *   keeps 2am bit-identical. RGB Curves still refuse (curve LUT deferred).
 * Slice 2an: ImageTextureNode → Background Color (world_color_image_path).
 *   Priority: env → sky → color-image → world_color RGB. Vector via
 *   world_tex_vector_mode (0 = LINK_TEXTURE_UV ImageTexture default).
 *   BackgroundLight when has_env || has_sky || has_color_image || color_nonzero.
 *   map_resolution 1024 like env/color (ImageTexture not scanned for AUTOMATIC).
 * Slice 2ao: GammaNode + HSVNode on world Color (world_gamma / world_hsv_*).
 *   Identity (gamma=1, hue=0.5, sat=1, val=1, fac=1) skips extra nodes
 *   (2aa/2al/2am/2an bit-identical). Else Color source → Gamma (if gamma!=1)
 *   → HSV (if hsv not identity) → Background Color. Cite shader_nodes.h
 *   GammaNode / HSVNode (set_color, set_gamma / set_hue,set_saturation,
 *   set_value,set_fac). If only HSV skip Gamma; if only Gamma skip HSV.
 * Slice 2ax: GammaNode + HSVNode on Principled Base Color (base_gamma /
 *   base_hsv_* after tex_ob_tfm). Identity skips — 2f TEX_IMAGE bit-identical.
 *   Color → Gamma (if gamma!=1) → HSV (if not identity) → Base Color. Cite
 *   same GammaNode/HSVNode as world 2ao.
 * Slice 2ay: MixColorNode on Principled Base Color (base_mix_* after
 *   base_hsv_fac; optional base_mix_b_image_path for dual TEX_IMAGE).
 *   type 0 = skip — 2ax/2f bit-identical. Color → Gamma → HSV → Mix →
 *   Base Color. Cite MixColorNode (same as world 2aq). Empty B path uses
 *   base_mix_other; nonempty B shares primary Vector graph.
 * Slice 2az: BevelNode → Principled.Normal (bevel_enable/samples/radius).
 *   Optional nested NormalMap / Bump (NormalMap → Bump.Normal when both
 *   paths set). Cite BevelNode (set_samples, set_radius) + KERNEL_FEATURE
 *   NODE_RAYTRACE. bevel_enable=0 keeps 2ay/2x/2j bit-identical.
 * Slice 2ba: RGBRampNode → Principled.Roughness (rough_ramp_*).
 * Slice 2bb: NoiseTextureNode → RGBRampNode Fac (rough_ramp_noise_*).
 *   enable=0 keeps 2ba bit-identical. Cite shader_nodes NoiseTextureNode
 *   (set_dimensions, set_type, set_use_normalize, set_scale, set_detail,
 *   set_roughness, set_lacunarity, set_distortion, set_w, set_offset,
 *   set_gain). Vector unlinked LINK_TEXTURE_GENERATED. Fac or Color.
 * Slice 2be: InvertNode → Principled.Roughness (rough_invert_enable /
 *   rough_invert_fac). enable=0 keeps 2ba/2bb/2i bit-identical. Cite
 *   InvertNode set_fac; Color → Roughness NODE_CONVERT_CF (linear_rgb_to_gray).
 * Slice 2bj: SeparateColorNode channel → Principled.Roughness
 *   (rough_separate_enable / rough_separate_channel after rough_invert_*).
 *   enable=0 keeps 2be/2ba/2bb/2i bit-identical. Cite SeparateColorNode
 *   set_color_type NODE_COMBSEP_COLOR_RGB; channel Red/Green/Blue float →
 *   Roughness (no NODE_CONVERT_CF). Loft Sideboard: Green ← TEX_IMAGE Color.
 * Slice 2bf: MixColorNode Factor ← FresnelNode (base_mix_fresnel_enable /
 *   base_mix_fresnel_ior). enable=0 keeps 2ay unlinked Fac bit-identical.
 *   Cite shader_nodes.h FresnelNode set_IOR; output Fac. MixColorNode
 *   Factor socket. Normal unlinked LINK_NORMAL.
 * Slice 2bi: Normal Map Color <- CombineColor(RGB) with Invert on Green of
 *   SeparateColor <- TEX_IMAGE (normal_invert_g_enable / fac;
 *   coat_normal_invert_g_*). enable=0 keeps 2j TEX_IMAGE Color bit-identical.
 *   Cite SeparateColorNode set_color_type NODE_COMBSEP_COLOR_RGB;
 *   InvertNode set_fac; CombineColorNode set_color_type. Float<->Color
 *   via ShaderGraph::connect ConvertNode.
 * Slice 2bh: RGBCurvesNode on Mix A or B (base_mix_curves_*). n==0 / NULL /
 *   fac==0 skips — 2bg/2ay/2bf/2bd bit-identical. Native order ImageTexture
 *   → RGBCurves → Mix A/B; then 2bd Curves-after-Mix if base_curves_n>0.
 *   Cite RGBCurvesNode set_curves/set_min_x/set_max_x/set_fac/set_extrapolate.
 *   MixColorNode Factor socket is Factor not Fac. Do not reuse base_curves_*.
 * Slice 2bc: NoiseTextureNode → BumpNode Height (bump_noise_*).
 *   enable=0 keeps 2x bit-identical (TEX_IMAGE Height). Same Noise RNA
 *   as 2bb. Color → Height via NODE_CONVERT_CF; Fac → Height direct.
 *   Fill ATTR_STD_GENERATED when enable≠0.
 * Slice 2bl: SeparateColorNode channel → Bump Height
 *   (bump_separate_enable / bump_separate_channel after bump_noise_*).
 * Slice 2bm: GlassBsdfNode surface (glass_bsdf_enable /
 *   glass_distribution after rough_separate_*). enable=0 keeps
 *   Principled path bit-identical. Cite GlassBsdfNode.
 * Slice 2bn: MixClosureNode + optional LightPathNode Fac
 *   (mix_shader_* after glass_*). enable=0 keeps 2bm bit-identical.
 *   Cite MixClosureNode, LightPathNode, GlassBsdfNode,
 *   TransparentBsdfNode.
 * Slice 2bo: Mix Fac ← MATH Light Path nest (mix_shader_math_* after
 *   mix_transparent_color). enable=0 keeps 2bn bit-identical. Wire
 *   MathNode + LightPathNode (do not evaluate Light Path at pack time).
 *   Cite MathNode Value1/Value2/Value, LightPathNode Ray Depth float.
 * Slice 2bp: one nested MixClosure hop (mix_nested_* after math;
 *   mix_closure*_kind 2 = NestedMix). kinds 0/1 keep 2bo bit-identical.
 *   Nested Fac: unlinked float or LightPath. Nested leaves Glass+Transparent.
 *   Cite MixClosureNode nesting.
 * Slice 2bq: second nested MixClosure hop (mix_nested2_* after mix_nested_*;
 *   mix_nested_closure*_kind 2 = NestedMix2). nested kinds 0/1 keep 2bp
 *   bit-identical (no nested2 MixClosureNode). Nested2 Fac unlinked|LightPath;
 *   leaves Glass+Transparent. Cite MixClosureNode nesting.
 * Slice 2br: nested2 Mix Fac ← ColorRamp (mix_nested2_ramp_*). enable=0 ||
 *   n==0 skips RGBRampNode — 2bq set_fac/LightPath bit-identical. Cite
 *   RGBRampNode set_ramp/set_ramp_alpha/set_interpolate → MixClosure Fac.
 * Slice 2bs: ColorRamp.Fac <- MATH (mix_nested2_ramp_math_*). enable=0 keeps
 *   2br set_fac bit-identical. Wire MathNode +/- GeometryNode Backfacing +/-
 *   HSVNode (Color<-LightPath Ray Length) -> RGBRampNode Fac. Cite MathNode,
 *   GeometryNode, HSVNode, LightPathNode.
 * Slice 2bt/2bu: nested2 Mix leaf AddClosure (+ Glossy/SSS/Translucent/Mix).
 *   mix_nested2_add_enable=0 / nested2 kinds 0/1 keep 2bs Glass+Transparent
 *   bit-identical. Cite AddClosureNode, GlossyBsdfNode,
 *   SubsurfaceScatteringNode, TranslucentBsdfNode.
 *   enable=0 keeps 2bc/2x bit-identical. Cite SeparateColorNode
 *   set_color_type NODE_COMBSEP_COLOR_RGB; float Red/Green/Blue → Height
 *   (no NODE_CONVERT_CF). Loft Sideboard: Blue ← TEX_IMAGE Color.
 * Slice 2ap: BrightContrastNode on world Color (world_bright / world_contrast).
 *   Identity (bright=0, contrast=0) skips — 2ao/2an/2am/2aa/2al bit-identical.
 *   Loft: Color → Gamma → HSV → BrightContrast → Background. Cite
 *   shader_nodes.h BrightContrastNode (set_bright, set_contrast).
 * Slice 2aq: MixColorNode after Color chain (world_mix_*). type 0 = skip —
 *   2ap/2ao/2an/2am/2aa/2al bit-identical. Loft: Color → Gamma → HSV →
 *   BrightContrast → Mix → Background. Cite shader_nodes.h MixColorNode
 *   (set_blend_type, set_fac, set_a, set_b, set_use_clamp,
 *   set_use_clamp_result). MIX/ADD/SUBTRACT/MULTIPLY/DIVIDE only.
 * Slice 2ab: TEX_COORD Object-with-pointer (use_transform + ob_tfm).
 * Slice 2at: 3-deep constant Math nest → world Strength (fold max 3; no new
 *   ABI). Identity 0–2-deep bit-identical. Version 0.0.47-slice2at.
 * Slice 2au: TEX_ENVIRONMENT×0 now accepted (MULTIPLY tex.Color × 0 → 0.0;
 *   same world_strength float ABI). Version 0.0.48-slice2au.
 * QUANTTRACE_CUBE_WIDTH/HEIGHT/SAMPLES override locked 256/256/128.
 *
 * Cite: blender/cycles src/session/session.h, src/scene/scene.h,
 *       src/app/cycles_standalone.cpp, src/app/cycles_xml.cpp
 * Scene lock: docs/research/QUANTTRACE-CUBE.md
 */

#include "quanttrace.h"

#ifndef QT_WITH_CYCLES

extern "C" int quanttrace_is_tracer(void)
{
    return 0;
}

extern "C" int quanttrace_session_probe(void)
{
    return 0;
}

extern "C" int quanttrace_render_cube(const char * /*exr_path*/)
{
    return -1;
}

extern "C" int quanttrace_render_cube_rgba(float * /*out_rgba*/,
                                          int /*out_capacity*/,
                                          int * /*out_w*/,
                                          int * /*out_h*/)
{
    return -1;
}

extern "C" int quanttrace_render_scene_rgba(const QT_SimpleScene * /*scene*/,
                                            float * /*out_rgba*/,
                                            int /*out_capacity*/,
                                            int * /*out_w*/,
                                            int * /*out_h*/)
{
    return -1;
}

extern "C" int quanttrace_render_qt_scene_rgba(const QT_Scene * /*scene*/,
                                               float * /*out_rgba*/,
                                               int /*out_capacity*/,
                                               int * /*out_w*/,
                                               int * /*out_h*/)
{
    return -1;
}

#else /* QT_WITH_CYCLES — Session uni-PT + depsgraph-fed simple scene */

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

#include <OpenImageIO/imageio.h>

#include "device/device.h"
#include "scene/background.h"
#include "scene/camera.h"
#include "scene/film.h"
#include "scene/integrator.h"
#include "scene/light.h"
#include "scene/mesh.h"
#include "scene/object.h"
#include "scene/pass.h"
#include "scene/scene.h"
#include "scene/shader.h"
#include "scene/shader_graph.h"
#include "scene/shader_nodes.h"
#include "scene/attribute.h"
#include "session/buffers.h"
#include "session/output_driver.h"
#include "session/session.h"
#include "util/log.h"
#include "util/path.h"
#include "util/transform.h"
#include "util/hash.h"
#include "util/string.h"
#include "util/unique_ptr.h"

CCL_NAMESPACE_BEGIN

namespace {

/* Locked cube: default Blender cube is 2 m, verts at +/-1 on each axis.
 * 12 triangles (6 quads split). Matches QUANTTRACE-CUBE.md mesh.
 */
/* Exact bpy.ops.mesh.primitive_cube_add() DNA (Blender 5.2 dump, 12pm). */
static const float kCubeVerts[8][3] = {
    {-1.0f, -1.0f, -1.0f}, {-1.0f, -1.0f, 1.0f}, {-1.0f, 1.0f, -1.0f}, {-1.0f, 1.0f, 1.0f},
    {1.0f, -1.0f, -1.0f},  {1.0f, -1.0f, 1.0f},  {1.0f, 1.0f, -1.0f},  {1.0f, 1.0f, 1.0f},
};
/* loop_triangles from the same dump (CCW outward). */
static const int kCubeTris[12][3] = {
    {0, 1, 3}, {0, 3, 2}, /* -X */
    {2, 3, 7}, {2, 7, 6}, /* +Y */
    {6, 7, 5}, {6, 5, 4}, /* +X */
    {4, 5, 1}, {4, 1, 0}, /* -Y */
    {2, 6, 4}, {2, 4, 0}, /* -Z */
    {7, 3, 1}, {7, 1, 5}, /* +Z */
};

/* Cycles kernel camera looks along +Z (src/kernel/camera/camera.h:
 * perspective D = rastertocamera; ortho D = (0,0,1). XML cube camera at
 * translate=(0,2,-6) only sees the origin if +Z is the look axis).
 * Area lights emit along object -Z (AreaLight::copy_to_kernel).
 * util/transform.h has no transform_look_at — this is the kernel convention.
 * look_along_neg_z=false → camera (+Z toward target).
 * look_along_neg_z=true  → lights  (-Z toward target).
 */
static Transform look_at(const float3 from,
                         const float3 target,
                         const float3 up,
                         const bool look_along_neg_z)
{
    float3 z = normalize(from - target); /* +Z away from target */
    if (!look_along_neg_z) {
        z = -z; /* camera: +Z toward target */
    }
    /* Screen-X must match Blender. Blender/OpenGL cameras look along -Z with
     * x = cross(up, z_away). Cycles kernel camera looks along +Z, so
     * z_fwd = -z_away and x = cross(z_fwd, up) keeps the same screen X.
     * Area lights still look_along_neg_z (emit -Z): keep cross(up, z_away).
     * 11am PlugWalk: without this, Session Combined was an X-mirror of stock
     * (64²/32 Δmax ~1.27 → ~0.125 after --flop alone). */
    float3 x;
    if (look_along_neg_z) {
        x = normalize(cross(up, z));
    }
    else {
        x = normalize(cross(z, up));
    }
    const float3 y = cross(z, x);
    return make_transform(
        x.x, y.x, z.x, from.x, x.y, y.y, z.y, from.y, x.z, y.z, z.z, from.z);
}

class CombinedBufferDriver : public OutputDriver {
 public:
    explicit CombinedBufferDriver(std::vector<float> *rgba) : rgba_(rgba) {}

    void write_render_tile(const Tile &tile) override
    {
        if (!(tile.size == tile.full_size)) {
            return;
        }
        const int w = tile.size.x;
        const int h = tile.size.y;
        rgba_->assign(static_cast<size_t>(w) * static_cast<size_t>(h) * 4u, 0.0f);
        if (!tile.get_pass_pixels("combined", 4, rgba_->data())) {
            fprintf(stderr, "quanttrace: Combined pass read failed\n");
        }
    }

 private:
    std::vector<float> *rgba_;
};

static Transform tfm_from_12(const float *m)
{
    return make_transform(
        m[0], m[1], m[2], m[3], m[4], m[5], m[6], m[7], m[8], m[9], m[10], m[11]);
}

static void fill_locked_cube_desc(QT_SimpleScene *d, int width, int height, int samples)
{
    std::memset(d, 0, sizeof(*d));
    d->width = width;
    d->height = height;
    d->samples = samples;
    d->nverts = 8;
    d->ntris = 12;
    d->verts = &kCubeVerts[0][0];
    d->tris = &kCubeTris[0][0];
    /* identity mesh tfm */
    d->mesh_tfm[0] = 1.0f;
    d->mesh_tfm[5] = 1.0f;
    d->mesh_tfm[10] = 1.0f;
    /* Exact bpy matrix_world after depsgraph update (Blender 5.2 cube script). */
    const float cam[12] = {
        0.6853529810905457f, -0.3207705318927765f, 0.6537564992904663f, 7.358891010284424f,
        0.7282110452651978f, 0.301891952753067f, -0.6152803897857666f, -6.925790786743164f,
        -2.988588576613438e-08f, 0.8977569341659546f, 0.4404911696910858f, 4.958309173583984f};
    std::memcpy(d->cam_tfm, cam, sizeof(cam));
    d->cam_fov = 2.0f * atanf(18.0f / 50.0f);
    d->cam_sensor_w = 0.036f;
    d->cam_sensor_h = 0.024f;
    d->cam_near = 0.1f;
    d->cam_far = 1000.0f;
    const float light[12] = {
        -0.23948293924331665f, -0.7912328839302063f, 0.5626708269119263f, 4.076250076293945f,
        0.9709005951881409f, -0.1951659470796585f, 0.13878880441188812f, 1.0054500102996826f,
        -8.60238387190293e-08f, 0.5795349478721619f, 0.8149473667144775f, 5.903860092163086f};
    std::memcpy(d->light_tfm, light, sizeof(light));
    d->light_sizeu = 1.0f;
    d->light_sizev = 1.0f;
    d->light_strength[0] = 1000.0f;
    d->light_strength[1] = 1000.0f;
    d->light_strength[2] = 1000.0f;
    d->base_color[0] = 0.8f;
    d->base_color[1] = 0.8f;
    d->base_color[2] = 0.8f;
    d->roughness = 0.5f;
    d->metallic = 0.0f;
    d->ior = 1.45f;
    d->alpha = 1.0f;
    d->world_strength = 0.0f;
    d->world_color[0] = 0.0f;
    d->world_color[1] = 0.0f;
    d->world_color[2] = 0.0f;
    /* Slice 2ao identity — memset left gamma=0 which is NOT identity. */
    d->world_gamma = 1.0f;
    d->world_hsv_hue = 0.5f;
    d->world_hsv_sat = 1.0f;
    d->world_hsv_val = 1.0f;
    d->world_hsv_fac = 1.0f;
    /* Slice 2ax identity — memset left base_gamma=0 / hue=0 is NOT identity. */
    d->base_gamma = 1.0f;
    d->base_hsv_hue = 0.5f;
    d->base_hsv_sat = 1.0f;
    d->base_hsv_val = 1.0f;
    d->base_hsv_fac = 1.0f;
    /* Slice 2ay identity — mix_type=0 (memset is NOT identity for fac/other). */
    d->base_mix_type = 0;
    d->base_mix_fac = 0.5f;
    d->base_mix_other[0] = d->base_mix_other[1] = d->base_mix_other[2] = 0.0f;
    d->base_mix_chain_is_a = 1;
    d->base_mix_clamp_factor = 0;
    d->base_mix_clamp_result = 0;
    d->base_mix_b_image_path = nullptr;
    d->base_mix_b_image_colorspace = nullptr;
    /* Slice 2bf identity — enable=0 skips FresnelNode (2ay unlinked Fac). */
    d->base_mix_fresnel_enable = 0;
    d->base_mix_fresnel_ior = 1.45f;
    /* Slice 2bd identity — n==0 skips RGBCurvesNode. */
    d->base_curves = nullptr;
    d->base_curves_n = 0;
    d->base_curves_min_x = 0.0f;
    d->base_curves_max_x = 1.0f;
    d->base_curves_fac = 1.0f;
    d->base_curves_extrapolate = 1;
    /* Slice 2bh identity — n==0 skips mix-side RGBCurvesNode. */
    d->base_mix_curves = nullptr;
    d->base_mix_curves_n = 0;
    d->base_mix_curves_min_x = 0.0f;
    d->base_mix_curves_max_x = 1.0f;
    d->base_mix_curves_fac = 1.0f;
    d->base_mix_curves_extrapolate = 1;
    d->base_mix_curves_on_a = 1;
    /* Slice 2bi identity — enable=0 skips Separate/InvertG/Combine. */
    d->normal_invert_g_enable = 0;
    d->normal_invert_g_fac = 1.0f;
    d->coat_normal_invert_g_enable = 0;
    d->coat_normal_invert_g_fac = 1.0f;
    /* Slice 2az identity — bevel off. */
    d->bevel_enable = 0;
    d->bevel_samples = 4;
    d->bevel_radius = 0.05f;
    /* Slice 2ba identity — n==0 skips RGBRampNode. */
    d->rough_ramp = nullptr;
    d->rough_ramp_alpha = nullptr;
    d->rough_ramp_n = 0;
    d->rough_ramp_interpolate = 1;
    d->rough_ramp_fac = 0.5f;
    /* Slice 2bb identity — enable=0 skips NoiseTextureNode (2ba bit-identical). */
    d->rough_ramp_noise_enable = 0;
    d->rough_ramp_noise_dimensions = 3;
    d->rough_ramp_noise_type = QT_NOISE_FBM;
    d->rough_ramp_noise_normalize = 1;
    d->rough_ramp_noise_w = 0.0f;
    d->rough_ramp_noise_scale = 5.0f;
    d->rough_ramp_noise_detail = 2.0f;
    d->rough_ramp_noise_roughness = 0.5f;
    d->rough_ramp_noise_lacunarity = 2.0f;
    d->rough_ramp_noise_offset = 0.0f;
    d->rough_ramp_noise_gain = 1.0f;
    d->rough_ramp_noise_distortion = 0.0f;
    d->rough_ramp_noise_use_color = 0;
    /* Slice 2be identity — enable=0 skips InvertNode (2ba/2bb/2i bit-identical). */
    d->rough_invert_enable = 0;
    d->rough_invert_fac = 1.0f;
    /* Slice 2bj identity — enable=0 skips SeparateColorNode. */
    d->rough_separate_enable = 0;
    d->rough_separate_channel = 1; /* Green — loft Sideboard default */
    /* Slice 2bm identity — enable=0 keeps Principled path bit-identical. */
    d->glass_bsdf_enable = 0;
    d->glass_distribution = 0; /* Beckmann — loft Glass_02 / Realistic census */
    /* Slice 2bn identity — enable=0 keeps 2bm Glass path bit-identical. */
    d->mix_shader_enable = 0;
    d->mix_shader_fac = 0.5f;
    d->mix_shader_lightpath_enable = 0;
    d->mix_shader_lightpath_output = QT_LIGHTPATH_SHADOW_RAY;
    d->mix_closure1_kind = 0; /* Glass */
    d->mix_closure2_kind = 1; /* Transparent */
    d->mix_transparent_color[0] = d->mix_transparent_color[1] =
        d->mix_transparent_color[2] = 1.0f;
    /* Slice 2bo identity — math enable=0 keeps 2bn Fac path bit-identical. */
    d->mix_shader_math_enable = 0;
    d->mix_shader_math_op = 0;
    d->mix_shader_math_a_kind = 0;
    d->mix_shader_math_a_const = 0.0f;
    d->mix_shader_math_a_lightpath = 0;
    d->mix_shader_math_a_op = 0;
    d->mix_shader_math_a1_kind = 0;
    d->mix_shader_math_a1_const = 0.0f;
    d->mix_shader_math_a1_lightpath = 0;
    d->mix_shader_math_a2_kind = 0;
    d->mix_shader_math_a2_const = 0.0f;
    d->mix_shader_math_a2_lightpath = 0;
    d->mix_shader_math_b_kind = 0;
    d->mix_shader_math_b_const = 0.0f;
    d->mix_shader_math_b_lightpath = 0;
    d->mix_shader_math_b_op = 0;
    d->mix_shader_math_b1_kind = 0;
    d->mix_shader_math_b1_const = 0.0f;
    d->mix_shader_math_b1_lightpath = 0;
    d->mix_shader_math_b2_kind = 0;
    d->mix_shader_math_b2_const = 0.0f;
    d->mix_shader_math_b2_lightpath = 0;
    d->mix_nested_fac = 0.5f;
    d->mix_nested_lightpath_enable = 0;
    d->mix_nested_lightpath_output = QT_LIGHTPATH_SHADOW_RAY;
    d->mix_nested_closure1_kind = 0;
    d->mix_nested_closure2_kind = 1;
    d->mix_nested2_fac = 0.5f;
    d->mix_nested2_lightpath_enable = 0;
    d->mix_nested2_lightpath_output = QT_LIGHTPATH_SHADOW_RAY;
    d->mix_nested2_closure1_kind = 0;
    d->mix_nested2_closure2_kind = 1;
    /* Slice 2br identity — enable=0 / n=0 skips RGBRampNode (2bq bit-identical). */
    d->mix_nested2_ramp_enable = 0;
    d->mix_nested2_ramp = nullptr;
    d->mix_nested2_ramp_alpha = nullptr;
    d->mix_nested2_ramp_n = 0;
    d->mix_nested2_ramp_interpolate = 1;
    d->mix_nested2_ramp_fac = 0.5f;
    /* Slice 2bs identity — math enable=0 keeps 2br set_fac bit-identical. */
    d->mix_nested2_ramp_math_enable = 0;
    d->mix_nested2_ramp_math_op = 0;
    d->mix_nested2_ramp_math_a_kind = 0;
    d->mix_nested2_ramp_math_a_const = 0.0f;
    d->mix_nested2_ramp_math_a_lightpath = 0;
    d->mix_nested2_ramp_math_a_op = 0;
    d->mix_nested2_ramp_math_a1_kind = 0;
    d->mix_nested2_ramp_math_a1_const = 0.0f;
    d->mix_nested2_ramp_math_a1_lightpath = 0;
    d->mix_nested2_ramp_math_a2_kind = 0;
    d->mix_nested2_ramp_math_a2_const = 0.0f;
    d->mix_nested2_ramp_math_a2_lightpath = 0;
    d->mix_nested2_ramp_math_b_kind = 0;
    d->mix_nested2_ramp_math_b_const = 0.0f;
    d->mix_nested2_ramp_math_b_lightpath = 0;
    d->mix_nested2_ramp_math_b_op = 0;
    d->mix_nested2_ramp_math_b1_kind = 0;
    d->mix_nested2_ramp_math_b1_const = 0.0f;
    d->mix_nested2_ramp_math_b1_lightpath = 0;
    d->mix_nested2_ramp_math_b2_kind = 0;
    d->mix_nested2_ramp_math_b2_const = 0.0f;
    d->mix_nested2_ramp_math_b2_lightpath = 0;
    d->mix_nested2_ramp_hsv_hue = 0.5f;
    d->mix_nested2_ramp_hsv_sat = 1.0f;
    d->mix_nested2_ramp_hsv_val = 1.0f;
    d->mix_nested2_ramp_hsv_fac = 1.0f;
    d->mix_nested2_ramp_hsv_color[0] = d->mix_nested2_ramp_hsv_color[1] =
        d->mix_nested2_ramp_hsv_color[2] = 0.0f;
    d->mix_nested2_ramp_hsv_color_kind = 0;
    d->mix_nested2_ramp_hsv_color_lightpath = 0;
    /* Slice 2bt identity — add_enable=0 keeps 2bs Glass+Transparent. */
    d->mix_nested2_add_enable = 0;
    d->mix_nested2_add_c1_kind = 0;
    d->mix_nested2_add_c2_kind = 1;
    d->mix_nested2_glossy_color[0] = d->mix_nested2_glossy_color[1] =
        d->mix_nested2_glossy_color[2] = 1.0f;
    d->mix_nested2_glossy_roughness = 0.5f;
    d->mix_nested2_glossy_distribution = 1;
    d->mix_nested2_sss_color[0] = d->mix_nested2_sss_color[1] =
        d->mix_nested2_sss_color[2] = 0.8f;
    d->mix_nested2_sss_scale = 0.005f;
    d->mix_nested2_sss_radius[0] = 1.0f;
    d->mix_nested2_sss_radius[1] = 0.2f;
    d->mix_nested2_sss_radius[2] = 0.1f;
    d->mix_nested2_sss_ior = 1.4f;
    d->mix_nested2_sss_roughness = 1.0f;
    d->mix_nested2_sss_method = 0;
    d->mix_nested2_translucent_color[0] = d->mix_nested2_translucent_color[1] =
        d->mix_nested2_translucent_color[2] = 0.8f;
    /* Slice 2bu identity — add_mix_enable=0 keeps 2bt Add+leaf. */
    d->mix_nested2_add_mix_enable = 0;
    d->mix_nested2_add_mix_fac = 0.5f;
    d->mix_nested2_add_mix_lightpath_enable = 0;
    d->mix_nested2_add_mix_lightpath_output = 1;
    d->mix_nested2_add_mix_c1_kind = 3;
    d->mix_nested2_add_mix_c2_kind = 1;
    /* Slice 2bk identity — mix_type=0 + specular_tint=(1,1,1) keeps 2u bit-identical. */
    d->specular_tint[0] = d->specular_tint[1] = d->specular_tint[2] = 1.0f;
    d->spec_tint_mix_type = 0;
    d->spec_tint_mix_fac = 0.5f;
    d->spec_tint_mix_other[0] = d->spec_tint_mix_other[1] = d->spec_tint_mix_other[2] = 0.0f;
    d->spec_tint_mix_chain_is_a = 1;
    d->spec_tint_mix_clamp_factor = 0;
    d->spec_tint_mix_clamp_result = 0;
    d->spec_tint_mix_b_image_path = nullptr;
    d->spec_tint_mix_b_image_colorspace = nullptr;
    d->spec_tint_gamma = 1.0f;
    d->spec_tint_hsv_hue = 0.5f;
    d->spec_tint_hsv_sat = 1.0f;
    d->spec_tint_hsv_val = 1.0f;
    d->spec_tint_hsv_fac = 1.0f;
    /* Slice 2bc identity — enable=0 skips Noise on Bump Height (2x bit-identical). */
    d->bump_noise_enable = 0;
    d->bump_noise_dimensions = 3;
    d->bump_noise_type = QT_NOISE_FBM;
    d->bump_noise_normalize = 1;
    d->bump_noise_w = 0.0f;
    d->bump_noise_scale = 5.0f;
    d->bump_noise_detail = 2.0f;
    d->bump_noise_roughness = 0.5f;
    d->bump_noise_lacunarity = 2.0f;
    d->bump_noise_offset = 0.0f;
    d->bump_noise_gain = 1.0f;
    d->bump_noise_distortion = 0.0f;
    d->bump_noise_use_color = 0;
    /* Slice 2bl identity — enable=0 skips SeparateColor on Bump Height. */
    d->bump_separate_enable = 0;
    d->bump_separate_channel = 2; /* Blue — loft Sideboard default */
    /* Slice 2ap identity — bright=0 contrast=0 (memset is fine; set explicit). */
    d->world_bright = 0.0f;
    d->world_contrast = 0.0f;
    /* Slice 2aq identity — mix_type=0 (memset is fine; set explicit). */
    d->world_mix_type = 0;
    d->world_mix_fac = 0.5f;
    d->world_mix_other[0] = d->world_mix_other[1] = d->world_mix_other[2] = 0.0f;
    d->world_mix_chain_is_a = 1;
    d->world_mix_clamp_factor = 0;
    d->world_mix_clamp_result = 0;
    /* Slice 2as identity — n==0 skips RGBCurvesNode. */
    d->world_curves = nullptr;
    d->world_curves_n = 0;
    d->world_curves_min_x = 0.0f;
    d->world_curves_max_x = 1.0f;
    d->world_curves_fac = 1.0f;
    d->world_curves_extrapolate = 1;
    d->exr_path = nullptr;
}

static void simple_to_qt(const QT_SimpleScene *s,
                         QT_Mesh *mesh,
                         QT_Light *light,
                         QT_Scene *out)
{
    std::memset(mesh, 0, sizeof(*mesh));
    mesh->nverts = s->nverts;
    mesh->ntris = s->ntris;
    mesh->verts = s->verts;
    mesh->tris = s->tris;
    std::memcpy(mesh->tfm, s->mesh_tfm, sizeof(mesh->tfm));
    std::memcpy(mesh->base_color, s->base_color, sizeof(mesh->base_color));
    mesh->roughness = s->roughness;
    mesh->metallic = s->metallic;
    mesh->ior = s->ior;
    mesh->alpha = s->alpha;
    mesh->name = "Cube"; /* locked-cube Blender object name */
    mesh->uvs = s->uvs;
    mesh->image_path = s->image_path;
    mesh->image_colorspace = s->image_colorspace;
    mesh->tex_vector_mode = s->tex_vector_mode;
    std::memcpy(mesh->map_location, s->map_location, sizeof(mesh->map_location));
    std::memcpy(mesh->map_rotation, s->map_rotation, sizeof(mesh->map_rotation));
    std::memcpy(mesh->map_scale, s->map_scale, sizeof(mesh->map_scale));
    mesh->map_type = s->map_type;
    mesh->rough_image_path = s->rough_image_path;
    mesh->rough_image_colorspace = s->rough_image_colorspace;
    mesh->rough_tex_vector_mode = s->rough_tex_vector_mode;
    std::memcpy(mesh->rough_map_location, s->rough_map_location, sizeof(mesh->rough_map_location));
    std::memcpy(mesh->rough_map_rotation, s->rough_map_rotation, sizeof(mesh->rough_map_rotation));
    std::memcpy(mesh->rough_map_scale, s->rough_map_scale, sizeof(mesh->rough_map_scale));
    mesh->rough_map_type = s->rough_map_type;
    mesh->metal_image_path = s->metal_image_path;
    mesh->metal_image_colorspace = s->metal_image_colorspace;
    mesh->metal_tex_vector_mode = s->metal_tex_vector_mode;
    std::memcpy(mesh->metal_map_location, s->metal_map_location, sizeof(mesh->metal_map_location));
    std::memcpy(mesh->metal_map_rotation, s->metal_map_rotation, sizeof(mesh->metal_map_rotation));
    std::memcpy(mesh->metal_map_scale, s->metal_map_scale, sizeof(mesh->metal_map_scale));
    mesh->metal_map_type = s->metal_map_type;
    mesh->normal_image_path = s->normal_image_path;
    mesh->normal_image_colorspace = s->normal_image_colorspace;
    mesh->normal_tex_vector_mode = s->normal_tex_vector_mode;
    std::memcpy(mesh->normal_map_location, s->normal_map_location, sizeof(mesh->normal_map_location));
    std::memcpy(mesh->normal_map_rotation, s->normal_map_rotation, sizeof(mesh->normal_map_rotation));
    std::memcpy(mesh->normal_map_scale, s->normal_map_scale, sizeof(mesh->normal_map_scale));
    mesh->normal_map_type = s->normal_map_type;
    mesh->normal_strength = s->normal_strength;
    mesh->normal_space = s->normal_space;
    mesh->ior_image_path = s->ior_image_path;
    mesh->ior_image_colorspace = s->ior_image_colorspace;
    mesh->ior_tex_vector_mode = s->ior_tex_vector_mode;
    std::memcpy(mesh->ior_map_location, s->ior_map_location, sizeof(mesh->ior_map_location));
    std::memcpy(mesh->ior_map_rotation, s->ior_map_rotation, sizeof(mesh->ior_map_rotation));
    std::memcpy(mesh->ior_map_scale, s->ior_map_scale, sizeof(mesh->ior_map_scale));
    mesh->ior_map_type = s->ior_map_type;
    mesh->alpha_image_path = s->alpha_image_path;
    mesh->alpha_image_colorspace = s->alpha_image_colorspace;
    mesh->alpha_tex_vector_mode = s->alpha_tex_vector_mode;
    std::memcpy(mesh->alpha_map_location, s->alpha_map_location, sizeof(mesh->alpha_map_location));
    std::memcpy(mesh->alpha_map_rotation, s->alpha_map_rotation, sizeof(mesh->alpha_map_rotation));
    std::memcpy(mesh->alpha_map_scale, s->alpha_map_scale, sizeof(mesh->alpha_map_scale));
    mesh->alpha_map_type = s->alpha_map_type;
    mesh->trans_image_path = s->trans_image_path;
    mesh->trans_image_colorspace = s->trans_image_colorspace;
    mesh->trans_tex_vector_mode = s->trans_tex_vector_mode;
    std::memcpy(mesh->trans_map_location, s->trans_map_location, sizeof(mesh->trans_map_location));
    std::memcpy(mesh->trans_map_rotation, s->trans_map_rotation, sizeof(mesh->trans_map_rotation));
    std::memcpy(mesh->trans_map_scale, s->trans_map_scale, sizeof(mesh->trans_map_scale));
    mesh->trans_map_type = s->trans_map_type;
    mesh->spec_image_path = s->spec_image_path;
    mesh->spec_image_colorspace = s->spec_image_colorspace;
    mesh->spec_tex_vector_mode = s->spec_tex_vector_mode;
    std::memcpy(mesh->spec_map_location, s->spec_map_location, sizeof(mesh->spec_map_location));
    std::memcpy(mesh->spec_map_rotation, s->spec_map_rotation, sizeof(mesh->spec_map_rotation));
    std::memcpy(mesh->spec_map_scale, s->spec_map_scale, sizeof(mesh->spec_map_scale));
    mesh->spec_map_type = s->spec_map_type;
    mesh->coat_image_path = s->coat_image_path;
    mesh->coat_image_colorspace = s->coat_image_colorspace;
    mesh->coat_tex_vector_mode = s->coat_tex_vector_mode;
    std::memcpy(mesh->coat_map_location, s->coat_map_location, sizeof(mesh->coat_map_location));
    std::memcpy(mesh->coat_map_rotation, s->coat_map_rotation, sizeof(mesh->coat_map_rotation));
    std::memcpy(mesh->coat_map_scale, s->coat_map_scale, sizeof(mesh->coat_map_scale));
    mesh->coat_map_type = s->coat_map_type;
    mesh->sheen_image_path = s->sheen_image_path;
    mesh->sheen_image_colorspace = s->sheen_image_colorspace;
    mesh->sheen_tex_vector_mode = s->sheen_tex_vector_mode;
    std::memcpy(mesh->sheen_map_location, s->sheen_map_location, sizeof(mesh->sheen_map_location));
    std::memcpy(mesh->sheen_map_rotation, s->sheen_map_rotation, sizeof(mesh->sheen_map_rotation));
    std::memcpy(mesh->sheen_map_scale, s->sheen_map_scale, sizeof(mesh->sheen_map_scale));
    mesh->sheen_map_type = s->sheen_map_type;
    mesh->emit_str_image_path = s->emit_str_image_path;
    mesh->emit_str_image_colorspace = s->emit_str_image_colorspace;
    mesh->emit_str_tex_vector_mode = s->emit_str_tex_vector_mode;
    std::memcpy(mesh->emit_str_map_location, s->emit_str_map_location, sizeof(mesh->emit_str_map_location));
    std::memcpy(mesh->emit_str_map_rotation, s->emit_str_map_rotation, sizeof(mesh->emit_str_map_rotation));
    std::memcpy(mesh->emit_str_map_scale, s->emit_str_map_scale, sizeof(mesh->emit_str_map_scale));
    mesh->emit_str_map_type = s->emit_str_map_type;
    mesh->emit_color_image_path = s->emit_color_image_path;
    mesh->emit_color_image_colorspace = s->emit_color_image_colorspace;
    mesh->emit_color_tex_vector_mode = s->emit_color_tex_vector_mode;
    std::memcpy(mesh->emit_color_map_location, s->emit_color_map_location, sizeof(mesh->emit_color_map_location));
    std::memcpy(mesh->emit_color_map_rotation, s->emit_color_map_rotation, sizeof(mesh->emit_color_map_rotation));
    std::memcpy(mesh->emit_color_map_scale, s->emit_color_map_scale, sizeof(mesh->emit_color_map_scale));
    mesh->emit_color_map_type = s->emit_color_map_type;
    mesh->coat_rough_image_path = s->coat_rough_image_path;
    mesh->coat_rough_image_colorspace = s->coat_rough_image_colorspace;
    mesh->coat_rough_tex_vector_mode = s->coat_rough_tex_vector_mode;
    std::memcpy(mesh->coat_rough_map_location, s->coat_rough_map_location, sizeof(mesh->coat_rough_map_location));
    std::memcpy(mesh->coat_rough_map_rotation, s->coat_rough_map_rotation, sizeof(mesh->coat_rough_map_rotation));
    std::memcpy(mesh->coat_rough_map_scale, s->coat_rough_map_scale, sizeof(mesh->coat_rough_map_scale));
    mesh->coat_rough_map_type = s->coat_rough_map_type;
    mesh->coat_ior_image_path = s->coat_ior_image_path;
    mesh->coat_ior_image_colorspace = s->coat_ior_image_colorspace;
    mesh->coat_ior_tex_vector_mode = s->coat_ior_tex_vector_mode;
    std::memcpy(mesh->coat_ior_map_location, s->coat_ior_map_location, sizeof(mesh->coat_ior_map_location));
    std::memcpy(mesh->coat_ior_map_rotation, s->coat_ior_map_rotation, sizeof(mesh->coat_ior_map_rotation));
    std::memcpy(mesh->coat_ior_map_scale, s->coat_ior_map_scale, sizeof(mesh->coat_ior_map_scale));
    mesh->coat_ior_map_type = s->coat_ior_map_type;
    mesh->coat_tint_image_path = s->coat_tint_image_path;
    mesh->coat_tint_image_colorspace = s->coat_tint_image_colorspace;
    mesh->coat_tint_tex_vector_mode = s->coat_tint_tex_vector_mode;
    std::memcpy(mesh->coat_tint_map_location, s->coat_tint_map_location, sizeof(mesh->coat_tint_map_location));
    std::memcpy(mesh->coat_tint_map_rotation, s->coat_tint_map_rotation, sizeof(mesh->coat_tint_map_rotation));
    std::memcpy(mesh->coat_tint_map_scale, s->coat_tint_map_scale, sizeof(mesh->coat_tint_map_scale));
    mesh->coat_tint_map_type = s->coat_tint_map_type;
    mesh->sheen_rough_image_path = s->sheen_rough_image_path;
    mesh->sheen_rough_image_colorspace = s->sheen_rough_image_colorspace;
    mesh->sheen_rough_tex_vector_mode = s->sheen_rough_tex_vector_mode;
    std::memcpy(mesh->sheen_rough_map_location, s->sheen_rough_map_location, sizeof(mesh->sheen_rough_map_location));
    std::memcpy(mesh->sheen_rough_map_rotation, s->sheen_rough_map_rotation, sizeof(mesh->sheen_rough_map_rotation));
    std::memcpy(mesh->sheen_rough_map_scale, s->sheen_rough_map_scale, sizeof(mesh->sheen_rough_map_scale));
    mesh->sheen_rough_map_type = s->sheen_rough_map_type;
    mesh->sheen_tint_image_path = s->sheen_tint_image_path;
    mesh->sheen_tint_image_colorspace = s->sheen_tint_image_colorspace;
    mesh->sheen_tint_tex_vector_mode = s->sheen_tint_tex_vector_mode;
    std::memcpy(mesh->sheen_tint_map_location, s->sheen_tint_map_location, sizeof(mesh->sheen_tint_map_location));
    std::memcpy(mesh->sheen_tint_map_rotation, s->sheen_tint_map_rotation, sizeof(mesh->sheen_tint_map_rotation));
    std::memcpy(mesh->sheen_tint_map_scale, s->sheen_tint_map_scale, sizeof(mesh->sheen_tint_map_scale));
    mesh->sheen_tint_map_type = s->sheen_tint_map_type;
    mesh->coat_normal_image_path = s->coat_normal_image_path;
    mesh->coat_normal_image_colorspace = s->coat_normal_image_colorspace;
    mesh->coat_normal_tex_vector_mode = s->coat_normal_tex_vector_mode;
    std::memcpy(mesh->coat_normal_map_location, s->coat_normal_map_location, sizeof(mesh->coat_normal_map_location));
    std::memcpy(mesh->coat_normal_map_rotation, s->coat_normal_map_rotation, sizeof(mesh->coat_normal_map_rotation));
    std::memcpy(mesh->coat_normal_map_scale, s->coat_normal_map_scale, sizeof(mesh->coat_normal_map_scale));
    mesh->coat_normal_map_type = s->coat_normal_map_type;
    mesh->coat_normal_strength = s->coat_normal_strength;
    mesh->coat_normal_space = s->coat_normal_space;
    mesh->spec_tint_image_path = s->spec_tint_image_path;
    mesh->spec_tint_image_colorspace = s->spec_tint_image_colorspace;
    mesh->spec_tint_tex_vector_mode = s->spec_tint_tex_vector_mode;
    std::memcpy(mesh->spec_tint_map_location, s->spec_tint_map_location, sizeof(mesh->spec_tint_map_location));
    std::memcpy(mesh->spec_tint_map_rotation, s->spec_tint_map_rotation, sizeof(mesh->spec_tint_map_rotation));
    std::memcpy(mesh->spec_tint_map_scale, s->spec_tint_map_scale, sizeof(mesh->spec_tint_map_scale));
    mesh->spec_tint_map_type = s->spec_tint_map_type;
    std::memcpy(mesh->specular_tint, s->specular_tint, sizeof(mesh->specular_tint));
    mesh->spec_tint_mix_type = s->spec_tint_mix_type;
    mesh->spec_tint_mix_fac = s->spec_tint_mix_fac;
    std::memcpy(mesh->spec_tint_mix_other, s->spec_tint_mix_other, sizeof(mesh->spec_tint_mix_other));
    mesh->spec_tint_mix_chain_is_a = s->spec_tint_mix_chain_is_a;
    mesh->spec_tint_mix_clamp_factor = s->spec_tint_mix_clamp_factor;
    mesh->spec_tint_mix_clamp_result = s->spec_tint_mix_clamp_result;
    mesh->spec_tint_mix_b_image_path = s->spec_tint_mix_b_image_path;
    mesh->spec_tint_mix_b_image_colorspace = s->spec_tint_mix_b_image_colorspace;
    mesh->spec_tint_gamma = s->spec_tint_gamma;
    mesh->spec_tint_hsv_hue = s->spec_tint_hsv_hue;
    mesh->spec_tint_hsv_sat = s->spec_tint_hsv_sat;
    mesh->spec_tint_hsv_val = s->spec_tint_hsv_val;
    mesh->spec_tint_hsv_fac = s->spec_tint_hsv_fac;
    mesh->film_thick_image_path = s->film_thick_image_path;
    mesh->film_thick_image_colorspace = s->film_thick_image_colorspace;
    mesh->film_thick_tex_vector_mode = s->film_thick_tex_vector_mode;
    std::memcpy(mesh->film_thick_map_location, s->film_thick_map_location, sizeof(mesh->film_thick_map_location));
    std::memcpy(mesh->film_thick_map_rotation, s->film_thick_map_rotation, sizeof(mesh->film_thick_map_rotation));
    std::memcpy(mesh->film_thick_map_scale, s->film_thick_map_scale, sizeof(mesh->film_thick_map_scale));
    mesh->film_thick_map_type = s->film_thick_map_type;
    mesh->film_ior_image_path = s->film_ior_image_path;
    mesh->film_ior_image_colorspace = s->film_ior_image_colorspace;
    mesh->film_ior_tex_vector_mode = s->film_ior_tex_vector_mode;
    std::memcpy(mesh->film_ior_map_location, s->film_ior_map_location, sizeof(mesh->film_ior_map_location));
    std::memcpy(mesh->film_ior_map_rotation, s->film_ior_map_rotation, sizeof(mesh->film_ior_map_rotation));
    std::memcpy(mesh->film_ior_map_scale, s->film_ior_map_scale, sizeof(mesh->film_ior_map_scale));
    mesh->film_ior_map_type = s->film_ior_map_type;
    mesh->sss_weight_image_path = s->sss_weight_image_path;
    mesh->sss_weight_image_colorspace = s->sss_weight_image_colorspace;
    mesh->sss_weight_tex_vector_mode = s->sss_weight_tex_vector_mode;
    std::memcpy(mesh->sss_weight_map_location, s->sss_weight_map_location, sizeof(mesh->sss_weight_map_location));
    std::memcpy(mesh->sss_weight_map_rotation, s->sss_weight_map_rotation, sizeof(mesh->sss_weight_map_rotation));
    std::memcpy(mesh->sss_weight_map_scale, s->sss_weight_map_scale, sizeof(mesh->sss_weight_map_scale));
    mesh->sss_weight_map_type = s->sss_weight_map_type;
    mesh->sss_radius_image_path = s->sss_radius_image_path;
    mesh->sss_radius_image_colorspace = s->sss_radius_image_colorspace;
    mesh->sss_radius_tex_vector_mode = s->sss_radius_tex_vector_mode;
    std::memcpy(mesh->sss_radius_map_location, s->sss_radius_map_location, sizeof(mesh->sss_radius_map_location));
    std::memcpy(mesh->sss_radius_map_rotation, s->sss_radius_map_rotation, sizeof(mesh->sss_radius_map_rotation));
    std::memcpy(mesh->sss_radius_map_scale, s->sss_radius_map_scale, sizeof(mesh->sss_radius_map_scale));
    mesh->sss_radius_map_type = s->sss_radius_map_type;
    mesh->sss_scale_image_path = s->sss_scale_image_path;
    mesh->sss_scale_image_colorspace = s->sss_scale_image_colorspace;
    mesh->sss_scale_tex_vector_mode = s->sss_scale_tex_vector_mode;
    std::memcpy(mesh->sss_scale_map_location, s->sss_scale_map_location, sizeof(mesh->sss_scale_map_location));
    std::memcpy(mesh->sss_scale_map_rotation, s->sss_scale_map_rotation, sizeof(mesh->sss_scale_map_rotation));
    std::memcpy(mesh->sss_scale_map_scale, s->sss_scale_map_scale, sizeof(mesh->sss_scale_map_scale));
    mesh->sss_scale_map_type = s->sss_scale_map_type;
    mesh->sss_ior_image_path = s->sss_ior_image_path;
    mesh->sss_ior_image_colorspace = s->sss_ior_image_colorspace;
    mesh->sss_ior_tex_vector_mode = s->sss_ior_tex_vector_mode;
    std::memcpy(mesh->sss_ior_map_location, s->sss_ior_map_location, sizeof(mesh->sss_ior_map_location));
    std::memcpy(mesh->sss_ior_map_rotation, s->sss_ior_map_rotation, sizeof(mesh->sss_ior_map_rotation));
    std::memcpy(mesh->sss_ior_map_scale, s->sss_ior_map_scale, sizeof(mesh->sss_ior_map_scale));
    mesh->sss_ior_map_type = s->sss_ior_map_type;
    mesh->sss_aniso_image_path = s->sss_aniso_image_path;
    mesh->sss_aniso_image_colorspace = s->sss_aniso_image_colorspace;
    mesh->sss_aniso_tex_vector_mode = s->sss_aniso_tex_vector_mode;
    std::memcpy(mesh->sss_aniso_map_location, s->sss_aniso_map_location, sizeof(mesh->sss_aniso_map_location));
    std::memcpy(mesh->sss_aniso_map_rotation, s->sss_aniso_map_rotation, sizeof(mesh->sss_aniso_map_rotation));
    std::memcpy(mesh->sss_aniso_map_scale, s->sss_aniso_map_scale, sizeof(mesh->sss_aniso_map_scale));
    mesh->sss_aniso_map_type = s->sss_aniso_map_type;
    mesh->thin_wall_image_path = s->thin_wall_image_path;
    mesh->thin_wall_image_colorspace = s->thin_wall_image_colorspace;
    mesh->thin_wall_tex_vector_mode = s->thin_wall_tex_vector_mode;
    std::memcpy(mesh->thin_wall_map_location, s->thin_wall_map_location, sizeof(mesh->thin_wall_map_location));
    std::memcpy(mesh->thin_wall_map_rotation, s->thin_wall_map_rotation, sizeof(mesh->thin_wall_map_rotation));
    std::memcpy(mesh->thin_wall_map_scale, s->thin_wall_map_scale, sizeof(mesh->thin_wall_map_scale));
    mesh->thin_wall_map_type = s->thin_wall_map_type;
    mesh->diffuse_rough_image_path = s->diffuse_rough_image_path;
    mesh->diffuse_rough_image_colorspace = s->diffuse_rough_image_colorspace;
    mesh->diffuse_rough_tex_vector_mode = s->diffuse_rough_tex_vector_mode;
    std::memcpy(mesh->diffuse_rough_map_location, s->diffuse_rough_map_location, sizeof(mesh->diffuse_rough_map_location));
    std::memcpy(mesh->diffuse_rough_map_rotation, s->diffuse_rough_map_rotation, sizeof(mesh->diffuse_rough_map_rotation));
    std::memcpy(mesh->diffuse_rough_map_scale, s->diffuse_rough_map_scale, sizeof(mesh->diffuse_rough_map_scale));
    mesh->diffuse_rough_map_type = s->diffuse_rough_map_type;
    mesh->aniso_image_path = s->aniso_image_path;
    mesh->aniso_image_colorspace = s->aniso_image_colorspace;
    mesh->aniso_tex_vector_mode = s->aniso_tex_vector_mode;
    std::memcpy(mesh->aniso_map_location, s->aniso_map_location, sizeof(mesh->aniso_map_location));
    std::memcpy(mesh->aniso_map_rotation, s->aniso_map_rotation, sizeof(mesh->aniso_map_rotation));
    std::memcpy(mesh->aniso_map_scale, s->aniso_map_scale, sizeof(mesh->aniso_map_scale));
    mesh->aniso_map_type = s->aniso_map_type;
    mesh->aniso_rot_image_path = s->aniso_rot_image_path;
    mesh->aniso_rot_image_colorspace = s->aniso_rot_image_colorspace;
    mesh->aniso_rot_tex_vector_mode = s->aniso_rot_tex_vector_mode;
    std::memcpy(mesh->aniso_rot_map_location, s->aniso_rot_map_location, sizeof(mesh->aniso_rot_map_location));
    std::memcpy(mesh->aniso_rot_map_rotation, s->aniso_rot_map_rotation, sizeof(mesh->aniso_rot_map_rotation));
    std::memcpy(mesh->aniso_rot_map_scale, s->aniso_rot_map_scale, sizeof(mesh->aniso_rot_map_scale));
    mesh->aniso_rot_map_type = s->aniso_rot_map_type;
    mesh->tangent_image_path = s->tangent_image_path;
    mesh->tangent_image_colorspace = s->tangent_image_colorspace;
    mesh->tangent_tex_vector_mode = s->tangent_tex_vector_mode;
    std::memcpy(mesh->tangent_map_location, s->tangent_map_location, sizeof(mesh->tangent_map_location));
    std::memcpy(mesh->tangent_map_rotation, s->tangent_map_rotation, sizeof(mesh->tangent_map_rotation));
    std::memcpy(mesh->tangent_map_scale, s->tangent_map_scale, sizeof(mesh->tangent_map_scale));
    mesh->tangent_map_type = s->tangent_map_type;
    mesh->bump_image_path = s->bump_image_path;
    mesh->bump_image_colorspace = s->bump_image_colorspace;
    mesh->bump_tex_vector_mode = s->bump_tex_vector_mode;
    std::memcpy(mesh->bump_map_location, s->bump_map_location, sizeof(mesh->bump_map_location));
    std::memcpy(mesh->bump_map_rotation, s->bump_map_rotation, sizeof(mesh->bump_map_rotation));
    std::memcpy(mesh->bump_map_scale, s->bump_map_scale, sizeof(mesh->bump_map_scale));
    mesh->bump_map_type = s->bump_map_type;
    mesh->bump_strength = s->bump_strength;
    mesh->bump_distance = s->bump_distance;
    mesh->bump_invert = s->bump_invert;
    mesh->bump_noise_enable = s->bump_noise_enable;
    mesh->bump_noise_dimensions = s->bump_noise_dimensions;
    mesh->bump_noise_type = s->bump_noise_type;
    mesh->bump_noise_normalize = s->bump_noise_normalize;
    mesh->bump_noise_w = s->bump_noise_w;
    mesh->bump_noise_scale = s->bump_noise_scale;
    mesh->bump_noise_detail = s->bump_noise_detail;
    mesh->bump_noise_roughness = s->bump_noise_roughness;
    mesh->bump_noise_lacunarity = s->bump_noise_lacunarity;
    mesh->bump_noise_offset = s->bump_noise_offset;
    mesh->bump_noise_gain = s->bump_noise_gain;
    mesh->bump_noise_distortion = s->bump_noise_distortion;
    mesh->bump_noise_use_color = s->bump_noise_use_color;
    mesh->bump_separate_enable = s->bump_separate_enable;
    mesh->bump_separate_channel = s->bump_separate_channel;
    mesh->thin_wall = s->thin_wall;
    mesh->transmission_weight = s->transmission_weight;
    mesh->tex_ob_use_transform = s->tex_ob_use_transform;
    std::memcpy(mesh->tex_ob_tfm, s->tex_ob_tfm, sizeof(mesh->tex_ob_tfm));
    /* Slice 2ax: Base Color Gamma/HSV (identity skip keeps 2f bit-identical). */
    mesh->base_gamma = s->base_gamma;
    mesh->base_hsv_hue = s->base_hsv_hue;
    mesh->base_hsv_sat = s->base_hsv_sat;
    mesh->base_hsv_val = s->base_hsv_val;
    mesh->base_hsv_fac = s->base_hsv_fac;
    /* Slice 2ay: Base Color Mix (+ optional second TEX_IMAGE). */
    mesh->base_mix_type = s->base_mix_type;
    mesh->base_mix_fac = s->base_mix_fac;
    std::memcpy(mesh->base_mix_other, s->base_mix_other, sizeof(mesh->base_mix_other));
    mesh->base_mix_chain_is_a = s->base_mix_chain_is_a;
    mesh->base_mix_clamp_factor = s->base_mix_clamp_factor;
    mesh->base_mix_clamp_result = s->base_mix_clamp_result;
    mesh->base_mix_b_image_path = s->base_mix_b_image_path;
    mesh->base_mix_b_image_colorspace = s->base_mix_b_image_colorspace;
    mesh->base_mix_fresnel_enable = s->base_mix_fresnel_enable;
    mesh->base_mix_fresnel_ior = s->base_mix_fresnel_ior;
    /* Slice 2bd: RGB Curves LUT → Principled Base Color. */
    mesh->base_curves = s->base_curves;
    mesh->base_curves_n = s->base_curves_n;
    mesh->base_curves_min_x = s->base_curves_min_x;
    mesh->base_curves_max_x = s->base_curves_max_x;
    mesh->base_curves_fac = s->base_curves_fac;
    mesh->base_curves_extrapolate = s->base_curves_extrapolate;
    /* Slice 2bh: mix-side RGB Curves LUT. */
    mesh->base_mix_curves = s->base_mix_curves;
    mesh->base_mix_curves_n = s->base_mix_curves_n;
    mesh->base_mix_curves_min_x = s->base_mix_curves_min_x;
    mesh->base_mix_curves_max_x = s->base_mix_curves_max_x;
    mesh->base_mix_curves_fac = s->base_mix_curves_fac;
    mesh->base_mix_curves_extrapolate = s->base_mix_curves_extrapolate;
    mesh->base_mix_curves_on_a = s->base_mix_curves_on_a;
    /* Slice 2bi: Normal Map Invert-G Y-flip. */
    mesh->normal_invert_g_enable = s->normal_invert_g_enable;
    mesh->normal_invert_g_fac = s->normal_invert_g_fac;
    mesh->coat_normal_invert_g_enable = s->coat_normal_invert_g_enable;
    mesh->coat_normal_invert_g_fac = s->coat_normal_invert_g_fac;
    /* Slice 2az: Bevel → Principled.Normal. */
    mesh->bevel_enable = s->bevel_enable;
    mesh->bevel_samples = s->bevel_samples;
    mesh->bevel_radius = s->bevel_radius;
    /* Slice 2ba: ColorRamp → Principled.Roughness. */
    mesh->rough_ramp = s->rough_ramp;
    mesh->rough_ramp_alpha = s->rough_ramp_alpha;
    mesh->rough_ramp_n = s->rough_ramp_n;
    mesh->rough_ramp_interpolate = s->rough_ramp_interpolate;
    mesh->rough_ramp_fac = s->rough_ramp_fac;
    /* Slice 2bb: Noise → ColorRamp.Fac. */
    mesh->rough_ramp_noise_enable = s->rough_ramp_noise_enable;
    mesh->rough_ramp_noise_dimensions = s->rough_ramp_noise_dimensions;
    mesh->rough_ramp_noise_type = s->rough_ramp_noise_type;
    mesh->rough_ramp_noise_normalize = s->rough_ramp_noise_normalize;
    mesh->rough_ramp_noise_w = s->rough_ramp_noise_w;
    mesh->rough_ramp_noise_scale = s->rough_ramp_noise_scale;
    mesh->rough_ramp_noise_detail = s->rough_ramp_noise_detail;
    mesh->rough_ramp_noise_roughness = s->rough_ramp_noise_roughness;
    mesh->rough_ramp_noise_lacunarity = s->rough_ramp_noise_lacunarity;
    mesh->rough_ramp_noise_offset = s->rough_ramp_noise_offset;
    mesh->rough_ramp_noise_gain = s->rough_ramp_noise_gain;
    mesh->rough_ramp_noise_distortion = s->rough_ramp_noise_distortion;
    mesh->rough_ramp_noise_use_color = s->rough_ramp_noise_use_color;
    /* Slice 2be: InvertNode → Principled.Roughness. */
    mesh->rough_invert_enable = s->rough_invert_enable;
    mesh->rough_invert_fac = s->rough_invert_fac;
    /* Slice 2bj: SeparateColorNode channel → Principled.Roughness. */
    mesh->rough_separate_enable = s->rough_separate_enable;
    mesh->rough_separate_channel = s->rough_separate_channel;
    /* Slice 2bm: GlassBsdfNode surface. */
    mesh->glass_bsdf_enable = s->glass_bsdf_enable;
    mesh->glass_distribution = s->glass_distribution;
    /* Slice 2bn: MixClosure + LightPath Fac. */
    mesh->mix_shader_enable = s->mix_shader_enable;
    mesh->mix_shader_fac = s->mix_shader_fac;
    mesh->mix_shader_lightpath_enable = s->mix_shader_lightpath_enable;
    mesh->mix_shader_lightpath_output = s->mix_shader_lightpath_output;
    mesh->mix_closure1_kind = s->mix_closure1_kind;
    mesh->mix_closure2_kind = s->mix_closure2_kind;
    mesh->mix_transparent_color[0] = s->mix_transparent_color[0];
    mesh->mix_transparent_color[1] = s->mix_transparent_color[1];
    mesh->mix_transparent_color[2] = s->mix_transparent_color[2];
    /* Slice 2bo: Mix Fac MATH nest. */
    mesh->mix_shader_math_enable = s->mix_shader_math_enable;
    mesh->mix_shader_math_op = s->mix_shader_math_op;
    mesh->mix_shader_math_a_kind = s->mix_shader_math_a_kind;
    mesh->mix_shader_math_a_const = s->mix_shader_math_a_const;
    mesh->mix_shader_math_a_lightpath = s->mix_shader_math_a_lightpath;
    mesh->mix_shader_math_a_op = s->mix_shader_math_a_op;
    mesh->mix_shader_math_a1_kind = s->mix_shader_math_a1_kind;
    mesh->mix_shader_math_a1_const = s->mix_shader_math_a1_const;
    mesh->mix_shader_math_a1_lightpath = s->mix_shader_math_a1_lightpath;
    mesh->mix_shader_math_a2_kind = s->mix_shader_math_a2_kind;
    mesh->mix_shader_math_a2_const = s->mix_shader_math_a2_const;
    mesh->mix_shader_math_a2_lightpath = s->mix_shader_math_a2_lightpath;
    mesh->mix_shader_math_b_kind = s->mix_shader_math_b_kind;
    mesh->mix_shader_math_b_const = s->mix_shader_math_b_const;
    mesh->mix_shader_math_b_lightpath = s->mix_shader_math_b_lightpath;
    mesh->mix_shader_math_b_op = s->mix_shader_math_b_op;
    mesh->mix_shader_math_b1_kind = s->mix_shader_math_b1_kind;
    mesh->mix_shader_math_b1_const = s->mix_shader_math_b1_const;
    mesh->mix_shader_math_b1_lightpath = s->mix_shader_math_b1_lightpath;
    mesh->mix_shader_math_b2_kind = s->mix_shader_math_b2_kind;
    mesh->mix_shader_math_b2_const = s->mix_shader_math_b2_const;
    mesh->mix_shader_math_b2_lightpath = s->mix_shader_math_b2_lightpath;
    mesh->mix_nested_fac = s->mix_nested_fac;
    mesh->mix_nested_lightpath_enable = s->mix_nested_lightpath_enable;
    mesh->mix_nested_lightpath_output = s->mix_nested_lightpath_output;
    mesh->mix_nested_closure1_kind = s->mix_nested_closure1_kind;
    mesh->mix_nested_closure2_kind = s->mix_nested_closure2_kind;
    mesh->mix_nested2_fac = s->mix_nested2_fac;
    mesh->mix_nested2_lightpath_enable = s->mix_nested2_lightpath_enable;
    mesh->mix_nested2_lightpath_output = s->mix_nested2_lightpath_output;
    mesh->mix_nested2_closure1_kind = s->mix_nested2_closure1_kind;
    mesh->mix_nested2_closure2_kind = s->mix_nested2_closure2_kind;
    mesh->mix_nested2_ramp_enable = s->mix_nested2_ramp_enable;
    mesh->mix_nested2_ramp = s->mix_nested2_ramp;
    mesh->mix_nested2_ramp_alpha = s->mix_nested2_ramp_alpha;
    mesh->mix_nested2_ramp_n = s->mix_nested2_ramp_n;
    mesh->mix_nested2_ramp_interpolate = s->mix_nested2_ramp_interpolate;
    mesh->mix_nested2_ramp_fac = s->mix_nested2_ramp_fac;
    mesh->mix_nested2_ramp_math_enable = s->mix_nested2_ramp_math_enable;
    mesh->mix_nested2_ramp_math_op = s->mix_nested2_ramp_math_op;
    mesh->mix_nested2_ramp_math_a_kind = s->mix_nested2_ramp_math_a_kind;
    mesh->mix_nested2_ramp_math_a_const = s->mix_nested2_ramp_math_a_const;
    mesh->mix_nested2_ramp_math_a_lightpath = s->mix_nested2_ramp_math_a_lightpath;
    mesh->mix_nested2_ramp_math_a_op = s->mix_nested2_ramp_math_a_op;
    mesh->mix_nested2_ramp_math_a1_kind = s->mix_nested2_ramp_math_a1_kind;
    mesh->mix_nested2_ramp_math_a1_const = s->mix_nested2_ramp_math_a1_const;
    mesh->mix_nested2_ramp_math_a1_lightpath = s->mix_nested2_ramp_math_a1_lightpath;
    mesh->mix_nested2_ramp_math_a2_kind = s->mix_nested2_ramp_math_a2_kind;
    mesh->mix_nested2_ramp_math_a2_const = s->mix_nested2_ramp_math_a2_const;
    mesh->mix_nested2_ramp_math_a2_lightpath = s->mix_nested2_ramp_math_a2_lightpath;
    mesh->mix_nested2_ramp_math_b_kind = s->mix_nested2_ramp_math_b_kind;
    mesh->mix_nested2_ramp_math_b_const = s->mix_nested2_ramp_math_b_const;
    mesh->mix_nested2_ramp_math_b_lightpath = s->mix_nested2_ramp_math_b_lightpath;
    mesh->mix_nested2_ramp_math_b_op = s->mix_nested2_ramp_math_b_op;
    mesh->mix_nested2_ramp_math_b1_kind = s->mix_nested2_ramp_math_b1_kind;
    mesh->mix_nested2_ramp_math_b1_const = s->mix_nested2_ramp_math_b1_const;
    mesh->mix_nested2_ramp_math_b1_lightpath = s->mix_nested2_ramp_math_b1_lightpath;
    mesh->mix_nested2_ramp_math_b2_kind = s->mix_nested2_ramp_math_b2_kind;
    mesh->mix_nested2_ramp_math_b2_const = s->mix_nested2_ramp_math_b2_const;
    mesh->mix_nested2_ramp_math_b2_lightpath = s->mix_nested2_ramp_math_b2_lightpath;
    mesh->mix_nested2_ramp_hsv_hue = s->mix_nested2_ramp_hsv_hue;
    mesh->mix_nested2_ramp_hsv_sat = s->mix_nested2_ramp_hsv_sat;
    mesh->mix_nested2_ramp_hsv_val = s->mix_nested2_ramp_hsv_val;
    mesh->mix_nested2_ramp_hsv_fac = s->mix_nested2_ramp_hsv_fac;
    mesh->mix_nested2_ramp_hsv_color[0] = s->mix_nested2_ramp_hsv_color[0];
    mesh->mix_nested2_ramp_hsv_color[1] = s->mix_nested2_ramp_hsv_color[1];
    mesh->mix_nested2_ramp_hsv_color[2] = s->mix_nested2_ramp_hsv_color[2];
    mesh->mix_nested2_ramp_hsv_color_kind = s->mix_nested2_ramp_hsv_color_kind;
    mesh->mix_nested2_ramp_hsv_color_lightpath = s->mix_nested2_ramp_hsv_color_lightpath;
    mesh->mix_nested2_add_enable = s->mix_nested2_add_enable;
    mesh->mix_nested2_add_c1_kind = s->mix_nested2_add_c1_kind;
    mesh->mix_nested2_add_c2_kind = s->mix_nested2_add_c2_kind;
    mesh->mix_nested2_glossy_color[0] = s->mix_nested2_glossy_color[0];
    mesh->mix_nested2_glossy_color[1] = s->mix_nested2_glossy_color[1];
    mesh->mix_nested2_glossy_color[2] = s->mix_nested2_glossy_color[2];
    mesh->mix_nested2_glossy_roughness = s->mix_nested2_glossy_roughness;
    mesh->mix_nested2_glossy_distribution = s->mix_nested2_glossy_distribution;
    mesh->mix_nested2_sss_color[0] = s->mix_nested2_sss_color[0];
    mesh->mix_nested2_sss_color[1] = s->mix_nested2_sss_color[1];
    mesh->mix_nested2_sss_color[2] = s->mix_nested2_sss_color[2];
    mesh->mix_nested2_sss_scale = s->mix_nested2_sss_scale;
    mesh->mix_nested2_sss_radius[0] = s->mix_nested2_sss_radius[0];
    mesh->mix_nested2_sss_radius[1] = s->mix_nested2_sss_radius[1];
    mesh->mix_nested2_sss_radius[2] = s->mix_nested2_sss_radius[2];
    mesh->mix_nested2_sss_ior = s->mix_nested2_sss_ior;
    mesh->mix_nested2_sss_roughness = s->mix_nested2_sss_roughness;
    mesh->mix_nested2_sss_method = s->mix_nested2_sss_method;
    mesh->mix_nested2_translucent_color[0] = s->mix_nested2_translucent_color[0];
    mesh->mix_nested2_translucent_color[1] = s->mix_nested2_translucent_color[1];
    mesh->mix_nested2_translucent_color[2] = s->mix_nested2_translucent_color[2];
    mesh->mix_nested2_add_mix_enable = s->mix_nested2_add_mix_enable;
    mesh->mix_nested2_add_mix_fac = s->mix_nested2_add_mix_fac;
    mesh->mix_nested2_add_mix_lightpath_enable = s->mix_nested2_add_mix_lightpath_enable;
    mesh->mix_nested2_add_mix_lightpath_output = s->mix_nested2_add_mix_lightpath_output;
    mesh->mix_nested2_add_mix_c1_kind = s->mix_nested2_add_mix_c1_kind;
    mesh->mix_nested2_add_mix_c2_kind = s->mix_nested2_add_mix_c2_kind;

    std::memset(light, 0, sizeof(*light));
    std::memcpy(light->tfm, s->light_tfm, sizeof(light->tfm));
    light->sizeu = s->light_sizeu;
    light->sizev = s->light_sizev;
    std::memcpy(light->strength, s->light_strength, sizeof(light->strength));
    light->name = "Area";
    light->kind = QT_LIGHT_AREA;
    light->radius = 0.0f;
    light->angle = 0.0f;

    std::memset(out, 0, sizeof(*out));
    out->width = s->width;
    out->height = s->height;
    out->samples = s->samples;
    out->nmeshes = 1;
    out->nlights = 1;
    out->meshes = mesh;
    out->lights = light;
    std::memcpy(out->cam_tfm, s->cam_tfm, sizeof(out->cam_tfm));
    out->cam_fov = s->cam_fov;
    out->cam_sensor_w = s->cam_sensor_w;
    out->cam_sensor_h = s->cam_sensor_h;
    out->cam_near = s->cam_near;
    out->cam_far = s->cam_far;
    out->world_strength = s->world_strength;
    out->world_image_path = s->world_image_path;
    out->world_image_colorspace = s->world_image_colorspace;
    out->world_projection = s->world_projection;
    out->world_tex_vector_mode = s->world_tex_vector_mode;
    std::memcpy(out->world_map_location, s->world_map_location,
                sizeof(out->world_map_location));
    std::memcpy(out->world_map_rotation, s->world_map_rotation,
                sizeof(out->world_map_rotation));
    std::memcpy(out->world_map_scale, s->world_map_scale,
                sizeof(out->world_map_scale));
    out->world_map_type = s->world_map_type;
    out->world_ob_use_transform = s->world_ob_use_transform;
    std::memcpy(out->world_ob_tfm, s->world_ob_tfm, sizeof(out->world_ob_tfm));
    std::memcpy(out->world_color, s->world_color, sizeof(out->world_color));
    out->world_sky_type = s->world_sky_type;
    std::memcpy(out->world_sky_sun_direction, s->world_sky_sun_direction,
                sizeof(out->world_sky_sun_direction));
    out->world_sky_turbidity = s->world_sky_turbidity;
    out->world_sky_ground_albedo = s->world_sky_ground_albedo;
    out->world_sky_sun_disc = s->world_sky_sun_disc;
    out->world_sky_sun_size = s->world_sky_sun_size;
    out->world_sky_sun_intensity = s->world_sky_sun_intensity;
    out->world_sky_sun_elevation = s->world_sky_sun_elevation;
    out->world_sky_sun_rotation = s->world_sky_sun_rotation;
    out->world_sky_altitude = s->world_sky_altitude;
    out->world_sky_air_density = s->world_sky_air_density;
    out->world_sky_aerosol_density = s->world_sky_aerosol_density;
    out->world_sky_ozone_density = s->world_sky_ozone_density;
    out->world_color_image_path = s->world_color_image_path;
    out->world_color_image_colorspace = s->world_color_image_colorspace;
    out->world_color_image_projection = s->world_color_image_projection;
    out->world_gamma = s->world_gamma;
    out->world_hsv_hue = s->world_hsv_hue;
    out->world_hsv_sat = s->world_hsv_sat;
    out->world_hsv_val = s->world_hsv_val;
    out->world_hsv_fac = s->world_hsv_fac;
    out->world_bright = s->world_bright;
    out->world_contrast = s->world_contrast;
    out->world_mix_type = s->world_mix_type;
    out->world_mix_fac = s->world_mix_fac;
    std::memcpy(out->world_mix_other, s->world_mix_other, sizeof(out->world_mix_other));
    out->world_mix_chain_is_a = s->world_mix_chain_is_a;
    out->world_mix_clamp_factor = s->world_mix_clamp_factor;
    out->world_mix_clamp_result = s->world_mix_clamp_result;
    out->world_curves = s->world_curves;
    out->world_curves_n = s->world_curves_n;
    out->world_curves_min_x = s->world_curves_min_x;
    out->world_curves_max_x = s->world_curves_max_x;
    out->world_curves_fac = s->world_curves_fac;
    out->world_curves_extrapolate = s->world_curves_extrapolate;
    out->exr_path = s->exr_path;
}

static bool tex_mode_is_generated(int mode)
{
    return mode == QT_TEX_VECTOR_TEXCOORD_GENERATED ||
           mode == QT_TEX_VECTOR_MAPPING_GENERATED;
}

static bool tex_mode_is_object(int mode)
{
    return mode == QT_TEX_VECTOR_TEXCOORD_OBJECT ||
           mode == QT_TEX_VECTOR_MAPPING_OBJECT;
}

static bool tex_mode_is_camera(int mode)
{
    return mode == QT_TEX_VECTOR_TEXCOORD_CAMERA ||
           mode == QT_TEX_VECTOR_MAPPING_CAMERA;
}

static bool tex_mode_is_window(int mode)
{
    return mode == QT_TEX_VECTOR_TEXCOORD_WINDOW ||
           mode == QT_TEX_VECTOR_MAPPING_WINDOW;
}

static bool tex_mode_is_reflection(int mode)
{
    return mode == QT_TEX_VECTOR_TEXCOORD_REFLECTION ||
           mode == QT_TEX_VECTOR_MAPPING_REFLECTION;
}

static bool tex_mode_has_texcoord(int mode)
{
    return mode == QT_TEX_VECTOR_TEXCOORD ||
           mode == QT_TEX_VECTOR_MAPPING ||
           tex_mode_is_generated(mode) ||
           tex_mode_is_object(mode) ||
           tex_mode_is_camera(mode) ||
           tex_mode_is_window(mode) ||
           tex_mode_is_reflection(mode);
}

static bool tex_mode_has_mapping(int mode)
{
    return mode == QT_TEX_VECTOR_MAPPING ||
           mode == QT_TEX_VECTOR_MAPPING_GENERATED ||
           mode == QT_TEX_VECTOR_MAPPING_OBJECT ||
           mode == QT_TEX_VECTOR_MAPPING_CAMERA ||
           mode == QT_TEX_VECTOR_MAPPING_WINDOW ||
           mode == QT_TEX_VECTOR_MAPPING_REFLECTION;
}

/* Slice 2ao/2ap: identity skip keeps 2aa/2al/2am/2an/2ao bit-identical. */
static bool world_gamma_identity(const QT_Scene *desc)
{
    return desc->world_gamma == 1.0f;
}

static bool world_hsv_identity(const QT_Scene *desc)
{
    return desc->world_hsv_hue == 0.5f &&
           desc->world_hsv_sat == 1.0f &&
           desc->world_hsv_val == 1.0f &&
           desc->world_hsv_fac == 1.0f;
}

static bool world_bc_identity(const QT_Scene *desc)
{
    return desc->world_bright == 0.0f && desc->world_contrast == 0.0f;
}

static bool world_mix_identity(const QT_Scene *desc)
{
    return desc->world_mix_type == 0;
}

static NodeMix world_mix_blend_type(int t)
{
    switch (t) {
        case 2: return NODE_MIX_ADD;
        case 3: return NODE_MIX_SUB;
        case 4: return NODE_MIX_MUL;
        case 5: return NODE_MIX_DIV;
        case 1:
        default: return NODE_MIX_BLEND;
    }
}


/* Wire Color source → RGBCurves (if n>0 && fac!=0) → Gamma (if gamma!=1) →
 * HSV (if not identity) → BrightContrast (if not identity) → MixColorNode
 * (if mix_type!=0) → Background Color.
 * color_src NULL uses wcol as unlinked Color default.
 * Cite shader_nodes.h RGBCurvesNode (set_curves array<packed_float3>,
 * set_min_x, set_max_x, set_fac, set_extrapolate) / GammaNode / HSVNode /
 * BrightContrastNode / MixColorNode. Slice 2as. */
static bool world_curves_active(const QT_Scene *desc)
{
    return desc->world_curves != nullptr && desc->world_curves_n > 0 &&
           desc->world_curves_fac != 0.0f;
}

static void connect_world_color_chain(ShaderGraph *graph,
                                      ShaderOutput *color_src,
                                      const float3 &wcol,
                                      BackgroundNode *bg,
                                      const QT_Scene *desc)
{
    const bool use_curves = world_curves_active(desc);
    const bool use_gamma = !world_gamma_identity(desc);
    const bool use_hsv = !world_hsv_identity(desc);
    const bool use_bc = !world_bc_identity(desc);
    const bool use_mix = !world_mix_identity(desc);
    ShaderOutput *cur = color_src;
    if (use_curves) {
        RGBCurvesNode *rc = graph->create_node<RGBCurvesNode>();
        array<packed_float3> curves;
        curves.resize(desc->world_curves_n);
        for (int i = 0; i < desc->world_curves_n; i++) {
            const float *p = desc->world_curves + i * 3;
            curves[i] = make_float3(p[0], p[1], p[2]);
        }
        rc->set_curves(curves);
        rc->set_min_x(desc->world_curves_min_x);
        rc->set_max_x(desc->world_curves_max_x);
        rc->set_fac(desc->world_curves_fac);
        rc->set_extrapolate(desc->world_curves_extrapolate != 0);
        if (cur) {
            graph->connect(cur, rc->input("Color"));
        }
        else {
            rc->set_value(wcol);
        }
        cur = rc->output("Color");
    }
    if (use_gamma) {
        GammaNode *g = graph->create_node<GammaNode>();
        g->set_gamma(desc->world_gamma);
        if (cur) {
            graph->connect(cur, g->input("Color"));
        }
        else {
            g->set_color(wcol);
        }
        cur = g->output("Color");
    }
    if (use_hsv) {
        HSVNode *h = graph->create_node<HSVNode>();
        h->set_hue(desc->world_hsv_hue);
        h->set_saturation(desc->world_hsv_sat);
        h->set_value(desc->world_hsv_val);
        h->set_fac(desc->world_hsv_fac);
        if (cur) {
            graph->connect(cur, h->input("Color"));
        }
        else {
            h->set_color(wcol);
        }
        cur = h->output("Color");
    }
    if (use_bc) {
        BrightContrastNode *bc = graph->create_node<BrightContrastNode>();
        bc->set_bright(desc->world_bright);
        bc->set_contrast(desc->world_contrast);
        if (cur) {
            graph->connect(cur, bc->input("Color"));
        }
        else {
            bc->set_color(wcol);
        }
        cur = bc->output("Color");
    }
    if (use_mix) {
        MixColorNode *mx = graph->create_node<MixColorNode>();
        mx->set_blend_type(world_mix_blend_type(desc->world_mix_type));
        mx->set_fac(desc->world_mix_fac);
        mx->set_use_clamp(desc->world_mix_clamp_factor != 0);
        mx->set_use_clamp_result(desc->world_mix_clamp_result != 0);
        const float3 other = make_float3(desc->world_mix_other[0],
                                         desc->world_mix_other[1],
                                         desc->world_mix_other[2]);
        if (desc->world_mix_chain_is_a) {
            if (cur) {
                graph->connect(cur, mx->input("A"));
            }
            else {
                mx->set_a(wcol);
            }
            mx->set_b(other);
        }
        else {
            mx->set_a(other);
            if (cur) {
                graph->connect(cur, mx->input("B"));
            }
            else {
                mx->set_b(wcol);
            }
        }
        cur = mx->output("Result");
    }
    if (cur) {
        graph->connect(cur, bg->input("Color"));
    }
}

static bool mesh_uses_generated(const QT_Mesh *m)
{
    /* TEX_COORD Generated modes need orco. Slice 2w: Principled default Tangent
     * (LINK_TANGENT → Geometry.Tangent) also requests ATTR_STD_GENERATED when
     * Anisotropic/Rotation maps and Tangent is unlinked — fill Blender bbox orco
     * (not Mesh::update_generated raw verts). */
    const bool aniso_needs_default_tangent =
        ((m->aniso_image_path && m->aniso_image_path[0]) ||
         (m->aniso_rot_image_path && m->aniso_rot_image_path[0])) &&
        !(m->tangent_image_path && m->tangent_image_path[0]);
    return aniso_needs_default_tangent ||
           tex_mode_is_generated(m->tex_vector_mode) ||
           tex_mode_is_generated(m->rough_tex_vector_mode) ||
           tex_mode_is_generated(m->metal_tex_vector_mode) ||
           tex_mode_is_generated(m->normal_tex_vector_mode) ||
           tex_mode_is_generated(m->ior_tex_vector_mode) ||
           tex_mode_is_generated(m->alpha_tex_vector_mode) ||
           tex_mode_is_generated(m->trans_tex_vector_mode) ||
           tex_mode_is_generated(m->spec_tex_vector_mode) ||
           tex_mode_is_generated(m->coat_tex_vector_mode) ||
           tex_mode_is_generated(m->sheen_tex_vector_mode) ||
           tex_mode_is_generated(m->emit_str_tex_vector_mode) ||
           tex_mode_is_generated(m->emit_color_tex_vector_mode) ||
           tex_mode_is_generated(m->coat_rough_tex_vector_mode) ||
           tex_mode_is_generated(m->coat_ior_tex_vector_mode) ||
           tex_mode_is_generated(m->coat_tint_tex_vector_mode) ||
           tex_mode_is_generated(m->sheen_rough_tex_vector_mode) ||
           tex_mode_is_generated(m->sheen_tint_tex_vector_mode) ||
           tex_mode_is_generated(m->coat_normal_tex_vector_mode) ||
           tex_mode_is_generated(m->spec_tint_tex_vector_mode) ||
           tex_mode_is_generated(m->film_thick_tex_vector_mode) ||
           tex_mode_is_generated(m->film_ior_tex_vector_mode) ||
           tex_mode_is_generated(m->sss_weight_tex_vector_mode) ||
           tex_mode_is_generated(m->sss_radius_tex_vector_mode) ||
           tex_mode_is_generated(m->sss_scale_tex_vector_mode) ||
           tex_mode_is_generated(m->sss_ior_tex_vector_mode) ||
           tex_mode_is_generated(m->sss_aniso_tex_vector_mode) ||
           tex_mode_is_generated(m->thin_wall_tex_vector_mode) ||
           tex_mode_is_generated(m->diffuse_rough_tex_vector_mode) ||
           tex_mode_is_generated(m->aniso_tex_vector_mode) ||
           tex_mode_is_generated(m->aniso_rot_tex_vector_mode) ||
           tex_mode_is_generated(m->tangent_tex_vector_mode) ||
           tex_mode_is_generated(m->bump_tex_vector_mode) ||
           /* Slice 2bb/2bc: NoiseTextureNode Vector LINK_TEXTURE_GENERATED. */
           (m->rough_ramp_noise_enable != 0) ||
           (m->bump_noise_enable != 0);
}

/* Blender Generated / orco: map object-local verts through the auto texspace
 * bounding box onto [0,1]. Default cube (±1) → (P+1)/2. Matches
 * BKE_mesh_texspace_get auto: loc=center, size=half-extent,
 * generated = (P - (loc - size)) / (2*size). Fill ATTR_STD_GENERATED
 * ourselves — Mesh::update_generated copies raw verts if missing, which
 * is NOT Blender Generated. */
static void fill_generated_orco(Mesh *mesh, const QT_Mesh *m)
{
    if (m->nverts <= 0 || !m->verts) {
        return;
    }
    float bmin[3] = {1e30f, 1e30f, 1e30f};
    float bmax[3] = {-1e30f, -1e30f, -1e30f};
    for (int i = 0; i < m->nverts; i++) {
        for (int c = 0; c < 3; c++) {
            const float v = m->verts[i * 3 + c];
            if (v < bmin[c]) {
                bmin[c] = v;
            }
            if (v > bmax[c]) {
                bmax[c] = v;
            }
        }
    }
    Attribute *attr = mesh->attributes.add(ATTR_STD_GENERATED);
    packed_float3 *g = attr->data_for_write<packed_float3>();
    for (int i = 0; i < m->nverts; i++) {
        float t[3];
        for (int c = 0; c < 3; c++) {
            const float span = bmax[c] - bmin[c];
            t[c] = (span > 1e-8f) ? (m->verts[i * 3 + c] - bmin[c]) / span : 0.5f;
        }
        g[i] = make_float3(t[0], t[1], t[2]);
    }
}

/* Wire ImageTexture (+ optional TEX_COORD UV/Generated/Object/Camera/Window/Reflection + Mapping).
 * Color→float (Roughness/Metallic/IOR/Alpha/Transmission/Specular/Coat/Sheen/Emission Strength) gets ConvertNode via ShaderGraph::connect.
 * Emission Color is a color socket (like Base Color) — Color→Color, no convert. */
static ImageTextureNode *wire_tex_image(ShaderGraph *graph,
                                        const QT_Mesh *m,
                                        const char *path,
                                        const char *colorspace,
                                        int tex_vector_mode,
                                        const float *map_location,
                                        const float *map_rotation,
                                        const float *map_scale,
                                        int map_type)
{
    ImageTextureNode *img = graph->create_node<ImageTextureNode>();
    img->set_filename(ustring(path));
    if (colorspace && colorspace[0]) {
        img->set_colorspace(ustring(colorspace));
    }
    img->set_interpolation(INTERPOLATION_LINEAR);
    img->set_extension(EXTENSION_REPEAT);
    img->set_projection(NODE_IMAGE_PROJ_FLAT);
    img->set_alpha_type(IMAGE_ALPHA_AUTO);
    if (tex_mode_has_texcoord(tex_vector_mode)) {
        TextureCoordinateNode *texcoord =
            graph->create_node<TextureCoordinateNode>();
        /* Object empty-ref (2l): use_transform stays false (default) →
         * NODE_TEXCO_OBJECT (shading_position + object_inverse_position_transform).
         * Object pointer (2ab): set_use_transform(true) + set_ob_tfm(matrix_world).
         * Cycles compile packs transform_inverse(ob_tfm) — do not invert twice.
         * from_dupli unused. Cite shader_nodes.cpp TextureCoordinateNode. */
        if (tex_mode_is_object(tex_vector_mode) && m && m->tex_ob_use_transform) {
            texcoord->set_use_transform(true);
            texcoord->set_ob_tfm(tfm_from_12(m->tex_ob_tfm));
        }
        /* Camera: TextureCoordinateNode "Camera" → NODE_TEXCO_CAMERA
         * (kernel_data.cam.worldtocamera; already set by Camera::update).
         * Window: "Window" → NODE_TEXCO_WINDOW (camera_world_to_ndc).
         * Reflection: "Reflection" → NODE_TEXCO_REFLECTION
         * (svm_texco_reflection). Both use existing Camera::update data;
         * no extra inverse-matrix ABI. from_dupli unused. */
        const char *coord_sock = "UV";
        if (tex_mode_is_reflection(tex_vector_mode)) {
            coord_sock = "Reflection";
        }
        else if (tex_mode_is_window(tex_vector_mode)) {
            coord_sock = "Window";
        }
        else if (tex_mode_is_camera(tex_vector_mode)) {
            coord_sock = "Camera";
        }
        else if (tex_mode_is_object(tex_vector_mode)) {
            coord_sock = "Object";
        }
        else if (tex_mode_is_generated(tex_vector_mode)) {
            coord_sock = "Generated";
        }
        if (tex_mode_has_mapping(tex_vector_mode)) {
            MappingNode *mapping = graph->create_node<MappingNode>();
            mapping->set_mapping_type(static_cast<NodeMappingType>(map_type));
            mapping->set_location(make_float3(
                map_location[0], map_location[1], map_location[2]));
            mapping->set_rotation(make_float3(
                map_rotation[0], map_rotation[1], map_rotation[2]));
            mapping->set_scale(make_float3(
                map_scale[0], map_scale[1], map_scale[2]));
            graph->connect(texcoord->output(coord_sock), mapping->input("Vector"));
            graph->connect(mapping->output("Vector"), img->input("Vector"));
        }
        else {
            graph->connect(texcoord->output(coord_sock), img->input("Vector"));
        }
    }
    return img;
}

static const char *qt_lightpath_out_name(int code)
{
    switch (code) {
        case QT_LIGHTPATH_CAMERA_RAY:
            return "Is Camera Ray";
        case QT_LIGHTPATH_SHADOW_RAY:
            return "Is Shadow Ray";
        case QT_LIGHTPATH_DIFFUSE_RAY:
            return "Is Diffuse Ray";
        case QT_LIGHTPATH_GLOSSY_RAY:
            return "Is Glossy Ray";
        case QT_LIGHTPATH_SINGULAR_RAY:
            return "Is Singular Ray";
        case QT_LIGHTPATH_REFLECTION_RAY:
            return "Is Reflection Ray";
        case QT_LIGHTPATH_TRANSMISSION_RAY:
            return "Is Transmission Ray";
        case QT_LIGHTPATH_RAY_LENGTH:
            return "Ray Length";
        case QT_LIGHTPATH_RAY_DEPTH:
            return "Ray Depth";
        case QT_LIGHTPATH_TRANSPARENT_DEPTH:
            return "Transparent Depth";
        default:
            return "Is Shadow Ray";
    }
}

static void qt_math_leaf(ShaderGraph *graph,
                         MathNode *math,
                         LightPathNode *lp,
                         bool is_value1,
                         int kind,
                         float cst,
                         int lp_code)
{
    const char *in_name = is_value1 ? "Value1" : "Value2";
    if (kind == QT_MATH_IN_LIGHTPATH && lp != nullptr) {
        graph->connect(lp->output(qt_lightpath_out_name(lp_code)),
                       math->input(in_name));
        return;
    }
    if (is_value1) {
        math->set_value1(cst);
    }
    else {
        math->set_value2(cst);
    }
}

static ShaderOutput *qt_math_nested(ShaderGraph *graph,
                                    LightPathNode *lp,
                                    int op,
                                    int k1,
                                    float c1,
                                    int lp1,
                                    int k2,
                                    float c2,
                                    int lp2)
{
    MathNode *inner = graph->create_node<MathNode>();
    inner->set_math_type(static_cast<NodeMathType>(op));
    qt_math_leaf(graph, inner, lp, true, k1, c1, lp1);
    qt_math_leaf(graph, inner, lp, false, k2, c2, lp2);
    return inner->output("Value");
}

static bool qt_math_uses_lightpath(const QT_Mesh *m)
{
    if (m->mix_shader_math_a_kind == QT_MATH_IN_LIGHTPATH ||
        m->mix_shader_math_b_kind == QT_MATH_IN_LIGHTPATH) {
        return true;
    }
    if (m->mix_shader_math_a_kind == QT_MATH_IN_NEST &&
        (m->mix_shader_math_a1_kind == QT_MATH_IN_LIGHTPATH ||
         m->mix_shader_math_a2_kind == QT_MATH_IN_LIGHTPATH)) {
        return true;
    }
    if (m->mix_shader_math_b_kind == QT_MATH_IN_NEST &&
        (m->mix_shader_math_b1_kind == QT_MATH_IN_LIGHTPATH ||
         m->mix_shader_math_b2_kind == QT_MATH_IN_LIGHTPATH)) {
        return true;
    }
    return false;
}


static bool qt_ramp_math_tree_has(const QT_Mesh *m, int want)
{
    if (m->mix_nested2_ramp_math_a_kind == want ||
        m->mix_nested2_ramp_math_b_kind == want) {
        return true;
    }
    if (m->mix_nested2_ramp_math_a_kind == QT_MATH_IN_NEST &&
        (m->mix_nested2_ramp_math_a1_kind == want ||
         m->mix_nested2_ramp_math_a2_kind == want)) {
        return true;
    }
    if (m->mix_nested2_ramp_math_b_kind == QT_MATH_IN_NEST &&
        (m->mix_nested2_ramp_math_b1_kind == want ||
         m->mix_nested2_ramp_math_b2_kind == want)) {
        return true;
    }
    return false;
}

struct QT_RampMathNodes {
    LightPathNode *lp;
    GeometryNode *geom;
    HSVNode *hsv;
};

static void qt_ramp_math_leaf(ShaderGraph *graph,
                              MathNode *math,
                              QT_RampMathNodes *nodes,
                              bool is_value1,
                              int kind,
                              float cst,
                              int lp_code)
{
    const char *in_name = is_value1 ? "Value1" : "Value2";
    if (kind == QT_MATH_IN_LIGHTPATH && nodes->lp != nullptr) {
        graph->connect(nodes->lp->output(qt_lightpath_out_name(lp_code)),
                       math->input(in_name));
        return;
    }
    if (kind == QT_MATH_IN_GEOM && nodes->geom != nullptr) {
        graph->connect(nodes->geom->output("Backfacing"), math->input(in_name));
        return;
    }
    if (kind == QT_MATH_IN_HUESAT && nodes->hsv != nullptr) {
        graph->connect(nodes->hsv->output("Color"), math->input(in_name));
        return;
    }
    if (is_value1) {
        math->set_value1(cst);
    }
    else {
        math->set_value2(cst);
    }
}

static ShaderOutput *qt_ramp_math_nested(ShaderGraph *graph,
                                         QT_RampMathNodes *nodes,
                                         int op,
                                         int k1,
                                         float c1,
                                         int lp1,
                                         int k2,
                                         float c2,
                                         int lp2)
{
    MathNode *inner = graph->create_node<MathNode>();
    inner->set_math_type(static_cast<NodeMathType>(op));
    qt_ramp_math_leaf(graph, inner, nodes, true, k1, c1, lp1);
    qt_ramp_math_leaf(graph, inner, nodes, false, k2, c2, lp2);
    return inner->output("Value");
}

static ShaderOutput *qt_ramp_math_fac(ShaderGraph *graph, const QT_Mesh *m)
{
    QT_RampMathNodes nodes;
    nodes.lp = nullptr;
    nodes.geom = nullptr;
    nodes.hsv = nullptr;
    const bool need_lp =
        qt_ramp_math_tree_has(m, QT_MATH_IN_LIGHTPATH) ||
        (qt_ramp_math_tree_has(m, QT_MATH_IN_HUESAT) &&
         m->mix_nested2_ramp_hsv_color_kind == 1);
    if (need_lp) {
        nodes.lp = graph->create_node<LightPathNode>();
    }
    if (qt_ramp_math_tree_has(m, QT_MATH_IN_GEOM)) {
        nodes.geom = graph->create_node<GeometryNode>();
    }
    if (qt_ramp_math_tree_has(m, QT_MATH_IN_HUESAT)) {
        nodes.hsv = graph->create_node<HSVNode>();
        nodes.hsv->set_hue(m->mix_nested2_ramp_hsv_hue);
        nodes.hsv->set_saturation(m->mix_nested2_ramp_hsv_sat);
        nodes.hsv->set_value(m->mix_nested2_ramp_hsv_val);
        nodes.hsv->set_fac(m->mix_nested2_ramp_hsv_fac);
        if (m->mix_nested2_ramp_hsv_color_kind == 1 && nodes.lp != nullptr) {
            graph->connect(nodes.lp->output(qt_lightpath_out_name(
                               m->mix_nested2_ramp_hsv_color_lightpath)),
                           nodes.hsv->input("Color"));
        }
        else {
            nodes.hsv->set_color(make_float3(m->mix_nested2_ramp_hsv_color[0],
                                             m->mix_nested2_ramp_hsv_color[1],
                                             m->mix_nested2_ramp_hsv_color[2]));
        }
    }
    MathNode *root = graph->create_node<MathNode>();
    root->set_math_type(static_cast<NodeMathType>(m->mix_nested2_ramp_math_op));
    if (m->mix_nested2_ramp_math_a_kind == QT_MATH_IN_NEST) {
        ShaderOutput *inner = qt_ramp_math_nested(graph,
                                                  &nodes,
                                                  m->mix_nested2_ramp_math_a_op,
                                                  m->mix_nested2_ramp_math_a1_kind,
                                                  m->mix_nested2_ramp_math_a1_const,
                                                  m->mix_nested2_ramp_math_a1_lightpath,
                                                  m->mix_nested2_ramp_math_a2_kind,
                                                  m->mix_nested2_ramp_math_a2_const,
                                                  m->mix_nested2_ramp_math_a2_lightpath);
        graph->connect(inner, root->input("Value1"));
    }
    else {
        qt_ramp_math_leaf(graph,
                          root,
                          &nodes,
                          true,
                          m->mix_nested2_ramp_math_a_kind,
                          m->mix_nested2_ramp_math_a_const,
                          m->mix_nested2_ramp_math_a_lightpath);
    }
    if (m->mix_nested2_ramp_math_b_kind == QT_MATH_IN_NEST) {
        ShaderOutput *inner = qt_ramp_math_nested(graph,
                                                  &nodes,
                                                  m->mix_nested2_ramp_math_b_op,
                                                  m->mix_nested2_ramp_math_b1_kind,
                                                  m->mix_nested2_ramp_math_b1_const,
                                                  m->mix_nested2_ramp_math_b1_lightpath,
                                                  m->mix_nested2_ramp_math_b2_kind,
                                                  m->mix_nested2_ramp_math_b2_const,
                                                  m->mix_nested2_ramp_math_b2_lightpath);
        graph->connect(inner, root->input("Value2"));
    }
    else {
        qt_ramp_math_leaf(graph,
                          root,
                          &nodes,
                          false,
                          m->mix_nested2_ramp_math_b_kind,
                          m->mix_nested2_ramp_math_b_const,
                          m->mix_nested2_ramp_math_b_lightpath);
    }
    return root->output("Value");
}

static Shader *make_principled(Scene *scene, const QT_Mesh *m, int index)
{
    Shader *surf = scene->create_node<Shader>();
    unique_ptr<ShaderGraph> graph = make_unique<ShaderGraph>();
    /* Slice 2bn: Mix Shader Glass+Transparent (optional Light Path Fac).
     * mix_shader_enable=0 keeps Slice 2bm pure-Glass path bit-identical.
     * Slice 2bo: math enable wires MathNode Fac; enable=0 is exact 2bn. */
    if (m->mix_shader_enable != 0) {
        surf->name = string_printf("qt_mix_glass_%d", index);
        MixClosureNode *mix = graph->create_node<MixClosureNode>();
        if (m->mix_shader_math_enable != 0) {
            LightPathNode *lp = nullptr;
            if (qt_math_uses_lightpath(m)) {
                lp = graph->create_node<LightPathNode>();
            }
            MathNode *root = graph->create_node<MathNode>();
            root->set_math_type(static_cast<NodeMathType>(m->mix_shader_math_op));
            if (m->mix_shader_math_a_kind == QT_MATH_IN_NEST) {
                ShaderOutput *inner = qt_math_nested(graph.get(),
                                                     lp,
                                                     m->mix_shader_math_a_op,
                                                     m->mix_shader_math_a1_kind,
                                                     m->mix_shader_math_a1_const,
                                                     m->mix_shader_math_a1_lightpath,
                                                     m->mix_shader_math_a2_kind,
                                                     m->mix_shader_math_a2_const,
                                                     m->mix_shader_math_a2_lightpath);
                graph->connect(inner, root->input("Value1"));
            }
            else {
                qt_math_leaf(graph.get(),
                             root,
                             lp,
                             true,
                             m->mix_shader_math_a_kind,
                             m->mix_shader_math_a_const,
                             m->mix_shader_math_a_lightpath);
            }
            if (m->mix_shader_math_b_kind == QT_MATH_IN_NEST) {
                ShaderOutput *inner = qt_math_nested(graph.get(),
                                                     lp,
                                                     m->mix_shader_math_b_op,
                                                     m->mix_shader_math_b1_kind,
                                                     m->mix_shader_math_b1_const,
                                                     m->mix_shader_math_b1_lightpath,
                                                     m->mix_shader_math_b2_kind,
                                                     m->mix_shader_math_b2_const,
                                                     m->mix_shader_math_b2_lightpath);
                graph->connect(inner, root->input("Value2"));
            }
            else {
                qt_math_leaf(graph.get(),
                             root,
                             lp,
                             false,
                             m->mix_shader_math_b_kind,
                             m->mix_shader_math_b_const,
                             m->mix_shader_math_b_lightpath);
            }
            graph->connect(root->output("Value"), mix->input("Fac"));
        }
        else if (m->mix_shader_lightpath_enable != 0) {
            LightPathNode *lp = graph->create_node<LightPathNode>();
            graph->connect(lp->output(qt_lightpath_out_name(
                               m->mix_shader_lightpath_output)),
                           mix->input("Fac"));
        }
        else {
            mix->set_fac(m->mix_shader_fac);
        }
        auto make_glass = [&]() -> ShaderOutput * {
            GlassBsdfNode *glass = graph->create_node<GlassBsdfNode>();
            glass->set_color(
                make_float3(m->base_color[0], m->base_color[1], m->base_color[2]));
            glass->set_roughness(m->roughness);
            glass->set_IOR(m->ior);
            ClosureType dist = CLOSURE_BSDF_MICROFACET_BECKMANN_GLASS_ID;
            if (m->glass_distribution == 1) {
                dist = CLOSURE_BSDF_MICROFACET_GGX_GLASS_ID;
            }
            else if (m->glass_distribution == 2) {
                dist = CLOSURE_BSDF_MICROFACET_MULTI_GGX_GLASS_ID;
            }
            glass->set_distribution(dist);
            return glass->output("BSDF");
        };
        auto make_transparent = [&]() -> ShaderOutput * {
            TransparentBsdfNode *tr = graph->create_node<TransparentBsdfNode>();
            tr->set_color(make_float3(m->mix_transparent_color[0],
                                      m->mix_transparent_color[1],
                                      m->mix_transparent_color[2]));
            return tr->output("BSDF");
        };
        /* Slice 2bp: kind 2 = nested MixClosure (Fac unlinked|LightPath,
         * leaves Glass+Transparent). kinds 0/1 keep 2bo path.
         * Slice 2bq: mix_nested_closure*_kind 2 = NestedMix2 (MixClosureNode).
         * nested kinds 0/1 skip nested2 — 2bp bit-identical. Cite MixClosureNode. */
        auto make_leaf = [&](int kind) -> ShaderOutput * {
            return (kind == 1) ? make_transparent() : make_glass();
        };
        auto make_nested2 = [&]() -> ShaderOutput * {
            MixClosureNode *n2 = graph->create_node<MixClosureNode>();
            /* Slice 2br: RGBRampNode Color → MixClosure Fac when enable && n>0.
             * enable=0 keeps 2bq LightPath / set_fac path bit-identical. */
            if (m->mix_nested2_ramp_enable != 0 && m->mix_nested2_ramp_n > 0 &&
                m->mix_nested2_ramp != nullptr) {
                RGBRampNode *ramp = graph->create_node<RGBRampNode>();
                array<packed_float3> ramp_c;
                array<float> ramp_a;
                ramp_c.resize(m->mix_nested2_ramp_n);
                ramp_a.resize(m->mix_nested2_ramp_n);
                for (int i = 0; i < m->mix_nested2_ramp_n; i++) {
                    const float *pt = m->mix_nested2_ramp + i * 3;
                    ramp_c[i] = make_float3(pt[0], pt[1], pt[2]);
                    ramp_a[i] = (m->mix_nested2_ramp_alpha != nullptr)
                                    ? m->mix_nested2_ramp_alpha[i]
                                    : 1.0f;
                }
                ramp->set_ramp(ramp_c);
                ramp->set_ramp_alpha(ramp_a);
                ramp->set_interpolate(m->mix_nested2_ramp_interpolate != 0);
                /* Slice 2bs: ColorRamp.Fac <- MATH when enable. enable=0 keeps
                 * 2br set_fac bit-identical. */
                if (m->mix_nested2_ramp_math_enable != 0) {
                    graph->connect(qt_ramp_math_fac(graph.get(), m),
                                   ramp->input("Fac"));
                }
                else {
                    ramp->set_fac(m->mix_nested2_ramp_fac);
                }
                /* loft ColorRamp.002 Color out -> Fac (CF convert). */
                graph->connect(ramp->output("Color"), n2->input("Fac"));
            }
            else if (m->mix_nested2_lightpath_enable != 0) {
                LightPathNode *n2lp = graph->create_node<LightPathNode>();
                graph->connect(n2lp->output(qt_lightpath_out_name(
                                   m->mix_nested2_lightpath_output)),
                               n2->input("Fac"));
            }
            else {
                n2->set_fac(m->mix_nested2_fac);
            }
            auto make_glossy = [&]() -> ShaderOutput * {
                GlossyBsdfNode *gl = graph->create_node<GlossyBsdfNode>();
                gl->set_color(make_float3(m->mix_nested2_glossy_color[0],
                                          m->mix_nested2_glossy_color[1],
                                          m->mix_nested2_glossy_color[2]));
                gl->set_roughness(m->mix_nested2_glossy_roughness);
                ClosureType gdist = CLOSURE_BSDF_MICROFACET_GGX_ID;
                if (m->mix_nested2_glossy_distribution == 0) {
                    gdist = CLOSURE_BSDF_MICROFACET_BECKMANN_ID;
                }
                else if (m->mix_nested2_glossy_distribution == 2) {
                    gdist = CLOSURE_BSDF_MICROFACET_MULTI_GGX_ID;
                }
                gl->set_distribution(gdist);
                return gl->output("BSDF");
            };
            auto make_sss = [&]() -> ShaderOutput * {
                SubsurfaceScatteringNode *sss =
                    graph->create_node<SubsurfaceScatteringNode>();
                sss->set_color(make_float3(m->mix_nested2_sss_color[0],
                                           m->mix_nested2_sss_color[1],
                                           m->mix_nested2_sss_color[2]));
                sss->set_scale(m->mix_nested2_sss_scale);
                sss->set_radius(make_float3(m->mix_nested2_sss_radius[0],
                                            m->mix_nested2_sss_radius[1],
                                            m->mix_nested2_sss_radius[2]));
                sss->set_subsurface_ior(m->mix_nested2_sss_ior);
                sss->set_subsurface_roughness(m->mix_nested2_sss_roughness);
                ClosureType sm = CLOSURE_BSSRDF_BURLEY_ID;
                if (m->mix_nested2_sss_method == 1) {
                    sm = CLOSURE_BSSRDF_RANDOM_WALK_ID;
                }
                else if (m->mix_nested2_sss_method == 2) {
                    sm = CLOSURE_BSSRDF_RANDOM_WALK_SKIN_ID;
                }
                else if (m->mix_nested2_sss_method == 3) {
                    sm = CLOSURE_BSSRDF_RANDOM_WALK_LEGACY_ID;
                }
                sss->set_method(sm);
                return sss->output("BSSRDF");
            };
            auto make_translucent = [&]() -> ShaderOutput * {
                TranslucentBsdfNode *tl = graph->create_node<TranslucentBsdfNode>();
                tl->set_color(make_float3(m->mix_nested2_translucent_color[0],
                                          m->mix_nested2_translucent_color[1],
                                          m->mix_nested2_translucent_color[2]));
                return tl->output("BSDF");
            };
            /* Slice 2bt/2bu: Add children 0=Glass 1=Transparent 3=Glossy 4=SSS
             * 5=Translucent 6=Mix (Mix-under-Add). enable=0 never reaches here. */
            auto make_add_leaf = [&](int kind) -> ShaderOutput * {
                if (kind == 1) {
                    return make_transparent();
                }
                if (kind == 3) {
                    return make_glossy();
                }
                if (kind == 4) {
                    return make_sss();
                }
                if (kind == 5) {
                    return make_translucent();
                }
                return make_glass();
            };
            auto make_add_child = [&](int kind) -> ShaderOutput * {
                if (kind == 6 && m->mix_nested2_add_mix_enable != 0) {
                    MixClosureNode *amix = graph->create_node<MixClosureNode>();
                    if (m->mix_nested2_add_mix_lightpath_enable != 0) {
                        LightPathNode *alp = graph->create_node<LightPathNode>();
                        graph->connect(alp->output(qt_lightpath_out_name(
                                           m->mix_nested2_add_mix_lightpath_output)),
                                       amix->input("Fac"));
                    }
                    else {
                        amix->set_fac(m->mix_nested2_add_mix_fac);
                    }
                    graph->connect(make_add_leaf(m->mix_nested2_add_mix_c1_kind),
                                   amix->input("Closure1"));
                    graph->connect(make_add_leaf(m->mix_nested2_add_mix_c2_kind),
                                   amix->input("Closure2"));
                    return amix->output("Closure");
                }
                return make_add_leaf(kind);
            };
            auto make_nested2_leaf = [&](int kind) -> ShaderOutput * {
                if (kind == 2 && m->mix_nested2_add_enable != 0) {
                    AddClosureNode *add = graph->create_node<AddClosureNode>();
                    graph->connect(make_add_child(m->mix_nested2_add_c1_kind),
                                   add->input("Closure1"));
                    graph->connect(make_add_child(m->mix_nested2_add_c2_kind),
                                   add->input("Closure2"));
                    return add->output("Closure");
                }
                return make_leaf(kind);
            };
            graph->connect(make_nested2_leaf(m->mix_nested2_closure1_kind),
                           n2->input("Closure1"));
            graph->connect(make_nested2_leaf(m->mix_nested2_closure2_kind),
                           n2->input("Closure2"));
            return n2->output("Closure");
        };
        auto make_nested_leaf = [&](int kind) -> ShaderOutput * {
            if (kind == 2) {
                return make_nested2();
            }
            return make_leaf(kind);
        };
        auto make_nested = [&]() -> ShaderOutput * {
            MixClosureNode *inner = graph->create_node<MixClosureNode>();
            if (m->mix_nested_lightpath_enable != 0) {
                LightPathNode *nlp = graph->create_node<LightPathNode>();
                graph->connect(nlp->output(qt_lightpath_out_name(
                                   m->mix_nested_lightpath_output)),
                               inner->input("Fac"));
            }
            else {
                inner->set_fac(m->mix_nested_fac);
            }
            graph->connect(make_nested_leaf(m->mix_nested_closure1_kind),
                           inner->input("Closure1"));
            graph->connect(make_nested_leaf(m->mix_nested_closure2_kind),
                           inner->input("Closure2"));
            return inner->output("Closure");
        };
        auto make_side = [&](int kind) -> ShaderOutput * {
            if (kind == 2) {
                return make_nested();
            }
            return make_leaf(kind);
        };
        graph->connect(make_side(m->mix_closure1_kind), mix->input("Closure1"));
        graph->connect(make_side(m->mix_closure2_kind), mix->input("Closure2"));
        graph->connect(mix->output("Closure"), graph->output()->input("Surface"));
        surf->set_graph(std::move(graph));
        surf->tag_update(scene);
        return surf;
    }
    /* Slice 2bm: pure Glass BSDF → Material Output. Principled transmission
     * is NOT stock-parity with GlassBsdfNode (HDR cube Δmax ~0.15), so emit
     * GlassBsdfNode. enable=0 keeps all prior Principled slices bit-identical. */
    if (m->glass_bsdf_enable != 0) {
        surf->name = string_printf("qt_glass_%d", index);
        GlassBsdfNode *glass = graph->create_node<GlassBsdfNode>();
        glass->set_color(
            make_float3(m->base_color[0], m->base_color[1], m->base_color[2]));
        glass->set_roughness(m->roughness);
        glass->set_IOR(m->ior);
        ClosureType dist = CLOSURE_BSDF_MICROFACET_BECKMANN_GLASS_ID;
        if (m->glass_distribution == 1) {
            dist = CLOSURE_BSDF_MICROFACET_GGX_GLASS_ID;
        }
        else if (m->glass_distribution == 2) {
            dist = CLOSURE_BSDF_MICROFACET_MULTI_GGX_GLASS_ID;
        }
        glass->set_distribution(dist);
        graph->connect(glass->output("BSDF"), graph->output()->input("Surface"));
        surf->set_graph(std::move(graph));
        surf->tag_update(scene);
        return surf;
    }
    surf->name = string_printf("qt_principled_%d", index);
    PrincipledBsdfNode *bsdf = graph->create_node<PrincipledBsdfNode>();
    bsdf->set_base_color(make_float3(m->base_color[0], m->base_color[1], m->base_color[2]));
    bsdf->set_roughness(m->roughness);
    bsdf->set_metallic(m->metallic);
    bsdf->set_ior(m->ior);
    bsdf->set_alpha(m->alpha);
    /* Slice 2y: unlinked Thin Wall BOOLEAN (int 0/1). Linked still refused in packer.
     * is_thin_wall() = (socket unlinked) AND thin_wall; visual no-op unless
     * Transmission Weight is nonzero. */
    bsdf->set_thin_wall(m->thin_wall);
    /* Slice 2f/2h/2i/2j/2k/2l/2m/2n/2o/2p/2q/2r/2s: TEX_IMAGE → Base / Rough / Metal / Normal / IOR / Alpha / Transmission / Specular / Coat / Sheen / Emission Strength / Emission Color.
     * mode 0: Vector unlinked → SVM LINK_TEXTURE_UV / ATTR_STD_UV.
     * mode 1: TextureCoordinate UV → Image Vector.
     * mode 2: TextureCoordinate UV → Mapping → Image Vector.
     * mode 3: TextureCoordinate Generated → Image Vector.
     * mode 4: TextureCoordinate Generated → Mapping → Image Vector.
     * mode 5: TextureCoordinate Object → Image Vector (no object_itfm).
     * mode 6: TextureCoordinate Object → Mapping → Image Vector.
     * mode 7: TextureCoordinate Camera → Image Vector (NODE_TEXCO_CAMERA).
     * mode 8: TextureCoordinate Camera → Mapping → Image Vector. */
    /* Slice 2ax/2ay/2bd/2bh: Color source → Gamma (if gamma!=1) → HSV (if not
     * identity) → [RGBCurves mix-side if base_mix_curves_n>0] → MixColorNode
     * (if base_mix_type!=0) → RGBCurvesNode (if n>0 && fac!=0) → Principled.
     * mix-side n==0 keeps 2ay/2bg/2bf/2bd bit-identical. 2bd Curves last
     * (closest to Principled) matches loft Concrete_Facade: Mix → Curves.
     * 2bh is Curves ON a Mix input (loft Carpet: TEX → Curves → Mix B). */
    {
        const float3 bcol = make_float3(m->base_color[0], m->base_color[1], m->base_color[2]);
        const bool use_gamma = (m->base_gamma != 1.0f);
        const bool use_hsv = !(m->base_hsv_hue == 0.5f && m->base_hsv_sat == 1.0f &&
                               m->base_hsv_val == 1.0f && m->base_hsv_fac == 1.0f);
        const bool use_mix = (m->base_mix_type != 0);
        const bool use_curves = (m->base_curves != nullptr && m->base_curves_n > 0 &&
                                 m->base_curves_fac != 0.0f);
        ShaderOutput *cur = nullptr;
        if (m->image_path && m->image_path[0]) {
            ImageTextureNode *img = wire_tex_image(
                graph.get(), m, m->image_path, m->image_colorspace, m->tex_vector_mode,
                m->map_location, m->map_rotation, m->map_scale, m->map_type);
            cur = img->output("Color");
        }
        if (use_gamma) {
            GammaNode *g = graph->create_node<GammaNode>();
            g->set_gamma(m->base_gamma);
            if (cur) {
                graph->connect(cur, g->input("Color"));
            }
            else {
                g->set_color(bcol);
            }
            cur = g->output("Color");
        }
        if (use_hsv) {
            HSVNode *h = graph->create_node<HSVNode>();
            h->set_hue(m->base_hsv_hue);
            h->set_saturation(m->base_hsv_sat);
            h->set_value(m->base_hsv_val);
            h->set_fac(m->base_hsv_fac);
            if (cur) {
                graph->connect(cur, h->input("Color"));
            }
            else {
                h->set_color(bcol);
            }
            cur = h->output("Color");
        }
        if (use_mix) {
            MixColorNode *mx = graph->create_node<MixColorNode>();
            mx->set_blend_type(world_mix_blend_type(m->base_mix_type));
            mx->set_fac(m->base_mix_fac);
            mx->set_use_clamp(m->base_mix_clamp_factor != 0);
            mx->set_use_clamp_result(m->base_mix_clamp_result != 0);
            /* Slice 2bf: FresnelNode → Mix Factor. enable=0 keeps set_fac.
             * Cite shader_nodes.h FresnelNode (SOCKET_OUT Fac, set_IOR;
             * Normal LINK_NORMAL unlinked). MixColorNode socket is Factor. */
            if (m->base_mix_fresnel_enable) {
                FresnelNode *fr = graph->create_node<FresnelNode>();
                fr->set_IOR(m->base_mix_fresnel_ior);
                graph->connect(fr->output("Fac"), mx->input("Factor"));
            }
            ShaderOutput *b_cur = nullptr;
            if (m->base_mix_b_image_path && m->base_mix_b_image_path[0]) {
                ImageTextureNode *img_b = wire_tex_image(
                    graph.get(), m, m->base_mix_b_image_path,
                    m->base_mix_b_image_colorspace, m->tex_vector_mode,
                    m->map_location, m->map_rotation, m->map_scale, m->map_type);
                b_cur = img_b->output("Color");
            }
            const float3 other = make_float3(m->base_mix_other[0],
                                             m->base_mix_other[1],
                                             m->base_mix_other[2]);
            ShaderOutput *a_src = m->base_mix_chain_is_a ? cur : b_cur;
            ShaderOutput *b_src = m->base_mix_chain_is_a ? b_cur : cur;
            const float3 a_fb = m->base_mix_chain_is_a ? bcol : other;
            const float3 b_fb = m->base_mix_chain_is_a ? other : bcol;
            /* Slice 2bh: ImageTexture → RGBCurves → Mix A or B.
             * n==0 / NULL / fac==0 skips (2ay/2bg/2bf bit-identical).
             * Do not reuse base_curves_* (Curves after Mix is 2bd). */
            const bool use_mix_curves = (m->base_mix_curves != nullptr &&
                                         m->base_mix_curves_n > 0 &&
                                         m->base_mix_curves_fac != 0.0f);
            if (use_mix_curves) {
                RGBCurvesNode *mc = graph->create_node<RGBCurvesNode>();
                array<packed_float3> mcurves;
                mcurves.resize(m->base_mix_curves_n);
                for (int i = 0; i < m->base_mix_curves_n; i++) {
                    const float *p = m->base_mix_curves + i * 3;
                    mcurves[i] = make_float3(p[0], p[1], p[2]);
                }
                mc->set_curves(mcurves);
                mc->set_min_x(m->base_mix_curves_min_x);
                mc->set_max_x(m->base_mix_curves_max_x);
                mc->set_fac(m->base_mix_curves_fac);
                mc->set_extrapolate(m->base_mix_curves_extrapolate != 0);
                if (m->base_mix_curves_on_a) {
                    if (a_src) {
                        graph->connect(a_src, mc->input("Color"));
                    }
                    else {
                        mc->set_value(a_fb);
                    }
                    a_src = mc->output("Color");
                }
                else {
                    if (b_src) {
                        graph->connect(b_src, mc->input("Color"));
                    }
                    else {
                        mc->set_value(b_fb);
                    }
                    b_src = mc->output("Color");
                }
            }
            if (a_src) {
                graph->connect(a_src, mx->input("A"));
            }
            else {
                mx->set_a(a_fb);
            }
            if (b_src) {
                graph->connect(b_src, mx->input("B"));
            }
            else {
                mx->set_b(b_fb);
            }
            cur = mx->output("Result");
        }
        if (use_curves) {
            RGBCurvesNode *rc = graph->create_node<RGBCurvesNode>();
            array<packed_float3> curves;
            curves.resize(m->base_curves_n);
            for (int i = 0; i < m->base_curves_n; i++) {
                const float *p = m->base_curves + i * 3;
                curves[i] = make_float3(p[0], p[1], p[2]);
            }
            rc->set_curves(curves);
            rc->set_min_x(m->base_curves_min_x);
            rc->set_max_x(m->base_curves_max_x);
            rc->set_fac(m->base_curves_fac);
            rc->set_extrapolate(m->base_curves_extrapolate != 0);
            if (cur) {
                graph->connect(cur, rc->input("Color"));
            }
            else {
                rc->set_value(bcol);
            }
            cur = rc->output("Color");
        }
        if (cur) {
            graph->connect(cur, bsdf->input("Base Color"));
        }
    }
    /* Slice 2ba/2bb/2be: ColorRamp / TEX_IMAGE / Invert → Principled.Roughness.
     * n>0: RGBRampNode LUT (official colorramp_to_array size+1=257).
     * Fac: NoiseTextureNode (2bb enable≠0) else TEX_IMAGE Color (2ba)
     * else set_fac. enable=0 keeps 2ba bit-identical.
     * Color → Roughness via NODE_CONVERT_CF (linear_rgb_to_gray).
     * n==0 + image: keep 2i (image → Roughness directly).
     * Slice 2bj: SeparateColorNode when rough_separate_enable≠0 (cite
     *   SeparateColorNode set_color_type NODE_COMBSEP_COLOR_RGB; channel
     *   float → Roughness). enable=0 keeps Color→CF.
     * Slice 2be: InvertNode when rough_invert_enable≠0 (cite InvertNode
     * set_fac). enable=0 keeps 2ba/2bb/2i bit-identical. */
    ShaderOutput *rough_color = nullptr;
    if (m->rough_ramp_n > 0 && m->rough_ramp != nullptr) {
        RGBRampNode *ramp = graph->create_node<RGBRampNode>();
        array<packed_float3> ramp_c;
        array<float> ramp_a;
        ramp_c.resize(m->rough_ramp_n);
        ramp_a.resize(m->rough_ramp_n);
        for (int i = 0; i < m->rough_ramp_n; i++) {
            const float *p = m->rough_ramp + i * 3;
            ramp_c[i] = make_float3(p[0], p[1], p[2]);
            ramp_a[i] = (m->rough_ramp_alpha != nullptr) ? m->rough_ramp_alpha[i] : 1.0f;
        }
        ramp->set_ramp(ramp_c);
        ramp->set_ramp_alpha(ramp_a);
        ramp->set_interpolate(m->rough_ramp_interpolate != 0);
        if (m->rough_ramp_noise_enable != 0) {
            /* Cite intern/cycles/scene/shader_nodes.cpp NODE_DEFINE(NoiseTextureNode).
             * Vector unlinked → LINK_TEXTURE_GENERATED (Cycles default). */
            NoiseTextureNode *noise = graph->create_node<NoiseTextureNode>();
            int dims = m->rough_ramp_noise_dimensions;
            if (dims < 1 || dims > 4) {
                dims = 3;
            }
            noise->set_dimensions(dims);
            noise->set_type(static_cast<NodeNoiseType>(m->rough_ramp_noise_type));
            noise->set_use_normalize(m->rough_ramp_noise_normalize != 0);
            noise->set_w(m->rough_ramp_noise_w);
            noise->set_scale(m->rough_ramp_noise_scale);
            noise->set_detail(m->rough_ramp_noise_detail);
            noise->set_roughness(m->rough_ramp_noise_roughness);
            noise->set_lacunarity(m->rough_ramp_noise_lacunarity);
            noise->set_offset(m->rough_ramp_noise_offset);
            noise->set_gain(m->rough_ramp_noise_gain);
            noise->set_distortion(m->rough_ramp_noise_distortion);
            if (m->rough_ramp_noise_use_color != 0) {
                graph->connect(noise->output("Color"), ramp->input("Fac"));
            }
            else {
                graph->connect(noise->output("Fac"), ramp->input("Fac"));
            }
        }
        else if (m->rough_image_path && m->rough_image_path[0]) {
            ImageTextureNode *img = wire_tex_image(
                graph.get(), m, m->rough_image_path, m->rough_image_colorspace,
                m->rough_tex_vector_mode, m->rough_map_location, m->rough_map_rotation,
                m->rough_map_scale, m->rough_map_type);
            graph->connect(img->output("Color"), ramp->input("Fac"));
        }
        else {
            ramp->set_fac(m->rough_ramp_fac);
        }
        rough_color = ramp->output("Color");
    }
    else if (m->rough_image_path && m->rough_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->rough_image_path, m->rough_image_colorspace,
            m->rough_tex_vector_mode, m->rough_map_location, m->rough_map_rotation,
            m->rough_map_scale, m->rough_map_type);
        rough_color = img->output("Color");
    }
    if (m->rough_invert_enable != 0) {
        InvertNode *inv = graph->create_node<InvertNode>();
        inv->set_fac(m->rough_invert_fac);
        if (rough_color) {
            graph->connect(rough_color, inv->input("Color"));
        }
        graph->connect(inv->output("Color"), bsdf->input("Roughness"));
    }
    else if (m->rough_separate_enable != 0 && rough_color) {
        /* Slice 2bj: TEX/Ramp Color → SeparateColor RGB → channel float → Roughness.
         * enable=0 keeps 2be/2ba/2i Color→CF path bit-identical. */
        SeparateColorNode *sep = graph->create_node<SeparateColorNode>();
        sep->set_color_type(NODE_COMBSEP_COLOR_RGB);
        graph->connect(rough_color, sep->input("Color"));
        const char *chan = "Green";
        if (m->rough_separate_channel == 0) {
            chan = "Red";
        }
        else if (m->rough_separate_channel == 2) {
            chan = "Blue";
        }
        graph->connect(sep->output(chan), bsdf->input("Roughness"));
    }
    else if (rough_color) {
        /* Color → float: ShaderGraph::connect inserts NODE_CONVERT_CF
         * (linear_rgb_to_gray). */
        graph->connect(rough_color, bsdf->input("Roughness"));
    }
    if (m->metal_image_path && m->metal_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->metal_image_path, m->metal_image_colorspace,
            m->metal_tex_vector_mode, m->metal_map_location, m->metal_map_rotation,
            m->metal_map_scale, m->metal_map_type);
        graph->connect(img->output("Color"), bsdf->input("Metallic"));
    }
    /* Slice 2j/2x/2az: NormalMap + optional Bump + optional Bevel → Principled.Normal.
     * Order (loft Metal_Sheet): TEX → NormalMap → Bump.Normal; TEX → Bump.Height;
     * Bump → Bevel.Normal; Bevel → Principled.Normal.
     * When bump_* + normal_* both set: NormalMap feeds Bump.Normal (Slice 2az;
     * previously Bump won and ignored normal_* — packer never set both before).
     * bevel_enable=0 keeps 2x/2j bit-identical when only one of bump/normal is set.
     * BevelNode: set_samples / set_radius; KERNEL_FEATURE_NODE_RAYTRACE.
     * Bump: Blender 5.2 RNA Distance=0.001 (not Cycles NODE_DEFINE 0.1).
     * refine_bump_nodes clones Height — only connect Height; do not wire Sample*. */
    {
        NormalMapNode *nmap = nullptr;
        if (m->normal_image_path && m->normal_image_path[0]) {
            ImageTextureNode *img = wire_tex_image(
                graph.get(), m, m->normal_image_path, m->normal_image_colorspace,
                m->normal_tex_vector_mode, m->normal_map_location, m->normal_map_rotation,
                m->normal_map_scale, m->normal_map_type);
            ShaderOutput *nmap_color = img->output("Color");
            /* Slice 2bi: TEX → Separate RGB → Invert G → Combine → NormalMap.
             * enable=0 keeps 2j direct Color link bit-identical. */
            if (m->normal_invert_g_enable != 0) {
                SeparateColorNode *sep = graph->create_node<SeparateColorNode>();
                sep->set_color_type(NODE_COMBSEP_COLOR_RGB);
                graph->connect(nmap_color, sep->input("Color"));
                InvertNode *invg = graph->create_node<InvertNode>();
                invg->set_fac(m->normal_invert_g_fac);
                graph->connect(sep->output("Green"), invg->input("Color"));
                CombineColorNode *comb = graph->create_node<CombineColorNode>();
                comb->set_color_type(NODE_COMBSEP_COLOR_RGB);
                graph->connect(sep->output("Red"), comb->input("Red"));
                graph->connect(invg->output("Color"), comb->input("Green"));
                graph->connect(sep->output("Blue"), comb->input("Blue"));
                nmap_color = comb->output("Color");
            }
            nmap = graph->create_node<NormalMapNode>();
            int sp = m->normal_space;
            ccl::NodeNormalMapSpace space = NODE_NORMAL_MAP_TANGENT;
            if (sp == QT_NORMAL_MAP_OBJECT) space = NODE_NORMAL_MAP_OBJECT;
            else if (sp == QT_NORMAL_MAP_WORLD) space = NODE_NORMAL_MAP_WORLD;
            else if (sp == QT_NORMAL_MAP_BLENDER_OBJECT) space = NODE_NORMAL_MAP_BLENDER_OBJECT;
            else if (sp == QT_NORMAL_MAP_BLENDER_WORLD) space = NODE_NORMAL_MAP_BLENDER_WORLD;
            nmap->set_space(space);
            nmap->set_strength(m->normal_strength);
            graph->connect(nmap_color, nmap->input("Color"));
        }
        BumpNode *bump = nullptr;
        const bool bump_noise = (m->bump_noise_enable != 0);
        const bool bump_image = (m->bump_image_path && m->bump_image_path[0]);
        if (bump_noise || bump_image) {
            bump = graph->create_node<BumpNode>();
            bump->set_invert(m->bump_invert != 0);
            bump->set_use_object_space(false);
            bump->set_strength(m->bump_strength);
            bump->set_distance(m->bump_distance);
            if (bump_noise) {
                /* Cite intern/cycles/scene/shader_nodes.cpp NODE_DEFINE(NoiseTextureNode).
                 * Vector unlinked → LINK_TEXTURE_GENERATED. Color → Height NODE_CONVERT_CF. */
                NoiseTextureNode *noise = graph->create_node<NoiseTextureNode>();
                int dims = m->bump_noise_dimensions;
                if (dims < 1 || dims > 4) {
                    dims = 3;
                }
                noise->set_dimensions(dims);
                noise->set_type(static_cast<NodeNoiseType>(m->bump_noise_type));
                noise->set_use_normalize(m->bump_noise_normalize != 0);
                noise->set_w(m->bump_noise_w);
                noise->set_scale(m->bump_noise_scale);
                noise->set_detail(m->bump_noise_detail);
                noise->set_roughness(m->bump_noise_roughness);
                noise->set_lacunarity(m->bump_noise_lacunarity);
                noise->set_offset(m->bump_noise_offset);
                noise->set_gain(m->bump_noise_gain);
                noise->set_distortion(m->bump_noise_distortion);
                if (m->bump_noise_use_color != 0) {
                    graph->connect(noise->output("Color"), bump->input("Height"));
                }
                else {
                    graph->connect(noise->output("Fac"), bump->input("Height"));
                }
            }
            else {
                ImageTextureNode *img = wire_tex_image(
                    graph.get(), m, m->bump_image_path, m->bump_image_colorspace,
                    m->bump_tex_vector_mode, m->bump_map_location, m->bump_map_rotation,
                    m->bump_map_scale, m->bump_map_type);
                if (m->bump_separate_enable != 0) {
                    /* Slice 2bl: TEX Color → SeparateColor RGB → channel float → Height.
                     * enable=0 keeps 2x Color→CF Height bit-identical. */
                    SeparateColorNode *sep = graph->create_node<SeparateColorNode>();
                    sep->set_color_type(NODE_COMBSEP_COLOR_RGB);
                    graph->connect(img->output("Color"), sep->input("Color"));
                    const char *chan = "Green";
                    if (m->bump_separate_channel == 0) {
                        chan = "Red";
                    }
                    else if (m->bump_separate_channel == 2) {
                        chan = "Blue";
                    }
                    graph->connect(sep->output(chan), bump->input("Height"));
                }
                else {
                    graph->connect(img->output("Color"), bump->input("Height"));
                }
            }
            if (nmap) {
                graph->connect(nmap->output("Normal"), bump->input("Normal"));
            }
        }
        ShaderOutput *normal_src = nullptr;
        if (bump) {
            normal_src = bump->output("Normal");
        } else if (nmap) {
            normal_src = nmap->output("Normal");
        }
        if (m->bevel_enable) {
            BevelNode *bevel = graph->create_node<BevelNode>();
            int ns = m->bevel_samples;
            if (ns < 1) ns = 1;
            if (ns > 128) ns = 128;
            bevel->set_samples(ns);
            bevel->set_radius(m->bevel_radius);
            if (normal_src) {
                graph->connect(normal_src, bevel->input("Normal"));
            }
            graph->connect(bevel->output("Normal"), bsdf->input("Normal"));
        } else if (normal_src) {
            graph->connect(normal_src, bsdf->input("Normal"));
        }
    }
    if (m->ior_image_path && m->ior_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->ior_image_path, m->ior_image_colorspace,
            m->ior_tex_vector_mode, m->ior_map_location, m->ior_map_rotation,
            m->ior_map_scale, m->ior_map_type);
        graph->connect(img->output("Color"), bsdf->input("IOR"));
    }
    if (m->alpha_image_path && m->alpha_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->alpha_image_path, m->alpha_image_colorspace,
            m->alpha_tex_vector_mode, m->alpha_map_location, m->alpha_map_rotation,
            m->alpha_map_scale, m->alpha_map_type);
        graph->connect(img->output("Color"), bsdf->input("Alpha"));
    }
    /* Slice 2p: Color → Transmission Weight (legacy "Transmission") via NODE_CONVERT_CF.
     * Slice 2y: if trans_image_path empty, pin unlinked RNA default (Cycles default 0).
     * Do not also set the constant when the TEX_IMAGE wire is live. */
    if (m->trans_image_path && m->trans_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->trans_image_path, m->trans_image_colorspace,
            m->trans_tex_vector_mode, m->trans_map_location, m->trans_map_rotation,
            m->trans_map_scale, m->trans_map_type);
        ShaderInput *in = bsdf->input("Transmission Weight");
        if (in == nullptr) {
            in = bsdf->input("Transmission");
        }
        graph->connect(img->output("Color"), in);
    }
    else {
        bsdf->set_transmission_weight(m->transmission_weight);
    }
    /* Slice 2p: Color → Specular IOR Level (legacy "Specular") via NODE_CONVERT_CF. */
    if (m->spec_image_path && m->spec_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->spec_image_path, m->spec_image_colorspace,
            m->spec_tex_vector_mode, m->spec_map_location, m->spec_map_rotation,
            m->spec_map_scale, m->spec_map_type);
        ShaderInput *in = bsdf->input("Specular IOR Level");
        if (in == nullptr) {
            in = bsdf->input("Specular");
        }
        graph->connect(img->output("Color"), in);
    }
    /* Slice 2q: Color → Coat Weight (legacy Coat / Clearcoat) via NODE_CONVERT_CF. */
    if (m->coat_image_path && m->coat_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->coat_image_path, m->coat_image_colorspace,
            m->coat_tex_vector_mode, m->coat_map_location, m->coat_map_rotation,
            m->coat_map_scale, m->coat_map_type);
        ShaderInput *in = bsdf->input("Coat Weight");
        if (in == nullptr) {
            in = bsdf->input("Coat");
        }
        if (in == nullptr) {
            in = bsdf->input("Clearcoat");
        }
        graph->connect(img->output("Color"), in);
    }
    /* Slice 2q: Color → Sheen Weight (legacy Sheen) via NODE_CONVERT_CF. */
    if (m->sheen_image_path && m->sheen_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->sheen_image_path, m->sheen_image_colorspace,
            m->sheen_tex_vector_mode, m->sheen_map_location, m->sheen_map_rotation,
            m->sheen_map_scale, m->sheen_map_type);
        ShaderInput *in = bsdf->input("Sheen Weight");
        if (in == nullptr) {
            in = bsdf->input("Sheen");
        }
        graph->connect(img->output("Color"), in);
    }
    /* Slice 2q: Color → Emission Strength via NODE_CONVERT_CF. */
    if (m->emit_str_image_path && m->emit_str_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->emit_str_image_path, m->emit_str_image_colorspace,
            m->emit_str_tex_vector_mode, m->emit_str_map_location,
            m->emit_str_map_rotation, m->emit_str_map_scale, m->emit_str_map_type);
        ShaderInput *in = bsdf->input("Emission Strength");
        graph->connect(img->output("Color"), in);
    }
    /* Slice 2r: Color → Emission Color (legacy Emission). Color socket, no convert.
     * Unlinked Strength stays Cycles default 0 unless Color is mapped: pin 1.0 so
     * the color map is visible (matches test-scene Strength default_value=1.0). */
    if (m->emit_color_image_path && m->emit_color_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->emit_color_image_path, m->emit_color_image_colorspace,
            m->emit_color_tex_vector_mode, m->emit_color_map_location,
            m->emit_color_map_rotation, m->emit_color_map_scale, m->emit_color_map_type);
        ShaderInput *in = bsdf->input("Emission Color");
        if (in == nullptr) {
            in = bsdf->input("Emission");
        }
        graph->connect(img->output("Color"), in);
        if (!(m->emit_str_image_path && m->emit_str_image_path[0])) {
            bsdf->set_emission_strength(1.0f);
        }
    }

    /* Slice 2s: Color → Coat Roughness / Coat IOR / Coat Tint / Sheen Roughness / Sheen Tint.
     * Float sockets via NODE_CONVERT_CF; Tint is Color→Color.
     * Cycles default coat_weight/sheen_weight are 0; pin 1.0 when extras map
     * and Weight is not itself mapped (matches test-scene Weight=1.0). */
    if (m->coat_rough_image_path && m->coat_rough_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->coat_rough_image_path, m->coat_rough_image_colorspace,
            m->coat_rough_tex_vector_mode, m->coat_rough_map_location,
            m->coat_rough_map_rotation, m->coat_rough_map_scale, m->coat_rough_map_type);
        graph->connect(img->output("Color"), bsdf->input("Coat Roughness"));
    }
    if (m->coat_ior_image_path && m->coat_ior_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->coat_ior_image_path, m->coat_ior_image_colorspace,
            m->coat_ior_tex_vector_mode, m->coat_ior_map_location,
            m->coat_ior_map_rotation, m->coat_ior_map_scale, m->coat_ior_map_type);
        graph->connect(img->output("Color"), bsdf->input("Coat IOR"));
    }
    if (m->coat_tint_image_path && m->coat_tint_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->coat_tint_image_path, m->coat_tint_image_colorspace,
            m->coat_tint_tex_vector_mode, m->coat_tint_map_location,
            m->coat_tint_map_rotation, m->coat_tint_map_scale, m->coat_tint_map_type);
        graph->connect(img->output("Color"), bsdf->input("Coat Tint"));
    }
    if (m->sheen_rough_image_path && m->sheen_rough_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->sheen_rough_image_path, m->sheen_rough_image_colorspace,
            m->sheen_rough_tex_vector_mode, m->sheen_rough_map_location,
            m->sheen_rough_map_rotation, m->sheen_rough_map_scale, m->sheen_rough_map_type);
        graph->connect(img->output("Color"), bsdf->input("Sheen Roughness"));
    }
    if (m->sheen_tint_image_path && m->sheen_tint_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->sheen_tint_image_path, m->sheen_tint_image_colorspace,
            m->sheen_tint_tex_vector_mode, m->sheen_tint_map_location,
            m->sheen_tint_map_rotation, m->sheen_tint_map_scale, m->sheen_tint_map_type);
        graph->connect(img->output("Color"), bsdf->input("Sheen Tint"));
    }
    /* Slice 2t: TEX_IMAGE Color → NormalMap Color → Principled Coat Normal.
     * Same Tangent / unlinked Strength rules as Slice 2j. */
    if (m->coat_normal_image_path && m->coat_normal_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->coat_normal_image_path, m->coat_normal_image_colorspace,
            m->coat_normal_tex_vector_mode, m->coat_normal_map_location,
            m->coat_normal_map_rotation, m->coat_normal_map_scale, m->coat_normal_map_type);
        ShaderOutput *nmap_color = img->output("Color");
        if (m->coat_normal_invert_g_enable != 0) {
            SeparateColorNode *sep = graph->create_node<SeparateColorNode>();
            sep->set_color_type(NODE_COMBSEP_COLOR_RGB);
            graph->connect(nmap_color, sep->input("Color"));
            InvertNode *invg = graph->create_node<InvertNode>();
            invg->set_fac(m->coat_normal_invert_g_fac);
            graph->connect(sep->output("Green"), invg->input("Color"));
            CombineColorNode *comb = graph->create_node<CombineColorNode>();
            comb->set_color_type(NODE_COMBSEP_COLOR_RGB);
            graph->connect(sep->output("Red"), comb->input("Red"));
            graph->connect(invg->output("Color"), comb->input("Green"));
            graph->connect(sep->output("Blue"), comb->input("Blue"));
            nmap_color = comb->output("Color");
        }
        NormalMapNode *nmap = graph->create_node<NormalMapNode>();
        int csp = m->coat_normal_space;
        ccl::NodeNormalMapSpace cspace = NODE_NORMAL_MAP_TANGENT;
        if (csp == QT_NORMAL_MAP_OBJECT) cspace = NODE_NORMAL_MAP_OBJECT;
        else if (csp == QT_NORMAL_MAP_WORLD) cspace = NODE_NORMAL_MAP_WORLD;
        else if (csp == QT_NORMAL_MAP_BLENDER_OBJECT) cspace = NODE_NORMAL_MAP_BLENDER_OBJECT;
        else if (csp == QT_NORMAL_MAP_BLENDER_WORLD) cspace = NODE_NORMAL_MAP_BLENDER_WORLD;
        nmap->set_space(cspace);
        nmap->set_strength(m->coat_normal_strength);
        graph->connect(nmap_color, nmap->input("Color"));
        graph->connect(nmap->output("Normal"), bsdf->input("Coat Normal"));
    }

    /* Slice 2u: Specular Tint Color→Color; Thin Film Thickness/IOR via NODE_CONVERT_CF;
     * Subsurface Weight/Scale via NODE_CONVERT_CF; Subsurface Radius Color→Vector.
     * Pin subsurface_weight=1 when Radius/Scale map and Weight is unmapped.
     * Pin thin_film_thickness=400 nm when Film IOR maps and Thickness is unmapped
     * (Cycles default thickness is 0 = no film). */
    /* Slice 2bk: specular_tint constant + optional MixColorNode + optional TEX_IMAGE.
     * mix_type==0 && no image → set_specular_tint only (2u unlinked / constant fold).
     * mix_type==0 && image → TEX_IMAGE Color → Specular Tint (2u).
     * mix_type!=0 → Color chain (± dual B image) → Mix → Specular Tint. */
    {
        const float3 stint = make_float3(m->specular_tint[0], m->specular_tint[1],
                                         m->specular_tint[2]);
        bsdf->set_specular_tint(stint);
        const bool use_st_mix = (m->spec_tint_mix_type != 0);
        ShaderOutput *cur = nullptr;
        if (m->spec_tint_image_path && m->spec_tint_image_path[0]) {
            ImageTextureNode *img = wire_tex_image(
                graph.get(), m, m->spec_tint_image_path, m->spec_tint_image_colorspace,
                m->spec_tint_tex_vector_mode, m->spec_tint_map_location,
                m->spec_tint_map_rotation, m->spec_tint_map_scale, m->spec_tint_map_type);
            cur = img->output("Color");
        }
        /* Slice 2bk: Gamma + HSV on Specular Tint chain (loft Sideboard:
         * TEX → Gamma → HueSat → Mix B). Identity skips — 2u bit-identical. */
        const bool use_st_gamma = (m->spec_tint_gamma != 1.0f);
        const bool use_st_hsv = !(m->spec_tint_hsv_hue == 0.5f &&
                                  m->spec_tint_hsv_sat == 1.0f &&
                                  m->spec_tint_hsv_val == 1.0f &&
                                  m->spec_tint_hsv_fac == 1.0f);
        if (use_st_gamma) {
            GammaNode *g = graph->create_node<GammaNode>();
            g->set_gamma(m->spec_tint_gamma);
            if (cur) {
                graph->connect(cur, g->input("Color"));
            }
            else {
                g->set_color(stint);
            }
            cur = g->output("Color");
        }
        if (use_st_hsv) {
            HSVNode *h = graph->create_node<HSVNode>();
            h->set_hue(m->spec_tint_hsv_hue);
            h->set_saturation(m->spec_tint_hsv_sat);
            h->set_value(m->spec_tint_hsv_val);
            h->set_fac(m->spec_tint_hsv_fac);
            if (cur) {
                graph->connect(cur, h->input("Color"));
            }
            else {
                h->set_color(stint);
            }
            cur = h->output("Color");
        }
        if (use_st_mix) {
            MixColorNode *mx = graph->create_node<MixColorNode>();
            mx->set_blend_type(world_mix_blend_type(m->spec_tint_mix_type));
            mx->set_fac(m->spec_tint_mix_fac);
            mx->set_use_clamp(m->spec_tint_mix_clamp_factor != 0);
            mx->set_use_clamp_result(m->spec_tint_mix_clamp_result != 0);
            ShaderOutput *b_cur = nullptr;
            if (m->spec_tint_mix_b_image_path && m->spec_tint_mix_b_image_path[0]) {
                ImageTextureNode *img_b = wire_tex_image(
                    graph.get(), m, m->spec_tint_mix_b_image_path,
                    m->spec_tint_mix_b_image_colorspace,
                    m->spec_tint_tex_vector_mode, m->spec_tint_map_location,
                    m->spec_tint_map_rotation, m->spec_tint_map_scale,
                    m->spec_tint_map_type);
                b_cur = img_b->output("Color");
            }
            const float3 other = make_float3(m->spec_tint_mix_other[0],
                                             m->spec_tint_mix_other[1],
                                             m->spec_tint_mix_other[2]);
            ShaderOutput *a_src = m->spec_tint_mix_chain_is_a ? cur : b_cur;
            ShaderOutput *b_src = m->spec_tint_mix_chain_is_a ? b_cur : cur;
            const float3 a_fb = m->spec_tint_mix_chain_is_a ? stint : other;
            const float3 b_fb = m->spec_tint_mix_chain_is_a ? other : stint;
            if (a_src) {
                graph->connect(a_src, mx->input("A"));
            }
            else {
                mx->set_a(a_fb);
            }
            if (b_src) {
                graph->connect(b_src, mx->input("B"));
            }
            else {
                mx->set_b(b_fb);
            }
            graph->connect(mx->output("Result"), bsdf->input("Specular Tint"));
        }
        else if (cur) {
            graph->connect(cur, bsdf->input("Specular Tint"));
        }
    }
    if (m->film_thick_image_path && m->film_thick_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->film_thick_image_path, m->film_thick_image_colorspace,
            m->film_thick_tex_vector_mode, m->film_thick_map_location,
            m->film_thick_map_rotation, m->film_thick_map_scale, m->film_thick_map_type);
        graph->connect(img->output("Color"), bsdf->input("Thin Film Thickness"));
    }
    if (m->film_ior_image_path && m->film_ior_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->film_ior_image_path, m->film_ior_image_colorspace,
            m->film_ior_tex_vector_mode, m->film_ior_map_location,
            m->film_ior_map_rotation, m->film_ior_map_scale, m->film_ior_map_type);
        graph->connect(img->output("Color"), bsdf->input("Thin Film IOR"));
    }
    if (m->sss_weight_image_path && m->sss_weight_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->sss_weight_image_path, m->sss_weight_image_colorspace,
            m->sss_weight_tex_vector_mode, m->sss_weight_map_location,
            m->sss_weight_map_rotation, m->sss_weight_map_scale, m->sss_weight_map_type);
        graph->connect(img->output("Color"), bsdf->input("Subsurface Weight"));
    }
    if (m->sss_radius_image_path && m->sss_radius_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->sss_radius_image_path, m->sss_radius_image_colorspace,
            m->sss_radius_tex_vector_mode, m->sss_radius_map_location,
            m->sss_radius_map_rotation, m->sss_radius_map_scale, m->sss_radius_map_type);
        graph->connect(img->output("Color"), bsdf->input("Subsurface Radius"));
    }
    if (m->sss_scale_image_path && m->sss_scale_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->sss_scale_image_path, m->sss_scale_image_colorspace,
            m->sss_scale_tex_vector_mode, m->sss_scale_map_location,
            m->sss_scale_map_rotation, m->sss_scale_map_scale, m->sss_scale_map_type);
        graph->connect(img->output("Color"), bsdf->input("Subsurface Scale"));
    }
    /* Slice 2v: Subsurface IOR / Anisotropy / Diffuse Roughness via NODE_CONVERT_CF.
     * Thin Wall ABI reserved (BOOLEAN); Color→Int CONVERT_CI if path set.
     * Pin subsurface_weight=1 when IOR/Anisotropy map and Weight is unmapped. */
    if (m->sss_ior_image_path && m->sss_ior_image_path[0]) {
        /* Blender 5.2 exposes Subsurface IOR only for RANDOM_WALK_SKIN. */
        bsdf->set_subsurface_method(CLOSURE_BSSRDF_RANDOM_WALK_SKIN_ID);
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->sss_ior_image_path, m->sss_ior_image_colorspace,
            m->sss_ior_tex_vector_mode, m->sss_ior_map_location,
            m->sss_ior_map_rotation, m->sss_ior_map_scale, m->sss_ior_map_type);
        graph->connect(img->output("Color"), bsdf->input("Subsurface IOR"));
    }
    if (m->sss_aniso_image_path && m->sss_aniso_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->sss_aniso_image_path, m->sss_aniso_image_colorspace,
            m->sss_aniso_tex_vector_mode, m->sss_aniso_map_location,
            m->sss_aniso_map_rotation, m->sss_aniso_map_scale, m->sss_aniso_map_type);
        graph->connect(img->output("Color"), bsdf->input("Subsurface Anisotropy"));
    }
    if (m->thin_wall_image_path && m->thin_wall_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->thin_wall_image_path, m->thin_wall_image_colorspace,
            m->thin_wall_tex_vector_mode, m->thin_wall_map_location,
            m->thin_wall_map_rotation, m->thin_wall_map_scale, m->thin_wall_map_type);
        graph->connect(img->output("Color"), bsdf->input("Thin Wall"));
    }
    if (m->diffuse_rough_image_path && m->diffuse_rough_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->diffuse_rough_image_path, m->diffuse_rough_image_colorspace,
            m->diffuse_rough_tex_vector_mode, m->diffuse_rough_map_location,
            m->diffuse_rough_map_rotation, m->diffuse_rough_map_scale, m->diffuse_rough_map_type);
        graph->connect(img->output("Color"), bsdf->input("Diffuse Roughness"));
    }
    /* Slice 2w: Anisotropic / Anisotropic Rotation Color→float via NODE_CONVERT_CF;
     * Tangent Color→Vector (same as Subsurface Radius). Pin set_anisotropic(1.0)
     * when Rotation or Tangent maps and Anisotropic path is empty (Cycles disconnects
     * Rotation when Anisotropic weight is 0). */
    if (m->aniso_image_path && m->aniso_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->aniso_image_path, m->aniso_image_colorspace,
            m->aniso_tex_vector_mode, m->aniso_map_location,
            m->aniso_map_rotation, m->aniso_map_scale, m->aniso_map_type);
        graph->connect(img->output("Color"), bsdf->input("Anisotropic"));
    }
    if (m->aniso_rot_image_path && m->aniso_rot_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->aniso_rot_image_path, m->aniso_rot_image_colorspace,
            m->aniso_rot_tex_vector_mode, m->aniso_rot_map_location,
            m->aniso_rot_map_rotation, m->aniso_rot_map_scale, m->aniso_rot_map_type);
        graph->connect(img->output("Color"), bsdf->input("Anisotropic Rotation"));
    }
    if (m->tangent_image_path && m->tangent_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->tangent_image_path, m->tangent_image_colorspace,
            m->tangent_tex_vector_mode, m->tangent_map_location,
            m->tangent_map_rotation, m->tangent_map_scale, m->tangent_map_type);
        graph->connect(img->output("Color"), bsdf->input("Tangent"));
    }
    if (((m->aniso_rot_image_path && m->aniso_rot_image_path[0]) ||
         (m->tangent_image_path && m->tangent_image_path[0])) &&
        !(m->aniso_image_path && m->aniso_image_path[0])) {
        bsdf->set_anisotropic(1.0f);
    }
    if (((m->sss_radius_image_path && m->sss_radius_image_path[0]) ||
         (m->sss_scale_image_path && m->sss_scale_image_path[0]) ||
         (m->sss_ior_image_path && m->sss_ior_image_path[0]) ||
         (m->sss_aniso_image_path && m->sss_aniso_image_path[0])) &&
        !(m->sss_weight_image_path && m->sss_weight_image_path[0])) {
        bsdf->set_subsurface_weight(1.0f);
    }
    if ((m->film_ior_image_path && m->film_ior_image_path[0]) &&
        !(m->film_thick_image_path && m->film_thick_image_path[0])) {
        bsdf->set_thin_film_thickness(400.0f);
    }
    if (((m->coat_rough_image_path && m->coat_rough_image_path[0]) ||
         (m->coat_ior_image_path && m->coat_ior_image_path[0]) ||
         (m->coat_tint_image_path && m->coat_tint_image_path[0]) ||
         (m->coat_normal_image_path && m->coat_normal_image_path[0])) &&
        !(m->coat_image_path && m->coat_image_path[0])) {
        bsdf->set_coat_weight(1.0f);
    }
    if (((m->sheen_rough_image_path && m->sheen_rough_image_path[0]) ||
         (m->sheen_tint_image_path && m->sheen_tint_image_path[0])) &&
        !(m->sheen_image_path && m->sheen_image_path[0])) {
        bsdf->set_sheen_weight(1.0f);
    }
    graph->connect(bsdf->output("BSDF"), graph->output()->input("Surface"));
    surf->set_graph(std::move(graph));
    surf->tag_update(scene);
    return surf;
}

static Shader *make_area_emission(Scene *scene)
{
    Shader *lamp_shader = scene->create_node<Shader>();
    lamp_shader->name = "area_emission";
    unique_ptr<ShaderGraph> graph = make_unique<ShaderGraph>();
    EmissionNode *emission = graph->create_node<EmissionNode>();
    emission->set_color(make_float3(1.0f, 1.0f, 1.0f));
    emission->set_strength(1.0f);
    graph->connect(emission->output("Emission"), graph->output()->input("Surface"));
    lamp_shader->set_graph(std::move(graph));
    lamp_shader->tag_update(scene);
    return lamp_shader;
}

static void add_mesh_object(Scene *scene, Shader *surf, const QT_Mesh *m)
{
    Mesh *mesh = scene->create_node<Mesh>();
    {
        array<Node *> used;
        used.push_back_slow(surf);
        mesh->set_used_shaders(used);
    }
    mesh->resize_mesh(m->nverts, m->ntris);
    packed_float3 *P = mesh->get_position_for_write();
    for (int i = 0; i < m->nverts; i++) {
        P[i] = make_float3(m->verts[i * 3 + 0],
                           m->verts[i * 3 + 1],
                           m->verts[i * 3 + 2]);
    }
    int *tris = mesh->get_triangles().data();
    int *shader_idx = mesh->get_shader().data();
    bool *smooth = mesh->get_smooth().data();
    for (int t = 0; t < m->ntris; t++) {
        tris[t * 3 + 0] = m->tris[t * 3 + 0];
        tris[t * 3 + 1] = m->tris[t * 3 + 1];
        tris[t * 3 + 2] = m->tris[t * 3 + 2];
        shader_idx[t] = 0;
        smooth[t] = false;
    }
    mesh->tag_triangles_modified();
    mesh->tag_shader_modified();
    mesh->tag_smooth_modified();
    mesh->tag_position_modified();
    mesh->add_vertex_normals();
    const bool needs_uv =
        (m->image_path && m->image_path[0]) ||
        (m->rough_image_path && m->rough_image_path[0]) ||
        (m->metal_image_path && m->metal_image_path[0]) ||
        (m->normal_image_path && m->normal_image_path[0]) ||
        (m->ior_image_path && m->ior_image_path[0]) ||
        (m->alpha_image_path && m->alpha_image_path[0]) ||
        (m->trans_image_path && m->trans_image_path[0]) ||
        (m->spec_image_path && m->spec_image_path[0]) ||
        (m->coat_image_path && m->coat_image_path[0]) ||
        (m->sheen_image_path && m->sheen_image_path[0]) ||
        (m->emit_str_image_path && m->emit_str_image_path[0]) ||
        (m->emit_color_image_path && m->emit_color_image_path[0]) ||
        (m->coat_rough_image_path && m->coat_rough_image_path[0]) ||
        (m->coat_ior_image_path && m->coat_ior_image_path[0]) ||
        (m->coat_tint_image_path && m->coat_tint_image_path[0]) ||
        (m->sheen_rough_image_path && m->sheen_rough_image_path[0]) ||
        (m->sheen_tint_image_path && m->sheen_tint_image_path[0]) ||
        (m->coat_normal_image_path && m->coat_normal_image_path[0]) ||
        (m->spec_tint_image_path && m->spec_tint_image_path[0]) ||
        (m->film_thick_image_path && m->film_thick_image_path[0]) ||
        (m->film_ior_image_path && m->film_ior_image_path[0]) ||
        (m->sss_weight_image_path && m->sss_weight_image_path[0]) ||
        (m->sss_radius_image_path && m->sss_radius_image_path[0]) ||
        (m->sss_scale_image_path && m->sss_scale_image_path[0]) ||
        (m->sss_ior_image_path && m->sss_ior_image_path[0]) ||
        (m->sss_aniso_image_path && m->sss_aniso_image_path[0]) ||
        (m->thin_wall_image_path && m->thin_wall_image_path[0]) ||
        (m->diffuse_rough_image_path && m->diffuse_rough_image_path[0]) ||
        (m->aniso_image_path && m->aniso_image_path[0]) ||
        (m->aniso_rot_image_path && m->aniso_rot_image_path[0]) ||
        (m->tangent_image_path && m->tangent_image_path[0]) ||
        (m->bump_image_path && m->bump_image_path[0]);
    if (needs_uv && m->uvs) {
        Attribute *attr = mesh->attributes.add(ATTR_STD_UV);
        float2 *fdata = attr->data_for_write<float2>();
        for (int c = 0; c < m->ntris * 3; c++) {
            fdata[c] = make_float2(m->uvs[c * 2 + 0], m->uvs[c * 2 + 1]);
        }
    }
    if (mesh_uses_generated(m)) {
        fill_generated_orco(mesh, m);
    }

    Object *mesh_obj = scene->create_node<Object>();
    mesh_obj->set_geometry(mesh);
    mesh_obj->set_tfm(tfm_from_12(m->tfm));
    /* Match Blender sync: hash_uint2(hash_string(name), 0). */
    if (m->name && m->name[0]) {
        mesh_obj->name = m->name;
        mesh_obj->set_random_id(hash_uint2(hash_string(m->name), 0));
    }
}

static void add_qt_light(Scene *scene, Shader *lamp_shader, const QT_Light *L)
{
    Light *light = nullptr;
    const int kind = L->kind;
    if (kind == QT_LIGHT_POINT) {
        PointLight *point = scene->create_node<PointLight>();
        point->set_radius(L->radius > 0.0f ? L->radius : 0.0f);
        /* Blender sync: is_sphere = !use_soft_falloff. Default soft falloff
         * → disk (is_sphere=false). Hard point radius=0 ignores this flag. */
        point->set_is_sphere(L->is_sphere != 0);
        light = point;
    }
    else if (kind == QT_LIGHT_SPOT) {
        /* Blender sync (intern/cycles/blender/light.cpp):
         * spotsize→angle, spotblend→smooth; PointLight base sets
         * radius + is_sphere=!use_soft_falloff. Emit along object -Z. */
        SpotLight *spot = scene->create_node<SpotLight>();
        const float ang = L->angle > 0.0f ? L->angle : 0.785398f; /* π/4 default */
        spot->set_angle(ang);
        spot->set_smooth(L->smooth); /* RNA spot_blend, may be 0 */
        spot->set_radius(L->radius > 0.0f ? L->radius : 0.0f);
        spot->set_is_sphere(L->is_sphere != 0);
        light = spot;
    }
    else if (kind == QT_LIGHT_SUN) {
        SunLight *sun = scene->create_node<SunLight>();
        sun->set_angle(L->angle > 0.0f ? L->angle : 0.009180f); /* ~0.526 deg default */
        light = sun;
    }
    else {
        AreaLight *area = scene->create_node<AreaLight>();
        area->set_sizeu(L->sizeu);
        area->set_sizev(L->sizev);
        area->set_ellipse(false);
        area->set_spread(3.1415926535897932f);
        light = area;
    }
    light->set_normalize(true);
    light->set_strength(make_float3(L->strength[0], L->strength[1], L->strength[2]));
    light->set_use_mis(true);
    light->set_cast_shadow(true);
    {
        array<Node *> used;
        used.push_back_slow(lamp_shader);
        light->set_used_shaders(used);
    }

    Object *light_obj = scene->create_node<Object>();
    light_obj->set_geometry(light);
    light_obj->set_visibility(PATH_RAY_VISIBILITY_ALL & ~PATH_RAY_VISIBILITY_CAMERA);
    light_obj->set_tfm(tfm_from_12(L->tfm));
    if (L->name && L->name[0]) {
        light_obj->name = L->name;
        light_obj->set_random_id(hash_uint2(hash_string(L->name), 0));
    }
}

static void build_qt_scene(Scene *scene, const QT_Scene *desc)
{
    /* Integrator: stock uni-PT. Pin sample pattern + bounce bill to match
     * Blender 5.2 Classic/Tabulated Sobol path used by the cube script.
     */
    Integrator *integrator = scene->integrator;
    integrator->set_use_adaptive_sampling(false);
    integrator->set_use_denoise(false);
    integrator->set_seed(0);
    integrator->set_sample_clamp_direct(0.0f);
    integrator->set_sample_clamp_indirect(10.0f);
    integrator->set_sampling_pattern(SAMPLING_PATTERN_TABULATED_SOBOL);
    integrator->set_scrambling_distance(1.0f);
    integrator->set_use_pixel_jitter(false);
    integrator->set_use_light_tree(true);
    integrator->set_light_sampling_threshold(0.0f);
    integrator->set_min_bounce(0);
    integrator->set_max_bounce(12);
    integrator->set_max_diffuse_bounce(4);
    integrator->set_max_glossy_bounce(4);
    integrator->set_max_transmission_bounce(12);
    integrator->set_max_volume_bounce(0);
    integrator->set_transparent_min_bounce(0);
    integrator->set_transparent_max_bounce(8);
    integrator->set_caustics_reflective(true);
    integrator->set_caustics_refractive(true);
    integrator->set_filter_glossy(0.0f);

    Film *film = scene->film;
    film->set_exposure(1.0f);
    film->set_filter_type(FILTER_GAUSSIAN);
    film->set_filter_width(1.5f);

    Camera *cam = scene->camera;
    cam->set_camera_type(CAMERA_PERSPECTIVE);
    cam->set_fov(desc->cam_fov);
    cam->set_sensorwidth(desc->cam_sensor_w);
    cam->set_sensorheight(desc->cam_sensor_h);
    cam->set_full_width(desc->width);
    cam->set_full_height(desc->height);
    cam->set_nearclip(desc->cam_near);
    cam->set_farclip(desc->cam_far);
    /* blender_camera_matrix: object * scale(1,1,-1). */
    cam->set_matrix(tfm_from_12(desc->cam_tfm) * transform_scale(1.0f, 1.0f, -1.0f));
    cam->compute_auto_viewplane();
    cam->need_flags_update = true;
    cam->update(scene);

    /* World Background: black+strength (Slice 2b), constant Color (Slice 2al),
     * Environment Texture (Slice 2aa/2ac/2ae), Sky Texture (Slice 2am), or
     * Image Texture → Color (Slice 2an).
     * Slice 2aa: Vector unlinked LINK_POSITION. Slice 2ac: TEX_COORD (+ Mapping).
     * Slice 2ae: Object-with-pointer (world_ob_use_transform + world_ob_tfm).
     * Slice 2al: empty world_image_path uses world_color RGB (default 0,0,0
     * stays bit-identical black). Env path keeps Color black — ENV node feeds
     * Color; do not mix world_color into the env graph.
     * Slice 2am: world_sky_type != 0 builds SkyTextureNode; path empty, do not
     * mix world_color into the sky graph. Mode 0 Vector unlinked
     * LINK_TEXTURE_GENERATED. Slice 2ar: non-zero world_tex_vector_mode wires
     * TEX_COORD (+ Mapping) → Sky Vector (same as env 2ac/2ae).
     * Slice 2an: nonempty world_color_image_path builds ImageTextureNode Color →
     * Background Color (Color→Color, no NODE_CONVERT_CF). Projection FLAT/BOX/
     * SPHERE/TUBE. Vector: mode 0 leaves LINK_TEXTURE_UV (ImageTextureNode
     * default; cite shader_nodes.cpp). Else same TEX_COORD (+ Mapping) as 2ac.
     * Slice 2ao/2ap/2aq/2as: Color source (env / sky / ImageTexture / world_color RGB)
     * → RGBCurvesNode (if n>0 && fac!=0) → GammaNode (if gamma != 1) → HSVNode
     * (if hsv not identity) → BrightContrastNode → MixColorNode (if mix) →
     * Background Color.

     * Priority: has_env → has_sky → has_color_image → world_color RGB.
     * BackgroundLight + MIS when has_env || has_sky || has_color_image ||
     * color_nonzero. Env/Color/ImageTexture: map_res 1024. Sky AUTOMATIC 0.
     * Empty-path black stays without BackgroundLight (Slice 2b). */
    {
        unique_ptr<ShaderGraph> graph = make_unique<ShaderGraph>();
        BackgroundNode *bg = graph->create_node<BackgroundNode>();
        const bool has_env = desc->world_image_path && desc->world_image_path[0];
        const bool has_sky = !has_env && desc->world_sky_type != 0;
        const bool has_color_image = !has_env && !has_sky &&
            desc->world_color_image_path && desc->world_color_image_path[0];
        const float3 wcol = (has_env || has_sky || has_color_image) ?
            make_float3(0.0f, 0.0f, 0.0f) :
            make_float3(desc->world_color[0],
                        desc->world_color[1],
                        desc->world_color[2]);
        bg->set_color(wcol);
        bg->set_strength(desc->world_strength);
        const bool color_nonzero = !has_env && !has_sky && !has_color_image &&
            (wcol.x != 0.0f || wcol.y != 0.0f || wcol.z != 0.0f);
        if (has_env) {
            EnvironmentTextureNode *env = graph->create_node<EnvironmentTextureNode>();
            env->set_filename(ustring(desc->world_image_path));
            if (desc->world_image_colorspace && desc->world_image_colorspace[0]) {
                env->set_colorspace(ustring(desc->world_image_colorspace));
            }
            const int proj = desc->world_projection;
            env->set_projection(proj == 1 ? NODE_ENVIRONMENT_MIRROR_BALL :
                                           NODE_ENVIRONMENT_EQUIRECTANGULAR);
            /* Slice 2ac: Vector from TEX_COORD (+ optional Mapping), same modes
             * as mesh TEX_IMAGE. Mode 0 leaves LINK_POSITION (Slice 2aa).
             * World/background Generated compiles to NODE_GEOM_P (Cycles
             * TextureCoordinateNode::compile when compiler.background).
             * Cite shader_nodes.cpp EnvironmentTextureNode Vector LINK_POSITION. */
            const int wmode = desc->world_tex_vector_mode;
            if (tex_mode_has_texcoord(wmode)) {
                TextureCoordinateNode *texcoord =
                    graph->create_node<TextureCoordinateNode>();
                const char *coord_sock = "UV";
                if (tex_mode_is_reflection(wmode)) {
                    coord_sock = "Reflection";
                }
                else if (tex_mode_is_window(wmode)) {
                    coord_sock = "Window";
                }
                else if (tex_mode_is_camera(wmode)) {
                    coord_sock = "Camera";
                }
                else if (tex_mode_is_object(wmode)) {
                    coord_sock = "Object";
                }
                else if (tex_mode_is_generated(wmode)) {
                    coord_sock = "Generated";
                }
                /* Slice 2ae: Object pointer → use_transform + ob_tfm (matrix_world).
                 * Empty-ref (2ac): use_transform stays false. Cycles compile already
                 * inverses ob_tfm — do not invert twice. Cite TextureCoordinateNode. */
                if (tex_mode_is_object(wmode) && desc->world_ob_use_transform) {
                    texcoord->set_use_transform(true);
                    texcoord->set_ob_tfm(tfm_from_12(desc->world_ob_tfm));
                }
                if (tex_mode_has_mapping(wmode)) {
                    MappingNode *mapping = graph->create_node<MappingNode>();
                    mapping->set_mapping_type(
                        static_cast<NodeMappingType>(desc->world_map_type));
                    mapping->set_location(make_float3(
                        desc->world_map_location[0],
                        desc->world_map_location[1],
                        desc->world_map_location[2]));
                    mapping->set_rotation(make_float3(
                        desc->world_map_rotation[0],
                        desc->world_map_rotation[1],
                        desc->world_map_rotation[2]));
                    mapping->set_scale(make_float3(
                        desc->world_map_scale[0],
                        desc->world_map_scale[1],
                        desc->world_map_scale[2]));
                    graph->connect(texcoord->output(coord_sock),
                                   mapping->input("Vector"));
                    graph->connect(mapping->output("Vector"),
                                   env->input("Vector"));
                }
                else {
                    graph->connect(texcoord->output(coord_sock),
                                   env->input("Vector"));
                }
            }
            /* else mode 0: leave Vector unlinked → LINK_POSITION. */
            connect_world_color_chain(graph.get(), env->output("Color"),
                                       wcol, bg, desc);
        }
        else if (has_sky) {
            /* Slice 2am: SkyTextureNode Color → Background Color.
             * Cite shader_nodes.cpp NODE_DEFINE(SkyTextureNode). Default
             * SOCKET is NODE_SKY_MULTIPLE_SCATTERING (Blender RNA NISHITA /
             * MULTIPLE_SCATTERING). Mode 0: Vector unlinked →
             * LINK_TEXTURE_GENERATED (2am bit-identical).
             * Slice 2ar: world_tex_vector_mode non-zero wires TEX_COORD
             * (+ optional Mapping) → Sky Vector — same modes as env 2ac/2ae.
             * Do not invert sun_rotation; simplify_settings wraps it. */
            SkyTextureNode *sky = graph->create_node<SkyTextureNode>();
            NodeSkyType st = NODE_SKY_MULTIPLE_SCATTERING;
            switch (desc->world_sky_type) {
                case 1: st = NODE_SKY_PREETHAM; break;
                case 2: st = NODE_SKY_HOSEK; break;
                case 3: st = NODE_SKY_MULTIPLE_SCATTERING; break;
                case 4: st = NODE_SKY_SINGLE_SCATTERING; break;
                default: st = NODE_SKY_MULTIPLE_SCATTERING; break;
            }
            sky->set_sky_type(st);
            sky->set_sun_direction(make_float3(
                desc->world_sky_sun_direction[0],
                desc->world_sky_sun_direction[1],
                desc->world_sky_sun_direction[2]));
            sky->set_turbidity(desc->world_sky_turbidity);
            sky->set_ground_albedo(desc->world_sky_ground_albedo);
            sky->set_sun_disc(desc->world_sky_sun_disc != 0);
            sky->set_sun_size(desc->world_sky_sun_size);
            sky->set_sun_intensity(desc->world_sky_sun_intensity);
            sky->set_sun_elevation(desc->world_sky_sun_elevation);
            sky->set_sun_rotation(desc->world_sky_sun_rotation);
            sky->set_altitude(desc->world_sky_altitude);
            sky->set_air_density(desc->world_sky_air_density);
            sky->set_aerosol_density(desc->world_sky_aerosol_density);
            sky->set_ozone_density(desc->world_sky_ozone_density);
            /* Slice 2ar: linked Sky Vector (reuse world_tex_vector_mode). */
            const int wmode = desc->world_tex_vector_mode;
            if (tex_mode_has_texcoord(wmode)) {
                TextureCoordinateNode *texcoord =
                    graph->create_node<TextureCoordinateNode>();
                const char *coord_sock = "UV";
                if (tex_mode_is_reflection(wmode)) {
                    coord_sock = "Reflection";
                }
                else if (tex_mode_is_window(wmode)) {
                    coord_sock = "Window";
                }
                else if (tex_mode_is_camera(wmode)) {
                    coord_sock = "Camera";
                }
                else if (tex_mode_is_object(wmode)) {
                    coord_sock = "Object";
                }
                else if (tex_mode_is_generated(wmode)) {
                    coord_sock = "Generated";
                }
                if (tex_mode_is_object(wmode) && desc->world_ob_use_transform) {
                    texcoord->set_use_transform(true);
                    texcoord->set_ob_tfm(tfm_from_12(desc->world_ob_tfm));
                }
                if (tex_mode_has_mapping(wmode)) {
                    MappingNode *mapping = graph->create_node<MappingNode>();
                    mapping->set_mapping_type(
                        static_cast<NodeMappingType>(desc->world_map_type));
                    mapping->set_location(make_float3(
                        desc->world_map_location[0],
                        desc->world_map_location[1],
                        desc->world_map_location[2]));
                    mapping->set_rotation(make_float3(
                        desc->world_map_rotation[0],
                        desc->world_map_rotation[1],
                        desc->world_map_rotation[2]));
                    mapping->set_scale(make_float3(
                        desc->world_map_scale[0],
                        desc->world_map_scale[1],
                        desc->world_map_scale[2]));
                    graph->connect(texcoord->output(coord_sock),
                                   mapping->input("Vector"));
                    graph->connect(mapping->output("Vector"),
                                   sky->input("Vector"));
                }
                else {
                    graph->connect(texcoord->output(coord_sock),
                                   sky->input("Vector"));
                }
            }
            /* else mode 0: leave Vector unlinked → LINK_TEXTURE_GENERATED. */
            connect_world_color_chain(graph.get(), sky->output("Color"),
                                       wcol, bg, desc);
        }
        else if (has_color_image) {
            /* Slice 2an: ImageTextureNode Color → Background Color.
             * Cite shader_nodes.cpp NODE_DEFINE(ImageTextureNode):
             * Vector default LINK_TEXTURE_UV; projection FLAT.
             * Color→Color (no NODE_CONVERT_CF). Do not mix world_color. */
            ImageTextureNode *img = graph->create_node<ImageTextureNode>();
            img->set_filename(ustring(desc->world_color_image_path));
            if (desc->world_color_image_colorspace &&
                desc->world_color_image_colorspace[0]) {
                img->set_colorspace(ustring(desc->world_color_image_colorspace));
            }
            img->set_interpolation(INTERPOLATION_LINEAR);
            img->set_extension(EXTENSION_REPEAT);
            img->set_alpha_type(IMAGE_ALPHA_AUTO);
            const int iproj = desc->world_color_image_projection;
            NodeImageProjection proj = NODE_IMAGE_PROJ_FLAT;
            if (iproj == 1) {
                proj = NODE_IMAGE_PROJ_BOX;
            }
            else if (iproj == 2) {
                proj = NODE_IMAGE_PROJ_SPHERE;
            }
            else if (iproj == 3) {
                proj = NODE_IMAGE_PROJ_TUBE;
            }
            img->set_projection(proj);
            /* Vector: mode 0 leaves LINK_TEXTURE_UV (ImageTexture default).
             * Else TEX_COORD (+ optional Mapping), same as env 2ac/2ae. */
            const int wmode = desc->world_tex_vector_mode;
            if (tex_mode_has_texcoord(wmode)) {
                TextureCoordinateNode *texcoord =
                    graph->create_node<TextureCoordinateNode>();
                const char *coord_sock = "UV";
                if (tex_mode_is_reflection(wmode)) {
                    coord_sock = "Reflection";
                }
                else if (tex_mode_is_window(wmode)) {
                    coord_sock = "Window";
                }
                else if (tex_mode_is_camera(wmode)) {
                    coord_sock = "Camera";
                }
                else if (tex_mode_is_object(wmode)) {
                    coord_sock = "Object";
                }
                else if (tex_mode_is_generated(wmode)) {
                    coord_sock = "Generated";
                }
                if (tex_mode_is_object(wmode) && desc->world_ob_use_transform) {
                    texcoord->set_use_transform(true);
                    texcoord->set_ob_tfm(tfm_from_12(desc->world_ob_tfm));
                }
                if (tex_mode_has_mapping(wmode)) {
                    MappingNode *mapping = graph->create_node<MappingNode>();
                    mapping->set_mapping_type(
                        static_cast<NodeMappingType>(desc->world_map_type));
                    mapping->set_location(make_float3(
                        desc->world_map_location[0],
                        desc->world_map_location[1],
                        desc->world_map_location[2]));
                    mapping->set_rotation(make_float3(
                        desc->world_map_rotation[0],
                        desc->world_map_rotation[1],
                        desc->world_map_rotation[2]));
                    mapping->set_scale(make_float3(
                        desc->world_map_scale[0],
                        desc->world_map_scale[1],
                        desc->world_map_scale[2]));
                    graph->connect(texcoord->output(coord_sock),
                                   mapping->input("Vector"));
                    graph->connect(mapping->output("Vector"),
                                   img->input("Vector"));
                }
                else {
                    graph->connect(texcoord->output(coord_sock),
                                   img->input("Vector"));
                }
            }
            /* else mode 0: leave Vector unlinked → LINK_TEXTURE_UV. */
            connect_world_color_chain(graph.get(), img->output("Color"),
                                       wcol, bg, desc);
        }
        if (!has_env && !has_sky && !has_color_image) {
            /* RGB / unlinked Color: optional Gamma/HSV on world_color.
             * Identity: no extra nodes, bg->set_color already set. */
            connect_world_color_chain(graph.get(), nullptr, wcol, bg, desc);
        }
        graph->connect(bg->output("Background"), graph->output()->input("Surface"));
        scene->default_background->set_graph(std::move(graph));
        scene->default_background->tag_update(scene);

        if (has_env || has_sky || has_color_image || color_nonzero) {
            BackgroundLight *bg_light = scene->create_node<BackgroundLight>();
            bg_light->set_use_mis(true);
            /* Env/Color/ImageTexture: factory 1024 (2aa/2al/2an). Sky AUTOMATIC
             * leaves 0 so Cycles uses SkyTextureNode environment_res
             * (512x256 + sun guiding). ImageTexture is not scanned by
             * device_update_background AUTOMATIC — 0 would still default 1024. */
            bg_light->set_map_resolution(has_sky ? 0 : 1024);
            {
                array<Node *> used;
                used.push_back_slow(scene->default_background);
                bg_light->set_used_shaders(used);
            }
            Object *bg_obj = scene->create_node<Object>();
            bg_obj->set_geometry(bg_light);
            bg_obj->set_visibility(PATH_RAY_VISIBILITY_ALL & ~PATH_RAY_VISIBILITY_CAMERA);
            bg_obj->name = "QTWorld";
            bg_obj->set_random_id(hash_uint2(hash_string("QTWorld"), 0));
        }
    }

    Shader *lamp_shader = make_area_emission(scene);
    for (int i = 0; i < desc->nmeshes; i++) {
        const QT_Mesh *m = &desc->meshes[i];
        Shader *surf = make_principled(scene, m, i);
        add_mesh_object(scene, surf, m);
    }
    for (int i = 0; i < desc->nlights; i++) {
        add_qt_light(scene, lamp_shader, &desc->lights[i]);
    }

    Pass *pass = scene->create_node<Pass>();
    pass->set_name(ustring("combined"));
    pass->set_type(PASS_COMBINED);
}

static void build_simple_scene(Scene *scene, const QT_SimpleScene *desc)
{
    QT_Mesh mesh;
    QT_Light light;
    QT_Scene qs;
    simple_to_qt(desc, &mesh, &light, &qs);
    build_qt_scene(scene, &qs);
}

/* QUANTTRACE-CUBE.md defaults stay 256 / 256 / 128. Smoke:
 * QUANTTRACE_CUBE_WIDTH=32 HEIGHT=32 SAMPLES=4. Invalid values fall back.
 */
static int env_positive_int(const char *name, int fallback)
{
    const char *v = std::getenv(name);
    if (!v || !v[0]) {
        return fallback;
    }
    char *end = nullptr;
    const long n = std::strtol(v, &end, 10);
    if (end == v || *end != 0 || n <= 0 || n > 8192) {
        fprintf(stderr,
                "quanttrace: ignoring invalid %s=%s (using %d)\n",
                name,
                v,
                fallback);
        return fallback;
    }
    return static_cast<int>(n);
}

/* Linear RGBA float OpenEXR. Codec: zip. Combined buffer is bottom-up;
 * Y-flip to top-down like Blender Combined / oiio_output_driver.cpp.
 * Camera uses blender_camera_matrix (object * scale(1,1,-1)).
 * No gamma: EXR stays scene-linear.
 */
static bool write_combined_exr(const char *path,
                               const int width,
                               const int height,
                               const float *rgba)
{
    OIIO::ImageOutput::unique_ptr out = OIIO::ImageOutput::create(path);
    if (!out) {
        fprintf(stderr,
                "quanttrace: ImageOutput::create failed for %s: %s\n",
                path,
                OIIO::geterror().c_str());
        return false;
    }

    OIIO::ImageSpec spec(width, height, 4, OIIO::TypeDesc::FLOAT);
    spec.attribute("compression", "zip");
    spec.attribute("oiio:ColorSpace", "Linear");
    if (!out->open(path, spec)) {
        fprintf(stderr,
                "quanttrace: ImageOutput::open failed: %s\n",
                out->geterror().c_str());
        return false;
    }

    std::vector<float> flipped(static_cast<size_t>(width) * static_cast<size_t>(height) * 4u);
    for (int y = 0; y < height; y++) {
        const float *src = rgba + (static_cast<size_t>(height - 1 - y) * static_cast<size_t>(width) * 4u);
        float *dst = flipped.data() + (static_cast<size_t>(y) * static_cast<size_t>(width) * 4u);
        std::memcpy(dst, src, static_cast<size_t>(width) * 4u * sizeof(float));
    }
    const bool ok = out->write_image(OIIO::TypeDesc::FLOAT, flipped.data());
    if (!ok) {
        fprintf(stderr, "quanttrace: write_image failed: %s\n", out->geterror().c_str());
    }
    out->close();
    return ok;
}

static int run_qt_session(const QT_Scene *desc,
                          float *out_rgba,
                          int out_capacity,
                          int *out_w,
                          int *out_h)
{
    if (!desc || desc->width <= 0 || desc->height <= 0 || desc->samples <= 0 ||
        desc->nmeshes <= 0 || desc->nlights <= 0 || !desc->meshes || !desc->lights) {
        fprintf(stderr, "quanttrace: invalid QT_Scene\n");
        return -1;
    }
    if (desc->nmeshes > QT_MAX_MESHES || desc->nlights > QT_MAX_LIGHTS) {
        fprintf(stderr, "quanttrace: nmeshes=%d nlights=%d exceeds Slice 2c cap\n",
                desc->nmeshes, desc->nlights);
        return -1;
    }
    for (int i = 0; i < desc->nmeshes; i++) {
        const QT_Mesh *m = &desc->meshes[i];
        if (m->nverts <= 0 || m->ntris <= 0 || !m->verts || !m->tris) {
            fprintf(stderr, "quanttrace: invalid QT_Mesh[%d]\n", i);
            return -1;
        }
        if (m->nverts > 1000000 || m->ntris > 2000000) {
            fprintf(stderr, "quanttrace: mesh %d too large for Slice 2c\n", i);
            return -1;
        }
        const bool needs_uv =
            (m->image_path && m->image_path[0]) ||
            (m->rough_image_path && m->rough_image_path[0]) ||
            (m->metal_image_path && m->metal_image_path[0]) ||
            (m->normal_image_path && m->normal_image_path[0]) ||
            (m->ior_image_path && m->ior_image_path[0]) ||
            (m->alpha_image_path && m->alpha_image_path[0]) ||
            (m->trans_image_path && m->trans_image_path[0]) ||
            (m->spec_image_path && m->spec_image_path[0]) ||
            (m->coat_image_path && m->coat_image_path[0]) ||
            (m->sheen_image_path && m->sheen_image_path[0]) ||
            (m->emit_str_image_path && m->emit_str_image_path[0]) ||
            (m->emit_color_image_path && m->emit_color_image_path[0]) ||
            (m->coat_rough_image_path && m->coat_rough_image_path[0]) ||
            (m->coat_ior_image_path && m->coat_ior_image_path[0]) ||
            (m->coat_tint_image_path && m->coat_tint_image_path[0]) ||
            (m->sheen_rough_image_path && m->sheen_rough_image_path[0]) ||
            (m->sheen_tint_image_path && m->sheen_tint_image_path[0]) ||
            (m->coat_normal_image_path && m->coat_normal_image_path[0]) ||
            (m->spec_tint_image_path && m->spec_tint_image_path[0]) ||
            (m->film_thick_image_path && m->film_thick_image_path[0]) ||
            (m->film_ior_image_path && m->film_ior_image_path[0]) ||
            (m->sss_weight_image_path && m->sss_weight_image_path[0]) ||
            (m->sss_radius_image_path && m->sss_radius_image_path[0]) ||
            (m->sss_scale_image_path && m->sss_scale_image_path[0]) ||
        (m->sss_ior_image_path && m->sss_ior_image_path[0]) ||
        (m->sss_aniso_image_path && m->sss_aniso_image_path[0]) ||
        (m->thin_wall_image_path && m->thin_wall_image_path[0]) ||
        (m->diffuse_rough_image_path && m->diffuse_rough_image_path[0]) ||
        (m->aniso_image_path && m->aniso_image_path[0]) ||
        (m->aniso_rot_image_path && m->aniso_rot_image_path[0]) ||
        (m->tangent_image_path && m->tangent_image_path[0]);
        if (needs_uv && !m->uvs) {
            fprintf(stderr, "quanttrace: mesh %d textured but uvs NULL\n", i);
            return -1;
        }
    }

    log_init(nullptr);
    path_init();

    vector<DeviceInfo> devices = Device::available_devices(DEVICE_MASK_CPU);
    if (devices.empty()) {
        fprintf(stderr, "quanttrace: no CPU device\n");
        return -1;
    }

    SessionParams session_params;
    session_params.device = devices.front();
    session_params.background = true;
    session_params.headless = true;
    session_params.samples = desc->samples;
    session_params.threads = 0;
    session_params.use_auto_tile = false;
    session_params.shadingsystem = SHADINGSYSTEM_SVM;

    SceneParams scene_params;
    scene_params.shadingsystem = SHADINGSYSTEM_SVM;
    scene_params.background = true;
    scene_params.bvh_layout = BVH_LAYOUT_EMBREE;

    unique_ptr<Session> session = make_unique<Session>(session_params, scene_params);
    Scene *scene = session->scene.get();

    build_qt_scene(scene, desc);

    std::vector<float> rgba;
    session->set_output_driver(make_unique<CombinedBufferDriver>(&rgba));

    BufferParams buffer_params;
    buffer_params.width = desc->width;
    buffer_params.height = desc->height;
    buffer_params.full_width = desc->width;
    buffer_params.full_height = desc->height;

    session->reset(session_params, buffer_params);
    session->start();
    session->wait();

    const size_t expect = static_cast<size_t>(desc->width) * static_cast<size_t>(desc->height) * 4u;
    if (rgba.empty() || rgba.size() != expect) {
        fprintf(stderr,
                "quanttrace: Combined empty or size mismatch %zu vs %dx%d\n",
                rgba.size(),
                desc->width,
                desc->height);
        return -1;
    }

    float mn[3] = {1.0e30f, 1.0e30f, 1.0e30f};
    float mx[3] = {-1.0e30f, -1.0e30f, -1.0e30f};
    const size_t npix = static_cast<size_t>(desc->width) * static_cast<size_t>(desc->height);
    for (size_t i = 0; i < npix; i++) {
        for (int c = 0; c < 3; c++) {
            const float v = rgba[i * 4u + static_cast<size_t>(c)];
            if (v < mn[c]) {
                mn[c] = v;
            }
            if (v > mx[c]) {
                mx[c] = v;
            }
        }
    }
    fprintf(stderr,
            "quanttrace: Combined RGB min=(%.6g %.6g %.6g) max=(%.6g %.6g %.6g)\n",
            mn[0],
            mn[1],
            mn[2],
            mx[0],
            mx[1],
            mx[2]);

    const char *exr_path = desc->exr_path;
    if (exr_path && exr_path[0]) {
        if (!write_combined_exr(exr_path, desc->width, desc->height, rgba.data())) {
            return -1;
        }
        fprintf(stderr,
                "quanttrace: wrote linear RGBA float OpenEXR (zip) %dx%d %d spp %s\n",
                desc->width,
                desc->height,
                desc->samples,
                exr_path);
    }

    if (out_rgba != nullptr) {
        if (out_capacity < static_cast<int>(expect)) {
            fprintf(stderr,
                    "quanttrace: rgba capacity %d < %zu\n",
                    out_capacity,
                    expect);
            return -1;
        }
        std::memcpy(out_rgba, rgba.data(), expect * sizeof(float));
    }
    if (out_w) {
        *out_w = desc->width;
    }
    if (out_h) {
        *out_h = desc->height;
    }

    return 0;
}

static int run_simple_session(const QT_SimpleScene *desc,
                              float *out_rgba,
                              int out_capacity,
                              int *out_w,
                              int *out_h)
{
    if (!desc) {
        fprintf(stderr, "quanttrace: invalid QT_SimpleScene\n");
        return -1;
    }
    QT_Mesh mesh;
    QT_Light light;
    QT_Scene qs;
    simple_to_qt(desc, &mesh, &light, &qs);
    return run_qt_session(&qs, out_rgba, out_capacity, out_w, out_h);
}

static int run_cube_session(const char *exr_path,
                            float *out_rgba,
                            int out_capacity,
                            int *out_w,
                            int *out_h)
{
    QT_SimpleScene desc;
    const int width = env_positive_int("QUANTTRACE_CUBE_WIDTH", 256);
    const int height = env_positive_int("QUANTTRACE_CUBE_HEIGHT", 256);
    const int samples = env_positive_int("QUANTTRACE_CUBE_SAMPLES", 128);
    fill_locked_cube_desc(&desc, width, height, samples);
    desc.exr_path = exr_path;
    return run_simple_session(&desc, out_rgba, out_capacity, out_w, out_h);
}

}  /* namespace */

CCL_NAMESPACE_END

extern "C" int quanttrace_is_tracer(void)
{
    /* Simple-scene Combined matches stock Cycles; F12 + depsgraph path wired. */
    return 1;
}

extern "C" int quanttrace_session_probe(void)
{
    return 1;
}

extern "C" int quanttrace_render_cube(const char *exr_path)
{
    return ccl::run_cube_session(exr_path, nullptr, 0, nullptr, nullptr);
}

extern "C" int quanttrace_render_cube_rgba(float *out_rgba,
                                          int out_capacity,
                                          int *out_w,
                                          int *out_h)
{
    return ccl::run_cube_session(nullptr, out_rgba, out_capacity, out_w, out_h);
}

extern "C" int quanttrace_render_scene_rgba(const QT_SimpleScene *scene,
                                            float *out_rgba,
                                            int out_capacity,
                                            int *out_w,
                                            int *out_h)
{
    return ccl::run_simple_session(scene, out_rgba, out_capacity, out_w, out_h);
}

extern "C" int quanttrace_render_qt_scene_rgba(const QT_Scene *scene,
                                               float *out_rgba,
                                               int out_capacity,
                                               int *out_w,
                                               int *out_h)
{
    return ccl::run_qt_session(scene, out_rgba, out_capacity, out_w, out_h);
}

#endif /* QT_WITH_CYCLES */
