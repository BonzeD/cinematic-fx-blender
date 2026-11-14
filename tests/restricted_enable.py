"""Regression for Blender's restricted data during legacy add-on registration.

The standalone bpy wheel has a separate module wrapper from Blender's
embedded Python. Point the real RestrictBlend helper to the wrapper seen by
this add-on, so registration actually receives _RestrictData as in Blender.
"""
import os,sys,bpy,addon_utils,_bpy_restrict_state
root=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0,root)
_bpy_restrict_state._bpy = bpy
errors=[]
addon=addon_utils.enable('cinematic_fx', handle_error=errors.append)
assert addon is not None, [(type(e).__name__,str(e)) for e in errors]
assert not errors
assert bpy.app.timers.is_registered(addon.migrate_after_enable)
# If Blender has not released data yet, the timer retries instead of crashing.
original_data=bpy.data
try:
    bpy.data=object()
    assert addon.migrate_after_enable()==0.1
finally:
    bpy.data=original_data
# Fresh projects still install and disable safely after the restriction ends.
assert bpy.ops.cinematic_fx.install() == {'FINISHED'}
settings=bpy.context.scene.cinematic_fx
fx=next(e for e in bpy.context.scene.compositor_effects if e.node_group==settings.node_group)
assert fx.enable_for_preview is False
assert addon.migrate_after_enable() is None
addon_utils.disable('cinematic_fx',handle_error=errors.append)
assert not errors
assert not bpy.app.timers.is_registered(addon.migrate_after_enable)
print('CFX RESTRICTED ENABLE TEST PASSED')
