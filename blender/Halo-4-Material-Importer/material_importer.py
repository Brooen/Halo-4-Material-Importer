import bpy
import struct
import os
import collections
import re
import importlib.util, sys
# ───────── Cubemap helper import (works in every load context) ─────────
try:
    # 1) Normal package-relative import (when __package__ is set)
    from . import cubemap_to_equirect as c2e
except ImportError:
    # 2) Fallback – load cubemap_to_equirect.py from the same folder
    import importlib.util, sys, os as _os
    _mod_path = _os.path.join(_os.path.dirname(__file__), "cubemap_to_equirect.py")
    spec = importlib.util.spec_from_file_location("cubemap_to_equirect", _mod_path)
    c2e = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(c2e)
    sys.modules["cubemap_to_equirect"] = c2e   # optional: so others can import it
# -----------------------------------------------------------------------

UV2_TABLE = set()
_cfg_path = os.path.join(os.path.dirname(__file__), "uv2_overrides.txt")

if os.path.exists(_cfg_path):
    with open(_cfg_path, "r", encoding="utf-8") as fh:
        for line in fh:
            m = re.match(r"\s*([\w:]+)\s*::\s*([\w:]+)", line)
            if m:
                UV2_TABLE.add((m.group(1).lower(), m.group(2).lower()))
else:
    print(f"[INFO] No uv2_overrides.txt found in {os.path.dirname(__file__)} "
          "(UV-1 will be used for all inputs).")

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

# ── helper: dynamic load of a one-off shader module ───────────────────
_ONEOFF_DIR = os.path.join(os.path.dirname(__file__), "oneoffs")

def _load_oneoff(shader_name: str):
    """Return a module object if <oneoffs/<base>.py> exists; else None."""
    # strip any extension (e.g. '.material') so we match 'surface_hard_light'
    base = os.path.splitext(shader_name)[0]
    fp   = os.path.join(_ONEOFF_DIR, f"{base}.py")
    if not os.path.isfile(fp):
        return None
    spec = importlib.util.spec_from_file_location(base, fp)
    mod  = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        return mod
    except Exception as exc:
        print(f"[ERROR] Failed to load one-off '{base}': {exc}")
        return None


def get_shader_name(shader: str) -> str:
    """Extracts the shader name by removing everything before the last '\\'."""
    return shader.split("\\")[-1]  # Takes only the last part after the last backslash

def clean_file_path(filepath: str) -> str:
    """Removes the first four characters from the file path."""
    return filepath[4:] if len(filepath) > 4 else filepath  # Ensures it doesn't break on short strings

# ── helper: reuse textures / bools that already exist ─────────────────
def _link_existing_normals(mat, vec_node, shader_group):
    nt   = mat.node_tree
    lnks = nt.links

    # -------------------------------------------------------------
    # 1. normal_map  (bitmap)
    if shader_group.inputs.get("normal_map") and shader_group.inputs["normal_map"].is_linked:
        src = shader_group.inputs["normal_map"].links[0].from_node
        if "normal_map" in vec_node.inputs and not vec_node.inputs["normal_map"].is_linked:
            lnks.new(src.outputs["Color"], vec_node.inputs["normal_map"])

    # 2. normal_detail_map  (bitmap)
    if shader_group.inputs.get("normal_detail_map") and shader_group.inputs["normal_detail_map"].is_linked:
        src = shader_group.inputs["normal_detail_map"].links[0].from_node
        if "normal_detail_map" in vec_node.inputs and not vec_node.inputs["normal_detail_map"].is_linked:
            lnks.new(src.outputs["Color"], vec_node.inputs["normal_detail_map"])

    # 3. detail_normals  (boolean)
    if "detail_normals" in shader_group.inputs and "detail_normals" in vec_node.inputs:
        vec_node.inputs["detail_normals"].default_value = shader_group.inputs["detail_normals"].default_value

    # 4. reflection_normal  (float)  
    if "reflection_normal" in shader_group.inputs and "reflection_normal" in vec_node.inputs:
        vec_node.inputs["reflection_normal"].default_value = shader_group.inputs["reflection_normal"].default_value

