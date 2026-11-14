import os
from multiprocessing import Pool, cpu_count
import numpy as np
import sys
import datetime
from collections import defaultdict
import geopandas as gpd

# Helper function to parse command-line arguments (key-value pairs)
def parse_args(args):
    arg_dict = {}
    for i in range(0, len(args), 2):
        key = args[i].strip('\'"')
        val = args[i+1].strip('\'"') if i + 1 < len(args) else None
        arg_dict[key] = val
    return arg_dict

args = parse_args(sys.argv[1:])

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

city = args.get('city_name')
intermediate_folder = args.get('intermediate_folder')
result_folder = args.get('result_folder')

data_integration_dir = os.path.join(result_folder, "stats/cooling_plots/")
cooling_txt = os.path.join(data_integration_dir, "cooling.txt")

building_typology_field = args.get('building_typology_field')
glazing_ratio_field = args.get('glazing_ratio_field')

cpu_count = 2

if not os.path.exists(data_integration_dir):
    os.makedirs(data_integration_dir)

projected_buildings = os.path.join(intermediate_folder, "footprint/projected.shp")
building_shp_projected = gpd.read_file(projected_buildings)

unique_pairs = building_shp_projected[[building_typology_field, glazing_ratio_field]].drop_duplicates().dropna()

bld_types_and_WWR = {}
for i, (_, row) in enumerate(unique_pairs.iterrows(), start=101):
    typology = str(row[building_typology_field])
    wwr = float(row[glazing_ratio_field])
    bld_types_and_WWR[i] = (typology, wwr)

def validate_building_typology(shp_path, typology_field, bld_types_and_WWR):
    """
    Validate that all values in the specified typology field of the Shapefile
    are within the allowed codes defined in bld_types_and_WWR.
    
    - If only some of the 10 types exist: pass
    - If unknown codes appear: error and exit
    """
    if not typology_field:
        print("Warning: No building_typology_field provided. All buildings will use default glazing ratios.")
        return None

    try:
        gdf = gpd.read_file(shp_path)
        
        if typology_field not in gdf.columns:
            print(f"Error: Field '{typology_field}' not found in Shapefile.")
            print(f"Available fields: {list(gdf.columns)}")
            sys.exit(1)
        
    except ImportError:
        print("Error: geopandas is required for typology validation. Please install it.")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading Shapefile for typology validation: {e}")
        sys.exit(1)

building_typology_field = args.get('building_typology_field')
validate_building_typology(
    shp_path=args.get('shp'),
    typology_field=building_typology_field,
    bld_types_and_WWR=bld_types_and_WWR
)

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

first_month = dates_arr[0][0]
first_day = dates_arr[0][1]

def build_dates_hours_arr_from_range(start_dt_arg, end_dt_arg):
    """
    Build dates_hours_arr with [month, day, start_hour, end_hour] per day,
    clamping to actual irradiance hours from EPW.
    Hour range: 0-23 as per user input and Ladybug AnalysisPeriod support.
    """
    start_parsed = parse_mmdd_hh_label(start_dt_arg)
    end_parsed = parse_mmdd_hh_label(end_dt_arg)

    if not start_parsed or not end_parsed:
        print("Invalid or missing start_dt/end_dt format. Must be 'MM-DD HH' (HH: 0-23)")
        return None

    start_month, start_day, start_label = start_parsed
    end_month, end_day, end_label = end_parsed

    # Load EPW/wea for irradiance check
    epw_file = args.get('epw_file')
    try:
        wea_obj = Wea.from_epw_file(epw_file) if epw_file else None
        ghi_collection = wea_obj.global_horizontal_irradiance if wea_obj else None
    except Exception as e:
        print(f"Failed to load EPW file {epw_file}: {e}")
        ghi_collection = None

    if not ghi_collection:
        print("Warning: ghi_collection not available; falling back to default dates_hours_arr.")
        return None

    current_year = datetime.datetime.now().year

    start_dt = datetime.datetime(current_year, start_month, start_day, start_label)
    end_dt   = datetime.datetime(current_year, end_month,   end_day,   end_label)

    # Handle cross-year
    if end_dt < start_dt:
        end_dt = end_dt.replace(year=current_year + 1)

    if end_dt < start_dt:
        print("Error: End datetime must not be earlier than start datetime.")
        return None

    # Group user hours by date
    by_date = defaultdict(list)
    current = start_dt
    while current <= end_dt:
        m, d = current.month, current.day
        user_hour = current.hour
        by_date[(m, d)].append(user_hour)
        current += datetime.timedelta(hours=1)

    dates_hours = []
    for (month, day) in sorted(by_date.keys()):
        label_list = sorted(set(by_date[(month, day)]))
        user_hours = label_list[:]

        valid_labels = []
        for label_hour in label_list:
            anp = ap.AnalysisPeriod(month, day, label_hour, month, day, label_hour, 1)
            ghi = ghi_collection.filter_by_analysis_period(anp)[0]
            if ghi > 10:
                valid_labels.append(label_hour)

        if not valid_labels:
            continue

        observed_sun_rise = min(valid_labels)
        observed_sun_set  = max(valid_labels)

        user_start = min(user_hours)
        user_end   = max(user_hours)

        final_start = max(observed_sun_rise, user_start)
        final_end   = min(observed_sun_set,  user_end)

        if final_start <= final_end:
            dates_hours.append([month, day, final_start, final_end])

    return dates_hours if dates_hours else None

