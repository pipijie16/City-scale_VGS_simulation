import os
import subprocess
import math
import io
import torch
from tqdm import tqdm
import numpy as np
import sys

# Force UTF-8 encoding on standard streams to prevent Windows GBK crashes
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# Helper function to parse command-line arguments (key-value pairs)
def parse_args(args):
    arg_dict = {}
    for i in range(0, len(args), 2):
        key = args[i].strip('\'"')
        val = args[i+1].strip('\'"') if i + 1 < len(args) else None
        arg_dict[key] = val
    return arg_dict

def get_gpu_vram_gb(device):
    """Gets total GPU VRAM in GB for current CUDA device."""
    if device.type == 'cuda':
        try:
            total_memory_bytes = torch.cuda.get_device_properties(device).total_memory
            return total_memory_bytes / (1024**3)
        except Exception as e:
            print(f"Warning: Could not query GPU memory. Error: {e}")
            return 8.0
    return 0.0

args = parse_args(sys.argv[1:])

city = args.get('city_name')
gpu_flag = args.get('gpu_flag')
intermediate_folder = args.get('intermediate_folder')

# Determine execution device
device = torch.device('cuda' if torch.cuda.is_available() and str(gpu_flag).lower() == 'true' else 'cpu')

radiance_bin_dir = "C:/Radiance/bin/"
accelerad_bin_dir = "C:/Program Files/Accelerad/bin"

directory = os.path.join(intermediate_folder, "view_factors_radiance/")
folders = [d for d in os.listdir(directory) if os.path.isdir(os.path.join(directory, d))]

points_path = os.path.join(intermediate_folder, f"{city}_basic_data/{city}_Points.txt")

# Load and compute spatial center coordinates for relative transformation
points_data = np.loadtxt(points_path, delimiter=",", usecols=(0, 1, 2))
if points_data.ndim == 1:
    points_data = points_data.reshape(1, -1)

center_x, center_y, center_z = np.mean(points_data, axis=0)
print(f"Calculated center coordinates: X={center_x:.2f}, Y={center_y:.2f}, Z={center_z:.2f}")

if device.type == 'cuda':
    vram_gb = get_gpu_vram_gb(device)
    TARGET_POINTS_PER_BATCH = int(max(1000, (vram_gb / 8.0) * 2500))
    print(f"Using GPU: Target points per batch set to {TARGET_POINTS_PER_BATCH} (~{TARGET_POINTS_PER_BATCH * 144:,} rays)")
else:
    TARGET_POINTS_PER_BATCH = 500
    print(f"Using CPU: Target points per batch set to {TARGET_POINTS_PER_BATCH}")

center_coords_tensor = torch.tensor([center_x, center_y, center_z], dtype=torch.float32, device=device)

def generate_hemisphere_directions(samples=144):
    sqrt_samples = int(math.sqrt(samples))
    directions = []
    for i in range(sqrt_samples):
        for j in range(sqrt_samples):
            theta = math.acos(1 - (i + 0.5) / sqrt_samples)
            phi = 2 * math.pi * (j + 0.5) / sqrt_samples
            dx = math.sin(theta) * math.cos(phi)
            dy = math.sin(theta) * math.sin(phi)
            dz = math.cos(theta)
            directions.append([dx, dy, dz])
    return torch.tensor(directions, dtype=torch.float32, device=device)

hemisphere_directions = generate_hemisphere_directions(samples=144)

def rotate_vector(vec_gpu, axis_gpu, angle_gpu):
    cos_theta = torch.cos(angle_gpu)
    sin_theta = torch.sin(angle_gpu)
    cross_prod = torch.cross(axis_gpu, vec_gpu, dim=2)
    dot_prod = torch.sum(axis_gpu * vec_gpu, dim=2)
    return vec_gpu * cos_theta.unsqueeze(2) + cross_prod * sin_theta.unsqueeze(2) + axis_gpu * dot_prod.unsqueeze(2) * (1 - cos_theta.unsqueeze(2))