# ── helper: append one line to <addon>/missing_shaders.txt ─────────────
_missing_counter = {}   # {shader_name: count}

def _log_missing_shader(shader_name: str):
    """Record one fallback to srf_blinn.

    On every call we update the in-memory counter **and**
    rewrite <addon>/missing_shaders.txt from scratch.
    """
    # bump session counter
    _missing_counter[shader_name] = _missing_counter.get(shader_name, 0) + 1

    # path inside the add-on folder
    log_path = os.path.join(os.path.dirname(__file__), "missing_shaders.txt")

    # overwrite the file each time
    with open(log_path, "w", encoding="utf-8") as fh:
        for name, cnt in _missing_counter.items():
            fh.write(f"{name:50s} {cnt}\n")

    print(f"[WARN] Shader '{shader_name}' not found – recorded ({_missing_counter[shader_name]}) in {log_path}")
# -----------------------------------------------------------------------

def get_uv_node(mat, uv_name: str):
    """
    Return a ShaderNodeUVMap set to *uv_name*.
    Re-uses an existing node if one already exists in the material.
    """
    for n in mat.node_tree.nodes:
        if n.type == 'UVMAP' and n.uv_map == uv_name:
            return n
    # create a new one
    n = mat.node_tree.nodes.new("ShaderNodeUVMap")
    n.uv_map  = uv_name
    n.label   = f"UV {uv_name}"
    n.location = (-800, -220 if uv_name.endswith(".001") else -100)
    return n

# helper (leave near the top of the file)
def ensure_nonzero_scale(map_node):
    """Replace any 0 component of the Mapping node’s Scale with 1."""
    if map_node and map_node.type == 'MAPPING':
        scale_sock = map_node.inputs['Scale'].default_value
        for i in range(3):                       # X, Y, Z
            if scale_sock[i] == 0:
                scale_sock[i] = 1


def read_patterned_file(filepath, material):
    with open(filepath, 'rb') as f:
        f.seek(176)  # Start at byte 176

        # Skip through 12 blocks
        for _ in range(12):
            f.seek(8, 1)  # Skip 8 bytes
            size = struct.unpack('<I', f.read(4))[0]  # Read size
            f.seek(size, 1)  # Skip size bytes

        start_offset = f.tell()  # Get the position after skipping blocks

        # Search for 'tsgt' starting from the current position
        for _ in range(100):  # Try three times (88, 92, 96)
            if f.read(4) == b'\x74\x73\x67\x74':  # 'tsgt' in hex
                break  # Stop looping if found
            

        f.seek(-12, 1)  # Move back to align properly

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

        print(f"Shader: {get_shader_name(shader)}")
        print(f"Blend Mode: {BlendModes.VALUES[blend_mode] if blend_mode < len(BlendModes.VALUES) else 'Unknown'}")
        print(f"TSP: {TransparentShadowPolicies.VALUES[tsp] if tsp < len(TransparentShadowPolicies.VALUES) else 'Unknown'}")
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
                    f"Type: Bitmap",
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
        
        blend_value = 1.0
        if blend_mode < len(BlendModes.VALUES):
            mode = BlendModes.VALUES[blend_mode]
            blend_value = 0.0 if mode == "Opaque" else 1.0 if mode == "Alpha_Blend" else 0.5 if mode == "Additive" else 1.0
        
        tsp_value = 1.0
        if tsp < len(TransparentShadowPolicies.VALUES):
            tsp_mode = TransparentShadowPolicies.VALUES[tsp]
            tsp_value = 0.0 if tsp_mode in ["None", "Render_as_decal"] else 1.0

        parameters.append({"name": "Blend Mode", "type": "blend_mode", "value": blend_value, "data": []})
        parameters.append({"name": "TSP", "type": "tsp", "value": tsp_value, "data": []})
        
        # Append Shader Name, Blend Mode, and TSP at the end
        parameters.append({"name": "Shader", "type": "shader", "value": get_shader_name(shader), "data": []})
            
        return parameters  # Return structured data

