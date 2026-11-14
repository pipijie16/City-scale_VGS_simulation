import cupy as cp
import math
import numpy as np
import os
import mmap
import time
from cupy.cuda import stream
from cupy.cuda.memory import MemoryPool
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

# Initialize CuPy memory pool
cp.cuda.set_allocator(MemoryPool().malloc)

# Add ladybug paths
import ladybug.epw as epw
import ladybug.analysisperiod as ap
from ladybug.wea import Wea

city = args.get('city_name')

data_processing_dir = args.get('data_processing_dir')
intermediate_folder = args.get('intermediate_folder')
result_folder = args.get('result_folder')

ground_temperature_array = np.load(os.path.join(intermediate_folder, f"{city}_basic_data/ERA5_ground_temperature.npy"))

start_time = time.time()

# EPW file path
epw_file = args.get('epw_file')
epw_data = epw.EPW(epw_file)

start_dt_arg = args.get('start_dt')
end_dt_arg = args.get('end_dt')

# Read from .epw file
T_db_collection = epw_data.dry_bulb_temperature
T_dew_collection = epw_data.dew_point_temperature
P_a_collection = epw_data.atmospheric_station_pressure
RH_collection = epw_data.relative_humidity
cloud_cover = epw_data.total_sky_cover

wea_obj = Wea.from_epw_file(epw_file)
ghi_collection = wea_obj.global_horizontal_irradiance

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

# Build hour_list and helper mappings (month, day, hour_label)
hour_list = []
date_start_indices = []
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
    num_hours = len(hour_list)

T_db_array = cp.zeros(num_hours, dtype=cp.float32)
T_dew_array = cp.zeros(num_hours, dtype=cp.float32)
P_a_array = cp.zeros(num_hours, dtype=cp.float32)
RH_array = cp.zeros(num_hours, dtype=cp.float32)
T_gr_K_array = cp.zeros(num_hours, dtype=cp.float32)
cloud_cover_array = cp.zeros(num_hours, dtype=cp.float32)
epsilon_sky_array = cp.zeros(num_hours, dtype=cp.float32)

def calculate_epsilon_sky(T_dew_C, hour_label, cloud_cover_fraction, 
                          station_pressure_Pa):
    """
    Calculate sky longwave emissivity using Berdahl and Martin model.
    
    - Clear sky part: dew point + diurnal + elevation correction
    - Cloud correction: ε_sky = ε_clear + (1 - ε_clear) * C
    
    Args:
        T_dew_C (cp.array or scalar): Dew point temperature in °C
        hour_label (cp.array or scalar): Hour label 1~24 (as used in your hour_list)
        cloud_cover_fraction (cp.array or scalar): Total cloud cover fraction (0.0 = clear, 1.0 = fully overcast)
        station_pressure_Pa (float): Station atmospheric pressure in Pa (default sea level)
    
    Returns:
        epsilon_sky (cp.float32): Sky emissivity (0.7 ~ 1.0)
    """
    T_dp = cp.array(T_dew_C, dtype=cp.float32)
    t = cp.array(hour_label, dtype=cp.float32)          # 1~24
    P_mbar = station_pressure_Pa / 100.0                # convert to millibar
    
    T_dp_100 = T_dp / 100.0
    epsilon0 = cp.float32(0.711) + cp.float32(0.56) * T_dp_100 + cp.float32(0.73) * (T_dp_100 ** 2)
    
    delta_epsilon_h = cp.float32(0.013) * cp.cos(2 * cp.pi * t / 24.0)
    
    delta_epsilon_e = cp.float32(0.00012) * (P_mbar - 1000.0)
    
    # Clear sky emissivity
    epsilon_clear = epsilon0 + delta_epsilon_h + delta_epsilon_e
    epsilon_clear = cp.clip(epsilon_clear, cp.float32(0.70), cp.float32(1.0))
    
    C = cp.array(cloud_cover_fraction, dtype=cp.float32)
    C = cp.clip(C, 0.0, 1.0)
    
    epsilon_sky = epsilon_clear + (cp.float32(1.0) - epsilon_clear) * C
    
    epsilon_sky = cp.clip(epsilon_sky, cp.float32(0.70), cp.float32(1.0))
    
    return epsilon_sky

error_txt = os.path.join(intermediate_folder, "numerical_model_GW_partial_error.txt")
if not os.path.exists(error_txt):
    with open(error_txt, 'w') as f:
        pass

# Fill arrays with EPW data and ground temperature
global_idx = 0

for date_idx, (month, day) in enumerate(dates_arr):
    start_h, end_h = hour_ranges[date_idx]
    
    for h_label in range(start_h, end_h + 1):
        period = ap.AnalysisPeriod(month, day, h_label, month, day, h_label, 1)
        
        T_db_array[global_idx] = T_db_collection.filter_by_analysis_period(period).values[0]
        T_dew_array[global_idx] = T_dew_collection.filter_by_analysis_period(period).values[0]
        P_a_array[global_idx]  = P_a_collection.filter_by_analysis_period(period).values[0]
        RH_array[global_idx]   = RH_collection.filter_by_analysis_period(period).values[0]
        cloud_cover_array[global_idx] = cloud_cover.filter_by_analysis_period(period).values[0] / 10.0
        epsilon_sky_array[global_idx] = calculate_epsilon_sky(T_dew_array[global_idx], h_label, cloud_cover_array[global_idx], P_a_array[global_idx])
        
        # Ground temperature is taken sequentially from the ERA5 array
        T_gr_K_array[global_idx] = ground_temperature_array[global_idx] + cp.float32(273.15)

        global_idx += 1

