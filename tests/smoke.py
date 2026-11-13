"""Run with Blender 5.3: blender -b --python tests/smoke.py"""
import os, sys, math
import bpy
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cinematic_fx as addon
addon.register()
s = bpy.context.scene
# Verify that an existing effect is not replaced.
prior = s.compositor_effects.new('Pre-existing')
prior_tree = bpy.data.node_groups.new('Pre-existing tree', 'CompositorNodeTree')
prior.node_group = prior_tree
assert bpy.ops.cinematic_fx.install() == {'FINISHED'}
settings = s.cinematic_fx
t = settings.node_group
assert t and any(e.node_group == t for e in s.compositor_effects)
assert prior in list(s.compositor_effects) and prior.node_group == prior_tree
assert bpy.ops.cinematic_fx.install() == {'CANCELLED'}
settings.opacity = 0.3
settings.volumetric_density = 0.5
assert abs(t.nodes['Mask Strength'].inputs[1].default_value - 0.15) < 1e-5
settings.pattern = 'STREAKS'; settings.pattern_density = 8
assert t.nodes['Streaks'].inputs['Streaks'].default_value == 8
assert t.nodes['Sun Beams'].inputs['Strength'].default_value == 0
settings.sun_position = (0.2, 0.7)
assert abs(t.nodes['Sun Beams'].inputs['Sun Position'].default_value[0] - 0.2) < 1e-5
settings.enable_caustics = True
assert t.nodes['Caustic Look'].inputs['Strength'].default_value > 0
settings.blend_mode = 'SCREEN'
assert t.nodes['Blend with Original'].blend_type == 'SCREEN'
img = bpy.data.images.new('Test texture', 8, 8)
settings.texture = img; settings.source_type = 'TEXTURE'
assert t.nodes['Sun Beams'].inputs['Image'].links[0].from_node.name == 'Custom Texture Mapping'
settings.source_type = 'SOURCE'; assert t.nodes['Sun Beams'].inputs['Image'].links[0].from_node.name == 'Input'
settings.mask_type = 'CUSTOM'; settings.mask_image = img
assert t.nodes['Mask Luminance'].inputs['Image'].links[0].from_node.name == 'Custom Mask Mapping'
settings.mask_type = 'NONE'; settings.mask_image = None; settings.use_density_mask = False
assert not t.nodes['Mask Luminance'].inputs['Image'].is_linked
assert bpy.ops.cinematic_fx.remove() == {'FINISHED'}
assert prior in list(s.compositor_effects) and prior.node_group == prior_tree
addon.unregister()
print('CFX SMOKE TEST PASSED')
