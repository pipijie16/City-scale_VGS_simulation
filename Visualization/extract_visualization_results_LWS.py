import numpy as np
import os
import mmap
import sys
import re

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

city = args.get('city_name')

intermediate_folder = args.get('intermediate_folder')
result_folder = args.get('result_folder')

# Read visualization_times token string passed from main and split into list of tokens
visualization_times_raw = args.get('visualization_times', '')
visualization_tokens = [t.strip() for t in visualization_times_raw.split(',') if t.strip()]

# Count points
def count_lines_mmap(file_path):
    with open(file_path, 'r') as f:
        mmapped_file = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        line_count = mmapped_file.read().count(b'\n')
        mmapped_file.close()
    return line_count

file_path = os.path.join(intermediate_folder, f"{city}_basic_data/{city}_Points.txt")
num_points = count_lines_mmap(file_path)

# Build hour_list from visualization_tokens
# visualization_tokens example: ["07-23 00", "07-24 12-07-24 18"]
hour_list = []
seen = set()

# days in month for non-leap year
days_in_month = {1:31,2:28,3:31,4:30,5:31,6:30,7:31,8:31,9:30,10:31,11:30,12:31}
# Optional: if era5_year provided and is a leap year, treat February as 29 days
era5_year_str = args.get('era5_year')
if era5_year_str:
    try:
        y = int(era5_year_str)
        if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)):
            days_in_month[2] = 29
    except Exception:
        # ignore malformed year and keep default days_in_month
        pass

def _inc_month_day_hour(m, d, h):
    h = int(h)
    d = int(d)
    m = int(m)
    if h < 24:
        h += 1
        return m, d, h
    # h == 24 -> next hour is 01 of next day
    h = 1
    d += 1
    maxd = days_in_month.get(m, 31)
    if d > maxd:
        d = 1
        m += 1
        if m > 12:
            m = 1
    return m, d, h

for token in visualization_tokens:
    matches = list(re.finditer(r"\d{2}-\d{2}\s+\d{1,2}", token))
    if len(matches) == 0:
        raise ValueError(f"Invalid visualization token: '{token}'. Expected 'MM-DD HH' or ranges like 'MM-DD HH-MM-DD HH'.")

    i = 0
    while i < len(matches):
        cur = matches[i].group(0)
        # decide if this and the next form a range (there is a '-' between them)
        if i + 1 < len(matches):
            between = token[matches[i].end():matches[i+1].start()]
            if '-' in between:
                # range
                start_date, start_hour = matches[i].group(0).split()
                end_date, end_hour = matches[i+1].group(0).split()
                s_m, s_d = start_date.split('-')
                e_m, e_d = end_date.split('-')
                s_h = f"{int(start_hour):02d}"
                e_h = f"{int(end_hour):02d}"
                a = (int(s_m), int(s_d), int(s_h))
                b = (int(e_m), int(e_d), int(e_h))
                # ensure end >= start by lexicographic compare
                if b < a:
                    raise ValueError(f"Invalid range in token '{token}': end before start.")
                # iterate from a to b using simple increment
                cur_m, cur_d, cur_h = a
                while True:
                    tup = (f"{int(cur_m):02d}", f"{int(cur_d):02d}", f"{int(cur_h):02d}")
                    if tup not in seen:
                        hour_list.append(tup)
                        seen.add(tup)
                    if (cur_m, cur_d, cur_h) == b:
                        break
                    cur_m, cur_d, cur_h = _inc_month_day_hour(cur_m, cur_d, cur_h)
                i += 2
                continue
        # single timestamp
        date_str, hour_str = cur.split()
        m_s, d_s = date_str.split('-')
        h_s = f"{int(hour_str):02d}"
        tup = (m_s, d_s, h_s)
        if tup not in seen:
            hour_list.append(tup)
            seen.add(tup)
        i += 1

for t_idx, (month, day, hour) in enumerate(hour_list):
    # Replace with your actual .npy file path
    npy_path = os.path.join(result_folder, f'surface_temperatures/{city}_surface_temperatures_LWS_{int(month)}_{int(day)}_{int(hour)}.npy').replace('\\', '/')

    # Load the array
    array = np.memmap(npy_path, dtype=np.float32, mode='r', shape=(num_points, 3))

    values = array[:, 0]

    txt_file = os.path.join(result_folder, f'{city}_results_LWS_{int(month)}_{int(day)}_{int(hour)}.txt')

    # Save to txt, one value per line
    with open(txt_file, 'w') as f:
        for val in values:
            f.write(f'{val}\n')

    print(f"Extraction complete. The {t_idx + 1}th.txt created.")