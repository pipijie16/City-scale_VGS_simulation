import sys
import os

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

import rhinoinside
rhinoinside.load()
import Rhino
import Rhino.Geometry as rg
import numpy as np

city = args.get('city_name')
intermediate_folder = args.get('intermediate_folder')

path = os.path.join(intermediate_folder, f"footprint/{city}_without_terrain.3dm")

output_dir = os.path.join(intermediate_folder, "partitioned_models/")

os.makedirs(output_dir, exist_ok=True)

file_3dm = Rhino.FileIO.File3dm.Read(path)
meshes = [obj for obj in file_3dm.Objects if isinstance(obj.Geometry, rg.Mesh)]
geometries = []
attributes = []
for obj in meshes:
    if isinstance(obj.Geometry, rg.Mesh):
        geometries.append(obj.Geometry)
        attributes.append(obj.Attributes)

num_buildings = len(meshes)
if num_buildings > 4000:
    min_points_per_cluster = 2000
    max_points_per_cluster = 2100

    # Extract centroids (x, y coordinates only)
    centroids = []
    for mesh in meshes:
        vertices = np.array([[v.X, v.Y] for v in mesh.Geometry.Vertices])
        centroid = np.mean(vertices, axis=0)
        centroids.append(centroid)

    centroids = np.array(centroids)
    num_points = len(centroids)

    remaining_indices = set(range(num_points))
    clusters = []

    # Region growing clustering with strict spatial contiguity
    while len(remaining_indices) >= min_points_per_cluster:
        seed = remaining_indices.pop()
        current_cluster = [seed]
        # Expand the cluster by always adding the nearest unclustered point to the last added point
        while len(current_cluster) < max_points_per_cluster and remaining_indices:
            last_point = current_cluster[-1]
            candidate_indices = np.array(list(remaining_indices))
            dists = np.linalg.norm(centroids[candidate_indices] - centroids[last_point], axis=1)
            nearest_idx_in_candidates = np.argmin(dists)
            nearest_point_global = candidate_indices[nearest_idx_in_candidates]
            current_cluster.append(nearest_point_global)
            remaining_indices.remove(nearest_point_global)
        clusters.append(current_cluster)

    # Merge remaining points (less than min_points_per_cluster) to the nearest cluster
    if remaining_indices:
        rest = list(remaining_indices)
        if len(rest) > 500:
            clusters.append(rest)  # Form a new cluster with all remaining points
        else:
            cluster_centers = [np.mean(centroids[c], axis=0) for c in clusters]
            for idx in rest:
                dists = [np.linalg.norm(centroids[idx] - center) for center in cluster_centers]
                nearest_cluster = np.argmin(dists)
                clusters[nearest_cluster].append(idx)
else:
    print(f"Building count ({num_buildings}) <= 4000, saving as single part.")
    clusters = [list(range(num_buildings))]

# Save each cluster as a separate .3dm file
os.makedirs(output_dir, exist_ok=True)
num_valid_clusters = 0
cluster_sizes = []
for i, cluster in enumerate(clusters):
    part_model = Rhino.FileIO.File3dm()
    part_model.Settings.ModelUnitSystem = Rhino.UnitSystem.Meters
    part_model.Settings.ModelAbsoluteTolerance = 1e-6
    for idx in cluster:
        if idx < len(meshes):
            part_model.Objects.Add(geometries[idx], attributes[idx])
    output_path = f"{output_dir}{city}_part{i+1}.3dm"
    success = part_model.Write(output_path, 8)
    if success:
        print(f"Saved: {output_path}")
        num_valid_clusters += 1
        cluster_sizes.append(len(cluster))
    else:
        print(f"Failed to save: {output_path}")

print(f"Number of valid clusters: {num_valid_clusters}")
print(f"Cluster sizes: {cluster_sizes}")
print("Completed clustering.")