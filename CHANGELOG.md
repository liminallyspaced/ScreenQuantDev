# Changelog

## 0.3.3 — 2026-08-19

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
