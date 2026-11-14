import os
import shutil
import sys
import tempfile

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

def ensure_queenbee_local_unicode_patch(site_packages_dir):
    """
    Patches queenbee_local's subprocess stdout reader so non-UTF-8 bytes
    (e.g. GBK/cp936 text emitted by Radiance .exe on Chinese-locale Windows)
    don't crash the task with UnicodeDecodeError and trigger endless retries.
    """
    target_file = os.path.join(site_packages_dir, "queenbee_local", "__init__.py")

    if not os.path.exists(target_file):
        print(f"Warning: queenbee_local not found at {target_file}, skipping patch.")
        return

    old_snippet = "line.decode('utf-8').strip()"
    new_snippet = "line.decode('utf-8', errors='ignore').strip()"

    try:
        with open(target_file, "r", encoding="utf-8") as f:
            content = f.read()

        if new_snippet in content:
            # Already patched in a previous run
            return

        if old_snippet not in content:
            print(f"Warning: expected decode line not found in {target_file}; "
                  f"queenbee_local may have changed, skipping patch.")
            return

        # Keep a one-time backup of the original file, just in case
        backup_path = target_file + ".orig_bak"
        if not os.path.exists(backup_path):
            shutil.copy2(target_file, backup_path)

        patched_content = content.replace(old_snippet, new_snippet)
        with open(target_file, "w", encoding="utf-8") as f:
            f.write(patched_content)

        print(f"queenbee_local Unicode decode patch applied to: {target_file}")

    except Exception as e:
        print(f"Warning: Failed to patch queenbee_local for Unicode decode errors: {e}")

# Inject patch into Ladybug's python environment
ensure_queenbee_local_unicode_patch(ladybug_python)

from lbt_recipes.recipe import Recipe
from honeybee_radiance.lightsource.sky import ClimateBased
from ladybug.wea import Wea
import ladybug.analysisperiod as ap
import fnmatch
import time
import gc
import datetime

def parse_mmdd_hh_label(s):
    """Parse 'MM-DD HH' where HH is 0..23 and return (month, day, hour_label) or None."""
    try:
        mmdd, hh = s.rsplit(' ', 1)
        hh_int = int(hh)
        if not (0 <= hh_int <= 23):
            return None
        dt = datetime.datetime.strptime(mmdd, "%m-%d")
        return (dt.month, dt.day, hh_int)
    except Exception:
        return None

intermediate_folder = args.get('intermediate_folder')
directory = os.path.join(intermediate_folder, f"solar_radiance/")
os.makedirs(directory, exist_ok=True)

os.environ["TEMP"] = os.path.join(intermediate_folder, "temp/")
os.environ["TMP"] = os.path.join(intermediate_folder, "temp/")
os.makedirs(os.environ["TEMP"], exist_ok=True)

folders = subdirs = [d for d in os.listdir(directory) if os.path.isdir(os.path.join(directory, d))]  

epw_file = args.get('epw_file')
wea_obj = Wea.from_epw_file(epw_file)
ghi_collection = wea_obj.global_horizontal_irradiance
dni_collection = wea_obj.direct_normal_irradiance
dhi_collection = wea_obj.diffuse_horizontal_irradiance

gpu_flag = args.get('gpu_flag')
threads = int(args.get('num_threads'))

# Determine run interval from arguments: prefer 'start_dt'/'end_dt' strings like "MM-DD HH"
start_dt_arg = args.get('start_dt')
end_dt_arg = args.get('end_dt')

error_written = False  # Flag to track if anything was written to error_txt

# Also patch current main process
def _safe_tempfile_rmtree_local(cls, name, ignore_errors=False):
    try:
        shutil.rmtree(name, ignore_errors=True)
    except Exception:
        pass
tempfile.TemporaryDirectory._rmtree = classmethod(_safe_tempfile_rmtree_local)

# Custom rmtree function to avoid recursion issues
def safe_rmtree(path, max_retries=5, delay=0.5):
    """Safely remove a directory tree, handling permissions and sharing violations."""
    path = str(path)
    if not os.path.exists(path):
        return

    def on_rm_error(func, p, exc_info):
        try:
            os.chmod(p, 0o777)
            func(p)
        except Exception:
            pass

    for attempt in range(max_retries):
        try:
            if os.path.isfile(path):
                os.chmod(path, 0o666)
                os.remove(path)
            elif os.path.isdir(path):
                shutil.rmtree(path, onerror=on_rm_error)
            return
        except (PermissionError, OSError):
            time.sleep(delay)
        except Exception as e:
            print(f"Warning: Error removing {path}: {e}")
            return

def try_CPU_instead(_metric_):
    radiance_par_ = "-aa 0 -ab 2 -ad 512 -ar 16 -as 128 -dc 0.25 -dj 0.0 -dp 64 -dr 0 -ds 0.5 -dt 0.5 -lr 4 -lw 0.05 -ss 0.0 -st 0.85 -g 0"

    recipe.input_value_by_name('model', _model)
    recipe.input_value_by_name('sky', _sky)
    recipe.input_value_by_name('metric', _metric_)
    recipe.input_value_by_name('grid-filter', "*")
    recipe.input_value_by_name('radiance-parameters', radiance_par_)
    
    run_settings_ = f"--folder \"{simulation_folder}\" --workers {threads}"

    project_folder = recipe.run(run_settings_, radiance_check=True, silent=False, queenbee_path=queenbee_path)

