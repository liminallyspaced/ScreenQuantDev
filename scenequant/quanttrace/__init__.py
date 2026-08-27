# QuantTrace (SIDECAR): experimental second RenderEngine.
# Make it Fast stays on stock Cycles. Slice 2e: soft POINT is_sphere + SUN strength.
# See docs/research/SIDECAR-INTEGRATOR.md.

from . import engine

ENGINE_ID = engine.ENGINE_ID
ENGINE_LABEL = engine.ENGINE_LABEL


def register():
    engine.register()


def unregister():
    engine.unregister()
