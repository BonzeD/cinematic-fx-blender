bl_info = {
    'name': 'Cinematic FX — Camera Lens Flares',
    'author': 'Cinematic FX contributors',
    'version': (2, 0, 0),
    'blender': (5, 3, 0),
    'location': '3D View / Compositor > Sidebar > Cinematic FX',
    'description': 'Layered camera-space lens flares for selected scene sources',
    'category': 'Compositing',
}

import bpy
import math
from array import array
from bpy.props import BoolProperty, CollectionProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty, PointerProperty, StringProperty
from bpy.app.handlers import persistent
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

# Built-in texture recipes are generated on demand, then packed in the blend file.
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
    ('STAR4_FILLED', 'Four-point Star — Filled', 'Filled four-point star'),
    ('STAR6_FILLED', 'Six-point Star — Filled', 'Filled six-point star'),
    ('STAR8_FILLED', 'Eight-point Star — Filled', 'Filled eight-point star'),
    ('HEXAGON_FILLED', 'Hexagonal Aperture — Filled', 'Filled hexagonal aperture'),
    ('OCTAGON_FILLED', 'Octagonal Aperture — Filled', 'Filled octagonal aperture'),
    ('PETALS_FILLED', 'Iris Petals — Filled', 'Filled petal shape'),
    ('HALO_FILLED', 'Halo Disc — Filled', 'Filled circular halo'),
    ('GHOSTS_FILLED', 'Lens Ghosts — Filled', 'Filled ghost discs'),
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
    elif kind in {'STAR4_FILLED', 'STAR6_FILLED', 'STAR8_FILLED'}:
        count = {'STAR4_FILLED': 4, 'STAR6_FILLED': 6, 'STAR8_FILLED': 8}[kind]
        boundary = 0.15 + 0.40 * abs(math.cos(a * count / 2.0)) ** 3
        v = 0.85 * max(0.0, min(1.0, (boundary - r) / 0.018 + 0.5))
    elif kind in {'HEXAGON_FILLED', 'OCTAGON_FILLED'}:
        count = 6 if kind == 'HEXAGON_FILLED' else 8
        polygon_radius = max(x * math.cos(i * math.tau / count) + y * math.sin(i * math.tau / count) for i in range(count))
        v = 0.85 * max(0.0, min(1.0, (0.52 - polygon_radius) / 0.018 + 0.5))
    elif kind == 'PETALS_FILLED':
        petal_radius = 0.36 + 0.13 * math.cos(8.0 * a)
        v = 0.85 * max(0.0, min(1.0, (petal_radius - r) / 0.018 + 0.5))
    elif kind == 'HALO_FILLED':
        v = 0.85 * max(0.0, min(1.0, (0.58 - r) / 0.018 + 0.5))
    elif kind == 'GHOSTS_FILLED':
        v = 0.0
        for cx, cy, size, intensity in [(-0.55, -0.18, 0.15, 0.55), (-0.28, -0.09, 0.08, 0.7),
                                         (0.25, 0.08, 0.10, 0.55), (0.52, 0.17, 0.17, 0.4)]:
            d = math.hypot(x - cx, y - cy)
            v += intensity * max(0.0, min(1.0, (size - d) / 0.018 + 0.5))
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


# A flare layer is an optical overlay. It is NEVER treated as a scene highlight
# or fed back into Glare. The position of each ghost is on the source-center axis.
_busy = False


def socket(collection, identifier):
    return next((s for s in collection if s.identifier == identifier), None) or next(s for s in collection if s.name == identifier)


def set_value(sock, value, epsilon=1e-5):
    old = sock.default_value
    if isinstance(value, (tuple, list)):
        if len(old) == len(value) and all(abs(a-b) < epsilon for a,b in zip(old, value)):
            return
    elif abs(old-value) < epsilon:
        return
    sock.default_value = value


def make_node(tree, typ, name, x, y):
    n = tree.nodes.new(typ); n.name = n.label = name; n.location = (x, y)
    return n


def connect(tree, source, output, target, inp):
    a, b = socket(source.outputs, output), socket(target.inputs, inp)
    if not b.is_linked or b.links[0].from_socket != a:
        tree.links.new(a, b)


def mix_node(tree, name, x, y, mode):
    n = make_node(tree, 'ShaderNodeMix', name, x, y)
    n.data_type = 'RGBA'; n.blend_type = mode; n.clamp_factor = True; n.clamp_result = False
    socket(n.inputs, 'Factor_Float').default_value = 1.0
    return n


def is_v2(tree):
    return bool(tree and tree.get('cfx_lens_version') == 2)