def transform_to_normal(directions_gpu, normal_gpu):
    normal_gpu = normal_gpu / normal_gpu.norm(dim=2, keepdim=True)
    z_axis = torch.tensor([0, 0, 1], dtype=torch.float32, device=device).view(1, 1, 3)
    z_axis = z_axis.expand(normal_gpu.size(0), directions_gpu.size(1), 3)

    rotation_axis_gpu = torch.cross(z_axis, normal_gpu, dim=2)
    norm_rotation_axis = torch.norm(rotation_axis_gpu, dim=2, keepdim=True)
    non_zero_mask = norm_rotation_axis > 1e-6

    rotation_axis_gpu = torch.where(non_zero_mask, rotation_axis_gpu / norm_rotation_axis, rotation_axis_gpu)
    angle_gpu = torch.acos(torch.sum(z_axis * normal_gpu, dim=2))

    directions_gpu = rotate_vector(directions_gpu, rotation_axis_gpu, angle_gpu)
    return directions_gpu

def generate_rays_fast(batch_coordinates_tensor, directions_tensor):
    """Generates rays using fast C-level memory buffer formatting."""
    batch_coordinates_expanded = batch_coordinates_tensor.unsqueeze(1).expand(-1, directions_tensor.size(1), -1)
    rays_tensor = torch.cat((batch_coordinates_expanded, directions_tensor), dim=2)
    rays_np = rays_tensor.reshape(-1, 6).cpu().numpy()

    buf = io.BytesIO()
    np.savetxt(buf, rays_np, fmt="%.4f", delimiter=" ")
    return buf.getvalue().decode('ascii')

def process_pts_files(folder, output_dir, scene_file):
    pts_dir = os.path.join(directory, f"{folder}/model/grid/")
    if not os.path.exists(pts_dir):
        pts_dir = os.path.join(directory, f"{folder}/grid/")

    pts_files = [f for f in os.listdir(pts_dir) if f.endswith(".pts")]
    if not pts_files:
        return

    # 1. Pre-scan file point counts in memory (eliminates double disk reads!)
    file_point_info = []
    for f in pts_files:
        p_path = os.path.join(pts_dir, f)
        pts_list = []
        with open(p_path, 'r', encoding='utf-8', errors='ignore') as fp:
            for line in fp:
                line_str = line.strip()
                if line_str:
                    pts_list.append([float(x) for x in line_str.split()[:6]])
        file_point_info.append((f, pts_list))

    # 2. Dynamic Point-based Batching: group files until target point count threshold is met
    batches = []
    cur_files = []
    cur_pts_data = []
    cur_pts_count = 0

    for f_name, p_data in file_point_info:
        count = len(p_data)
        if count == 0:
            continue

        if cur_pts_count + count > TARGET_POINTS_PER_BATCH and cur_files:
            batches.append((cur_files, cur_pts_data))
            cur_files = [f_name]
            cur_pts_data = [p_data]
            cur_pts_count = count
        else:
            cur_files.append(f_name)
            cur_pts_data.append(p_data)
            cur_pts_count += count

    if cur_files:
        batches.append((cur_files, cur_pts_data))

    total_batches = len(batches)
    print(f"[{folder}] Re-chunked into {total_batches} optimized batches (Previously ~{math.ceil(len(pts_files)/24)} batches).")

    # Command configuration
    if device.type == 'cuda':
        rtrace_bin = os.path.join(accelerad_bin_dir, "accelerad_rtrace.exe")
    else:
        rtrace_bin = os.path.join(radiance_bin_dir, "rtrace.exe")

    rtrace_cmd = f'"{rtrace_bin}" -h -aa 0 -ab 0 "{scene_file}"'

    # 3. Process each packed batch
    for batch_idx, (batch_files, batch_pts_list) in enumerate(tqdm(batches, desc=f"Raytracing {folder}", unit="batch")):
        counts_per_file = [len(p) for p in batch_pts_list]
        total_batch_points = sum(counts_per_file)

        # Flatten into unified PyTorch tensor on target device
        flat_points = [p for sublist in batch_pts_list for p in sublist]
        points_tensor = torch.tensor(flat_points, dtype=torch.float32, device=device)

        coordinates = points_tensor[:, :3] - center_coords_tensor
        normals = points_tensor[:, 3:]

        # Map each point to its 144 rays
        num_samples = hemisphere_directions.size(0)
        point_mappings = torch.arange(total_batch_points, dtype=torch.int64, device=device).repeat_interleave(num_samples)

        directions = transform_to_normal(
            hemisphere_directions.unsqueeze(0).expand(total_batch_points, -1, -1),
            normals.unsqueeze(1).expand(-1, num_samples, -1)
        )

        rays_input_str = generate_rays_fast(coordinates, directions)

        if device.type == 'cuda':
            torch.cuda.empty_cache()

        result = subprocess.run(
            rtrace_cmd, 
            input=rays_input_str, 
            text=True, 
            capture_output=True, 
            shell=True
        )

        if result.returncode != 0:
            print(f"Error executing rtrace command: {result.stderr}", file=sys.stderr)
            sys.exit(1)

        output_lines = result.stdout.strip().splitlines()
        num_rays = total_batch_points * num_samples

        # Vectorized hit detection
        hits = np.fromiter(
            (1 if (l and not l.startswith("0.000000e+000")) else 0 for l in output_lines),
            dtype=np.int32,
            count=len(output_lines)
        )

        hit_counts = torch.zeros(num_rays, dtype=torch.int32, device=device)
        output_len = min(len(hits), num_rays)
        hit_counts[:output_len] = torch.from_numpy(hits[:output_len]).to(device)

        # Aggregate hits per point
        hit_counts_for_point = torch.zeros(total_batch_points, dtype=torch.int32, device=device)
        hit_counts_for_point.index_add_(0, point_mappings, hit_counts)

        # Calculate BVF
        bvf = (hit_counts_for_point.float() / float(num_samples)).cpu().numpy()

        # 4. Write back results directly from memory slices (Zero disk re-reads!)
        idx_start = 0
        for f_name, num_p in zip(batch_files, counts_per_file):
            output_file = os.path.join(output_dir, f_name.replace('.pts', '_BVF.txt'))
            bvf_slice = bvf[idx_start:idx_start + num_p]

            with open(output_file, 'w', encoding='utf-8') as out_f:
                out_f.write("\n".join(f"{val:.6f}" for val in bvf_slice) + "\n")

            idx_start += num_p

        if device.type == 'cuda':
            torch.cuda.empty_cache()

