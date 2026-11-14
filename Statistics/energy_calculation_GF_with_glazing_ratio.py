import numpy as np
import os
import pandas as pd
import geopandas as gpd
from collections import defaultdict
import matplotlib.pyplot as plt
import mmap
from scipy.spatial import cKDTree
from matplotlib.ticker import FuncFormatter
import sys
import datetime

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

# Add ladybug paths
import ladybug.epw as epw
import ladybug.analysisperiod as ap

# EPW file path
epw_file = args.get('epw_file')
epw_data = epw.EPW(epw_file)

# Read from .epw file
T_db_collection = epw_data.dry_bulb_temperature
P_a_collection = epw_data.atmospheric_station_pressure

city = args.get('city_name')

intermediate_folder = args.get('intermediate_folder')
result_folder = args.get('result_folder')

data_integration_dir = os.path.join(result_folder, 'stats/energy_saving_plots/').replace('\\', '/')

start_dt_arg = args.get('start_dt')
end_dt_arg = args.get('end_dt')

building_shp = args.get('shp')
height_field = args.get('height_field')

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

def get_num_hours_and_dates(start_dt_arg, end_dt_arg):
    """
    Calculate total hours and generate dates list based on user-defined start and end time.
    Supports arbitrary time ranges, including cross-day and partial-day periods.
    
    Args:
        start_dt_arg (str): Start time string in format "MM-DD HH" (HH: 0-23)
        end_dt_arg (str): End time string in format "MM-DD HH" (HH: 0-23)
    
    Returns:
        tuple: (num_hours, dates_arr, hour_ranges)
            - num_hours: Total number of hours in the period
            - dates_arr: List of [month, day]
            - hour_ranges: List of (start_hour, end_hour) for each date (hours 0-23)
    """
    start_parsed = parse_mmdd_hh_label(start_dt_arg)
    end_parsed = parse_mmdd_hh_label(end_dt_arg)

    if not start_parsed or not end_parsed:
        print("Error: Invalid start_dt or end_dt format. Must be 'MM-DD HH' (HH from 0 to 23)")
        return 0, [], []

    s_month, s_day, s_hour = start_parsed
    e_month, e_day, e_hour = end_parsed

    current_year = datetime.datetime.now().year

    start_dt = datetime.datetime(current_year, s_month, s_day, s_hour)
    end_dt   = datetime.datetime(current_year, e_month, e_day, e_hour)

    # Handle cross-year case
    if end_dt < start_dt:
        end_dt = end_dt.replace(year=current_year + 1)

    if end_dt < start_dt:
        print("Error: End time must be after or equal to start time.")
        return 0, [], []

    # Generate hourly timeline
    current = start_dt
    total_hours = 0
    dates_arr = []
    hour_ranges = []

    while current <= end_dt:
        month = current.month
        day = current.day
        hour_label = current.hour

        # New date
        if not dates_arr or dates_arr[-1] != [month, day]:
            dates_arr.append([month, day])
            hour_ranges.append([hour_label, hour_label])
        else:
            # Update end hour of current date
            hour_ranges[-1][1] = hour_label

        total_hours += 1
        current += datetime.timedelta(hours=1)

    print(f"Calculated total hours: {total_hours}")
    print(f"dates_arr: {dates_arr}")
    print(f"hour_ranges: {hour_ranges}")

    return total_hours, dates_arr, hour_ranges

# Preload EPW data to GPU
num_hours, dates_arr, hour_ranges = get_num_hours_and_dates(start_dt_arg, end_dt_arg)

if num_hours == 0:
    print("Error: Failed to calculate valid time range.")
    sys.exit(1)

# Build a flat ordered list of (month, day, hour_label) for every timestep
hour_list = []  # list of (month, day, hour_label)
date_start_indices = []  # indices in hour_list where each date begins
day_index_arr = []
hour_label_list = []
for date_idx, (month, day) in enumerate(dates_arr):
    start_h, end_h = hour_ranges[date_idx]
    date_start_indices.append(len(hour_list))
    for h in range(start_h, end_h + 1):
        hour_list.append((month, day, h))
        day_index_arr.append(date_idx)
        hour_label_list.append(h)