def get_curve_from_db(texture_path, bitmap_index, all_paths):
    """
    Retrieves the curve value for the given texture path using a preloaded index.
    If not found, tries an adjusted version missing the first character.
    """
    search_path = f"{texture_path}.bitmap"  # Normal expected path

    if search_path in bitmap_index:
        curve_value = bitmap_index[search_path]
        print(f"✅ Found curve for {texture_path}: {curve_value}")
        return curve_value

    # If not found, print the 1000th bitmap entry (if exists)
    if len(all_paths) > 1000:
        print(f"⚠ DEBUG: 1000th Entry in bitmap.db: {all_paths[999]}")
    else:
        print(f"⚠ DEBUG: bitmap.db has only {len(all_paths)} entries, no 1000th entry.")

    print(f"⚠ Curve for {texture_path} not found. Using default: 1")
    return 1  # Default to 1 if not found


def load_bitmap_db(addon_directory):
    """
    Loads the entire bitmap.db into a dictionary for fast lookups.
    """
    db_path = os.path.join(addon_directory, "bitmap.db")
    curve_mapping = {
        0x00: 1,
        0x01: 1.95,
        0x02: 2,
        0x03: 1,
        0x04: 1,
        0x05: 2.2
    }

    bitmap_index = {}  # Store path -> curve value
    all_paths = []  # Keep track of all paths for debugging (even if not used)

    try:
        with open(db_path, "rb") as f:
            while True:
                path_bytes = bytearray()
                
                # Read path until null terminator (\x00)
                while True:
                    byte = f.read(1)
                    if not byte or byte == b"\x00":
                        break
                    path_bytes.append(byte[0])

                if not path_bytes:
                    break  # Stop if we reach the end of the file

                # Convert bytes to string
                raw_path = path_bytes.decode("ascii").strip()
                all_paths.append(raw_path)  # Store for debugging

                # Read u8 curve identifier
                curve_id_bytes = f.read(1)
                if len(curve_id_bytes) == 0:
                    break  # Stop if EOF

                curve_id = struct.unpack("<B", curve_id_bytes)[0]  # Read as unsigned byte

                # Store in dictionary for instant lookup
                bitmap_index[raw_path] = curve_mapping.get(curve_id, 1)  # Default to 1 if not found

        return bitmap_index, all_paths  # ✅ Return two values

    except FileNotFoundError:
        print(f"⚠ WARNING: {db_path} not found.")
        return {}, []
    except Exception as e:
        print(f"❌ ERROR reading {db_path}: {e}")
        return {}, []



