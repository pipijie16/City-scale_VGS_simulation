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
import ladybug_rhino
from honeybee.face import Face
from honeybee.model import Model
from honeybee.facetype import Wall
from honeybee_radiance.sensorgrid import SensorGrid
from ladybug_geometry.geometry3d.pointvector import Point3D
from ladybug_rhino.fromgeometry import from_point3d
from ladybug_rhino.togeometry import to_face3d

from Rhino.Geometry import Mesh

try:  # use try/except so that the code is still usable without RhinoCommon
    import Rhino.Geometry.Mesh as rhm
    import Rhino.Geometry.MeshingParameters as mp
    meshing_parameters = mp.FastRenderMesh
except ImportError:
    rhm, meshing_parameters = None, None

city = args.get('city_name')
intermediate_folder = args.get('intermediate_folder')

directory = os.path.join(intermediate_folder, "partitioned_models_with_glazing_ratio/")
os.makedirs(directory, exist_ok=True)

files = [f for f in os.listdir(directory) if f.endswith(".3dm")]

terrain_flag = str(args.get('terrain_flag')).lower() == 'true'

if terrain_flag:
    shade_mesh_directory = os.path.join(intermediate_folder, f"footprint/{city}_with_glazing_ratio.3dm")
    terrain_brep_directory = os.path.join(intermediate_folder, f"DEM/{city}_terrain.3dm")
else:
    shade_mesh_directory = os.path.join(intermediate_folder, f"footprint/{city}_with_glazing_ratio_without_terrain.3dm")

def getBuildingGeo(path):
    all_geo = []
    attributes = []
    file_3dm = Rhino.FileIO.File3dm.Read(path)
    if file_3dm:
        for obj in file_3dm.Objects:
            all_geo.append(obj.Geometry)
            attributes.append(obj.Attributes)
    return all_geo, attributes

def getGeo(path):
    all_geo = []
    file_3dm = Rhino.FileIO.File3dm.Read(path)
    if file_3dm:
        for obj in file_3dm.Objects:
            all_geo.append(obj.Geometry)
    return all_geo

def is_mesh_within_buffer(mesh, buffer_curve, z):
    mesh_bounding_box = mesh.GetBoundingBox(True)
    center = mesh_bounding_box.Center
    center_point = Rhino.Geometry.Point3d(center.X, center.Y, z)
    if buffer_curve.Contains(center_point) == Rhino.Geometry.PointContainment.Inside:
        return True
    return False

def create_buffer_zone(center_point, radius):
    circle = Rhino.Geometry.Circle(center_point, radius)
    return circle.ToNurbsCurve()

def get_hb_faces_bounding_boxes(meshes):
    bounding_box = Rhino.Geometry.BoundingBox.Empty
    for mesh in meshes:
        bounding_box.Union(mesh.GetBoundingBox(True))
    return bounding_box

def clip_mesh(mesh, center, radius):
    min_x, max_x = center.X - radius, center.X + radius
    min_y, max_y = center.Y - radius, center.Y + radius
    
    clipped_mesh = Mesh()
    vertex_map = {}
    
    for face_index in range(mesh.Faces.Count):
        face = mesh.Faces[face_index]
        
        vertices = [
            mesh.Vertices[face.A],
            mesh.Vertices[face.B],
            mesh.Vertices[face.C],
            mesh.Vertices[face.D] if face.IsQuad else None
        ]
        
        vertices_inside = [
            (min_x <= v.X <= max_x and min_y <= v.Y <= max_y) for v in vertices if v is not None
        ]
        
        if any(vertices_inside):
            indices = []
            for i, v in enumerate(vertices):
                if v is not None:
                    vertex_key = (v.X, v.Y, v.Z)
                    if vertex_key not in vertex_map:
                        new_index = clipped_mesh.Vertices.Add(v)
                        vertex_map[vertex_key] = new_index
                    indices.append(vertex_map[vertex_key])
            
            if len(indices) == 3:
                clipped_mesh.Faces.AddFace(indices[0], indices[1], indices[2])
            elif len(indices) == 4:
                clipped_mesh.Faces.AddFace(indices[0], indices[1], indices[2], indices[3])

    clipped_mesh.Normals.ComputeNormals()
    clipped_mesh.UnifyNormals()
    clipped_mesh.Weld(0.001)
    clipped_mesh.Compact()

    if clipped_mesh.Faces.Count == 0:
        print("No mesh faces inside clipping range.")
        return None
    
    print(f"Clipped mesh contains {clipped_mesh.Faces.Count} faces and {clipped_mesh.Vertices.Count} vertices.")
    return clipped_mesh