def local_tree(scene, settings):
    tree = settings.node_group
    if not tree or not is_v2(tree): return tree
    # A duplicated scene can share a node group; never change another scene.
    for other in bpy.data.scenes:
        if other != scene and any(e.node_group == tree for e in other.compositor_effects):
            copy = tree.copy()
            for effect in scene.compositor_effects:
                if effect.node_group == tree: effect.node_group = copy
            settings.node_group = copy
            return copy
    return tree


def build_tree():
    tree = bpy.data.node_groups.new('Cinematic FX Lens Flare', 'CompositorNodeTree')
    try:
        tree['cfx_lens_version'] = 2
        tree.interface.new_socket(name='Image', in_out='INPUT', socket_type='NodeSocketColor')
        tree.interface.new_socket(name='Image', in_out='OUTPUT', socket_type='NodeSocketColor')
        inp = make_node(tree, 'NodeGroupInput', 'Input', -900, 600)
        out = make_node(tree, 'NodeGroupOutput', 'Output', 1000, 600)
        # Optional highlight-driven bloom uses actual rendered pixels and sees their occlusion.
        glare = make_node(tree, 'CompositorNodeGlare', 'Highlight Bloom', -650, 650)
        glare.inputs['Type'].default_value = 'Bloom'
        glare.inputs['Quality'].default_value = 'Low'
        connect(tree, inp, 'Image', glare, 'Image')
        combine = mix_node(tree, 'Bloom + Lens Layers', -350, 600, 'ADD')
        connect(tree, inp, 'Image', combine, 'A_Color')
        connect(tree, glare, 'Glare', combine, 'B_Color')
        mask = make_node(tree, 'CompositorNodeImage', 'Screen Mask', -900, -150)
        maskfit = make_node(tree, 'CompositorNodeScale', 'Screen Mask Fit', -700, -150)
        maskfit.inputs['Type'].default_value = 'Render Size'
        maskbw = make_node(tree, 'CompositorNodeRGBToBW', 'Screen Mask Luminance', -500, -150)
        connect(tree, mask, 'Image', maskfit, 'Image'); connect(tree, maskfit, 'Image', maskbw, 'Image')
        separate = make_node(tree, 'CompositorNodeSeparateColor', 'Original Alpha', 450, 200)
        setalpha = make_node(tree, 'CompositorNodeSetAlpha', 'Preserve Alpha', 750, 600)
        setalpha.inputs['Type'].default_value = 'Replace Alpha'
        connect(tree, inp, 'Image', separate, 'Image')
        connect(tree, separate, 'Alpha', setalpha, 'Alpha')
        connect(tree, combine, 'Result_Color', setalpha, 'Image')
        connect(tree, setalpha, 'Image', out, 'Image')
        return tree
    except Exception:
        bpy.data.node_groups.remove(tree)
        raise


def emitter_projection(scene, entry, depsgraph):
    """Return frame coordinates or None. Ray casts are geometric, not optical."""
    camera, obj = scene.camera, entry.object
    if not camera or camera.data.type not in {'PERSP', 'ORTHO'} or not obj or not entry.enabled or obj.name not in scene.objects or obj.hide_render:
        return None
    if obj.type == 'LIGHT' and obj.data.energy <= 0:
        return None
    if obj.name not in depsgraph.view_layer.objects:
        return None
    try:
        camera_eval = camera.evaluated_get(depsgraph)
        obj_eval = obj.evaluated_get(depsgraph)
        origin = camera_eval.matrix_world.translation.copy()
        is_sun = obj.type == 'LIGHT' and obj.data and obj.data.type == 'SUN'
        if is_sun:
            # Sun is directional, not positional. Orthographic direction has no
            # unique screen position, so reject it instead of showing a phantom.
            if camera.data.type != 'PERSP': return None
            direction = (obj_eval.matrix_world.to_quaternion() @ Vector((0, 0, 1))).normalized()
            point = origin + direction * max(10.0, min(camera.data.clip_end * 0.5, 1000.0))
        else:
            point = obj_eval.matrix_world.translation.copy()
        projected = world_to_camera_view(scene, camera_eval, point)
        x, y = float(projected.x), float(projected.y)
        if projected.z <= camera.data.clip_start or (not is_sun and projected.z >= camera.data.clip_end): return None
        if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0): return None
        if entry.occlusion:
            if camera.data.type == 'ORTHO' and not is_sun:
                # Orthographic camera rays are parallel, not from its center.
                forward = camera_eval.matrix_world.to_quaternion() @ Vector((0, 0, -1))
                delta = point - origin
                origin += delta - forward * delta.dot(forward)
            delta = point - origin
            distance = (camera.data.clip_end if is_sun else delta.length)
            if distance > 1e-5:
                direction = delta.normalized()
                hit, _, _, _, hit_obj, _ = scene.ray_cast(depsgraph, origin + direction * 1e-4, direction, distance=max(0.0, distance-2e-4))
                # An emitter mesh itself is visible if it is the first hit.
                if hit and (is_sun or not hit_obj or hit_obj.original != obj.original): return None
        return (x, y)
    except (ReferenceError, AttributeError, ValueError, RuntimeError, ZeroDivisionError):
        return None