def process_material(filepath, material, h4ek_base_path, addon_directory):

    """
    Reads the material file, extracts parameters, and applies them to a shader in Blender.
    """
    print(f"\n--- Processing Material File: {filepath} ---")

    material_name = bpy.path.basename(filepath).replace(".material", "")
    material = bpy.data.materials.get(material_name) or bpy.data.materials.new(name=material_name)

    print(f"Material Created/Found: {material_name}")

    # Read the patterned file and get parameters
    parameters = read_patterned_file(filepath, material)

    if not parameters:
        print(f"ERROR: No parameters found in {filepath}. Skipping material creation.")
        return

    print(f"Extracted Parameters from File:\n{parameters}")

    # Extract shader name from parameters
    shader_name = next((param["value"] for param in parameters if isinstance(param, dict) and param.get("name") == "Shader"), None)

    print(f"DEBUG: Found Shader Name: {shader_name}")

    if not shader_name:
        print("ERROR: Shader name not found in material parameters. Skipping.")
        return
        if not shader_name:
            print("ERROR: Shader name not found in material parameters. Skipping.")
            return

    print(f"Shader Identified: {shader_name}")

    # Convert parameters into structured data for Blender
    structured_parameters = {}

    for param in parameters:
        if not isinstance(param, dict):  # Skip any non-dictionaries
            continue

        param_name = None
        param_type = None
        param_value = None
        extra_data = {}  # Store extra properties like wrap mode, filter mode, etc.

        # Ensure "data" exists and is a list
        if isinstance(param.get("data"), list):
            for data_entry in param["data"]:
                if isinstance(data_entry, str) and ": " in data_entry:
                    key, value = data_entry.split(": ", 1)
                    key = key.strip()
                    value = value.strip()

                    if key == "Name":  
                        param_name = value  # Assign the correct name
                        print(f"DEBUG: Found Parameter Name: {param_name}")
                    elif key == "Type":
                        param_type = value.lower()  # Store type
                    elif key in ["Scale", "Offset"]:  
                        param_value = tuple(map(float, value.strip("()").split(",")))
                        extra_data[key] = param_value  # ✅ Store it in `extra_data`
                    elif key == "ARGB":  # ✅ Ensure color is properly stored
                        param_value = tuple(map(float, value.strip("()").split(",")))  # Convert ARGB to tuple
                        print(f"DEBUG: Found ARGB Value: {param_value}")  # Debugging output
                        print(f"DEBUG: Found {key} Value: {param_value}")
                    elif key in ["File Path"]:
                        param_value = value
                    elif key == "Value":
                        try:
                            if param_type == "boolean":  # ✅ Fix: Check the actual type instead of key
                                param_value = value.lower() == "true"  # Convert string "true"/"false" to actual boolean
                            else:
                                param_value = float(value)
                        except ValueError:
                            param_value = value  # Keep as-is for other cases


                    else:
                        # Store extra data like "Wrap Mode", "Filter Mode", etc.
                        extra_data[key] = value

        # If the extracted name and value are valid, store them in structured_parameters
        if param_name:
            structured_parameters[param_name] = {
                "type": param_type if param_type else "unknown",
                "value": param_value,
                "extra": extra_data  # Store all extra properties here
            }
        else:
            print(f"WARNING: Skipping parameter due to missing name or value. Name: {param_name}, Value: {param_value}")

        # Extract blend_mode and tsp from parameters
        blend_mode = next((param["value"] for param in parameters if param.get("name") == "Blend Mode"), "Unknown")
        tsp = next((param["value"] for param in parameters if param.get("name") == "TSP"), "Unknown")

        # Include Blend Mode & TSP in structured_parameters
        structured_parameters["Blend Mode"] = {
            "type": "blend_mode",
            "value": blend_mode
        }

        structured_parameters["TSP"] = {
            "type": "tsp",
            "value": tsp
        }


    # Debugging print
    print("\n--- Passing to create_shader_in_blender ---")
    print(f"Shader: {shader_name}")
    print(f"Total Extracted Parameters: {len(parameters)}")
    print("\nStructured Parameters:")
    for key, value in structured_parameters.items():
        print(f" - {key}: {value}")

    # Apply shader in Blender
    create_shader_in_blender(shader_name, structured_parameters, material, h4ek_base_path, addon_directory)

    print(f"Shader '{shader_name}' successfully applied to '{material.name}'\n")


