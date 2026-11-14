import os
from multiprocessing import Pool, cpu_count
import pandas as pd
import numpy as np
import logging
import matplotlib.pyplot as plt
import sys
import datetime
from collections import defaultdict

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

cpu_count = 2

if not os.path.exists(data_integration_dir):
    os.makedirs(data_integration_dir)

if not os.path.exists(cooling_txt):
    with open(cooling_txt, 'a') as f:
        pass

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
    class_id, base_dir, time_points = args
    th_data = {}
    heights_data = {}
    
    sample_file = f"{base_dir}/{first_month}.{first_day}/VCWG_{city}_Class{class_id}/th_profiles{city}_Class{class_id}.txt"
    if not os.path.exists(sample_file):
        logging.warning(f"File {sample_file} not found. Skipping Class {class_id}")
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
                        th_data[class_id][h_idx, t_idx] = float(line.strip().split()[hour])
        
        return class_id, th_data, heights_data
    except Exception as e:
        logging.error(f"Error loading data for Class {class_id}: {str(e)}")
        print(f"Error loading data for Class {class_id}: {str(e)}")
        return class_id, None, None

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

time_points = build_full_time_points(dates_arr, start_dt, end_dt)

def extract_temperature():
    """Extract daytime and full-day temperature at 1.5m height for all Class_IDs at specified times and save to Excel."""
    daytime_points = [(m, d, h) for m, d, start_h, end_h in dates_hours_arr for h in range(start_h, end_h + 1)]

    first_month = dates_arr[0][0]
    first_day = dates_arr[0][1]

    result_base_dir = os.path.join(intermediate_folder, f"VCWG_{city}_Result_LWS/")
    os.makedirs(result_base_dir, exist_ok=True)
    origin_result_base_dir = os.path.join(intermediate_folder, f"VCWG_{city}_Result_origin/")
    os.makedirs(origin_result_base_dir, exist_ok=True)
    height_tolerance = 0.01  # Tolerance for matching 1.5m height
    
    # Get all Class_IDs
    num_classes = len([f for f in os.listdir(result_base_dir + f"{first_month}.{first_day}/") if f.startswith(f"VCWG_{city}_Class")])
    num_origin_classes = len([f for f in os.listdir(origin_result_base_dir + f"{first_month}.{first_day}/") if f.startswith(f"VCWG_{city}_Class")])

    daily_avg_t_reduction_daytime = {f"{m}.{d}": [] for m, d in dates_arr}  # Daytime only
    daily_avg_t_reduction_full = {f"{m}.{d}": [] for m, d in dates_arr}     # Full day
    
    # Create tasks for parallel processing
    result_tasks = [(i, result_base_dir, time_points) for i in range(1, num_classes + 1)]
    origin_tasks = [(i, origin_result_base_dir, time_points) for i in range(1, num_origin_classes + 1)]
    
    try:
        with Pool(processes=cpu_count) as pool:
            result_results = pool.map(load_class_data, result_tasks)
            origin_results = pool.map(load_class_data, origin_tasks)
        
        # Organize results
        th_data = {}
        heights_data = {}
        origin_th_data = {}
        origin_heights_data = {}
        
        for class_id, th_data_dict, heights_data_dict in result_results:
            if th_data_dict is not None:
                th_data[class_id] = th_data_dict[class_id]
                heights_data[class_id] = heights_data_dict[class_id]
        
        for class_id, origin_th_data_dict, origin_heights_data_dict in origin_results:
            if origin_th_data_dict is not None:
                origin_th_data[class_id] = origin_th_data_dict[class_id]
                origin_heights_data[class_id] = origin_heights_data_dict[class_id]
        
        # Process each Class_ID for temperature at all heights
        for class_id in range(1, max(num_classes, num_origin_classes) + 1):
            try:
                # Initialize T_reduction for all heights
                t_reductions_all_heights = []
                
                # Get heights (use intersection of origin and result heights to ensure consistency)
                if class_id in heights_data and class_id in origin_heights_data:
                    heights = heights_data[class_id]
                    origin_heights = origin_heights_data[class_id]
                    common_heights = sorted(set(heights) & set(origin_heights))  # Intersection of heights
                    if not common_heights:
                        logging.warning(f"No common heights found for Class {class_id}")
                        print(f"Warning: No common heights found for Class {class_id}")
                        continue
                    
                    # Calculate T_reduction for each height
                    for height in common_heights:
                        t_before = None
                        t_after = None
                        
                        # Extract T_before from origin data
                        for h_idx, h in enumerate(origin_heights):
                            if abs(h - height) <= height_tolerance:
                                t_before = origin_th_data[class_id][h_idx, :]
                                break
                        
                        # Extract T_after from result data
                        for h_idx, h in enumerate(heights):
                            if abs(h - height) <= height_tolerance:
                                t_after = th_data[class_id][h_idx, :]
                                break
                        
                        if t_before is not None and t_after is not None:
                            t_reductions = t_before - t_after
                            t_reductions_all_heights.append(t_reductions)
                else:
                    logging.warning(f"Skipping Class {class_id}: Missing data in heights_data or origin_heights_data")
                    print(f"Warning: Skipping Class {class_id}: Missing data")
                    continue
                
                # Calculate daily average T_reduction for all heights (daytime and full day)
                if t_reductions_all_heights:
                    # Average T_reduction across all heights for each time point
                    t_reductions_avg_height = np.mean(t_reductions_all_heights, axis=0)
                    
                    # Calculate daily average for each date
                    for m, d in dates_arr:
                        # Daytime average
                        day_indices = [i for i, (month, day, h) in enumerate(time_points) if month == m and day == d and (m, d, h) in daytime_points]
                        if day_indices:
                            daily_avg_daytime = np.mean(t_reductions_avg_height[day_indices])
                            daily_avg_t_reduction_daytime[f"{m}.{d}"].append(daily_avg_daytime)
                        
                        # Full-day average
                        full_day_indices = [i for i, (month, day, h) in enumerate(time_points) if month == m and day == d]
                        if full_day_indices:
                            daily_avg_full = np.mean(t_reductions_avg_height[full_day_indices])
                            daily_avg_t_reduction_full[f"{m}.{d}"].append(daily_avg_full)
                
            except Exception as e:
                logging.error(f"Error processing Class {class_id}: {str(e)}")
                print(f"Error processing Class {class_id}: {str(e)}")
                continue
        
        # Save daily average T_reduction to cooling.txt (daytime and full day)
        try:
            with open(cooling_txt, 'a') as f:
                # Save daytime averages
                f.write("Daytime Average T_reduction:\n")
                for date_key in daily_avg_t_reduction_daytime:
                    if daily_avg_t_reduction_daytime[date_key]:
                        avg_t_reduction = np.mean(daily_avg_t_reduction_daytime[date_key])
                        f.write(f"Date: {date_key}, Average T_reduction (Daytime): {avg_t_reduction:.2f}°C for LWS (all heights)\n")
                        print(f"Saved daytime average T_reduction for {date_key} to {cooling_txt}")
                    else:
                        logging.warning(f"No daytime T_reduction data for {date_key}")
                        print(f"Warning: No daytime T_reduction data for {date_key}")
                
                # Save full-day averages
                f.write("\nFull-Day Average T_reduction:\n")
                for date_key in daily_avg_t_reduction_full:
                    if daily_avg_t_reduction_full[date_key]:
                        avg_t_reduction = np.mean(daily_avg_t_reduction_full[date_key])
                        f.write(f"Date: {date_key}, Average T_reduction (Full Day): {avg_t_reduction:.2f}°C for LWS (all heights)\n")
                        print(f"Saved full-day average T_reduction for {date_key} to {cooling_txt}")
                    else:
                        logging.warning(f"No full-day T_reduction data for {date_key}")
                        print(f"Warning: No full-day T_reduction data for {date_key}")
        except Exception as e:
            logging.error(f"Error writing to {cooling_txt}: {str(e)}")
            print(f"Error writing to {cooling_txt}: {str(e)}")
            raise
    except Exception as e:
        logging.error(f"Error in extract_temperature: {str(e)}")
        print(f"Error in extract_temperature: {str(e)}")
        raise

def main():
    try:
        extract_temperature()
        print("Temperature extraction process complete")
    except Exception as e:
        logging.error(f"Error in main: {str(e)}")
        raise

if __name__ == "__main__":
    main()