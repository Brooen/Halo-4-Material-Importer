"""Surface Self-Illumination Light – one-off material builder
======================================================
Based on srf_forerunner_lewis_lights, but removes palette mapping and wrap modes.
All fx_map_a, fx_map_b, and base_map use the same 'selfillum_map' bitmap parameter.
"""
import os
import struct
import bpy

# ── Helpers ─────────────────────────────────────────────────────────

def _make_tex(rel_path, base_path):
    """Load DDS bitmap (_00_00.dds) into Blender, set to Linear Rec.709 and channel-packed alpha."""
    if not rel_path:
        return None
    p = os.path.normpath(rel_path)
    full = os.path.join(base_path, 'images', f"{p}_00_00.dds")
    if not os.path.exists(full):
        print(f"[WARN] Missing texture file: {full}")
        return None
    img = bpy.data.images.load(full, check_existing=True)
    img.alpha_mode = 'CHANNEL_PACKED'
    img.colorspace_settings.name = 'Linear Rec.709'
    return img


def get_uv_node(mat, uv_name):
    """Return or create a UVMap node locked to uv_name."""
    for n in mat.node_tree.nodes:
        if n.type == 'UVMAP' and n.uv_map == uv_name:
            return n
    n = mat.node_tree.nodes.new('ShaderNodeUVMap')
    n.uv_map = uv_name
    n.label = f"UV {uv_name}"
    return n


def get_curve_from_db(tex_rel, idx, paths):
    key = f"{tex_rel}.bitmap"
    return idx.get(key, 1)


NODE_LOCATIONS = {
    'base_vec':    (-1200, 0),
    'fx_map_a_uv': (-2100, 150),
    'fx_map_a_map':(-1900, 150),
    'fx_map_a_tex':(-1500, 150),
    'fx_map_b_uv': (-2100, -200),
    'fx_map_b_map':(-1900, -200),
    'fx_map_b_tex':(-1500, -200),
    'base_map_uv': (-2100, -550),
    'base_map_tex':(-700, 0),
    'base_map_alpha_map':(-900, -300),
    'base_map_alpha_tex':(-700, -300),
    'main_group':  (-200, 0),
    'output':      (0, 0),
}