# Compute sky temperature and other environmental data
T_sky_K = ((T_db_array + cp.float32(273.15)) * (cp.float32(0.8) + T_dew_array / cp.float32(250)) ** cp.float32(0.25))
k_Pa = cp.round(P_a_array / cp.float32(1000), decimals=3)
rho_air = P_a_array / (cp.float32(287.05) * (T_db_array + cp.float32(273.15))) + cp.float32(1e-6)

# Compute diurnal hours using hour_list
diurnal_t_idx_list = []
solar_file_counter = 0
for t_idx in range(num_hours):
    month, day, hour_label = hour_list[t_idx]
    solar_path = os.path.join(result_folder, f'solar_irradiation/solar_hourly_with_glazing_ratio_{month}_{day}_{hour_label}.npy').replace('\\', '/')
    if os.path.exists(solar_path):
        diurnal_t_idx_list.append(t_idx)
        solar_file_counter += 1

# Broadcast environmental data for one time step
def get_broadcasted_data(t_idx):
    return {
        'T_sky_K': cp.array(T_sky_K[t_idx], dtype=cp.float32),
        'epsilon_sky': epsilon_sky_array[t_idx],
        'T_gr_K': cp.array(T_gr_K_array[t_idx], dtype=cp.float32),
        'k_Pa': cp.array(k_Pa[t_idx], dtype=cp.float32),
        'rho_air': cp.array(rho_air[t_idx], dtype=cp.float32),
        'RH': cp.array(RH_array[t_idx], dtype=cp.float32)
    }

# Count points
def count_lines_mmap(file_path):
    with open(file_path, 'r') as f:
        mmapped_file = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        line_count = mmapped_file.read().count(b'\n')
        mmapped_file.close()
    return line_count

file_path = os.path.join(intermediate_folder, f"{city}_basic_data/{city}_Points_with_glazing_ratio.txt")
num_points = count_lines_mmap(file_path)

# Load representative points
representative_points_file = os.path.join(intermediate_folder, f"{city}_basic_data/{city}_representative_points_with_glazing_ratio.txt")
representative_points = []

def load_points():
    with open(representative_points_file, 'r') as f:
        lines = f.readlines()
        for line in lines:
            x, y, z, nx, ny, nz, class_id, fc_name = line.strip().split(',')
            representative_points.append((float(x), float(y), float(z), float(nx), float(ny), float(nz), 
                                         int(class_id), fc_name))
    return representative_points

points_list = load_points()
num_rep_points = len(points_list)

# Load data files
output_dir = result_folder
os.makedirs(output_dir, exist_ok=True)
view_factors_data = cp.array(np.memmap(os.path.join(output_dir, 'view_factors_data_with_glazing_ratio.npy'), dtype=np.float32, mode='r', shape=(num_points, 5)))

# Organize points by facade
points_by_facade = {}
for idx, point in enumerate(points_list):
    fc_name = point[7]
    if fc_name not in points_by_facade:
        points_by_facade[fc_name] = []
    points_by_facade[fc_name].append(idx)

z_values_by_facade = {}
for fc_name, indices in points_by_facade.items():
    z_values = sorted(points_list[idx][2] for idx in indices)
    z_values_by_facade[fc_name] = cp.array(z_values, dtype=cp.float32)

# Build point mapping
def build_point_mapping(file, points_list):
    rep_mapping = {}
    z_tolerance = 0.1
    for idx, point in enumerate(points_list):
        x, y, z, _, _, _, class_id, fc_name = point
        z_rounded = round(z, 4)
        rep_mapping[(fc_name, z_rounded)] = idx

    mapping = {}
    with open(file, 'r') as f:
        for w_idx, line in enumerate(f):
            parts = line.strip().split(',')
            try:
                x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
                fc_name = parts[6]
                z_rounded = round(z, 4)
                key = (fc_name, z_rounded)
                rep_idx = rep_mapping.get(key)
                if rep_idx is None and fc_name in z_values_by_facade:
                    z_array = z_values_by_facade[fc_name]
                    idx = cp.searchsorted(z_array, z, side='left')
                    if idx > 0 and abs(float(z_array[idx-1]) - z) <= z_tolerance:
                        z_closest = float(z_array[idx-1])
                        z_rounded_closest = round(z_closest, 4)
                        key_closest = (fc_name, z_rounded_closest)
                        rep_idx = rep_mapping.get(key_closest)
                    elif idx < len(z_array) and abs(float(z_array[idx]) - z) <= z_tolerance:
                        z_closest = float(z_array[idx])
                        z_rounded_closest = round(z_closest, 4)
                        key_closest = (fc_name, z_rounded_closest)
                        rep_idx = rep_mapping.get(key_closest)
                if rep_idx is not None:
                    mapping[w_idx] = (rep_idx, x, y, z)
            except ValueError:
                print(f"Invalid line at w_idx {w_idx}: {line.strip()}")
                continue
    return mapping

point_mapping = build_point_mapping(file_path, points_list)

# Constants
sigma = cp.float32(5.67e-8)
g = cp.float32(9.8)
kappa = cp.float32(0.5)
LAI = cp.float32(args.get('LAI'))
tau = cp.float32(round(math.exp(-kappa * LAI), 2))
epsilon_wall = cp.float32(0.9)
epsilon_gr = cp.float32(0.92)
epsilon_leaf = cp.float32(0.96)
alpha_wall = cp.float32(args.get('wall_absorptivity'))
alpha_leaf = cp.float32(0.84)
h1 = cp.float32(8.0)
c_pa = cp.float32(1005)
U_wall = cp.float32(args.get('U_value'))
R_vw = cp.float32(1.0) / U_wall
rho_of_wall = cp.float32(args.get('rho_of_wall'))
c_pw = cp.float32(args.get('c_pw'))
Zo_w = cp.float32(0.01)
Kv = cp.float32(0.4)
r_ch = cp.float32(0.63)
dt = cp.float32(3600)
R = cp.float32(287)
z = cp.float32(args.get('wall_thickness'))