if len(hour_list) != num_hours:
    # Fallback: ensure counts match
    num_hours = len(hour_list)

# Specific heat capacity
Cp  = 1005           # J/(kg·K)

# Building volume
try:
    # Read building footprints
    gdf = gpd.read_file(building_shp)

    # Validate height field
    if height_field not in gdf.columns:
        raise KeyError(f"Height field '{height_field}' not found in shapefile attributes.")

    # If CRS is geographic (degrees) or undefined, reproject to a metric CRS for area calculation
    try:
        is_geographic = gdf.crs.is_geographic
    except Exception:
        is_geographic = True if (gdf.crs is None) else False

    if is_geographic or gdf.crs is None:
        # EPSG:3857 provides meter units (approx). For higher accuracy consider local UTM.
        gdf = gdf.to_crs(epsg=3857)

    # Compute polygon area in m^2
    gdf['area_m2'] = gdf.geometry.area

    # Coerce height values to numeric (meters). Non-numeric -> 0
    gdf['height_m'] = pd.to_numeric(gdf[height_field], errors='coerce').fillna(0.0)

    # Volume per feature (m^3)
    gdf['volume_m3'] = gdf['area_m2'] * gdf['height_m']

    total_building_volume_m3 = float(gdf['volume_m3'].sum())
    print(f"Computed total building volume from shapefile: {total_building_volume_m3:.2f} m^3")
except Exception as e:
    # Fallback: set zero and warn; script continues but numerical model may be invalid
    raise ValueError(f"Warning: failed to compute total building volume from shapefile '{building_shp}': {e}")

ACH_COOLING = 0.75
ACH_HEATING = 0.35
ACH_TRANSITION = 0.50

# Different COP for cooling and heating
COP_COOLING = 3.50
COP_HEATING = 3.00

# Indoor temperature settings for bare load calculation
T_IND_COOL_C = 26.0
T_IND_HEAT_C = 20.0
T_IND_COOL_K = T_IND_COOL_C + 273.15
T_IND_HEAT_K = T_IND_HEAT_C + 273.15

# Thresholds for transition seasons
T_COOLING_ON = 26.0   # °C → turn on cooling
T_HEATING_ON = 14.0   # °C → turn on heating

# Wall heat transfer
h1 = 8.0
U = float(args.get('U_value'))
grid_size = float(args.get('grid_size'))
GRID_AREA = grid_size ** 2
R_vw = 1 / U
z_sub = 0.03
lambda_sub = 0.4
R_vs = z_sub / lambda_sub  # Substrate thermal resistance

# Files
points_path     = os.path.join(intermediate_folder, f"{city}_basic_data/{city}_Points_with_glazing_ratio.txt").replace('\\', '/')
rep_points_path = os.path.join(intermediate_folder, f"{city}_basic_data/{city}_representative_points_with_glazing_ratio.txt").replace('\\', '/')
result_txt      = os.path.join(result_folder, 'stats/energy_saving_plots/energy_GF_with_glazing_ratio.txt').replace('\\', '/')
excel_out       = os.path.join(result_folder, 'stats/energy_saving_plots/energy_savings_per_building_GF_partial.xlsx').replace('\\', '/')
bar_chart_out   = os.path.join(result_folder, 'stats/energy_saving_plots/GF_partial_savings_by_floor.png').replace('\\', '/')

os.makedirs(data_integration_dir, exist_ok=True)

total_shading_Wh = 0.0
total_cooling_Wh = 0.0

# Load data and build mappings
def count_lines_mmap(file_path):
    with open(file_path, 'r') as f:
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        lines = mm.read().count(b'\n')
        mm.close()
    return lines

print("Loading GF data...")
num_points = count_lines_mmap(points_path)
num_rep_points = count_lines_mmap(rep_points_path)
print(f"Wall points: {num_points:,} | Representative points: {num_rep_points:,}")

