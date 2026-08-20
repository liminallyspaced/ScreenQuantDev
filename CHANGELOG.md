# Changelog

## 0.3.3 — Unreleased

- MESH_EMIT_SHADOW_SKIP inventory/apply (Auto off). Cycles-correct write: turn off object shadow ray visibility (`visible_shadow` / `cycles_visibility.shadow`, `intern/cycles/blender/object.cpp` `SD_OBJECT_SHADOW`) on MESH_EMIT_BACKFACE cards so shadow rays never hit the Transparent Mix. Camera/glossy/diffuse stay; emission still lights as a mesh light. Journal `SHADOW_VIS_OFF` `{object, prev}`. Not cull RNA. Not unlink Transparent (that is the quality-risk alternate: Cycles 4.5 does not sync `use_backface_culling`, F12 back becomes Emission). TRIM still keeps `visible_shadow` True. Planner hook `mesh_emit_shadow_skip_actions` (time_factor 1.0) is not called from `build_speed_plan`. Auto off until HDR-FLIP on Classroom and loft. Never `is_portal`. Never AREA convert. Never integrator RNA. No time claim. Official Classroom DNA (no bpy): MESH_EMIT_BACKFACE=2; 2.79 has no `visible_shadow` — Cycles ray vis is IDProperty `cycles_visibility.shadow`; hallWindow group empty (shadow key absent) → UNKNOWN; windows `shadow=0` already off; SHADOW_SKIP_OK not proven. BMW27: 0 emit cards. Does not change Classroom 41% / loft 52%.
- BACKFACE_EMIT_OPAQUE shadow-ray source note (blender-v4.5-release). Cycles does not sync `use_backface_culling` (`intern/cycles/blender/shader.cpp`). No `SHADER_BACKFACE_CULL` / `SD_USE_BACKFACE_CULLING`. Kernel `SD_BACKFACING` is post-hit (`shader_data.h`, camera + shadow + diffuse) and does not skip intersections — shadow rays are not culled. Unlink Transparent still drops `SD_HAS_TRANSPARENT_SHADOW` (`svm.cpp` `has_surface_transparent` on remaining closures; `shadow_all.h` opaque stop). Mix becomes Emission passthrough without cull; Cycles F12 back is Emission. Auto still off. No time claim. Does not change Classroom 41% / loft 52%.
- BACKFACE_EMIT_OPAQUE inventory/apply (Auto off). Unlink Transparent on MESH_EMIT_BACKFACE + journaled `use_backface_culling` so Cycles drops `SD_HAS_TRANSPARENT_SHADOW` (intern/cycles/scene/shader.cpp / kernel shadow retrace). hasattr-gated (Blender 4.1+ Cycles). Quality: outside the room the card disappears (cull) instead of transparent; window rebate / two-way views can change. Auto off until HDR-FLIP on Classroom and loft. Manual-first. Never `is_portal`. Never AREA convert. Never integrator RNA. No time claim. Does not change Classroom 41% / loft 52%.
- PORTAL_MESH role correction: official Classroom 2 hits (`dayLight_portal` on hallWindow / windows) are mesh *lights* with backface hide (`MESH_EMIT_BACKFACE`), not Cycles portal lights. Cycles `Light.cycles.is_portal` (`intern/cycles/scene/light.cpp`) does not emit — converting MESH_EMIT_BACKFACE to `is_portal` is forbidden (drops the lamp). Later convert (Manual, unbuilt) would be AREA light matching strength×area + hide_render mesh, not a portal. `WORLD_PORTAL_CARD` (Transparent+Backfacing without proven Emission) is a different class, still unbuilt. Auto off. No convert. No time claim. Does not change Classroom 41% / loft 52%.
- PORTAL_MESH inventory: hide_render=False MESH/CURVE whose used-face material is Mix(Transparent BSDF, Emission) with Fac linked to Geometry Backfacing. Skip HERO/EXCLUDE, linked ids, GROUP trees, glass/refraction/principled transmission, and objects that already are Cycles portal lights. Name is not how we detect. No convert, no light create. Planner hook `portal_mesh_actions` (time_factor 1.0) is not called from `build_speed_plan`. Auto off. No time claim. Official Classroom DNA (no bpy, `_mainScene`): PORTAL_MESH=2 (hallWindow / Box321.002 and windows / Plane, material dayLight_portal, Fac=Geometry.Backfacing proven). BMW27 DNA: PORTAL_MESH=0 (no Geometry node). Does not change Classroom 41% / loft 52%.
- Classroom DNA Mix inventory (no bpy): official `classroom.zip` (`BLENDER-v279`, 67 MB, not git-added). Local `_mainScene` Mix walk complete (UNKNOWN_FAC=0, material links intact). PRUNE_MIX_TRANSPARENT=0 PRUNE_DISPLACE=0 UNIQUE_UNUSED_SLOTS=0 UNUSED_COLOR_ATTRS=0. 14 Mix Shader Fac proven 0.01–0.15 (gloss mixes, not 0/1); only Transparent BSDF is `dayLight_portal` (Fac linked to Backfacing). KEEP_GLASS=1 SKIP_GROUP=1. Auto off. No time claim. Does not change Classroom 41% / loft 52%.
- BMW27 DNA inventory (no bpy) results: Mix-Transparent/Displace/unique-slots/color-attrs all 0. KEEP_GLASS=3. Auto off. Does not change Classroom 41% / loft 52%.
- PRUNE_DISPLACE: Material Output Displacement linked to a proven-zero constant (Value=0 / Combine XYZ 0 / Displacement Height+Scale 0). Unlink Displacement (existing NODE_UNLINK). Unconnected is already dead (no record). Texture / noise / GROUP / Math skipped. Apply exists, Auto off, no time claim. Official BMW27 DNA (no bpy): PRUNE_DISPLACE=0 (2 Displacement links are HueSat/Image, not proven-zero). Auto off, no time claim.
- UNUSED_COLOR_ATTRS: unique local meshes, skip linked / override / HERO / EXCLUDE / any modifier. Color attributes (color_attributes or vertex_colors) not named by a used-face Attribute / Vertex Color / Color Attribute node. UV maps and position/normal built-ins are never candidates. Inventory-only: apply would drop pixel values and revert cannot restore the layer data without a blob. Auto off, no time claim. Official BMW27 DNA (no bpy): UNUSED_COLOR_ATTRS=0 (no CD_MCOL/CD_MLOOPCOL). Auto off, no time claim.

