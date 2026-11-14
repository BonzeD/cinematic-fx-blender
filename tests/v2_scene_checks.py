"""Blender 5.3 scene ownership, projection, legacy upgrade and persistence checks."""
import bpy,sys,os,math
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cinematic_fx as a
a.register(); s=bpy.context.scene; c=s.cinematic_fx
assert bpy.ops.cinematic_fx.install()=={'FINISHED'}
assert len(c.ray_layers)==3 and len(bpy.data.images)>=3
s.camera.location=(0,0,10); s.camera.rotation_euler=(0,0,0)
light=bpy.data.objects['Light']; light.location=(0,0,0); e=c.emitters.add(); e.object=light
a.refresh(s,c,force_rebuild=True); assert not c.last_error
assert c.node_group.nodes.get('Lens Mix 0 2')
# Missing managed nodes are rebuilt without deleting editable gradients.
custom_ramp=c.node_group.nodes['Layer Gradient 0']; custom_ramp.color_ramp.elements[0].color=(1,0,0,1)
c.node_group.nodes.remove(c.node_group.nodes['Lens Softness 0 0'])
a.refresh(s,c,force_rebuild=True)
assert c.node_group.nodes.get('Lens Softness 0 0') and custom_ramp.color_ramp.elements[0].color[0]==1
# Frame offsets, source disable and camera moves are reflected in the graph.
old=c.node_group; e.enabled=False
assert a.socket(old.nodes['Lens Mix 0 0'].inputs,'Factor_Float').default_value==0
e.enabled=True; e.occlusion=False
bpy.context.view_layer.update(); assert a.emitter_projection(s,e,bpy.context.evaluated_depsgraph_get()) is not None
# An orthographic camera casts parallel occlusion rays rather than center rays.
s.camera.data.type='ORTHO'; a.refresh(s,c,force_rebuild=True)
assert a.emitter_projection(s,e,bpy.context.evaluated_depsgraph_get()) is not None
# Directional lights have a position only for perspective cameras.
light.data.type='SUN'; assert a.emitter_projection(s,e,bpy.context.evaluated_depsgraph_get()) is None
s.camera.data.type='PERSP'; light.rotation_euler=(0,math.pi,0); bpy.context.view_layer.update()
assert a.emitter_projection(s,e,bpy.context.evaluated_depsgraph_get()) is not None
light.rotation_euler=(0,0,0); bpy.context.view_layer.update()
assert a.emitter_projection(s,e,bpy.context.evaluated_depsgraph_get()) is None
# Every bundled texture can be generated and packed.
for preset,_,_ in a.PRESETS:
 image=a.preset_image(preset, 64); assert image.packed_file and len(image.pixels)>0
# Multi-scene ownership: sharing a group then editing another scene isolates it.
other=s.copy(); other.name='CFX Second Scene'
assert other.cinematic_fx.node_group == old
a.refresh(other,other.cinematic_fx,force_rebuild=True)
assert not other.cinematic_fx.last_error, other.cinematic_fx.last_error
assert other.cinematic_fx.node_group != old
assert s.cinematic_fx.node_group == old
# Legacy effect: upgrade does not delete it or corrupt its layers and sources.
legacy=bpy.data.node_groups.new('Legacy Test','CompositorNodeTree')
legacy.interface.new_socket(name='Image',in_out='INPUT',socket_type='NodeSocketColor')
legacy.interface.new_socket(name='Image',in_out='OUTPUT',socket_type='NodeSocketColor')
fx=other.compositor_effects.new('Legacy Test'); fx.node_group=legacy; fx.enable_for_preview=True; fx.enable_for_render=True
other.cinematic_fx.node_group=legacy
a.migrate_on_load(None); assert not fx.enable_for_preview and fx.enable_for_render
# Activate scene so the operator runs in the intended scene.
bpy.context.window.scene=other
assert bpy.ops.cinematic_fx.install()=={'FINISHED'}
assert fx.node_group==legacy and not fx.enable_for_preview and not fx.enable_for_render
assert len(other.cinematic_fx.emitters)==1 and len(other.cinematic_fx.ray_layers)>=3
# Opening an actual .blend keeps the graph, layers and assigned source.
bpy.ops.wm.save_as_mainfile(filepath='/tmp/cfx-v2-persistence.blend')
bpy.ops.wm.open_mainfile(filepath='/tmp/cfx-v2-persistence.blend')
c=bpy.context.scene.cinematic_fx
assert a.is_v2(c.node_group) and len(c.emitters)==1 and c.emitters[0].object
assert c.ray_layers[0].image and c.ray_layers[0].image.packed_file
print('CFX V2 SCENE CHECKS PASSED')
