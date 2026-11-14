"""Install + auto-enable ZIP under restricted Blender data.

Use a NEW empty BLENDER_USER_SCRIPTS directory when invoking this test; the
installer writes into its addons folder. It refuses to overwrite the add-on.
"""
import os,sys,tempfile,zipfile
import bpy,addon_utils,_bpy_restrict_state
scripts=os.environ.get('BLENDER_USER_SCRIPTS')
assert scripts and os.path.isabs(scripts), 'Set BLENDER_USER_SCRIPTS to a new empty absolute directory'
target=os.path.join(scripts,'addons','cinematic_fx.py')
assert not os.path.exists(target), 'Choose a new empty BLENDER_USER_SCRIPTS directory'
source=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'cinematic_fx.py')
# Match embedded Blender's restricted wrapper; standalone bpy may expose two modules.
_bpy_restrict_state._bpy=bpy
with tempfile.TemporaryDirectory() as tmp:
    archive=os.path.join(tmp,'cinematic_fx.zip')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as out:
        out.write(source,'cinematic_fx.py')
    assert bpy.ops.preferences.addon_install(filepath=archive,overwrite=True,enable_on_install=True)=={'FINISHED'}
    addon=sys.modules['cinematic_fx']
    assert os.path.realpath(addon.__file__)==os.path.realpath(target)
    assert addon.__addon_enabled__ and bpy.app.timers.is_registered(addon.migrate_after_enable)
    assert bpy.ops.cinematic_fx.install()=={'FINISHED'}
    assert bpy.ops.preferences.addon_disable(module='cinematic_fx')=={'FINISHED'}
    assert not bpy.app.timers.is_registered(addon.migrate_after_enable)
print('CFX RESTRICTED ZIP AUTO-ENABLE TEST PASSED')
