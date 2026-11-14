import os
import subprocess
import datetime
import sys
import argparse
import json

# Try to import PyYAML safely for yaml configuration files.
# If not installed, users can fall back to JSON config files.
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

# Configuration
FACADE_TYPES = [
    "Green Facades",
    "Living Wall Systems",
    "Green Facades with glazing ratio",
    "Living Wall Systems with glazing ratio"
]
DATETIME_INPUT_FORMAT = "%m-%d %H"

SHP_TO_MODEL_VISUALIZATION = os.path.join("Data_Processing", "shp_to_model_for_visualization.py")

FACADE_CONFIG = {
    "Green Facades": {
        "shp_to_model_script": os.path.join("Data_Processing", "shp_to_model.py"),
        "cluster_buildings_script": os.path.join("Data_Processing", "cluster_buildings.py"),
    },
    "Living Wall Systems": {
        "shp_to_model_script": os.path.join("Data_Processing", "shp_to_model.py"),
        "cluster_buildings_script": os.path.join("Data_Processing", "cluster_buildings.py"),
    },
    "Green Facades with glazing ratio": {
        "shp_to_model_script": os.path.join("Data_Processing", "shp_to_model_with_glazing_ratio.py"),
        "cluster_buildings_script": os.path.join("Data_Processing", "cluster_buildings_with_glazing_ratio.py"),
    },
    "Living Wall Systems with glazing ratio": {
        "shp_to_model_script": os.path.join("Data_Processing", "shp_to_model_with_glazing_ratio.py"),
        "cluster_buildings_script": os.path.join("Data_Processing", "cluster_buildings_with_glazing_ratio.py"),
    },
}

ERA5_GROUND_TEMPRATURE = os.path.join("Data_Processing", "ERA5_ground_temperature.py")

VIEW_FACTOR_SCRIPT = {
    "Green Facades": {
        "model_to_rad": os.path.join("View_Factors_Computation", "model_to_rad_for_view_factors.py"),
        "Sky_View" : os.path.join("View_Factors_Computation", "Sky_View.py"),
        "Building_View_Factors": os.path.join("View_Factors_Computation", "BVF.py"),
        "View_Factors_Results_Process": os.path.join("View_Factors_Computation", "view_factors_result_process.py"),
    },
    "Living Wall Systems": {
        "model_to_rad": os.path.join("View_Factors_Computation", "model_to_rad_for_view_factors.py"),
        "Sky_View" : os.path.join("View_Factors_Computation", "Sky_View.py"),
        "Building_View_Factors": os.path.join("View_Factors_Computation", "BVF.py"),
        "View_Factors_Results_Process": os.path.join("View_Factors_Computation", "view_factors_result_process.py"),
    },
    "Green Facades with glazing ratio": {
        "model_to_rad": os.path.join("View_Factors_Computation", "model_to_rad_for_view_factors_with_glazing_ratio.py"),
        "Sky_View" : os.path.join("View_Factors_Computation", "Sky_View_with_glazing_ratio.py"),
        "Building_View_Factors": os.path.join("View_Factors_Computation", "BVF_with_glazing_ratio.py"),
        "View_Factors_Results_Process": os.path.join("View_Factors_Computation", "view_factors_result_process_with_glazing_ratio.py"),
    },
    "Living Wall Systems with glazing ratio": {
        "model_to_rad": os.path.join("View_Factors_Computation", "model_to_rad_for_view_factors_with_glazing_ratio.py"),
        "Sky_View" : os.path.join("View_Factors_Computation", "Sky_View_with_glazing_ratio.py"),
        "Building_View_Factors": os.path.join("View_Factors_Computation", "BVF_with_glazing_ratio.py"),
        "View_Factors_Results_Process": os.path.join("View_Factors_Computation", "view_factors_result_process_with_glazing_ratio.py"),
    },
}

