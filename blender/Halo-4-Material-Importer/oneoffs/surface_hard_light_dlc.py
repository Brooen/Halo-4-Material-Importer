"""Surface Hard Light – one‑off material builder
================================================
This standalone module is auto‑loaded when the shader name is `surface_hard_light`.
It defines its own helpers (texture loading, UV nodes, mapping correction, bitmap DB lookup)
and constructs the custom node layout without importing from material_importer.
"""
import os
import struct
import bpy

# ── Helpers ─────────────────────────────────────────────────────────

def load_bitmap_db(addon_directory):
    """Load bitmap.db from the H4EK base path."""
    db_path = os.path.join(addon_directory, 'bitmap.db')
    curve_mapping = {0x00:1,0x01:1.95,0x02:2,0x03:1,0x04:1,0x05:2.2}
    idx, paths = {}, []
    try:
        with open(db_path, 'rb') as f:
            while True:
                b = bytearray()
                while True:
                    c = f.read(1)
                    if not c or c == b'\x00': break
                    b.append(c[0])
                if not b: break
                raw = b.decode('ascii', errors='ignore')
                paths.append(raw)
                curve_id = struct.unpack('<B', f.read(1))[0]
                idx[raw] = curve_mapping.get(curve_id, 1)
        return idx, paths
    except FileNotFoundError:
        print(f"[WARN] bitmap.db not found at {db_path}")
        return {}, []


def get_curve_from_db(tex_rel, idx, paths):
    """Get curve value for a relative texture path."""
    key = f"{tex_rel}.bitmap"
    return idx.get(key, 1)


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
        if n.type=='UVMAP' and n.uv_map==uv_name:
            return n
    n = mat.node_tree.nodes.new('ShaderNodeUVMap')
    n.uv_map = uv_name
    n.label = f"UV {uv_name}"
    return n


def ensure_nonzero_scale(map_node):
    """Replace any 0 in mapping Scale with 1."""
    if map_node and map_node.type=='MAPPING':
        sv = map_node.inputs['Scale'].default_value
        for i in range(3):
            if sv[i]==0: sv[i]=1

# ── Main builder ─────────────────────────────────────────────────────

NODE_LOCATIONS = {
    'base_vec':      (-1200, 0),
    'fx_map_a_uv':   (-2100, 0),
    'fx_map_a_map':  (-1900, 150),
    'fx_map_a_tex':  (-1500, 150),
    'fx_map_b_uv':   (-2100, 0),
    'fx_map_b_map':  (-1900, -200),
    'fx_map_b_tex':  (-1500, -200),
    'palette_vec':   (-700, 0),
    'base_map_tex':  (-1000, 0),
    'palette_map_tex':(-500, 0),
    'main_group':    (-200, 0),
    'output':        (0, 0),
    'base_map_uv': (-2100, 0),
    'base_map_map':(-1900, -550),
    'base_map_mapped_tex':(-1000, 0),
}

