"""CPU renders for independent colored textured rays (Blender 5.3)."""
import os,sys
import bpy
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cinematic_fx as addon
addon.register(); s=bpy.context.scene
s.render.engine='CYCLES'; s.render.compositor_device='CPU'; s.cycles.device='CPU'; s.cycles.samples=1
s.render.resolution_x=64; s.render.resolution_y=64; s.render.resolution_percentage=100
s.render.image_settings.file_format='OPEN_EXR'; s.render.image_settings.color_mode='RGBA'; s.render.image_settings.color_depth='32'
bpy.ops.cinematic_fx.install(); c=s.cinematic_fx
c.source_type='LAYERS'; c.opacity=1; c.volumetric_density=1; c.threshold=0.2
c.ray_strength=2; c.glow_strength=2; c.emitter_strength=10; c.edge_smoothness=0
c.primary_color=(1,1,1,1); c.secondary_color=(1,1,1,1)
for i,(preset,size,color) in enumerate([('HEXAGON_FILLED',0.7,(1,0.1,0.1,1)),('STAR6_FILLED',0.4,(0.1,1,0.1,1)),('PETALS',0.25,(0.1,0.1,1,1))]):
 layer=c.ray_layers[i]; layer.preset=preset; layer.size=size; layer.color=color; layer.offset=(i*0.08,0)

def render(name):
 p='/tmp/cfx-layer-'+name+'.exr'; s.render.filepath=p; bpy.ops.render.render(write_still=True)
 image=bpy.data.images.load(p); return list(image.pixels[:])

def delta(a,b): return sum(abs(x-y) for x,y in zip(a,b))
all_three=render('three')
c.ray_layers[1].enabled=False; c.ray_layers[2].enabled=False
one=render('one')
print('THREE VS ONE:',delta(all_three,one)); assert delta(all_three,one)>1
c.ray_layers[0].color=(0.1,0.1,1.0,1.0)
blue=render('blue')
print('RED VS BLUE:',delta(one,blue)); assert delta(one,blue)>1
c.ray_layers[0].size=0.3
small=render('small')
print('LARGE VS SMALL:',delta(blue,small)); assert delta(blue,small)>1
# Same layer stack follows a scene object, not only the centered mode.
c.source_type='OBJECTS'; entry=c.emitters.add(); entry.object=bpy.data.objects['Cube']; c.emitter_use_layers=True
c.ray_layers[1].enabled=True; c.ray_layers[2].enabled=True
objects=render('objects')
entry.enabled=False
noobjects=render('noobjects')
print('OBJECT LAYERS VS NONE:',delta(objects,noobjects)); assert delta(objects,noobjects)>1
print('CFX LAYER RENDER TEST PASSED')
