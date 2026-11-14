"""Run in Blender 5.3: blender --factory-startup -b --python tests/layers.py."""
import os, sys, tempfile
import bpy
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cinematic_fx as addon
addon.register()
s = bpy.context.scene
assert bpy.ops.cinematic_fx.install() == {'FINISHED'}
c = s.cinematic_fx
c.source_type = 'LAYERS'
assert c.ray_layer_count == 3 and len(c.ray_layers) == 3
specs = [('HEXAGON_FILLED', 0.8, (1.0,0.25,0.25,1.0)),
         ('STAR6_FILLED', 0.45, (0.25,1.0,0.25,1.0)),
         ('PETALS', 0.25, (0.25,0.25,1.0,1.0))]
for i,(preset,size,color) in enumerate(specs):
    layer = c.ray_layers[i]; layer.preset = preset; layer.size = size; layer.color = color
    layer.offset = (0.07*i, -0.03*i); layer.rotation = 0.2*i
    assert layer.image and layer.image.packed_file and layer.image.get('cinematic_fx_preset') == preset
    t = c.node_group
    assert t.nodes['CFX Layer Image 0 %d' % i].image == layer.image
    assert abs(t.nodes['CFX Layer Transform 0 %d' % i].inputs['Scale'].default_value-size) < 1e-5
    assert all(abs(a-b)<1e-5 for a,b in zip(addon.socket(t.nodes['CFX Layer Tint 0 %d' % i].inputs, 'B_Color').default_value,color))
# Reducing the count hides slots without erasing the user's edits.
c.ray_layer_count = 1
assert not c.node_group.nodes.get('CFX Layer Image 0 2')
c.ray_layer_count = 3
assert c.ray_layers[2].preset == 'PETALS' and abs(c.ray_layers[2].size-0.25)<1e-5
assert c.node_group.nodes.get('CFX Layer Image 0 2')
# Full shapes have a bright interior where their outline counterparts are dark.
for filled,outline in [('HEXAGON_FILLED','HEXAGON'),('OCTAGON_FILLED','OCTAGON'),('PETALS_FILLED','PETALS')]:
    assert addon._preset_value(filled,0.2,0.06) > addon._preset_value(outline,0.2,0.06) + 0.5
# The same three layers are available at every object emitter.
c.source_type = 'OBJECTS'
e = c.emitters.add(); e.object = bpy.data.objects['Cube']
c.emitter_use_layers = True
assert c.node_group.nodes.get('CFX Layer Image 0 2')
assert c.node_group.nodes['CFX Layer Image 0 1'].image == c.ray_layers[1].image
# A missing or disabled source produces no layer.
e.enabled = False
assert addon.socket(c.node_group.nodes['CFX Layer Mix 0 0'].inputs, 'Factor_Float').default_value == 0.0
e.enabled = True
assert addon.socket(c.node_group.nodes['CFX Layer Mix 0 0'].inputs, 'Factor_Float').default_value == 1.0
# Save and reload while using object layers.
path = os.path.join(tempfile.gettempdir(), 'cfx-layer-persistence.blend')
bpy.ops.wm.save_as_mainfile(filepath=path)
bpy.ops.wm.open_mainfile(filepath=path)
c=bpy.context.scene.cinematic_fx
assert c.emitter_use_layers and c.ray_layer_count == 3
assert c.ray_layers[0].preset == 'HEXAGON_FILLED' and c.ray_layers[0].image.packed_file
assert c.ray_layers[1].preset == 'STAR6_FILLED' and abs(c.ray_layers[1].size - 0.45)<1e-5
assert tuple(round(v,2) for v in c.ray_layers[2].color) == (0.25,0.25,1.0,1.0)
assert c.node_group.nodes['CFX Layer Image 0 1'].image == c.ray_layers[1].image
print('CFX LAYERS TEST PASSED')
