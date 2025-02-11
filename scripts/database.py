import os
import struct

def process_bitmap_files(directory):
    output_file = os.path.join(directory, "bitmap.db")
    with open(output_file, "wb") as db:
        for root, _, files in os.walk(directory):
            for filename in sorted(files):
                if filename.endswith(".bitmap"):
                    file_path = os.path.join(root, filename)
                    try:
                        with open(file_path, "rb") as bitmap:
                            # Get file size
                            bitmap.seek(0, os.SEEK_END)
                            file_size = bitmap.tell()
                            
                            # Calculate the position 123 bytes before the end
                            read_position = file_size - 123
                            
                            if read_position >= 0:
                                bitmap.seek(read_position)
                                u8_value = struct.unpack("<B", bitmap.read(1))[0]  # Read a u8 (1 byte)
                            else:
                                print(f"Skipping {file_path}: File too small")
                                continue

                            # Get relative path
                            relative_path = os.path.relpath(file_path, directory)
                            ascii_path = relative_path.encode("ascii")

                            # Prepare data to write: path + null byte + u8 value
                            data = ascii_path + b"\x00" + struct.pack("<B", u8_value)

                            # Write to output file
                            db.write(data)

                    except (IOError, struct.error) as e:
                        print(f"Failed to process file {file_path}: {e}")

    print(f"Data saved to {output_file}")

# Specify the root directory containing .bitmap files
root_directory = r"F:\SteamLibrary\steamapps\common\H4EK\tags"  # Replace with your root directory path

if os.path.isdir(root_directory):
    process_bitmap_files(root_directory)
else:
    print("Invalid directory path. Please check the path and try again.")