def build_material(material, params, context, h4ek_base_path, addon_directory):
    def loc(name):
        return NODE_LOCATIONS.get(name, (0,0))

    mat = material
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    nodes.clear()

    # load curve DB
    db_path = os.path.join(addon_directory, 'bitmap.db')
    idx, paths = {}, []
    try:
        with open(db_path, 'rb') as f:
            while True:
                b = bytearray()
                while (c := f.read(1)) and c != b'\x00':
                    b.append(c[0])
                if not b:
                    break
                raw = b.decode('ascii', errors='ignore')
                paths.append(raw)
                curve_id = struct.unpack('<B', f.read(1))[0]
                idx[raw] = {0x00:1,0x01:1.95,0x02:2,0x03:1,0x04:1,0x05:2.2}.get(curve_id,1)
    except FileNotFoundError:
        print(f"[WARN] bitmap.db not found at {db_path}")

    # base map vector group
    base_vec = nodes.new('ShaderNodeGroup')
    base_vec.node_tree = bpy.data.node_groups['srf_forerunner_lewis_lights selfillum_map_vector']
    base_vec.location = loc('base_vec')

    # all maps use 'selfillum_map'
    data = params.get('selfillum_map', {})
    tex = _make_tex(data.get('value'), h4ek_base_path)
    if tex:
        # scroll maps replace fx_map_a and fx_map_b
        names = ('scrolling_map1', 'scrolling_map2')
        for i, name in enumerate(names):
            uv = get_uv_node(mat, 'UVMap')
            uv.location = loc(f'fx_map_{"a" if i==0 else "b"}_uv')

            map_node = nodes.new('ShaderNodeMapping')
            map_node.vector_type = 'POINT'
            map_node.location = loc(f'fx_map_{"a" if i==0 else "b"}_map')
            # scale driven by params
            u_val = float(params.get(f'{name}_u', {}).get('value', 1.0))
            v_val = float(params.get(f'{name}_v', {}).get('value', 1.0))
            map_node.inputs['Scale'].default_value = (u_val, v_val, 1)
            # keep offset as before
            ox, oy = data.get('extra', {}).get('Offset', (0,0))
            map_node.inputs['Location'].default_value = (ox, oy, 0)

            tex_node = nodes.new('ShaderNodeTexImage')
            tex_node.image = tex
            tex_node.location = loc(f'fx_map_{"a" if i==0 else "b"}_tex')

            links.new(uv.outputs['UV'], map_node.inputs['Vector'])
            links.new(map_node.outputs['Vector'], tex_node.inputs['Vector'])
            links.new(tex_node.outputs['Color'], base_vec.inputs[name])

            # set curve on base_vec
            curve_val = get_curve_from_db(data.get('value'), idx, paths)
            input_curve = f'{name}_curve'
            if input_curve in base_vec.inputs:
                base_vec.inputs[input_curve].default_value = curve_val

        # base_map color
        uv_b = get_uv_node(mat, 'UVMap')
        uv_b.location = loc('base_map_uv')

        tex_b = nodes.new('ShaderNodeTexImage')
        tex_b.image = tex
        tex_b.location = loc('base_map_tex')
        links.new(base_vec.outputs['selfillum_map_vector'], tex_b.inputs['Vector'])

        # separate alpha with its own mapping
        uv_a = get_uv_node(mat, 'UVMap')
        uv_a.location = loc('base_map_uv')
        map_alpha = nodes.new('ShaderNodeMapping')
        map_alpha.vector_type = 'POINT'
        map_alpha.location = loc('base_map_alpha_map')
        sx, sy = data.get('extra', {}).get('Scale', (1,1))
        ox, oy = data.get('extra', {}).get('Offset', (0,0))
        map_alpha.inputs['Scale'].default_value = (sx, sy, 1)
        map_alpha.inputs['Location'].default_value = (ox, oy, 0)

        tex_alpha = nodes.new('ShaderNodeTexImage')
        tex_alpha.image = tex
        tex_alpha.location = loc('base_map_alpha_tex')
        links.new(uv_a.outputs['UV'], map_alpha.inputs['Vector'])
        links.new(map_alpha.outputs['Vector'], tex_alpha.inputs['Vector'])

    # main group
    main = nodes.new('ShaderNodeGroup')
    main.node_tree = bpy.data.node_groups['srf_forerunner_lewis_lights']
    main.location = loc('main_group')

    if tex:
        links.new(tex_b.outputs['Color'], main.inputs['selfillum_map'])
        links.new(tex_alpha.outputs['Alpha'], main.inputs['selfillum_map_alpha'])
        si_curve = get_curve_from_db(data.get('value'), idx, paths)
        if 'selfillum_map_curve' in main.inputs:
            main.inputs['selfillum_map_curve'].default_value = si_curve

    # blend, shadows, two-sided
    blend = float(params.get('Blend Mode', {}).get('value', 1.0))
    if '0 Opaque, .5 Additive, 1 Alpha Blend' in main.inputs:
        main.inputs['0 Opaque, .5 Additive, 1 Alpha Blend'].default_value = blend
    cast = bool(params.get('Cast shadows? [0-1]', {}).get('value', 1))
    if 'cull shadows' in main.inputs:
        main.inputs['cull shadows'].default_value = 1 if blend == 0.0 else cast
    if 'material is two-sided' in main.inputs:
        main.inputs['material is two-sided'].default_value = 1 if blend == 0.0 else cast

    # other parameters
    for name in (
        'si_intensity'
    ):
        if name in params and name in main.inputs:
            main.inputs[name].default_value = float(params[name]['value'])
    # color parameter
    for name in (
        'si_color',
    ):
        if name in params and name in main.inputs:
            col = params[name]['value']
            main.inputs[name].default_value = (
                col[1], col[2], col[3], col[0] if len(col) > 3 else 1.0
            )

    # output
    out = nodes.new('ShaderNodeOutputMaterial')
    out.location = loc('output')
    links.new(main.outputs['Shader'], out.inputs['Surface'])

    mat.blend_method = 'HASHED'
    mat.use_backface_culling = False

    print('surface_selfillum_light built.')