SOLAR_IRRADIATION_SCRIPT_STANDARD = {
    "model_to_rad": os.path.join("Solar_Irradiation_Calculation", "model_to_rad_for_solar.py"),
    "joint": os.path.join("Data_Processing", "joint.py"),
    "Solar_Irradiation": os.path.join("Solar_Irradiation_Calculation", "Point-in-Time_Grid_solar_irradiation.py"),
    "Solar_Results_Process": os.path.join("Solar_Irradiation_Calculation", "solar_result_process.py"),
}
SOLAR_IRRADIATION_SCRIPT_GLAZING = {
    "model_to_rad": os.path.join("Solar_Irradiation_Calculation", "model_to_rad_for_solar_with_glazing_ratio.py"),
    "joint": os.path.join("Data_Processing", "joint_with_glazing_ratio.py"),
    "Solar_Irradiation": os.path.join("Solar_Irradiation_Calculation", "Point-in-Time_Grid_solar_irradiation_with_glazing_ratio.py"),
    "Solar_Results_Process": os.path.join("Solar_Irradiation_Calculation", "solar_result_process_with_glazing_ratio.py"),
}

MORPHOLOGICAL_TESSELLATION_SCRIPT = os.path.join("Microclimate_Simulation", "morphological_tessellation.py")

HOMOGENEOUS_MORPHOLOGICAL_UNITS_SCRIPT = os.path.join("Microclimate_Simulation/ArcPy", "classify_homogeneous_morphological_units.py")
HOMOGENEOUS_MORPHOLOGICAL_UNITS_SCRIPT_GLAZING = os.path.join("Microclimate_Simulation/ArcPy", "classify_homogeneous_morphological_units_with_glazing_ratio.py")

MICROCLIMATE_SCRIPT = {
    "Green Facades": {
        "VCWG_GF": os.path.join("Microclimate_Simulation", "VCWG_GF.py"),
        "VCWG_origin": os.path.join("Microclimate_Simulation", "VCWG_origin.py"),
        "VCWG_Results_Process_GF" : os.path.join("Microclimate_Simulation", "VCWG_result_process_GF.py"),
        "VCWG_cooling_output_GF": os.path.join("Microclimate_Simulation", "VCWG_cooling_output_GF.py"),
    },
    "Living Wall Systems": {
        "VCWG_LWS": os.path.join("Microclimate_Simulation", "VCWG_LWS.py"),
        "VCWG_origin": os.path.join("Microclimate_Simulation", "VCWG_origin.py"),
        "VCWG_Results_Process_LWS" : os.path.join("Microclimate_Simulation", "VCWG_result_process_LWS.py"),
        "VCWG_cooling_output_LWS": os.path.join("Microclimate_Simulation", "VCWG_cooling_output_LWS.py"),
    },
    "Green Facades with glazing ratio": {
        "VCWG_GF": os.path.join("Microclimate_Simulation", "VCWG_GF_with_glazing_ratio.py"),
        "VCWG_origin": os.path.join("Microclimate_Simulation", "VCWG_origin_with_glazing_ratio.py"),
        "VCWG_Results_Process_GF" : os.path.join("Microclimate_Simulation", "VCWG_result_process_with_glazing_ratio_GF.py"),
        "VCWG_cooling_output_GF": os.path.join("Microclimate_Simulation", "VCWG_cooling_output_glazing_ratio_GF.py"),
    },
    "Living Wall Systems with glazing ratio": {
        "VCWG_LWS": os.path.join("Microclimate_Simulation", "VCWG_LWS_with_glazing_ratio.py"),
        "VCWG_origin": os.path.join("Microclimate_Simulation", "VCWG_origin_with_glazing_ratio.py"),
        "VCWG_Results_Process_LWS" : os.path.join("Microclimate_Simulation", "VCWG_result_process_with_glazing_ratio_LWS.py"),
        "VCWG_cooling_output_LWS": os.path.join("Microclimate_Simulation", "VCWG_cooling_output_glazing_ratio_LWS.py"),
    },
}

TERRAIN_PROCESSING_SCRIPT = os.path.join("Data_Processing/ArcPy", "DEM_to_Multipoint.py")
MULTIPOINT_TO_TERRAIN_SCRIPT = os.path.join("Data_Processing", "multipoint_to_terrain.py")

