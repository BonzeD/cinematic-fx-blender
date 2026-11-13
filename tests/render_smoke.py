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
print('CFX RENDER TEST PASSED')