def calculate_effective_depth(lambda_wall, total_wall_thickness):
    """
    Calculate effective heat storage thickness (z_eff) based on daily periodic thermal wave theory.
    
    This follows the periodic penetration depth concept from ISO 13786.
    The temperature amplitude decays exponentially with depth. 
    Effective depth is typically 1.5δ to 2.5δ, where δ is the penetration depth.
    """
    if lambda_wall is None:
        lambda_wall = cp.float32(1.40)      # Normal-weight concrete, typical value 1.2-1.7 W/m·K
    
    if total_wall_thickness is None:
        total_wall_thickness = cp.float32(0.25)   # Assume 250 mm common wall thickness
    
    # Thermal diffusivity α = λ / (ρ · c)   unit: m²/s
    alpha = lambda_wall / (rho_of_wall * c_pw)
    
    # Angular frequency for daily cycle (P = 86400 s)
    P = cp.float32(86400.0)
    omega = cp.float32(2.0) * cp.pi / P
    
    # Periodic penetration depth δ (m)
    # δ = sqrt(2α / ω)  ==  sqrt(α * P / π)
    delta = cp.sqrt(2.0 * alpha / omega)
    
    # Effective storage thickness: usually ~2.0 * δ (balanced engineering value)
    # Limited by half of the actual wall thickness for thick walls
    z_eff_calc = cp.float32(2.0) * delta
    z_eff = cp.minimum(z_eff_calc, total_wall_thickness / cp.float32(2.0))

    return z_eff

z_eff = calculate_effective_depth(
    lambda_wall=z/R_vw,      # Change according to your actual wall material
    total_wall_thickness=z,  # Total wall thickness including plaster etc.
)

# Precompute aerodynamic parameters
Za = cp.float32(2)
Zd = cp.float32(0.21)
Zo_f = cp.maximum(cp.float32(0.131) * cp.power(Za, cp.float32(0.997)), cp.float32(0.02))
C_hnw = cp.power(Kv / cp.log(Za / Zo_w), cp.float32(2)) / r_ch
C_hnf = cp.power(Kv / cp.log((Za - Zd) / (Zo_f + cp.float32(1e-6))), cp.float32(2))

rep_idx_arr = cp.array([point_mapping[w_idx][0] for w_idx in range(num_points)], dtype=cp.int32)

# View factors
F_sky = view_factors_data[:, 4]
F_bld = view_factors_data[:, 3]
F_gr = cp.float32(1) - F_sky - F_bld

# Preallocate temporary arrays
def preallocate_temp_arrays(batch_size):
    return {
        'T_af_K': cp.zeros(batch_size, dtype=cp.float32),
        'v_af': cp.zeros(batch_size, dtype=cp.float32),
        'denominator': cp.zeros(batch_size, dtype=cp.float32),
        'R_ib': cp.zeros(batch_size, dtype=cp.float32),
        'gamma_h': cp.zeros(batch_size, dtype=cp.float32),
        'b_cof': cp.zeros(batch_size, dtype=cp.float32),
        'LR_vw': cp.zeros(batch_size, dtype=cp.float32),
        'LR_leaf': cp.zeros(batch_size, dtype=cp.float32),
        'LR_bw': cp.zeros(batch_size, dtype=cp.float32),
        'XR': cp.zeros(batch_size, dtype=cp.float32),
        'SR_vw': cp.zeros(batch_size, dtype=cp.float32),
        'SR_leaf': cp.zeros(batch_size, dtype=cp.float32),
        'SR_bw': cp.zeros(batch_size, dtype=cp.float32),
        'Q_wall': cp.zeros(batch_size, dtype=cp.float32),
        'rho_leaf': cp.zeros(batch_size, dtype=cp.float32),
        'rho_af': cp.zeros(batch_size, dtype=cp.float32),
        'rho_wall': cp.zeros(batch_size, dtype=cp.float32),
        'rho_avw': cp.zeros(batch_size, dtype=cp.float32),
        'C_vw': cp.zeros(batch_size, dtype=cp.float32),
        'C_leaf': cp.zeros(batch_size, dtype=cp.float32),
        'C_bw': cp.zeros(batch_size, dtype=cp.float32),
        'R_n': cp.zeros(batch_size, dtype=cp.float32),
        'r_air': cp.zeros(batch_size, dtype=cp.float32),
        'r_s': cp.zeros(batch_size, dtype=cp.float32),
        'e_s': cp.zeros(batch_size, dtype=cp.float32),
        'e_air': cp.zeros(batch_size, dtype=cp.float32),
        'delta': cp.zeros(batch_size, dtype=cp.float32),
        'gamma': cp.zeros(batch_size, dtype=cp.float32),
        'LH_leaf': cp.zeros(batch_size, dtype=cp.float32),
        'S_wall': cp.zeros(batch_size, dtype=cp.float32),
        'S_leaf': cp.zeros(batch_size, dtype=cp.float32),
        'S_bw': cp.zeros(batch_size, dtype=cp.float32),
        'eq1': cp.zeros(batch_size, dtype=cp.float32),
        'eq2': cp.zeros(batch_size, dtype=cp.float32),
        'LR_bw': cp.zeros(batch_size, dtype=cp.float32),
        'SR_bw': cp.zeros(batch_size, dtype=cp.float32),
        'C_bw': cp.zeros(batch_size, dtype=cp.float32)
    }