FACADE_NUMERICAL_SCRIPT_MAPPING = {
    "Green Facades": os.path.join("Numerical_Models", "numerical_model_for_Green_Wall.py"),
    "Living Wall Systems": os.path.join("Numerical_Models", "numerical_model_for_Living_Wall_Systems.py"),
    "Green Facades with glazing ratio": os.path.join("Numerical_Models", "numerical_model_for_Green_Wall_with_glazing_ratio.py"),
    "Living Wall Systems with glazing ratio": os.path.join("Numerical_Models", "numerical_model_for_Living_Wall_Systems_with_glazing_ratio.py"),
}

ENERGY_CALCULATION_SCRIPT = {
    "Green Facades": os.path.join("Statistics", "energy_calculation_GF.py"),
    "Living Wall Systems": os.path.join("Statistics", "energy_calculation_LWS.py"),
    "Green Facades with glazing ratio": os.path.join("Statistics", "energy_calculation_GF_with_glazing_ratio.py"),
    "Living Wall Systems with glazing ratio": os.path.join("Statistics", "energy_calculation_LWS_with_glazing_ratio.py"),
}

VISUALIZATION_SCRIPT = {
    "Green Facades": {
        "extract_visualization_results": os.path.join("Visualization", "extract_visualization_results_GF.py"),
        "visualization": os.path.join("Visualization", "visualization_GF.py"),
    },
    "Living Wall Systems": {
        "extract_visualization_results": os.path.join("Visualization", "extract_visualization_results_LWS.py"),
        "visualization": os.path.join("Visualization", "visualization_LWS.py"),
    },
    "Green Facades with glazing ratio": {
        "extract_visualization_results": os.path.join("Visualization", "extract_visualization_results_GF_with_glazing_ratio.py"),
        "visualization": os.path.join("Visualization", "visualization_GF_with_glazing_ratio.py"),
    },
    "Living Wall Systems with glazing ratio": {
        "extract_visualization_results": os.path.join("Visualization", "extract_visualization_results_LWS_with_glazing_ratio.py"),
        "visualization": os.path.join("Visualization", "visualization_LWS_with_glazing_ratio.py"),
    },
}

