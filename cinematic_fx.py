bl_info = {
    'name': 'Cinematic FX',
    'author': 'Cinematic FX contributors',
    'version': (1, 0, 0),
    'blender': (5, 3, 0),
    'location': '3D View / Compositor > Sidebar > Cinematic FX',
    'description': 'Non-destructive cinematic rays, streaks, glow and masks',
    'category': 'Compositing',
}

import bpy
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty,
                       IntProperty, PointerProperty)


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
        source = n['Custom Texture Mapping'] if self.source_type == 'TEXTURE' and self.texture else n['Input']
        for name in ('Sun Beams', 'Streaks', 'Glow', 'Caustic Look'):
            link(t, source, 'Image', n[name], 'Image')
            n[name].inputs['Threshold'].default_value = self.threshold
            n[name].inputs['Smoothness'].default_value = self.edge_smoothness
        sun, streak, glow, ghost = (n[x] for x in ('Sun Beams', 'Streaks', 'Glow', 'Caustic Look'))
        sun.inputs['Sun Position'].default_value = (self.sun_position[0], self.sun_position[1])
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


class CFX_Settings(bpy.types.PropertyGroup):
    node_group: PointerProperty(type=bpy.types.NodeTree)
    source_type: EnumProperty(name='Source Type', items=[('SOURCE','Source','Scene image'),('TEXTURE','Texture','Use the custom image as effect source')], default='SOURCE', update=update_settings)
    texture: PointerProperty(name='Custom Texture', type=bpy.types.Image, update=update_settings)
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
    box.template_ID_preview(s, 'texture', open='image.open', rows=2, cols=4)
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


classes = (CFX_Settings, CFX_OT_install, CFX_OT_remove, CFX_PT_view, CFX_PT_compositor)


def register():
    for cls in classes: bpy.utils.register_class(cls)
    bpy.types.Scene.cinematic_fx = PointerProperty(type=CFX_Settings)


def unregister():
    del bpy.types.Scene.cinematic_fx
    for cls in reversed(classes): bpy.utils.unregister_class(cls)


if __name__ == '__main__':
    register()
