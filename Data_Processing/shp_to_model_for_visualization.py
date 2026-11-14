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
import triangle
import geopandas as gpd
from shapely.geometry import Polygon

# File paths
city = args.get('city_name')
intermediate_folder = args.get('intermediate_folder')
height_field = args.get('height_field')

footprint_dir = os.path.join(intermediate_folder, "footprint")
os.makedirs(footprint_dir, exist_ok=True)

projected_glazing = os.path.join(intermediate_folder, "footprint/projected_with_glazing_ratio.shp")
projected_standard = os.path.join(intermediate_folder, "footprint/projected.shp")

if os.path.exists(projected_glazing):
    projected_buildings = projected_glazing
    print(f"[VGS] Detection: Using glazing ratio shapefile for visualization: {projected_buildings}")
else:
    projected_buildings = projected_standard
    print(f"[VGS] Detection: Using standard shapefile for visualization: {projected_buildings}")

building_shp_projected = gpd.read_file(projected_buildings)

building_3dm_path = os.path.join(footprint_dir, f"{city}_Buildings_temp.3dm")
optimized_3dm_path = os.path.join(footprint_dir, f"{city}_Buildings_temp2.3dm")
output_path_without_terrain = os.path.join(footprint_dir, f"{city}_3D_city_models_visualization.3dm")

building_attributes = []

def shp_to_3dm():
    """
    Convert shapefile polygons to 3DM file, saving each polygon as an independent mesh.
    """
    global building_shp_projected
    if building_shp_projected is None:
        return False

    global building_attributes
    building_attributes = []

    rhino_meshes = []
    skipped_count = 0
    processed_count = 0

    for idx, (geom, height, class_id, building_id) in enumerate(
        zip(building_shp_projected.geometry, building_shp_projected[height_field], building_shp_projected["Class_ID"], building_shp_projected["ID"])
    ):
        if geom is None or geom.is_empty or geom.geom_type != "Polygon":
            skipped_count += 1
            continue
        
        coords = list(geom.exterior.coords)[:-1]
        if len(coords) < 3:
            skipped_count += 1
            continue

        try:
            poly = Polygon(coords)
            if not poly.is_valid:
                poly = poly.buffer(0)
                if not poly.is_valid or poly.is_empty:
                    skipped_count += 1
                    continue
                coords = list(poly.exterior.coords)[:-1]
        except Exception:
            skipped_count += 1
            continue

        try:
            height = float(height)
            if height <= 0:
                skipped_count += 1
                continue
        except (ValueError, TypeError):
            skipped_count += 1
            continue

        base_points = np.array([[x, y, 0.0] for x, y in coords], dtype=np.float64)
        n_points = len(base_points)

        try:
            vertices = base_points[:, :2]
            tri_input = {
                'vertices': vertices,
                'segments': [[i, (i + 1) % n_points] for i in range(n_points)]
            }
            tri = triangle.triangulate(tri_input, 'p')
            if 'triangles' not in tri or 'vertices' not in tri:
                skipped_count += 1
                continue
            tri_vertices = np.hstack([tri['vertices'], np.zeros((len(tri['vertices']), 1))])
            tri_faces = tri['triangles']
        except Exception:
            skipped_count += 1
            continue

        top_vertices = tri_vertices.copy()
        top_vertices[:, 2] = height
        points = np.vstack([tri_vertices, top_vertices])
        n_tri_vertices = len(tri_vertices)
        base_faces = tri_faces.tolist()
        top_faces = [[i + n_tri_vertices, j + n_tri_vertices, k + n_tri_vertices] for i, j, k in reversed(tri_faces)]
        
        # Create side faces as triangles (split quads into triangles)
        side_faces = []
        for i in range(n_points):
            i_next = (i + 1) % n_points
            # First triangle
            side_faces.append([i, i_next, n_tri_vertices + i_next])
            # Second triangle
            side_faces.append([i, n_tri_vertices + i_next, n_tri_vertices + i])

        # Combine faces (all are triangles)
        faces = base_faces + top_faces + side_faces

        # Create Rhino mesh
        try:
            rhino_mesh = rg.Mesh()
            # Add vertices
            for point in points:
                # Map obj Y to Rhino Z
                rhino_mesh.Vertices.Add(point[0], point[1], point[2])
            # Add faces (all are triangles)
            for face in faces:
                rhino_mesh.Faces.AddFace(int(face[0]), int(face[1]), int(face[2]))
        
            rhino_mesh.Normals.ComputeNormals()
            rhino_mesh.UnifyNormals()
            rhino_mesh.Compact()
            rhino_mesh.Weld(0.001)
            rhino_mesh.FillHoles()
        except Exception:
            skipped_count += 1
            continue

        rhino_meshes.append(rhino_mesh)
        building_attributes.append({
            "index": idx,
            "height": height,
            "class_id": int(class_id),
            "id": int(building_id)
        })
        processed_count += 1

    print(f"Processed {processed_count} polygons, skipped {skipped_count} polygons")

    if not rhino_meshes:
        print("No valid meshes generated! Check shapefile data.")
        return False

    try:
        model = Rhino.FileIO.File3dm()
        model.Settings.ModelUnitSystem = Rhino.UnitSystem.Meters
        model.Settings.ModelAbsoluteTolerance = 1e-8
        for mesh in rhino_meshes:
            model.Objects.AddMesh(mesh)
        model.Write(building_3dm_path, 8)
        print(f"3DM file saved to: {building_3dm_path}")
        return True
    except Exception as e:
        print(f"Failed to save 3DM file: {e}")
        return False

