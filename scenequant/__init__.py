# SceneQuant — analysis-driven, camera-aware, reversible scene optimization.
# Registration plus the render pre-flight VRAM check; all other logic lives in
# the submodules.

import logging

import bpy
from bpy.app.handlers import persistent

from . import journal, props
from .ui import operators, panels

logger = logging.getLogger("scenequant")

MB_PER_GB = 1024.0
# Registration order; unregister and rollback walk it in reverse.
_MODULES = (props, journal, operators, panels)


def _preflight_threshold_mb(settings):
    """Usable VRAM in MB, or None when no budget is set or the threshold cannot
    be computed. vram_budget_gb is PHYSICAL VRAM; effective_budget_threshold_mb
    is the one place the reserve is applied, so this must never scale the budget
    itself (see constants.BUDGET_HEADROOM). Failing to None disarms the check
    rather than warning against a threshold we do not trust."""
    budget_mb = settings.vram_budget_gb * MB_PER_GB
    if budget_mb <= 0.0:
        return None
    from .analysis import memory_model
    try:
        return memory_model.effective_budget_threshold_mb(budget_mb)
    except Exception:
        logger.exception("SceneQuant pre-flight: budget threshold failed")
        return None


@persistent
def _preflight_render_init(scene, *_args):
    """Warn BEFORE the render when the last Analyze estimate exceeds the usable
    VRAM budget — the silent spill-to-system-memory slowdown is exactly what
    SceneQuant exists to prevent.

    This runs on the render job's thread at every F12, so it is read-only and
    cheap by contract: no depsgraph evaluation, no scene walk, no RNA write and
    no popup. The stored report is the only input; without one the check stays
    silent (the panel says to run Analyze to arm it). Storing the warning for
    the panel is handed to a main-thread timer. Fully guarded: a pre-flight
    failure never breaks a render.
    """
    try:
        settings = getattr(scene, "scenequant", None)
        if settings is None:
            return
        if not settings.preflight_enabled:
            _defer_warning(scene, "")
            return
        threshold_mb = _preflight_threshold_mb(settings)
        if not threshold_mb:
            _defer_warning(scene, "")
            return
        estimate_mb = panels.report_estimate_mb(scene)
        if estimate_mb is None:
            return  # never analyzed: nothing to compare against
        if estimate_mb <= threshold_mb:
            _defer_warning(scene, "")
            return
        message = (
            f"estimated {estimate_mb:.0f} MB (last Analyze) exceeds the usable "
            f"{threshold_mb:.0f} MB VRAM budget — the render may spill to "
            "system memory. Run Fit to Budget first."
        )
        print(f"[SceneQuant] Pre-flight: scene '{scene.name}' {message}")
        _defer_warning(scene, message)
    except Exception:
        logger.exception("SceneQuant pre-flight check failed (render continues)")


def _defer_warning(scene, message):
    """Hand the preflight_warning write to the main thread: RNA writes from the
    render job's thread are not safe. The scene can be deleted (or the addon
    unregistered) before the timer fires, so the write is fully guarded."""
    scene_name = scene.name

    def store():
        try:
            target = bpy.data.scenes.get(scene_name)
            settings = getattr(target, "scenequant", None) if target else None
            if settings is not None and settings.preflight_warning != message:
                settings.preflight_warning = message
        except Exception:
            logger.exception("SceneQuant pre-flight could not store its warning")
        return None  # one shot

    try:
        bpy.app.timers.register(store, first_interval=0.0)
    except Exception:
        logger.exception("SceneQuant pre-flight could not schedule its warning")


def register():
    registered = []
    try:
        for module in _MODULES:
            module.register()
            registered.append(module)
        if _preflight_render_init not in bpy.app.handlers.render_init:
            bpy.app.handlers.render_init.append(_preflight_render_init)
    except Exception:
        # A half-registered addon leaves unregister() permanently broken (the
        # first group to fail aborts the rest, leaking handlers and classes).
        for module in reversed(registered):
            try:
                module.unregister()
            except Exception:
                logger.exception("SceneQuant registration rollback failed for %s",
                                 module.__name__)
        raise


def unregister():
    errors = []
    try:
        if _preflight_render_init in bpy.app.handlers.render_init:
            bpy.app.handlers.render_init.remove(_preflight_render_init)
    except Exception as error:
        logger.exception("SceneQuant could not remove the pre-flight handler")
        errors.append(f"render_init handler: {error}")
    # Every group gets its turn: one failing unregister must not strand the rest.
    for module in reversed(_MODULES):
        try:
            module.unregister()
        except Exception as error:
            logger.exception("SceneQuant unregister failed for %s", module.__name__)
            errors.append(f"{module.__name__}: {error}")
    if errors:
        logger.error("SceneQuant unregistered with %d error(s): %s",
                     len(errors), "; ".join(errors))