def ensure_layers(settings):
    global _busy
    was_busy = _busy; _busy = True
    try:
        initial = [('STAR6', 0.42, (1.0, 0.86, 0.68, 1.0), 'SOURCE', 0.0, 1.0),
                   ('ANAMORPHIC', 0.95, (0.45, 0.65, 1.0, 1.0), 'SOURCE', 0.0, 0.45),
                   ('HEXAGON_FILLED', 0.12, (0.45, 0.65, 1.0, 1.0), 'GHOST', 1.5, 0.22)]
        while len(settings.ray_layers) < settings.ray_layer_count:
            i = len(settings.ray_layers); layer = settings.ray_layers.add()
            if i < len(initial):
                layer.preset, layer.size, layer.color, layer.role, layer.axis_position, layer.intensity = initial[i]
            layer.image = preset_image(layer.preset)
    finally:
        _busy = was_busy


def rebuild(scene, settings):
    tree = local_tree(scene, settings)
    if not is_v2(tree): return
    ensure_layers(settings)
    count = len(settings.emitters); layers = min(settings.ray_layer_count, len(settings.ray_layers))
    signature = '4:%d:%d' % (count, layers)
    # Preserve per-layer gradient controls across graph rebuilds.
    for j in range(layers):
        if not tree.nodes.get('Layer Gradient %d' % j):
            ramp = make_node(tree, 'ShaderNodeValToRGB', 'Layer Gradient %d' % j, -1100, -300 - j*200)
            ramp.color_ramp.elements[0].color = (1,1,1,1)
            ramp.color_ramp.elements[1].color = (1,1,1,1)
    if tree.get('cfx_signature') == signature:
        # Also ensure that user deletion of managed nodes is repaired.
        prefixes = ('Lens Image ', 'Lens Luminance ', 'Lens Ramp ', 'Lens Gradient Tint ', 'Lens Fit ', 'Lens Transform ', 'Lens Softness ', 'Lens Tint ', 'Lens Gain ', 'Lens Mix ', 'Lens Mix Mask ')
        if all(tree.nodes.get(prefix + '%d %d' % (i,j)) for i in range(count) for j in range(layers) for prefix in prefixes):
            return
    for n in list(tree.nodes):
        if n.get('cfx_managed'): tree.nodes.remove(n)
    previous, out = tree.nodes['Bloom + Lens Layers'], 'Result_Color'
    for i in range(count):
        for j in range(layers):
            key = '%d %d' % (i,j); y = -300 - 250*(i*layers+j)
            image = make_node(tree, 'CompositorNodeImage', 'Lens Image '+key, -850, y)
            bw = make_node(tree, 'CompositorNodeRGBToBW', 'Lens Luminance '+key, -850, y-100)
            # Each source has its own ramp node; its settings are synchronized
            # from the shared editable layer ramp in refresh().
            grad = make_node(tree, 'ShaderNodeValToRGB', 'Lens Ramp '+key, -650, y-100)
            gradmix = mix_node(tree, 'Lens Gradient Tint '+key, -550, y-100, 'MULTIPLY')
            scale = make_node(tree, 'CompositorNodeScale', 'Lens Fit '+key, -650, y)
            scale.inputs['Type'].default_value = 'Render Size'
            scale.inputs['Frame Type'].default_value = 'Fit'
            transform = make_node(tree, 'CompositorNodeTransform', 'Lens Transform '+key, -450, y)
            blur = make_node(tree, 'CompositorNodeBlur', 'Lens Softness '+key, -300, y-50)
            tint = mix_node(tree, 'Lens Tint '+key, -250, y, 'MULTIPLY')
            gain = make_node(tree, 'CompositorNodeColorCorrection', 'Lens Gain '+key, -50, y)
            mix = mix_node(tree, 'Lens Mix '+key, 150, y, 'ADD')
            mask = make_node(tree, 'CompositorNodeRGBToBW', 'Lens Mix Mask '+key, 0, y-100)
            for n in (image, bw, grad, gradmix, scale, transform, blur, tint, gain, mix, mask): n['cfx_managed'] = True
            connect(tree, image, 'Image', bw, 'Image'); connect(tree, bw, 'Val', grad, 'Fac')
            connect(tree, image, 'Image', gradmix, 'A_Color'); connect(tree, grad, 'Color', gradmix, 'B_Color')
            connect(tree, gradmix, 'Result_Color', scale, 'Image'); connect(tree, scale, 'Image', transform, 'Image')
            connect(tree, transform, 'Image', blur, 'Image'); connect(tree, blur, 'Image', tint, 'A_Color'); connect(tree, tint, 'Result_Color', gain, 'Image')
            connect(tree, blur, 'Image', mask, 'Image')
            connect(tree, previous, out, mix, 'A_Color'); connect(tree, gain, 'Image', mix, 'B_Color')
            previous, out = mix, 'Result_Color'
    connect(tree, previous, out, tree.nodes['Preserve Alpha'], 'Image')
    tree['cfx_signature'] = signature


