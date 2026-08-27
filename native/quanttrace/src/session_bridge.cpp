/* QuantTrace Slice 2 — Cycles Session API bridge sketch.
 *
 * Default build: stub (QT_WITH_CYCLES off). Compiles into libquanttrace
 * next to hello.c. quanttrace_is_tracer() stays 0 in hello.c.
 *
 * -DQT_WITH_CYCLES=1: this file WILL call ccl::Session / Scene / Mesh /
 * AreaLight / PrincipledBsdfNode. After Session::wait it writes Combined
 * as linear RGBA float OpenEXR (zip) when exr_path is set. It still
 * does not flip is_tracer. Pixel-match vs stock Cycles Combined is later.
 * QUANTTRACE_CUBE_WIDTH/HEIGHT/SAMPLES override the locked 256/256/128
 * defaults (smoke: 32/32/4).
 *
 * Cite: blender/cycles src/session/session.h, src/scene/scene.h,
 *       src/app/cycles_standalone.cpp, src/app/cycles_xml.cpp
 * Scene lock: docs/research/QUANTTRACE-CUBE.md
 */

#include "quanttrace.h"

#ifndef QT_WITH_CYCLES

extern "C" int quanttrace_session_probe(void)
{
    return 0;
}

extern "C" int quanttrace_render_cube(const char * /*exr_path*/)
{
    return -1;
}

#else /* QT_WITH_CYCLES — real Session path, still not a product tracer */

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
#include "session/buffers.h"
#include "session/output_driver.h"
#include "session/session.h"
#include "util/log.h"
#include "util/path.h"
#include "util/transform.h"
#include "util/unique_ptr.h"

CCL_NAMESPACE_BEGIN

