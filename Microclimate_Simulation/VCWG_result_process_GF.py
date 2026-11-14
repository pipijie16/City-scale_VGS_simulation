import os
import numpy as np
from collections import defaultdict
import shutil
import logging
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

args = parse_args(sys.argv[1:])

city = args.get('city_name')
intermediate_folder = args.get('intermediate_folder')
result_folder = args.get('result_folder')
microclimate_sim_dir = args.get('microclimate_sim_dir')

base_data_dir = os.path.join(intermediate_folder, f"solar_radiance/")
os.makedirs(base_data_dir, exist_ok=True)
output_dir = os.path.join(intermediate_folder, "temptxt/")
os.makedirs(output_dir, exist_ok=True)
representative_points_file = os.path.join(intermediate_folder, f"{city}_basic_data/representative_points.txt")
itg_folder = os.path.join(intermediate_folder, "itg_folder/")
os.makedirs(itg_folder, exist_ok=True)

template_dir = os.path.join(microclimate_sim_dir, f"VCWGv2.0.0  for Green Facades/")
vcwg_epw = os.path.join(template_dir, 'resources/epw/').replace('\\', '/')

if os.path.exists(vcwg_epw):
  for filename in os.listdir(vcwg_epw):
    file_path = os.path.join(vcwg_epw, filename)
    try:
      if os.path.isfile(file_path) or os.path.islink(file_path):
        os.unlink(file_path)
      elif os.path.isdir(file_path):
        shutil.rmtree(file_path)
    except Exception as e:
      print(f"Failed to delete {file_path}: {e}")
else:
  # Ensure the directory exists if missing
  os.makedirs(vcwg_epw, exist_ok=True)

origin_template_dir = os.path.join(microclimate_sim_dir, f"VCWGv2.0.0-main/")
origin_vcwg_epw = os.path.join(origin_template_dir, 'resources/epw/').replace('\\', '/')

if os.path.exists(origin_vcwg_epw):
  for filename in os.listdir(origin_vcwg_epw):
    file_path = os.path.join(origin_vcwg_epw, filename)
    try:
      if os.path.isfile(file_path) or os.path.islink(file_path):
        os.unlink(file_path)
      elif os.path.isdir(file_path):
        shutil.rmtree(file_path)
    except Exception as e:
      print(f"Failed to delete {file_path}: {e}")
else:
  # Ensure the directory exists if missing
  os.makedirs(origin_vcwg_epw, exist_ok=True)

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

dates = sorted([[month, day] for month, day in dates_set])

first_month = dates[0][0]
first_day = dates[0][1]

os.makedirs(itg_folder, exist_ok=True)
os.makedirs(result_folder, exist_ok=True)

def cleanup_itg_folder():
    """Clean up the integration folder."""
    if os.path.exists(itg_folder):
        for item in os.listdir(itg_folder):
            try:
                item_path = os.path.join(itg_folder, item)
                if os.path.isfile(item_path): os.unlink(item_path)
                elif os.path.isdir(item_path): shutil.rmtree(item_path)
            except Exception as e:
                print(f"Cleanup skipped: {item} -> {e}")
    os.makedirs(itg_folder, exist_ok=True)

