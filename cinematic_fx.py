bl_info = {
    'name': 'Cinematic FX',
    'author': 'Cinematic FX contributors',
    'version': (1, 1, 0),
    'blender': (5, 3, 0),
    'location': '3D View / Compositor > Sidebar > Cinematic FX',
    'description': 'Non-destructive cinematic rays, streaks, glow and masks',
    'category': 'Compositing',
}

import bpy
import math
from array import array
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty, FloatVectorProperty,
                       IntProperty, PointerProperty)
from bpy.app.handlers import persistent
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


# Presets are deterministic recipes bundled in the add-on. Images are generated
# only when requested, cached as Blender images and packed into the .blend.
PRESETS = (
    ('ANAMORPHIC', 'Anamorphic Streak', 'Horizontal cinematic streak'),
    ('STAR4', 'Four-point Star', 'Four pointed light star'),
    ('STAR6', 'Six-point Star', 'Six pointed light star'),
    ('STAR8', 'Eight-point Star', 'Eight pointed light star'),
    ('HEXAGON', 'Hexagonal Aperture', 'Hexagonal aperture outline'),
    ('OCTAGON', 'Octagonal Aperture', 'Octagonal aperture outline'),
    ('PETALS', 'Iris Petals', 'Eight soft aperture petals'),
    ('HALO', 'Halo Rings', 'Concentric lens rings'),
    ('GHOSTS', 'Lens Ghosts', 'A chain of soft lens ghosts'),
    ('FAN', 'Radial Fan', 'A fan of narrow radial rays'),
)


def _bell(value, center, width):
    return math.exp(-((value - center) / width) ** 2)


def _star(angle, count, radius, sharpness=0.14):
    return math.exp(-(math.sin(angle * count / 2.0) / sharpness) ** 2) * math.exp(-2.2 * radius)


def _preset_value(kind, x, y):
    r = math.hypot(x, y)
    a = math.atan2(y, x)
    core = 0.9 * math.exp(-((r / 0.055) ** 2))
    if kind == 'ANAMORPHIC':
        v = 0.9 * math.exp(-((y / 0.018) ** 2)) * math.exp(-1.5 * abs(x))
        v += 0.28 * math.exp(-((y / 0.065) ** 2)) * math.exp(-2.0 * abs(x))
    elif kind in {'STAR4', 'STAR6', 'STAR8'}:
        count = {'STAR4': 4, 'STAR6': 6, 'STAR8': 8}[kind]
        v = _star(a, count, r) * 0.95
    elif kind in {'HEXAGON', 'OCTAGON'}:
        count = 6 if kind == 'HEXAGON' else 8
        polygon_radius = max(x * math.cos(i * math.tau / count) + y * math.sin(i * math.tau / count) for i in range(count))
        v = 0.9 * _bell(polygon_radius, 0.52, 0.018) + 0.23 * _star(a, count, r)
    elif kind == 'PETALS':
        petal_radius = 0.36 + 0.13 * math.cos(8.0 * a)
        v = 0.85 * _bell(r, petal_radius, 0.05) + 0.2 * _bell(r, 0.62, 0.035)
    elif kind == 'HALO':
        v = (0.65 * _bell(r, 0.35, 0.025) + 0.44 * _bell(r, 0.58, 0.04)
             + 0.22 * _bell(r, 0.78, 0.055))
    elif kind == 'GHOSTS':
        v = 0.0
        for cx, cy, size, intensity in [(-0.55, -0.18, 0.15, 0.55), (-0.28, -0.09, 0.08, 0.7),
                                         (0.25, 0.08, 0.10, 0.55), (0.52, 0.17, 0.17, 0.4)]:
            d = math.hypot(x - cx, y - cy)
            v += intensity * (_bell(d, size, 0.025) + 0.22 * math.exp(-((d / size) ** 2)))
        v += 0.2 * math.exp(-((y / 0.025) ** 2)) * math.exp(-abs(x))
    elif kind == 'FAN':
        v = 0.88 * _star(a, 16, r, 0.19) + 0.18 * _bell(r, 0.55, 0.05)
    else:
        raise ValueError('Unknown Cinematic FX texture preset: ' + kind)
    return min(1.0, max(0.0, core + v))


