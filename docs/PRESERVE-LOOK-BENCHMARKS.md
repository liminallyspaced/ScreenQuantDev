# Preserve Look benchmark protocol

This lane measures the default product contract separately from the historical
Aggressive proof plates. A result is publishable only when it comes from the
named physical machine and the exact `.blend` identified by SHA-256.

## Required two runs

1. **Low-end machine fixture:** run a representative Cycles animation scene on
   the actual low-end CPU/GPU we want to support. Do not label a throttled
   high-end computer or a CPU-only run as low-end hardware.
2. **User problem scene:** run the user's original scene without manually
   simplifying it first. Keep their renderer, denoiser, compositor, resolution,
   color management and output frame range intact.

Run from PowerShell:

```powershell
pwsh -NoProfile -File bench/run_preserve_look.ps1 `
  -BlenderExe 'C:\Program Files\Blender Foundation\Blender 4.5\blender.exe' `
  -BlendFile 'D:\scenes\problem.blend' `
  -Output 'D:\results\problem-preserve-look.json' `
  -Label 'user-problem-scene' `
  -Repeats 2
```

The runner does not save the `.blend`. It benchmarks full-resolution renders
before and after SceneQuant in one isolated background process and writes:

- physical machine, Blender and Cycles-device inventory;
- scene path, SHA-256, resolution and representative frames;
- per-frame baseline/optimized timings and sequence medians;
- optimization overhead and the number of sequences needed to break even;
- per-frame mean, p95 and max scene-linear RGB delta;
- adjacent-frame temporal residuals to catch smearing, crawling or flicker;
- every planned action and the automatic visual guard's accepted/rolled-back
  groups.

## Acceptance gate

For Video, every representative frame must remain at or below mean `0.002` and
p95 `0.008` scene-linear RGB delta. Every adjacent-frame temporal residual must
meet the same limits. Max delta is diagnostic only so one firefly cannot reject
an otherwise stable render. The operator and automatic guard must finish without
an error, and the optimized representative sequence must be faster than the
baseline. Any failed operational, timing, frame or temporal gate makes the
result `FAIL`.

Do not publish a speed percentage until both required runs exist and pass. Keep
the two result files separate: a low-end fixture does not substitute for the
user's problem scene, and the problem scene does not prove low-end behavior.
