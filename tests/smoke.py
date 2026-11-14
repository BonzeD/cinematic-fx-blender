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
assert t.nodes['Sun Beams'].inputs['Image'].links[0].from_node.name == 'CFX Texture Scene Mask'
assert addon.socket(t.nodes['CFX Texture Scene Mask'].inputs, 'A_Color').links[0].from_node.name == 'Input'
assert addon.socket(t.nodes['CFX Texture Scene Mask'].inputs, 'B_Color').links[0].from_node.name == 'Custom Texture Gain'
settings.source_type = 'SOURCE'; assert t.nodes['Sun Beams'].inputs['Image'].links[0].from_node.name == 'Input'
# All embedded presets generate distinct, packed image datablocks.
signatures = set()
for key, label, _ in addon.PRESETS:
    settings.builtin_preset = key
    assert bpy.ops.cinematic_fx.use_preset() == {'FINISHED'}
    image = settings.texture
    assert image and image.packed_file and settings.source_type == 'TEXTURE'
    assert image.get('cinematic_fx_preset') == key
    assert addon.preset_image(key) == image  # Cache, not a duplicate.
    pixels = image.pixels[:]
    assert max(pixels[0::4]) > 0.4
    signatures.add(tuple(round(pixels[i], 4) for i in range(0, len(pixels), 4004)))
assert len(signatures) == len(addon.PRESETS)
settings.texture_gain = 7.0
assert t.nodes['Custom Texture Gain'].inputs['Master Gain'].default_value == 7.0
settings.mask_type = 'CUSTOM'; settings.mask_image = img
assert t.nodes['Mask Luminance'].inputs['Image'].links[0].from_node.name == 'Custom Mask Mapping'
settings.mask_type = 'NONE'; settings.mask_image = None; settings.use_density_mask = False
assert not t.nodes['Mask Luminance'].inputs['Image'].is_linked
# Existing 1.0 groups are upgraded in place when texture gain is used.
t.nodes.remove(t.nodes['Custom Texture Gain'])
settings.source_type = 'TEXTURE'
assert t.nodes.get('Custom Texture Gain')
assert t.nodes['Sun Beams'].inputs['Image'].links[0].from_node.name == 'CFX Texture Scene Mask'
# Test multi-object emitters, tracking, disabled items, and reindexing.
settings.source_type = 'OBJECTS'
cube = bpy.data.objects.get('Cube'); light = bpy.data.objects.get('Light')
assert cube and light and s.camera
first = settings.emitters.add(); first.object = cube
second = settings.emitters.add(); second.object = light
assert len(settings.emitters) == 2
em = t.nodes['CFX Emitter 0']
assert em.inputs['Value'].default_value == 1.0
xy = tuple(em.inputs['Position'].default_value)
assert all(0 <= v <= 1 for v in xy)
assert all(abs(a-b) < 1e-5 for a,b in zip(xy, t.nodes['Sun Beams'].inputs['Sun Position'].default_value))
first.enabled = False
assert em.inputs['Value'].default_value == 0.0
assert bpy.ops.cinematic_fx.remove_emitter(index=0) == {'FINISHED'}
assert len(settings.emitters) == 1 and t.nodes.get('CFX Emitter 0') and not t.nodes.get('CFX Emitter 1')
# Switch to texture patterns at each object, then back to discs.
settings.emitter_use_texture = True
assert t.nodes['CFX Emitter 0'].bl_idname == 'CompositorNodeTransform'
assert t.nodes.get('CFX Emitter Mix 0')
settings.emitter_use_texture = False
assert t.nodes['CFX Emitter 0'].bl_idname == 'CompositorNodeEllipseMask'
# Track an object as it moves out of view.
settings.emitters[0].object = cube
cube.location = (10000.0, 10000.0, 10000.0)
bpy.context.view_layer.update(); addon.refresh_emitters_handler()
assert t.nodes['CFX Emitter 0'].inputs['Value'].default_value == 0.0
cube.location = (0.0, 0.0, 0.0)
bpy.context.view_layer.update(); addon.refresh_emitters_handler()
assert t.nodes['CFX Emitter 0'].inputs['Value'].default_value == 1.0
# Animated source positions follow frames through the registered handlers.
cube.location = (0, 0, 0); cube.keyframe_insert(data_path='location', frame=1)
cube.location = (0.5, 0, 0); cube.keyframe_insert(data_path='location', frame=5)
s.frame_set(1); xy1 = tuple(t.nodes['CFX Emitter 0'].inputs['Position'].default_value)
s.frame_set(5); xy2 = tuple(t.nodes['CFX Emitter 0'].inputs['Position'].default_value)
assert max(abs(a-b) for a,b in zip(xy1,xy2)) > 0.001
# A Sun light uses direction, not its irrelevant object location.
from mathutils import Vector
sun_data = bpy.data.lights.new('Test Sun', 'SUN')
sun_obj = bpy.data.objects.new('Test Sun', sun_data); s.collection.objects.link(sun_obj)
direction = s.camera.matrix_world.to_quaternion() @ Vector((0, 0, -1))
sun_obj.rotation_euler = Vector((0, 0, 1)).rotation_difference(direction).to_euler()
bpy.context.view_layer.update()
sun_point = addon.projected_emitter(s, sun_obj)
assert sun_point and abs(sun_point[0] - 0.5) < 0.01 and abs(sun_point[1] - 0.5) < 0.01
assert bpy.ops.cinematic_fx.remove() == {'FINISHED'}
assert prior in list(s.compositor_effects) and prior.node_group == prior_tree
addon.unregister()
print('CFX SMOKE TEST PASSED')