def preset_image(kind, size=256):
    label = next((item[1] for item in PRESETS if item[0] == kind), None)
    if label is None:
        raise ValueError('Unknown texture preset: ' + kind)
    for image in bpy.data.images:
        if image.get('cinematic_fx_preset') == kind and image.get('cinematic_fx_preset_version') == 1:
            return image
    image = bpy.data.images.new('CFX - ' + label, width=size, height=size, alpha=True)
    try:
        pixels = array('f')
        for j in range(size):
            y = (2.0 * (j + 0.5) / size) - 1.0
            for i in range(size):
                x = (2.0 * (i + 0.5) / size) - 1.0
                value = _preset_value(kind, x, y)
                pixels.extend((value, value, value, 1.0))
        image.pixels.foreach_set(pixels)
        image.update()
        image['cinematic_fx_preset'] = kind
        image['cinematic_fx_preset_version'] = 1
        image.pack()
        return image
    except Exception:
        bpy.data.images.remove(image)
        raise


def texture_gain_node(tree):
    # Upgrade effect groups created by 1.0 without replacing their nodes.
    n = tree.nodes.get('Custom Texture Gain')
    if n is None:
        n = node(tree, 'CompositorNodeColorCorrection', 'Custom Texture Gain', -850, -100)
        link(tree, tree.nodes['Custom Texture Mapping'], 'Image', n, 'Image')
    return n


# These identifiers are private to our node group; no scene nodes are overwritten.
def node(tree, kind, name, x, y):
    n = tree.nodes.new(kind)
    n.name = n.label = name
    n.location = (x, y)
    return n


def socket(collection, identifier):
    return next((s for s in collection if s.identifier == identifier), None) or next(s for s in collection if s.name == identifier)


def link(tree, a, out_id, b, in_id):
    tree.links.new(socket(a.outputs, out_id), socket(b.inputs, in_id))


def color_mix(tree, name, x, y, mode='ADD'):
    n = node(tree, 'ShaderNodeMix', name, x, y)
    n.data_type = 'RGBA'
    n.blend_type = mode
    n.clamp_factor = True
    n.clamp_result = False
    socket(n.inputs, 'Factor_Float').default_value = 1.0
    return n


def image_chain(tree, label, x, y):
    img = node(tree, 'CompositorNodeImage', label, x, y)
    scale = node(tree, 'CompositorNodeScale', label + ' Fit', x + 200, y)
    scale.inputs['Type'].default_value = 'Render Size'
    transform = node(tree, 'CompositorNodeTransform', label + ' Mapping', x + 400, y)
    link(tree, img, 'Image', scale, 'Image')
    link(tree, scale, 'Image', transform, 'Image')
    return img, transform


