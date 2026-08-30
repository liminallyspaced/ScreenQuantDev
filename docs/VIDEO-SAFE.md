# Preserve Look / Video Safe contract

SceneQuant's default job is to remove render cost without redesigning the shot.
It is not allowed to obtain a default-mode speedup by changing lights, shadows,
materials, visibility, bounce response, or the artist's denoiser choices.

## Quality contracts

### Preserve Look (default)

Allowed automatic writes are explicitly allowlisted in
`scenequant/planning/speed_solver.py`. They are limited to:

- selecting a proven GPU backend;
- persistent render data when measured VRAM headroom permits it;
- locking the interface while rendering;
- disabling deform motion blur only on objects proven not to deform;
- adaptive sampling plus a raised minimum-sample floor;
- GPU-only path-guiding no-ops;
- solid-world MIS and no-volume/homogeneous-volume no-ops;
- GPU denoiser placement without changing whether or how denoising runs; and
- GPU compositor placement.

Lowering the maximum sample count is not an ordinary plan action. It must pass
the measured sample-floor probe described below.

### Balanced

Balanced may change sampling ceilings and noise distribution. It still blocks
changes to lighting, materials, visibility, geometry, transparent shadows,
caustics, bounce/clamp response, glossy filtering, and denoiser quality.

### Aggressive

Aggressive is the explicit compatibility path for the historical tier-0/1
stack. Every action is previewed. The user owns the perceptual tradeoff.

## Video sample-floor rule

Auto render intent resolves any multi-frame output range to Video. Video:

1. samples evenly spaced frames including the first and last frame;
2. renders the sample ladder using the artist's existing denoiser choice;
3. requires both mean linear-RGB convergence and a p95 local-detail threshold;
4. rejects the entire reduction if any checked frame does not converge;
5. chooses the highest accepted knee across all checked frames; and
6. never lowers the live sample ceiling below 128 spp.

This is deliberately conservative. A three-frame probe does not prove every
frame. Important sequences still require an artist review of representative
motion, thin highlights, hair, transparency, volumetrics, and dark interiors.

## Acceptance gates for future speed levers

A new Preserve Look lever needs all of the following before it enters the
allowlist:

1. A data-driven classifier with explicit unknown/refuse states.
2. Journaled apply and verified revert behavior.
3. Linear EXR comparisons on stills and multiple animation frames.
4. Shadow, alpha-cutout, glass, small-emitter, reflection, indirect-light, and
   motion coverage where relevant.
5. A measured timing win on the hardware/scene pair being claimed.
6. No unexplained temporal crawling, flicker, or denoiser smearing.

Implementation, automated image checks, timing proof, and human acceptance are
reported separately. A reversible action is not automatically a safe action.

## Highest-value next work

- Automatically render and compare a low-resolution baseline before/after each
  candidate action group, reverting the group when its contract fails.
- Add worst-region and luminance/shadow metrics alongside mean and p95 RGB.
- Detect GPU memory pressure before render and select persistent data, GPU
  denoising, compositor placement, and tile/cache policy from real headroom.
- Benchmark Preserve Look separately from the historical aggressive proof
  plates, including CPU-only and low-VRAM systems.
- Add adjacent-frame motion fixtures for hair, alpha cards, glass, small
  emissive lights, volumetrics, and dark indirect interiors.