# Equations for green wall
def equations_green_wall(T_svw_K, T_leaf_K, t_idx, T_air_gw_K, v, C_hnf, Za, Zd, Zo_f, 
                         T_sky_K, epsilon_sky, T_gr_K, k_Pa, F_sky, F_gr, F_bld, I_s, rho_air, 
                         prev_T_svw_K, prev_T_leaf_K, RH, temp_arrays, is_warmup=False):
    T_sky_K = cp.full_like(T_svw_K, T_sky_K)
    epsilon_sky = cp.full_like(T_svw_K, epsilon_sky)
    T_gr_K = cp.full_like(T_svw_K, T_gr_K)
    rho_air = cp.full_like(T_svw_K, rho_air)
    k_Pa = cp.full_like(T_svw_K, k_Pa)
    RH = cp.full_like(T_svw_K, RH)

    T_indoor_C = cp.where(T_air_gw_K >= 26.0, cp.float32(26.0), cp.float32(22.0))
    T_indoor_C = cp.where(T_air_gw_K <= 14.0, cp.float32(20.0), cp.float32(22.0))
    
    T_inw_C = (h1 * T_indoor_C + U_wall * (T_svw_K - cp.float32(273.15))) / (h1 + U_wall)
    T_inw_K = T_inw_C + cp.float32(273.15)
    
    temp_arrays['T_af_K'][:] = tau * T_air_gw_K + (1 - tau) * (cp.float32(0.3) * T_air_gw_K + cp.float32(0.6) * T_leaf_K + cp.float32(0.1) * T_svw_K)
    temp_arrays['v_af'][:] = cp.float32(0.83) * (1 - tau) * v * cp.sqrt(C_hnf) + tau * v
    temp_arrays['denominator'][:] = (temp_arrays['T_af_K'] + T_svw_K) * cp.power(temp_arrays['v_af'], 2) + cp.float32(1e-6)
    temp_arrays['R_ib'][:] = 2 * g * Za * (T_svw_K - temp_arrays['T_af_K']) / temp_arrays['denominator']

    mask_stable = temp_arrays['R_ib'] >= 0 
    gamma_stable = 1.0 / (1.0 + 5.0 * temp_arrays['R_ib'])

    arg_unstable = 1.0 - 16.0 * temp_arrays['R_ib']
    gamma_unstable = 1.0 / cp.sqrt(arg_unstable)

    temp_arrays['gamma_h'][:] = cp.where(mask_stable, gamma_stable, gamma_unstable)

    temp_arrays['b_cof'][:] = temp_arrays['gamma_h'] * (tau * C_hnw + (1 - tau) * C_hnf) + cp.float32(1e-6)
    temp_arrays['LR_vw'][:] = (tau * epsilon_wall * epsilon_sky * sigma * F_sky * (cp.power(T_sky_K, 4) - cp.power(T_svw_K, 4)) +
                               tau * epsilon_wall * epsilon_gr * sigma * F_gr * (cp.power(T_gr_K, 4) - cp.power(T_svw_K, 4)) +
                               tau * epsilon_wall * epsilon_leaf * sigma * F_bld * (cp.power(T_leaf_K, 4) - cp.power(T_svw_K, 4)))
    temp_arrays['LR_leaf'][:] = (epsilon_leaf * epsilon_sky * sigma * F_sky * (cp.power(T_sky_K, 4) - cp.power(T_leaf_K, 4)) +
                                 epsilon_leaf * epsilon_gr * sigma * F_gr * (cp.power(T_gr_K, 4) - cp.power(T_leaf_K, 4)) +
                                 tau * epsilon_leaf * epsilon_wall * sigma * F_bld * (cp.power(T_svw_K, 4) - cp.power(T_leaf_K, 4)))
    temp_arrays['XR'][:] = (1 - tau) * (epsilon_leaf * epsilon_wall) / (epsilon_leaf + epsilon_wall - epsilon_leaf * epsilon_wall) * sigma * (cp.power(T_svw_K, 4) - cp.power(T_leaf_K, 4))
    temp_arrays['SR_vw'][:] = I_s * alpha_wall * tau
    temp_arrays['SR_leaf'][:] = I_s * alpha_leaf * (1 - tau)
    temp_arrays['Q_wall'][:] = (T_svw_K - T_inw_K) / (R_vw + cp.float32(1e-6))
    temp_arrays['rho_leaf'][:] = rho_air * T_air_gw_K / (T_leaf_K + cp.float32(1e-6))
    temp_arrays['rho_af'][:] = k_Pa * cp.float32(1000) / (R * T_leaf_K)
    temp_arrays['rho_wall'][:] = rho_air * T_air_gw_K / (T_svw_K + cp.float32(1e-6))
    temp_arrays['rho_avw'][:] = (rho_air + temp_arrays['rho_wall']) / cp.float32(2)
    temp_arrays['C_vw'][:] = temp_arrays['rho_avw'] * c_pa * temp_arrays['b_cof'] * temp_arrays['v_af'] * (T_svw_K - temp_arrays['T_af_K'])
    temp_arrays['C_leaf'][:] = cp.float32(1.1) * LAI * temp_arrays['rho_af'] * c_pa * C_hnf * temp_arrays['v_af'] * (T_leaf_K - temp_arrays['T_af_K'])
    temp_arrays['R_n'][:] = cp.float32(0.86) * (temp_arrays['LR_leaf'] + temp_arrays['SR_leaf'] + temp_arrays['XR'])
    
    # Leaf stomatal resistance (r_l) - Jarvis Model
    # Typical physiological limits for generalized green wall plants
    r_l_min = cp.float32(100.0)
    r_l_max = cp.float32(5000.0)
    
    # Photosynthetically Active Radiation (PAR) is roughly 50% of global solar radiation
    PAR = cp.float32(0.5) * I_s
    k_light = cp.float32(50.0)  # Light response decay coefficient
    
    # Base stomatal response: smooth transition from r_l_max (night) to r_l_min (bright day)
    r_l_base = r_l_min + (r_l_max - r_l_min) * cp.exp(-PAR / k_light)
    
    # Calculate Vapor Pressure Deficit (VPD) in kPa to quantify global atmospheric dryness
    T_air_C = T_air_gw_K - cp.float32(273.15)
    e_s_kpa = cp.float32(0.6108) * cp.exp((cp.float32(17.27) * T_air_C) / (T_air_C + cp.float32(237.3)))
    e_a_kpa = e_s_kpa * (RH / cp.float32(100.0))
    VPD = cp.maximum(e_s_kpa - e_a_kpa, cp.float32(0.0))
    
    # VPD stress penalty: stomata automatically close in extremely dry air (>1.5 kPa) to prevent water loss
    vpd_stress = cp.where(VPD > cp.float32(1.5), cp.float32(1.0) + cp.float32(0.5) * (VPD - cp.float32(1.5)), cp.float32(1.0))
    
    r_l = cp.minimum(r_l_base * vpd_stress, r_l_max)
    
    temp_arrays['r_air'][:] = cp.power((cp.log((Za - Zd) / Zo_f)), 2) / (cp.power(Kv, 2) * cp.maximum(v, cp.float32(0.1)))
    temp_arrays['r_s'][:] = r_l / (cp.float32(0.5) * LAI)
    temp_arrays['e_s'][:] = cp.float32(610.78) * cp.exp((cp.float32(17.27) * (T_air_gw_K - cp.float32(273.15))) / (T_air_gw_K - cp.float32(273.15) + cp.float32(237.3)))
    temp_arrays['e_air'][:] = (RH / cp.float32(100)) * temp_arrays['e_s']
    temp_arrays['delta'][:] = (cp.float32(4098) * temp_arrays['e_s']) / ((T_air_gw_K - cp.float32(273.15) + cp.float32(237.3)) ** 2)
    temp_arrays['gamma'][:] = cp.float32(0.665) * k_Pa
    temp_arrays['LH_leaf'][:] = (temp_arrays['delta'] * temp_arrays['R_n'] + rho_air * c_pa * (temp_arrays['e_s'] - temp_arrays['e_air']) / (temp_arrays['r_air'] + cp.float32(1e-6))) / (temp_arrays['delta'] + temp_arrays['gamma'] * (1 + temp_arrays['r_s'] / (temp_arrays['r_air'] + cp.float32(1e-6))))
    condition = cp.full_like(T_svw_K, is_warmup and t_idx == 0, dtype=cp.bool_)
    cooling_rate = cp.float32(0.0)
    if is_warmup and t_idx == 0:
        T_air_now = T_air_gw_K + 273.15
        T_wall_init = prev_T_svw_K
        delta_T = T_wall_init - T_air_now
        cooling_rate = z_eff * c_pw * rho_of_wall * delta_T / dt
        cooling_rate = cp.clip(cooling_rate, -30.0, 30.0)
    S_init = cooling_rate
    temp_arrays['S_wall'][:] = cp.where(condition, S_init, z_eff * c_pw * rho_of_wall * (T_svw_K - prev_T_svw_K) / dt)
    temp_arrays['S_leaf'][:] = cp.where(condition, cp.float32(0), cp.float32(2400) * LAI * (T_leaf_K - prev_T_leaf_K) / dt)
    temp_arrays['eq1'][:] = temp_arrays['LR_leaf'] + temp_arrays['SR_leaf'] + temp_arrays['XR'] - temp_arrays['C_leaf'] - temp_arrays['LH_leaf'] - temp_arrays['S_leaf']
    temp_arrays['eq2'][:] = temp_arrays['LR_vw'] + temp_arrays['SR_vw'] - temp_arrays['XR'] - temp_arrays['C_vw'] - temp_arrays['Q_wall'] - temp_arrays['S_wall']
    return temp_arrays['eq1'], temp_arrays['eq2']

