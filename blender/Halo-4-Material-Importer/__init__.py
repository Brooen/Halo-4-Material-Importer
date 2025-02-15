bl_info = {
    "name": "Halo 4 Material Importer",
    "author": "Brooen",    
    "blender": (4, 3, 2),
    "category": "Object",
}

import bpy
import os
import importlib.util
import subprocess
from bpy.types import Operator, AddonPreferences, Panel
from bpy.props import StringProperty

class FILE_OT_run_material_importer(Operator):
    bl_idname = "file.run_material_importer"
    bl_label = "Run Material Importer"

    def execute(self, context):
        prefs = context.preferences.addons["Halo-4-Material-Importer"].preferences
        addon_directory = os.path.dirname(__file__)  # Define addon_directory

        # Ensure Shaders node group is loaded
        if "Shaders" not in bpy.data.node_groups:
            shaders_blend = os.path.join(addon_directory, "Shaders.blend")
            if os.path.exists(shaders_blend):
                with bpy.data.libraries.load(shaders_blend, link=False) as (data_from, data_to):
                    if "Shaders" in data_from.node_groups:
                        data_to.node_groups = ["Shaders"]
                        self.report({'INFO'}, "Appended Shaders nodegroup from Shaders.blend.")
                    else:
                        self.report({'WARNING'}, "Shaders nodegroup not found in Shaders.blend.")
            else:
                self.report({'WARNING'}, "Shaders.blend file not found.")
        else:
            self.report({'INFO'}, "Shaders nodegroup already exists.")

        # Import material_importer.py dynamically
        script_path = os.path.join(addon_directory, "material_importer.py")
        if not os.path.exists(script_path):
            self.report({'ERROR'}, "Material importer script not found.")
            return {'CANCELLED'}

        spec = importlib.util.spec_from_file_location("material_importer", script_path)
        material_importer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(material_importer)

        # Iterate over selected objects and process materials
        processed_materials = set()

        # Get h4ek_base_path from preferences
        h4ek_base_path = prefs.h4ek_base_path  

        for obj in context.selected_objects:
            if not obj.data or not hasattr(obj.data, "materials"):
                continue  # Skip objects without materials

            for mat in obj.data.materials:
                if mat and mat.get("tag_name") and mat.name not in processed_materials:
                    tag_name = os.path.join(h4ek_base_path, "tags", mat["tag_name"] + ".material")
                    self.report({'INFO'}, f"Processing material: {mat.name} with tag_name: {tag_name}")

                    # Get h4ek_base_path from preferences
                    h4ek_base_path = prefs.h4ek_base_path  

                    try:
                        # Pass h4ek_base_path as an additional argument
                        material_importer.process_material(tag_name, mat, h4ek_base_path, addon_directory)
                    except Exception as e:
                        self.report({'ERROR'}, f"Error processing {tag_name}: {str(e)}")

                    except Exception as e:
                        self.report({'ERROR'}, f"Error processing {tag_name}: {str(e)}")

                    processed_materials.add(mat.name)


        self.report({'INFO'}, "Materials processed successfully")
        return {'FINISHED'}


class FILE_OT_export_all_bitmaps(Operator):
    """Export all bitmaps from the H4EK base path using tool.exe 
    (converts everything to DDS in the images folder in H4EK (25 GB))"""
    
    bl_idname = "file.export_all_bitmaps"
    bl_label = "Export All Bitmaps"

    def execute(self, context):
        prefs = context.preferences.addons["Halo-4-Material-Importer"].preferences
        addon_directory = os.path.dirname(__file__)  # Get the addon directory
        script_path = os.path.join(addon_directory, "export_all_bitmaps.py")

        if not os.path.exists(script_path):
            self.report({'ERROR'}, "Export script not found.")
            return {'CANCELLED'}

        # Run the script and pass h4ek_base_path
        try:
            subprocess.run(["python", script_path, prefs.h4ek_base_path, addon_directory], check=True)
            self.report({'INFO'}, "Export All Bitmaps executed successfully.")
        except subprocess.CalledProcessError as e:
            self.report({'ERROR'}, f"Error executing export script: {str(e)}")

        return {'FINISHED'}




class MATERIAL_IMPORTER_PT_panel(Panel):
    bl_label = "Material Importer"
    bl_idname = "MATERIAL_IMPORTER_PT_panel"
    bl_category = "Halo 4 Material Importer"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_context = "objectmode"

    def draw(self, context):
        layout = self.layout
        layout.operator("file.run_material_importer")


class MaterialImporterPreferences(AddonPreferences):
    bl_idname = __name__

    h4ek_base_path: StringProperty(
        name="H4EK Base Path",
        subtype='DIR_PATH',
        description="Set the base path for H4EK files",  # Alt text (tooltip)
        default="C:\\Program Files (x86)\\Steam\\steamapps\\common\\H4EK\\"  # Placeholder (grayed-out text)
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Material Importer Addon Preferences")
        layout.prop(self, "h4ek_base_path", text="Base Path")  # Label for the input box
        # Export button with tooltip
        export_btn = layout.operator(
            "file.export_all_bitmaps",
            text="Export All Bitmaps",
            icon="EXPORT"
        )
 
# Register classes
classes = [
    FILE_OT_run_material_importer,
    FILE_OT_export_all_bitmaps,
    MATERIAL_IMPORTER_PT_panel,
    MaterialImporterPreferences
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
