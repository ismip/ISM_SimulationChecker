"""
NetCDF file generator for ISMIP7 ice sheet simulation data.

Generates NetCDF files with variables and metadata following ISMIP7
conventions as defined in the criteria CSV files and grid definitions, both of
which ship as package data alongside the checker.
"""
import argparse
import re
from importlib import resources
import numpy as np
import xarray as xr
from datetime import datetime
from pathlib import Path
import netCDF4

DATA_PACKAGE = f'{__package__}.data'

# Synthetic data is drawn from a seeded generator so that a given seed always
# produces the same files: reproducible test data, and no test that can drift
# across a numerical bound from one run to the next.
DEFAULT_SEED = 0


def data_dir() -> Path:
    """Return the bundled directory of criteria CSVs and `gdfs` grid definitions.

    The package is always installed as a directory rather than a zip, so the
    resource is a real path on disk.
    """
    return Path(str(resources.files(DATA_PACKAGE)))


def get_available_grids(conventions_dir=None):
    """
    Get available grid definitions from the `gdfs` directory.

    Parameters
    ----------
    conventions_dir : str, optional
        Path to conventions directory (default: the bundled package data)

    Returns
    -------
    dict
        Dictionary with grid info: {'GrIS': [...], 'AIS': [...]}
    """
    if conventions_dir is None:
        conventions_dir = data_dir()
    gdf_dir = Path(conventions_dir) / 'gdfs'

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


def read_variable_criteria(csv_file, include_non_mandatory=False):
    """
    Read variable criteria from CSV file.

    Parameters
    ----------
    csv_file : str
        Path to the CSV file
    include_non_mandatory : bool
        Whether to include non-mandatory variables

    Returns
    -------
    dict
        Dictionary with variable information
    """
    import pandas as pd

    variables = {}

    # Read the CSV file
    df = pd.read_csv(csv_file)

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
        elif dim_str == 'x,y,z,t':
            dimensions = ['x', 'y', 'z', 't']
        elif dim_str == 'x,y':
            dimensions = ['x', 'y']
        else:
            dimensions = ['x', 'y', 't']  # Default

        variables[var_name] = {
            'dimensions': dimensions,
            'type': row['Type'],
            'description': row['long_name'],  # Use long_name from CSV
            'standard_name': row['standard_name'] if pd.notna(row['standard_name']) else '',
            'units': str(row['units']) if pd.notna(row['units']) else '',
            'mandatory': row['Mandatory (yes/no)'].lower() == 'yes',
        }

        # Collect any min_/max_ columns (case-insensitive) from the CSV
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


