import arcpy
import os
from arcpy.sa import *
import sys
from shlex import quote as q

# Function to safely retrieve argument values from sys.argv
def get_arg_value(arg_name):
    """Retrieves the value corresponding to a command-line argument tag."""
    value = None
    try:
        if arg_name in sys.argv:
            # Check if the next argument exists and is not another tag
            index = sys.argv.index(arg_name)
            value = sys.argv[index + 1]
    except IndexError:
        pass # Argument found, but no value following it (should not happen with our setup)
    return value

try:
    # Get values passed from the run_simulation function via command line
    city = get_arg_value("city_name")
    intermediate_folder = get_arg_value("intermediate_folder")
    dem = get_arg_value("terrain_path") # DEM path is passed as terrain_path

    epsg_code = int(get_arg_value("utm_epsg"))

    # Get the General Python Interpreter path
    general_python_interpreter = get_arg_value("general_interpreter")
    
    # Validation
    if not all([city, intermediate_folder, dem, general_python_interpreter]):
        missing_args = []
        if not city: missing_args.append("city_name")
        if not intermediate_folder: missing_args.append("intermediate_folder")
        if not dem: missing_args.append("terrain_path (DEM)")
        if not general_python_interpreter: missing_args.append("general_interpreter")
        raise ValueError(f"Missing required arguments: {', '.join(missing_args)}")

except Exception as e:
    print(f"Error parsing command-line arguments: {e}")
    sys.exit(1)

arcpy.env.overwriteOutput = True
arcpy.env.parallelProcessingFactor = "100%"

spatial_ref = arcpy.SpatialReference(epsg_code)
arcpy.env.outputCoordinateSystem = spatial_ref

# Define the specific output directory inside the intermediate folder
dem_output_dir = os.path.join(intermediate_folder, "DEM")
os.makedirs(dem_output_dir, exist_ok=True) 

# Set absolute paths for intermediate data using the parsed intermediate_folder
out_contour = os.path.join(dem_output_dir, f"{city}_DEM_Contour.shp")
out_multipoint = os.path.join(dem_output_dir, f"{city}_DEM_Multipoint.shp")

print(f"Starting Contour generation for {city}...")
Contour(dem, out_contour, contour_interval=5)
print(f"Contour feature class saved to: {out_contour}")

print("Converting Contour to Multipoint...")

arcpy.management.FeatureToPoint(out_contour, out_multipoint)
print(f"Multipoint feature class saved to: {out_multipoint}")

in_features = out_multipoint
output_type = "DXF_R2018"
output_file = os.path.join(dem_output_dir, f"{city}_DEM_Multipoint.dxf")

print(f"Exporting Multipoint to DXF file: {output_file}")
arcpy.conversion.ExportCAD(in_features, output_type, output_file, 
                           "USE_FILENAMES_IN_TABLES", "OVERWRITE_EXISTING_FILES")

print("ArcPy Terrain Pre-processing Done.")
print("All steps completed successfully in DEM_to_Multipoint.py.")