shade_mesh = getGeo(shade_mesh_directory)

terrain_brep = None
if terrain_flag and os.path.exists(terrain_brep_directory):
    terrain_brep = getGeo(terrain_brep_directory)

file_count = 1

for file in files:
    filepath = os.path.join(directory, f"{city}_part{file_count}.3dm")
    building_geo, attributes = getBuildingGeo(filepath)

    def create_honeybee_faces(meshes):
        hb_faces = []
        face_count = 1
        face_mappings = []
        for mesh_idx, mesh in enumerate(meshes):
            hb_face = ladybug_rhino.togeometry.to_face3d(mesh)
            for lb_face in hb_face:
                face_name = "Face_" + str(file_count) + "_" + str(face_count)
                face = Face(face_name, lb_face)
                hb_faces.append(face)
                face_mappings.append((face, mesh_idx))
                face_count = face_count + 1
        return hb_faces, face_mappings

    hb_faces, face_mappings = create_honeybee_faces(building_geo)

    bounding_box = get_hb_faces_bounding_boxes(building_geo)

    bounding_box_center = bounding_box.Center

    point = Point3D(bounding_box_center.X, bounding_box_center.Y, bounding_box_center.Z)
    Point3d = from_point3d(point)

    def create_honeybee_model(surrounding_faces):
        model_name = "Model_1"
        model = Model(model_name, rooms=None, orphaned_faces=surrounding_faces, shade_meshes=None)
        return model
    
    # Set the radius of buffer as 1000 meters longer than the distance between the center and the vertex of bounding box
    distance_to_vertex = Rhino.Geometry.Point3d.DistanceTo(bounding_box_center, bounding_box.Min)
    radius = distance_to_vertex + 1000

    buffer_zone = create_buffer_zone(Point3d, radius)
    
    surrounding_meshes = [m for m in shade_mesh if is_mesh_within_buffer(m, buffer_zone, bounding_box_center.Z)]
    surrounding_faces, _ = create_honeybee_faces(surrounding_meshes)

    surrounding_bbox = get_hb_faces_bounding_boxes(surrounding_meshes)

    surrounding_faces.extend(hb_faces)

    if terrain_flag and terrain_brep and len(terrain_brep) > 0:
        terrain_brep_clipped = clip_mesh(terrain_brep[0], Point3d, radius)

        # Check if clipping produced a valid mesh (not None)
        if terrain_brep_clipped is not None:
            def create_terrain_faces(mesh_geo):
                if mesh_geo is None:
                    return []
                hb_faces = []
                face_count = 1
                hb_face = ladybug_rhino.togeometry.to_face3d(mesh_geo)
                if hb_face:
                    for lb_face in hb_face:
                        face_name = "Face_" + str(file_count) + "_" + str(face_count)
                        face = Face(face_name, lb_face)
                        hb_faces.append(face)
                        face_count = face_count + 1
                return hb_faces

            terrain_faces = create_terrain_faces(terrain_brep_clipped)
            surrounding_faces.extend(terrain_faces)
            print(f"Added {len(terrain_faces)} terrain faces to part {file_count}.")
        else:
            print(f"Notice: Part {file_count} has no overlapping terrain within buffer range. Skipping terrain for this partition.")

    hb_model = create_honeybee_model(surrounding_faces)

    def create_analysis_grid(hb_faces, face_mappings, grid_size, offset):
        """
        Creates sensor grids for radiance analysis based on wall faces, using glaz_ratio from Mesh UserDictionary.
        """
        faces = [obj for obj in hb_faces if isinstance(obj.type, Wall)]
        if not faces:
            print("No wall faces found for sensor grid creation.")
            return []

        # Create a mapping from Face to its source Mesh
        
        grid_counter = 1
        sensor_grids = []

        f_geos = [face.geometry for face in faces]
    
        for face, geo in zip(faces, f_geos):
            # Retrieve glaz_ratio from Mesh's UserString
            matching_mappings = [m for m in face_mappings if m[0] == face]
            original_idx = matching_mappings[0][1]
            glaz_ratio = float(attributes[original_idx].GetUserString("glaz_ratio"))
            class_id = int(attributes[original_idx].GetUserString("Class_ID"))
            building_id = int(attributes[original_idx].GetUserString("ID"))

            try:
                lb_mesh = geo.mesh_grid(x_dim=grid_size, y_dim=grid_size, offset=offset)
            except Exception as e:
                print(f"The face {face} is too small, skipping.")
                continue

            base_poss = [(pt.x, pt.y, pt.z) for pt in lb_mesh.face_centroids]
            base_dirs = [(vec.x, vec.y, vec.z) for vec in lb_mesh.face_normals]
            sensor_name = "Sensor_" + str(file_count) + "_" + str(grid_counter)+ "_" + str(building_id) + "_" + str(class_id)
            grid = SensorGrid.from_position_and_direction(sensor_name, base_poss, base_dirs)
            grid.mesh = lb_mesh
            
            if grid:
                positions = [(s.pos[0], s.pos[1], s.pos[2]) for s in grid.sensors]
                directions = [(s.dir[0], s.dir[1], s.dir[2]) for s in grid.sensors]
                
                strips = []
                current_strip_positions = []
                current_strip_directions = []
                current_xy = None

                for i, (pos, dir) in enumerate(zip(positions, directions)):
                    xy = (pos[0], pos[1])
                    if i == 0:
                        current_xy = xy
                        current_strip_positions.append(pos)
                        current_strip_directions.append(dir)
                    elif xy == current_xy:
                        current_strip_positions.append(pos)
                        current_strip_directions.append(dir)
                    else:
                        strips.append((current_strip_positions, current_strip_directions))
                        current_strip_positions = [pos]
                        current_strip_directions = [dir]
                        current_xy = xy

                if current_strip_positions:
                    strips.append((current_strip_positions, current_strip_directions))

                total_strips = len(strips)
                greening_ratio = 1 - glaz_ratio
                num_strips_to_keep = int(total_strips * greening_ratio)
                if num_strips_to_keep < 1:
                    num_strips_to_keep = 1 

                if total_strips > 1:
                    step = total_strips / num_strips_to_keep
                    indices_to_keep = [int(i * step) for i in range(num_strips_to_keep)]
                    indices_to_keep = [i for i in indices_to_keep if i < total_strips]
                else:
                    indices_to_keep = [0]

                kept_strips = [strips[i] for i in indices_to_keep]

                kept_positions = []
                kept_directions = []
                for strip_positions, strip_directions in kept_strips:
                    kept_positions.extend(strip_positions)
                    kept_directions.extend(strip_directions)
                                    
                new_grid = SensorGrid.from_position_and_direction(sensor_name, kept_positions, kept_directions)
                sensor_grids.append(new_grid)
                
                grid_counter += 1

        return sensor_grids
    
    grid_size = float(args.get('grid_size'))
    offset = 0.2
    sensor_grids = create_analysis_grid(hb_faces, face_mappings, grid_size, offset)

    output_folder = os.path.join(intermediate_folder, f"solar_radiance_with_glazing_ratio/Rad{file_count}/")
    os.makedirs(output_folder, exist_ok=True)

    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    another_model = hb_model.duplicate()
    another_model.properties.radiance.add_sensor_grids(sensor_grids)
    another_model.to.rad_folder(another_model, output_folder, minimal=False)

    file_count = file_count + 1

print("Completed generating Radiance files for solar analysis.")