for folder in folders:
    _model = os.path.join(directory, folder)

    simulation_folder = os.path.join(intermediate_folder, f"Point-in-Time/Simulation_{folder}")

    if not os.path.exists(simulation_folder):
        os.makedirs(simulation_folder)

    recipe = Recipe('point-in-time-grid')

    if gpu_flag:
        radiance_par_ = "-aa 0 -ab 2 -ad 512 -ar 16 -as 128 -dc 0.25 -dj 0.0 -dp 64 -dr 0 -ds 0.5 -dt 0.5 -lr 4 -lw 0.05 -ss 0.0 -st 0.85"
        run_settings_ = f"--folder \"{simulation_folder}\" --workers 1"
    else:
        radiance_par_ = "-aa 0 -ab 2 -ad 512 -ar 16 -as 128 -dc 0.25 -dj 0.0 -dp 64 -dr 0 -ds 0.5 -dt 0.5 -lr 4 -lw 0.05 -ss 0.0 -st 0.85 -g 0"
        run_settings_ = f"--folder \"{simulation_folder}\" --workers {threads}"

    _metric_ = "irradiance"

    # Build run_ranges: list of (month, day, hour) based on user input
    run_ranges = []

    start_dt_arg = args.get('start_dt')
    end_dt_arg = args.get('end_dt')

    start_parsed = parse_mmdd_hh_label(start_dt_arg) if start_dt_arg else None
    end_parsed = parse_mmdd_hh_label(end_dt_arg) if end_dt_arg else None

    if start_parsed is None or end_parsed is None:
        raise ValueError("Invalid or missing start_dt/end_dt. Must be 'MM-DD HH' format (HH: 0-23)")

    s_m, s_d, s_h = start_parsed
    e_m, e_d, e_h = end_parsed

    current_year = datetime.datetime.now().year
    start_dt = datetime.datetime(current_year, s_m, s_d, s_h)
    end_dt = datetime.datetime(current_year, e_m, e_d, e_h)

    # Handle cross-year
    if end_dt < start_dt:
        end_dt = end_dt.replace(year=current_year + 1)

    if end_dt < start_dt:
        raise ValueError("End datetime must not be earlier than start datetime.")

    # Generate sequence
    current = start_dt
    while current <= end_dt:
        run_ranges.append((current.month, current.day, current.hour))
        current += datetime.timedelta(hours=1)

    for (month, day, hour) in run_ranges:
        anp = ap.AnalysisPeriod(month, day, hour, month, day, hour, 1)
        ghi = ghi_collection.filter_by_analysis_period(anp)[0]
        dni = dni_collection.filter_by_analysis_period(anp)[0]
        dhi = dhi_collection.filter_by_analysis_period(anp)[0]

        if ghi == 0:
            continue
        # hour is user label 0..23; pass as-is to ClimateBased
        _sky = ClimateBased.from_location(location=wea_obj.location, month=month, day=day, hour=hour+1, direct_normal_irradiance=dni, diffuse_horizontal_irradiance=dhi, north_angle=0, is_colored=False)

        recipe.input_value_by_name('model', _model)
        recipe.input_value_by_name('sky', _sky)
        recipe.input_value_by_name('metric', _metric_)
        recipe.input_value_by_name('grid-filter', "*")
        recipe.input_value_by_name('radiance-parameters', radiance_par_)

        project_folder = recipe.run(run_settings_, radiance_check=True, silent=True)

        res_file_path = os.path.join(simulation_folder,'point_in_time_grid/results/pit/')

        if os.path.exists(res_file_path):
            res_files = [f for f in os.listdir(res_file_path) if f.endswith(".res")]

            res_file = os.path.join(res_file_path, res_files[0])

            # If cannot use GPU due to CUDA error, try CPU instead
            if os.path.getsize(res_file) != 0:
                print("File size is not zero, proceeding to copy results.")
            else:
                try_CPU_instead(_metric_)
        else:
            try_CPU_instead(_metric_)

        # Copy result files
        result_folder = os.path.join(simulation_folder,'point_in_time_grid/results/')
        target_folder = os.path.join(intermediate_folder, f'Solar_Irradiance_Results/{month}.{day} {hour + 1}/{folder}')
        if not os.path.exists(target_folder):
            os.makedirs(target_folder)
        try:
            shutil.copytree(result_folder, target_folder, dirs_exist_ok=True)
        except Exception as e:
            error_msg = f"Failed to copy results | Context: {month}.{day} {hour + 1}/{folder} | {e}"
            print(error_msg)
            error_txt = os.path.join(intermediate_folder, "solar_error.txt")
            with open(error_txt, "a", encoding="utf-8") as f:
                f.write(f"{error_msg}\n")

        time.sleep(0.5)
        
        # Clean up isolated simulation folder
        safe_rmtree(simulation_folder)

        # Clean up temporary directories
        temp_path = os.path.join(intermediate_folder, "temp/")
        if temp_path and os.path.exists(temp_path):
            for entry in os.listdir(temp_path):
                entry_path = os.path.join(temp_path, entry)
                if os.path.isdir(entry_path):
                    safe_rmtree(entry_path)
                else:
                    try:
                        os.chmod(entry_path, 0o666)
                        os.remove(entry_path)
                    except Exception:
                        pass
        gc.collect()

del recipe

print("Done Point-in-Time Grid Calculation")

if error_written:
    print("Some errors were logged during processing. Please check the error log for details.")