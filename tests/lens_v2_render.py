"""Real CPU EXR renders: moving source/ghost, occlusion, colors and no phantom."""
import os,sys,math
import bpy
from mathutils import Vector
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cinematic_fx as a
a.register(); s=bpy.context.scene
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
s.render.engine='CYCLES'; s.render.compositor_device='CPU'; s.cycles.device='CPU'; s.cycles.samples=1
s.render.resolution_x=96; s.render.resolution_y=64; s.render.resolution_percentage=100
s.render.image_settings.file_format='OPEN_EXR'; s.render.image_settings.color_mode='RGBA'; s.render.image_settings.color_depth='32'
s.world.color=(0,0,0); s.world.use_nodes=True; s.world.node_tree.nodes['Background'].inputs['Color'].default_value=(0,0,0,1)
bpy.ops.object.camera_add(location=(0,0,10)); s.camera=bpy.context.object
s.camera.data.type='PERSP'; s.camera.data.lens=35
bpy.ops.object.light_add(type='POINT',location=(1,0,0)); light=bpy.context.object; light.data.energy=1
assert bpy.ops.cinematic_fx.install()=={'FINISHED'}; c=s.cinematic_fx
assert not next(e for e in s.compositor_effects if e.node_group==c.node_group).enable_for_preview
bpy.ops.object.select_all(action='DESELECT'); light.select_set(True); bpy.context.view_layer.objects.active=light
assert bpy.ops.cinematic_fx.add_selected()=={'FINISHED'}
c.bloom_strength=0; c.ray_layer_count=1; layer=c.ray_layers[0]; layer.preset='HALO_FILLED'; layer.size=0.12; layer.color=(1,0,0,1); layer.intensity=1; c.opacity=1

def render(name):
 s.render.filepath='/tmp/cfxv2-'+name+'.exr'; bpy.ops.render.render(write_still=True)
 image=bpy.data.images.load(s.render.filepath, check_existing=False); pixels=list(image.pixels[:]); bpy.data.images.remove(image); return pixels

def stats(p):
 W,H=s.render.resolution_x,s.render.resolution_y; items=[(p[4*(y*W+x)],x,y) for y in range(H) for x in range(W)]; total=sum(v for v,x,y in items)
 return (total, sum(v*x for v,x,y in items)/max(total,1e-9),sum(v*y for v,x,y in items)/max(total,1e-9),sum(p[i+1] for i in range(0,len(p),4)),sum(p[i+2] for i in range(0,len(p),4)))
base=render('source'); print('SOURCE',stats(base))
assert stats(base)[0]>1
assert stats(base)[1]>49, stats(base)
light.location.x=-1; bpy.context.view_layer.update(); moved=render('moved'); print('MOVED',stats(moved)); assert stats(moved)[1] < stats(base)[1]-4
layer.role='GHOST'; layer.axis_position=2; ghost=render('ghost'); print('GHOST',stats(ghost)); assert stats(ghost)[1] > stats(moved)[1]+4
layer.color=(0,0,1,1); blue=render('blue'); print('BLUE',stats(blue)); assert stats(blue)[4]>1 and stats(blue)[0]<0.01
layer.color=(1,0,0,1); layer.role='SOURCE'
bpy.ops.mesh.primitive_cube_add(size=2,location=(-0.5,0,5)); blocker=bpy.context.object
blocked=render('blocked'); print('BLOCKED',stats(blocked)); assert stats(blocked)[0] < 0.01
blocker.location=(20,0,5); bpy.context.view_layer.update(); unblocked=render('unblocked'); print('UNBLOCKED',stats(unblocked)); assert stats(unblocked)[0]>1
c.emitters[0].enabled=False; none=render('none'); print('NONE',stats(none)); assert stats(none)[0]<0.01

