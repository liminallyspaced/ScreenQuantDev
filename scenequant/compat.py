# Version compatibility layer. ALL Blender-version divergence lives here.
# Rule: RNA attribute access only — never dict-style id['prop'] access (broke in 5.0).

import bpy

BLENDER_5 = bpy.app.version >= (5, 0, 0)
BLENDER_52 = bpy.app.version >= (5, 2, 0)


def has(owner, prop_name):
    return hasattr(owner, prop_name)


def supports_half_precision():
    """Image.use_half_precision exists broadly but is Cycles-effective only <= 5.1."""
    return not BLENDER_52 and "use_half_precision" in bpy.types.Image.bl_rna.properties


def is_linked(datablock):
    """Library-linked AND library-override datablocks are off-limits: linked data
    is read-only, and writes into overrides break on library reload."""
    if getattr(datablock, "library", None) is not None:
        return True
    return getattr(datablock, "override_library", None) is not None