def create_shader_in_blender(shader_name, parameters, material, h4ek_base_path, addon_directory):
    """Creates or updates a shader node group in Blender and applies it to the given material."""
    # Ensure the node group exists
    node_group_name = f"{shader_name}"
    if node_group_name not in bpy.data.node_groups:
        _log_missing_shader(node_group_name) 
        print(f"Node group '{node_group_name}' not found in Blender, using blinn")
        node_group_name = "srf_blinn_reflection"
        
    
    node_group = bpy.data.node_groups[node_group_name]
    
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links

    # Clear existing nodes
    nodes.clear()

    # ───────────────── one-off override ───────────────────────────────
    oneoff_mod = _load_oneoff(shader_name)
    if oneoff_mod and hasattr(oneoff_mod, "build_material"):
        print(f"[INFO] Using one-off handler for shader '{shader_name}'")
        try:
            # hand over everything the module might need
            oneoff_mod.build_material(
                material      = material,         # bpy.types.Material
                params        = parameters,       # dict you already parsed
                context       = bpy.context,   
                h4ek_base_path   = h4ek_base_path,             # in case it needs scene info
                addon_directory = addon_directory
            )
            return material   # skip the default pipeline
        except Exception as exc:
            print(f"[ERROR] One-off '{shader_name}' failed: {exc} – falling back.")
    # ───────────────────────────────────────────────────────────────────

    # Add the node group to the material's node tree
    group_node = nodes.new('ShaderNodeGroup')
    group_node.node_tree = node_group
    group_node.name = shader_name
    group_node.label = shader_name
    group_node.location = (400, 0)  # Move the node group to the right
    
    group_inputs_lc = {sock.name.lower(): sock for sock in group_node.inputs}

    print(f"Setting up shader '{shader_name}' with parameters: {parameters}")
    
    blend_mode = float(parameters.get("Blend Mode", {}).get("value", 1.0))
    tsp_value = float(parameters.get("TSP", {}).get("value", 1.0))
    
    if "0 Opaque, .5 Additive, 1 Alpha Blend" in group_node.inputs.keys():
        group_node.inputs["0 Opaque, .5 Additive, 1 Alpha Blend"].default_value = float(blend_mode)
    
    if "cull shadows" in group_node.inputs:

        # `blend_mode` should already hold the string for this material
        # e.g. 'opaque', 'alpha_test', 'transparent', …
        if blend_mode == 0:
            # keep the value coming from the TSP (0 or 1)
            group_node.inputs["cull shadows"].default_value = 1
        else:
            # non-opaque materials always cast shadows
            group_node.inputs["cull shadows"].default_value = int(tsp_value)
            
    if "material is two-sided" in group_node.inputs:

        # `blend_mode` should already hold the string for this material
        # e.g. 'opaque', 'alpha_test', 'transparent', …
        if blend_mode == 0:
            # keep the value coming from the TSP (0 or 1)
            group_node.inputs["material is two-sided"].default_value = 1
        else:
            # non-opaque materials always cast shadows
            group_node.inputs["material is two-sided"].default_value = int(tsp_value)

    
    # Set the initial positions for nodes
    x_offset = -200
    y_offset = 0
    y_step = -300  # Vertical spacing between nodes
    
    alpha_connected = False

    for param_name, param_data in parameters.items():
        print(f"Processing parameter '{param_name}' of type '{param_data['type']}'")

        if param_data['type'] == 'bitmap':
            # Extract file path and construct new path format
            texture_path = param_data['value']
            
            

            # ───────────────────────────────────────────────────────────
            # SPECIAL CASE: reflection_map → convert cubemap to equirect
            # ───────────────────────────────────────────────────────────
            if param_name.lower() == "reflection_map":
                # DDS path to face 00
                cubemap_00 = os.path.join(
                    h4ek_base_path, "images", f"{texture_path}_00_00.dds"
                )

                if not os.path.exists(cubemap_00):
                    print(f"⚠ Reflection map cubemap not found: {cubemap_00}")
                    continue

                try:
                    # -- call the helper (no blender-load; we’ll do that next)
                    rgb_png, a_png = c2e.convert_cubemap(
                        first_face_path=cubemap_00,
                        rotate_deg=[90, -90, 0, 180, 180, 0],   # tweak later if you store per-material rots
                        face_size_out=0,
                        load_in_blender=False,
                    )
                except Exception as err:
                    print(f"❌ Cubemap→equirect failed: {err}")
                    continue

                # load the 2 PNGs as Blender images
                img_rgb   = bpy.data.images.load(rgb_png,   check_existing=True)
                img_alpha = bpy.data.images.load(a_png,     check_existing=True)
                img_alpha.colorspace_settings.is_data = True

                # add two texture nodes
                tex_rgb = nodes.new('ShaderNodeTexEnvironment')
                tex_rgb.image = img_rgb
                tex_rgb.image.colorspace_settings.name = 'Non-Color'
                tex_rgb.location = (x_offset, y_offset)

                tex_alpha_env = nodes.new('ShaderNodeTexEnvironment')
                tex_alpha_env.image = img_alpha
                tex_alpha_env.image.colorspace_settings.name = 'Non-Color'
                tex_alpha_env.location = (x_offset, y_offset - 230)
                y_offset += y_step - 170    # keep vertical spacing consistent
                
                
                # drive both with the “Reflection Map vector” node if present,
                # otherwise fall back to the UV Map node.
                # ── drive both Env textures from “Reflection Map vector” only ──────────
                vec_node = next((n for n in nodes
                                 if n.type == 'GROUP' and n.node_tree
                                 and n.node_tree.name == "Reflection Map vector"), None)

                if not vec_node:
                    if "Reflection Map vector" in bpy.data.node_groups:
                        vec_node = nodes.new("ShaderNodeGroup")
                        vec_node.node_tree = bpy.data.node_groups["Reflection Map vector"]
                        vec_node.label = "Reflection Map vector"
                        vec_node.location = (x_offset - 300, y_offset + 80)
                    
                    else:
                        print(f"⚠  Node-group ‘Reflection Map vector’ missing; "
                              f"reflection textures not linked in material “{material.name}”.")
                        return   # bail out—better to leave them un-hooked



                # ---------------------------------------------------------------------
                # call it immediately after vec_node is created
                _link_existing_normals(material, vec_node, group_node)



                # ──────────────────────────────────────────────────────────────────
                #  2.  Hook its Vector output into BOTH env textures
                # ──────────────────────────────────────────────────────────────────
                links.new(vec_node.outputs["Vector"], tex_rgb.inputs["Vector"])
                links.new(vec_node.outputs["Vector"], tex_alpha_env.inputs["Vector"])

                # ──────────────────────────────────────────────────────────────────
                # 3.  Pass any matching parameters into the vec_node inputs
                #    (uses the SAME rules you already apply to the shader group)
                # ──────────────────────────────────────────────────────────────────
                


                if 'reflection_map' in group_node.inputs:
                    links.new(tex_rgb.outputs['Color'],
                              group_node.inputs['reflection_map'])

                if 'reflection_map_alpha' in group_node.inputs:
                    links.new(tex_alpha_env.outputs['Color'],      # ← use COLOR output
                              group_node.inputs['reflection_map_alpha'])


                print("✅ Reflection map processed via cubemap_to_equirect.")
                continue    # ↩︎ skip the normal bitmap branch
            # ───────────────────────────────────────────────────────────
            # (normal bitmap code continues below as-is)

            
            # Use h4ek_base_path to form the correct texture path
            new_texture_path = os.path.join(h4ek_base_path, "images", f"{(texture_path)}_00_00.dds") 

            # Check if the file exists before attempting to load it
            if not os.path.exists(new_texture_path):
                print(f"⚠ Skipping missing texture: {new_texture_path}")
                continue  # Skip this texture and move to the next one

            # Check if the image is already loaded in Blender
            image_name = os.path.basename(new_texture_path)
            image = bpy.data.images.get(image_name)
            
            if image is None:
                # Load the image if not already loaded
                print(f"Loading texture from path: {new_texture_path}")
                try:
                    image = bpy.data.images.load(new_texture_path)
                except RuntimeError:
                    print(f"❌ Failed to load image: {new_texture_path}. Skipping this texture.")
                    continue  # Skip to the next parameter if the image fails to load

            # Create the texture node
            tex_node = nodes.new('ShaderNodeTexImage')
            tex_node.name = param_name
            tex_node.label = param_name
            tex_node.image = image
            tex_node.location = (x_offset, y_offset)
            y_offset += y_step  # Move down for the next node
            

            if param_name in ("normal_map", "normal_detail_map"):
                vec_node = next(
                    (n for n in material.node_tree.nodes
                     if n.type == 'GROUP'
                     and n.node_tree
                     and n.node_tree.name == "Reflection Map vector"),
                    None
                )
                if vec_node and param_name in vec_node.inputs:
                    # avoid duplicate links
                    if not vec_node.inputs[param_name].is_linked:
                        material.node_tree.links.new(
                            tex_node.outputs['Color'],
                            vec_node.inputs[param_name]
                        )

            print(f"✅ Texture node '{tex_node.name}' created/updated at location {tex_node.location}.")
            # Set the curve (color space) if provided
            # curve = param_data['curve']
            # if curve:
                # if curve.lower() == "linear":
                    # curve = "Linear Rec.709"
                # elif curve.lower() == "srgb":
                    # curve = "sRGB"
                # tex_node.image.colorspace_settings.name = curve
            # print(f"Color space set to: {tex_node.image.colorspace_settings.name}")
            
            tex_node.image.alpha_mode = 'CHANNEL_PACKED'
            tex_node.image.colorspace_settings.name = 'Linear Rec.709'
            
            # Create a mapping node and set UV scale
            mapping_node = nodes.new('ShaderNodeMapping')
            mapping_node.name = f"{param_name}_Mapping"
            mapping_node.label = f"{param_name}_Mapping"
            mapping_node.location = (x_offset - 300, y_offset + 150)  # Place above and to the left of the texture node


            # Check if scale and offset exist
            if "Scale" in param_data['extra']:
                scale_x, scale_y = param_data['extra']["Scale"]
                mapping_node.inputs['Scale'].default_value[0] = scale_x  # X
                mapping_node.inputs['Scale'].default_value[1] = scale_y  # Y
                print(f"Applied Scale: X={scale_x}, Y={scale_y}")

            if "Offset" in param_data['extra']:
                offset_x, offset_y = param_data['extra']["Offset"]
                mapping_node.inputs['Location'].default_value[0] = offset_x  # X
                mapping_node.inputs['Location'].default_value[1] = offset_y  # Y
                print(f"Applied Offset: X={offset_x}, Y={offset_y}")

            ensure_nonzero_scale(mapping_node)            
            
            # decide UV set for THIS bitmap
            use_uv2 = ((shader_name.lower(), param_name.lower()) in UV2_TABLE)
            uv_map_name = "UVMap.001" if use_uv2 else "UVMap"

            uv_map_node = get_uv_node(material, uv_map_name)
            

            
            # Connect the UV Map node to the Mapping node
            links.new(uv_map_node.outputs['UV'], mapping_node.inputs['Vector'])
            print(f"Connected UV Map node to mapping node.")

            # Connect the mapping node to the texture node
            links.new(mapping_node.outputs['Vector'], tex_node.inputs['Vector'])
            print(f"Connected mapping node to texture node.")
            
            # Check if the node group has an _alpha input
            
            # Check if the main color input exists in the node group
            if param_name in group_node.inputs.keys():
                print(f"'{param_name}' exists in group node inputs. Connecting color...")
                links.new(tex_node.outputs['Color'], group_node.inputs[param_name])
                print(f"Connected texture node color output to group node input '{param_name}'.")
            alpha_input_name = f"{param_name}_alpha"
            print(f"Checking for alpha input '{alpha_input_name}' in node group...")
            
            # ── CURVE hookup (case-insensitive) ───────────────────────────────
            curve_input_name = f"{param_name}_curve"
            curve_sock = group_inputs_lc.get(curve_input_name.lower())

            if curve_sock:
                print(f"'{curve_sock.name}' socket found – fetching curve value …")

                # Load bitmap.db once and store the index
                bitmap_index, all_paths = load_bitmap_db(addon_directory)

                # Use the preloaded index for fast look-ups
                curve_value = get_curve_from_db(texture_path, bitmap_index, all_paths)

                # Set the curve value
                curve_sock.default_value = curve_value
                print(f"✅ Set curve parameter '{curve_sock.name}' to {curve_value}")

            else:
                print(f"Curve socket '{curve_input_name}' not found on node group "
                      "(checked case-insensitively).")
            
            # ── ALPHA hookup (case-insensitive) ────────────────────────────────
            alpha_input_name = f"{param_name}_alpha"
            alpha_sock = group_inputs_lc.get(alpha_input_name.lower())

            if alpha_sock:
                # link only if the socket is free
                if not alpha_sock.is_linked:
                    links.new(tex_node.outputs["Alpha"], alpha_sock)
                    print(f"Connected ALPHA of '{param_name}' → socket '{alpha_sock.name}'")

                # mark alpha-connected for blend-mode adjustment
                if param_name.lower() in ("surface_color_map", "color_map"):
                    alpha_connected = True
            else:
                print(f"Alpha socket “{alpha_input_name}” not found on node-group "
                      f"(looked up case-insensitively).")



            sock = group_inputs_lc.get(param_name.lower())
            if sock:
                links.new(tex_node.outputs['Color'], sock)
                print(f"Connected texture node to group node input '{param_name}'.")

        elif param_data['type'] == 'color':
            # 1) find the socket by LOWER-cased name
            sock = group_inputs_lc.get(param_name.lower())
            if not sock:
                print(f"[WARN] Color param “{param_name}” not found on node-group "
                      f"({shader_name}); skipped.")
                continue

            try:
                # Convert ARGB (A,R,G,B) → RGBA (R,G,B,A)
                argb = param_data['value']

                if isinstance(argb, tuple) and len(argb) == 4:
                    rgba = (argb[1], argb[2], argb[3], argb[0])
                    sock.default_value = rgba
                    print(f"Set color {param_name} → {rgba}  (from ARGB {argb})")
                else:
                    print(f"WARNING: Invalid ARGB for '{param_name}': {argb}")

            except TypeError:
                # single-float sockets (rare): use the red channel
                sock.default_value = argb[1]
                print(f"Color {param_name} expected float; set to red {argb[1]}")


        elif param_data['type'] == 'real':
            # --- existing code that feeds the main shader ---
            if param_name in group_node.inputs.keys():
                sock = group_inputs_lc.get(param_name.lower())
                if sock:
                    sock.default_value = float(param_data["value"])


            # --- NEW: pipe reflection_normal into the vector node ---
            if param_name == "reflection_normal":
                vec_node = next(
                    (n for n in material.node_tree.nodes
                     if n.type == 'GROUP'
                     and n.node_tree
                     and n.node_tree.name == "Reflection Map vector"),
                    None
                )
                if vec_node and "reflection_normal" in vec_node.inputs:
                    vec_node.inputs["reflection_normal"].default_value = float(param_data['value'])

        elif param_data['type'] == 'boolean':
            if param_name in group_node.inputs.keys():
                # always define boolean_value
                boolean_value = param_data.get('value', False)
                if isinstance(boolean_value, str):
                    boolean_value = boolean_value.lower() == "true"

                sock = group_inputs_lc.get(param_name.lower())
                if sock:
                    sock.default_value = bool(boolean_value)


                # ── feed detail_normals into the Reflection Map vector ──
                if param_name == "detail_normals":
                    vec_node = next(
                        (n for n in material.node_tree.nodes
                         if n.type == 'GROUP'
                         and n.node_tree
                         and n.node_tree.name == "Reflection Map vector"),
                        None
                    )
                    if vec_node and "detail_normals" in vec_node.inputs:
                        vec_node.inputs["detail_normals"].default_value = bool(boolean_value)



                print(f"✅ Set boolean parameter '{param_name}' to {boolean_value}")

        elif param_data['type'] == 'int':
            if param_name in group_node.inputs.keys():
                group_node.inputs[param_name].default_value = param_data['value']
                print(f"Set int parameter '{param_name}' to {param_data['value']}")
    
    # Ensure the Material Output node is present
    material_output = None

    # Try to find an existing Material Output node
    for node in nodes:
        if isinstance(node, bpy.types.ShaderNodeOutputMaterial):
            material_output = node
            break

    # If no Material Output node exists, create one
    if material_output is None:
        material_output = nodes.new(type="ShaderNodeOutputMaterial")
        material_output.location = (800, 0)  # Move it to the right
        print("✅ Created a new Material Output node.")

    # Ensure the Shader node group is connected to the Material Output
    if "Shader" in group_node.outputs and "Surface" in material_output.inputs:
        links.new(group_node.outputs["Shader"], material_output.inputs["Surface"])
        print("✅ Connected Shader node group to Material Output.")
# Example usage
#read_patterned_file("F:\\SteamLibrary\\steamapps\\common\\H4EK\\tags\\levels\\dlc\\materials\\ca_port\\ca_port_emissive_lights.material")