def process_grid(grid_info):
    """Extract points from grid files and save as txt with ClassID."""
    grid_path, _ = grid_info
    points = []
    try:
        with open(grid_path, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 6:
                    points.append(list(map(float, parts[:6])))
    except: return

    if not points: return

    fc_name = os.path.basename(grid_path).replace('.pts', '')
    txt_path = os.path.join(output_dir, f"{fc_name}_with_classid.txt")

    try:
        if not fc_name.startswith('Sensor_'): return 
        class_id = int(fc_name.split('_')[-1])
    except: return

    try:
        with open(txt_path, 'w') as f:
            for p in points:
                f.write(f"{p[0]},{p[1]},{p[2]},{p[3]},{p[4]},{p[5]},{class_id},{fc_name}\n")
    except: pass

def process_file_representative(txt_file):
    """Process a single txt file to extract representative points."""
    z_tol = 0.1
    local_pts = []
    try:
        with open(os.path.join(output_dir, txt_file), 'r') as f:
            for line in f:
                p = line.strip().split(',')
                # x,y,z,nx,ny,nz,class_id,fc_name
                row = (float(p[0]), float(p[1]), float(p[2]), float(p[3]), 
                       float(p[4]), float(p[5]), int(p[6]), p[7])
                
                # Simple Z-level deduplication
                z = row[2]
                if not any(abs(existing[2] - z) <= z_tol for existing in local_pts):
                    local_pts.append(row)
    except: return []
    return local_pts

def process_representative_points():
    """Sequential extraction of representative points (no multiprocessing)."""
    txt_files = [f for f in os.listdir(output_dir) if f.endswith("_with_classid.txt")]
    if not txt_files:
        print("No _with_classid.txt files found")
        return None

    all_rep_points = []
    for txt in txt_files:
        local = process_file_representative(txt)
        all_rep_points.extend(local)

    try:
        with open(representative_points_file, 'w') as f:
            for p in all_rep_points:
                f.write(f"{p[0]},{p[1]},{p[2]},{p[3]},{p[4]},{p[5]},{p[6]},{p[7]}\n")
        print(f"Found {len(all_rep_points)} representative points")
        return True
    except Exception as e:
        print(f"Error saving points: {e}")
        return False

def load_class_data(args):
    """Convert simulation txt data to .npy files. DO NOT return data arrays."""
    cid, base_dir, t_points, is_origin = args
    prefix = 'origin_' if is_origin else ''
    
    # Check if exists
    check_f = f"{itg_folder}{prefix}heights_class_{cid}.npy"
    if os.path.exists(check_f): return

    src_file = f"{base_dir}/{first_month}.{first_day}/VCWG_{city}_Class{cid}/th_profiles{city}_Class{cid}.txt"
    if not os.path.exists(src_file): return

    try:
        with open(src_file, 'r') as f:
            lines = f.readlines()[3:]
        heights = [float(l.split()[0]) for l in lines]
        n_h = len(heights)
        n_t = len(t_points)

        # Use float32 to save disk/memory
        th = np.zeros((n_h, n_t), dtype=np.float32)
        vx = np.zeros((n_h, n_t), dtype=np.float32)
        vy = np.zeros((n_h, n_t), dtype=np.float32)

        for t_idx, (m, d, h) in enumerate(t_points):
            bp = f"{base_dir}/{m}.{d}/VCWG_{city}_Class{cid}/"
            
            def read_col(fname, arr):
              path = bp + fname
              if os.path.exists(path):
                with open(path, 'r') as f:
                  for i, l in enumerate(f.readlines()[3:]):
                    try:
                      arr[i, t_idx] = float(l.split()[h + 1])
                    except:
                      pass
            
            read_col(f"th_profiles{city}_Class{cid}.txt", th)
            read_col(f"vx_profiles{city}_Class{cid}.txt", vx)
            read_col(f"vy_profiles{city}_Class{cid}.txt", vy)

        np.save(f"{itg_folder}{prefix}th_class_{cid}.npy", th)
        np.save(f"{itg_folder}{prefix}vx_class_{cid}.npy", vx)
        np.save(f"{itg_folder}{prefix}vy_class_{cid}.npy", vy)
        np.save(f"{itg_folder}{prefix}heights_class_{cid}.npy", np.array(heights))
        print(f"Saved Class {cid} (Origin={is_origin})")

    except Exception as e:
        print(f"Error loading {cid}: {e}")

def prepare_simulation_data():
    """Prepare and map simulation data."""
    t_points = [(m, d, h) for m, d in dates for h in range(0, 24)]
    
    base_gf = os.path.join(intermediate_folder, f"VCWG_{city}_Result_GF/")
    base_og = os.path.join(intermediate_folder, f"VCWG_{city}_Result_origin/")
    
    tasks = []
    # Build tasks
    for base, is_org in [(base_gf, False), (base_og, True)]:
        sample_day = base + f"{first_month}.{first_day}/"
        if os.path.exists(sample_day):
            for d in os.listdir(sample_day):
                if d.startswith(f"VCWG_{city}_Class"):
                    try:
                        cid = int(d.replace(f"VCWG_{city}_Class", ""))
                        tasks.append((cid, base, t_points, is_org))
                    except: pass
    
    print(f"Processing {len(tasks)} simulation files...")
    for idx, task in enumerate(tasks, 1):
        load_class_data(task)

    # Map data using mmap
    data_map = {'GF': defaultdict(dict), 'OG': defaultdict(dict)}
    
    for cid, _, _, is_org in tasks:
        pre = 'origin_' if is_org else ''
        k = 'OG' if is_org else 'GF'
        try:
            f_th = f"{itg_folder}{pre}th_class_{cid}.npy"
            if os.path.exists(f_th):
                data_map[k]['th'][cid] = np.load(f_th, mmap_mode='r')
                data_map[k]['vx'][cid] = np.load(f"{itg_folder}{pre}vx_class_{cid}.npy", mmap_mode='r')
                data_map[k]['vy'][cid] = np.load(f"{itg_folder}{pre}vy_class_{cid}.npy", mmap_mode='r')
                data_map[k]['h'][cid] = np.load(f"{itg_folder}{pre}heights_class_{cid}.npy", mmap_mode='r')
        except: pass
        
    return data_map, t_points

def compute_wind(vx, vy):
    return np.sqrt(vx**2 + vy**2)

def organize_high_dim_array():
    if not process_representative_points(): return

    # 1. Prepare data (IO phase)
    data_map, t_points = prepare_simulation_data()

    num_hours = len(t_points)

    # 2. Load points
    print("Loading representative points...")
    with open(representative_points_file, 'r') as f:
        lines = f.readlines()
    
    num_points = len(lines)
    if num_points == 0: return

    # Parse points
    coords = []
    meta = [] # (z, class_id, fc_name)
    
    for line in lines:
        parts = line.strip().split(',')
        coords.append([float(x) for x in parts[:3]])
        meta.append((float(parts[2]), int(parts[6]), parts[7]))
    
    coords = np.array(coords, dtype=np.float32)
    
    # 3. Pre-compute Geometry Indices
    print("Pre-computing geometry indices (Optimization)...")
    
    # Group Z by facade name
    fc_z_map = {}
    temp_z = defaultdict(list)
    for z, _, fc in meta:
        temp_z[fc].append(z)
    
    # Sort Z values for each facade
    for fc, z_list in temp_z.items():
        fc_z_map[fc] = np.sort(np.unique(z_list))
    
    # Compute metadata for each point: (h_idx, class_id)
    # This avoids doing list.index() inside the main loop
    point_metadata = []
    for i in range(num_points):
        z, cid, fc = meta[i]
        
        # Use binary search (searchsorted) for speed
        sorted_z = fc_z_map[fc]
        h_idx = np.searchsorted(sorted_z, z)
        
        # Check exact match tolerance
        if h_idx < len(sorted_z) and abs(sorted_z[h_idx] - z) < 1e-4:
            pass # Found
        else:
            h_idx = -1 # Not found
            
        point_metadata.append((h_idx, cid))

    print(f"Start filling {num_hours} hours (Optimized Single-Thread)...")

    # 4. Main Time Loop (Single Thread for stability)
    for hour_idx in range(num_hours):
        month, day, hour = t_points[hour_idx]

        include = True
        if month == s_m and day == s_d:
            if hour < s_h:
                include = False
        if month == e_m and day == e_d:
            if hour > e_h:
                include = False
        
        if not include:
            continue
        
        fpath = os.path.join(result_folder, f'VCWG_results/VCWG_results_GF_{month}_{day}_{hour}.npy').replace('\\', '/')

        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        
        # Create new memmap file
        fp = np.memmap(fpath, dtype='float32', mode='w+', shape=(num_points, 7))
        
        # Write coordinates
        fp[:, :3] = coords
        
        # Fill data point by point (using pre-computed indices)
        for i in range(num_points):
            h_idx, cid = point_metadata[i]
            
            if h_idx == -1: continue
                
            # GF Data
            if cid in data_map['GF']['th']:
                src_th = data_map['GF']['th'][cid]
                # Boundary check
                s = 3 * h_idx
                if s < src_th.shape[0]:
                    e = min(s + 3, src_th.shape[0])
                    
                    # Sequential Read from Disk (OS Cache friendly)
                    val_th = np.mean(src_th[s:e, hour_idx])
                    val_vx = np.mean(data_map['GF']['vx'][cid][s:e, hour_idx])
                    val_vy = np.mean(data_map['GF']['vy'][cid][s:e, hour_idx])
                    
                    fp[i, 3] = val_th
                    fp[i, 4] = compute_wind(val_vx, val_vy)
                    
                    # Origin Data
                    if cid in data_map['OG']['th']:
                        src_og = data_map['OG']['th'][cid]
                        if s < src_og.shape[0]:
                            e_og = min(s + 3, src_og.shape[0])
                            o_th = np.mean(src_og[s:e_og, hour_idx])
                            o_vx = np.mean(data_map['OG']['vx'][cid][s:e_og, hour_idx])
                            o_vy = np.mean(data_map['OG']['vy'][cid][s:e_og, hour_idx])
                            
                            fp[i, 5] = o_th
                            fp[i, 6] = compute_wind(o_vx, o_vy)

        fp.flush()
        # Clean memory occasionally
        if (hour_idx + 1) % 10 == 0:
            print(f"Completed {hour_idx + 1}/{num_hours}")
            
    if os.path.exists(output_dir): shutil.rmtree(output_dir)
    print("VCWG results processes complete.")

def main():
    try:
        os.makedirs(output_dir, exist_ok=True)
        # Grid processing
        grid_tasks = []
        for batch in os.listdir(base_data_dir):
            bp = os.path.join(base_data_dir, batch)
            if not os.path.isdir(bp): continue
            gp = os.path.join(bp, "model/grid/")
            if not os.path.exists(gp): continue
            for g in os.listdir(gp):
                if g.endswith(".pts"):
                    grid_tasks.append((os.path.join(gp, g), gp))

        if grid_tasks:
            print(f"Processing {len(grid_tasks)} grid files (single-thread)...")
            for task in grid_tasks:
                process_grid(task)
        
        organize_high_dim_array()
        cleanup_itg_folder()
        
    except Exception as e:
        logging.error(str(e))
        raise

if __name__ == "__main__":
    main()