def refresh(scene, settings, depsgraph=None, force_rebuild=False):
    global _busy
    if _busy or not scene or not scene.is_editable or not is_v2(settings.node_group): return
    _busy = True
    try:
        if force_rebuild: rebuild(scene, settings)
        tree = local_tree(scene, settings)
        if depsgraph is None:
            if bpy.context.scene == scene:
                depsgraph = bpy.context.evaluated_depsgraph_get()
            else:
                with bpy.context.temp_override(scene=scene, view_layer=scene.view_layers[0]):
                    depsgraph = bpy.context.evaluated_depsgraph_get()
        width = scene.render.resolution_x * scene.render.resolution_percentage / 100.0
        height = scene.render.resolution_y * scene.render.resolution_percentage / 100.0
        mask_image = tree.nodes['Screen Mask']
        if mask_image.image != settings.lens_mask_image: mask_image.image = settings.lens_mask_image
        glare = tree.nodes['Highlight Bloom']
        combine = tree.nodes['Bloom + Lens Layers']
        target = socket(combine.inputs, 'B_Color')
        if settings.bloom_strength > 0:
            connect(tree, glare, 'Glare', combine, 'B_Color')
        else:
            for old in list(target.links): tree.links.remove(old)
            set_value(target, (0.0, 0.0, 0.0, 1.0))
        set_value(glare.inputs['Strength'], settings.bloom_strength)
        set_value(glare.inputs['Size'], settings.bloom_size)
        set_value(socket(glare.inputs, 'Highlights Threshold'), settings.threshold)
        if glare.inputs['Quality'].default_value != settings.bloom_quality:
            glare.inputs['Quality'].default_value = settings.bloom_quality
        for i, entry in enumerate(settings.emitters):
            p = emitter_projection(scene, entry, depsgraph)
            for j, layer in enumerate(settings.ray_layers[:settings.ray_layer_count]):
                key = '%d %d' % (i,j)
                image = tree.nodes.get('Lens Image '+key); transform = tree.nodes.get('Lens Transform '+key)
                tint = tree.nodes.get('Lens Tint '+key); blur = tree.nodes.get('Lens Softness '+key); gain = tree.nodes.get('Lens Gain '+key); mix = tree.nodes.get('Lens Mix '+key)
                if not all((image, transform, blur, tint, gain, mix)): continue
                set_value(blur.inputs['Size'], (layer.softness, layer.softness))
                if image.image != layer.image: image.image = layer.image
                if mix.blend_type != settings.blend_mode: mix.blend_type = settings.blend_mode
                ramp = tree.nodes['Layer Gradient %d' % j].color_ramp
                duplicate = tree.nodes['Lens Ramp '+key].color_ramp
                # Copy even user-added ramp stops without needlessly invalidating nodes.
                if layer.use_gradient:
                    while len(duplicate.elements) < len(ramp.elements): duplicate.elements.new(0.5)
                    while len(duplicate.elements) > len(ramp.elements): duplicate.elements.remove(duplicate.elements[-1])
                    if duplicate.interpolation != ramp.interpolation: duplicate.interpolation = ramp.interpolation
                    for src,dst in zip(ramp.elements, duplicate.elements):
                        if abs(src.position-dst.position)>1e-5: dst.position=src.position
                        if any(abs(x-y)>1e-5 for x,y in zip(src.color,dst.color)): dst.color=src.color
                else:
                    while len(duplicate.elements)>2: duplicate.elements.remove(duplicate.elements[-1])
                    for e in duplicate.elements:
                        if tuple(e.color)!=(1.0,1.0,1.0,1.0): e.color=(1,1,1,1)
                factor = settings.opacity if p and layer.enabled and layer.image else 0.0
                factor_socket = socket(mix.inputs, 'Factor_Float')
                # Mix must not darken the rest of the image with a black rectangle.
                # The math node limits the mix to texture luminance.
                math_name='Lens Opacity '+key
                math_node=tree.nodes.get(math_name)
                if not math_node:
                    math_node=make_node(tree, 'ShaderNodeMath', math_name, 100, -100); math_node.operation='MULTIPLY'; math_node['cfx_managed']=True
                    connect(tree, tree.nodes['Lens Mix Mask '+key], 'Val', math_node, 'Value')
                set_value(math_node.inputs[1], factor)
                mask_name='Lens Screen Opacity '+key
                mask_node=tree.nodes.get(mask_name)
                if not mask_node:
                    mask_node=make_node(tree, 'ShaderNodeMath', mask_name, 100, -250); mask_node.operation='MULTIPLY'; mask_node['cfx_managed']=True
                    connect(tree, tree.nodes['Screen Mask Luminance'], 'Val', mask_node, 'Value')
                second=mask_node.inputs[1]
                if settings.blend_mode == 'MIX': connect(tree, math_node, 'Value', mask_node, second.identifier)
                else:
                    for old in list(second.links): tree.links.remove(old)
                    set_value(second, factor)
                if settings.lens_mask and settings.lens_mask_image:
                    connect(tree, mask_node, 'Value', mix, 'Factor_Float')
                elif settings.blend_mode == 'MIX':
                    connect(tree, math_node, 'Value', mix, 'Factor_Float')
                else:
                    for old in list(factor_socket.links): tree.links.remove(old)
                    set_value(factor_socket, factor)
                color = layer.color
                if entry.use_light_color and entry.object and entry.object.type == 'LIGHT':
                    light = entry.object.data.color
                    color = (color[0]*light[0], color[1]*light[1], color[2]*light[2], color[3])
                set_value(socket(tint.inputs, 'B_Color'), tuple(color))
                set_value(socket(gain.inputs, 'Master Gain'), settings.intensity * entry.strength * layer.intensity)
                if p:
                    # 0=source, 1=frame center, 2=mirrored across center.
                    t = layer.axis_position if layer.role == 'GHOST' else 0.0
                    x = p[0] + (0.5-p[0])*t + layer.offset[0]
                    y = p[1] + (0.5-p[1])*t + layer.offset[1]
                    set_value(transform.inputs['X'], (x-0.5)*width)
                    set_value(transform.inputs['Y'], (y-0.5)*height)
                    set_value(transform.inputs['Scale'], layer.size)
                    set_value(transform.inputs['Angle'], layer.rotation)
        settings.last_error = ''
    except (KeyError, AttributeError, TypeError, ValueError, ReferenceError, RuntimeError, StopIteration) as exc:
        settings.last_error = str(exc)[:240] or type(exc).__name__
        print('Cinematic FX:', settings.last_error)
    finally:
        _busy = False


