import bpy
import struct

def clear_material():
    """Removes the existing material from the active object."""
    obj = bpy.context.object
    if obj and obj.type == 'MESH':
        obj.active_material = None

def import_shader(shader_name):
    """Finds the shader node group in Blender and applies it to the material."""
    # Check if the shader node group exists in Blender
    shader_group_name = f"H5 material_shader: {shader_name}"
    if shader_group_name not in bpy.data.node_groups:
        print(f"Shader node group '{shader_group_name}' not found.")
        return None

    # Create a new material
    mat = bpy.data.materials.new(name=shader_name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes

    # Clear all nodes
    for node in nodes:
        nodes.remove(node)

    # Create new nodes
    output_node = nodes.new(type="ShaderNodeOutputMaterial")
    output_node.location = (400, 0)

    shader_node = nodes.new(type="ShaderNodeGroup")
    shader_node.node_tree = bpy.data.node_groups[shader_group_name]
    shader_node.location = (0, 0)

    # Connect Shader output to Material Output Surface
    mat.node_tree.links.new(shader_node.outputs["Shader"], output_node.inputs["Surface"])

    return mat

def assign_material_to_active_object(material):
    """Assigns the given material to the active object."""
    obj = bpy.context.object
    if obj and obj.type == 'MESH':
        obj.active_material = material

class MaterialParameter:
    BITMAP = 0
    REAL = 1
    INT = 2
    BOOLEAN = 3
    COLOR = 4

class BlendModes:
    VALUES = [
        "Opaque", "Additive", "Multiply", "Alpha_Blend", "Double_Multiply", "Pre_Multiplied_Alpha",  #only use Opaque, Additive, or Alpha blend, set everything else to Alpha Blend
        "Maximum", "Multiply_Add", "Add_Source_Times_Destination_Alpha", "Add_Source_Times_Source_Alpha",
        "Inv_Alpha_Blend", "Motion_Blur_Static", "Motion_Blur_Inhibit", "Apply_Shadow_Into_Shadow_Mask",
        "Alpha_Blend_Constant", "Overdraw_Apply", "Wet_Screen_Effect", "Minimum", "Reverse_Subtract",
        "Forge_Lightmap", "Forge_Lightmap_Inv", "Replace_All_Channels", "Alpha_Blend_Max",
        "Opaque_Alpha_Blend", "Alpha_Blend_Additive_Transparent"
    ]

class TransparentShadowPolicies:
    VALUES = ["None", "Render_as_decal", "Render_with_material"]  #None and Render_as_decal - no backface, no shadow

class WrapMode:
    VALUES = ["wrap", "clamp", "mirror", "black_border", "mirror_once", "mirror_once_border"]

class FilterMode:
    VALUES = ["trilinear", "point", "bilinear", "UNUSED_0", "anisotropic_two_expensive", "UNUSED_1", "anisotropic_four_EXPENSIVE", "lightprobe_texture_array", "texture_array_quadlinear", "texture_array_quadanisotropic_two"]

class SharpenMode:
    VALUES = ["blur2.00", "blur1.75", "blur1.50", "blur1.25", "blur1.00", "blur0.75", "blur0.50", "blur0.25", "0.0", "sharpen0.25", "sharpen0.50", "sharpen0.75", "sharpen1.00"]

class ExternMode:
    VALUES = ["use_bitmap_as_normal", "albedo_buffer", "normal_buffer", "dynamic_UI", "depth_camera"]

def get_shader_name(shader: str) -> str:
    """Extracts the shader name by removing everything before the last '\\'."""
    return shader.split("\\")[-1]  # Takes only the last part after the last backslash

def clean_file_path(filepath: str) -> str:
    """Removes the first four characters from the file path."""
    return filepath[4:] if len(filepath) > 4 else filepath  # Ensures it doesn't break on short strings

import struct

def read_patterned_file(filepath):
    with open(filepath, 'rb') as f:
        f.seek(176)

        for _ in range(12):
            f.seek(8, 1)
            size = struct.unpack('<I', f.read(4))[0]
            f.seek(size, 1)

        # First, try moving 100 bytes forward and checking for 'tsgt'
        f.seek(96, 1)
        pos_100 = f.tell()
        if f.read(4) != b'\x74\x73\x67\x74':  # 'tsgt' in hex
            # If not found, try 104 bytes forward instead
            f.seek(4, 1)

        # Move back 8 bytes before 'tsgt'
        f.seek(-12, 1)       

                
        print(f"Current Offset: 0x{f.tell():X}")
        blend_mode = struct.unpack('<B', f.read(1))[0]
        f.seek(3, 1)
        tsp = struct.unpack('<I', f.read(4))[0]
        f.seek(20, 1)
        shader_length = struct.unpack('<I', f.read(4))[0]
        shader = f.read(shader_length).decode('ascii', errors='ignore')
        f.seek(12, 1)
        parameter_count = struct.unpack('<I', f.read(4))[0]
        f.seek(4, 1)

       # Print results
        print(f"Blend Mode: {BlendModes.VALUES[blend_mode] if blend_mode < len(BlendModes.VALUES) else 'Unknown'}")
        print(f"TSP: {TransparentShadowPolicies.VALUES[tsp] if tsp < len(TransparentShadowPolicies.VALUES) else 'Unknown'}")
        print(f"Shader Length: {shader_length}")
        print(f"Shader: {get_shader_name(shader)}")
        print(f"Parameter Count: {parameter_count}")

        
        parameters = []
        
        for i in range(parameter_count):
            offset = f.tell()
            f.seek(4, 1)
            param_type = struct.unpack('<I', f.read(4))[0]
            parameters.append({'index': i, 'offset': offset, 'type': param_type, 'data': []})
            
            if param_type == MaterialParameter.BITMAP:
                f.seek(40, 1)
                scale = struct.unpack('<2f', f.read(8))
                offset = struct.unpack('<2f', f.read(8))
                f.seek(6, 1)
                filter_mode, wrap_mode, wrap_mode_u, wrap_mode_v, sharpen_mode, extern_mode = struct.unpack('<6H', f.read(12))
                parameters[-1]['data'].extend([
                    "Type: Bitmap",
                    f"Scale: {scale}", f"Offset: {offset}",
                    f"Filter Mode: {FilterMode.VALUES[filter_mode] if filter_mode < len(FilterMode.VALUES) else 'Unknown'}",
                    f"Wrap Mode: {WrapMode.VALUES[wrap_mode] if wrap_mode < len(WrapMode.VALUES) else 'Unknown'}",
                    f"Sharpen Mode: {SharpenMode.VALUES[sharpen_mode] if sharpen_mode < len(SharpenMode.VALUES) else 'Unknown'}"
                ])
                f.seek(86, 1)
            
            elif param_type == MaterialParameter.COLOR:
                f.seek(24, 1)
                argb = struct.unpack('<4f', f.read(16))
                parameters[-1]['data'].extend(["Type: Color", f"ARGB: {argb}"])
                f.seek(120, 1)
            
            elif param_type == MaterialParameter.REAL:
                f.seek(40, 1)
                real_value = struct.unpack('<f', f.read(4))[0]
                parameters[-1]['data'].extend(["Type: Real", f"Value: {real_value}"])
                f.seek(116, 1)
            
            elif param_type == MaterialParameter.BOOLEAN:
                f.seek(56, 1)
                boolean_value = struct.unpack('<I', f.read(4))[0]
                parameters[-1]['data'].extend(["Type: Boolean", f"Value: {bool(boolean_value)}"])
                f.seek(100, 1)
            
            elif param_type == MaterialParameter.INT:
                f.seek(68, 1)
                integer_value = struct.unpack('<I', f.read(4))[0]
                parameters[-1]['data'].extend(["Type: Int", f"Value: {integer_value}"])
                f.seek(624, 1)
                
        for param in parameters:
            f.seek(20, 1)
            name_length = struct.unpack('<I', f.read(4))[0]
            param_name = f.read(name_length).decode('ascii', errors='ignore')
            param['data'].insert(0, f"Name: {param_name}")
            
            if param['type'] == MaterialParameter.BITMAP:
                f.seek(8, 1)
                path_length = struct.unpack('<I', f.read(4))[0]
                file_path = f.read(path_length).decode('ascii', errors='ignore')
                param['data'].append(f"File Path: {clean_file_path(file_path)}")
                f.seek(8, 1)
                default_length = struct.unpack('<I', f.read(4))[0]
                default_file_path = f.read(default_length).decode('ascii', errors='ignore')
                param['data'].append(f"Default File Path: {default_file_path}")
            else:
                f.seek(24, 1)
            
            f.seek(8, 1)
            data_length = struct.unpack('<I', f.read(4))[0]
            f.seek(data_length, 1)
            f.seek(36, 1)
        
        print("\n\n".join(["\n".join(param['data']) for param in parameters]))

# Example usage
#read_patterned_file("F:\\SteamLibrary\\steamapps\\common\\H4EK\\tags\\levels\\dlc\\materials\\ca_port\\ca_port_emissive_lights.material")
