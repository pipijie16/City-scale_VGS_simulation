import os
import sys

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

points_path = os.path.join(intermediate_folder, f"{city}_basic_data/{city}_Points_with_glazing_ratio.txt")
pts_folder = os.path.join(intermediate_folder, f"solar_radiance_with_glazing_ratio/")
os.makedirs(pts_folder, exist_ok=True)

batch_folders = [folder for folder in os.listdir(pts_folder) 
                 if os.path.isdir(os.path.join(pts_folder, folder)) and folder.startswith('Rad')]

os.makedirs(os.path.dirname(points_path), exist_ok=True)

with open(points_path, 'w') as output_file:
    total_lines = 0
    for batch_folder_name in batch_folders:
        batch_folder = os.path.join(pts_folder, batch_folder_name)
        grids = os.path.join(batch_folder, "model/grid/")
        
        if not os.path.exists(grids):
            print(f"Grid directory not found: {grids}")
            continue
        
        for filename in os.listdir(grids):
            if filename.endswith('.pts'):
                fc_name = os.path.basename(filename).replace('.pts', '')
                file_path = os.path.join(grids, filename)
                try:
                    with open(file_path, 'r') as f:
                        for line in f:
                            if line.strip():
                                columns = line.strip().split()
                                if len(columns) >= 6:
                                    new_line = ",".join(columns[:6]) + f",{fc_name}\n"
                                    output_file.write(new_line)
                                    total_lines += 1
                                else:
                                    print(f"Skipping line in {filename}: {line.strip()} (less than 6 columns)")
                except Exception as e:
                    print(f"Error reading {file_path}: {e}")
                    continue

print(f"All .pts files have been merged into {points_path}")
print(f"Total non-empty lines with at least 6 columns: {total_lines}")