coords = np.loadtxt(points_path, delimiter=',', usecols=(0,1,2), dtype=np.float64)
building_ids = np.array([
    int(line.strip().split(',')[-1].split('_')[-2])
    for line in open(points_path)
], dtype=np.int64)

points_array = np.empty(num_points, dtype=[('x','f8'),('y','f8'),('z','f8'),('building_id','i8')])
points_array['x'] = coords[:,0]
points_array['y'] = coords[:,1]
points_array['z'] = coords[:,2]
points_array['building_id'] = building_ids

rep_coords = np.loadtxt(rep_points_path, delimiter=',', usecols=(0,1,2), dtype=np.float64)
rep_kdtree = cKDTree(rep_coords)
wall_kdtree = cKDTree(coords)

# V_dot distribution
print("Assigning wall grids to representative points for ventilation distribution...")
_, wall_to_rep_idx = rep_kdtree.query(coords, k=1)
rep_grid_counts = np.bincount(wall_to_rep_idx, minlength=num_rep_points)

# Floor mapping
z_rounded = np.round(points_array['z'], 1)
sort_idx = np.lexsort((z_rounded, points_array['building_id']))
sorted_bid = points_array['building_id'][sort_idx]
sorted_z   = z_rounded[sort_idx]
diff = np.diff(sorted_bid, prepend=-1)
bid_changes = np.where(diff != 0)[0]
bid_starts = bid_changes
bid_ends   = np.concatenate([bid_changes[1:], [len(sorted_bid)]])

points_floors = np.zeros(num_points, dtype=np.int32)
for start, end in zip(bid_starts, bid_ends):
    z_block = sorted_z[start:end]
    unique_z, inv = np.unique(z_block, return_inverse=True)
    floors = np.arange(1, len(unique_z)+1)[inv]
    points_floors[sort_idx[start:end]] = floors

building_to_z_to_floor = {}
unique_bids = np.unique(building_ids)
for bid in unique_bids:
    mask = points_array['building_id'] == bid
    z_vals = z_rounded[mask]
    unique_z = np.unique(z_vals)
    building_to_z_to_floor[bid] = {z: i+1 for i, z in enumerate(np.sort(unique_z))}

bid_to_idx = {bid: i for i, bid in enumerate(unique_bids)}

# Containers
building_total_arr = np.zeros(len(unique_bids), dtype=np.float32)
floor_building_total = defaultdict(lambda: defaultdict(float))

# Main Loop
with open(result_txt, 'w') as f:
    f.write(f"Vertical Greening (GF) Energy Savings in {city}\n")