# CORE API FUNCTION
def run_simulation(shp_file, epw_file, terrain_flag, terrain_path, start_datetime_str, end_datetime_str, 
                   selected_facade_types, city_name, general_python_interpreter_path, arcpy_interpreter_path, 
                   ladybug_path, intermediate_folder, result_folder, gpu_flag, grid_size, num_threads, 
                   era5_year, era5_time_zone, era5_bounding_box, utm_epsg,
                   height_field, microclimate_sim_dir, data_processing_dir, LAI, wall_absorptivity, U_value, wall_thickness, rho_of_wall, c_pw,
                   building_typology_field, glazing_ratio_field, visualization_times):
    """
    Python API to run the city-scale VGS simulation.
    Replaces raw tkinter dialog popups with standard Python exceptions.
    """
    print("\n[VGS API] Simulation Start")

    has_glazing_simulation = any("glazing ratio" in ft for ft in selected_facade_types)
    
    if has_glazing_simulation:
        if not building_typology_field or str(building_typology_field).strip() == "":
            raise ValueError("building_typology_field must be specified when simulating with glazing ratio.")
        if not glazing_ratio_field or str(glazing_ratio_field).strip() == "":
            raise ValueError("glazing_ratio_field must be specified when simulating with glazing ratio.")
    else:
        if not building_typology_field:
            building_typology_field = "None"
        if not glazing_ratio_field:
            glazing_ratio_field = "None"

    # Input Validation
    try:
        grid_size_float = float(grid_size)
        if grid_size_float <= 0:
            raise ValueError("Grid size must be a positive number.")
    except ValueError as e:
        raise ValueError(f"Invalid grid size format: {e}")

    try:
        num_threads_int = int(num_threads)
        if num_threads_int <= 0:
            raise ValueError("Number of threads must be a positive integer.")
    except ValueError as e:
        raise ValueError(f"Invalid thread count format: {e}")

    # Time Parsing
    try:
        start_parts = start_datetime_str.strip().split()
        if len(start_parts) != 2:
            raise ValueError("Start time format should be MM-DD HH")
        start_date_str, start_hour_str = start_parts
        start_month, start_day = map(int, start_date_str.split('-'))
        start_hour_input = int(start_hour_str)

        end_parts = end_datetime_str.strip().split()
        if len(end_parts) != 2:
            raise ValueError("End time format should be MM-DD HH")
        end_date_str, end_hour_str = end_parts
        end_month, end_day = map(int, end_date_str.split('-'))
        end_hour_input = int(end_hour_str)

        if not (0 <= start_hour_input <= 23) or not (1 <= end_hour_input <= 23):
            raise ValueError("Hour must be between 00 and 23 for start and 01 and 23 for end")

        start_h = 0 if start_hour_input == 24 else start_hour_input
        end_h = 0 if end_hour_input == 24 else end_hour_input

        current_year = datetime.datetime.now().year
        start_datetime = datetime.datetime(current_year, start_month, start_day, start_h)
        end_datetime = datetime.datetime(current_year, end_month, end_day, end_h)

        if end_hour_input == 24:
            end_datetime += datetime.timedelta(days=1)
    except Exception as e:
        raise ValueError(f"Date/Time parsing failed. Ensure format is 'MM-DD HH'. Error: {e}")

    # Calculate hour of the year
    try:
        year_start = datetime.datetime(current_year, 1, 1)
        start_hour = (start_datetime - year_start).total_seconds() / 3600
        end_hour = (end_datetime - year_start).total_seconds() / 3600
    except Exception as e:
        raise ValueError(f"Date calculation failed: {e}")

    if not (0 <= start_hour <= 8760 and 0 <= end_hour <= 8760 and start_hour <= end_hour):
        raise ValueError("Invalid start or end datetime. Simulation period must be valid within a single year.")

    # Define common pipeline arguments
    common_args = [
        "shp", shp_file,
        "epw_file", epw_file,
        "start_dt", start_datetime_str,
        "end_dt", end_datetime_str,
        "terrain_flag", str(terrain_flag),
        "city_name", city_name,
        "intermediate_folder", intermediate_folder,
        "result_folder", result_folder,
        "general_interpreter", general_python_interpreter_path,
        "ladybug_path", ladybug_path,
        "gpu_flag", str(gpu_flag),
        "grid_size", str(grid_size_float),
        "num_threads", str(num_threads_int),
        "era5_year", str(era5_year),
        "era5_time_zone", era5_time_zone,
        "era5_bounding_box", str(era5_bounding_box),
        "utm_epsg", str(utm_epsg),
        "height_field", height_field,
        "microclimate_sim_dir", microclimate_sim_dir,
        "data_processing_dir", data_processing_dir,
        "LAI", str(LAI),
        "wall_absorptivity", str(wall_absorptivity),
        "U_value", str(U_value),
        "wall_thickness", str(wall_thickness),
        "rho_of_wall", str(rho_of_wall),
        "c_pw", str(c_pw),
        "building_typology_field", building_typology_field,
        "glazing_ratio_field", glazing_ratio_field,
        "visualization_times", visualization_times,
    ]

    # Validate paths
    if terrain_flag:
        if not os.path.exists(terrain_path):
            raise FileNotFoundError(f"Terrain file not found: {terrain_path}")
        if not os.path.exists(arcpy_interpreter_path):
            raise FileNotFoundError(f"ArcPy Interpreter not found at: {arcpy_interpreter_path}")
        common_args.extend(["terrain_path", terrain_path])
    
    if not general_python_interpreter_path or not os.path.exists(general_python_interpreter_path):
        raise FileNotFoundError(f"General Python Interpreter not found at: {general_python_interpreter_path}")
    
    if terrain_flag and (not ladybug_path or not os.path.isdir(ladybug_path)):
        raise ValueError(f"Terrain pre-processing is enabled. Please provide a valid Ladybug tools directory: {ladybug_path}")

    if not intermediate_folder or not result_folder:
        raise ValueError("Both intermediate_folder and result_folder must be specified.")

    base_dir = os.path.dirname(__file__) if os.path.dirname(__file__) else os.getcwd()
    microclimate_sim_dir = os.path.join(base_dir, "Microclimate_Simulation")
    data_processing_dir = os.path.join(base_dir, "Data_Processing")

    both_non_glazing = ("Green Facades" in selected_facade_types and "Living Wall Systems" in selected_facade_types)
    both_glazing = ("Green Facades with glazing ratio" in selected_facade_types and "Living Wall Systems with glazing ratio" in selected_facade_types)
    
    run_once_done = set()
    run_once_scripts = {
        SHP_TO_MODEL_VISUALIZATION,
        ERA5_GROUND_TEMPRATURE,
        MORPHOLOGICAL_TESSELLATION_SCRIPT,
        TERRAIN_PROCESSING_SCRIPT,
        MULTIPOINT_TO_TERRAIN_SCRIPT,
        HOMOGENEOUS_MORPHOLOGICAL_UNITS_SCRIPT,
        HOMOGENEOUS_MORPHOLOGICAL_UNITS_SCRIPT_GLAZING,
    }

    # Execute simulation loop
    for facade_type in selected_facade_types:
        print(f"\n[VGS API] Processing configuration for: {facade_type}")

        config = FACADE_CONFIG.get(facade_type)
        if not config:
            raise KeyError(f"Configuration map not found for facade type: {facade_type}")

        shp_to_model_visualization_script = SHP_TO_MODEL_VISUALIZATION
        facade_data_script = config.get("shp_to_model_script")
        cluster_buildings_script = config.get("cluster_buildings_script")
        facade_numerical_script = FACADE_NUMERICAL_SCRIPT_MAPPING.get(facade_type)
        ground_temperature_script = ERA5_GROUND_TEMPRATURE
        view_factors_script = VIEW_FACTOR_SCRIPT.get(facade_type)

        if not facade_data_script or not cluster_buildings_script or not facade_numerical_script or not view_factors_script:
            raise KeyError(f"Missing script configuration paths for facade type: {facade_type}")

        solar_script = SOLAR_IRRADIATION_SCRIPT_GLAZING if "glazing ratio" in facade_type else SOLAR_IRRADIATION_SCRIPT_STANDARD
        morpho_tessel_script = MORPHOLOGICAL_TESSELLATION_SCRIPT
        homogeneous_script = HOMOGENEOUS_MORPHOLOGICAL_UNITS_SCRIPT_GLAZING if "glazing ratio" in facade_type else HOMOGENEOUS_MORPHOLOGICAL_UNITS_SCRIPT

        # Pipeline orchestration
        skip_geometry_steps = False
        if facade_type == "Living Wall Systems" and both_non_glazing:
            skip_geometry_steps = True
        elif facade_type == "Living Wall Systems with glazing ratio" and both_glazing:
            skip_geometry_steps = True

        steps_to_execute = []

        if not skip_geometry_steps:
            if terrain_flag:
                steps_to_execute.append((TERRAIN_PROCESSING_SCRIPT, "Terrain Pre-processing"))
                steps_to_execute.append((MULTIPOINT_TO_TERRAIN_SCRIPT, "Multi-point to Terrain Processing"))

            steps_to_execute.append((morpho_tessel_script, "Morphological Tessellation"))
            steps_to_execute.append((homogeneous_script, "Homogeneous Morphological Units Classification"))
            steps_to_execute.append((facade_data_script, "Data Pre-processing (Facade-specific)"))
            steps_to_execute.append((cluster_buildings_script, "Building Clustering"))
            steps_to_execute.append((shp_to_model_visualization_script, "Shapefile to Model Visualization"))
            steps_to_execute.append((ground_temperature_script, "ERA5 Ground Temperature Processing"))
            
            # Solar Irradiation
            steps_to_execute.append((solar_script.get("model_to_rad"), "Solar: Model Conversion"))
            steps_to_execute.append((solar_script.get("joint"), "Solar: Joint Calculation"))
            steps_to_execute.append((solar_script.get("Solar_Irradiation"), "Solar: Irradiation Calculation"))
            steps_to_execute.append((solar_script.get("Solar_Results_Process"), "Solar: Result Processing"))

            # View Factors
            steps_to_execute.append((view_factors_script.get("model_to_rad"), "View Factors: Model Conversion"))
            steps_to_execute.append((view_factors_script.get("Sky_View"), "View Factors: Sky View Calculation"))
            steps_to_execute.append((view_factors_script.get("Building_View_Factors"), "View Factors: Building View Calculation"))
            steps_to_execute.append((view_factors_script.get("View_Factors_Results_Process"), "View Factors: Result Processing"))

        # Microclimate
        microclimate_map = MICROCLIMATE_SCRIPT.get(facade_type, {})
        if microclimate_map:
            # Re-initialize internally (API/CLI users do not need to provide these arguments)
            LWS_view_factors_flag = False
            LWS_view_factors_with_glazing_ratio_flag = False

            if facade_type == "Living Wall Systems" and both_non_glazing:
                LWS_view_factors_flag = True
            if facade_type == "Living Wall Systems with glazing ratio" and both_glazing:
                LWS_view_factors_with_glazing_ratio_flag = True

            if microclimate_map.get("VCWG_GF"):
                steps_to_execute.append((microclimate_map.get("VCWG_GF"), "Microclimate: VCWG GF"))
            if microclimate_map.get("VCWG_LWS"):
                steps_to_execute.append((microclimate_map.get("VCWG_LWS"), "Microclimate: VCWG LWS"))

            origin_script = microclimate_map.get("VCWG_origin")
            if origin_script:
                if not ((facade_type == "Living Wall Systems" and LWS_view_factors_flag) or (facade_type == "Living Wall Systems with glazing ratio" and LWS_view_factors_with_glazing_ratio_flag)):
                    steps_to_execute.append((origin_script, "Microclimate: Origin"))

            if microclimate_map.get("VCWG_Results_Process_GF"):
                steps_to_execute.append((microclimate_map.get("VCWG_Results_Process_GF"), "Microclimate: Results Process GF"))
            if microclimate_map.get("VCWG_Results_Process_LWS"):
                steps_to_execute.append((microclimate_map.get("VCWG_Results_Process_LWS"), "Microclimate: Results Process LWS"))
            if microclimate_map.get("VCWG_cooling_output_GF"):
                steps_to_execute.append((microclimate_map.get("VCWG_cooling_output_GF"), "Microclimate: Cooling Output GF"))
            if microclimate_map.get("VCWG_cooling_output_LWS"):
                steps_to_execute.append((microclimate_map.get("VCWG_cooling_output_LWS"), "Microclimate: Cooling Output LWS"))

        steps_to_execute.append((facade_numerical_script, "Numerical Model"))

        energy_calculation_script = ENERGY_CALCULATION_SCRIPT.get(facade_type)
        if energy_calculation_script:
            steps_to_execute.append((energy_calculation_script, "Energy Calculation"))

        visualization_map = VISUALIZATION_SCRIPT.get(facade_type, {})
        if visualization_map:
            steps_to_execute.append((visualization_map.get("extract_visualization_results"), "Visualization: Extract Results"))
            steps_to_execute.append((visualization_map.get("visualization"), "Visualization: Script"))

        # Build execution arguments
        facade_args = common_args + ["facade_type", facade_type.replace(" ", "")]
        
        # Windows native argument escaping
        quoted_args = facade_args

        for script_rel_path, step_name in steps_to_execute:
            full_script_path = os.path.join(base_dir, script_rel_path)
            script_name = os.path.basename(full_script_path)

            if script_rel_path == TERRAIN_PROCESSING_SCRIPT and terrain_flag:
                interpreter = arcpy_interpreter_path
            elif script_rel_path in (HOMOGENEOUS_MORPHOLOGICAL_UNITS_SCRIPT, HOMOGENEOUS_MORPHOLOGICAL_UNITS_SCRIPT_GLAZING):
                interpreter = arcpy_interpreter_path
            else:
                interpreter = general_python_interpreter_path

            if script_rel_path in run_once_scripts and script_rel_path in run_once_done:
                print(f"[VGS API] Skipping completed one-time step: {script_name}")
                continue

            if not os.path.exists(full_script_path):
                raise FileNotFoundError(f"Required pipeline script not found: {full_script_path}")

            print(f"[VGS API] Executing Step: {step_name} ({script_name}) using {interpreter}...")
            
            cmd = [interpreter, full_script_path] + quoted_args

            try:
                result = subprocess.run(
                    cmd, 
                    check=True, 
                    cwd=base_dir
                )
                stdout_val = result.stdout.strip() if result.stdout else ""
                print(f"[VGS API] Success: {script_name}\nSnippet:\n{stdout_val[:100]}...\n")
                
                if script_rel_path in run_once_scripts:
                    run_once_done.add(script_rel_path)
            except subprocess.CalledProcessError as e:
                err_msg = e.stderr.strip() if e.stderr else "Unknown error (No stderr captured)."
                raise RuntimeError(
                    f"Pipeline script '{script_name}' failed during '{step_name}'.\n"
                    f"Error Details:\n{err_msg}"
                ) from e
            except FileNotFoundError:
                raise FileNotFoundError(f"Target python interpreter not found: {interpreter}")

        print(f"[VGS API] Facade simulation sequence finished for {facade_type}.")

    print("\n[VGS API] All selected simulation phases complete successfully.")


