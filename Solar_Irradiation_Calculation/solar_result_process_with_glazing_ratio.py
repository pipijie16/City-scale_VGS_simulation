import os
import numpy as np
import mmap
import time
from tqdm import tqdm
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

# This script must be run via the GUI's subprocess call, which passes arguments.
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

from ladybug.wea import Wea
import ladybug.analysisperiod as ap

city = args.get('city_name')

def count_lines_mmap(file_path):
    with open(file_path, 'r') as f:
        mmapped_file = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        
        line_count = mmapped_file.read().count(b'\n')
        mmapped_file.close()
    
    return line_count

intermediate_folder = args.get('intermediate_folder')
result_folder = args.get('result_folder')

file_path = os.path.join(intermediate_folder, f"{city}_basic_data/{city}_Points_with_glazing_ratio.txt")
num_points = count_lines_mmap(file_path)

# Build dates_hours_arr from start_dt/end_dt args when provided.
start_dt_arg = args.get('start_dt')
end_dt_arg = args.get('end_dt')

def parse_mmdd_hh_label(s):
    try:
        mmdd, hh = s.rsplit(' ', 1)
        hh_int = int(hh)
        if not (0 <= hh_int <= 23):
            return None
        dt = datetime.datetime.strptime(mmdd, "%m-%d")
        return (dt.month, dt.day, hh_int)
    except Exception:
        return None

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

        observed_sun_rise = min(valid_labels) + 1
        observed_sun_set  = max(valid_labels) + 1

        user_start = min(user_hours)
        user_end   = max(user_hours)

        final_start = max(observed_sun_rise, user_start)
        final_end   = min(observed_sun_set,  user_end)

        if final_start <= final_end:
            dates_hours.append([month, day, final_start, final_end])

    return dates_hours if dates_hours else None

dates_hours_arr = build_dates_hours_arr_from_range(start_dt_arg, end_dt_arg)
grids_directory = os.path.join(intermediate_folder, f"solar_radiance_with_glazing_ratio/")
os.makedirs(grids_directory, exist_ok=True)
result_directory = os.path.join(intermediate_folder, f'Solar_Irradiance_Results_with_glazing_ratio/')
os.makedirs(result_directory, exist_ok=True)

error_txt = os.path.join(intermediate_folder, "solar_error.txt")

folders = [d for d in os.listdir(grids_directory) if os.path.isdir(os.path.join(grids_directory, d))]
items = os.listdir(grids_directory)
folder_count = sum(os.path.isdir(os.path.join(grids_directory, item)) for item in items)

output_dir = os.path.join(result_folder, "solar_irradiation").replace('\\', '/')
os.makedirs(output_dir, exist_ok=True)

num_hours = sum([date[3] - date[2] + 1 for date in dates_hours_arr])

hour_index = 0

total_batches = sum(date[3] - date[2] + 1 for date in dates_hours_arr)

start_time = time.time()

with tqdm(total=num_hours, desc="Processing total hours") as pbar:
    for j, date in enumerate(dates_hours_arr):
        month = date[0]
        day = date[1]
        sun_rise = date[2]
        sun_set = date[3]

        for hour in range(sun_rise, sun_set + 1):
            # Initialize memmap for current hour
            output_file = os.path.join(output_dir, f'solar_hourly_with_glazing_ratio_{month}_{day}_{hour}.npy').replace('\\', '/')
            solar_hourly_memmap = np.memmap(
                output_file,
                dtype=np.float32,
                mode='w+',
                shape=(num_points, 4)
            )
            
            point_count = 0
            with tqdm(total=folder_count, desc=f"Processing solar results for hour {hour_index + 1}", leave=False) as pbar_inner:
                for folder in folders:
                    grids_path = os.path.join(grids_directory, f"{folder}/model/grid/")
                    grids = [f for f in os.listdir(grids_path) if f.endswith(".pts")]
                    
                    for grid in grids:
                        grid_path = os.path.join(grids_path, grid)
                        with open(grid_path, 'r') as grid_file:
                            grid_lines = grid_file.readlines()

                        result_path = os.path.join(result_directory, f"{month}.{day} {hour}/{folder}/pit/{grid.replace('.pts', '.res')}")
                        with open(result_path, 'r') as result_file:
                            result_lines = result_file.readlines()

                        if len(grid_lines) != len(result_lines):
                            error = f"The number of lines in the grid file and the result file are not the same in {month}.{day} {hour} {grid}\n"
                            with open(error_txt, "a") as file:
                                file.write(error)
                            continue

                        for grid_line, result_line in zip(grid_lines, result_lines):
                            grid_parts = grid_line.strip().split()
                            if len(grid_parts) >= 3:
                                x = float(grid_parts[0])
                                y = float(grid_parts[1])
                                z = float(grid_parts[2])
                            else:
                                continue

                            solar_irradiation = float(result_line.strip().split()[0])

                            solar_hourly_memmap[point_count, 0] = x
                            solar_hourly_memmap[point_count, 1] = y
                            solar_hourly_memmap[point_count, 2] = z
                            solar_hourly_memmap[point_count, 3] = solar_irradiation
                            
                            point_count += 1

                    pbar_inner.update(1)

            # Flush memmap to ensure data is written
            solar_hourly_memmap.flush()
            del solar_hourly_memmap

            if point_count != num_points:
                error = f"Processed {point_count} points instead of expected {num_points} for hour {hour_index + 1}\n"
                with open(error_txt, "a") as file:
                    file.write(error)

            hour_index += 1
            pbar.update(1)

end_time = time.time()
elapsed_time = end_time - start_time

# Convert elapsed time to days, hours, minutes, and seconds
days = elapsed_time // (24 * 3600)
elapsed_time = elapsed_time % (24 * 3600)
hours = elapsed_time // 3600
elapsed_time %= 3600
minutes = elapsed_time // 60
seconds = elapsed_time % 60

print(f"Done processing solar results in {int(days)} days, {int(hours)} hours, {int(minutes)} minutes, and {int(seconds)} seconds")