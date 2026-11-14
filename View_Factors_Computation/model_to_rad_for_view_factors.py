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

try:  # use try/except so that the code is still usable without RhinoCommon
    import Rhino.Geometry.Mesh as rhm
    import Rhino.Geometry.MeshingParameters as mp
    meshing_parameters = mp.FastRenderMesh
except ImportError:
    rhm, meshing_parameters = None, None

city = args.get('city_name')
intermediate_folder = args.get('intermediate_folder')

directory = os.path.join(intermediate_folder, "partitioned_models/")
os.makedirs(directory, exist_ok=True)

files = [f for f in os.listdir(directory) if f.endswith(".3dm")]

terrain_flag = str(args.get('terrain_flag')).lower() == 'true'

if terrain_flag:
    shade_mesh_directory = os.path.join(intermediate_folder, f"footprint/{city}.3dm")
else:
    shade_mesh_directory = os.path.join(intermediate_folder, f"footprint/{city}_without_terrain.3dm")

all_geo = []

another_models = []

def getGeo(path):
    file_3dm = Rhino.FileIO.File3dm.Read(path)
    if file_3dm:
        for obj in file_3dm.Objects:
            geo = obj.Geometry
            all_geo.append(geo)
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

shade_mesh = getGeo(shade_mesh_directory)

file_count = 1

for file in files:
    all_geo = []
    filepath = os.path.join(directory, f"{city}_part{file_count}.3dm")
    all_geo = getGeo(filepath)

    def create_honeybee_faces(breps):
        hb_faces = []
        face_count = 1
        for brep in breps:
            hb_face = ladybug_rhino.togeometry.to_face3d(brep)
            for lb_face in hb_face:
                face_name = "Face_" + str(file_count) + "_" + str(face_count)
                face = Face(face_name, lb_face)
                hb_faces.append(face)
                face_count = face_count + 1
        return hb_faces

    hb_faces = create_honeybee_faces(all_geo)

    bounding_box = get_hb_faces_bounding_boxes(all_geo)

    bounding_box_center = bounding_box.Center

    point = Point3D(bounding_box_center.X, bounding_box_center.Y, bounding_box_center.Z)
    Point3d = from_point3d(point)

    def create_honeybee_model(surrounding_faces):
        model_name = "Model_1"
        model = Model(model_name, rooms=None, orphaned_faces = surrounding_faces, shade_meshes=None)
        return model
    
    # Set the radius of buffer as 100 meters longer than the distance between the center and the vertex of bounding box
    distance_to_vertex = Rhino.Geometry.Point3d.DistanceTo(bounding_box_center, bounding_box.Min)
    radius = distance_to_vertex + 100

    buffer_zone = create_buffer_zone(Point3d, radius)
    
    surrounding_meshes = [m for m in shade_mesh if is_mesh_within_buffer(m, buffer_zone, bounding_box_center.Z)]

    surrounding_faces = create_honeybee_faces(surrounding_meshes)

    surrounding_faces.extend(hb_faces)

    hb_model = create_honeybee_model(surrounding_faces)

    def create_analysis_grid(hb_faces, grid_size, offset): 
        grids = []
        faces = []
        for obj in hb_faces:
            if isinstance(obj.type, Wall):
                faces.append(obj)

        if len(faces) != 0:
            # create the gridded ladybug Mesh3D
            f_geos = [face.geometry for face in faces]
            
            for geo in f_geos:
                try:
                    lb_mesh = geo.mesh_grid(x_dim=grid_size, y_dim=grid_size, offset=offset)
                except Exception as e:
                    print(f"The face {geo} is too small, skipping.")
                    continue
                
                # extract positions and directions from the mesh
                base_poss = [(pt.x, pt.y, pt.z) for pt in lb_mesh.face_centroids]
                base_dirs = [(vec.x, vec.y, vec.z) for vec in lb_mesh.face_normals]
                
                sensor_name = "Sensor_" + str(file_count) + "_" + str(len(grids) + 1)
                grid = SensorGrid.from_position_and_direction(sensor_name, base_poss, base_dirs)
                grid.mesh = lb_mesh
                
                grids.append(grid)
        return grids
    
    grid_size = float(args.get('grid_size'))
    offset = 0.2
    sensor_grids = create_analysis_grid(hb_faces,grid_size,offset)

    output_folder = os.path.join(intermediate_folder, f"view_factors_radiance/Rad{file_count}/")
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)

    another_model = hb_model.duplicate()
    another_model.properties.radiance.add_sensor_grids(sensor_grids)
    another_model.to.rad_folder(another_model, output_folder, minimal=False)

    file_count = file_count + 1

print("Completed generating Radiance files for all parts.")