# Equations for bare wall
def equations_bare_wall(T_sbw_K, t_idx, T_air_origin_K, v_origin, Za, 
                        T_sky_K, epsilon_sky, T_gr_K, F_sky, F_gr, I_s, rho_air, 
                        prev_T_sbw_K, temp_arrays, is_warmup=False):
    T_sky_K = cp.full_like(T_sbw_K, T_sky_K)
    epsilon_sky = cp.full_like(T_sbw_K, epsilon_sky)
    T_gr_K = cp.full_like(T_sbw_K, T_gr_K)
    rho_air = cp.full_like(T_sbw_K, rho_air)

    T_indoor_C = cp.where(T_air_origin_K >= 26.0, cp.float32(26.0), cp.float32(22.0))
    T_indoor_C = cp.where(T_air_origin_K <= 14.0, cp.float32(20.0), cp.float32(22.0))

    T_inw_C = (h1 * T_indoor_C + U_wall * (T_sbw_K - cp.float32(273.15))) / (h1 + U_wall)
    T_inw_K = T_inw_C + cp.float32(273.15)
    
    temp_arrays['LR_bw'][:] = (epsilon_wall * epsilon_sky * sigma * F_sky * (cp.power(T_sky_K, 4) - cp.power(T_sbw_K, 4)) +
                               epsilon_wall * epsilon_gr * sigma * F_gr * (cp.power(T_gr_K, 4) - cp.power(T_sbw_K, 4)))
    temp_arrays['SR_bw'][:] = I_s * alpha_wall
    temp_arrays['Q_wall'][:] = (T_sbw_K - T_inw_K) / (R_vw + cp.float32(1e-6))
    temp_arrays['C_bw'][:] = rho_air * c_pa * C_hnw * v_origin * (T_sbw_K - T_air_origin_K)
    condition = cp.full_like(T_sbw_K, is_warmup and t_idx == 0, dtype=cp.bool_)
    cooling_rate = cp.float32(0.0)
    if is_warmup and t_idx == 0:
        T_air_now = T_air_origin_K + 273.15
        T_wall_init = prev_T_sbw_K
        delta_T = T_wall_init - T_air_now
        cooling_rate = z_eff * c_pw * rho_of_wall * delta_T / dt
        cooling_rate = cp.clip(cooling_rate, -30.0, 30.0)
    S_init = cooling_rate
    temp_arrays['S_wall'][:] = cp.where(condition, S_init, z_eff * c_pw * rho_of_wall * (T_sbw_K - prev_T_sbw_K) / dt)
    return temp_arrays['LR_bw'] + temp_arrays['SR_bw'] - temp_arrays['C_bw'] - temp_arrays['Q_wall'] - temp_arrays['S_wall']