def build_tree():
    t = bpy.data.node_groups.new('Cinematic FX', 'CompositorNodeTree')
    try:
        t.interface.new_socket(name='Image', in_out='INPUT', socket_type='NodeSocketColor')
        t.interface.new_socket(name='Image', in_out='OUTPUT', socket_type='NodeSocketColor')
        inp = node(t, 'NodeGroupInput', 'Input', -1500, 700)
        out = node(t, 'NodeGroupOutput', 'Output', 1650, 700)
        image_chain(t, 'Custom Texture', -1500, -100)
        texture_gain_node(t)
        image_chain(t, 'Custom Mask', -1500, -650)
        sun = node(t, 'CompositorNodeGlare', 'Sun Beams', -700, 650)
        sun.inputs['Type'].default_value = 'Sun Beams'
        streak = node(t, 'CompositorNodeGlare', 'Streaks', -700, 350)
        streak.inputs['Type'].default_value = 'Streaks'
        glow = node(t, 'CompositorNodeGlare', 'Glow', -700, 50)
        glow.inputs['Type'].default_value = 'Fog Glow'
        ghost = node(t, 'CompositorNodeGlare', 'Caustic Look', -700, -250)
        ghost.inputs['Type'].default_value = 'Ghosts'
        combined = color_mix(t, 'Combine Rays and Streaks', -400, 600)
        link(t, sun, 'Glare', combined, 'A_Color'); link(t, streak, 'Glare', combined, 'B_Color')
        with_glow = color_mix(t, 'Combine Glow', -180, 600)
        link(t, combined, 'Result_Color', with_glow, 'A_Color'); link(t, glow, 'Glare', with_glow, 'B_Color')
        with_ghost = color_mix(t, 'Combine Caustic Look', 40, 600)
        link(t, with_glow, 'Result_Color', with_ghost, 'A_Color'); link(t, ghost, 'Glare', with_ghost, 'B_Color')
        bw = node(t, 'CompositorNodeRGBToBW', 'Ray Luminance', 260, 450)
        ramp = node(t, 'ShaderNodeValToRGB', 'Ray Color Gradient', 460, 400)
        ramp.color_ramp.elements[0].color = (0.16, 0.26, 0.8, 1.0)
        ramp.color_ramp.elements[1].color = (1.0, 0.9, 0.8, 1.0)
        link(t, with_ghost, 'Result_Color', bw, 'Image'); link(t, bw, 'Val', ramp, 'Fac')
        tint = color_mix(t, 'Tint Rays', 690, 600, 'MULTIPLY')
        link(t, with_ghost, 'Result_Color', tint, 'A_Color'); link(t, ramp, 'Color', tint, 'B_Color')
        correction = node(t, 'CompositorNodeColorCorrection', 'Ray Clarity', 900, 600)
        link(t, tint, 'Result_Color', correction, 'Image')
        blur = node(t, 'CompositorNodeBlur', 'Edge Smoothness', 1100, 600)
        link(t, correction, 'Image', blur, 'Image')
        mask_bw = node(t, 'CompositorNodeRGBToBW', 'Mask Luminance', 250, -350)
        mask_math = node(t, 'ShaderNodeMath', 'Mask Strength', 480, -200)
        mask_math.operation = 'MULTIPLY'; mask_math.use_clamp = True
        link(t, mask_bw, 'Val', mask_math, 'Value')
        final = color_mix(t, 'Blend with Original', 1400, 700)
        link(t, inp, 'Image', final, 'A_Color'); link(t, blur, 'Image', final, 'B_Color')
        link(t, mask_math, 'Value', final, 'Factor_Float'); link(t, final, 'Result_Color', out, 'Image')
        return t
    except Exception:
        bpy.data.node_groups.remove(t)
        raise


def set_if_changed(socket_value, value, epsilon=1e-6):
    current = socket_value.default_value
    if isinstance(value, tuple):
        if len(current) == len(value) and all(abs(a - b) < epsilon for a, b in zip(current, value)):
            return
    elif abs(current - value) < epsilon:
        return
    socket_value.default_value = value


def projected_emitter(scene, obj):
    camera = scene.camera
    if not camera or not obj:
        return None
    try:
        # SUN location has no meaning in Blender: +local Z points toward its source.
        if obj.type == 'LIGHT' and obj.data and obj.data.type == 'SUN':
            direction = obj.matrix_world.to_quaternion() @ Vector((0.0, 0.0, 1.0))
            position = camera.matrix_world.translation + direction * 1000.0
        else:
            position = obj.matrix_world.translation
        projected = world_to_camera_view(scene, camera, position)
        if projected.z <= 0.0 or not (0.0 <= projected.x <= 1.0 and 0.0 <= projected.y <= 1.0):
            return None
        return (float(projected.x), float(projected.y))
    except (ReferenceError, ValueError, AttributeError):
        return None


