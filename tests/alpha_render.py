"""Transparent render preserves original alpha in every blend mode."""
import os,sys,bpy
sys.path.insert(0,os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cinematic_fx as addon
addon.register();s=bpy.context.scene
s.render.engine='CYCLES';s.cycles.samples=1;s.render.compositor_device='CPU';s.render.resolution_x=32;s.render.resolution_y=32;s.render.resolution_percentage=100
s.render.film_transparent=True;s.render.image_settings.file_format='OPEN_EXR';s.render.image_settings.color_mode='RGBA';s.render.image_settings.color_depth='32'
def render(path):
 s.render.filepath=path;bpy.ops.render.render(write_still=True);return list(bpy.data.images.load(path).pixels[:])
before=render('/tmp/cfx-alpha-original.exr');bpy.ops.cinematic_fx.install();c=s.cinematic_fx;c.source_type='LAYERS';c.emitter_strength=10;c.threshold=0.2
for mode in ('ADD','SCREEN','MIX'):
 c.blend_mode=mode; after=render('/tmp/cfx-alpha-'+mode+'.exr')
 delta=max(abs(x-y) for x,y in zip(before[3::4],after[3::4]))
 print(mode,'alpha max delta',delta); assert delta<1e-5
print('CFX ALPHA TEST PASSED')
