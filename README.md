# SceneQuant

**One click. Faster Cycles. Full revert.**

Free Blender addon. Press **Make it Fast** — it plans a stack of Cycles speed levers, applies them through a journal, and you can undo the whole thing.

[Download the zip](https://github.com/liminallyspaced/ScreenQuantDev/releases/latest) · [itch.io](https://liminalvisual.itch.io/scenequant) · [Gumroad](https://8139959199815.gumroad.com/l/exyxdi)

Blender 4.2+ · GPL-3.0-or-later · Author: [Nick Siegel](https://github.com/liminallyspaced)

![loft.blend — 5:37 down to 2:41, 52% faster](docs/proof/loft-pair.jpg)

## Proof, not a promise

Timed on one machine, cold pair, factory-startup, persistent data off.

**Machine:** RTX 2080 Super Max-Q 8 GB · i7-10875H · 16 GB · Windows 11 · Cycles OptiX

| Scene | Blender | Res | spp | Baseline | Make it Fast | Cut |
|---|---|---|---|---|---|---|
| Classroom (Christophe Seux) | 4.5.5 LTS | 1920×1080 | 300 | 2:43 | 1:35 | **41%** |
| loft.blend | 4.5.5 LTS | 1080×1350 | 512 | 5:37 | 2:41 | **52%** |
| loft.blend | 5.1.2 | 1080×1350 | 512 | 5:50 | 2:12 | **62%** |

loft was timed at 100% (the native file is 250%). Already-tuned scenes may only move a little. These three pairs are **not** a promise for every file.

![Classroom — 2:43 down to 1:35, 41% faster](docs/proof/classroom-pair.jpg)

![loft.blend on Blender 5.1.2 — 5:50 down to 2:12, 62% faster](docs/proof/loft-51-pair.jpg)

## What Make it Fast does

It builds a revertible speed plan for **this** scene, then applies it. The default click covers:

- Adaptive sampling and a sample-knee cap (never below a safe floor)
- OIDN / GPU denoise placement
- Bounce and clamp tightening
- Light tree, caustics, camera cull
- Dead geometry and off-screen work that still gets traced

Draft mode, Fast GI, and resolution tricks are **not** in the default click.

Everything it writes goes through a journal. **Revert All** puts the scene back.

The N-panel is one **Make it Fast** button plus Revert. Analyze, VRAM, Manual, Tune, and Safety stay closed. The click runs Analyze, then the speed stack, then Fit to Budget only if VRAM is over.

Also in the addon: Analyze, Fit to Budget (VRAM), Probe Sample Knee, Verify Render.

## Install

1. Download `scenequant-0.3.3.zip` from [Releases](https://github.com/liminallyspaced/ScreenQuantDev/releases/latest).
2. Blender → Edit → Preferences → Add-ons → Install from Disk.
3. Enable **SceneQuant — Scene & Render Optimizer**.
4. 3D Viewport → N panel → **SceneQuant** → **Make it Fast**.

Do **not** install the GitHub “Source code” zip. That is the repo, not the addon.

Once it is on [extensions.blender.org](https://extensions.blender.org/), use Get Extensions instead.

## Honest limits

- These numbers are two files on one laptop. Your file will differ.
- A scene that is already well-tuned may only move a little.
- Quality change is small on the measured pairs (MAE ~5.6–7.0 / 255), not zero.
- Fit to Budget is a separate VRAM tool. It is not what the 41 / 52 / 62% plates measure.

## License

GPL-3.0-or-later. See [`LICENSE`](LICENSE).
