import pandas as pd
import os
import shutil
import math
import numpy
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
import sys
import datetime
import re

# Helper function to parse command-line arguments (key-value pairs)
def parse_args(args):
    arg_dict = {}
    for i in range(0, len(args), 2):
        key = args[i].strip('\'"')
        val = args[i+1].strip('\'"') if i + 1 < len(args) else None
        arg_dict[key] = val
    return arg_dict

args = parse_args(sys.argv[1:])

city = args.get('city_name')
intermediate_folder = args.get('intermediate_folder')

year = args.get('era5_year')

threads = int(args.get('num_threads'))

albedo = 1 - float(args.get('wall_absorptivity'))

# Extract variables from arguments
ladybug_folder = args.get('ladybug_path')

# Setup Ladybug paths dynamically using the passed argument
if not ladybug_folder:
    print("Error: ladybug_path not provided. Cannot initialize Rhino/Ladybug environment.")
    sys.exit(1)

# Add the site-packages path within the Ladybug installation to sys.path
ladybug_python = os.path.join(ladybug_folder, "python/Lib/site-packages")
sys.path.append(ladybug_python)
queenbee_path = os.path.join(ladybug_folder, "python/Scripts/queenbee.exe")

import ladybug.analysisperiod as ap
from ladybug.wea import Wea

epw_file = args.get('epw_file')
if not epw_file or not os.path.exists(epw_file):
    print("Error: EPW file not found. Cannot determine sunrise/sunset.")
    sys.exit(1)

# Use the actual EPW filename when updating template scripts
epw_basename = os.path.basename(epw_file)

try:
    wea = Wea.from_epw_file(epw_file)
    ghi_coll = wea.global_horizontal_irradiance
except Exception as e:
    print(f"Failed to load EPW: {e}")
    sys.exit(1)

microclimate_sim_dir = args.get('microclimate_sim_dir')

LAI = float(args.get('LAI'))  # Leaf Area Index

def parse_mmdd_hh_label(s):
    """Parse 'MM-DD HH' where HH is 0..23 and return (month, day, hour) or None."""
    try:
        mmdd, hh = s.rsplit(' ', 1)
        hh_int = int(hh)
        if not (0 <= hh_int <= 23):
            return None
        dt = datetime.datetime.strptime(mmdd, "%m-%d")
        return (dt.month, dt.day, hh_int)
    except Exception:
        return None

# Determine run interval from arguments: prefer 'start_dt'/'end_dt' strings like "MM-DD HH"
start_dt_arg = args.get('start_dt')
end_dt_arg = args.get('end_dt')

start_parsed = parse_mmdd_hh_label(start_dt_arg) if start_dt_arg else None
end_parsed = parse_mmdd_hh_label(end_dt_arg) if end_dt_arg else None

if start_parsed is None or end_parsed is None:
    raise ValueError("Invalid or missing start_dt/end_dt format. Must be 'MM-DD HH' (HH: 0-23)")

s_m, s_d, s_h = start_parsed
e_m, e_d, e_h = end_parsed

current_year = datetime.datetime.now().year
start_dt = datetime.datetime(current_year, s_m, s_d, s_h)
end_dt = datetime.datetime(current_year, e_m, e_d, e_h)

if end_dt < start_dt:
    end_dt = end_dt.replace(year=current_year + 1)

if end_dt < start_dt:
    raise ValueError("End datetime must not be earlier than start datetime.")

dates_set = set()
current = start_dt

while current <= end_dt:
    dates_set.add((current.month, current.day))
    current += datetime.timedelta(hours=1)

dates_arr = sorted([[month, day] for month, day in dates_set])

sun_rise_down = numpy.zeros((len(dates_arr), 2), dtype=int)

error_written = False  # Flag to track if anything was written to error_txt

# Define paths
base_dir = os.path.join(intermediate_folder, f"microclimate_simulation/VCWG_{city}/")
template_dir = os.path.join(microclimate_sim_dir, f"VCWGv2.0.0  for Green Facades/")
run_script_path = os.path.join(template_dir, 'Run_VCWGv2.0.0.py')

vcwg_epw = os.path.join(template_dir, 'resources/epw/').replace('\\', '/')

