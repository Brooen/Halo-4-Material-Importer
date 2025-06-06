import os
import struct
import bpy

def read_shader_from_file(filepath):
    with open(filepath, 'rb') as f:
        f.seek(176)
        for _ in range(12):
            f.seek(8, 1)
            size = struct.unpack('<I', f.read(4))[0]
            f.seek(size, 1)
        for _ in range(100):
            if f.read(4) == b'\x74\x73\x67\x74':
                break
        f.seek(-12, 1)
        f.read(1)
        f.seek(3, 1)
        f.read(4)
        f.seek(20, 1)
        shader_length = struct.unpack('<I', f.read(4))[0]
        shader = f.read(shader_length).decode('ascii', errors='ignore')
        return shader

def process_material_folder(root_folder):
    shader_counts = {}
    print(f"Starting scan in: {root_folder}")
    existing_nodegroups = {ng.name for ng in bpy.data.node_groups}
    for dirpath, dirnames, filenames in os.walk(root_folder):
        print(f"Entering directory: {dirpath}")
        for filename in filenames:
            if filename.lower().endswith('.material'):
                fullpath = os.path.join(dirpath, filename)
                print(f"Found .material file: {fullpath}")
                try:
                    shader_path = read_shader_from_file(fullpath)
                    normalized = shader_path.replace('\\', '/').split('/')[-1]
                    if normalized in existing_nodegroups:
                        print(f"Skipping '{normalized}' (node group exists)")
                        continue
                    prev_count = shader_counts.get(normalized, 0)
                    shader_counts[normalized] = prev_count + 1
                    print(f"Counted missing shader '{normalized}': {shader_counts[normalized]}")
                except Exception as e:
                    print(f"Failed to read shader from {fullpath}: {e}")
                    continue
    output_path = os.path.join(root_folder, "shader_list_without_finished_shaders.txt")
    print(f"Writing shader list to: {output_path}")
    with open(output_path, "w", encoding="utf-8") as fh:
        for name, cnt in sorted(shader_counts.items(), key=lambda item: item[1], reverse=True):
            fh.write(f"{name:50s} {cnt}\n")
    print("Done.")


process_material_folder(r"F:\SteamLibrary\steamapps\common\H4EK\tags")
