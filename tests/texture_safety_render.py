"""A texture cannot create light by itself on a black scene."""
import os,sys,bpy
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cinematic_fx as addon
addon.register();s=bpy.context.scene
s.render.engine='CYCLES';s.cycles.samples=1;s.cycles.device='CPU';s.render.compositor_device='CPU'
s.render.resolution_x=64;s.render.resolution_y=64;s.render.resolution_percentage=100
s.render.image_settings.file_format='OPEN_EXR';s.render.image_settings.color_mode='RGBA';s.render.image_settings.color_depth='32'
s.world.use_nodes=True;s.world.node_tree.nodes.get('Background').inputs['Strength'].default_value=0
for obj in s.objects:
 if obj.type in {'MESH','LIGHT'}: obj.hide_render=True
def render(path):
 s.render.filepath=path;bpy.ops.render.render(write_still=True);return list(bpy.data.images.load(path).pixels[:])
before=render('/tmp/cfx-dark-before.exr')
bpy.ops.cinematic_fx.install(); c=s.cinematic_fx;c.builtin_preset='FAN';bpy.ops.cinematic_fx.use_preset()
c.opacity=1;c.volumetric_density=1;c.texture_gain=4;c.threshold=0.2
assert c.source_type=='TEXTURE'
after=render('/tmp/cfx-dark-after.exr')
delta=sum(abs(a-b) for a,b in zip(before,after))
print('DARK SCENE PIXEL DELTA',delta);assert delta < 0.01
print('CFX TEXTURE SAFETY RENDER PASSED')