- UNUSED_SLOTS: unique-shader gate. Duplicate unused slots of an already-used material are RNA noise (Cycles `get_used_shaders()` unions unique shaders) and are skipped. Unique unused materials stay prune keepers; extra_attrs tags UV / UV_TANGENT / VCOL / GENERATED / GROUP that used shaders on that mesh do not request. Official loft 2026-08-19: 891 meshes / 21k unused slots (pre-gate). Classroom: 0. Apply exists, Auto off, no time claim.
- DEAD_CLOSURE_PRUNE: inventory/classifier only. Mix Shader Fac proven 0/1 with unused Transparent BSDF is PRUNE_MIX_TRANSPARENT (unlink dead shader input; apply exists, Auto off). Official Classroom/loft: 0 PRUNE_ALPHA, 0 PRUNE_VOLUME. Official BMW27 DNA (no bpy): PRUNE_MIX_TRANSPARENT=0 (1 Transparent BSDF on Glass Fac=0.8 → KEEP_GLASS=3; other Mix Facs 0.1–0.6 not 0/1). 0 PRUNE_ALPHA/VOLUME/AOV. Classroom/loft still 0. Auto off, no time claim.
- Opaque cutout shadows off on proven CLIP/HASHED cutouts only.
- Sample knee: already-adaptive files pad an extra doubling (512→128 becomes 256). Adaptive-off interiors stay one doubling (300→128).
- CAMERA_CULL tags linked scatter/tiny (Cycles flags, not hide_render) and turns on Simplify with high caps. Distance cull stays off.
- N-panel is one Make it Fast button plus Revert. Analyze / VRAM / Manual / Tune / Safety stay closed. Auto click runs Analyze then the speed stack, then Fit-to-Budget only if VRAM is over. Draft / Quantize / Tune are not auto-fired.
- CAMERA_CULL does not skip objects shared with other local scenes; Cycles evaluates the flag against the rendering camera (Classroom dustParticules/volumeLight).
- used-outside ignores linked library scenes, so CAMERA_CULL can tag linked scatter that only lives in this file.
- last_report maxlen is 1 MB and writes never emit truncated JSON, so Analyze grade survives Make it Fast.
- Operator copy reports the padded sample count (128 / 256), not the raw probe knee.
- FILTER_GLOSSY: `blur_glossy` 0→1.0 when glossy/glass/anisotropic/clearcoat is proven. Never raises a user value already > 0. GROUP/HERO-only skipped.
- AUTO_SCRAMBLE: `auto_scrambling_distance` on for GPU, paired with TABULATED_SOBOL. Never writes a huge manual `scrambling_distance`.
- Public Classroom claim stays 41%. loft unchanged.

**Versioning rule (tied to the journal schema):** a release that changes the journal
schema in a way older versions cannot faithfully revert is a **major** bump; additive,
revert-compatible changes (new levers, new entry fields with safe defaults) are a
**minor** bump; anything with no journal schema change is a **patch**.
Every shipped zip bumps `blender_manifest.toml` and is named `scenequant-X.Y.Z.zip`. Never replace the same version number.

## 0.3.2 — 2026-08-19

- Persistent Data on stills (next F12 keeps the BVH).
- Transparent shadows cap 4 when the scene proves alpha/glass.

## 0.3.1 — 2026-08-19

- Manifest website points at the public repo: `github.com/liminallyspaced/ScreenQuantDev`.
- Same Make it Fast addon as 0.3.0.

## 0.3.0 — 2026-08-19

First public build of **Make it Fast**.

- One-click revertible Cycles speed plan (adaptive sampling, sample-knee cap, OIDN / GPU denoise, bounce/clamp, light tree, caustics, camera cull, dead geometry).
- Draft / Fast GI / resolution tricks stay out of the default click.
- Also ships Analyze, Fit to Budget (VRAM), Probe Sample Knee, Verify Render, Revert All.

Measured on RTX 2080 Super Max-Q 8 GB, factory-startup, persistent data off:

- Classroom (Seux), Blender 4.5.5 LTS: 2:43 → 1:35 (41%)
- loft.blend, Blender 4.5.5 LTS: 5:37 → 2:41 (52%)
- loft.blend, Blender 5.1.2: 5:50 → 2:12 (62%)
