import os
import numpy as np
import mmap
import time
from tqdm import tqdm
import sys

# Helper function to parse command-line arguments (key-value pairs)
def parse_args(args):
    arg_dict = {}
    for i in range(0, len(args), 2):
        key = args[i].strip('\'"')
        val = args[i+1].strip('\'"') if i + 1 < len(args) else None
        arg_dict[key] = val
    return arg_dict


def count_lines_mmap(file_path):
    with open(file_path, 'r') as f:
        mmapped_file = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        
        line_count = mmapped_file.read().count(b'\n')
        mmapped_file.close()
    
    return line_count

# This script must be run via the GUI's subprocess call, which passes arguments.
args = parse_args(sys.argv[1:])

city = args.get('city_name')
intermediate_folder = args.get('intermediate_folder')
result_folder = args.get('result_folder')

file_path = os.path.join(intermediate_folder, f"{city}_basic_data/{city}_Points.txt")
num_points = count_lines_mmap(file_path)

grids_directory = os.path.join(intermediate_folder, f"view_factors_radiance/")

bvf_result_directory = os.path.join(intermediate_folder, f"BVF/results/")
svf_result_directory = os.path.join(intermediate_folder, f"SVF/results/")
os.makedirs(bvf_result_directory, exist_ok=True)
os.makedirs(svf_result_directory, exist_ok=True)

error_txt = os.path.join(intermediate_folder, "view_factors_error.txt")

folders = [d for d in os.listdir(grids_directory) if os.path.isdir(os.path.join(grids_directory, d))]
items = os.listdir(grids_directory)
folder_count = sum(os.path.isdir(os.path.join(grids_directory, item)) for item in items)

output_dir = result_folder
os.makedirs(output_dir, exist_ok=True)

data_shape = (num_points, 5)
view_factors_data_memmap = np.memmap(os.path.join(output_dir, 'view_factors_data.npy'), dtype=np.float32, mode='w+', shape=data_shape)

start_time = time.time()

def process_bvf_and_svf_results():
    point_data_matrix = np.zeros((num_points, 5), dtype=np.float32)  # Adjusted to 5 columns to include SVF
    point_count = 0
    
    folders = [d for d in os.listdir(grids_directory) if os.path.isdir(os.path.join(grids_directory, d))]

    with tqdm(total=folder_count, desc="Processing BVF and SVF results", leave=False) as pbar:
        for folder in folders:
            grids_path = os.path.join(grids_directory, f"{folder}/model/grid/")
            grids = [f for f in os.listdir(grids_path) if f.endswith(".pts")]
            grid_count = 1

            for grid in grids:
                grid_path = os.path.join(grids_path, grid)
                with open(grid_path, 'r') as grid_file:
                    grid_lines = grid_file.readlines()

                # Read BVF result
                bvf_result_path = os.path.join(bvf_result_directory, f"{folder}/{os.path.basename(grid_path).replace('.pts', '_BVF.txt')}")
                with open(bvf_result_path, 'r') as bvf_result_file:
                    bvf_result_lines = bvf_result_file.readlines()

                # Read SVF result
                svf_result_path = os.path.join(svf_result_directory, f"{folder}/{os.path.basename(grid_path).replace('.pts', '.res')}")
                try:
                    with open(svf_result_path, 'r') as svf_result_file:
                        svf_result_lines = svf_result_file.readlines()
                except Exception as e:
                    error = f"Error reading SVF result file {svf_result_path}: {e}\n"
                    with open(error_txt, "a") as file:
                        file.write(error)
                    continue

                # Check line count consistency
                if len(grid_lines) != len(bvf_result_lines) or len(grid_lines) != len(svf_result_lines):
                    error = f"Line count mismatch in {grid_path}, {bvf_result_path}, or {svf_result_path}\n"
                    with open(error_txt, "a") as file:
                        file.write(error)
                    continue
                
                for grid_line, bvf_result_line, svf_result_line in zip(grid_lines, bvf_result_lines, svf_result_lines):
                    grid_parts = grid_line.strip().split()
                    if len(grid_parts) >= 3:
                        x = float(grid_parts[0])
                        y = float(grid_parts[1])
                        z = float(grid_parts[2])
                        bvf_value = float(bvf_result_line.strip().split()[0])
                        svf_value = float(svf_result_line.strip().split()[0]) / 100  # Read SVF value
                        
                        point_data_matrix[point_count, 0] = x
                        point_data_matrix[point_count, 1] = y
                        point_data_matrix[point_count, 2] = z
                        point_data_matrix[point_count, 3] = bvf_value
                        point_data_matrix[point_count, 4] = svf_value

                        point_count += 1
                
                grid_count += 1

            pbar.update(1)
    
    if point_count != num_points:
        error = f"The number of lines in the grid file and the result file are not the same. \n"
        with open(error_txt, "a") as file:
            file.write(error)

    return point_data_matrix

point_data_matrix = process_bvf_and_svf_results()

view_factors_data_memmap[:, :] = point_data_matrix

del view_factors_data_memmap

end_time = time.time()
elapsed_time = end_time - start_time

# Convert elapsed time to days, hours, minutes, and seconds
days = elapsed_time // (24 * 3600)
elapsed_time = elapsed_time % (24 * 3600)
hours = elapsed_time // 3600
elapsed_time %= 3600
minutes = elapsed_time // 60
seconds = elapsed_time % 60

print(f"Done view factors result processing.")