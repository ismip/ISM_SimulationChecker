#!/usr/bin/env python3
"""
NetCDF file generator for ISMIP7 ice sheet simulation data.

This script generates NetCDF files with variables and metadata following
ISMIP7 conventions as defined in the criteria CSV files and grid definitions.
"""
import re
import numpy as np
import xarray as xr
from datetime import datetime
from pathlib import Path
import netCDF4


def get_available_grids(conventions_dir):
    """
    Get available grid definitions from gdfs directory.
    
    Parameters
    ----------
    conventions_dir : str
        Path to conventions directory
        
    Returns
    -------
    dict
        Dictionary with grid info: {'GrIS': [...], 'AIS': [...]}
    """
    # Grid definitions moved to project root `gdfs` directory
    gdf_dir = Path(conventions_dir).parent / 'gdfs'
    grids = {'GrIS': [], 'AIS': []}
    
    if not gdf_dir.exists():
        return grids
    
    for file in sorted(gdf_dir.glob('gdf_ISMIP7_*.txt')):
        # Extract grid type and resolution from filename
        # e.g., gdf_ISMIP7_GrIS_16000m.txt
        match = re.search(r'gdf_ISMIP7_(GrIS|AIS)_(\d+[a-z]+)', file.name)
        if match:
            grid_type = match.group(1)
            resolution = match.group(2)
            grids[grid_type].append(resolution)
    
    return grids


