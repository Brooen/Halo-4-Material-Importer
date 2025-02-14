import os
import sys
import subprocess

def read_bitmap_db(db_path):
    """ Reads bitmap.db and extracts all bitmap paths. """
    if not os.path.exists(db_path):
        print(f"Error: {db_path} not found.")
        return []

    paths = []
    with open(db_path, "rb") as f:
        while True:
            path_bytes = bytearray()
            while True:
                byte = f.read(1)
                if not byte or byte == b"\x00":
                    break
                path_bytes.append(byte[0])
            if not path_bytes:
                break  # End of file
            paths.append(path_bytes.decode("ascii"))
            f.read(1)  # Skip 1 byte after each string

    return paths

def export_bitmaps(h4ek_base_path, addon_directory):
    """ Runs tool export-bitmap-dds for each bitmap path. """
    bitmap_db_path = os.path.join(addon_directory, "bitmap.db")
    tool_exe = "tool.exe"  # No full path, runs from h4ek_base_path

    if not os.path.exists(os.path.join(h4ek_base_path, tool_exe)):
        print("Error: tool.exe not found in h4ek_base_path.")
        return

    bitmap_paths = read_bitmap_db(bitmap_db_path)
    
    for bitmap_path in bitmap_paths:
        source_path = bitmap_path.removesuffix(".bitmap")  # Remove .bitmap extension
        destination_path = os.path.join(h4ek_base_path, "images", os.path.dirname(source_path) + "/")

        os.makedirs(destination_path, exist_ok=True)

        command = f'cd /d "{h4ek_base_path}" && tool.exe export-bitmap-dds "{source_path}" "{destination_path}"'
        print("Running command:", command)

        try:
            # Run command in shell with correct working directory
            subprocess.Popen(command, shell=True, cwd=h4ek_base_path).wait()
        except subprocess.CalledProcessError as e:
            print(f"Error exporting {bitmap_path}: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python export_all_bitmaps.py <h4ek_base_path> <addon_directory>")
    else:
        export_bitmaps(sys.argv[1], sys.argv[2])
