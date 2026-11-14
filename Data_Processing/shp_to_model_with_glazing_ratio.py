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
type_field = args.get('building_typology_field')
glaz_ratio_field = args.get('glazing_ratio_field')

projected_glazing = os.path.join(intermediate_folder, "footprint/projected_with_glazing_ratio.shp")
projected_standard = os.path.join(intermediate_folder, "footprint/projected.shp")

if os.path.exists(projected_glazing):
    projected_buildings = projected_glazing
    print(f"[VGS] Detection: Using glazing ratio shapefile for visualization: {projected_buildings}")
else:
    projected_buildings = projected_standard
    print(f"[VGS] Detection: Using standard shapefile for visualization: {projected_buildings}")

building_shp_projected = gpd.read_file(projected_buildings)

building_3dm_path = os.path.join(intermediate_folder, f"footprint/{city}_Buildings_temp.3dm")
optimized_3dm_path = os.path.join(intermediate_folder, f"footprint/{city}_Buildings_temp2.3dm")
output_path = os.path.join(intermediate_folder, f"footprint/{city}_with_glazing_ratio.3dm")
output_path_without_terrain = os.path.join(intermediate_folder, f"footprint/{city}_with_glazing_ratio_without_terrain.3dm")

terrain_path = os.path.join(intermediate_folder, f"DEM/{city}_terrain.3dm")
terrain_flag = str(args.get('terrain_flag')).lower() == 'true'

