import os
import shutil
import sys
import tempfile

os.environ['PYTHONIOENCODING'] = 'utf-8'

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

queenbee_path = os.path.join(ladybug_folder, "python/Scripts/queenbee.exe")

# Add the site-packages path within the Ladybug installation to sys.path
ladybug_python = os.path.join(ladybug_folder, "python/Lib/site-packages")
sys.path.append(ladybug_python)

from lbt_recipes.recipe import Recipe
import fnmatch

intermediate_folder = args.get('intermediate_folder')

threads = int(args.get('num_threads'))
gpu_flag = args.get('gpu_flag')

directory = os.path.join(intermediate_folder, "view_factors_radiance_with_glazing_ratio/")

folders = subdirs = [d for d in os.listdir(directory) if os.path.isdir(os.path.join(directory, d))]

def try_CPU(simulation_folder):
    radiance_par_ = "-aa 0 -ab 2 -ad 512 -ar 16 -as 128 -dc 0.25 -dj 0.0 -dp 64 -dr 0 -ds 0.5 -dt 0.5 -lr 4 -lw 0.05 -ss 0.0 -st 0.85 -g 0"

    recipe.input_value_by_name('model', _model)
    recipe.input_value_by_name('grid-filter', "*")
    recipe.input_value_by_name('radiance-parameters', radiance_par_)
    
    run_settings_ = f"--folder {simulation_folder} --workers {threads}"

    project_folder = recipe.run(run_settings_, radiance_check=True, silent=False, queenbee_path=queenbee_path)

for folder in folders:
    _model = os.path.join(directory, folder)

    simulation_folder = os.path.join(intermediate_folder, "Point-in-Time", "SVF_Simulation").replace('\\', '/')

    if not os.path.exists(simulation_folder):
        os.makedirs(simulation_folder)

    recipe = Recipe('sky-view')

    if gpu_flag:
        radiance_par_ = "-aa 0 -ab 2 -ad 512 -ar 16 -as 128 -dc 0.25 -dj 0.0 -dp 64 -dr 0 -ds 0.5 -dt 0.5 -lr 4 -lw 0.05 -ss 0.0 -st 0.85"
    else:
        radiance_par_ = "-aa 0 -ab 2 -ad 512 -ar 16 -as 128 -dc 0.25 -dj 0.0 -dp 64 -dr 0 -ds 0.5 -dt 0.5 -lr 4 -lw 0.05 -ss 0.0 -st 0.85 -g 0"
    
    run_settings_ = f"--folder {simulation_folder} --workers {threads}"

    recipe.input_value_by_name('model', _model)
    recipe.input_value_by_name('grid-filter', "*")
    recipe.input_value_by_name('radiance-parameters', radiance_par_)

    project_folder = recipe.run(run_settings_, radiance_check=True, silent=False)

    res_file_path = os.path.join(simulation_folder,'sky_view/results/sky_view/')

    if os.path.exists(res_file_path):
        res_files = [f for f in os.listdir(res_file_path) if f.endswith(".res")]

        res_file = os.path.join(res_file_path, res_files[0])

        #If can not use GPU due to CUDA error, try CPU instead
        if os.path.getsize(res_file) != 0:
            print("File size is not zero, proceeding to copy results.")
        else:
            try_CPU(simulation_folder)
    else:
        try_CPU(simulation_folder)

    #Copy result files
    result_folder = os.path.join(simulation_folder,'sky_view/results/sky_view/')
    target_folder = os.path.join(intermediate_folder, f"SVF_with_glazing_ratio/results/{folder}")
    if not os.path.exists(target_folder):
        os.makedirs(target_folder)
    shutil.copytree(result_folder, target_folder, dirs_exist_ok=True)

    temp_path = tempfile.gettempdir()
    pattern = "RestructureResults*"

    entries = os.listdir(simulation_folder)
    
    for entry in entries:
        entry_path = os.path.join(simulation_folder, entry)
        if os.path.isdir(entry_path):
            shutil.rmtree(entry_path)
        else:
            os.remove(entry_path)
    
    for root, dirs, files in os.walk(temp_path, topdown=False):  
        for dir_name in dirs:  
            if fnmatch.fnmatch(dir_name, pattern):  
                full_dir_path = os.path.join(root, dir_name)  
                shutil.rmtree(full_dir_path)

print("Done Sky View")