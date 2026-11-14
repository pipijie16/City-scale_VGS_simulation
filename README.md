# City-Scale Vertical Greenery Systems Simulation

## 🔭 Introduction

![](assets/media/City_Scale_Surface_Temperature.gif)

### Abstract

Vertical greenery systems (VGS) have emerged as an effective approach for urban heat mitigation, energy savings, and carbon emission reduction. Traditional methods for quantifying cooling and energy-saving benefits of VGS cannot be scaled up to the city scale due to intensive computational demands, leaving a gap in city-scale assessment. Moreover, previous VGS simulations have exposed incompatibilities in spatial representations and computational units across different scales. In this paper, we develop a computational strategy including morphological clustering and GPU-accelerated numerical vectorization to enable city-scale VGS simulation within affordable computational time, along with a multi-scale consistent computational framework coordinating computations across different spatial scales. The simulation covers two types of VGS under both full and partial retrofitting scenarios, conducted over four representative days across the four seasons. Subsequently, we assess the cooling, energy-saving, and carbon reduction benefits, alongside the economic feasibility. The results reveal that citywide implementation of VGS in Wuhan can reduce average daytime air temperature by up to 0.25 °C, save 690.02–1279.88 GWh of energy annually, and avoid 0.45–0.77 MtCO₂ yr⁻¹ in carbon emissions, depending on the VGS type and retrofitting scenario. Such benefits involve substantial installation and operational costs, emphasizing a trade-off between environmental performance and economic feasibility. Our findings underscore the vast potential of VGS retrofitting, paving the way for translating such promising urban green infrastructure into actionable strategies.

## 🔧 Installation

### 1. Software Requirements

The following software must be installed before running the code:

