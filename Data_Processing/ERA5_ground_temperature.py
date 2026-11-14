import cdsapi
import xarray as xr
import numpy as np
import pandas as pd
import datetime
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

# This script must be run via the GUI's subprocess call, which passes arguments.
args = parse_args(sys.argv[1:])

# Configuration
city = args.get('city_name')

intermediate_folder = args.get('intermediate_folder')

# Set the desired year
year = int(args.get('era5_year'))
# Specify your local time zone
time_zone = args.get('era5_time_zone')
# Define the bounding box [North, West, South, East]
bounding_box = [float(x) for x in args.get('era5_bounding_box').split(',')]

# Define the expected datetime input format
DATETIME_INPUT_FORMAT = "%m-%d %H"
# Directory for saving NetCDF files
output_dir = args.get('intermediate_folder')

start_dt_arg = args.get('start_dt')
end_dt_arg = args.get('end_dt')

print("Starting ERA5 data retrieval, please ensure your Internet connection")

def parse_mmdd_hh_label(s):
    """Parse 'MM-DD HH' where HH is 0..23 and return (month, day, hour) or None."""
    try:
        mmdd, hh = s.rsplit(' ', 1)
        hh_int = int(hh)
        if not (0 <= hh_int <= 23):
            return None
        dt = datetime.datetime.strptime(mmdd, "%m-%d")
        return (dt.month, dt.day, hh_int)
    except Exception:
        return None

# Initialize CDS client once
C = cdsapi.Client()