def ensure_emitter_nodes(scene, settings):
    t = settings.node_group
    if not t:
        return None
    nodes = t.nodes
    base = nodes.get('CFX Emitter Base')
    if base is None:
        # Multiply the scene by black to establish the render's image domain.
        base = color_mix(t, 'CFX Emitter Base', -1450, -1150, 'MULTIPLY')
        socket(base.inputs, 'B_Color').default_value = (0.0, 0.0, 0.0, 1.0)
        link(t, nodes['Input'], 'Image', base, 'A_Color')
    strength = nodes.get('CFX Emitter Strength')
    if strength is None:
        strength = node(t, 'CompositorNodeColorCorrection', 'CFX Emitter Strength', -750, -1150)
    expected = len(settings.emitters)
    mode = 'TEXTURE' if settings.emitter_use_texture and settings.texture else 'DISC'
    managed = [n for n in nodes if n.get('cinematic_fx_emitter')]
    expected_nodes = expected * (2 if mode == 'TEXTURE' else 1)
    if len(managed) != expected_nodes or strength.get('cinematic_fx_emitter_mode') != mode:
        for n in managed:
            nodes.remove(n)
        for i in range(expected):
            if mode == 'TEXTURE':
                n = node(t, 'CompositorNodeTransform', 'CFX Emitter %d' % i, -1200 + i * 180, -1150)
                link(t, nodes['Custom Texture Mapping'], 'Image', n, 'Image')
                mix = color_mix(t, 'CFX Emitter Mix %d' % i, -1200 + i * 180, -1400, 'ADD')
                mix['cinematic_fx_emitter'] = True
            else:
                n = node(t, 'CompositorNodeEllipseMask', 'CFX Emitter %d' % i, -1200 + i * 160, -1150)
            n['cinematic_fx_emitter'] = True
        strength['cinematic_fx_emitter_mode'] = mode
    prev, output = base, 'Result_Color'
    for i in range(expected):
        current = nodes.get('CFX Emitter %d' % i)
        mix = nodes.get('CFX Emitter Mix %d' % i) if mode == 'TEXTURE' else None
        if current is None or (mode == 'TEXTURE' and mix is None):
            for n in [n for n in nodes if n.get('cinematic_fx_emitter')]:
                nodes.remove(n)
            return ensure_emitter_nodes(scene, settings)
        if mode == 'TEXTURE':
            if not socket(mix.inputs, 'A_Color').is_linked or socket(mix.inputs, 'A_Color').links[0].from_node != prev:
                link(t, prev, output, mix, 'A_Color')
            if not socket(mix.inputs, 'B_Color').is_linked or socket(mix.inputs, 'B_Color').links[0].from_node != current:
                link(t, current, 'Image', mix, 'B_Color')
            prev, output = mix, 'Result_Color'
        else:
            if not current.inputs['Mask'].is_linked or current.inputs['Mask'].links[0].from_node != prev:
                link(t, prev, output, current, 'Mask')
            prev, output = current, 'Mask'
    if not strength.inputs['Image'].is_linked or strength.inputs['Image'].links[0].from_node != prev:
        link(t, prev, output, strength, 'Image')
    set_if_changed(strength.inputs['Master Gain'], settings.emitter_strength)
    refresh_emitter_positions(scene, settings)
    return strength


def refresh_emitter_positions(scene, settings):
    t = settings.node_group
    if not t:
        return
    first = None
    use_texture = settings.emitter_use_texture and settings.texture
    width = scene.render.resolution_x * scene.render.resolution_percentage / 100.0
    height = scene.render.resolution_y * scene.render.resolution_percentage / 100.0
    for i, entry in enumerate(settings.emitters):
        n = t.nodes.get('CFX Emitter %d' % i)
        if not n:
            continue
        point = projected_emitter(scene, entry.object) if entry.enabled else None
        if use_texture and n.bl_idname == 'CompositorNodeTransform':
            mix = t.nodes.get('CFX Emitter Mix %d' % i)
            if mix:
                set_if_changed(socket(mix.inputs, 'Factor_Float'), 1.0 if point else 0.0)
            if point:
                set_if_changed(n.inputs['X'], (point[0] - 0.5) * width)
                set_if_changed(n.inputs['Y'], (point[1] - 0.5) * height)
                set_if_changed(n.inputs['Scale'], settings.emitter_texture_scale)
        elif n.bl_idname == 'CompositorNodeEllipseMask':
            set_if_changed(n.inputs['Value'], 1.0 if point else 0.0)
            if point:
                set_if_changed(n.inputs['Position'], point)
                set_if_changed(n.inputs['Size'], (settings.emitter_size, settings.emitter_size))
        if point and first is None:
            first = point
    if settings.source_type == 'OBJECTS' and settings.track_emitter and first:
        sun = t.nodes.get('Sun Beams')
        if sun:
            set_if_changed(sun.inputs['Sun Position'], first)


_refreshing_emitters = False


@persistent
def refresh_emitters_handler(*_args):
    global _refreshing_emitters
    if _refreshing_emitters:
        return
    _refreshing_emitters = True
    try:
        for scene in bpy.data.scenes:
            settings = getattr(scene, 'cinematic_fx', None)
            if settings and settings.source_type == 'OBJECTS' and settings.node_group:
                refresh_emitter_positions(scene, settings)
    finally:
        _refreshing_emitters = False


def emitter_entry_updated(self, context):
    scene = self.id_data
    if scene and hasattr(scene, 'cinematic_fx'):
        update_settings(scene.cinematic_fx, context)