# Screen mask affects the flare, not the original image.
c.emitters[0].enabled=True
mask=bpy.data.images.new('test black mask', width=4, height=4, alpha=True)
mask.pixels[:]=[0.0,0.0,0.0,1.0]*16; mask.update()
c.lens_mask=True; c.lens_mask_image=mask
masked=render('masked'); print('MASKED',stats(masked)); assert stats(masked)[0]<0.01
c.lens_mask=False
# Editing a ramp in the tree is synchronized to every source at render time.
layer.use_gradient=True
ramp=c.node_group.nodes['Layer Gradient 0'].color_ramp
for e in ramp.elements: e.color=(0,1,0,1)
layer.color=(1,1,1,1)
green=render('gradient'); print('GRADIENT',stats(green)); assert stats(green)[3]>1 and stats(green)[0]<0.01
layer.use_gradient=False
# Multiple independent layers must change the result and preserve custom settings.
c.ray_layer_count=3
c.ray_layers[1].preset='ANAMORPHIC'; c.ray_layers[1].color=(0,0,1,1)
c.ray_layers[1].intensity=0.5; c.ray_layers[2].enabled=False
many=render('multi'); assert stats(many)[4]>0.1
# A disabled source and non-zero base: no blend mode should darken the background.
c.emitters[0].enabled=False
s.world.node_tree.nodes['Background'].inputs['Color'].default_value=(0.25,0.25,0.25,1)
for mode in ('ADD','SCREEN','MIX'):
 c.blend_mode=mode; without=render('without-'+mode)
 effect=next(e for e in s.compositor_effects if e.node_group==c.node_group); effect.enable_for_render=False
 original=render('original-'+mode); effect.enable_for_render=True
 assert max(abs(x-y) for x,y in zip(without,original))<1e-5,mode
# MIX must not darken the background away from an enabled flare.
c.blend_mode='MIX'; c.emitters[0].enabled=True; mixed=render('mix')
assert max(abs(mixed[k]-original[k]) for k in (0,1,2))<1e-4
# The effect keeps the original alpha for all blend modes.
s.render.film_transparent=True
for mode in ('ADD','SCREEN','MIX'):
 c.blend_mode=mode; after=render('alpha-'+mode)
 effect.enable_for_render=False; before=render('alpha-base-'+mode); effect.enable_for_render=True
 assert max(abs(x-y) for x,y in zip(after[3::4],before[3::4]))<1e-5
# Disabled / offscreen / behind camera / zero energy are not phantom sources.
c.bloom_strength=0; c.blend_mode='ADD'; s.render.film_transparent=False
light.data.energy=0; bpy.context.view_layer.update(); assert a.emitter_projection(s,c.emitters[0],bpy.context.evaluated_depsgraph_get()) is None
light.data.energy=1; light.location=(100,0,0); bpy.context.view_layer.update(); assert a.emitter_projection(s,c.emitters[0],bpy.context.evaluated_depsgraph_get()) is None
light.location=(0,0,20); bpy.context.view_layer.update(); assert a.emitter_projection(s,c.emitters[0],bpy.context.evaluated_depsgraph_get()) is None
# Render-time refresh follows animated source even with viewport preview off.
s.world.node_tree.nodes['Background'].inputs['Color'].default_value=(0,0,0,1)
c.ray_layer_count=1; c.blend_mode='ADD'; c.emitters[0].occlusion=False
layer.color=(1,0,0,1); layer.role='SOURCE'
light.location=(-1,0,0); light.keyframe_insert(data_path='location',frame=1)
light.location=(1,0,0); light.keyframe_insert(data_path='location',frame=2)
s.frame_set(1); f1=render('frame1'); s.frame_set(2); f2=render('frame2')
print('ANIMATED',stats(f1),stats(f2)); assert stats(f2)[1]>stats(f1)[1]+4
# Moving the camera also changes the apparent position.
s.camera.location.x=1; bpy.context.view_layer.update(); camera_moved=render('camera-moved')
assert stats(camera_moved)[1]<stats(f2)[1]-4
print('LENS V2 RENDER TEST PASSED')