# Global variable for building attributes
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

    for idx, (geom, height, glaz_ratio, type_value, class_id, building_id) in enumerate(
        zip(building_shp_projected.geometry, building_shp_projected[height_field], building_shp_projected[glaz_ratio_field], building_shp_projected[type_field], building_shp_projected["Class_ID"], building_shp_projected["ID"])
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
        side_faces = []
        for i in range(n_points):
            i_next = (i + 1) % n_points
            side_faces.append([i, i_next, n_tri_vertices + i_next, n_tri_vertices + i])

        faces = base_faces + top_faces + side_faces

        try:
            rhino_mesh = rg.Mesh()
            for point in points:
                rhino_mesh.Vertices.Add(point[0], point[1], point[2])
            for face in faces:
                if len(face) == 3:
                    rhino_mesh.Faces.AddFace(int(face[0]), int(face[1]), int(face[2]))
                elif len(face) == 4:
                    rhino_mesh.Faces.AddFace(int(face[0]), int(face[1]), int(face[2]), int(face[3]))
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
            "id": int(building_id),
            "type_value": str(type_value),
            "glaz_ratio": float(glaz_ratio),
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

def load_optimized_buildings(building_path):
    """
    Loads optimized meshes from a 3DM file and verifies attribute correspondence.
    Returns: Tuple (list of rg.Mesh, list of corresponding indices in building_attributes)
    """
    building_file = Rhino.FileIO.File3dm.Read(building_path)
    building_geo = []
    if building_file:
        for obj in building_file.Objects:
            if isinstance(obj.Geometry, rg.Mesh):
                building_geo.append(obj.Geometry)
    
    global building_attributes
    if not building_geo:
        print("Failed to load optimized building geometry.")
        return [], []
        
    if len(building_geo) != len(building_attributes):
        print(f"Mismatch between number of meshes ({len(building_geo)}) and attributes ({len(building_attributes)}).")
        return [], [] 

    # Since the meshes were saved in shp_to_3dm, their order should match the attribute list
    indices = list(range(len(building_geo)))
    return building_geo, indices

def project_buildings_onto_terrain(building_geo, terrain_path):
    """
    Projects a list of building meshes onto the terrain found at terrain_path.
    Returns: Tuple (projected_meshes: list[rg.Mesh], terrain_geo: rg.Brep|rg.Mesh)
    """
    terrain_file = Rhino.FileIO.File3dm.Read(terrain_path)
    terrain_geo = None
    if terrain_file:
        for obj in terrain_file.Objects:
            if isinstance(obj.Geometry, (rg.Brep, rg.Mesh)):
                terrain_geo = obj.Geometry
                break

    if not terrain_geo:
        print("Failed to load terrain geometry. Skipping projection.")
        return [], None
    if not building_geo:
        print("No building geometry provided for projection.")
        return [], terrain_geo

    projected_buildings = []
    
    # We rely on the order of building_geo matching building_attributes globally
    for idx, geo in enumerate(building_geo):
        if isinstance(geo, rg.Mesh):
            # Get base vertices (Z=0) for projection
            base_vertices = [rg.Point3d(v.X, v.Y, v.Z) for v in geo.Vertices if abs(v.Z) < 0.001]
            if not base_vertices:
                continue

            # Project base vertices onto terrain and calculate Z differences
            z_differences = []
            for pt in base_vertices:
                closest_pt = terrain_geo.ClosestPoint(pt)
                if closest_pt:
                    z_diff = closest_pt.Z - pt.Z
                    z_differences.append(z_diff)

            if z_differences:
                # Select the maximum Z difference to ensure the building sits on the terrain
                max_z_diff = max(z_differences)
                translation_vector = rg.Vector3d(0, 0, max_z_diff)
                # Create a copy of the mesh
                new_mesh = geo.DuplicateMesh()
                new_mesh.Translate(translation_vector)
                projected_buildings.append(new_mesh)
    
    print(f"Number of buildings successfully projected: {len(projected_buildings)}")
    return projected_buildings, terrain_geo

def save_3dm_with_attributes(geometries, attributes_indices, output_path, terrain_geo=None):
    """
    Saves a list of geometries with associated attributes to a 3DM file.
    Optionally includes terrain geometry.
    """
    global building_attributes
    if not geometries:
        print(f"No geometries to save to: {output_path}")
        return False

    file_3dm = Rhino.FileIO.File3dm()
    file_3dm.Settings.ModelUnitSystem = Rhino.UnitSystem.Meters
    file_3dm.Settings.ModelAbsoluteTolerance = 1e-8

    for i, mesh in enumerate(geometries):
        attr_idx = attributes_indices[i]
        try:
            class_id = int(building_attributes[attr_idx]["class_id"])
            building_id = int(building_attributes[attr_idx]["id"])
            glaz_ratio = float(building_attributes[attr_idx]["glaz_ratio"])
            type_value = str(building_attributes[attr_idx]["type_value"])

            attributes = Rhino.DocObjects.ObjectAttributes()
            attributes.SetUserString("class_id", str(class_id))
            attributes.SetUserString("glaz_ratio", str(glaz_ratio))
            attributes.SetUserString("type_value", str(type_value))
            attributes.SetUserString("id", str(building_id))

            file_3dm.Objects.Add(mesh, attributes)
        except Exception as e:
            print(f"Failed to attach class_id/id to mesh {i}: {e}")
            continue

    if terrain_geo:
        file_3dm.Objects.AddMesh(terrain_geo)
        
    success = file_3dm.Write(output_path, 8)
    if success:
        print(f"File saved successfully to: {output_path}")
    else:
        print(f"Failed to save file to: {output_path}")
        
    return success

# Execute the initial geometry creation and optimization steps
shp_to_3dm()
merge_coplanar_faces(building_3dm_path, optimized_3dm_path, angle_tolerance_degrees=1.0)

# Load the optimized (but un-projected) buildings for saving
optimized_geo, indices = load_optimized_buildings(optimized_3dm_path)

if optimized_geo:
    # ALWAYS save the optimized buildings without terrain and without projection
    print("\nSaving buildings-only file (un-projected)...")
    save_3dm_with_attributes(optimized_geo, indices, output_path_without_terrain)
else:
    print("Skipping buildings-only save due to failed geometry loading or attribute mismatch.")

# Conditionally perform projection and save the final file with terrain
if terrain_flag and optimized_geo:
    print("\nStarting conditional terrain projection workflow...")
    
    # Perform projection (this only translates meshes, doesn't save)
    projected_buildings, terrain_geo = project_buildings_onto_terrain(
        optimized_geo, 
        terrain_path
    )
    
    if projected_buildings and terrain_geo:
        # Get the attribute indices again (they correspond to the original order)
        # Note: We reuse the indices from the optimized_geo load
        
        # Save projected buildings AND terrain to the final output path
        save_3dm_with_attributes(
            projected_buildings, 
            indices[:len(projected_buildings)], # Ensure indices match the number of projected meshes
            output_path, 
            terrain_geo=terrain_geo
        )
    else:
        print("Skipping final combined save because projection failed or terrain was missing.")

# Remove temporary files
if os.path.isfile(building_3dm_path):
    os.remove(building_3dm_path)
if os.path.isfile(optimized_3dm_path):
    os.remove(optimized_3dm_path)

print("Shapefile to 3DM conversion completed.")