for t_idx in range(num_hours):
    month, day, hour = hour_list[t_idx]

    period = ap.AnalysisPeriod(month, day, hour, month, day, hour, 1)
    P_a = P_a_collection.filter_by_analysis_period(period).values[0]
    T_db = T_db_collection.filter_by_analysis_period(period).values[0]
    rho = P_a / (287.05 * (T_db + 273.15))

    air_np     = np.memmap(os.path.join(result_folder, f'VCWG_results/VCWG_results_with_glazing_ratio_GF_{month}_{day}_{hour}.npy'),
                          dtype=np.float32, mode='r', shape=(num_rep_points, 7))
    surface_np = np.memmap(os.path.join(result_folder, f'surface_temperatures/{city}_surface_temperatures_GF_with_glazing_ratio_{month}_{day}_{hour}.npy'),
                          dtype=np.float32, mode='r', shape=(num_points, 3))

    T_outdoor = np.mean(air_np[:, 5]) - 273.15  # Convert from K to °C

    if T_outdoor >= T_COOLING_ON:
        mode = 'Cooling'
        ACH = ACH_COOLING
    elif T_outdoor <= T_HEATING_ON:
        mode = 'Heating'
        ACH = ACH_HEATING
    else:
        mode = 'No HVAC'
        ACH = ACH_TRANSITION

    V_dot_city  = total_building_volume_m3 * ACH / 3600.0
    Vdot_per_rep = V_dot_city * (rep_grid_counts.astype(np.float32) / num_points)

    # Wall conduction (W → Wh)
    delta_T_wall = surface_np[:, 0].astype(np.float32)      # T_bare - T_green
    Q_wall_W     = U * GRID_AREA * delta_T_wall
    wall_Wh      = np.sum(Q_wall_W)

    # Air-side load
    delta_T_air = (air_np[:, 5] - air_np[:, 3]).astype(np.float32)
    Q_air_W_rep = rho * Cp * Vdot_per_rep * delta_T_air
    air_Wh      = np.sum(Q_air_W_rep)

    if mode == 'Cooling':
        shading_elec = wall_Wh / COP_COOLING
        cooling_elec = air_Wh  / COP_COOLING
    elif mode == 'Heating':
        shading_elec = -wall_Wh / COP_HEATING
        cooling_elec = -air_Wh  / COP_HEATING
    else: 
        shading_elec = cooling_elec = 0.0

    elec_Wh = shading_elec + cooling_elec

    total_shading_Wh += shading_elec
    total_cooling_Wh += cooling_elec

    # Distribute savings
    # Wall part
    for i, w_Wh in enumerate(Q_wall_W):
        b = points_array['building_id'][i]
        f = points_floors[i]
        idx = bid_to_idx[b]
        if 'Cooling' in mode:
            contrib = w_Wh / COP_COOLING
        elif 'Heating' in mode:
            contrib = -w_Wh / COP_HEATING
        else:
            contrib = 0
        building_total_arr[idx] += contrib
        if f > 0:
            floor_building_total[f][b] += contrib

    # Air part (per rep)
    if abs(air_Wh) > 1e-6:
        _, nearest_wall = wall_kdtree.query(air_np[:, 0:3], k=1)
        nearest_bid = points_array['building_id'][nearest_wall]
        nearest_z = np.round(points_array['z'][nearest_wall], 1)
        for rep_idx, air_contrib_Wh in enumerate(Q_air_W_rep):
            b = nearest_bid[rep_idx]
            z = nearest_z[rep_idx]
            floor = building_to_z_to_floor.get(b, {}).get(z, 0)
            if 'Cooling' in mode:
                contrib = air_contrib_Wh / COP_COOLING
            elif 'Heating' in mode:
                contrib = -air_contrib_Wh / COP_HEATING
            else:
                contrib = 0
            if b in bid_to_idx:
                idx = bid_to_idx[b]
                building_total_arr[idx] += contrib
                if floor > 0:
                    floor_building_total[floor][b] += contrib

    kwh = elec_Wh / 1e3
    print(f"Hour {t_idx+1:04d}/{num_hours} | {month:02d}-{day:02d} {hour:02d}:00 | T={T_outdoor:5.1f}°C | {mode:10s} | Saving: {kwh} kWh")

    with open(result_txt, 'a') as f:
        f.write(f"Hour {t_idx+1:4d} ({month:02d}-{day:02d} {hour:02d}:00) | T={T_outdoor:5.1f}C | Mode={mode} | Elec={kwh} kWh \n")

    air_np._mmap.close()
    surface_np._mmap.close()

total_shading_kWh = total_shading_Wh / 1e3
total_cooling_kWh = total_cooling_Wh / 1e3
total_kWh = total_shading_kWh + total_cooling_kWh

with open(result_txt, 'a') as f:
    f.write("\n\n" + "="*80 + "\n")
    f.write(f"TOTAL ({start_dt_arg} to {end_dt_arg}, Total {num_hours} Hours)\n")
    f.write("="*80 + "\n")
    f.write(f"   Shading / Insulating Effect : {total_shading_kWh} kWh\n")
    f.write(f"   Cooling / Warming Effect    : {total_cooling_kWh} kWh\n")
    f.write(f"   Total Savings               : {total_kWh} kWh\n")

