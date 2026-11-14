import rhinoinside
rhinoinside.load()
import Rhino
import Rhino.Geometry as rg
from System.Drawing import Color
import os
import shutil
import re
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
result_folder = args.get('result_folder')

# Read visualization_times token string passed from main and split into list of tokens
visualization_times_raw = args.get('visualization_times', '')
visualization_tokens = [t.strip() for t in visualization_times_raw.split(',') if t.strip()]

limits_txt = os.path.join(result_folder, f'{city}_visualization_limits_LWS_with_glazing_ratio.txt')
if not os.path.exists(limits_txt):
    with open(limits_txt, 'w') as f:
        pass

# Define color gradient (10 segments) - Active scheme
'''
colors_gradient = [
    Color.FromArgb(241, 0, 0),
    Color.FromArgb(255, 98, 0),
    Color.FromArgb(255, 188, 0),
    Color.FromArgb(234, 233, 0),
    Color.FromArgb(156, 233, 73),
    Color.FromArgb(51, 219, 125),
    Color.FromArgb(0, 200, 177),
    Color.FromArgb(0, 179, 211),
    Color.FromArgb(0, 139, 234),
    Color.FromArgb(0, 96, 225)
]
'''

# Alternative color schemes (commented out)
# Scheme 1
colors_gradient = [
    Color.FromArgb(248, 230, 33),
    Color.FromArgb(205, 224, 29),
    Color.FromArgb(145, 214, 66),
    Color.FromArgb(61, 187, 115),
    Color.FromArgb(30, 157, 136),
    Color.FromArgb(38, 129, 142),
    Color.FromArgb(50, 99, 141),
    Color.FromArgb(66, 61, 132),
    Color.FromArgb(71, 24, 106),
    Color.FromArgb(68, 2, 85)
]

'''
# Scheme 2
colors_gradient = [
    Color.FromArgb(240, 37, 24),
    Color.FromArgb(240, 72, 39),
    Color.FromArgb(241, 143, 71),
    Color.FromArgb(241, 202, 98),
    Color.FromArgb(241, 246, 118),
    Color.FromArgb(210, 235, 135),
    Color.FromArgb(164, 213, 158),
    Color.FromArgb(123, 192, 178),
    Color.FromArgb(89, 175, 195),
    Color.FromArgb(64, 163, 207)
]
'''

# Scheme 3
'''
colors_gradient_alt3 = [
    Color.FromArgb(255, 130, 130),
    Color.FromArgb(255, 156, 156),
    Color.FromArgb(248, 241, 241),
    Color.FromArgb(218, 233, 242),
    Color.FromArgb(118, 218, 234),
    Color.FromArgb(159, 204, 225),
    Color.FromArgb(98, 167, 206),
    Color.FromArgb(43, 108, 157),
    Color.FromArgb(21, 74, 123),
    Color.FromArgb(4, 47, 96)
]
'''

file_path_points = os.path.join(intermediate_folder, f"{city}_basic_data/{city}_Points_with_glazing_ratio.txt")

# Build hour_list from visualization_tokens
# visualization_tokens example: ["07-23 00", "07-24 12-07-24 18"]
hour_list = []
seen = set()

# days in month for non-leap year
days_in_month = {1:31,2:28,3:31,4:30,5:31,6:30,7:31,8:31,9:30,10:31,11:30,12:31}
# Optional: if era5_year provided and is a leap year, treat February as 29 days
era5_year_str = args.get('era5_year')
if era5_year_str:
    try:
        y = int(era5_year_str)
        if (y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)):
            days_in_month[2] = 29
    except Exception:
        # ignore malformed year and keep default days_in_month
        pass

def _inc_month_day_hour(m, d, h):
    h = int(h)
    d = int(d)
    m = int(m)
    if h < 24:
        h += 1
        return m, d, h
    # h == 24 -> next hour is 01 of next day
    h = 1
    d += 1
    maxd = days_in_month.get(m, 31)
    if d > maxd:
        d = 1
        m += 1
        if m > 12:
            m = 1
    return m, d, h

for token in visualization_tokens:
    matches = list(re.finditer(r"\d{2}-\d{2}\s+\d{1,2}", token))
    if len(matches) == 0:
        raise ValueError(f"Invalid visualization token: '{token}'. Expected 'MM-DD HH' or ranges like 'MM-DD HH-MM-DD HH'.")

    i = 0
    while i < len(matches):
        cur = matches[i].group(0)
        # decide if this and the next form a range (there is a '-' between them)
        if i + 1 < len(matches):
            between = token[matches[i].end():matches[i+1].start()]
            if '-' in between:
                # range
                start_date, start_hour = matches[i].group(0).split()
                end_date, end_hour = matches[i+1].group(0).split()
                s_m, s_d = start_date.split('-')
                e_m, e_d = end_date.split('-')
                s_h = f"{int(start_hour):02d}"
                e_h = f"{int(end_hour):02d}"
                a = (int(s_m), int(s_d), int(s_h))
                b = (int(e_m), int(e_d), int(e_h))
                # ensure end >= start by lexicographic compare
                if b < a:
                    raise ValueError(f"Invalid range in token '{token}': end before start.")
                # iterate from a to b using simple increment
                cur_m, cur_d, cur_h = a
                while True:
                    tup = (f"{int(cur_m):02d}", f"{int(cur_d):02d}", f"{int(cur_h):02d}")
                    if tup not in seen:
                        hour_list.append(tup)
                        seen.add(tup)
                    if (cur_m, cur_d, cur_h) == b:
                        break
                    cur_m, cur_d, cur_h = _inc_month_day_hour(cur_m, cur_d, cur_h)
                i += 2
                continue
        # single timestamp
        date_str, hour_str = cur.split()
        m_s, d_s = date_str.split('-')
        h_s = f"{int(hour_str):02d}"
        tup = (m_s, d_s, h_s)
        if tup not in seen:
            hour_list.append(tup)
            seen.add(tup)
        i += 1