def update_settings(self, context):
    t = self.node_group
    if not t or not t.nodes.get('Blend with Original'):
        return
    n = t.nodes
    try:
        n['Custom Texture'].image = self.texture
        n['Custom Mask'].image = self.mask_image
        mapping = n['Custom Texture Mapping']
        mapping.inputs['Scale'].default_value = self.texture_scale
        mapping.inputs['Angle'].default_value = self.texture_rotation
        mapping.inputs['X'].default_value = self.texture_offset[0]
        mapping.inputs['Y'].default_value = self.texture_offset[1]
        # Replace links only inside the add-on's own group.
        gain = texture_gain_node(t)
        gain.inputs['Master Gain'].default_value = self.texture_gain
        if self.source_type == 'OBJECTS':
            source = ensure_emitter_nodes(self.id_data, self)
        elif self.source_type == 'TEXTURE' and self.texture:
            source = gain
        else:
            source = n['Input']
        for name in ('Sun Beams', 'Streaks', 'Glow', 'Caustic Look'):
            link(t, source, 'Image', n[name], 'Image')
            n[name].inputs['Threshold'].default_value = self.threshold
            n[name].inputs['Smoothness'].default_value = self.edge_smoothness
        sun, streak, glow, ghost = (n[x] for x in ('Sun Beams', 'Streaks', 'Glow', 'Caustic Look'))
        sun.inputs['Sun Position'].default_value = (self.sun_position[0], self.sun_position[1])
        if self.source_type == 'OBJECTS':
            refresh_emitter_positions(self.id_data, self)
        sun.inputs['Size'].default_value = 0.1 + 0.9 * self.falloff
        sun.inputs['Strength'].default_value = self.ray_strength if self.pattern in {'SUN', 'COMBINED'} else 0.0
        streak.inputs['Streaks'].default_value = self.pattern_density
        streak.inputs['Fade'].default_value = 0.65 + 0.34 * self.falloff
        streak.inputs['Streaks Angle'].default_value = self.streak_angle
        streak.inputs['Strength'].default_value = self.ray_strength if self.pattern in {'STREAKS', 'COMBINED'} else 0.0
        glow.inputs['Strength'].default_value = self.glow_strength
        glow.inputs['Size'].default_value = self.glow_size
        ghost.inputs['Strength'].default_value = 0.35 if self.enable_caustics else 0.0
        n['Ray Clarity'].inputs['Master Contrast'].default_value = 0.5 + self.ray_sharpness * 1.5
        blur_size = self.edge_smoothness * 4.0
        n['Edge Smoothness'].inputs['Size'].default_value = (blur_size, blur_size)
        n['Blend with Original'].blend_type = self.blend_mode
        # Brightness masking and the optional density mask are screen-space approximations.
        # WHITE means no spatial mask; image sockets can carry a constant color.
        mbw = n['Mask Luminance']
        mask_input = mbw.inputs['Image']
        for old in list(mask_input.links):
            t.links.remove(old)
        if self.mask_type == 'CUSTOM' and self.mask_image:
            link(t, n['Custom Mask Mapping'], 'Image', mbw, 'Image')
        elif self.mask_type == 'BRIGHTNESS' or self.use_density_mask:
            link(t, sun, 'Highlights', mbw, 'Image')
        else:
            mask_input.default_value = (1.0, 1.0, 1.0, 1.0)
        n['Mask Strength'].inputs[1].default_value = min(1.0, self.opacity * self.volumetric_density)
    except (KeyError, AttributeError, TypeError, ValueError, ReferenceError) as exc:
        print('Cinematic FX: unable to update nodes:', exc)


def update_colors(self, context):
    t = self.node_group
    if t and t.nodes.get('Ray Color Gradient'):
        ramp = t.nodes['Ray Color Gradient'].color_ramp
        ramp.elements[0].color = self.secondary_color
        ramp.elements[-1].color = self.primary_color


class CFX_Emitter(bpy.types.PropertyGroup):
    object: PointerProperty(name='Object', type=bpy.types.Object, update=emitter_entry_updated)
    enabled: BoolProperty(name='Enabled', default=True, update=emitter_entry_updated)


