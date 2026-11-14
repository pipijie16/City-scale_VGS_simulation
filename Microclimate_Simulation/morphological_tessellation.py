import geopandas as gpd
import momepy
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

args = parse_args(sys.argv[1:])

city = args.get('city_name')

intermediate_folder = args.get('intermediate_folder')

footprint_dir = os.path.join(intermediate_folder, "footprint")
os.makedirs(footprint_dir, exist_ok=True)

building_shp = args.get('shp')
building_shp_projected = os.path.join(footprint_dir, "projected.shp")

epsg_code = int(args.get('utm_epsg'))

gdf = gpd.read_file(building_shp)
gdf_projected = gdf.to_crs(epsg=epsg_code)
gdf_projected.to_file(building_shp_projected)
buildings = gpd.read_file(building_shp_projected)

limit = momepy.buffered_limit(buildings, buffer=100)

tessellation_gdf = momepy.morphological_tessellation(buildings, clip=limit)

microclimate_simulation_dir = os.path.join(intermediate_folder, "microclimate_simulation")
os.makedirs(microclimate_simulation_dir, exist_ok=True)

tessellation_gdf.to_file(os.path.join(microclimate_simulation_dir, "homogeneous_morphology_units.shp"))

print('Tessellation is done!')