def merge_coplanar_faces(input_3dm_path, output_3dm_path, angle_tolerance_degrees=1.0):
    """
    Merges coplanar faces in all meshes of a 3DM file.
    """
    file_3dm = Rhino.FileIO.File3dm.Read(input_3dm_path)
    if not file_3dm:
        print(f"Failed to load 3DM file: {input_3dm_path}")
        return False

    meshes = [obj.Geometry for obj in file_3dm.Objects if isinstance(obj.Geometry, rg.Mesh)]

    if not meshes:
        print("No meshes found in 3DM file.")
        return False

    global building_attributes
    if len(meshes) != len(building_attributes):
        print(f"Mismatch between number of meshes ({len(meshes)}) and attributes ({len(building_attributes)}).")
        return False

    angle_tolerance_radians = angle_tolerance_degrees * (3.14159265359 / 180.0)
    for idx, mesh in enumerate(meshes):
        try:
            mesh.MergeAllCoplanarFaces(angle_tolerance_radians)
        except Exception as e:
            print(f"Failed to merge coplanar faces for mesh {idx}: {e}")
            continue

    try:
        file_3dm = Rhino.FileIO.File3dm()
        file_3dm.Settings.ModelUnitSystem = Rhino.UnitSystem.Meters
        file_3dm.Settings.ModelAbsoluteTolerance = 1e-8
        for mesh in meshes:
            file_3dm.Objects.AddMesh(mesh)
        file_3dm.Write(output_3dm_path, 8)
        print(f"3DM file saved to: {output_3dm_path}")
        return True
    except Exception as e:
        print(f"Failed to save 3DM file: {e}")
        return False

def save_3dm(building_path, output_path):
    """
    Projects buildings onto terrain and saves the result, attaching class_id attributes.
    """
    # Load building geometry from 3DM
    building_file = Rhino.FileIO.File3dm.Read(building_path)
    building_geo = []
    if building_file:
        for obj in building_file.Objects:
            if isinstance(obj.Geometry, rg.Mesh):
                building_geo.append(obj.Geometry)
    print(f"Number of meshes in building_geo: {len(building_geo)}")

    if building_geo:
        # Attach class_id from building_attributes
        file_3dm = Rhino.FileIO.File3dm()
        file_3dm.Settings.ModelUnitSystem = Rhino.UnitSystem.Meters
        file_3dm.Settings.ModelAbsoluteTolerance = 1e-8
        for mesh in building_geo:
            file_3dm.Objects.AddMesh(mesh)

        success = file_3dm.Write(output_path, 8)
        if success:
            print(f"Projected buildings and terrain saved to: {output_path}")
        else:
            print(f"Failed to save projected buildings and terrain to: {output_path}")
        return success
    else:
        print("No buildings were successfully projected.")
        return False

# Execute the initial geometry creation and optimization steps
shp_to_3dm()
merge_coplanar_faces(building_3dm_path, optimized_3dm_path, angle_tolerance_degrees=1.0)
save_3dm(optimized_3dm_path, output_path_without_terrain)

# Remove temporary files
if os.path.isfile(building_3dm_path):
    os.remove(building_3dm_path)
if os.path.isfile(optimized_3dm_path):
    os.remove(optimized_3dm_path)

print("Shapefile to 3DM conversion for visualization completed.")