def generate_synthetic_data(shape, min_val, max_val, dtype=np.float32, eps=1e-6,
                            rng=None):
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
    rng : np.random.Generator, optional
        Random number generator to draw from (default: a fresh generator seeded
        with `DEFAULT_SEED`)

    Returns
    -------
    np.ndarray
        Random data within the specified range
    """
    if rng is None:
        rng = np.random.default_rng(DEFAULT_SEED)
    delta = eps * (max_val - min_val)
    data = rng.uniform(min_val + delta, max_val - delta, shape).astype(dtype)
    return data


def create_netcdf_file(output_file, grid_name='GrIS_16000m', scenario='ctrl', start_year=2015, nyears=5,
                       conventions_dir=None, include_non_mandatory=False, include_scalars=False,
                       include_xyt=False, output_root=None, nz=5,
                       ism_member_id='m001', esm_id='CESM2-WACCM', forcing_member_id='f001', set_counter='C001',
                       seed=DEFAULT_SEED):
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
    seed : int, optional
        Seed for the synthetic data; the same seed always produces the same values.
    """

    rng = np.random.default_rng(seed)

    group='ISMIP7'
    model='SYNTH1'
    contact_names='Your Name'
    contact_emails='your@email.org'

    # Determine conventions directory (bundled package data by default)
    if conventions_dir is None:
        conventions_dir = data_dir()

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
    models_dir = Path(output_root) if output_root is not None else Path.cwd() / 'Models'
    if grid_type == 'AIS':
        output_dir = models_dir / 'AIS' / group / model / 'CORE' / set_counter
    else:  # GrIS
        output_dir = models_dir / 'GrIS' / group / model / 'CORE' / set_counter

    output_dir.mkdir(parents=True, exist_ok=True)

    # Load grid definition
    gdf_file = conventions_dir / 'gdfs' / f'gdf_ISMIP7_{grid_type}_{resolution}.txt'
    if not gdf_file.exists():
        raise FileNotFoundError(f"Grid definition file not found: {gdf_file}")

    grid_params = parse_grid_file(str(gdf_file))

    nx = grid_params['xsize']
    ny = grid_params['ysize']
    xfirst = grid_params['xfirst']
    yfirst = grid_params['yfirst']
    xinc = grid_params['xinc']
    yinc = grid_params['yinc']

    # Read variable criteria from CSV file
    csv_file = conventions_dir / 'ISMIP7_variable_request.csv'
    if not csv_file.exists():
        print(f"Warning: {csv_file} not found")
        variables = {}
    else:
        variables = read_variable_criteria(str(csv_file), include_non_mandatory)

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

    # 4D variables with vertical z axis (e.g. litemp)
    xyzt_vars = {var: info for var, info in variables.items()
                if info['dimensions'] == ['x', 'y', 'z', 't']}

    # Static 2D spatial variables (e.g. ref_geoid)
    static_vars = {var: info for var, info in variables.items()
                  if info['dimensions'] == ['x', 'y']}

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
                # End of year: Jan 1 of next year (ISMIP7 convention)
                time_days = []
                time_bounds = None
                for i in range(nyears):
                    year = start_year + i
                    dt = datetime(year + 1, 1, 1).date()
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
                # Default to state variable timing (Jan 1 of next year)
                time_days = []
                time_bounds = None
                for i in range(nyears):
                    year = start_year + i
                    dt = datetime(year + 1, 1, 1).date()
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

            data = generate_synthetic_data((nyears, ny, nx), min_val, max_val, rng=rng)

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

    # Process x,y,z,t variables (4D snapshots, e.g. litemp)
    if include_xyt:
        _SNAPSHOT_NOMINAL_YEARS = {1900, 2000, 2100, 2200, 2300}
        end_year = start_year + nyears - 1
        snap_set = {end_year} | {y for y in _SNAPSHOT_NOMINAL_YEARS if start_year <= y <= end_year}
        if scenario == 'historical':
            snap_set.add(start_year)
        snapshot_years = sorted(snap_set)
        origin = datetime(1850, 1, 1).date()

        for var_name, var_info in xyzt_vars.items():
            # ST only for x,y,z,t variables per ISMIP7 spec
            time_days = [float((datetime(y + 1, 1, 1).date() - origin).days) for y in snapshot_years]
            time_coord = np.array(time_days, dtype=np.float32)
            n_snapshots = len(snapshot_years)

            min_val = var_info.get(val_key_min)
            max_val = var_info.get(val_key_max)
            if min_val is None and max_val is None:
                min_val, max_val = -1e6, 1e6
            else:
                if min_val is None:
                    min_val = max_val - 1.0
                if max_val is None:
                    max_val = min_val + 1.0
            if min_val >= max_val:
                max_val = min_val + 1.0

            data = generate_synthetic_data((n_snapshots, nz, ny, nx), min_val, max_val, rng=rng)

            data_vars = {
                var_name: (
                    ('time', 'z', 'y', 'x'),
                    data.astype(np.float32),
                    {
                        'long_name': var_info['description'],
                        'units': var_info['units'],
                        'standard_name': var_info['standard_name'],
                    }
                )
            }

            z = np.arange(nz, dtype=np.float32)
            coords = {
                'x': ('x', x, {'long_name': 'x-coordinate', 'units': 'm'}),
                'y': ('y', y, {'long_name': 'y-coordinate', 'units': 'm'}),
                'z': ('z', z, {'long_name': 'z-coordinate', 'units': '1'}),
                'time': ('time', time_coord, {'long_name': 'time', 'units': 'days since 1850-01-01', 'calendar': 'standard'}),
            }

            ds = xr.Dataset(data_vars, coords=coords)
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

            snap_time_range = f"{start_year}-{end_year}"
            snap_filename_template = (
                f"{domain_id}_{source_id}_{ism_id}_{ism_member_id}_{esm_id}_{forcing_member_id}_"
                f"{experiment_id}_{set_counter}_{snap_time_range}.nc"
            )
            filename = f"{var_name}_{snap_filename_template}"
            output_path = output_dir / filename

            encoding = {
                var_name: {'dtype': 'f4', '_FillValue': fillval},
                'time': {'dtype': 'f4', '_FillValue': fillval},
            }

            ds.to_netcdf(output_path, unlimited_dims=('time',), encoding=encoding)
            with netCDF4.Dataset(output_path, 'a') as nc:
                nc[var_name].missing_value = fillval
            created_files.append(str(output_path))

    # Process static x,y variables (e.g. ref_geoid)
    if include_xyt:
        for var_name, var_info in static_vars.items():
            min_val = var_info.get(val_key_min)
            max_val = var_info.get(val_key_max)
            if min_val is None and max_val is None:
                min_val, max_val = -1e6, 1e6
            else:
                if min_val is None:
                    min_val = max_val - 1.0
                if max_val is None:
                    max_val = min_val + 1.0
            if min_val >= max_val:
                max_val = min_val + 1.0

            data = generate_synthetic_data((ny, nx), min_val, max_val, rng=rng)

            data_vars = {
                var_name: (
                    ('y', 'x'),
                    data.astype(np.float32),
                    {
                        'long_name': var_info['description'],
                        'units': var_info['units'],
                        'standard_name': var_info['standard_name'],
                    }
                )
            }

            coords = {
                'x': ('x', x, {'long_name': 'x-coordinate', 'units': 'm'}),
                'y': ('y', y, {'long_name': 'y-coordinate', 'units': 'm'}),
            }

            ds = xr.Dataset(data_vars, coords=coords)
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

            # Static field: use 0000-0000 as year-range placeholder (checker skips this check)
            static_filename_template = (
                f"{domain_id}_{source_id}_{ism_id}_{ism_member_id}_{esm_id}_{forcing_member_id}_"
                f"{experiment_id}_{set_counter}_0000-0000.nc"
            )
            filename = f"{var_name}_{static_filename_template}"
            output_path = output_dir / filename

            encoding = {var_name: {'dtype': 'f4', '_FillValue': fillval}}

            ds.to_netcdf(output_path, unlimited_dims=(), encoding=encoding)
            with netCDF4.Dataset(output_path, 'a') as nc:
                nc[var_name].missing_value = fillval
            created_files.append(str(output_path))

    # Process scalar variables
    if include_scalars:
        for var_name, var_info in scalar_vars.items():
            var_type = var_info['type']

            # Select appropriate time coordinate (days since 1850)
            origin = datetime(1850, 1, 1).date()
            if var_type == 'ST':
                # End of year: Jan 1 of next year (ISMIP7 convention)
                time_days = []
                time_bounds = None
                for i in range(nyears):
                    year = start_year + i
                    dt = datetime(year + 1, 1, 1).date()
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
                # Default to state variable timing (Jan 1 of next year)
                time_days = []
                time_bounds = None
                for i in range(nyears):
                    year = start_year + i
                    dt = datetime(year + 1, 1, 1).date()
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
            data = generate_synthetic_data((nyears,), min_val, max_val, rng=rng).astype(np.float32)  # Wide range for scalar data
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
                          include_xyt=True, include_non_mandatory=False,
                          seed=DEFAULT_SEED):
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
        conventions_dir = data_dir()

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
                output_root=output_dir,
                include_scalars=(i == 0),
                include_xyt=include_xyt,
                include_non_mandatory=include_non_mandatory,
                seed=seed + i,
             )
            total_files += len(created_files)

    print(f"Total files created: {total_files}")


def main():
    """Command-line entry point for `ismip7-generate-test-files`."""
    # Get available grids
    conventions_directory = data_dir()
    available_grids = get_available_grids(conventions_directory)

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
        help='Write spatial variables: x,y,t (3D), x,y,z,t (4D snapshot), and x,y (static)'
    )
    parser.add_argument(
        '--include-non-mandatory',
        action='store_true',
        help='Include non-mandatory variables from the ISM CSV variable list'
    )
    parser.add_argument(
        '--multiple',
        action='store_true',
        help='Generate multiple test files with all available grids'
    )
    parser.add_argument(
        '--conventions-dir',
        default=str(conventions_directory),
        help=f'Path to conventions directory (default: {conventions_directory})'
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
        '--seed',
        type=int,
        default=DEFAULT_SEED,
        help=f'Seed for the synthetic data (default: {DEFAULT_SEED}); the same '
             f'seed always produces the same values'
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
        return

    if args.multiple:
        create_multiple_files(conventions_dir=args.conventions_dir,
                              start_year=args.start_year,
                              include_xyt=args.xyt,
                              include_non_mandatory=args.include_non_mandatory,
                              seed=args.seed)
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
            seed=args.seed,
        )


if __name__ == '__main__':
    main()