class CFX_Settings(bpy.types.PropertyGroup):
    node_group: PointerProperty(type=bpy.types.NodeTree)
    source_type: EnumProperty(name='Source Type', items=[('SOURCE','Source','Scene image'),('TEXTURE','Texture','Use the custom image as effect source'),('OBJECTS','Objects / Lights','Create screen-space sources at selected object origins')], default='SOURCE', update=update_settings)
    emitters: CollectionProperty(type=CFX_Emitter)
    emitter_size: FloatProperty(name='Source Size', description='Diameter of each artificial source relative to the image', default=0.035, min=0.001, max=0.5, update=update_settings)
    emitter_use_texture: BoolProperty(name='Use Texture for Sources', description='Place the selected texture at each projected source', default=False, update=update_settings)
    emitter_texture_scale: FloatProperty(name='Source Texture Scale', description='Size of the pattern at each source', default=0.5, min=0.01, max=4.0, update=update_settings)
    emitter_strength: FloatProperty(name='Source Brightness', description='Brightness of each synthetic source before the highlight threshold', default=5.0, min=0.0, max=100.0, update=update_settings)
    track_emitter: BoolProperty(name='Track First Source', description='Place the Sun Beams center at the first visible enabled source', default=True, update=update_settings)
    texture: PointerProperty(name='Custom Texture', type=bpy.types.Image, update=update_settings)
    builtin_preset: EnumProperty(name='Built-in Texture', items=PRESETS, default='ANAMORPHIC')
    texture_gain: FloatProperty(name='Texture Gain', description='Boost the selected image before extracting highlights', default=4.0, min=0.0, max=20.0, update=update_settings)
    texture_scale: FloatProperty(name='Scale', default=1.0, min=0.01, max=10.0, update=update_settings)
    texture_rotation: FloatProperty(name='Rotation', subtype='ANGLE', default=0.0, update=update_settings)
    texture_offset: FloatVectorProperty(name='Offset (px)', size=2, default=(0.0,0.0), update=update_settings)
    pattern: EnumProperty(name='Ray Pattern', items=[('COMBINED','Combined','Sun beams and streaks'),('SUN','Sun Beams','Radial sun beams'),('STREAKS','Streaks','Lens streaks')], default='COMBINED', update=update_settings)
    pattern_density: IntProperty(name='Pattern Density', default=6, min=2, max=16, update=update_settings)
    opacity: FloatProperty(name='Base Opacity', default=0.8, min=0, max=1, subtype='FACTOR', update=update_settings)
    blend_mode: EnumProperty(name='Blend Mode', items=[('ADD','Add','Add light'),('SCREEN','Screen','Screen blend'),('MIX','Mix','Mix colors')], default='ADD', update=update_settings)
    primary_color: FloatVectorProperty(name='Primary Ray Color', subtype='COLOR', size=4, default=(1.0,0.9,0.8,1.0), min=0, max=1, update=update_colors)
    secondary_color: FloatVectorProperty(name='Secondary Ray Color', subtype='COLOR', size=4, default=(0.16,0.26,0.8,1.0), min=0, max=1, update=update_colors)
    ray_sharpness: FloatProperty(name='Ray Sharpness', default=0.5, min=0, max=1, update=update_settings)
    edge_smoothness: FloatProperty(name='Edge Smoothness', default=0.1, min=0, max=1, update=update_settings)
    falloff: FloatProperty(name='Falloff', default=0.7, min=0, max=1, update=update_settings)
    use_density_mask: BoolProperty(name='Use Volumetric Density Mask', default=False, update=update_settings)
    volumetric_density: FloatProperty(name='Volumetric Density', default=1, min=0, max=1, subtype='FACTOR', update=update_settings)
    enable_caustics: BoolProperty(name='Enable Caustics (stylized)', default=False, update=update_settings)
    mask_type: EnumProperty(name='Mask Type', items=[('NONE','None','Apply across the image'),('BRIGHTNESS','Screen Brightness','Use source highlights as a screen-space mask'),('CUSTOM','Custom Mask','Use luminance of an image mask')], default='NONE', update=update_settings)
    mask_image: PointerProperty(name='Custom Mask', type=bpy.types.Image, update=update_settings)
    threshold: FloatProperty(name='Highlight Threshold', default=1.0, min=0, max=100, update=update_settings)
    ray_strength: FloatProperty(name='Ray Strength', default=1.0, min=0, max=10, update=update_settings)
    glow_strength: FloatProperty(name='Glow Strength', default=0.4, min=0, max=10, update=update_settings)
    glow_size: FloatProperty(name='Glow Size', default=0.5, min=0, max=1, update=update_settings)
    sun_position: FloatVectorProperty(name='Sun Position', size=2, subtype='XYZ', default=(0.5,0.5), min=0, max=1, update=update_settings)
    streak_angle: FloatProperty(name='Streak Angle', subtype='ANGLE', default=0, update=update_settings)