# CLI PARSER & LAUNCHER
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Unified Command Line Interface (CLI) for City-Scale VGS Simulation Pipeline."
    )
    
    # Configuration File Option
    parser.add_argument(
        "--config", 
        type=str, 
        default="", 
        help="Path to a YAML or JSON configuration file. If provided, command line options are overwritten by the file."
    )
    
    # CLI Pipeline Parameters
    parser.add_argument("--shp", type=str, default="", help="Path to the building shapefile (.shp)")
    parser.add_argument("--epw-file", type=str, default="", help="Path to the weather EPW file (.epw)")
    parser.add_argument("--terrain-flag", action="store_true", help="Include terrain DEM processing")
    parser.add_argument("--terrain-path", type=str, default="", help="Path to the terrain raster (.tif)")
    parser.add_argument("--start-dt", type=str, default="07-23 00", help="Start datetime (MM-DD HH)")
    parser.add_argument("--end-dt", type=str, default="07-23 23", help="End datetime (MM-DD HH)")
    parser.add_argument("--facade-types", nargs="+", choices=FACADE_TYPES, default=["Green Facades"], help="Facade simulation types to execute")
    parser.add_argument("--city-name", type=str, default="", help="City name (use underscores instead of spaces)")
    parser.add_argument("--general-interpreter", type=str, default=sys.executable, help="Path to General Python Interpreter executable")
    parser.add_argument("--arcpy-interpreter", type=str, default="", help="Path to ArcPy/Esri Python Interpreter executable")
    parser.add_argument("--ladybug-path", type=str, default="C:/Users/Administrator/ladybug_tools", help="Ladybug tools directory path")
    parser.add_argument("--intermediate-folder", type=str, default="", help="Directory for storing intermediate model cache")
    parser.add_argument("--result-folder", type=str, default="", help="Directory for storing final simulation results")
    parser.add_argument("--no-gpu", dest="gpu_flag", action="store_false", help="Disable GPU acceleration (GPU enabled by default)")
    parser.set_defaults(gpu_flag=True)
    parser.add_argument("--grid-size", type=str, default="3.0", help="Grid size on facades (meters)")
    parser.add_argument("--num-threads", type=str, default="4", help="Parallel execution thread count")
    parser.add_argument("--era5-year", type=str, default="2026", help="Target ERA5 weather year")
    parser.add_argument("--era5-time-zone", type=str, default="Asia/Shanghai", help="Target ERA5 local time zone")
    parser.add_argument("--era5-bounding-box", type=str, default="30.6,114.2,30.4,114.4", help="Target ERA5 bounding box (N,W,S,E)")
    parser.add_argument("--utm-epsg", type=str, default="0", help="Forced target local UTM EPSG code")
    parser.add_argument("--LAI", type=str, default="3.0", help="Leaf Area Index (LAI)")
    parser.add_argument("--wall-absorptivity", type=str, default="0.65", help="Wall solar absorptivity")
    parser.add_argument("--u-value", type=str, default="2.0", help="U-value of the wall")
    parser.add_argument("--wall-thickness", type=str, default="0.24", help="Wall thickness (meters)")
    parser.add_argument("--rho-of-wall", type=str, default="2000", help="Density of Wall Material (kg/m3)")
    parser.add_argument("--c-pw", type=str, default="1000", help="Specific Heat Capacity (J/kgK)")
    parser.add_argument("--building-typology-field", type=str, default="", help="Building Typology Field Name in shapefile")
    parser.add_argument("--glazing-ratio-field", type=str, default="", help="Glazing Ratio Field Name in shapefile")
    parser.add_argument("--visualization-times", type=str, default="07-23 14, 07-23 16-07-23 20", help="Hours scheduled for visualization extraction")
    parser.add_argument("--height-field", type=str, default="height", help="Building height field name in shapefile")

    args = parser.parse_args()

    # If script is run with ZERO CLI arguments (e.g. direct click run in VS Code)
    # and config.yaml exists in the current directory, use it automatically.
    if len(sys.argv) == 1 and os.path.exists("config.yaml"):
        args.config = "config.yaml"

    # Dictionary to hold the final parameters
    params = vars(args)

    # If configuration file path is provided, read and overwrite parameters
    if args.config:
        if not os.path.exists(args.config):
            print(f"[VGS CLI Error] Configuration file not found at: {args.config}")
            sys.exit(1)
        
        print(f"[VGS CLI] Loading parameters from config file: {args.config}")
        with open(args.config, "r", encoding="utf-8") as f:
            if args.config.endswith(".yaml") or args.config.endswith(".yml"):
                if not HAS_YAML:
                    print("[VGS CLI Error] PyYAML is not installed. Please 'pip install pyyaml' or use a .json configuration file.")
                    sys.exit(1)
                config_data = yaml.safe_load(f)
            else:
                config_data = json.load(f)
        
        # Map values from config file
        if config_data:
            for key, val in config_data.items():
                if key in params:
                    params[key] = val
                else:
                    print(f"[VGS CLI Warning] Ignored unrecognized configuration parameter: {key}")

    # Core Execution
    try:
        run_simulation(
            shp_file=params["shp"],
            epw_file=params["epw_file"],
            terrain_flag=params["terrain_flag"],
            terrain_path=params["terrain_path"],
            start_datetime_str=params["start_dt"],
            end_datetime_str=params["end_dt"],
            selected_facade_types=params["facade_types"],
            city_name=params["city_name"],
            general_python_interpreter_path=params["general_interpreter"],
            arcpy_interpreter_path=params["arcpy_interpreter"],
            ladybug_path=params["ladybug_path"],
            intermediate_folder=params["intermediate_folder"],
            result_folder=params["result_folder"],
            gpu_flag=params["gpu_flag"],
            grid_size=params["grid_size"],
            num_threads=params["num_threads"],
            era5_year=params["era5_year"],
            era5_time_zone=params["era5_time_zone"],
            era5_bounding_box=params["era5_bounding_box"],
            utm_epsg=params["utm_epsg"],
            height_field=params["height_field"],
            microclimate_sim_dir=os.path.join(os.getcwd(), "Microclimate_Simulation"),
            data_processing_dir=os.path.join(os.getcwd(), "Data_Processing"),
            LAI=params["LAI"],
            wall_absorptivity=params["wall_absorptivity"],
            U_value=params["u_value"],
            wall_thickness=params["wall_thickness"],
            rho_of_wall=params["rho_of_wall"],
            c_pw=params["c_pw"],
            building_typology_field=params["building_typology_field"],
            glazing_ratio_field=params["glazing_ratio_field"],
            visualization_times=params["visualization_times"]
        )
        print("[VGS CLI] Pipeline simulation execution finished successfully.")
    except Exception as e:
        import traceback
        print(f"\n[VGS CLI Fatal Error] Execution aborted: {e}")
        print(traceback.format_exc())
        sys.exit(1)