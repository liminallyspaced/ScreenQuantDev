# SceneQuant

Free Blender addon. One button, **Make it Fast**, cuts Cycles render time. Everything it changes is revertible.

Author: [Nick Siegel](https://github.com/liminallyspaced) · Blender 4.2+ · GPL-3.0-or-later

## Install

1. Download `scenequant-0.3.0.zip` from [Releases](https://github.com/liminallyspaced/ScreenQuantDev/releases).
2. Blender → Edit → Preferences → Add-ons → Install from Disk.
3. Enable **SceneQuant — Scene & Render Optimizer**.

Once it is on [extensions.blender.org](https://extensions.blender.org/), use Get Extensions instead.

Do not install the GitHub “Source code” zip. Use the Release asset.

## What the click does

Make it Fast plans a stack of Cycles speed levers (adaptive sampling, OIDN, bounces, light tree, caustics, camera cull, dead geometry, GPU denoise) and applies them through a journal. You can revert all of it.

Also in the addon: Analyze, Fit to Budget (VRAM), Probe Sample Knee, Verify Render, Revert All.

Draft / Fast GI / resolution tricks are not in the default click.

## Timed on my machine

RTX 2080 Super Max-Q 8 GB · i7-10875H · 16 GB · Windows 11 · Blender 4.5.5 LTS · Cycles OptiX · factory-startup · persistent data off.

| Scene | Res | spp | Baseline | Make it Fast | Cut |
|---|---|---|---|---|---|
| Classroom (Christophe Seux) | 1920×1080 | 300 | 2:43 | 1:35 | 41% |
| loft.blend | 1080×1350 | 512 | 5:37 | 2:41 | 52% |

loft was timed at 100% (the native file is 250%). Already-tuned scenes may only move a little. These two pairs are not a promise for every file.

## License

GPL-3.0-or-later. See `scenequant/LICENSE`.
