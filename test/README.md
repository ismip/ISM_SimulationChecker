# ISMIP7 NetCDF generator

`test/generate_test_files.py` creates ISMIP7-style NetCDF test files with synthetic data, one file per variable, following the naming convention and grid definitions used by the compliance checker.

Files are written to `Models/{GrIS|AIS}/ISMIP7/SYNTH1/CORE/`.

## Usage

```bash
conda activate isschecker
python test/generate_test_files.py [OPTIONS]
```

## Key options

| Option | Default | Description |
|--------|---------|-------------|
| `--grid` | `GrIS_16000m` | Grid to use (run `--list-grids` to see all available) |
| `--scenario` | `ctrl` | Experiment name written into filenames and the time axis |
| `--start-year` | `2015` | First year of the time axis |
| `--nyears` | `5` | Number of annual time steps |
| `--xyt` | off | Include x,y,t (3D) variables |
| `--scalars` | off | Include scalar (time-only) variables |
| `--include-non-mandatory` | off | Also generate non-mandatory variables |
| `--ism-member-id` | `m001` | ISM ensemble member id (written into filenames) |
| `--esm-id` | `CESM2-WACCM` | ESM id (written into filenames) |
| `--forcing-member-id` | `f001` | Forcing ensemble member id (written into filenames) |
| `--set-counter` | `C001` | Set counter id (written into filenames) |
| `--list-grids` | — | List all available grids and exit |

## Examples

```bash
# List available grids
python test/generate_test_files.py --list-grids

# Generate 286-year GrIS ctrl files (x,y,t variables)
python test/generate_test_files.py --grid GrIS_16000m --scenario ctrl \
  --xyt --nyears 286 --start-year 2015

# Generate 286-year AIS ssp370 files
python test/generate_test_files.py --grid AIS_08000m --scenario ssp370 \
  --xyt --nyears 286 --start-year 2015

# Generate scalar-only variables
python test/generate_test_files.py --grid GrIS_16000m --scenario ctrl \
  --scalars --nyears 286 --start-year 2015

# Generate both 3D and scalar variables, including non-mandatory ones
python test/generate_test_files.py --grid GrIS_16000m --scenario ctrl \
  --xyt --scalars --include-non-mandatory --nyears 286 --start-year 2015
```

## Implemented conventions

- CF-1.7 as baseline.
- Time encoding: `days since 1850-01-01`, `calendar='standard'`.
  - State (ST) variables: snapshot at year end (Dec 31).
  - Flux (FL) variables: mid-year (Jul 1) with bounds from Jan 1 to Jan 1 next year.
- Single precision (`float32`) for all variables and time.
- `_FillValue` and `missing_value` set to NetCDF4 default `f4` fill value.
- `time` is an unlimited (record) dimension.
- `x` and `y` are 1-D coordinate variables in metres.
- CRS set per domain: GrIS → `EPSG:3413`, AIS → `EPSG:3031`.

## Notes

- Variable metadata is read from `conventions/ISMIP7_variable_request.xlsx`; grid definitions from the top-level `gdfs/` directory.
- `group`, `model`, `contact_name`, and `contact_email` are hardcoded in `create_netcdf_file()` to synthetic defaults — edit there to customise.
- Generated files are synthetic and intended for testing the compliance checker, not for scientific use.