# Batch Jacobian for green wall
def batch_jacobian(T_svw, T_leaf, t_idx, batch_inputs, is_warmup, eps=cp.float32(1e-4)):
    eq1_ref, eq2_ref = equations_green_wall(T_svw, T_leaf, t_idx, *batch_inputs, is_warmup)
    eq1 = eq1_ref.copy()
    eq2 = eq2_ref.copy()
    
    eq1_p1_ref, eq2_p1_ref = equations_green_wall(T_svw + eps, T_leaf, t_idx, *batch_inputs, is_warmup)
    J11 = (eq1_p1_ref - eq1) / eps
    J21 = (eq2_p1_ref - eq2) / eps
    
    eq1_p2_ref, eq2_p2_ref = equations_green_wall(T_svw, T_leaf + eps, t_idx, *batch_inputs, is_warmup)
    J12 = (eq1_p2_ref - eq1) / eps
    J22 = (eq2_p2_ref - eq2) / eps

    J = cp.stack([J11, J12, J21, J22], axis=1).reshape(-1, 2, 2)
    
    b = cp.stack([-eq1, -eq2], axis=1)
        
    delta = cp.linalg.solve(J, b)
    return delta

# Process batch function
def process_batch(batch_idx, batch_size, t_idx, streams, result_memmap,
                  current_T_svw_K, current_T_leaf_K, current_T_sbw_K,
                  prev_T_svw_K, prev_T_leaf_K, prev_T_sbw_K, is_warmup):
    month, day, hour = hour_list[t_idx]
    VCWG_memmap = np.memmap(os.path.join(result_folder, f'VCWG_results/VCWG_results_with_glazing_ratio_GF_{month}_{day}_{hour}.npy').replace('\\', '/'), dtype=np.float32, mode='r', shape=(num_rep_points, 7))

    start_idx = batch_idx * batch_size
    end_idx = min((batch_idx + 1) * batch_size, num_points)
    batch_size_actual = end_idx - start_idx

    indices = cp.asnumpy(rep_idx_arr[start_idx:end_idx])
    batch_VCWG = cp.array(VCWG_memmap[indices], dtype=cp.float32)
    T_air_gw_K = batch_VCWG[:, 3]
    v = cp.maximum(batch_VCWG[:, 4], cp.float32(0.1))
    T_air_origin_K = batch_VCWG[:, 5]
    v_origin = cp.maximum(batch_VCWG[:, 6], cp.float32(0.1))

    # Load solar data for current hour
    if t_idx in diurnal_t_idx_list:
        solar_path = os.path.join(result_folder, f'solar_irradiation/solar_hourly_with_glazing_ratio_{month}_{day}_{hour}.npy').replace('\\', '/')
        solar_memmap = np.memmap(solar_path, dtype=np.float32, mode='r', shape=(num_points, 4))
        I_s = cp.array(solar_memmap[start_idx:end_idx, 3])
    else:
        I_s = cp.zeros(batch_size_actual, dtype=cp.float32)

    with streams[batch_idx % len(streams)]:
        batch_inputs = [
            T_air_gw_K,
            v,
            C_hnf,
            Za,
            Zd,
            Zo_f,
            get_broadcasted_data(t_idx)['T_sky_K'],
            get_broadcasted_data(t_idx)['epsilon_sky'],
            get_broadcasted_data(t_idx)['T_gr_K'],
            get_broadcasted_data(t_idx)['k_Pa'],
            F_sky[start_idx:end_idx],
            F_gr[start_idx:end_idx],
            F_bld[start_idx:end_idx],
            I_s,
            get_broadcasted_data(t_idx)['rho_air'],
            prev_T_svw_K[start_idx:end_idx],
            prev_T_leaf_K[start_idx:end_idx],
            get_broadcasted_data(t_idx)['RH'],
            preallocate_temp_arrays(batch_size_actual),
        ]

        local_prev_svw = batch_inputs[-4] # prev_T_svw_K slice
        
        bad_mask = (local_prev_svw > 353.15) | (local_prev_svw < 200) | cp.isnan(local_prev_svw)
        if cp.any(bad_mask):
            with open(error_txt, 'a') as f:
                f.write(f"Error, temperature anomaly detected in hour {t_idx}.\n")
                f.flush()
                raise RuntimeError(f"High temperature detected at t_idx {t_idx}. See {error_txt} for details.")

        batch_T_svw = current_T_svw_K[start_idx:end_idx].copy()
        batch_T_leaf = current_T_leaf_K[start_idx:end_idx].copy()
        batch_T_sbw = current_T_sbw_K[start_idx:end_idx].copy()

        # Newton-Raphson for green wall
        tol = cp.float32(1e-3)
        max_iter = 30
        for _ in range(max_iter):
            eq1, eq2 = equations_green_wall(batch_T_svw, batch_T_leaf, t_idx, *batch_inputs, is_warmup)
            if cp.all(cp.abs(eq1) < tol) & cp.all(cp.abs(eq2) < tol):
                break
            delta = batch_jacobian(batch_T_svw, batch_T_leaf, t_idx, batch_inputs, is_warmup)
            step_factor = cp.float32(0.8)
            T_svw_new = batch_T_svw + delta[:, 0] * step_factor
            T_leaf_new = batch_T_leaf + delta[:, 1] * step_factor
            mask = cp.logical_or(cp.isnan(T_svw_new) | cp.isinf(T_svw_new) | (T_svw_new < 200) | (T_svw_new > 353.15), 
                                 cp.isnan(T_leaf_new) | cp.isinf(T_leaf_new) | (T_leaf_new < 200) | (T_leaf_new > 353.15))
            while cp.any(mask):
                step_factor *= cp.float32(0.6)
                T_svw_new = batch_T_svw + delta[:, 0] * step_factor
                T_leaf_new = batch_T_leaf + delta[:, 1] * step_factor
                mask = cp.logical_or(cp.isnan(T_svw_new) | cp.isinf(T_svw_new) | (T_svw_new < 200) | (T_svw_new > 353.15), 
                                     cp.isnan(T_leaf_new) | cp.isinf(T_leaf_new) | (T_leaf_new < 200) | (T_leaf_new > 353.15))
                if step_factor < cp.float32(1e-6):
                    break
            batch_T_svw[:] = cp.where(mask, batch_T_svw, T_svw_new)
            batch_T_leaf[:] = cp.where(mask, batch_T_leaf, T_leaf_new)

        # Newton-Raphson for bare wall
        bare_wall_inputs = [
            T_air_origin_K,
            v_origin,
            Za,
            get_broadcasted_data(t_idx)['T_sky_K'],
            get_broadcasted_data(t_idx)['epsilon_sky'],
            get_broadcasted_data(t_idx)['T_gr_K'],
            F_sky[start_idx:end_idx],
            F_gr[start_idx:end_idx],
            I_s,
            get_broadcasted_data(t_idx)['rho_air'],
            prev_T_sbw_K[start_idx:end_idx],
            preallocate_temp_arrays(batch_size_actual)
        ]

        local_prev_sbw = bare_wall_inputs[-2]
        bad_mask_sbw = (local_prev_sbw > 353.15) | (local_prev_sbw < 200) | cp.isnan(local_prev_sbw)
        if cp.any(bad_mask_sbw):
            with open(error_txt, 'a') as f:
                f.write(f"Error, temperature anomaly detected in hour {t_idx}.\n")
                f.flush()
                raise RuntimeError(f"High temperature detected at t_idx {t_idx}. See {error_txt} for details.")

        for _ in range(max_iter):
            eq_ref = equations_bare_wall(batch_T_sbw, t_idx, *bare_wall_inputs, is_warmup)
            eq = eq_ref.copy()
            
            if cp.all(cp.abs(eq) < tol):
                break
            
            eps = cp.float32(1e-4)
            
            eq_p_ref = equations_bare_wall(batch_T_sbw + eps, t_idx, *bare_wall_inputs, is_warmup)
            eq_p = eq_p_ref
                        
            eq_p = equations_bare_wall(batch_T_sbw + eps, t_idx, *bare_wall_inputs, is_warmup).copy()
            eq_m = equations_bare_wall(batch_T_sbw - eps, t_idx, *bare_wall_inputs, is_warmup).copy()

            J = (eq_p - eq_m) / (2 * eps + cp.float32(1e-6))
            delta = eq / (J + cp.float32(1e-6))
            step_factor = cp.float32(0.8)
            T_sbw_new = batch_T_sbw - delta * step_factor
            mask = cp.logical_or(cp.isnan(T_sbw_new) | cp.isinf(T_sbw_new) | (T_sbw_new < 200) | (T_sbw_new > 353.15), cp.abs(delta) > cp.float32(50))
            while cp.any(mask):
                step_factor *= cp.float32(0.6)
                T_sbw_new = batch_T_sbw - delta * step_factor
                mask = cp.logical_or(cp.isnan(T_sbw_new) | cp.isinf(T_sbw_new) | (T_sbw_new < 200) | (T_sbw_new > 353.15), cp.abs(delta) > cp.float32(50))
                if step_factor < cp.float32(1e-6):
                    break
            batch_T_sbw[:] = cp.where(mask, batch_T_sbw, T_sbw_new)

        # Update results
        if result_memmap is not None:
            result_memmap[start_idx:end_idx, 0] = cp.asnumpy(batch_T_sbw - batch_T_svw)
            result_memmap[start_idx:end_idx, 1] = cp.asnumpy(batch_T_svw - cp.float32(273.15))
            result_memmap[start_idx:end_idx, 2] = cp.asnumpy(batch_T_sbw - cp.float32(273.15))
        
        current_T_svw_K[start_idx:end_idx] = batch_T_svw
        current_T_leaf_K[start_idx:end_idx] = batch_T_leaf
        current_T_sbw_K[start_idx:end_idx] = batch_T_sbw

        # Check for high temperatures
        T_svw_C = batch_T_svw - cp.float32(273.15)
        T_sbw_C = batch_T_sbw - cp.float32(273.15)
        T_leaf_C = batch_T_leaf - cp.float32(273.15)
        mask_error = (T_svw_C > 80) | (T_sbw_C > 80) | (T_leaf_C > 80)
        if cp.any(mask_error):
            error_indices = cp.where(mask_error)[0]
            with open(error_txt, 'a') as f:
                for idx in error_indices:
                    global_idx = start_idx + idx
                    f.write(f"Error in w_idx {global_idx}, t_idx {t_idx}: T_svw_C={T_svw_C[idx]}, T_sbw_C={T_sbw_C[idx]}, T_leaf_C={T_leaf_C[idx]}\n")
                f.flush()
                raise RuntimeError(f"High temperature detected at t_idx {t_idx}. See {error_txt} for details.")

    cp.get_default_memory_pool().free_all_blocks()
    print(f"Processed hour {t_idx + 1}/{num_hours}, batch {batch_idx + 1}/{num_batches}")