class CFX_OT_install(bpy.types.Operator):
    bl_idname = 'cinematic_fx.install'
    bl_label = 'Add Cinematic FX'
    bl_description = 'Add an independent effect to the scene compositor stack'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        settings = scene.cinematic_fx
        if settings.node_group and any(e.node_group == settings.node_group for e in scene.compositor_effects):
            self.report({'INFO'}, 'Cinematic FX is already installed in this scene')
            return {'CANCELLED'}
        t = None
        effect = None
        try:
            t = build_tree()
            effect = scene.compositor_effects.new('Cinematic FX')
            effect.node_group = t
            settings.node_group = t
            update_settings(settings, context)
            update_colors(settings, context)
        except Exception as exc:
            if effect: scene.compositor_effects.remove(effect)
            if t: bpy.data.node_groups.remove(t)
            self.report({'ERROR'}, 'Could not create effect: ' + str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, 'Cinematic FX added to the compositor effects stack')
        return {'FINISHED'}


class CFX_OT_add_selected(bpy.types.Operator):
    bl_idname = 'cinematic_fx.add_selected'
    bl_label = 'Add Selected Objects'
    bl_description = 'Add selected objects or lights as virtual screen-space sources'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.cinematic_fx
        existing = {entry.object for entry in settings.emitters if entry.object}
        selected = [obj for obj in context.view_layer.objects if obj.select_get() and obj not in existing]
        if not selected:
            self.report({'WARNING'}, 'Select objects in the 3D View that are not already listed')
            return {'CANCELLED'}
        if len(settings.emitters) + len(selected) > 32:
            self.report({'ERROR'}, 'A maximum of 32 sources is supported')
            return {'CANCELLED'}
        for obj in selected:
            entry = settings.emitters.add()
            entry.object = obj
        update_settings(settings, context)
        return {'FINISHED'}


class CFX_OT_remove_emitter(bpy.types.Operator):
    bl_idname = 'cinematic_fx.remove_emitter'
    bl_label = 'Remove Source'
    bl_options = {'REGISTER', 'UNDO'}
    index: IntProperty()

    def execute(self, context):
        settings = context.scene.cinematic_fx
        if not 0 <= self.index < len(settings.emitters):
            return {'CANCELLED'}
        settings.emitters.remove(self.index)
        update_settings(settings, context)
        return {'FINISHED'}


class CFX_OT_use_preset(bpy.types.Operator):
    bl_idname = 'cinematic_fx.use_preset'
    bl_label = 'Use Built-in Texture'
    bl_description = 'Generate and pack the chosen built-in texture, then use it as the effect source'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.cinematic_fx
        try:
            image = preset_image(settings.builtin_preset)
            settings.texture = image
            if settings.source_type != 'OBJECTS':
                settings.source_type = 'TEXTURE'
        except Exception as exc:
            self.report({'ERROR'}, 'Could not create texture: ' + str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, 'Built-in texture selected and packed')
        return {'FINISHED'}


class CFX_OT_remove(bpy.types.Operator):
    bl_idname = 'cinematic_fx.remove'
    bl_label = 'Remove Cinematic FX'
    bl_description = 'Remove only this scene’s Cinematic FX effect'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene; settings = scene.cinematic_fx; t = settings.node_group
        if not t:
            return {'CANCELLED'}
        for effect in list(scene.compositor_effects):
            if effect.node_group == t:
                scene.compositor_effects.remove(effect)
        settings.node_group = None
        # Retain the datablock if another scene or node uses it.
        if t.users == 0:
            bpy.data.node_groups.remove(t)
        return {'FINISHED'}


