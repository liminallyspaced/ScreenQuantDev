# QuantTrace (SIDECAR): experimental second RenderEngine.
# Make it Fast stays on stock Cycles. This package only registers the stub.
# See docs/research/SIDECAR-INTEGRATOR.md.

from . import engine

ENGINE_ID = engine.ENGINE_ID
ENGINE_LABEL = engine.ENGINE_LABEL


def register():
    engine.register()


def unregister():
    engine.unregister()