namespace {

/* Locked cube: default Blender cube is 2 m, verts at +/-1 on each axis.
 * 12 triangles (6 quads split). Matches QUANTTRACE-CUBE.md mesh.
 */
static const float kCubeVerts[8][3] = {
    {-1.0f, -1.0f, -1.0f}, {1.0f, -1.0f, -1.0f}, {1.0f, 1.0f, -1.0f}, {-1.0f, 1.0f, -1.0f},
    {-1.0f, -1.0f, 1.0f},  {1.0f, -1.0f, 1.0f},  {1.0f, 1.0f, 1.0f},  {-1.0f, 1.0f, 1.0f},
};
/* Each quad: v0,v1,v2,v3 -> tris (v0,v1,v2) (v0,v2,v3). */
static const int kCubeQuads[6][4] = {
    {0, 1, 2, 3}, /* -Z */
    {4, 7, 6, 5}, /* +Z */
    {0, 4, 5, 1}, /* -Y */
    {3, 2, 6, 7}, /* +Y */
    {0, 3, 7, 4}, /* -X */
    {1, 5, 6, 2}, /* +X */
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

static void build_cube_scene(Scene *scene, const int width, const int height)
{
    /* Integrator: stock uni-PT, 128 spp, adaptive off, clamp 0/10. */
    Integrator *integrator = scene->integrator;
    integrator->set_use_adaptive_sampling(false);
    integrator->set_use_denoise(false);
    integrator->set_seed(0); /* QUANTTRACE-CUBE.md locked seed */
    integrator->set_sample_clamp_direct(0.0f);
    integrator->set_sample_clamp_indirect(10.0f);

    Film *film = scene->film;
    film->set_exposure(1.0f);
    film->set_filter_type(FILTER_GAUSSIAN);
    film->set_filter_width(1.5f);

    /* Camera: 50 mm on 36 mm sensor. FOV = 2*atan(18/50). */
    Camera *cam = scene->camera;
    cam->set_camera_type(CAMERA_PERSPECTIVE);
    cam->set_fov(2.0f * atanf(18.0f / 50.0f));
    cam->set_sensorwidth(0.036f);
    cam->set_full_width(width);
    cam->set_full_height(height);
    cam->set_matrix(look_at(make_float3(7.358891f, -6.925791f, 4.958309f),
                            make_float3(0.0f, 0.0f, 0.0f),
                            make_float3(0.0f, 0.0f, 1.0f),
                            false)); /* +Z toward origin */
    cam->compute_auto_viewplane();
    cam->need_flags_update = true;
    cam->update(scene);

    /* Black world. */
    {
        unique_ptr<ShaderGraph> graph = make_unique<ShaderGraph>();
        BackgroundNode *bg = graph->create_node<BackgroundNode>();
        bg->set_color(make_float3(0.0f, 0.0f, 0.0f));
        bg->set_strength(0.0f);
        graph->connect(bg->output("Background"), graph->output()->input("Surface"));
        scene->default_background->set_graph(std::move(graph));
        scene->default_background->tag_update(scene);
    }

    /* Principled: base 0.8, roughness 0.5, metal 0, IOR 1.45, alpha 1. */
    Shader *surf = scene->create_node<Shader>();
    surf->name = "cube_principled";
    {
        unique_ptr<ShaderGraph> graph = make_unique<ShaderGraph>();
        PrincipledBsdfNode *bsdf = graph->create_node<PrincipledBsdfNode>();
        bsdf->set_base_color(make_float3(0.8f, 0.8f, 0.8f));
        bsdf->set_roughness(0.5f);
        bsdf->set_metallic(0.0f);
        bsdf->set_ior(1.45f);
        bsdf->set_alpha(1.0f);
        graph->connect(bsdf->output("BSDF"), graph->output()->input("Surface"));
        surf->set_graph(std::move(graph));
        surf->tag_update(scene);
    }

    /* Mesh cube. */
    Mesh *mesh = scene->create_node<Mesh>();
    {
        array<Node *> used;
        used.push_back_slow(surf);
        mesh->set_used_shaders(used);
    }
    mesh->resize_mesh(8, 12);
    packed_float3 *P = mesh->get_position_for_write();
    for (int i = 0; i < 8; i++) {
        P[i] = make_float3(kCubeVerts[i][0], kCubeVerts[i][1], kCubeVerts[i][2]);
    }
    int *tris = mesh->get_triangles().data();
    int *shader_idx = mesh->get_shader().data();
    bool *smooth = mesh->get_smooth().data();
    int t = 0;
    for (int q = 0; q < 6; q++) {
        const int v0 = kCubeQuads[q][0];
        const int v1 = kCubeQuads[q][1];
        const int v2 = kCubeQuads[q][2];
        const int v3 = kCubeQuads[q][3];
        tris[t * 3 + 0] = v0;
        tris[t * 3 + 1] = v1;
        tris[t * 3 + 2] = v2;
        shader_idx[t] = 0;
        smooth[t] = false;
        t++;
        tris[t * 3 + 0] = v0;
        tris[t * 3 + 1] = v2;
        tris[t * 3 + 2] = v3;
        shader_idx[t] = 0;
        smooth[t] = false;
        t++;
    }
    mesh->tag_triangles_modified();
    mesh->tag_shader_modified();
    mesh->tag_smooth_modified();
    mesh->tag_position_modified();
    mesh->add_vertex_normals();

    Object *cube_obj = scene->create_node<Object>();
    cube_obj->set_geometry(mesh);
    cube_obj->set_tfm(transform_identity());

    /* Area light: size 1 m, energy 1000, white, Blender startup lamp pose,
     * aimed at origin. Cycles area emits along object -Z. Official Blender
     * sync (intern/cycles/blender/light.cpp): strength = color * energy *
     * exp2(exposure). White × 1000 × exp2(0) → (1000,1000,1000). Normalize
     * socket default true matches Blender (!LA_UNNORMALIZED). No extra scale.
     */
    Shader *lamp_shader = scene->create_node<Shader>();
    lamp_shader->name = "area_emission";
    {
        unique_ptr<ShaderGraph> graph = make_unique<ShaderGraph>();
        EmissionNode *emission = graph->create_node<EmissionNode>();
        emission->set_color(make_float3(1.0f, 1.0f, 1.0f));
        emission->set_strength(1.0f);
        graph->connect(emission->output("Emission"), graph->output()->input("Surface"));
        lamp_shader->set_graph(std::move(graph));
        lamp_shader->tag_update(scene);
    }

    AreaLight *area = scene->create_node<AreaLight>();
    area->set_sizeu(1.0f);
    area->set_sizev(1.0f);
    area->set_strength(make_float3(1000.0f, 1000.0f, 1000.0f));
    area->set_use_mis(true);
    area->set_cast_shadow(true);
    {
        array<Node *> used;
        used.push_back_slow(lamp_shader);
        area->set_used_shaders(used);
    }

    Object *light_obj = scene->create_node<Object>();
    light_obj->set_geometry(area);
    light_obj->set_visibility(PATH_RAY_VISIBILITY_ALL & ~PATH_RAY_VISIBILITY_CAMERA);
    light_obj->set_tfm(look_at(make_float3(4.07625f, 1.00545f, 5.90386f),
                               make_float3(0.0f, 0.0f, 0.0f),
                               make_float3(0.0f, 0.0f, 1.0f),
                               true)); /* -Z toward origin (area emit) */

    Pass *pass = scene->create_node<Pass>();
    pass->set_name(ustring("combined"));
    pass->set_type(PASS_COMBINED);
}

/* QUANTTRACE-CUBE.md defaults stay 256 / 256 / 128. Smoke this hour:
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
 * camera look_at uses Cycles +Z with Blender screen-X (y = -Blender_Y),
 * so writing without an extra Y-flip matches Blender top-down Combined.
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

    /* No Y-flip here: look_at camera uses x=cross(z,up) so camera Y is
     * -Blender_Y; writing the bottom-up Combined buffer as-is cancels that
     * and matches Blender top-down EXR (measured 11am PlugWalk). */
    const bool ok = out->write_image(OIIO::TypeDesc::FLOAT, rgba);
    if (!ok) {
        fprintf(stderr, "quanttrace: write_image failed: %s\n", out->geterror().c_str());
    }
    out->close();
    return ok;
}

static int run_cube_session(const char *exr_path)
{
    log_init(nullptr);
    path_init();

    vector<DeviceInfo> devices = Device::available_devices(DEVICE_MASK_CPU);
    if (devices.empty()) {
        fprintf(stderr, "quanttrace: no CPU device\n");
        return -1;
    }

    const int width = env_positive_int("QUANTTRACE_CUBE_WIDTH", 256);
    const int height = env_positive_int("QUANTTRACE_CUBE_HEIGHT", 256);
    const int samples = env_positive_int("QUANTTRACE_CUBE_SAMPLES", 128);

    SessionParams session_params;
    session_params.device = devices.front();
    session_params.background = true;
    session_params.headless = true;
    session_params.samples = samples;
    session_params.threads = 0;
    session_params.use_auto_tile = false;
    session_params.shadingsystem = SHADINGSYSTEM_SVM;

    SceneParams scene_params;
    scene_params.shadingsystem = SHADINGSYSTEM_SVM;
    scene_params.background = true;
    scene_params.bvh_layout = BVH_LAYOUT_EMBREE; /* CPU Embree path */

    unique_ptr<Session> session = make_unique<Session>(session_params, scene_params);
    Scene *scene = session->scene.get();

    build_cube_scene(scene, width, height);

    std::vector<float> rgba;
    session->set_output_driver(make_unique<CombinedBufferDriver>(&rgba));

    BufferParams buffer_params;
    buffer_params.width = width;
    buffer_params.height = height;
    buffer_params.full_width = width;
    buffer_params.full_height = height;

    session->reset(session_params, buffer_params);
    session->start();
    session->wait();

    const size_t expect = static_cast<size_t>(width) * static_cast<size_t>(height) * 4u;
    if (rgba.empty() || rgba.size() != expect) {
        fprintf(stderr,
                "quanttrace: Combined empty or size mismatch %zu vs %dx%d\n",
                rgba.size(),
                width,
                height);
        return -1;
    }

    float mn[3] = {1.0e30f, 1.0e30f, 1.0e30f};
    float mx[3] = {-1.0e30f, -1.0e30f, -1.0e30f};
    const size_t npix = static_cast<size_t>(width) * static_cast<size_t>(height);
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

    if (exr_path && exr_path[0]) {
        if (!write_combined_exr(exr_path, width, height, rgba.data())) {
            return -1;
        }
        fprintf(stderr,
                "quanttrace: wrote linear RGBA float OpenEXR (zip) %dx%d %d spp %s\n",
                width,
                height,
                samples,
                exr_path);
    }

    return 0;
}

}  /* namespace */

CCL_NAMESPACE_END

extern "C" int quanttrace_session_probe(void)
{
    return 1; /* Session path compiled in. is_tracer still 0. */
}

extern "C" int quanttrace_render_cube(const char *exr_path)
{
    return ccl::run_cube_session(exr_path);
}

#endif /* QT_WITH_CYCLES */