# Plot: Horizontal grouped bar chart with seasonal total energy savings contributions
fig, ax = plt.subplots(figsize=(12, 6))

labels =['Shading / Insulating', 'Cooling / Warming (Vent)', 'Total Energy Savings']
values =[total_shading_kWh, total_cooling_kWh, total_kWh]
colors =['#1ea64e', '#3288bd', '#66c2a5']

bars = ax.bar(labels, values, color=colors, edgecolor='none', width=0.5)

ax.set_ylabel('Energy Savings (kWh)', fontsize=12, fontname='Arial')
ax.set_title(f'Energy Savings Under GF partial retrofitting\nPeriod: {start_dt_arg} to {end_dt_arg}',
             fontsize=14, pad=15, fontname='Arial', fontweight='bold')

# Vertical zero line
ax.axvline(0, 
           color=plt.rcParams['grid.color'],
           linewidth=plt.rcParams['grid.linewidth'],
           linestyle='--', 
           alpha=0.6)

# Legend below
ax.legend(loc='upper center', bbox_to_anchor=(0.5, -0.15), ncol=3, fontsize=11, frameon=False)

# Grid on x-axis
ax.grid(True, axis='x', linestyle='--', alpha=0.6)
ax.set_axisbelow(True)
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

# Value labels
for bar in bars:
    height = bar.get_height()
    va = 'bottom' if height >= 0 else 'top'
    offset = 3 if height >= 0 else -3
    ax.annotate(f'{height:.2f}',
                xy=(bar.get_x() + bar.get_width() / 2, height),
                xytext=(0, offset),  
                textcoords="offset points",
                ha='center', va=va, fontsize=11, fontname='Arial')

plt.tight_layout()
plt.savefig(f"{data_integration_dir}energy_temporal_GF_partial.png", dpi=400, bbox_inches='tight')
plt.close()

print("Exporting building savings...")
building_kWh =[]
for i, bid in enumerate(unique_bids):
    kWh = round(building_total_arr[i] / 1e3, 4)
    building_kWh.append({
        'Building_ID': bid, 
        'Energy_Savings_kWh': kWh, 
    })

df = pd.DataFrame(building_kWh).sort_values('Building_ID')
df.to_excel(excel_out, index=False)
print(f"Exported {len(df):,} buildings to {excel_out}")

print("Generating floor chart...")
all_floors = sorted(floor_building_total.keys())
floor_total = defaultdict(float)
floor_building_count = defaultdict(int)

for f in all_floors:
    for b in floor_building_total[f]:
        floor_total[f] += floor_building_total[f][b]
        floor_building_count[f] += 1

floor_avgs =[]
for f in all_floors:
    total_kWh = floor_total[f] / 1e3
    count = floor_building_count[f]
    avg = total_kWh / count if count > 0 else 0.0
    floor_avgs.append(avg)

bars = plt.bar(all_floors, floor_avgs, width=0.85, color='#66c2a5', edgecolor='none')

plt.xlabel('Floor Level', fontweight='bold', fontsize=10, fontname='Arial')
plt.ylabel('Average Period Energy Savings (kWh)', fontweight='bold', fontsize=10, fontname='Arial')
plt.title(f'Average Energy Savings per Floor ({start_dt_arg} to {end_dt_arg})',
          fontweight='bold', fontsize=14, pad=20, fontname='Arial')

step = 5
plt.xticks(
    ticks=all_floors[::step],
    labels=[str(f) for f in all_floors[::step]],
    fontsize=8,
    rotation=0
)
plt.gca().yaxis.set_major_formatter(FuncFormatter(lambda x, p: f'{x:,.1f}'))
plt.grid(True, axis='y', linestyle='--', alpha=0.7)
plt.gca().set_axisbelow(True)
plt.gca().spines[['top', 'right']].set_visible(False)

plt.tight_layout()
plt.savefig(bar_chart_out, dpi=300, bbox_inches='tight')
print(f"Floor chart saved: {bar_chart_out}")