def changed(self, context):
    if _busy: return
    scene = self.id_data
    if scene and hasattr(scene, 'cinematic_fx'):
        refresh(scene, scene.cinematic_fx, force_rebuild=True)


def preset_changed(self, context):
    if _busy: return
    if self.preset != 'CUSTOM':
        self.image = preset_image(self.preset)
    else:
        changed(self, context)


class CFX_Emitter(bpy.types.PropertyGroup):
    object: PointerProperty(name='Source', type=bpy.types.Object, update=changed)
    enabled: BoolProperty(name='Enabled', default=True, update=changed)
    strength: FloatProperty(name='Intensity', default=1.0, min=0.0, max=50.0, update=changed)
    occlusion: BoolProperty(name='Occlusion', description='Geometric ray cast to source origin (opaque approximation)', default=True, update=changed)
    use_light_color: BoolProperty(name='Use Light Color', default=False, update=changed)


class CFX_RayLayer(bpy.types.PropertyGroup):
    enabled: BoolProperty(name='Enabled', default=True, update=changed)
    preset: EnumProperty(name='Texture', items=PRESETS + (('CUSTOM', 'Custom Image', 'Choose an image'),), default='ANAMORPHIC', update=preset_changed)
    image: PointerProperty(name='Image', type=bpy.types.Image, update=changed)
    size: FloatProperty(name='Size', default=0.5, min=0.01, max=4.0, update=changed)
    color: FloatVectorProperty(name='Color', subtype='COLOR', size=4, default=(1,1,1,1), min=0, max=1, update=changed)
    rotation: FloatProperty(name='Rotation', subtype='ANGLE', default=0, update=changed)
    offset: FloatVectorProperty(name='Offset (frame)', size=2, default=(0,0), min=-2, max=2, update=changed)
    softness: FloatProperty(name='Softness (px)', default=0, min=0, max=30, update=changed)
    use_gradient: BoolProperty(name='Color Gradient', default=False, update=changed)
    role: EnumProperty(name='Placement', items=[('SOURCE','At Source','Centered on source'),('GHOST','Lens Ghost','Position along source-to-center axis')], default='SOURCE', update=changed)
    axis_position: FloatProperty(name='Axis Position', description='0: source; 1: frame center; 2: opposite side', default=1.5, min=-5, max=5, update=changed)
    intensity: FloatProperty(name='Intensity', default=1, min=0, max=20, update=changed)