def get_era5_skin_temperature(year: int, start_datetime_str: str, end_datetime_str: str, 
                              time_zone: str, bounding_box: list, output_dir: str):
    """
    Retrieves ERA5 skin temperature data for a specific time range defined in local time,
    handles the time zone shift, and returns the processed temperature array.

    Args:
        year (int): The target year.
        start_datetime_str (str): Local start date and hour string (e.g., "07-23 00").
        end_datetime_str (str): Local end date and hour string (e.g., "07-23 23").
        time_zone (str): The local time zone string (e.g., 'Asia/Shanghai').
        bounding_box (list): [N, W, S, E] for data retrieval area.
        output_dir (str): Directory to save the temporary NetCDF file.

    Returns:
        np.ndarray: A flattened NumPy array of skin temperatures in Celsius for the local time period.
        
    Note: The retrieval request fetches the full UTC days required to cover the local time range.
    """
    print(f"\n Processing Local Time Range: {start_datetime_str} to {end_datetime_str} (Year {year})")

    # Parse local datetimes
    try:
        start_parsed = parse_mmdd_hh_label(start_datetime_str) if start_datetime_str else None
        end_parsed = parse_mmdd_hh_label(end_datetime_str) if end_datetime_str else None

        if start_parsed is None or end_parsed is None:
            raise ValueError("Invalid or missing start_dt/end_dt. Must be 'MM-DD HH' format (HH: 0-23)")

        s_m, s_d, s_h = start_parsed
        e_m, e_d, e_h = end_parsed

        dt_start_local = datetime.datetime(year, s_m, s_d, 0)
        if s_h != 0:
            dt_start_local += datetime.timedelta(hours=s_h)

        dt_end_local = datetime.datetime(year, e_m, e_d, 0)
        if e_h != 0:
            dt_end_local += datetime.timedelta(hours=e_h)
    except Exception as e:
        print(f"Error parsing or adjusting date strings: {e}")
        return None

    # Localize
    dt_start_local = pd.to_datetime(dt_start_local).tz_localize(time_zone, ambiguous='NaT', nonexistent='shift_forward')
    dt_end_local   = pd.to_datetime(dt_end_local).tz_localize(time_zone, ambiguous='NaT', nonexistent='shift_forward')

    utc_start_slice = dt_start_local.tz_convert('UTC')
    utc_end_slice   = dt_end_local.tz_convert('UTC')

    # Determine required full UTC days for retrieval
    # CDS API requires full days to be specified. We must retrieve all full UTC days
    # between the start and end slicing boundaries.
    
    # Start day for retrieval is the day of utc_start_slice
    d_start = utc_start_slice.floor('D') 
    # End day for retrieval is the day of utc_end_slice, potentially shifted one day later
    d_end = utc_end_slice.ceil('D')
    
    # Generate the list of full UTC days required
    retrieval_days_range = pd.date_range(start=d_start, end=d_end, freq='D')
    
    # Extract year, month, and day lists for the API call
    retrieval_year = str(retrieval_days_range[0].year) # Should be consistent with input year
    retrieval_months = sorted(list(set(d.strftime('%m') for d in retrieval_days_range)))
    retrieval_days = sorted(list(set(d.strftime('%d') for d in retrieval_days_range)))

    # Construct output file path
    output_filename = f'Energyera5_{year}_{dt_start_local.month:02d}_{dt_start_local.day:02d}_ground_temperature.nc'
    output_path = os.path.join(output_dir, output_filename)

    print(f"Retrieval UTC Range (for CDS slicing): {utc_start_slice} to {utc_end_slice}")
    print(f"Retrieving full UTC days: Month(s) {retrieval_months}, Day(s) {retrieval_days}")

    # Call CDS API
    try:
        C.retrieve(
            'reanalysis-era5-single-levels',
            {
                'product_type': 'reanalysis',
                'format': 'netcdf',
                'variable': ['skin_temperature'],
                'year': [retrieval_year],
                'month': retrieval_months,
                'day': retrieval_days,
                'time': [f'{hour:02d}:00' for hour in range(24)],
                'area': bounding_box,
            },
            output_path
        )
        print(f"Successfully retrieved data and saved to: {output_path}")

    except Exception as e:
        print(f"Error during CDS retrieval: {e}")
        return None

    # Process the downloaded NetCDF file
    try:
        ds = xr.open_dataset(output_path)
        
        # Select the precise time slice in UTC
        time_dim = 'valid_time' if 'valid_time' in ds.dims else 'time'
    
        utc_start_naive = utc_start_slice.tz_convert('UTC').tz_localize(None)
        utc_end_naive   = utc_end_slice.tz_convert('UTC').tz_localize(None)

        shifted_part = ds.sel({time_dim: slice(utc_start_naive, utc_end_naive)})

        localtime = pd.to_datetime(shifted_part[time_dim].values).tz_localize('UTC')
        localtime = localtime.tz_convert(time_zone)
        shifted_part = shifted_part.assign_coords({time_dim: localtime})

        # Convert Kelvin (K) to Celsius (°C)
        skin_temperature_celsius = shifted_part['skt'] - 273.15

        # Flatten the skin temperature array for use in other models
        skin_temperature_array = skin_temperature_celsius.values.flatten()
        
        print(f"Processed skin temperature data shape: {skin_temperature_array.shape}")
        print(skin_temperature_celsius)
        print("skin_temperature_array:",skin_temperature_array)
        
        return skin_temperature_array

    except Exception as e:
        print(f"Error during data processing: {e}")
        return None

if __name__ == "__main__":
    # Execute the dynamic retrieval function
    result_array = get_era5_skin_temperature(
        year=year, 
        start_datetime_str=start_dt_arg, 
        end_datetime_str=end_dt_arg,
        time_zone=time_zone,
        bounding_box=bounding_box,
        output_dir=output_dir
    )

    if result_array is not None:
        print("\n--- Final Result Array Snippet (Celsius) ---")
        print(result_array[:5])
        np.save(os.path.join(intermediate_folder, f"{city}_basic_data/ERA5_ground_temperature.npy"), result_array)
    else:
        print("\nFailed to retrieve or process ERA5 data.")
        sys.exit(1)

print("Done retrieving ERA5 ground temperature data")