def parse_grid_file(gdf_file):
    """
    Parse ISMIP7 grid definition file.
    
    Parameters
    ----------
    gdf_file : str
        Path to grid definition file
        
    Returns
    -------
    dict
        Dictionary with grid parameters (xsize, ysize, xfirst, yfirst, xinc, yinc, etc.)
    """
    grid_params = {}
    
    with open(gdf_file, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith('#') or not line or '=' not in line:
                continue
            
            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"')
            
            try:
                # Try to convert to int or float
                if '.' in value:
                    grid_params[key] = float(value)
                else:
                    grid_params[key] = int(value)
            except ValueError:
                grid_params[key] = value
    
    return grid_params


def read_variable_criteria(excel_file, include_non_mandatory=False):
    """
    Read variable criteria from Excel file.
    
    Parameters
    ----------
    excel_file : str
        Path to the Excel file
    include_non_mandatory : bool
        Whether to include non-mandatory variables
        
    Returns
    -------
    dict
        Dictionary with variable information
    """
    import pandas as pd
    
    variables = {}
    
    # Read the Excel file
    df = pd.read_excel(excel_file, sheet_name='ISM')
    
    # Filter out rows that don't have variable names
    df = df.dropna(subset=['Variable Name'])
    
    # Filter mandatory variables if requested
    if not include_non_mandatory:
        df = df[df['Mandatory (yes/no)'].str.lower() == 'yes']
    
    for idx, row in df.iterrows():
        var_name = row['Variable Name']
        # Parse dimensions from Dim column
        dim_str = row['Dim']
        if dim_str == 'x,y,t':
            dimensions = ['x', 'y', 't']
        elif dim_str == 't':
            dimensions = ['t']
        else:
            dimensions = ['x', 'y', 't']  # Default
        
        variables[var_name] = {
            'dimensions': dimensions,
            'type': row['Type'],
            'description': row['long_name'],  # Use long_name from Excel
            'standard_name': row['standard_name'] if pd.notna(row['standard_name']) else '',
            'units': str(row['units']) if pd.notna(row['units']) else '',
            'mandatory': row['Mandatory (yes/no)'].lower() == 'yes',
        }

        # Collect any min_/max_ columns (case-insensitive) from the Excel sheet
        # Normalize keys to lowercase (e.g., 'min_gris', 'max_ais') and store
        for col in df.columns:
            try:
                lc = str(col).lower()
            except Exception:
                continue
            if lc.startswith('min_') or lc.startswith('max_'):
                try:
                    val = row[col]
                    if pd.isna(val):
                        parsed = None
                    else:
                        parsed = float(val)
                except Exception:
                    parsed = None
                variables[var_name][lc] = parsed
    
    return variables


def generate_synthetic_data(shape, min_val, max_val, dtype=np.float32, eps=1e-6):
    """
    Generate synthetic data within specified range.
    
    Parameters
    ----------
    shape : tuple
        Shape of the output array
    min_val : float
        Minimum value
    max_val : float
        Maximum value
    dtype : type
        Data type for the array
    eps : float, optional
        A small fraction by which `min_val` and `max_val` move toward one another to avoid
        synthetic data that violates numerical checks because of roundoff.
        
    Returns
    -------
    np.ndarray
        Random data within the specified range
    """
    delta = eps * (max_val - min_val)
    data = np.random.uniform(min_val + delta, max_val - delta, shape).astype(dtype)
    return data


def create_netcdf_file(output_file, grid_name='GrIS_16000m', scenario='ctrl', start_year=2015, nyears=5,
                       conventions_dir=None, include_non_mandatory=False, include_scalars=False,
                       include_xyt=False,
                       ism_member_id='m001', esm_id='CESM2-WACCM', forcing_member_id='f001', set_counter='C001'):
    """
    Create NetCDF files with ISMIP7 variables (one file per variable).
    
    Parameters
    ----------
    output_file : str
        Output file path (if None, will use default based on grid type)
    grid_name : str
        Grid name (e.g., 'GrIS_16000m', 'AIS_16000m')
    scenario : str
        Scenario name (default: 'ctrl')
    start_year : int
        First calendar year for the output time axis (default: 2015)
    nyears : int
        Number of years in the output (default: 5)
    conventions_dir : str
        Path to conventions directory containing gfds
    include_non_mandatory : bool
        Whether to include non-mandatory variables
    include_scalars : bool
        Whether to include scalar time-series variables
    include_xyt : bool
        Whether to include non-scalar x,y,t variables (3D). Set to False to skip x,y,t variables.
    """
    
    group='ISMIP7'
    model='SYNTH1'
    contact_names='Your Name'
    contact_emails='your@email.org'

    # Determine conventions directory
    if conventions_dir is None:
        # Try to find conventions directory relative to this script
        script_dir = Path(__file__).parent.parent
        conventions_dir = script_dir / 'conventions'

    conventions_dir = Path(conventions_dir)
    
    # Parse grid name to get grid type and resolution
    match = re.match(r'(GrIS|AIS)_(.+)', grid_name)
    if not match:
        raise ValueError(f"Invalid grid name: {grid_name}. Expected format: GrIS_16000m or AIS_16000m")
    
    grid_type, resolution = match.groups()

    # Choose CRS per domain: GrIS -> EPSG:3413, AIS -> EPSG:3031
    if grid_type == 'GrIS':
        domain_crs = 'EPSG:3413'
    else:
        domain_crs = 'EPSG:3031'
    
    # Determine output directory
    models_dir = Path(__file__).parent.parent / 'Models'
    if grid_type == 'AIS':
        output_dir = models_dir / 'AIS' / group / model / 'CORE'
    else:  # GrIS
        output_dir = models_dir / 'GrIS' / group / model / 'CORE'
    
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Load grid definition
    gdf_file = conventions_dir.parent / 'gdfs' / f'gdf_ISMIP7_{grid_type}_{resolution}.txt'
    if not gdf_file.exists():
        raise FileNotFoundError(f"Grid definition file not found: {gdf_file}")
    
    grid_params = parse_grid_file(str(gdf_file))
    
    nx = grid_params['xsize']
    ny = grid_params['ysize']
    xfirst = grid_params['xfirst']
    yfirst = grid_params['yfirst']
    xinc = grid_params['xinc']
    yinc = grid_params['yinc']
    
    # Read variable criteria from Excel file
    excel_file = conventions_dir / 'ISMIP7_variable_request.xlsx'
    if not excel_file.exists():
        print(f"Warning: {excel_file} not found")
        variables = {}
    else:
        variables = read_variable_criteria(str(excel_file), include_non_mandatory)
    
    # Create coordinate arrays
    x = np.arange(nx, dtype=np.float32) * xinc + xfirst
    y = np.arange(ny, dtype=np.float32) * yinc + yfirst
    
    # Create time coordinates - will be set per variable type later
    # ST (State) variables: end of year (e.g., 0.999, 1.999, ...)
    # FL (Flux) variables: middle of year (e.g., 0.5, 1.5, ...) with bounds
    
    # Select min/max values based on grid type
    val_key_min = f'min_value_{grid_type.lower()}'
    val_key_max = f'max_value_{grid_type.lower()}'

    # Fill value for single-precision floats (ISMIP7 recommends netCDF4 default f4)
    fillval = netCDF4.default_fillvals['f4']

    # contact defaults are provided via function signature
    
    # Create variables with x-y-t dimensions
    xyt_vars = {var: info for var, info in variables.items() 
               if info['dimensions'] == ['x', 'y', 't']}
    
    # Create scalar time-series variables (t dimension only)
    scalar_vars = {var: info for var, info in variables.items() 
                  if info['dimensions'] == ['t']}
    
    # Compute time range string for filename
    time_range = f"{start_year}-{start_year + nyears - 1}"

    # Create filename template following required pattern:
    # <domain_id>_<source_id>_<ism_id>_<ISM_member_id>_<ESM_id>_<forcing_member_id>_<experiment_id>_<set_counter>_<time_range>.nc
    domain_id = grid_type
    source_id = group
    ism_id = model
    experiment_id = scenario
    filename_template = (
        f"{domain_id}_{source_id}_{ism_id}_{ism_member_id}_{esm_id}_{forcing_member_id}_"
        f"{experiment_id}_{set_counter}_{time_range}.nc"
    )
    
    # Create separate file for each variable
    created_files = []
    
    # Process x-y-t variables (3D). Can be enabled via `include_xyt`.
    if include_xyt:
        for var_name, var_info in xyt_vars.items():
            var_type = var_info['type']

            # Select appropriate time coordinate (days since 1850, calendar: standard)
            origin = datetime(1850, 1, 1).date()
            if var_type == 'ST':
                # End of year (Dec 31)
                time_days = []
                time_bounds = None
                for i in range(nyears):
                    year = start_year + i
                    dt = datetime(year, 12, 31).date()
                    time_days.append(float((dt - origin).days))
                time_coord = np.array(time_days, dtype=np.float32)
            elif var_type == 'FL':
                # Middle of year (Jul 1) and bounds from Jan 1 to Jan 1 next year
                time_days = []
                time_bounds = np.zeros((nyears, 2), dtype=np.float32)
                for i in range(nyears):
                    year = start_year + i
                    mid = datetime(year, 7, 1).date()
                    t0 = datetime(year, 1, 1).date()
                    t1 = datetime(year + 1, 1, 1).date()
                    time_days.append(float((mid - origin).days))
                    time_bounds[i, 0] = float((t0 - origin).days)
                    time_bounds[i, 1] = float((t1 - origin).days)
                time_coord = np.array(time_days, dtype=np.float32)
            else:
                # Default to state variable timing (end of year)
                time_days = []
                time_bounds = None
                for i in range(nyears):
                    year = start_year + i
                    dt = datetime(year, 12, 31).date()
                    time_days.append(float((dt - origin).days))
                time_coord = np.array(time_days, dtype=np.float32)

            # Determine min/max for this variable (per-grid if available)
            min_val = var_info.get(val_key_min)
            max_val = var_info.get(val_key_max)
            if min_val is None and max_val is None:
                min_val = -1e6
                max_val = 1e6
            else:
                if min_val is None:
                    min_val = max_val - 1.0
                if max_val is None:
                    max_val = min_val + 1.0
            if min_val >= max_val:
                max_val = min_val + 1.0

            data = generate_synthetic_data((nyears, ny, nx), min_val, max_val)

            # Create data array with metadata
            data_vars = {
                var_name: (
                    ('time', 'y', 'x'),
                    data.astype(np.float32),
                    {
                        'long_name': var_info['description'],
                        'units': var_info['units'],
                        'standard_name': var_info['standard_name'],
                    }
                )
            }

            # Add time bounds for flux variables (units: days since 1850)
            if time_bounds is not None:
                data_vars[f'time_bounds'] = (
                    ('time', 'bounds'),
                    time_bounds.astype(np.float32),
                    {
                        'long_name': 'time bounds',
                        'units': 'days since 1850-01-01',
                    }
                )
                # The 'time' coordinate is created in `coords`, so we attach the
                # 'bounds' attribute to the Dataset's time coordinate after
                # constructing the Dataset (see below).

            # Create xarray Dataset
            coords = {
                'x': ('x', x, {'long_name': 'x-coordinate', 'units': 'm'}),
                'y': ('y', y, {'long_name': 'y-coordinate', 'units': 'm'}),
                'time': ('time', time_coord, {'long_name': 'time', 'units': 'days since 1850-01-01', 'calendar': 'standard'}),
            }

            ds = xr.Dataset(data_vars, coords=coords)

            # If time bounds were created, attach the bounds attribute to the time coordinate
            if time_bounds is not None:
                ds['time'].attrs['bounds'] = 'time_bounds'

            # Add grid mapping information if available
            grid_mapping_attrs = {}
            if 'proj_params' in grid_params:
                grid_mapping_attrs['proj_params'] = grid_params['proj_params']
            if 'grid_mapping_name' in grid_params:
                grid_mapping_attrs['grid_mapping_name'] = grid_params['grid_mapping_name']

            # Add global attributes
            ds.attrs.update({
                'title': f'ISMIP7 synthetic data - {var_name}',
                'history': f'Generated on {datetime.now().isoformat()}',
                'Conventions': 'CF-1.7',
                'grid_type': grid_type,
                'grid_resolution': resolution,
                'group': group,
                'model': model,
                'contact_name': contact_names,
                'contact_email': contact_emails,
                'crs': domain_crs,
            })

            # Add grid mapping attributes to global attributes
            ds.attrs.update(grid_mapping_attrs)

            # Create filename
            filename = f"{var_name}_{filename_template}"
            output_path = output_dir / filename

            # Prepare encoding to comply with conventions (single precision, fill values, unlimited time)
            encoding = {}
            encoding[var_name] = {'dtype': 'f4', '_FillValue': fillval}
            encoding['time'] = {'dtype': 'f4', '_FillValue': fillval}
            # time bounds are stored under the fixed name 'time_bounds'
            if 'time_bounds' in data_vars:
                encoding['time_bounds'] = {'dtype': 'f4', '_FillValue': fillval}

            ds.to_netcdf(output_path, unlimited_dims=('time',), encoding=encoding)
            # xarray drops missing_value from attrs when _FillValue is in encoding;
            # write it explicitly via netCDF4 to guarantee the attribute is present.
            with netCDF4.Dataset(output_path, 'a') as nc:
                nc[var_name].missing_value = fillval
            created_files.append(str(output_path))
    else:
        print(f"Skipping x,y,t variables (include_xyt=False); {len(xyt_vars)} variables not written")
    
    # Process scalar variables
    if include_scalars:
        for var_name, var_info in scalar_vars.items():
            var_type = var_info['type']
        
            # Select appropriate time coordinate (days since 1850)
            origin = datetime(1850, 1, 1).date()
            if var_type == 'ST':
                time_days = []
                time_bounds = None
                for i in range(nyears):
                    year = start_year + i
                    dt = datetime(year, 12, 31).date()
                    time_days.append(float((dt - origin).days))
                time_coord = np.array(time_days, dtype=np.float32)
            elif var_type == 'FL':
                time_days = []
                time_bounds = np.zeros((nyears, 2), dtype=np.float32)
                for i in range(nyears):
                    year = start_year + i
                    mid = datetime(year, 7, 1).date()
                    t0 = datetime(year, 1, 1).date()
                    t1 = datetime(year + 1, 1, 1).date()
                    time_days.append(float((mid - origin).days))
                    time_bounds[i, 0] = float((t0 - origin).days)
                    time_bounds[i, 1] = float((t1 - origin).days)
                time_coord = np.array(time_days, dtype=np.float32)
            else:
                time_days = []
                time_bounds = None
                for i in range(nyears):
                    year = start_year + i
                    dt = datetime(year, 12, 31).date()
                    time_days.append(float((dt - origin).days))
                time_coord = np.array(time_days, dtype=np.float32)
        
            # Determine min/max for this scalar variable (per-grid if available)
            min_val = var_info.get(val_key_min)
            max_val = var_info.get(val_key_max)
            if min_val is None and max_val is None:
                min_val = -1e12
                max_val = 1e12
            else:
                if min_val is None:
                    min_val = max_val - 1.0
                if max_val is None:
                    max_val = min_val + 1.0
            if min_val >= max_val:
                max_val = min_val + 1.0

            # Generate synthetic 1D data
            data = generate_synthetic_data((nyears,), min_val, max_val).astype(np.float32)  # Wide range for scalar data
            # Create data array with metadata
            data_vars = {
                var_name: (
                    ('time',),
                    data,
                    {
                        'long_name': var_info['description'],
                        'units': var_info['units'],
                        'standard_name': var_info['standard_name'],
                    }
                )
            }
            if time_bounds is not None:
                data_vars[f'time_bounds'] = (
                    ('time', 'bounds'),
                    time_bounds.astype(np.float32),
                    {
                        'long_name': 'time bounds',
                        'units': 'days since 1850-01-01',
                    }
                )
                # The 'time' coordinate is created in `coords`, so attach the
                # bounds attribute to the Dataset's time coordinate after
                # constructing the Dataset (see below).

            # Create xarray Dataset
            coords = {
                'time': ('time', time_coord, {'long_name': 'time', 'units': 'days since 1850-01-01', 'calendar': 'standard'}),
            }

            ds = xr.Dataset(data_vars, coords=coords)
            # If time bounds were created, attach the bounds attribute to the time coordinate
            if time_bounds is not None:
                ds['time'].attrs['bounds'] = 'time_bounds'

            # Add global attributes (include mandatory ISMIP7 attributes)
            ds.attrs.update({
                'title': f'ISMIP7 synthetic data - {var_name}',
                'history': f'Generated on {datetime.now().isoformat()}',
                'Conventions': 'CF-1.7',
                'grid_type': grid_type,
                'grid_resolution': resolution,
                'nt': nyears,
                'group': group,
                'model': model,
                'scenario': scenario,
                'contact_name': contact_names,
                'contact_email': contact_emails,
                'crs': domain_crs,
            })

            # Create filename
            filename = f"{var_name}_{filename_template}"
            output_path = output_dir / filename

            # Prepare encoding for scalars
            encoding = {var_name: {'dtype': 'f4', '_FillValue': fillval},
                        'time': {'dtype': 'f4', '_FillValue': fillval}}
            if f'time_bounds' in data_vars:
                encoding[f'time_bounds'] = {'dtype': 'f4', '_FillValue': fillval}

            ds.to_netcdf(output_path, unlimited_dims=('time',), encoding=encoding)
            # xarray drops missing_value from attrs when _FillValue is in encoding;
            # write it explicitly via netCDF4 to guarantee the attribute is present.
            with netCDF4.Dataset(output_path, 'a') as nc:
                nc[var_name].missing_value = fillval
            created_files.append(str(output_path))

    print(f"Created {len(created_files)} files in {output_dir}")
    print(f"  Grid: {grid_name} ({nx} x {ny})")
    print(f"  Years: {nyears}")
    
    
    return created_files


def create_multiple_files(output_dir=None, n_files=3, conventions_dir=None,
                          start_year=2015, contact_names='Your Name', contact_emails='your@email.org',
                          include_xyt=True, include_non_mandatory=False):
    """
    Create multiple NetCDF files for testing (one file per variable per grid).
    
    Parameters
    ----------
    output_dir : str
        Output directory (if None, uses default Models structure)
    n_files : int
        Number of files to generate per grid
    conventions_dir : str
        Path to conventions directory
    """
    
    if conventions_dir is None:
        # Try to find conventions directory relative to this script
        script_dir = Path(__file__).parent.parent
        conventions_dir = script_dir / 'conventions'
    
    # Get available grids
    grids = get_available_grids(str(conventions_dir))
    
    total_files = 0
    
    # Create files for both Antarctica (AIS) and Greenland (GrIS)
    for grid_type in ['GrIS', 'AIS']:
        if grid_type not in grids or not grids[grid_type]:
            print(f"No {grid_type} grids found")
            continue
        
        # Use the first n_files available grids
        for i, resolution in enumerate(grids[grid_type][:n_files]):
            grid_name = f'{grid_type}_{resolution}'
            
            created_files = create_netcdf_file(
                None,  # Use default output path
                grid_name=grid_name,
                nyears=5,  # Default 5 years for testing
                start_year=start_year,
                conventions_dir=conventions_dir,
                include_scalars=(i == 0),
                include_xyt=include_xyt,
                include_non_mandatory=include_non_mandatory,
             )
            total_files += len(created_files)
    
    print(f"Total files created: {total_files}")


if __name__ == '__main__':
    import argparse
    
    # Get available grids
    script_dir = Path(__file__).parent.parent
    conventions_dir = script_dir / 'conventions'
    available_grids = get_available_grids(str(conventions_dir))
    
    # Create list of available grid choices, excluding some high-resolution entries
    grid_choices = []
    for grid_type in ['GrIS', 'AIS']:
        if grid_type in available_grids:
            for resolution in available_grids[grid_type]:
                name = f'{grid_type}_{resolution}'
                grid_choices.append(name)
    
    parser = argparse.ArgumentParser(
        description='Generate ISMIP7 NetCDF files with synthetic data'
    )
    parser.add_argument(
        '--grid',
        default='GrIS_16000m',
        choices=grid_choices,
        help=f'Grid definition to use (default: GrIS_16000m). Available: {", ".join(grid_choices[:5])}...'
    )
    parser.add_argument(
        '--start-year',
        type=int,
        default=2015,
        help='First calendar year for the output time axis (default: 2015)'
    )
    parser.add_argument(
        '--nyears',
        type=int,
        default=5,
        help='Number of years in the output (default: 5)'
    )
    parser.add_argument(
        '--scenario',
        default='ctrl',
        help='Scenario name (default: ctrl)'
    )
    parser.add_argument(
        '--scalars',
        action='store_true',
        help='Include scalar time-series variables'
    )
    parser.add_argument(
        '--xyt',
        action='store_true',
        help='Write x,y,t variables'
    )
    parser.add_argument(
        '--include-non-mandatory',
        action='store_true',
        help='Include non-mandatory variables from the ISM Excel variable list'
    )
    parser.add_argument(
        '--multiple',
        action='store_true',
        help='Generate multiple test files with all available grids'
    )
    parser.add_argument(
        '--conventions-dir',
        default=str(conventions_dir),
        help=f'Path to conventions directory (default: {conventions_dir})'
    )
    parser.add_argument(
        '--ism-member-id',
        default='m001',
        help='ISM ensemble member id (default: m001)'
    )
    parser.add_argument(
        '--esm-id',
        default='CESM2-WACCM',
        help='ESM id (default: CESM2-WACCM)'
    )
    parser.add_argument(
        '--forcing-member-id',
        default='f001',
        help='Forcing ensemble member id (default: f001)'
    )
    parser.add_argument(
        '--set-counter',
        default='C001',
        help='Set counter id (default: C001)'
    )
    parser.add_argument(
        '--list-grids',
        action='store_true',
        help='List all available grids and exit'
    )
    
    args = parser.parse_args()
    
    # Handle list grids option
    if args.list_grids:
        print("\nAvailable grids:\n")
        for grid_type in ['GrIS', 'AIS']:
            if grid_type in available_grids:
                print(f"{grid_type}:")
                for resolution in available_grids[grid_type]:
                    print(f"  - {grid_type}_{resolution}")
        print()
        exit(0)
    
    if args.multiple:
        create_multiple_files(conventions_dir=args.conventions_dir,
                              start_year=args.start_year,
                              include_xyt=args.xyt,
                              include_non_mandatory=args.include_non_mandatory)
    else:
        create_netcdf_file(
            None,  # Use default output path
            grid_name=args.grid,
            scenario=args.scenario,
            start_year=args.start_year,
            nyears=args.nyears,
            conventions_dir=args.conventions_dir,
            include_scalars=args.scalars,
            include_xyt=args.xyt,
            include_non_mandatory=args.include_non_mandatory,
            ism_member_id=args.ism_member_id,
            esm_id=args.esm_id,
            forcing_member_id=args.forcing_member_id,
            set_counter=args.set_counter,
        )