def draw_panel(self, context):
    layout = self.layout; s = context.scene.cinematic_fx
    row = layout.row(align=True); row.operator('cinematic_fx.install', icon='ADD'); row.operator('cinematic_fx.remove', icon='REMOVE', text='')
    if not s.node_group:
        layout.label(text='Add the effect to start.', icon='INFO'); return
    box = layout.box(); box.label(text='Source & Texture'); box.prop(s, 'source_type')
    if s.source_type == 'OBJECTS':
        box.operator('cinematic_fx.add_selected', icon='ADD')
        for index, entry in enumerate(s.emitters):
            row = box.row(align=True); row.prop(entry, 'enabled', text=''); row.prop(entry, 'object', text=''); row.operator('cinematic_fx.remove_emitter', text='', icon='X').index = index
        box.prop(s, 'emitter_use_texture')
        if s.emitter_use_texture and s.texture:
            box.prop(s, 'emitter_texture_scale')
        else:
            box.prop(s, 'emitter_size')
            if s.emitter_use_texture: box.label(text='Select a texture below first', icon='INFO')
        box.prop(s, 'emitter_strength'); box.prop(s, 'track_emitter')
        if not context.scene.camera: box.label(text='Scene camera required', icon='ERROR')
        box.label(text='Screen-space sources; no occlusion', icon='INFO')
    box.prop(s, 'builtin_preset'); box.operator('cinematic_fx.use_preset', icon='TEXTURE')
    box.template_ID_preview(s, 'texture', open='image.open', rows=2, cols=4)
    if s.source_type == 'TEXTURE': box.prop(s, 'texture_gain')
    if s.source_type == 'TEXTURE' and not s.texture:
        box.label(text='No texture: using scene image', icon='INFO')
    box.label(text='Texture Remapping'); box.prop(s, 'texture_scale'); box.prop(s, 'texture_rotation'); box.prop(s, 'texture_offset')
    box = layout.box(); box.label(text='Custom Ray Settings'); box.prop(s, 'pattern'); box.prop(s, 'pattern_density'); box.prop(s, 'opacity'); box.prop(s, 'blend_mode'); box.prop(s, 'primary_color'); box.prop(s, 'secondary_color')
    ramp = s.node_group.nodes.get('Ray Color Gradient')
    if ramp: box.template_color_ramp(ramp, 'color_ramp', expand=True)
    box.prop(s, 'sun_position'); box.prop(s, 'streak_angle'); box.prop(s, 'threshold'); box.prop(s, 'ray_strength'); box.prop(s, 'glow_strength'); box.prop(s, 'glow_size')
    box = layout.box(); box.label(text='Pattern & Clarity Controls'); box.prop(s, 'ray_sharpness'); box.prop(s, 'edge_smoothness'); box.prop(s, 'falloff'); box.prop(s, 'use_density_mask')
    box = layout.box(); box.label(text='Volumetric & Density'); box.prop(s, 'volumetric_density'); box.prop(s, 'enable_caustics')
    box = layout.box(); box.label(text='Masking & Blending'); box.prop(s, 'mask_type')
    if s.mask_type == 'CUSTOM':
        box.template_ID_preview(s, 'mask_image', open='image.open', rows=2, cols=4)
        if not s.mask_image: box.label(text='No mask: unmasked', icon='INFO')
    layout.label(text='Screen-space look, not physical volume', icon='INFO')


class CFX_PT_view(bpy.types.Panel):
    bl_label = 'Cinematic FX'; bl_idname = 'CFX_PT_view'; bl_space_type = 'VIEW_3D'; bl_region_type = 'UI'; bl_category = 'Cinematic FX'
    draw = draw_panel


class CFX_PT_compositor(bpy.types.Panel):
    bl_label = 'Cinematic FX'; bl_idname = 'CFX_PT_compositor'; bl_space_type = 'NODE_EDITOR'; bl_region_type = 'UI'; bl_category = 'Cinematic FX'
    @classmethod
    def poll(cls, context): return context.space_data.tree_type == 'CompositorNodeTree'
    draw = draw_panel


classes = (CFX_Emitter, CFX_Settings, CFX_OT_install, CFX_OT_add_selected, CFX_OT_remove_emitter, CFX_OT_use_preset, CFX_OT_remove, CFX_PT_view, CFX_PT_compositor)


def register():
    for cls in classes: bpy.utils.register_class(cls)
    bpy.types.Scene.cinematic_fx = PointerProperty(type=CFX_Settings)
    for handlers in (bpy.app.handlers.frame_change_post, bpy.app.handlers.depsgraph_update_post):
        if refresh_emitters_handler not in handlers: handlers.append(refresh_emitters_handler)


def unregister():
    for handlers in (bpy.app.handlers.frame_change_post, bpy.app.handlers.depsgraph_update_post):
        if refresh_emitters_handler in handlers: handlers.remove(refresh_emitters_handler)
    del bpy.types.Scene.cinematic_fx
    for cls in reversed(classes): bpy.utils.unregister_class(cls)


if __name__ == '__main__':
    register()