dates_hours_arr = build_dates_hours_arr_from_range(start_dt_arg, end_dt_arg)

def load_class_data(args):
    """Load temperature data for a single class_id from a base directory."""
    class_id, base_dir, time_points, is_origin, type_value = args
    th_data = {}
    heights_data = {}
    
    sample_file = f"{base_dir}/{first_month}.{first_day}/VCWG_{city}_Class{class_id}/th_profiles{city}_Class{class_id}.txt"
    if not os.path.exists(sample_file):
        print(f"Warning: File {sample_file} not found. Skipping Class {class_id}")
        return class_id, None, None
    
    try:
        with open(sample_file, 'r') as f:
            lines = f.readlines()[3:]
        heights = [float(line.split()[0]) for line in lines]
        num_heights = len(heights)
        heights_data[class_id] = heights
        
        th_data[class_id] = np.zeros((num_heights, len(time_points)))
        
        for t_idx, (month, day, hour) in enumerate(time_points):
            th_file = f"{base_dir}/{month}.{day}/VCWG_{city}_Class{class_id}/th_profiles{city}_Class{class_id}.txt"
            if os.path.exists(th_file):
                with open(th_file, 'r') as f:
                    lines = f.readlines()[3:]
                    for h_idx, line in enumerate(lines):
                        values = line.strip().split()
                        if hour < len(values):
                            th_data[class_id][h_idx, t_idx] = float(values[hour])
        
        return class_id, th_data, heights_data
    except Exception as e:
        print(f"Error loading data for Class {class_id}: {str(e)}")
        return class_id, None, None

# Global containers to collect data from ALL types
all_class_reductions = []   # Each item: one class's height-averaged time series

def build_full_time_points(dates_arr, start_dt, end_dt):
    points = []
    for (m, d) in dates_arr:
        is_first_day = (m == start_dt.month and d == start_dt.day)
        is_last_day = (m == end_dt.month and d == end_dt.day)

        day_start_hour = start_dt.hour if is_first_day else 0
        day_end_hour = end_dt.hour if is_last_day else 23

        for h in range(day_start_hour, day_end_hour + 1):
            points.append((m, d, h))
    return points

full_time_points = build_full_time_points(dates_arr, start_dt, end_dt)

daytime_points = [(m, d, h) for m, d, start_h, end_h in dates_hours_arr for h in range(start_h, end_h + 1)]

