"""Preview defaults, one-time migration, and stable graph updates in Blender 5.3."""
import os,sys,tempfile,bpy
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cinematic_fx as addon
addon.register();scene=bpy.context.scene
# Existing unrelated effects are never modified by migration.
other=scene.compositor_effects.new('Other user effect');other.enable_for_preview=True
assert bpy.ops.cinematic_fx.install() == {'FINISHED'}
s=scene.cinematic_fx; t=s.node_group
fx=next(e for e in scene.compositor_effects if e.node_group==t)
assert fx.enable_for_preview is False and fx.enable_for_render is True
assert other.enable_for_preview is True
s.builtin_preset='FAN';bpy.ops.cinematic_fx.use_preset()
assert s.source_type=='TEXTURE'
mask=t.nodes['CFX Texture Scene Mask']
assert t.nodes['Sun Beams'].inputs['Image'].links[0].from_node==mask
# Repeated no-change updates must not replace graph links.
old={link.as_pointer() for link in t.links}
for i in range(10): addon.update_settings(s,None)
assert {link.as_pointer() for link in t.links} == old
# Emulate a legacy 1.2 project, with preview on and texture as a standalone image.
del t['cfx_safe_preview_version'];t.nodes.remove(mask)
addon.link(t,t.nodes['Custom Texture Gain'],'Image',t.nodes['Sun Beams'],'Image')
fx.enable_for_preview=True
path=os.path.join(tempfile.gettempdir(),'cfx-old-project-migration.blend')
bpy.ops.wm.save_as_mainfile(filepath=path);bpy.ops.wm.open_mainfile(filepath=path)
scene=bpy.context.scene;s=scene.cinematic_fx;t=s.node_group
fx=next(e for e in scene.compositor_effects if e.node_group==t)
assert fx.enable_for_preview is False and fx.enable_for_render is True
assert t.get('cfx_safe_preview_version')==1
assert t.nodes['Sun Beams'].inputs['Image'].links[0].from_node.name=='CFX Texture Scene Mask'
assert scene.compositor_effects.get('Other user effect').enable_for_preview is True
# Explicit opt-in after migration is retained across saving and reopening.
fx.enable_for_preview=True
bpy.ops.wm.save_as_mainfile(filepath=path);bpy.ops.wm.open_mainfile(filepath=path)
scene=bpy.context.scene;t=scene.cinematic_fx.node_group
assert next(e for e in scene.compositor_effects if e.node_group==t).enable_for_preview is True
# Enabling the upgraded add-on with an already open old project also migrates it.
fx=next(e for e in scene.compositor_effects if e.node_group==t)
del t['cfx_safe_preview_version']; fx.enable_for_preview=True
addon.unregister(); addon.register()
assert bpy.app.timers.is_registered(addon.migrate_after_enable)
addon.migrate_after_enable()  # Standalone bpy has no interactive event loop.
scene=bpy.context.scene;t=scene.cinematic_fx.node_group
fx=next(e for e in scene.compositor_effects if e.node_group==t)
assert fx.enable_for_preview is False and t.get('cfx_safe_preview_version') == 1
print('CFX VIEWPORT SAFETY TEST PASSED')