class CFX_Settings(bpy.types.PropertyGroup):
    # The existing names deliberately remain for migration of 1.x scenes.
    last_error: StringProperty(name='Last Error', default='', options={'HIDDEN'})
    node_group: PointerProperty(type=bpy.types.NodeTree)
    emitters: CollectionProperty(type=CFX_Emitter)
    ray_layers: CollectionProperty(type=CFX_RayLayer)
    ray_layer_count: IntProperty(name='Layers', default=3, min=1, max=12, update=changed)
    intensity: FloatProperty(name='Master Intensity', default=1, min=0, max=20, update=changed)
    opacity: FloatProperty(name='Opacity', default=0.8, min=0, max=1, subtype='FACTOR', update=changed)
    blend_mode: EnumProperty(name='Blend Mode', items=[('ADD','Add','Additive optical light'),('SCREEN','Screen','Screen blend'),('MIX','Mix','Mix colors')], default='ADD', update=changed)
    lens_mask: BoolProperty(name='Use Screen Mask', description='Mask lens layers using a screen-space image', default=False, update=changed)
    lens_mask_image: PointerProperty(name='Screen Mask', type=bpy.types.Image, update=changed)
    bloom_strength: FloatProperty(name='Highlight Bloom', description='Bloom generated from bright rendered pixels', default=0, min=0, max=10, update=changed)
    bloom_size: FloatProperty(name='Bloom Size', default=0.4, min=0, max=1, update=changed)
    bloom_quality: EnumProperty(name='Bloom Quality', items=[('Low','Low','Fastest'),('Medium','Medium','Balanced'),('High','High','Full resolution')], default='Low', update=changed)
    threshold: FloatProperty(name='Bloom Threshold', default=1.0, min=0, max=100, update=changed)


class CFX_OT_install(bpy.types.Operator):
    bl_idname = 'cinematic_fx.install'; bl_label = 'Add / Upgrade Lens Flare'; bl_options = {'REGISTER', 'UNDO'}
    def execute(self, context):
        scene = context.scene; s = scene.cinematic_fx; old = s.node_group
        if is_v2(old) and any(e.node_group == old for e in scene.compositor_effects):
            self.report({'INFO'}, 'Lens flare already installed'); return {'CANCELLED'}
        tree = effect = None
        try:
            tree = build_tree(); effect = scene.compositor_effects.new('Cinematic FX Lens Flare')
            effect.enable_for_preview = False; effect.node_group = tree; s.node_group = tree
            rebuild(scene, s); refresh(scene, s)
            if s.last_error: raise RuntimeError(s.last_error)
            # Preserve old node tree and settings, but prevent doubled/phantom flares.
            if old and not is_v2(old):
                for e in scene.compositor_effects:
                    if e.node_group == old:
                        e.enable_for_preview = False; e.enable_for_render = False
        except Exception as exc:
            s.node_group = old
            if effect: scene.compositor_effects.remove(effect)
            if tree and tree.users == 0: bpy.data.node_groups.remove(tree)
            self.report({'ERROR'}, 'Could not create lens flare: ' + str(exc)); return {'CANCELLED'}
        self.report({'INFO'}, 'Lens flare added; any previous Cinematic FX effect was disabled')
        return {'FINISHED'}


class CFX_OT_add_selected(bpy.types.Operator):
    bl_idname = 'cinematic_fx.add_selected'; bl_label = 'Add Selected Sources'; bl_options = {'REGISTER','UNDO'}
    def execute(self, context):
        global _busy
        s = context.scene.cinematic_fx
        existing = {e.object for e in s.emitters if e.object}
        selected = [o for o in context.view_layer.objects if o.select_get() and o not in existing and o.type in {'LIGHT','MESH','CURVE','EMPTY'}]
        if not selected:
            self.report({'WARNING'}, 'Select new light, mesh, curve or empty objects in the 3D View'); return {'CANCELLED'}
        if len(s.emitters)+len(selected)>8:
            self.report({'ERROR'}, 'Maximum 8 sources; use fewer to keep preview responsive'); return {'CANCELLED'}
        _busy = True
        try:
            for obj in selected:
                e = s.emitters.add(); e.object = obj
        finally: _busy = False
        refresh(context.scene, s, force_rebuild=True)
        return {'FINISHED'}