def process_folder(folder):
    parallel_dir = os.path.join(directory, f"{folder}/model/scene/")
    scene_file = os.path.join(parallel_dir, "scene.oct")
    mat_file = os.path.join(parallel_dir, "envelope.mat")
    rad_file = os.path.join(parallel_dir, "envelope.rad")
    transformed_rad_file = os.path.join(parallel_dir, "transformed.rad")
    sky_rad = os.path.join(parallel_dir, "sky.rad")
    output_dir = os.path.join(intermediate_folder, f"BVF/results/{folder}/")

    os.makedirs(output_dir, exist_ok=True)

    gendaylit_cmd = f'"{os.path.join(radiance_bin_dir, "gendaylit")}" 6 21 12 -W 700 25 > "{sky_rad}"'
    subprocess.run(gendaylit_cmd, shell=True, check=True)

    trans_x = -center_x
    trans_y = -center_y
    trans_z = -center_z

    print(f"Generating scene file for {folder}...")
    transform_cmd = f'"{os.path.join(radiance_bin_dir, "xform")}" -t {trans_x} {trans_y} {trans_z} "{rad_file}" > "{transformed_rad_file}"'
    subprocess.run(transform_cmd, shell=True, check=True)

    oconv_cmd = f'"{os.path.join(radiance_bin_dir, "oconv")}" "{sky_rad}" "{mat_file}" "{transformed_rad_file}" > "{scene_file}"'
    subprocess.run(oconv_cmd, shell=True, check=True)
    print(f"Complete: scene.oct for {folder}")

    process_pts_files(folder, output_dir, scene_file)

def main():
    if not folders:
        print("Warning: No folders found to process.")
        return
        
    for folder in tqdm(folders, desc="Processing folders", unit="folder"):
        process_folder(folder)
    print("Done BVF computation.")

if __name__ == "__main__":
    main()