for t_idx, (month, day, hour) in enumerate(hour_list):
    # File paths
    file_path_values = os.path.join(result_folder, f'{city}_results_with_glazing_ratio_LWS_{int(month)}_{int(day)}_{int(hour)}.txt')
    output_3dm = os.path.join(result_folder, f'{city}_LWS_with_glazing_ratio_{month}_{day}_{hour}.3dm')

    # Check if output_3dm exists, if not, copy and rename
    if not os.path.exists(output_3dm):
        source_file = os.path.join(intermediate_folder, f'footprint/{city}_3D_city_models_visualization.3dm').replace('\\', '/')
        shutil.copy(source_file, output_3dm)

    # Read points data
    with open(file_path_points, 'r') as f:
        lines_points = f.readlines()
    points = []
    normals = []
    for i, line in enumerate(lines_points, 1):
        parts = line.strip().split(',')
        x, y, z, nx, ny, nz = map(float, parts[:6])
        points.append(rg.Point3d(x, y, z))
        normals.append(rg.Vector3d(nx, ny, nz))
        print(f"Processing point {i}/{len(lines_points)}")

    # Read values data
    with open(file_path_values, 'r') as f:
        lines_values = f.readlines()
    values = [float(line.strip()) for line in lines_values]

    if len(points) != len(values) or len(points) != len(normals):
        raise ValueError("Data mismatch between points, values, and normals.")

    # Create mesh and assign colors
    mesh = rg.Mesh()
    colors = []
    half_size = 1.5  # Half of 3m edge length

    # Dynamically set lower and upper limits from values
    lower = min(values)
    upper = max(values)
    value_range = upper - lower

    for i, (pt, norm, val) in enumerate(zip(points, normals, values), 1):
        # Ensure normal is unit length
        norm.Unitize()
        
        # Define the plane at the point with normal as Z-axis
        plane = rg.Plane(pt, norm)
        
        # Create four vertices for a 3m x 3m quad
        v1 = plane.PointAt(-half_size, -half_size, 0)
        v2 = plane.PointAt(half_size, -half_size, 0)
        v3 = plane.PointAt(half_size, half_size, 0)
        v4 = plane.PointAt(-half_size, half_size, 0)
        
        # Add vertices to mesh
        v1_idx = mesh.Vertices.Add(v1)
        v2_idx = mesh.Vertices.Add(v2)
        v3_idx = mesh.Vertices.Add(v3)
        v4_idx = mesh.Vertices.Add(v4)
        
        # Add face
        mesh.Faces.AddFace(v1_idx, v2_idx, v3_idx, v4_idx)
        
        # Normalize value to 0-1 range based on lower and upper
        norm_val = (val - lower) / value_range if value_range > 0 else 0.5
        norm_val = max(0.0, min(1.0, norm_val))  # Clamp to [0, 1]
        
        # Interpolate color with smooth gradient
        seg_size = 1.0 / 9.0
        t = norm_val / seg_size
        seg_idx = int(t)
        seg_idx = min(9, max(0, seg_idx))  # Ensure within 0-9
        t_in_seg = t - seg_idx  # Fraction within segment
        
        if seg_idx < 9:
            color1 = colors_gradient[seg_idx]
            color2 = colors_gradient[seg_idx + 1]
            r = int(color1.R + (color2.R - color1.R) * t_in_seg)
            g = int(color1.G + (color2.G - color1.G) * t_in_seg)
            b = int(color1.B + (color2.B - color1.B) * t_in_seg)
            colors.append(Color.FromArgb(r, g, b))
        else:
            colors.append(colors_gradient[9])  # Use last color for t >= 1
        
        print(f"Processing face {i}/{len(points)}")

    # Assign colors to mesh faces with vertex color propagation
    mesh.VertexColors.Clear()
    mesh.VertexColors.CreateMonotoneMesh(Color.Black)  # Initialize
    for i, color in enumerate(colors):
        # Get vertices of the face
        face = mesh.Faces[i]
        mesh.VertexColors.SetColor(face[0], color)  # Set color to all vertices of the face
        mesh.VertexColors.SetColor(face[1], color)
        mesh.VertexColors.SetColor(face[2], color)
        mesh.VertexColors.SetColor(face[3], color)

    existing_file = Rhino.FileIO.File3dm.Read(output_3dm)

    # Save to .3dm file using File3dm
    file_3dm = Rhino.FileIO.File3dm()
    file_3dm.Settings.ModelUnitSystem = Rhino.UnitSystem.Meters
    file_3dm.Objects.AddMesh(mesh)

    for obj in existing_file.Objects:
        file_3dm.Objects.AddMesh(obj.Geometry)

    file_3dm.Write(output_3dm, 8)  # Rhino 8 file version
    limits = f"Mesh saved to {output_3dm} with dynamic limits: [{lower}, {upper}]\n"
    with open(limits_txt, "a") as file:
        file.write(limits)