class CFX_OT_remove_emitter(bpy.types.Operator):
    bl_idname = 'cinematic_fx.remove_emitter'; bl_label = 'Remove Source'; bl_options = {'REGISTER','UNDO'}
    index: IntProperty()
    def execute(self, context):
        s = context.scene.cinematic_fx
        if not 0 <= self.index < len(s.emitters): return {'CANCELLED'}
        s.emitters.remove(self.index); refresh(context.scene, s, force_rebuild=True); return {'FINISHED'}


class CFX_OT_remove(bpy.types.Operator):
    bl_idname = 'cinematic_fx.remove'; bl_label = 'Remove Lens Flare'; bl_options = {'REGISTER','UNDO'}
    def execute(self, context):
        scene=context.scene; s=scene.cinematic_fx; tree=s.node_group
        if not is_v2(tree): return {'CANCELLED'}
        for effect in list(scene.compositor_effects):
            if effect.node_group == tree: scene.compositor_effects.remove(effect)
        s.node_group = None
        if tree.users == 0: bpy.data.node_groups.remove(tree)
        return {'FINISHED'}


class CFX_OT_refresh(bpy.types.Operator):
    bl_idname = 'cinematic_fx.refresh'; bl_label = 'Refresh Lens Flare'; bl_options = {'REGISTER'}
    def execute(self, context):
        s=context.scene.cinematic_fx; refresh(context.scene, s, force_rebuild=True)
        if s.last_error: self.report({'ERROR'}, s.last_error); return {'CANCELLED'}
        return {'FINISHED'}


def draw_panel(self, context):
    scene=context.scene; s=scene.cinematic_fx; layout=self.layout
    if not is_v2(s.node_group):
        if s.node_group:
            layout.label(text='Legacy 1.x effect found', icon='INFO')
            layout.label(text='Upgrade disables it, preserves its nodes')
        layout.operator('cinematic_fx.install', icon='ADD')
        return
    row=layout.row(align=True); row.operator('cinematic_fx.refresh', icon='FILE_REFRESH'); row.operator('cinematic_fx.remove', text='', icon='REMOVE')
    if s.last_error: layout.label(text=s.last_error[:90], icon='ERROR')
    effects=[e for e in scene.compositor_effects if e.node_group == s.node_group]
    if effects:
        layout.prop(effects[0], 'enable_for_preview', text='Viewport Preview (camera view)')
        if effects[0].enable_for_preview: layout.label(text='Preview may be slow; use camera view', icon='INFO')
    else: layout.label(text='Effect missing from stack', icon='ERROR'); layout.operator('cinematic_fx.install')
    if not scene.camera: layout.label(text='Set a scene camera', icon='ERROR')
    box=layout.box(); box.label(text='Sources', icon='LIGHT'); box.operator('cinematic_fx.add_selected', icon='ADD')
    if not s.emitters: box.label(text='Select a light or emitter in 3D View', icon='INFO')
    for i,e in enumerate(s.emitters):
        sub=box.box(); row=sub.row(align=True); row.prop(e,'enabled',text=''); row.prop(e,'object',text=''); row.operator('cinematic_fx.remove_emitter',text='',icon='X').index=i
        sub.prop(e,'strength'); sub.prop(e,'occlusion')
        if e.object and e.object.type == 'LIGHT': sub.prop(e,'use_light_color')
    box=layout.box(); box.label(text='Lens Layers', icon='IMAGE_DATA'); box.prop(s,'ray_layer_count')
    for i, layer in enumerate(s.ray_layers[:s.ray_layer_count]):
        sub=box.box(); row=sub.row(); row.prop(layer,'enabled',text='Layer %d' % (i+1)); sub.prop(layer,'role')
        if layer.role == 'GHOST': sub.prop(layer,'axis_position')
        sub.prop(layer,'preset')
        if layer.preset == 'CUSTOM': sub.template_ID_preview(layer,'image',open='image.open',rows=2,cols=4)
        elif layer.image: sub.template_ID_preview(layer,'image',open='image.open',rows=2,cols=4)
        sub.prop(layer,'use_gradient')
        ramp=s.node_group.nodes.get('Layer Gradient %d' % i)
        if layer.use_gradient and ramp: sub.template_color_ramp(ramp, 'color_ramp', expand=True)
        sub.prop(layer,'size'); sub.prop(layer,'color'); sub.prop(layer,'intensity'); sub.prop(layer,'softness'); sub.prop(layer,'rotation'); sub.prop(layer,'offset')
    box=layout.box(); box.label(text='Composite'); box.prop(s,'intensity'); box.prop(s,'opacity'); box.prop(s,'blend_mode'); box.prop(s,'lens_mask')
    if s.lens_mask: box.template_ID_preview(s,'lens_mask_image',open='image.open',rows=2,cols=4)
    box=layout.box(); box.label(text='Rendered Highlights'); box.prop(s,'bloom_strength')
    if s.bloom_strength > 0: box.prop(s,'threshold'); box.prop(s,'bloom_size'); box.prop(s,'bloom_quality')
    layout.label(text='Optical effect, not real volumetrics', icon='INFO')


