"""Check packed preset image and settings across .blend save/load (factory startup)."""
import os, sys, tempfile
import bpy
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cinematic_fx as addon
addon.register()
bpy.ops.cinematic_fx.install()
s = bpy.context.scene.cinematic_fx
s.builtin_preset = 'HEXAGON'
assert bpy.ops.cinematic_fx.use_preset() == {'FINISHED'}
assert s.texture.packed_file
before = s.texture.pixels[:]
name = s.texture.name
cube = bpy.data.objects.get('Cube')
s.source_type = 'OBJECTS'
entry = s.emitters.add(); entry.object = cube
s.emitter_use_texture = True
path = os.path.join(tempfile.gettempdir(), 'cfx-persistence-test.blend')
bpy.ops.wm.save_as_mainfile(filepath=path)
bpy.ops.wm.open_mainfile(filepath=path)
s = bpy.context.scene.cinematic_fx
assert s.texture and s.texture.name == name and s.texture.packed_file
assert s.source_type == 'OBJECTS' and s.node_group
assert len(s.emitters) == 1 and s.emitters[0].object.name == 'Cube' and s.emitter_use_texture
assert s.node_group.nodes['Custom Texture'].image == s.texture
# Packed generated images may be quantized; tolerate standard PNG quantization.
after = s.texture.pixels[:]
assert max(after[0::4]) > 0.4
assert max(abs(a-b) for a,b in zip(before,after)) < 0.03
print('CFX PERSISTENCE TEST PASSED')
