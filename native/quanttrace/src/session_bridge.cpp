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
 *   when has_env || has_sky || color_nonzero. Unlinked Vector (GENERATED).
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
 * Slice 2ab: TEX_COORD Object-with-pointer (use_transform + ob_tfm).
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
    mesh->thin_wall = s->thin_wall;
    mesh->transmission_weight = s->transmission_weight;
    mesh->tex_ob_use_transform = s->tex_ob_use_transform;
    std::memcpy(mesh->tex_ob_tfm, s->tex_ob_tfm, sizeof(mesh->tex_ob_tfm));

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

/* Slice 2ao: identity skip keeps 2aa/2al/2am/2an bit-identical. */
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

/* Wire Color source → Gamma (if gamma!=1) → HSV (if not identity) →
 * Background Color. color_src NULL uses wcol as unlinked Color default.
 * Cite shader_nodes.h GammaNode (set_color, set_gamma) / HSVNode
 * (set_color, set_hue, set_saturation, set_value, set_fac). */
static void connect_world_color_chain(ShaderGraph *graph,
                                      ShaderOutput *color_src,
                                      const float3 &wcol,
                                      BackgroundNode *bg,
                                      const QT_Scene *desc)
{
    const bool use_gamma = !world_gamma_identity(desc);
    const bool use_hsv = !world_hsv_identity(desc);
    ShaderOutput *cur = color_src;
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
           tex_mode_is_generated(m->bump_tex_vector_mode);
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

static Shader *make_principled(Scene *scene, const QT_Mesh *m, int index)
{
    Shader *surf = scene->create_node<Shader>();
    surf->name = string_printf("qt_principled_%d", index);
    unique_ptr<ShaderGraph> graph = make_unique<ShaderGraph>();
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
    if (m->image_path && m->image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->image_path, m->image_colorspace, m->tex_vector_mode,
            m->map_location, m->map_rotation, m->map_scale, m->map_type);
        graph->connect(img->output("Color"), bsdf->input("Base Color"));
    }
    if (m->rough_image_path && m->rough_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->rough_image_path, m->rough_image_colorspace,
            m->rough_tex_vector_mode, m->rough_map_location, m->rough_map_rotation,
            m->rough_map_scale, m->rough_map_type);
        /* Color → float: ShaderGraph::connect inserts NODE_CONVERT_CF (average). */
        graph->connect(img->output("Color"), bsdf->input("Roughness"));
    }
    if (m->metal_image_path && m->metal_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->metal_image_path, m->metal_image_colorspace,
            m->metal_tex_vector_mode, m->metal_map_location, m->metal_map_rotation,
            m->metal_map_scale, m->metal_map_type);
        graph->connect(img->output("Color"), bsdf->input("Metallic"));
    }
    /* Slice 2x: TEX_IMAGE Color → NODE_CONVERT_CF → Bump Height → Principled Normal.
     * Official Cycles BumpNode (shader_nodes.cpp NODE_DEFINE): invert=false,
     * use_object_space=false, height=1.0, strength=1.0, distance=0.1f.
     * Blender 5.2 ShaderNodeBump RNA (bpy-verified): invert=False, Strength=1.0,
     * Distance=0.001, Filter Width=0.1, Height=1.0. No use_object_space RNA.
     * Match the Blender node (packer copies RNA defaults), not Cycles 0.1 distance.
     * ShaderGraph::refine_bump_nodes clones Height onto SampleCenter/X/Y —
     * only connect Height; do not wire Sample*. Graph finalize on Session.
     * If both bump_* and normal_* paths are set, Bump wins (packer fills one). */
    if (m->bump_image_path && m->bump_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->bump_image_path, m->bump_image_colorspace,
            m->bump_tex_vector_mode, m->bump_map_location, m->bump_map_rotation,
            m->bump_map_scale, m->bump_map_type);
        BumpNode *bump = graph->create_node<BumpNode>();
        bump->set_invert(m->bump_invert != 0);
        bump->set_use_object_space(false);
        bump->set_strength(m->bump_strength);
        bump->set_distance(m->bump_distance);
        graph->connect(img->output("Color"), bump->input("Height"));
        graph->connect(bump->output("Normal"), bsdf->input("Normal"));
    }
    /* Slice 2j: TEX_IMAGE Color → NormalMap Color → Principled Normal.
     * Official Blender sync (intern/cycles/blender/shader.cpp ShaderNodeNormalMap):
     *   space TANGENT → NODE_NORMAL_MAP_TANGENT (default).
     *   Strength unlinked RNA default 1.0 → set_strength.
     *   Color from Image Texture Color; convention OpenGL default;
     *   attribute empty → ATTR_STD_UV + undisplaced tangents
     *   (Mesh::update_tangents during geometry update). */
    else if (m->normal_image_path && m->normal_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->normal_image_path, m->normal_image_colorspace,
            m->normal_tex_vector_mode, m->normal_map_location, m->normal_map_rotation,
            m->normal_map_scale, m->normal_map_type);
        NormalMapNode *nmap = graph->create_node<NormalMapNode>();
        /* Slice 2z/2ad: TANGENT/OBJECT/WORLD/BLENDER_OBJECT/BLENDER_WORLD.
         * Unknown → TANGENT. Cite src/scene/shader_nodes.cpp SOCKET_ENUM space
         * + kernel/svm/types.h NodeNormalMapSpace + tex_coord.h Y/Z flip for
         * BLENDER_*. Blender RNA identifiers match QT ints 0..4. */
        int sp = m->normal_space;
        ccl::NodeNormalMapSpace space = NODE_NORMAL_MAP_TANGENT;
        if (sp == QT_NORMAL_MAP_OBJECT) space = NODE_NORMAL_MAP_OBJECT;
        else if (sp == QT_NORMAL_MAP_WORLD) space = NODE_NORMAL_MAP_WORLD;
        else if (sp == QT_NORMAL_MAP_BLENDER_OBJECT) space = NODE_NORMAL_MAP_BLENDER_OBJECT;
        else if (sp == QT_NORMAL_MAP_BLENDER_WORLD) space = NODE_NORMAL_MAP_BLENDER_WORLD;
        nmap->set_space(space);
        nmap->set_strength(m->normal_strength);
        graph->connect(img->output("Color"), nmap->input("Color"));
        graph->connect(nmap->output("Normal"), bsdf->input("Normal"));
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
        NormalMapNode *nmap = graph->create_node<NormalMapNode>();
        int csp = m->coat_normal_space;
        ccl::NodeNormalMapSpace cspace = NODE_NORMAL_MAP_TANGENT;
        if (csp == QT_NORMAL_MAP_OBJECT) cspace = NODE_NORMAL_MAP_OBJECT;
        else if (csp == QT_NORMAL_MAP_WORLD) cspace = NODE_NORMAL_MAP_WORLD;
        else if (csp == QT_NORMAL_MAP_BLENDER_OBJECT) cspace = NODE_NORMAL_MAP_BLENDER_OBJECT;
        else if (csp == QT_NORMAL_MAP_BLENDER_WORLD) cspace = NODE_NORMAL_MAP_BLENDER_WORLD;
        nmap->set_space(cspace);
        nmap->set_strength(m->coat_normal_strength);
        graph->connect(img->output("Color"), nmap->input("Color"));
        graph->connect(nmap->output("Normal"), bsdf->input("Coat Normal"));
    }

    /* Slice 2u: Specular Tint Color→Color; Thin Film Thickness/IOR via NODE_CONVERT_CF;
     * Subsurface Weight/Scale via NODE_CONVERT_CF; Subsurface Radius Color→Vector.
     * Pin subsurface_weight=1 when Radius/Scale map and Weight is unmapped.
     * Pin thin_film_thickness=400 nm when Film IOR maps and Thickness is unmapped
     * (Cycles default thickness is 0 = no film). */
    if (m->spec_tint_image_path && m->spec_tint_image_path[0]) {
        ImageTextureNode *img = wire_tex_image(
            graph.get(), m, m->spec_tint_image_path, m->spec_tint_image_colorspace,
            m->spec_tint_tex_vector_mode, m->spec_tint_map_location,
            m->spec_tint_map_rotation, m->spec_tint_map_scale, m->spec_tint_map_type);
        graph->connect(img->output("Color"), bsdf->input("Specular Tint"));
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
     * mix world_color into the sky graph. Vector unlinked LINK_TEXTURE_GENERATED.
     * Slice 2an: nonempty world_color_image_path builds ImageTextureNode Color →
     * Background Color (Color→Color, no NODE_CONVERT_CF). Projection FLAT/BOX/
     * SPHERE/TUBE. Vector: mode 0 leaves LINK_TEXTURE_UV (ImageTextureNode
     * default; cite shader_nodes.cpp). Else same TEX_COORD (+ Mapping) as 2ac.
     * Slice 2ao: Color source (env / sky / ImageTexture / world_color RGB)
     * → GammaNode (if gamma != 1) → HSVNode (if hsv not identity) →
     * Background Color. Identity skips extra nodes (2aa/2al/2am/2an
     * bit-identical). Cite shader_nodes.h GammaNode / HSVNode.
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
             * MULTIPLE_SCATTERING). Vector unlinked → LINK_TEXTURE_GENERATED.
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