- **ArcGIS Pro** – Required for geospatial processing and morphological clustering through ArcPy.
- **Rhinoceros 3D (Rhino 8)** – Required for 3D geometric modelling and visualization.
- **Python 3.9 or above** – Required for running the Python scripts. Python 3.11 is the version used in the tested simulation environment.
- **Ladybug Tools** – Required for solar irradiation simulation, grid discretization, and related workflows. Visit the [Ladybug Tools website](https://www.ladybug.tools/) for installation instructions.
- **Radiance** – Required for solar irradiation calculation and view factor computation. The installation directory should be `C:/Radiance`.
- **Accelerad** – Used for GPU-accelerated Radiance calculations. Please follow the instructions in the [Accelerad documentation](https://nljones.github.io/Accelerad/documentation.html) for installation and configuration.

Please ensure that the corresponding Python environments, software dependencies, and executables are accessible to the scripts.

### 2. Python Environment

The code has been tested in the following environment:

| Component | Version / Specification |
|---|---|
| Operating System | Windows 11 |
| Python | 3.11.0 |
| PyTorch | 2.5.0 |
| CUDA | 13.0 |
| GPU | NVIDIA GeForce RTX 3070 |
| CPU | Intel(R) Core(TM) i7-10700 CPU @ 2.90GHz |
| CUDA Driver | 581.08 |

### 3. Python Dependencies

The code uses the following third-party Python packages:

| Package | Main purpose |
|---|---|
| `numpy` | Numerical computation and array operations |
| `scipy` | Scientific computing and numerical algorithms |
| `pandas` | Tabular data processing |
| `geopandas` | Geospatial vector data processing |
| `shapely` | Geometric operations |
| `xarray` | Multidimensional data processing |
| `momepy` | Morphological tessellation |
| `open3d` | 3D point cloud and geometry processing |
| `ezdxf` | CAD/DXF data processing |
| `triangle` | Triangular mesh generation |
| `cupy` | GPU-accelerated numerical computation |
| `torch` | GPU-accelerated computation |
| `matplotlib` | Data visualization |
| `tqdm` | Progress bars |
| `cdsapi` | ERA5 climate data retrieval |
| `PyYAML` | YAML configuration file parsing |
| `ladybug-core` | Ladybug Tools core functionality |
| `ladybug-geometry` | Geometry operations for Ladybug Tools |
| `ladybug-rhino` | Ladybug-Rhino integration |
| `honeybee-core` | Honeybee core functionality |
| `honeybee-radiance` | Radiance-based simulation |
| `lbt-recipes` | Ladybug Tools simulation recipes |
| `rhinoinside` | Rhino.Inside integration |
| `pythonnet` | .NET integration for Python |

You can install the general-purpose Python dependencies using:

```bash
pip install numpy scipy pandas geopandas shapely xarray momepy open3d ezdxf triangle matplotlib tqdm cdsapi PyYAML
```

**Rhino.Inside dependencies**

For external Python scripts that use Rhino.Inside, install the required Python integration packages in the corresponding Python environment:

```bash
pip install rhinoinside pythonnet
```

**GPU acceleration**

For GPU acceleration, install CuPy and PyTorch versions compatible with your CUDA environment.

For example, the CuPy package for CUDA 13.x can be installed using:

```bash
pip install cupy-cuda13x
```

**Important notes:**

- PyTorch should be installed according to the CUDA version supported by your system. Refer to the [official PyTorch installation guide](https://pytorch.org/get-started/locally/).
- CuPy and PyTorch require compatible GPU drivers and CUDA runtime components.
- `arcpy` is provided by ArcGIS Pro and should not be installed using `pip`. Run ArcPy-dependent scripts using the Python interpreter bundled with ArcGIS Pro.
- `Rhino`, `Rhino.Geometry`, and related .NET components are provided through the Rhino environment. Installing `rhinoinside` and `pythonnet` alone does not replace the Rhinoceros 3D installation.
- Ladybug Tools workflows may also require the corresponding Radiance executables and a properly configured Ladybug Tools installation.
- The Python packages required by each script must be available in the Python environment used to execute that script.

### 4. Configuring ArcPy and Rhino Python Environments

#### ArcGIS Pro (ArcPy)

ArcPy is provided by ArcGIS Pro and does not need to be installed separately using pip. The Python interpreter bundled with ArcGIS Pro is typically located at:

```text
<ArcGIS Pro installation directory>/bin/Python/envs/arcgispro-py3/python.exe
```

Specify the actual path to this interpreter using `arcpy_interpreter` in `config.yaml`.

#### Rhinoceros 3D (Rhino 8 Python)

Rhino 8 provides its own Python 3.9 runtime, which is typically located at:

```text
%USERPROFILE%\.rhinocode\py39-rh8
```

When using VS Code or another external Python IDE to develop scripts involving Rhino APIs, the Rhino Python environment can be configured to provide API recognition and code completion.

For VS Code, add the following settings to `.vscode/settings.json`:

```json
{
    "python.defaultInterpreterPath": "${env:USERPROFILE}\\.rhinocode\\py39-rh8\\python.exe",
    "python.analysis.stubPath": "${env:USERPROFILE}\\.rhinocode\\py39-rh8\\site-stubs",
    "python.analysis.extraPaths": [
        "${env:USERPROFILE}\\.rhinocode\\py39-rh8\\site-interop",
        "${env:USERPROFILE}\\.rhinocode\\py39-rh8\\site-rhinopython"
    ]
}
```

These settings primarily configure the editor and Python module search paths. Running Rhino geometry operations from an external Python process may additionally require proper Rhino.Inside initialization.

## 📂 Input Data

Before running the simulation, prepare the following input data.

### 1. Building Shapefile (Required)

A building footprint Shapefile (`.shp`) containing building geometries and a building-height attribute.

The Shapefile must contain a height field specifying the height of each building, which will be used for 3D modeling. The field name should be specified using `height_field` in `config.yaml`.

Make sure that all associated Shapefile components are available, including `.shp`, `.shx`, `.dbf`, and `.prj` files.

If you intend to simulate VGS scenarios with glazing ratios, the Shapefile must additionally contain:

- A building typology field, specified using `building_typology_field`.
- A glazing ratio field, specified using `glazing_ratio_field`.

The actual field names depend on your input Shapefile.

### 2. EPW Weather File (Required)

An EnergyPlus Weather (`.epw`) file for the study area. Specify its path using `epw_file` in `config.yaml`.

### 3. Digital Elevation Model (Optional)

A terrain raster in GeoTIFF format (`.tif`).

This input is only required when terrain processing is enabled. Set `terrain_flag: True` and specify the raster path using `terrain_path`.

If terrain is not included in the simulation, set `terrain_flag: False`.

## ⚙️ Configuration

The simulation is configured through `config.yaml`. The configuration file specifies input data paths, Python interpreters, output directories, simulation settings, and material properties.

An example configuration file is provided below. **Please replace the example paths and field names with those corresponding to your own data and software installations.**

```yaml
# 1. Paths & Inputs
city_name: "Wuhan"    # City Name (Use '_' for spaces, e.g., Hong_Kong)
shp: "E:/City-scale_VGS_simulation/Data/Wuhan_Building.shp"    # Building Shapefile (.shp)
height_field: "height"    # Height Field Name
building_typology_field: "type"    # Building Typology Field Name
glazing_ratio_field: "glaz_ratio"    # Glazing Ratio Field Name
epw_file: "E:/City-scale_VGS_simulation/Data/Wuhan.epw"    # Weather File (.epw)

# 2. Environments
general_interpreter: "C:/Python311/python.exe"    # General Python Interpreter (.exe)
arcpy_interpreter: "C:/Program Files/ArcGIS/Pro/bin/Python/envs/arcgispro-py3/python.exe"    # ArcPy Interpreter (.exe)
ladybug_path: "C:/Users/Administrator/ladybug_tools"    # Ladybug Folder Path

# 3. Outputs
intermediate_folder: "E:/City-scale_VGS_simulation/intermediate_folder"    # Intermediate Folder Path
result_folder: "E:/City-scale_VGS_simulation/result_folder"    # Results Folder Path

# 4. Performance Settings
grid_size: "3.0"    # Grid Size on Facades (m)
num_threads: "4"    # Number of Threads (Parallel)
gpu_flag: True    # Enable GPU Acceleration

# 5. Time Settings (MM-DD HH)
start_dt: "07-23 00"    # Start Time
end_dt: "07-23 23"    # End Time
visualization_times: "07-23 14, 07-23 16-07-23 20"    # Visualization Hours

# 6. ERA5 Settings
era5_year: "2025"    # Year
era5_time_zone: "Asia/Shanghai"    # Time Zone
era5_bounding_box: "30.6,114.2,30.4,114.4"    # Bounding Box (N,W,S,E)
utm_epsg: "32649"    # UTM EPSG Code

# 7. Material Properties
LAI: "3.0"    # Leaf Area Index (LAI)
wall_absorptivity: "0.65"    # Wall Solar Absorptivity
u_value: "2.0"    # U-value of the wall
wall_thickness: "0.24"    # Wall Thickness (m)
rho_of_wall: "2000"    # Density of Wall Material (kg/m³)
c_pw: "1000"    # Specific Heat Capacity (J/kg·K)

# 8. Simulation Options
terrain_flag: True    # Include Terrain in Simulation
terrain_path: "E:/City-scale_VGS_simulation/Data/Wuhan_DEM.tif"    # Terrain File (.tif)
facade_types:
  - "Green Facades"
  - "Living Wall Systems"
  - "Green Facades with glazing ratio"
  - "Living Wall Systems with glazing ratio"
```

### Configuration Parameter Descriptions

| Parameter | Description |
|---|---|
| `city_name` | Name of the study area. Use underscores instead of spaces, e.g., Hong_Kong. |
| `shp` | Path to the building footprint Shapefile. |
| `height_field` | Attribute field containing building heights. |
| `building_typology_field` | Attribute field containing building typologies. |
| `glazing_ratio_field` | Attribute field containing window-to-wall ratios (WWR). |
| `epw_file` | Path to the EPW weather file. |
| `general_interpreter` | Path to the general Python interpreter used to run non-ArcPy scripts. |
| `arcpy_interpreter` | Path to the Python interpreter bundled with ArcGIS Pro. |
| `ladybug_path` | Path to the local Ladybug Tools installation directory. |
| `intermediate_folder` | Directory for intermediate simulation files. |
| `result_folder` | Directory for final simulation results. |
| `grid_size` | Grid resolution on building facades, in meters. |
| `num_threads` | Number of CPU threads used for parallel processing. |
| `gpu_flag` | Whether to enable GPU acceleration. |
| `start_dt` | Simulation start time, in `MM-DD HH` format. |
| `end_dt` | Simulation end time, in `MM-DD HH` format. |
| `visualization_times` | Time points or time intervals for generating visualizations in `MM-DD HH-MM-DD HH` format. Separate multiple entries with commas. |
| `era5_year` | Year of ERA5 data used in the workflow. |
| `era5_time_zone` | Time zone used for ERA5 data processing. |
| `era5_bounding_box` | ERA5 spatial bounding box in the order North, West, South, East. |
| `utm_epsg` | EPSG code of the projected coordinate reference system used for spatial processing. |
| `LAI` | Leaf Area Index used to represent vegetation characteristics. |
| `wall_absorptivity` | Solar absorptivity of the building wall. |
| `u_value` | Thermal transmittance (U-value) of the building wall. |
| `wall_thickness` | Thickness of the building wall, in meters. |
| `rho_of_wall` | Density of the wall material, in kg/m³. |
| `c_pw` | Specific heat capacity of the wall material, in J/(kg·K). |
| `terrain_flag` | Whether terrain data are included in the simulation. |
| `terrain_path` | Path to the DEM GeoTIFF. Required when `terrain_flag` is `True`. |
| `facade_types` | VGS scenarios to be simulated. |

### Selecting VGS Scenarios

The `facade_types` parameter determines which VGS scenarios will be included in the simulation. The available options are:

- `Green Facades`
- `Living Wall Systems`
- `Green Facades with glazing ratio`
- `Living Wall Systems with glazing ratio`

If you select either of the scenarios with **glazing ratio**, make sure that the corresponding building typology and glazing ratio fields are available in your input Shapefile and correctly specified in the configuration file.

If you only select the first two scenarios, the building typology and glazing ratio fields are not required for these scenarios.

### Notes on Configuring File Paths

- Use absolute paths for input files, software environments, and output directories.
- Replace all example paths with paths on your own computer.
- Make sure that the specified Python interpreter paths point to valid Python executables.
- The general Python interpreter and ArcGIS Pro Python interpreter may be different environments. Both should have the required packages for the scripts they execute.
- Ensure that the output directories exist or can be created by the program.

## 🚀 Running the Simulation

After preparing the input data, installing the required software and Python packages, and editing `config.yaml`, run the main script:

```bash
python main.py
```

The program can also be launched with an explicitly specified configuration file:

```bash
python main.py --config config.yaml
```

Make sure that the Python interpreter used to launch `main.py` is the one specified in `general_interpreter`.

## 📊 Outputs

Simulation outputs are saved in the directory specified by `result_folder`. Intermediate files generated during the workflow are stored in `intermediate_folder`.

The output files include the results generated by the different processing and simulation stages. Please refer to the corresponding output folders and file names for the detailed results.

## 💡 Citation

If you use this code in your research, please cite the associated publication.

**Citation information will be added upon publication.**

[Publication details and DOI to be added.]

## 📬 Contact

pipijie@whu.edu.cn