# Main loop
if not os.path.exists(result_folder):
    os.makedirs(result_folder)

# Initialize previous temperatures
prev_T_svw_K = cp.full((num_points,), T_db_array[0] + 273.15 + 2, dtype=cp.float32)
prev_T_leaf_K = cp.full((num_points,), T_db_array[0] + 273.15 + 0, dtype=cp.float32)
prev_T_sbw_K = cp.full((num_points,), T_db_array[0] + 273.15 + 5, dtype=cp.float32)

# Estimate batch size
free_mem, _ = cp.cuda.runtime.memGetInfo()
bytes_per_point = 4 * 20
batch_size = min(50000000, free_mem // bytes_per_point)
num_batches = (num_points + batch_size - 1) // batch_size
streams = [stream.Stream() for _ in range(16)]

for t_idx in range(num_hours):
    month, day, hour = hour_list[t_idx]
    # Only run warm-up once at simulation start
    if t_idx == 0:
        print("\nStarting warm-up 24h for simulation start (day 1)")

        # Warm-up runs the next 24 physical hours starting from this hour index if available
        for warmup_hour in range(24):
            wu_t_idx = t_idx + warmup_hour
            if wu_t_idx >= num_hours:
                break

            current_T_svw_K = prev_T_svw_K.copy()
            current_T_leaf_K = prev_T_leaf_K.copy()
            current_T_sbw_K = prev_T_sbw_K.copy()

            for batch_idx in range(num_batches):
                process_batch(batch_idx, batch_size, wu_t_idx, streams, None,
                              current_T_svw_K, current_T_leaf_K, current_T_sbw_K,
                              prev_T_svw_K, prev_T_leaf_K, prev_T_sbw_K, is_warmup=True)

            for s in streams:
                s.synchronize()

            prev_T_svw_K = current_T_svw_K.copy()
            prev_T_leaf_K = current_T_leaf_K.copy()
            prev_T_sbw_K = current_T_sbw_K.copy()

        print("Warm-up finished, now starting formal simulation\n")

    # Initialize result memmap for current time step
    result_file = os.path.join(result_folder, f'surface_temperatures/{city}_surface_temperatures_GF_with_glazing_ratio_{month}_{day}_{hour}.npy').replace('\\', '/')

    os.makedirs(os.path.dirname(result_file), exist_ok=True)
    
    result_memmap = np.memmap(result_file, dtype=np.float32, mode='w+', shape=(num_points, 3))

    # Initialize temperatures
    current_T_svw_K = prev_T_svw_K.copy()
    current_T_leaf_K = prev_T_leaf_K.copy()
    current_T_sbw_K = prev_T_sbw_K.copy()

    for batch_idx in range(num_batches):
        process_batch(batch_idx, batch_size, t_idx, streams, result_memmap,
                      current_T_svw_K, current_T_leaf_K, current_T_sbw_K,
                      prev_T_svw_K, prev_T_leaf_K, prev_T_sbw_K, is_warmup=False)
    
    for s in streams:
        s.synchronize()

    prev_T_svw_K = current_T_svw_K.copy()
    prev_T_leaf_K = current_T_leaf_K.copy()
    prev_T_sbw_K = current_T_sbw_K.copy()

    # Save results
    result_memmap.flush()  # Ensure memmap is flushed
    del result_memmap

    # Free GPU memory at the start of each logical day to reduce fragmentation
    if (t_idx < len(hour_label_list) and hour_label_list[t_idx] == 1):
        cp.get_default_memory_pool().free_all_blocks()

    print(f"Results saved to {result_file}")

end_time = time.time()
elapsed_time = end_time - start_time
days = elapsed_time // (24 * 3600)
hours = (elapsed_time % (24 * 3600)) // 3600
minutes = (elapsed_time % 3600) // 60
seconds = elapsed_time % 60

print(f"Done in {int(days)} days, {int(hours)} hours, {int(minutes)} minutes, and {int(seconds)} seconds")