def extract_temperature(type_value):
    """Load data for one glazing ratio and append to global containers."""
    global all_class_reductions
    
    first_month = dates_arr[0][0]
    first_day = dates_arr[0][1]

    result_base_dir = os.path.join(intermediate_folder, f"VCWG_{city}_Result_LWS_of_{type_value}").replace('\\', '/')
    origin_result_base_dir = os.path.join(intermediate_folder, f"VCWG_{city}_Result_origin_of_{type_value}").replace('\\', '/')

    if not os.path.exists(os.path.join(result_base_dir, f"{first_month}.{first_day}")):
        print(f"Directory not found for glazing ratio {type_value}: {result_base_dir}, skipping...")
        return

    num_classes = len([f for f in os.listdir(os.path.join(result_base_dir, f"{first_month}.{first_day}")) if f.startswith(f"VCWG_{city}_Class")])
    num_origin_classes = len([f for f in os.listdir(os.path.join(origin_result_base_dir, f"{first_month}.{first_day}")) if f.startswith(f"VCWG_{city}_Class")])

    result_tasks = [(i, result_base_dir, full_time_points, False, type_value) for i in range(1, num_classes + 1)]
    origin_tasks = [(i, origin_result_base_dir, full_time_points, True, type_value) for i in range(1, num_origin_classes + 1)]
    
    with Pool(processes=cpu_count) as pool:
        result_results = pool.map(load_class_data, result_tasks)
        origin_results = pool.map(load_class_data, origin_tasks)
    
    th_data = {}
    heights_data = {}
    origin_th_data = {}
    origin_heights_data = {}
    
    for class_id, th_dict, h_dict in result_results:
        if th_dict is not None:
            th_data[class_id] = th_dict[class_id]
            heights_data[class_id] = h_dict[class_id]
    
    for class_id, th_dict, h_dict in origin_results:
        if th_dict is not None:
            origin_th_data[class_id] = th_dict[class_id]
            origin_heights_data[class_id] = h_dict[class_id]
    
    for class_id in th_data:
        if class_id not in origin_th_data:
            continue
        heights = heights_data[class_id]
        o_heights = origin_heights_data[class_id]
        common_heights = sorted(set(heights) & set(o_heights))
        if not common_heights:
            continue
        
        reductions_per_height = []
        for h in common_heights:
            h_idx_res = np.argmin(np.abs(np.array(heights) - h))
            h_idx_ori = np.argmin(np.abs(np.array(o_heights) - h))
            t_before = origin_th_data[class_id][h_idx_ori, :]
            t_after = th_data[class_id][h_idx_res, :]
            reductions_per_height.append(t_before - t_after)
        
        if reductions_per_height:
            class_avg = np.mean(reductions_per_height, axis=0)
            all_class_reductions.append(class_avg)

    print(f"Finished loading glazing ratio {type_value}, current total classes: {len(all_class_reductions)}")

def main():
    # Step 1: Load data from ALL glazing ratios
    for level2, (type_name, glazing_ratio) in bld_types_and_WWR.items():
        print(f"\n=== Loading data for glazing ratio {glazing_ratio} ({type_name}) ===")
        extract_temperature(type_name)
    
    print(f"\nAll data loaded! Total valid classes: {len(all_class_reductions)}")
    
    if not all_class_reductions:
        print("No valid data!")
        return
    
    # Step 2: Final overall average calculation (only once!)
    overall_series = np.mean(all_class_reductions, axis=0)
        
    daytime_results = {}
    fullday_results = {}
    
    for m, d, sh, eh in dates_hours_arr:
        indices = [i for i, (mm, dd, hh) in enumerate(full_time_points) if mm == m and dd == d and sh <= hh <= eh]
        if indices:
            daytime_results[f"{m}.{d}"] = np.mean(overall_series[indices])
    
    for m, d in dates_arr:
        indices = [i for i, (mm, dd, _) in enumerate(full_time_points) if mm == m and dd == d]
        if indices:
            fullday_results[f"{m}.{d}"] = np.mean(overall_series[indices])
    
    # Write final unified result
    with open(cooling_txt, 'a') as f:
        for date in dates_arr:
            month, day = date
            date_key = f"{month}.{day}"
            if date_key in daytime_results:
                val = daytime_results[date_key]
                f.write(f"Date: {month}.{day}, Average T_reduction (Daytime): {val:.2f}°C for LWS with glazing ratio (all heights)\n")
            else:
                f.write(f"Date: {month}.{day}, Average T_reduction (Daytime): N/A\n")

        f.write("\nFull-Day Average T_reduction:\n")
        for date in dates_arr:
            month, day = date
            date_key = f"{month}.{day}"
            if date_key in fullday_results:
                val = fullday_results[date_key]
                f.write(f"Date: {month}.{day}, Average T_reduction (Full Day): {val:.2f}°C for LWS with glazing ratio (all heights)\n")
            else:
                f.write(f"Date: {month}.{day}, Average T_reduction (Full Day): N/A (no valid full-day data)\n")
        
    print("\nAll done! Final overall average written to cooling.txt")

if __name__ == "__main__":
    main()