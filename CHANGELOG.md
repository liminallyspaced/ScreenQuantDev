# Changelog

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