class CFX_PT_view(bpy.types.Panel):
    bl_label='Cinematic FX'; bl_idname='CFX_PT_view'; bl_space_type='VIEW_3D'; bl_region_type='UI'; bl_category='Cinematic FX'
    draw=draw_panel


class CFX_PT_compositor(bpy.types.Panel):
    bl_label='Cinematic FX'; bl_idname='CFX_PT_compositor'; bl_space_type='NODE_EDITOR'; bl_region_type='UI'; bl_category='Cinematic FX'
    @classmethod
    def poll(cls, context): return context.space_data.tree_type == 'CompositorNodeTree'
    draw=draw_panel


def preview_enabled(scene, settings):
    return any(e.node_group == settings.node_group and e.enable_for_preview for e in scene.compositor_effects)


@persistent
def depsgraph_handler(scene, depsgraph):
    s=getattr(scene, 'cinematic_fx', None)
    if s and is_v2(s.node_group) and preview_enabled(scene, s): refresh(scene, s, depsgraph)


@persistent
def frame_handler(scene, depsgraph=None):
    s=getattr(scene, 'cinematic_fx', None)
    if s and is_v2(s.node_group) and preview_enabled(scene, s): refresh(scene, s, depsgraph, force_rebuild=True)


@persistent
def render_handler(scene, depsgraph=None):
    s=getattr(scene, 'cinematic_fx', None)
    if s and is_v2(s.node_group): refresh(scene, s, depsgraph, force_rebuild=True)


@persistent
def migrate_on_load(_dummy):
    # Do not run old effects in the viewport until the user upgrades them.
    for scene in bpy.data.scenes:
        s=getattr(scene, 'cinematic_fx', None)
        if s and s.node_group and not is_v2(s.node_group) and scene.is_editable:
            for effect in scene.compositor_effects:
                if effect.node_group == s.node_group: effect.enable_for_preview=False


def migrate_after_enable():
    # register() can run under Blender's RestrictBlend: bpy.data.scenes is unavailable.
    if not hasattr(bpy.data, 'scenes'): return 0.1
    migrate_on_load(None); return None


classes=(CFX_Emitter, CFX_RayLayer, CFX_Settings, CFX_OT_install, CFX_OT_add_selected, CFX_OT_remove_emitter, CFX_OT_remove, CFX_OT_refresh, CFX_PT_view, CFX_PT_compositor)


def register():
    for cls in classes: bpy.utils.register_class(cls)
    bpy.types.Scene.cinematic_fx=PointerProperty(type=CFX_Settings)
    for handlers, fn in ((bpy.app.handlers.load_post,migrate_on_load), (bpy.app.handlers.depsgraph_update_post,depsgraph_handler), (bpy.app.handlers.frame_change_post,frame_handler), (bpy.app.handlers.render_pre,render_handler)):
        if fn not in handlers: handlers.append(fn)
    if not bpy.app.timers.is_registered(migrate_after_enable): bpy.app.timers.register(migrate_after_enable, first_interval=0.1)


def unregister():
    if bpy.app.timers.is_registered(migrate_after_enable): bpy.app.timers.unregister(migrate_after_enable)
    for handlers, fn in ((bpy.app.handlers.load_post,migrate_on_load), (bpy.app.handlers.depsgraph_update_post,depsgraph_handler), (bpy.app.handlers.frame_change_post,frame_handler), (bpy.app.handlers.render_pre,render_handler)):
        if fn in handlers: handlers.remove(fn)
    del bpy.types.Scene.cinematic_fx
    for cls in reversed(classes): bpy.utils.unregister_class(cls)


if __name__ == '__main__': register()
