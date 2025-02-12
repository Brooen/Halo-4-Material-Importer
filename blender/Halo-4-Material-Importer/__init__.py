bl_info = {
    "name": "Halo 4 Material Importer",
    "author": "Brooen",    
    "blender": (4, 3, 2),
    "category": "Object",
}

import bpy
import os
import importlib.util
from bpy.types import Operator, AddonPreferences, Panel
from bpy.props import StringProperty

class FILE_OT_run_material_importer(Operator):
    bl_idname = "file.run_material_importer"
    bl_label = "Run Material Importer"

    def execute(self, context):
        prefs = context.preferences.addons[__name__].preferences
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

        for obj in context.selected_objects:
            if not obj.data or not hasattr(obj.data, "materials"):
                continue  # Skip objects without materials

            for mat in obj.data.materials:
                if mat and mat.get("tag_name") and mat.name not in processed_materials:
                    tag_name = os.path.join(prefs.tag_base_path, mat["tag_name"] + ".material")  # Get the material tag name from custom properties
                    self.report({'INFO'}, f"Processing material: {mat.name} with tag_name: {tag_name}")

                    try:
                        material_importer.read_patterned_file(tag_name)  # Run the parameter reader
                    except Exception as e:
                        self.report({'ERROR'}, f"Error processing {tag_name}: {str(e)}")

                    processed_materials.add(mat.name)  # Avoid duplicate processing

        self.report({'INFO'}, "Materials processed successfully")
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

    tag_base_path: StringProperty(
        name="Tag Base Path",
        subtype='DIR_PATH'
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Material Importer Addon Preferences")
        layout.prop(self, "tag_base_path")


# Register classes
classes = [FILE_OT_run_material_importer, MATERIAL_IMPORTER_PT_panel, MaterialImporterPreferences]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()
