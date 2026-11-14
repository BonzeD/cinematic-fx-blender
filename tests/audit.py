"""Regression audit for scenes, repair, RNA animation, errors, and cleanup."""
import os,sys,bpy
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cinematic_fx as addon
addon.register(); scene=bpy.context.scene
assert bpy.ops.cinematic_fx.install() == {'FINISHED'}
c=scene.cinematic_fx; c.source_type='LAYERS'; original=c.node_group
# Duplicate scenes must not share mutable compositor nodes.
copy=scene.copy(); cc=copy.cinematic_fx
cc.opacity=0.25
assert cc.node_group != original
assert any(effect.node_group == cc.node_group for effect in copy.compositor_effects)
assert abs(original.nodes['Mask Strength'].inputs[1].default_value-0.8)<1e-4
assert abs(cc.node_group.nodes['Mask Strength'].inputs[1].default_value-0.25)<1e-4
# Changing one copied scene's color must not touch the first.
cc.primary_color=(0.2,0.3,0.4,1)
assert tuple(round(v,2) for v in original.nodes['Ray Color Gradient'].color_ramp.elements[-1].color)==(1.0,0.9,0.8,1.0)
# Older groups without alpha nodes are repaired in place.
original.nodes.remove(original.nodes['CFX Original Alpha']); c.opacity=0.7
assert original.nodes.get('CFX Original Alpha') and original.nodes.get('CFX Preserve Alpha')
# A removed managed node is rebuilt; no user data outside the group is changed.
original.nodes.remove(original.nodes['CFX Layer Tint 0 1']); c.opacity=0.6
assert original.nodes.get('CFX Layer Tint 0 1') and not c.last_error
# An unrecoverable user edit is visible to the UI, not silently swallowed.
n=original.nodes.get('Ray Clarity'); original.nodes.remove(n); c.opacity=0.5
assert 'Ray Clarity' in c.last_error
# Restore the test node and the error should clear.
n=addon.node(original,'CompositorNodeColorCorrection','Ray Clarity',900,600)
addon.link(original,original.nodes['Tint Rays'],'Result_Color',n,'Image')
addon.link(original,n,'Image',original.nodes['Edge Smoothness'],'Image')
c.opacity=0.55; assert not c.last_error
# Animation RNA evaluation must update the nodes even without property callbacks.
c.opacity=0.1;c.keyframe_insert(data_path='opacity',frame=1)
c.opacity=0.9;c.keyframe_insert(data_path='opacity',frame=5)
c.emitter_strength=2;c.keyframe_insert(data_path='emitter_strength',frame=1)
c.emitter_strength=9;c.keyframe_insert(data_path='emitter_strength',frame=5)
l=c.ray_layers[0];l.size=0.2;l.keyframe_insert(data_path='size',frame=1)
l.size=0.7;l.keyframe_insert(data_path='size',frame=5)
for f,opacity,strength,size in [(1,.1,2,.2),(5,.9,9,.7)]:
 scene.frame_set(f)
 assert abs(original.nodes['Mask Strength'].inputs[1].default_value-opacity)<1e-4
 assert abs(original.nodes['CFX Emitter Strength'].inputs['Master Gain'].default_value-strength)<1e-4
 assert abs(original.nodes['CFX Layer Transform 0 0'].inputs['Scale'].default_value-size)<1e-4
# Unchanged color properties must not overwrite manual color-ramp edits each frame.
ramp=original.nodes['Ray Color Gradient'].color_ramp
ramp.elements[0].color=(.3,.4,.5,1);scene.frame_set(2)
assert tuple(round(v,2) for v in ramp.elements[0].color)==(.3,.4,.5,1.0)
# Keyframed color settings reach the gradient at the matching frame.
c.primary_color=(1,0,0,1);c.keyframe_insert(data_path='primary_color',frame=1)
c.primary_color=(0,0,1,1);c.keyframe_insert(data_path='primary_color',frame=5)
scene.frame_set(1); assert tuple(round(v,2) for v in ramp.elements[-1].color)==(1,0,0,1)
scene.frame_set(5); assert tuple(round(v,2) for v in ramp.elements[-1].color)==(0,0,1,1)
# Registry and handlers cleanly unregister.
addon.unregister()
assert addon.update_frame_handler not in bpy.app.handlers.frame_change_post
assert addon.refresh_emitters_handler not in bpy.app.handlers.depsgraph_update_post
print('CFX AUDIT TEST PASSED')