epw_exists = False
if os.path.exists(vcwg_epw) and os.path.isdir(vcwg_epw):
    for file_name in os.listdir(vcwg_epw):
        if file_name.lower().endswith('.epw'):
            epw_exists = True
            break

if not epw_exists:
    shutil.copy(epw_file, vcwg_epw)
    print(f"Copied EPW file to: {vcwg_epw}")

# Load data
df = pd.read_excel(os.path.join(intermediate_folder, f"{city}_basic_data/{city}_classes.xlsx"))

error_txt = os.path.join(intermediate_folder, 'VCWG_error.txt')

if os.path.exists(error_txt):
    with open(error_txt, 'w') as f:
        pass

# Ensure the base directory exists
if not os.path.exists(base_dir):
    os.makedirs(base_dir)

# Clear previous results
if os.path.isdir(base_dir):
    contents = os.listdir(base_dir)
    for item in contents:
        item_path = os.path.join(base_dir, item)
        if os.path.isfile(item_path):
            os.remove(item_path)
        elif os.path.isdir(item_path):
            shutil.rmtree(item_path)

for j, date in enumerate(dates_arr):

    month = date[0]
    day = date[1]
    
    # Function to create folder, copy files, and modify .uwg file
    def process_class(class_data):
        class_id = int(class_data['Class_ID'])
        avg_building_height = class_data['wei_bld_he']
        avg_width_roof = class_data['MEAN_roof_']
        canyon_width = class_data['MEAN_canyo']
        orienta_angle = class_data['MEAN_orien']
        h_top = class_data['h_top']

        class_dir = os.path.join(base_dir, f"VCWG_{city}_Class{class_id}/").replace('\\', '/')

        viewfactor_dir = os.path.join(class_dir, f"resources/Parameters/ViewFactor_{city}_Class{class_id}.txt").replace('\\', '/')

        old_viewfactor_dir = os.path.join(intermediate_folder, f"microclimate_simulation/VCWG_ViewFactors/ViewFactor_{city}_Class{class_id}.txt").replace('\\', '/')

        if not os.path.exists(class_dir):
            os.makedirs(class_dir)
            
            # Copy the entire contents of the template directory to the new class directory
            for item in os.listdir(template_dir):
                s = os.path.join(template_dir, item)
                d = os.path.join(class_dir, item)
                if os.path.isdir(s):
                    shutil.copytree(s, d, dirs_exist_ok=True)
                else:
                    shutil.copy2(s, d)

            if os.path.exists(old_viewfactor_dir):
                shutil.copy(old_viewfactor_dir, viewfactor_dir)

            # Modify the .uwg file
            old_uwg_path = os.path.join(class_dir, f"resources/Parameters/initialize_Wuhan_LCZ1.uwg")
            new_uwg_path = os.path.join(os.path.join(class_dir, "resources/Parameters"), f"initialize_{city}_Class{class_id}.uwg")
            os.rename(old_uwg_path, new_uwg_path)
            with open(new_uwg_path, 'r') as file:
                uwg_data = file.read()
            
            #Write parameters into new .uwg file
            uwg_data = uwg_data.replace("nz,90,", f"nz,{math.ceil(h_top)},")
            uwg_data = uwg_data.replace("nz_u,30,", f"nz_u,{math.ceil(avg_building_height)},")
            uwg_data = uwg_data.replace("Width_canyon,10,", f"Width_canyon,{round(canyon_width, 2)},")
            uwg_data = uwg_data.replace("Width_roof,12,", f"Width_roof,{round(avg_width_roof, 2)},")
            uwg_data = uwg_data.replace("theta_canyon,0.0,", f"theta_canyon,{round(orienta_angle, 2)},")
            uwg_data = uwg_data.replace("Height_canyon,30,", f"Height_canyon,{round(avg_building_height, 2)},")

            uwg_data = uwg_data.replace("albedo_W,0.25,", f"albedo_W,{albedo},")

            radius_tree = math.floor(0.1 * canyon_width)
            distance_tree = math.floor(0.2 * canyon_width)

            if radius_tree < 1:
                radius_tree = 1
            if radius_tree > 3:
                radius_tree = 3

            if 8 < avg_building_height < 12 and radius_tree > 2:
                radius_tree = 2
            if avg_building_height <= 8 and radius_tree > 1:
                radius_tree = 1
            if avg_building_height <= 6 and radius_tree > 0.8:
                radius_tree = 0.8
            if avg_building_height <= 4 and radius_tree > 0.5:
                radius_tree = 0.5

            if distance_tree < 2:
                distance_tree = 2
            
            uwg_data = uwg_data.replace("distance_tree,2.0,", f"distance_tree,{distance_tree},")
            uwg_data = uwg_data.replace("Radius_tree,2.0,", f"Radius_tree,{radius_tree},")

            # Do not take trees into consideration temporarily
            uwg_data = uwg_data.replace("fveg_G,0.1,", "fveg_G,0.0,")
            uwg_data = uwg_data.replace("fimp_G,0.9,", "fimp_G,1.0,")

            if avg_building_height < 4:
                uwg_data = uwg_data.replace("0,1,2,3,4,5,6,7,8,", "0,1,2,")
                uwg_data = uwg_data.replace("0,0.002,0.02,0.03,0.046,0.04,0.036,0.02,0.01,", "0,0.002,0.02,")
            if 4 <= avg_building_height < 5:
                uwg_data = uwg_data.replace("0,1,2,3,4,5,6,7,8,", "0,1,2,3,")
                uwg_data = uwg_data.replace("0,0.002,0.02,0.03,0.046,0.04,0.036,0.02,0.01,", "0,0.002,0.02,0.03,")
            if 5 <= avg_building_height <= 6:
                uwg_data = uwg_data.replace("0,1,2,3,4,5,6,7,8,", "0,1,2,3,4,")
                uwg_data = uwg_data.replace("0,0.002,0.02,0.03,0.046,0.04,0.036,0.02,0.01,", "0,0.002,0.02,0.03,0.046,")
            if 6 < avg_building_height < 7:
                uwg_data = uwg_data.replace("0,1,2,3,4,5,6,7,8,", "0,1,2,3,4,5,")
                uwg_data = uwg_data.replace("0,0.002,0.02,0.03,0.046,0.04,0.036,0.02,0.01,", "0,0.002,0.02,0.03,0.046,0.04,")
            if 7 <= avg_building_height < 8:
                uwg_data = uwg_data.replace("0,1,2,3,4,5,6,7,8,", "0,1,2,3,4,5,6,")
                uwg_data = uwg_data.replace("0,0.002,0.02,0.03,0.046,0.04,0.036,0.02,0.01,", "0,0.002,0.02,0.03,0.046,0.04,0.036,")
            if 8 <= avg_building_height < 9:
                uwg_data = uwg_data.replace("0,1,2,3,4,5,6,7,8,", "0,1,2,3,4,5,6,7,")
                uwg_data = uwg_data.replace("0,0.002,0.02,0.03,0.046,0.04,0.036,0.02,0.01,", "0,0.002,0.02,0.03,0.046,0.04,0.036,0.02,")

            uwg_data = uwg_data.replace("WindMin_Urban,0.01,", "WindMin_Urban,0.05,")

            if os.path.exists(viewfactor_dir):
                uwg_data = uwg_data.replace("OPTION_RAY,0,", "OPTION_RAY,1,")

            # Modify specific lines    
            if j == 0:
                uwg_data = uwg_data.replace(f"Month,3,", f"Month,{month},")
                uwg_data = uwg_data.replace(f"Day,20,", f"Day,{day},")
            elif j > 0:
                uwg_data = uwg_data.replace(f"Month,{dates_arr[j-1][0]},", f"Month,{month},")
                uwg_data = uwg_data.replace(f"Day,{dates_arr[j-1][1]},", f"Day,{day},")

            # GHI > 0 indicates daytime (sun up)
            bool_solar_raised_array = []  # 0: night, 1: day

            for i in range(0, 24):
                # Create single-hour AnalysisPeriod
                anp = ap.AnalysisPeriod(month, day, i, month, day, i, 1)
                
                # Get GHI value for this hour
                ghi_value = ghi_coll.filter_by_analysis_period(anp)[0]
                
                if ghi_value > 0:
                    bool_solar_raised_array.append(1)
                else:
                    bool_solar_raised_array.append(0)

            # Find min/max hours with GHI > 0 (daytime hours)
            valid_hours = [i+1 for i, val in enumerate(bool_solar_raised_array) if val == 1]

            if valid_hours:
                sunrise_hour = min(valid_hours)
                sunset_hour = max(valid_hours)

            # Update sun_rise_down array
            sun_rise_down[j][0] = sunrise_hour  # nightEnd
            sun_rise_down[j][1] = sunset_hour   # nightStart

            # Update uwg_data
            if j == 0:
                # First day: replace default values
                uwg_data = uwg_data.replace("nightEnd,6,", f"nightEnd,{sunrise_hour},")
                uwg_data = uwg_data.replace("nightStart,18,", f"nightStart,{sunset_hour},")
            else:
                # Subsequent days: replace previous day's values for continuity
                uwg_data = uwg_data.replace(f"nightEnd,{sun_rise_down[j-1][0]},", f"nightEnd,{sunrise_hour},")
                uwg_data = uwg_data.replace(f"nightStart,{sun_rise_down[j-1][1]},", f"nightStart,{sunset_hour},")

            with open(new_uwg_path, 'w') as file:
                file.write(uwg_data)
            
        else:            
            uwg_path = os.path.join(os.path.join(class_dir, "resources/Parameters"), f"initialize_{city}_Class{class_id}.uwg")
            with open(uwg_path, 'r') as file:
                uwg_data = file.read()

            # Modify specific lines
            if j == 0:
                uwg_data = uwg_data.replace(f"Month,3,", f"Month,{month},")
                uwg_data = uwg_data.replace(f"Day,20,", f"Day,{day},")
            elif j > 0:
                uwg_data = uwg_data.replace(f"Month,{dates_arr[j-1][0]},", f"Month,{month},")
                uwg_data = uwg_data.replace(f"Day,{dates_arr[j-1][1]},", f"Day,{day},")

            # GHI > 0 indicates daytime (sun up)
            bool_solar_raised_array = []  # 0: night, 1: day

            for i in range(0, 24):
                # Create single-hour AnalysisPeriod
                anp = ap.AnalysisPeriod(month, day, i, month, day, i, 1)
                
                # Get GHI value for this hour
                ghi_value = ghi_coll.filter_by_analysis_period(anp)[0]
                
                if ghi_value > 0:
                    bool_solar_raised_array.append(1)
                else:
                    bool_solar_raised_array.append(0)

            # Find min/max hours with GHI > 0 (daytime hours)
            valid_hours = [i+1 for i, val in enumerate(bool_solar_raised_array) if val == 1]

            if valid_hours:
                sunrise_hour = min(valid_hours)
                sunset_hour = max(valid_hours)

            # Update sun_rise_down array
            sun_rise_down[j][0] = sunrise_hour  # nightEnd
            sun_rise_down[j][1] = sunset_hour   # nightStart

            # Update uwg_data
            if j == 0:
                # First day: replace default values
                uwg_data = uwg_data.replace("nightEnd,6,", f"nightEnd,{sunrise_hour},")
                uwg_data = uwg_data.replace("nightStart,18,", f"nightStart,{sunset_hour},")
            else:
                # Subsequent days: replace previous day's values for continuity
                uwg_data = uwg_data.replace(f"nightEnd,{sun_rise_down[j-1][0]},", f"nightEnd,{sunrise_hour},")
                uwg_data = uwg_data.replace(f"nightStart,{sun_rise_down[j-1][1]},", f"nightStart,{sunset_hour},")

            if os.path.exists(viewfactor_dir):
                uwg_data = uwg_data.replace("OPTION_RAY,0,", "OPTION_RAY,1,")

            with open(uwg_path, 'w') as file:
                    file.write(uwg_data)

        # Modify the VCWG_Hydrology.py script
        VCWG_Hydrology_path = os.path.join(class_dir, f"VCWG_Hydrology.py")
        with open(VCWG_Hydrology_path, 'r') as file:
            VCWG_Hydrology_data = file.read()

        VCWG_Hydrology_data = VCWG_Hydrology_data.replace("self.VCWGParamFileName = os.path.join(os.path.join('resources','Parameters'),VCWGParamFileName)", f"self.VCWGParamFileName = os.path.join('{class_dir}/resources/Parameters',VCWGParamFileName)")
        VCWG_Hydrology_data = VCWG_Hydrology_data.replace("self.ViewFactorFileName = os.path.join(os.path.join('resources','Parameters'),ViewFactorFileName)", f"self.ViewFactorFileName = os.path.join('{class_dir}/resources/Parameters',ViewFactorFileName)")
        VCWG_Hydrology_data = VCWG_Hydrology_data.replace("readDOE_file = open('readDOE.PKL', 'rb')", f"readDOE_file = open('{class_dir}/readDOE.PKL', 'rb')")
        VCWG_Hydrology_data = VCWG_Hydrology_data.replace('Output_dir =  "Results"', f"Output_dir = '{class_dir}/Results'")
        
        with open(VCWG_Hydrology_path, 'w') as file:
            file.write(VCWG_Hydrology_data)

        # Modify the weather.py script
        weather_path = os.path.join(class_dir, f"weather.py")
        with open(weather_path, 'r') as file:
            weather_data = file.read()

        weather_data = weather_data.replace("EPW_path = os.path.join('resources','epw')", f"EPW_path = os.path.join('{class_dir}/resources/epw')")

        with open(weather_path, 'w') as file:
            file.write(weather_data)

        # Modify the EB_Canyon.py script
        EB_Canyon_path = os.path.join(class_dir, f"EB_Canyon.py")
        with open(EB_Canyon_path, 'r') as file:
            EB_Canyon_data = file.read()

        EB_Canyon_data = re.sub(r"LAI = [\d.]+", f"LAI = {LAI}", EB_Canyon_data)

        with open(EB_Canyon_path, 'w') as file:
            file.write(EB_Canyon_data)

        # Modify the EB_Wall.py script
        EB_Wall_path = os.path.join(class_dir, f"EB_Wall.py")
        with open(EB_Wall_path, 'r') as file:
            EB_Wall_data = file.read()

        EB_Wall_data = re.sub(r"LAI = [\d.]+", f"LAI = {LAI}", EB_Wall_data)

        with open(EB_Wall_path, 'w') as file:
            file.write(EB_Wall_data)

        # Modify the WB_Canyon.py script
        WB_Canyon_path = os.path.join(class_dir, f"WB_Canyon.py")
        with open(WB_Canyon_path, 'r') as file:
            WB_Canyon_data = file.read()

        WB_Canyon_data = re.sub(r"LAI = [\d.]+", f"LAI = {LAI}", WB_Canyon_data)

        with open(WB_Canyon_path, 'w') as file:
            file.write(WB_Canyon_data)

        # Modify the WB_Wall.py script
        WB_Wall_path = os.path.join(class_dir, f"WB_Wall.py")
        with open(WB_Wall_path, 'r') as file:
            WB_Wall_data = file.read()

        WB_Wall_data = re.sub(r"LAI = [\d.]+", f"LAI = {LAI}", WB_Wall_data)

        with open(WB_Wall_path, 'w') as file:
            file.write(WB_Wall_data)

        # Modify the UrbanSurfaceHeatFlux.py script
        UrbanSurfaceHeatFlux_path = os.path.join(class_dir, f"UrbanSurfaceHeatFlux.py")
        with open(UrbanSurfaceHeatFlux_path, 'r') as file:
            UrbanSurfaceHeatFlux_data = file.read()

            UrbanSurfaceHeatFlux_data = UrbanSurfaceHeatFlux_data.replace(f"VCWG_param_file_path = os.path.join('resources','Parameters','initialize_Wuhan_LCZ1.uwg')", f"VCWG_param_file_path = os.path.join('{class_dir}/resources/Parameters','initialize_{city}_Class{class_id}.uwg')")
            UrbanSurfaceHeatFlux_data = UrbanSurfaceHeatFlux_data.replace(f"epw_file = 'WuhanEPW.epw'", f"epw_file = '{class_dir}/resources/epw/{epw_basename}'")
            UrbanSurfaceHeatFlux_data = re.sub(r"LAI = [\d.]+", f"LAI = {LAI}", UrbanSurfaceHeatFlux_data)

        with open(UrbanSurfaceHeatFlux_path, 'w') as file:
            file.writelines(UrbanSurfaceHeatFlux_data)

        # Modify the Run_VCWGv2.0.0.py script
        run_script_new_path = os.path.join(class_dir, f"Run_VCWGv2.0.0_Class{class_id}.py")
        with open(run_script_path, 'r') as file:
            script_data = file.read()

            script_data = script_data.replace(f'WuhanEPW.epw', f'{epw_basename}')
            script_data = script_data.replace(f'initialize_Wuhan_LCZ1.uwg', f'initialize_{city}_Class{class_id}.uwg')
            script_data = script_data.replace(f'ViewFactor_Wuhan_LCZ1.txt', f'ViewFactor_{city}_Class{class_id}.txt')
            script_data = script_data.replace(f'Wuhan_LCZ1', f'{city}_Class{class_id}')

        with open(run_script_new_path, 'w') as file:
            file.write(script_data)

        origin_run_script_path = os.path.join(class_dir, "Run_VCWGv2.0.0.py")
        if os.path.exists(origin_run_script_path):
            os.remove(origin_run_script_path)

        return run_script_new_path

    # Process all classes and collect paths to run scripts
    run_scripts = []
    for _, row in df.iterrows():
        run_scripts.append(process_class(row))

    # Function to run a script
    def run_script(script_path):
        os.system(f"python {script_path}")

    # Run the scripts in parallel
    with ThreadPoolExecutor(max_workers=threads) as executor:
        executor.map(run_script, run_scripts)

    subdirs = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]  

    for i in range(len(subdirs)):
        result_folder = os.path.join(base_dir, f"VCWG_{city}_Class{i+1}", "Results")
        destination_folder = os.path.join(intermediate_folder, f"VCWG_{city}_Result_GF/{month}.{day}/VCWG_{city}_Class{i+1}/")

        Temperature_path = os.path.join(result_folder, f"th_profiles{city}_Class{i+1}.txt")
        vx_path = os.path.join(result_folder, f"vx_profiles{city}_Class{i+1}.txt")
        vy_path = os.path.join(result_folder, f"vy_profiles{city}_Class{i+1}.txt")
        
        if not os.path.exists(destination_folder):
            os.makedirs(destination_folder)

        if os.path.exists(Temperature_path):
            shutil.copy(Temperature_path, destination_folder)
        if os.path.exists(vx_path):
            shutil.copy(vx_path, destination_folder)
        if os.path.exists(vy_path):
            shutil.copy(vy_path, destination_folder)

        viewfactor_dir = os.path.join(base_dir, f"VCWG_{city}_Class{i+1}/resources/Parameters/ViewFactor_{city}_Class{i+1}.txt")
        viewfactor_folder = os.path.join(intermediate_folder, f"microclimate_simulation/VCWG_ViewFactors/")

        if not os.path.exists(viewfactor_folder):
            os.makedirs(viewfactor_folder)

        if not os.path.exists(viewfactor_dir):
            viewfactor_txt = f"No ViewFactor: Class{i+1}\n"
            with open(error_txt, "a") as file:
                file.write(viewfactor_txt)
                error_written = True
        else:
            shutil.copy(viewfactor_dir, viewfactor_folder)

        if (not os.path.exists(Temperature_path)) or (not os.path.exists(vx_path)) or (not os.path.exists(vy_path)):
            energybalance_txt = f"EnergyBalance Failed at {month} {day}: Class{i+1}\n"
            with open(error_txt, "a") as file:
                file.write(energybalance_txt)
                error_written = True
        if os.path.isdir(result_folder):
            contents = os.listdir(result_folder)
            for item in contents:
                item_path = os.path.join(result_folder, item)
                if os.path.isfile(item_path):
                    os.remove(item_path)
                elif os.path.isdir(item_path):
                    shutil.rmtree(item_path)

print("VCWG results successfully saved")

if error_written:
    print("Some classes missed, please check VCWG_error.txt for details.")