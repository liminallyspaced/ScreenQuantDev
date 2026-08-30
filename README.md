# SceneQuant

Faster Cycles. Preview first. Full undo.

Free Blender addon for **Blender 4.2+**. Open the **SceneQuant** tab in the 3D Viewport N-panel, press **Analyze & Preview**, read the plan, then render.

[Download scenequant-0.3.5.zip](https://github.com/liminallyspaced/ScreenQuantDev/releases/latest) · [itch.io](https://liminalvisual.itch.io/scenequant) · [Gumroad](https://8139959199815.gumroad.com/l/exyxdi)

Do **not** install GitHub’s “Source code” zip. That is the repo, not the addon.

Author: [Nick Siegel](https://github.com/liminallyspaced) · GPL-3.0-or-later

---

## Install

1. Download `scenequant-0.3.5.zip` from [Releases](https://github.com/liminallyspaced/ScreenQuantDev/releases/latest).
2. Blender → **Edit → Preferences → Add-ons → Install from Disk**.
3. Enable **SceneQuant — Scene & Render Optimizer**.
4. In the 3D Viewport, press **N**, open the **SceneQuant** tab.

You need a **Cycles** scene with a **camera**. EEVEE is not what this addon plans for.

---

## The 30-second path

This is the whole product for most people.

1. Leave **Quality Contract** on **Preserve Look**.
2. Leave **Render Intent** on **Auto**.
3. Click **Analyze & Preview**.
4. Read the plan. Confirm if you want it applied.
5. Hit F12 / render animation as usual.
6. Hate it? Click **Revert SceneQuant Changes**.

Preserve Look does **not** change lights, shadows, materials, object visibility, bounce limits, or your denoiser. It will not turn OIDN on, and it will not switch Accurate prefilter to Fast.

---

## Main panel (open when you install)

### Quality Contract

How much SceneQuant is allowed to change in exchange for speed.

| Choice | What it means |
| --- | --- |
| **Preserve Look** (default) | Safe for finals and video. Sampling and no-op GPU settings only. Look stays. |
| **Balanced** | May lower samples after measuring. Still keeps lighting, materials, visibility, and denoiser quality. |
| **Aggressive** | The old full stack. Can change the look (culling, path settings, perceptual levers). Review every action. |

The published 41% / 52% / 62% plates were timed on **Aggressive**, not on Preserve Look. Preserve Look will usually move less. That is the point.

### Render Intent

| Choice | What it means |
| --- | --- |
| **Auto** | If your output range is more than one frame, treat it as Video. |
| **Video** | Checks several frames before lowering samples. The hardest frame wins. A weak frame rejects the cut for the whole shot. |
| **Still** | Optimize the current frame only. |

**Video Check Frames** (shows when Intent is Auto or Video): how many frames to sample. Default is 3. Range is 2–7.

### Analyze & Preview

The big button. It:

1. Analyzes the scene.
2. Builds a speed plan for **this** file under the contract you picked.
3. Shows the plan before applying.
4. Applies what you accept.
5. Writes every change to a journal so it can undo.

A dialog reports the quality contract, render intent, how many video frames were checked, and how many appearance-risk levers were withheld.

### Automatic visual guard

On **Preserve Look**, this is on by default.

For each group of changes it renders a small before/after. If the picture drifted past the quality contract, that group is **rolled back immediately**. You will see a line like `Visual guard: N accepted · M rolled back`.

This is a conservative screen, not a substitute for checking an important shot at full resolution.

### Revert SceneQuant Changes

Puts the scene back to how it was before SceneQuant touched it.

---

## Extra panels (closed by default)

You do not need these for the 30-second path. They are there when you want control.

### Analyze

- **Frame Samples** — how many frames to sample for camera coverage (default 5).
- **Analyze Scene** — grades the scene and lists the top problems.
- **Export Report** — writes the last analysis out.

### VRAM

- **VRAM Budget (GB)** — your card’s total, or a ceiling you set. 0 means unset. Do not subtract a reserve yourself; the planner already holds headroom.
- **Detect VRAM** (memory icon) — fills the budget from the GPU.
- **Fit to VRAM Budget** — only when you are over budget. This is **not** what the 41 / 52 / 62% plates measure. Preserve Look does not auto-run this.
- **Pre-flight VRAM Check** — before each render, warn if the last Analyze estimate will not fit. Run Analyze first to arm it.

### Manual

- **Auto / Manual** — Auto previews the selected contract. Manual lets you pick classes, then confirm.
- **Measure sample floor** — render a low-res ladder before lowering samples. Video checks multiple frames.
- **Dead work** / **Path settings** — only in Manual. Off-screen leftover work, or bounce/clamp/light-tree/caustics/volume paths.
- **Knee** — Probe Sample Knee by itself.
- **Verify** — render a before/after check and report the delta.
- **Merge Duplicate Data** — datablock dedup.
- **Keep Reflections** + **Trim Off-screen & Distant** — hide work the camera cannot see. With Keep Reflections on, trimmed objects still show in mirrors and glass.
- **Quality Factor** / **Min Texture Size** / **Quantize Textures** — downscale textures the camera does not need. Hero/Keep images are skipped.
- **Draft Mode** — temporary draft render settings. Toggle off when done.
- **Enable Camera Cull (opt-in)** — Cycles camera cull flags. Opt-in, not the default click.
- **Mark Hero / Mark Exclude / Clear Override** — protect selected objects (see below).

### Tune

- **Lossless** / **Perceptually Safe** — which Auto-Tune tiers to apply.
- **Auto-Tune Settings** — apply those tiers. Not part of Preserve Look.

### Safety

- A count of recorded changes, grouped by tag, each with **Revert**.
- **Revert All Changes** — same as the main revert button.
- **Purge Backups (permanent)** — deletes backup copies. Cannot undo.
- **Recover Journal** — if the in-file journal is empty but a sidecar still exists beside the `.blend`.

---

## Protect a hero object or a texture

**Object Properties → SceneQuant** (on the selected object):

- **Auto** — SceneQuant may optimize from camera coverage.
- **Hero** — never reduce this object’s textures or ray visibility.
- **Exclude** — never touch this object at all.

**Image Editor → SceneQuant** (when an image is open):

- **Auto** — may quantize from coverage.
- **Keep** — never downscale or replace this image.

---

## Proof (two files, one laptop)

Timed cold, factory-startup, persistent data off.

**Machine:** RTX 2080 Super Max-Q 8 GB · i7-10875H · 16 GB · Windows 11 · Cycles OptiX

| Scene | Blender | Res | spp | Before | After | Cut |
| --- | --- | --- | --- | --- | --- | --- |
| Classroom (Christophe Seux) | 4.5.5 LTS | 1920×1080 | 300 | 2:43 | 1:35 | **41%** |
| loft.blend | 4.5.5 LTS | 1080×1350 | 512 | 5:37 | 2:41 | **52%** |
| loft.blend | 5.1.2 | 1080×1350 | 512 | 5:50 | 2:12 | **62%** |

loft was timed at 100% (the native file is 250%). These plates used the older **Aggressive** stack. They are not a Preserve Look promise, and they are not a promise for every file. A scene that is already tuned may only move a little.

![Classroom — 2:43 to 1:35, 41%](docs/proof/classroom-pair.jpg)

![loft.blend — 5:37 to 2:41, 52%](docs/proof/loft-pair.jpg)

![loft on Blender 5.1.2 — 5:50 to 2:12, 62%](docs/proof/loft-51-pair.jpg)

---

## Honest limits

- Cycles only, and a camera is required for Analyze & Preview.
- Preserve Look is a policy plus a visual guard, not pixel-identity on every GPU.
- Check important shots at full resolution before a long sequence.
- Fit to Budget is a separate VRAM tool.
- Draft, Fast GI, and resolution tricks are **not** in the default click.

---

## License

GPL-3.0-or-later. See [`LICENSE`](LICENSE).
