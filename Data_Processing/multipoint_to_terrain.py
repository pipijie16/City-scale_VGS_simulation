import sys
import os
import numpy as np
import open3d as o3d 
import ezdxf
import gc
import clr
from shlex import quote as q

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

# Initialize Rhino Inside
import rhinoinside
rhinoinside.load()
import Rhino
import Rhino.FileIO as FileIO
import Rhino.Geometry as rg

city = args.get('city_name')
intermediate_folder = args.get('intermediate_folder')

# Setup Input and Output paths
dem_output_dir = os.path.join(intermediate_folder, "DEM")
# The previous script (DEM_to_Multipoint.py) saves the DXF here
contour_points = os.path.join(dem_output_dir, f"{city}_DEM_Multipoint.dxf")
# The current script saves the resulting 3DM terrain file here
output_path = os.path.join(dem_output_dir, f"{city}_terrain.3dm")

# Function to read points from DXF file using ezdxf
def read_points_from_dxf(file_path):
    """Read point cloud data from a DXF file using ezdxf."""
    points = []
    
    if not os.path.exists(file_path):
        print(f"DXF file not found: {file_path}")
        return points
    
    try:
        doc = ezdxf.readfile(file_path)
        msp = doc.modelspace()
        for entity in msp.query('POINT'):
            point = entity.dxf.location
            points.append([point[0], point[1], point[2]])
        
        print(f"Read {len(points)} points from DXF file.")
        if points:
            print("First 5 points:", points[:5])
    except Exception as e:
        print(f"Error reading DXF file with ezdxf: {str(e)}")
    
    return np.array(points)

# Function to create mesh using Open3D and convert to Rhino mesh
def create_mesh_from_points(points):
    """Create a mesh from point cloud using Open3D and convert to Rhino mesh."""
    if points.shape[0] == 0:
        print("No points provided for mesh creation.")
        return None
    
    try:
        # Create Open3D point cloud
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(points)
        
        # Estimate normals (required for Poisson reconstruction)
        pcd.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.1, max_nn=30))
        
        # Poisson surface reconstruction
        mesh, densities = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
            pcd, depth=8, scale=1.1, linear_fit=True
        )
                
        print(f"Created Open3D mesh with {len(mesh.vertices)} vertices and {len(mesh.triangles)} triangles.")
        
        # Convert Open3D mesh to Rhino mesh
        rhino_mesh = rg.Mesh()
        for v in np.asarray(mesh.vertices):
            rhino_mesh.Vertices.Add(v[0], v[1], v[2])
        for f in np.asarray(mesh.triangles):
            # Ensure face is added correctly (Triangle meshes only have 3 vertices per face)
            rhino_mesh.Faces.AddFace(int(f[0]), int(f[1]), int(f[2]))
                
        print("Converted to Rhino mesh successfully.")
        return rhino_mesh
    
    except Exception as e:
        print(f"Error creating mesh: {str(e)}")
        return None
    finally:
        gc.collect()
        clr.System.GC.Collect()

# Main execution
def main():
    print("Starting multipoint to terrain 3DM conversion.")
    
    points_array = read_points_from_dxf(contour_points)
    
    if points_array.size == 0:
        print("Error: Could not read points from DXF file. Exiting.")
        sys.exit(1)
        
    rhino_mesh = create_mesh_from_points(points_array)
    
    if rhino_mesh is None:
        print("Error: Failed to create Rhino mesh. Exiting.")
        sys.exit(1)
        
    # Save the Rhino mesh to a 3DM file
    file3dm = FileIO.File3dm()
    file3dm.Objects.AddMesh(rhino_mesh)
    
    try:
        file3dm.Write(output_path, FileIO.File3dmWriteOptions())
        print(f"Successfully saved terrain mesh to: {output_path}")
    except Exception as e:
        print(f"Error saving 3DM file: {str(e)}")
        sys.exit(1)

    print("Terrain 3DM file generation completed successfully.")

if __name__ == "__main__":
    main()