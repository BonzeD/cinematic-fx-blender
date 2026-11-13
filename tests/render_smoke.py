"""CPU render test; verifies actual compositing changes pixels in Blender 5.3."""
import os, sys
import bpy
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cinematic_fx as addon
addon.register()
s = bpy.context.scene
s.render.engine = 'CYCLES'
s.render.compositor_device = 'CPU'
s.cycles.device = 'CPU'; s.cycles.samples = 1
s.render.resolution_x = 64; s.render.resolution_y = 64; s.render.resolution_percentage = 100
s.render.image_settings.file_format = 'OPEN_EXR'
s.render.image_settings.color_mode = 'RGBA'
s.render.image_settings.color_depth = '32'
s.render.film_transparent = False
# Default cube provides a compact bright source against a dark world.
cube = bpy.data.objects.get('Cube')
mat = bpy.data.materials.new('Emission test'); mat.use_nodes = True
nodes = mat.node_tree.nodes; nodes.clear()
em = nodes.new('ShaderNodeEmission'); em.inputs['Color'].default_value = (1.0, 1.0, 1.0, 1.0); em.inputs['Strength'].default_value = 20.0
out = nodes.new('ShaderNodeOutputMaterial'); mat.node_tree.links.new(em.outputs[0], out.inputs['Surface']); cube.data.materials.clear(); cube.data.materials.append(mat)
s.world.use_nodes = True; s.world.node_tree.nodes.get('Background').inputs['Strength'].default_value = 0.0
s.render.filepath = '/tmp/cfx-before.exr'; bpy.ops.render.render(write_still=True)
bpy.ops.cinematic_fx.install(); c=s.cinematic_fx
c.pattern = 'COMBINED'; c.opacity = 1; c.volumetric_density=1; c.ray_strength=2; c.glow_strength=2; c.edge_smoothness=0; c.threshold=0.5
s.render.filepath = '/tmp/cfx-after.exr'; bpy.ops.render.render(write_still=True)
a=bpy.data.images.load('/tmp/cfx-before.exr'); b=bpy.data.images.load('/tmp/cfx-after.exr')
diff=sum(abs(x-y) for x,y in zip(a.pixels[:],b.pixels[:]))
print('CFX PIXEL DIFFERENCE:', diff)
assert diff > 1.0, 'Effect did not change rendered pixels'
# Opacity zero and a black custom mask must bypass the effect.
c.opacity = 0.0
s.render.filepath = '/tmp/cfx-zero.exr'; bpy.ops.render.render(write_still=True)
z = bpy.data.images.load('/tmp/cfx-zero.exr')
zero_diff = sum(abs(x-y) for x,y in zip(a.pixels[:], z.pixels[:]))
print('CFX ZERO-OPACITY DIFFERENCE:', zero_diff)
assert zero_diff < 0.01, 'Zero opacity must preserve input'
c.opacity = 1.0
black = bpy.data.images.new('Black mask', 64, 64, alpha=True, float_buffer=True)
black.pixels[:] = [0.0, 0.0, 0.0, 1.0] * (64 * 64)
c.mask_image = black; c.mask_type = 'CUSTOM'
s.render.filepath = '/tmp/cfx-black-mask.exr'; bpy.ops.render.render(write_still=True)
m = bpy.data.images.load('/tmp/cfx-black-mask.exr')
mask_diff = sum(abs(x-y) for x,y in zip(a.pixels[:], m.pixels[:]))
print('CFX BLACK-MASK DIFFERENCE:', mask_diff)
assert mask_diff < 0.01, 'Black custom mask must preserve input'
# A built-in texture should drive a visible compositing result.
c.mask_type = 'NONE'; c.mask_image = None
c.builtin_preset = 'ANAMORPHIC'; bpy.ops.cinematic_fx.use_preset()
s.render.filepath = '/tmp/cfx-preset.exr'; bpy.ops.render.render(write_still=True)
p = bpy.data.images.load('/tmp/cfx-preset.exr')
preset_diff = sum(abs(x-y) for x,y in zip(a.pixels[:], p.pixels[:]))
print('CFX PRESET DIFFERENCE:', preset_diff)
assert preset_diff > 1.0, 'Built-in preset must visibly change the render'
# Object mode: an empty selection emits nothing; a selected object emits light.
c.source_type = 'OBJECTS'
s.render.filepath = '/tmp/cfx-empty-emitters.exr'; bpy.ops.render.render(write_still=True)
e = bpy.data.images.load('/tmp/cfx-empty-emitters.exr')
empty_diff = sum(abs(x-y) for x,y in zip(a.pixels[:],e.pixels[:]))
print('CFX EMPTY EMITTER DIFFERENCE:', empty_diff)
assert empty_diff < 0.01, 'No sources should not add light'
item = c.emitters.add(); item.object = cube
s.render.filepath = '/tmp/cfx-object-emitter.exr'; bpy.ops.render.render(write_still=True)
o = bpy.data.images.load('/tmp/cfx-object-emitter.exr')
object_diff = sum(abs(x-y) for x,y in zip(a.pixels[:],o.pixels[:]))
print('CFX OBJECT EMITTER DIFFERENCE:', object_diff)
assert object_diff > 1.0, 'Selected emitter must visibly change the render'
c.emitter_use_texture = True
s.render.filepath = '/tmp/cfx-textured-emitter.exr'; bpy.ops.render.render(write_still=True)
t = bpy.data.images.load('/tmp/cfx-textured-emitter.exr')
texture_object_diff = sum(abs(x-y) for x,y in zip(a.pixels[:],t.pixels[:]))
print('CFX TEXTURED EMITTER DIFFERENCE:', texture_object_diff)
assert texture_object_diff > 1.0, 'Texture must visibly contribute to object emitter'
print('CFX RENDER TEST PASSED')