def build_material(material, params, context, h4ek_base_path, addon_directory):
    def loc(name):
        return NODE_LOCATIONS.get(name, (0, 0))

    mat = material
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    nodes.clear()

    # load bitmaps
    idx, paths = load_bitmap_db(addon_directory)

    # base map vector group
    base_vec = nodes.new('ShaderNodeGroup')
    base_vec.node_tree = bpy.data.node_groups['surface_hard_light - base_map_vector']
    base_vec.location = loc('base_vec')

    # fx_map rows
    for i, key in enumerate(('fx_map_a', 'fx_map_b')):
        suffix = chr(97 + i)
        data = params.get(key, {})
        tex = _make_tex(data.get('value'), h4ek_base_path)
        if not tex:
            continue

        uv = get_uv_node(mat, 'UVMap')
        uv.location = loc(f'fx_map_{suffix}_uv')

        map_node = nodes.new('ShaderNodeMapping')
        map_node.vector_type = 'POINT'
        map_node.location = loc(f'fx_map_{suffix}_map')
        sx, sy = data.get('extra', {}).get('Scale', (1, 1))
        ox, oy = data.get('extra', {}).get('Offset', (0, 0))
        map_node.inputs['Scale'].default_value = (sx, sy, 1)
        map_node.inputs['Location'].default_value = (ox, oy, 0)
        ensure_nonzero_scale(map_node)

        tex_node = nodes.new('ShaderNodeTexImage')
        tex_node.image = tex
        tex_node.location = loc(f'fx_map_{suffix}_tex')

        links.new(uv.outputs['UV'], map_node.inputs['Vector'])
        # ── splice in wrap_modes ─────────────────────────────
        wrap_nm = nodes.new('ShaderNodeGroup')                               # ← new
        wrap_nm.node_tree = bpy.data.node_groups['wrap_modes']               # ← new
        wrap_nm.location = ((map_node.location.x + tex_node.location.x)/2,    # ← new
                           map_node.location.y)
        extra = data.get('extra', {})                                        # ← new
        wrap_nm.inputs['wrap_mode'].default_value   = extra.get('wrap_mode',   0)  # ← new
        wrap_nm.inputs['wrap_mode_u'].default_value = extra.get('wrap_mode_u', 0)  # ← new
        wrap_nm.inputs['wrap_mode_v'].default_value = extra.get('wrap_mode_v', 0)  # ← new
        links.new(map_node.outputs['Vector'], wrap_nm.inputs['Vector'])       # ← new
        links.new(wrap_nm.outputs['Vector'], tex_node.inputs['Vector'])      # ← new
        links.new(tex_node.outputs['Color'], base_vec.inputs[key])
        links.new(tex_node.outputs['Alpha'], base_vec.inputs[f'{key}_alpha'])

        curve = get_curve_from_db(data.get('value'), idx, paths)
        if f'{key}_curve' in base_vec.inputs:
            base_vec.inputs[f'{key}_curve'].default_value = curve

    # distortion_strength
    if 'distortion_strength' in params and 'distortion_strength' in base_vec.inputs:
        base_vec.inputs['distortion_strength'].default_value = float(params['distortion_strength']['value'])

    # palette map vector group
    pal_vec = nodes.new('ShaderNodeGroup')
    pal_vec.node_tree = bpy.data.node_groups['surface_hard_light - palette_map_vector']
    pal_vec.location = loc('palette_vec')
    links.new(base_vec.outputs['fxMapValue'], pal_vec.inputs['fxMapValue'])
    if 'base_map_curve' in params and 'base_map_curve' in pal_vec.inputs:
        curve = get_curve_from_db(params['base_map_curve']['value'], idx, paths)
        pal_vec.inputs['base_map_curve'].default_value = curve

    # base_map texture with mapping
    base_map = params.get('base_map', {})
    tex_b = _make_tex(base_map.get('value'), h4ek_base_path)
    if tex_b:
        uv_b = get_uv_node(mat, 'UVMap')
        uv_b.location = loc('base_map_uv')

        map_b = nodes.new('ShaderNodeMapping')
        map_b.vector_type = 'POINT'
        map_b.location = loc('base_map_map')
        sx, sy = base_map.get('extra', {}).get('Scale', (1, 1))
        ox, oy = base_map.get('extra', {}).get('Offset', (0, 0))
        map_b.inputs['Scale'].default_value = (sx, sy, 1)
        map_b.inputs['Location'].default_value = (ox, oy, 0)
        ensure_nonzero_scale(map_b)

        tn = nodes.new('ShaderNodeTexImage')
        tn.image = tex_b
        tn.location = loc('base_map_mapped_tex')

        links.new(uv_b.outputs['UV'], map_b.inputs['Vector'])
        links.new(base_vec.outputs['base_map_vector'], tn.inputs['Vector'])
        # ── splice in wrap_modes for base_map ────────────
        wrap_b = nodes.new('ShaderNodeGroup')                                        # ← new
        wrap_b.node_tree = bpy.data.node_groups['wrap_modes']                         # ← new
        wrap_b.location = ((map_b.location.x + base_vec.location.x)/2,                 # ← new
                          map_b.location.y)
        extra_b = base_map.get('extra', {})                                            # ← new
        wrap_b.inputs['wrap_mode'].default_value   = extra_b.get('wrap_mode',   0)      # ← new
        wrap_b.inputs['wrap_mode_u'].default_value = extra_b.get('wrap_mode_u', 0)      # ← new
        wrap_b.inputs['wrap_mode_v'].default_value = extra_b.get('wrap_mode_v', 0)      # ← new
        links.new(map_b.outputs['Vector'], wrap_b.inputs['Vector'])                     # ← new
        links.new(wrap_b.outputs['Vector'], base_vec.inputs['base_map_transform'])      # ← new
        links.new(tn.outputs['Color'], pal_vec.inputs['base_map'])


    # palette_map texture
    pal_map = params.get('palette_map', {})
    tex_p = _make_tex(pal_map.get('value'), h4ek_base_path)
    if tex_p:
        tn2 = nodes.new('ShaderNodeTexImage')
        tn2.image = tex_p
        tn2.location = loc('palette_map_tex')
        tn2.extension = 'EXTEND'
        links.new(pal_vec.outputs['palette_map_vector'], tn2.inputs['Vector'])

    # main surface_hard_light group
    main = nodes.new('ShaderNodeGroup')
    main.node_tree = bpy.data.node_groups['surface_hard_light']
    main.location = loc('main_group')
    if tex_b and 'base_map_alpha' in main.inputs:
        links.new(tn.outputs['Alpha'], main.inputs['base_map_alpha'])
    if tex_p and 'palette_map' in main.inputs:
        links.new(tn2.outputs['Color'], main.inputs['palette_map'])

    # blend, shadows, two-sided
    blend = float(params.get('Blend Mode', {}).get('value', 1.0))
    if '0 Opaque, .5 Additive, 1 Alpha Blend' in main.inputs:
        main.inputs['0 Opaque, .5 Additive, 1 Alpha Blend'].default_value = blend
    cast = bool(params.get('Cast shadows? [0-1]', {}).get('value', 1))
    if 'cull shadows' in main.inputs:
        main.inputs['cull shadows'].default_value = 1 if blend == 0.0 else cast
    if 'material is two-sided' in main.inputs:
        main.inputs['material is two-sided'].default_value = 1 if blend == 0.0 else cast

    # other float/bool params
    for name in (
        'fx_map_blend', 'palette_v_coord', 'add_blue_to_base',
        'intensity', 'alpha_multiplier', 'alpha_black_point',
        'alpha_white_point', 'depth_based_color_strength',
        'edge_fade_cutoff_dot_prod', 'edge_fade_range'
    ):
        if name in params and name in main.inputs:
            main.inputs[name].default_value = float(params[name]['value'])

    # output node
    out = nodes.new('ShaderNodeOutputMaterial')
    out.location = loc('output')
    links.new(main.outputs['Shader'], out.inputs['Surface'])

    mat.blend_method = 'BLEND'
    mat.use_backface_culling = False

    print('surface_hard_light built.')