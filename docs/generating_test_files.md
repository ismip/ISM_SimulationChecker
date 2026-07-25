# ISMIP7 NetCDF generator

`ismip7-generate-test-files` creates ISMIP7-style NetCDF test files with synthetic data, one file per variable, following the naming convention and grid definitions used by the compliance checker. It is part of the `isschecker` package (`isschecker.generate`), so it is installed along with the checker and can be run from any directory.

Files are written to `Models/{GrIS|AIS}/ISMIP7/SYNTH1/CORE/{set_counter}/` (default `C001`) beneath the current working directory.

## Usage

```bash
conda activate isschecker
ismip7-generate-test-files [OPTIONS]
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
| `--seed` | `0` | Seed for the synthetic data; the same seed always produces the same values |
| `--list-grids` | — | List all available grids and exit |

## Examples

```bash
# List available grids
ismip7-generate-test-files --list-grids

# Generate 286-year GrIS ctrl files (x,y,t variables)
ismip7-generate-test-files --grid GrIS_16000m --scenario ctrl \
  --xyt --nyears 286 --start-year 2015

# Generate 286-year AIS ssp370 files
ismip7-generate-test-files --grid AIS_08000m --scenario ssp370 \
  --xyt --nyears 286 --start-year 2015

# Generate scalar-only variables
ismip7-generate-test-files --grid GrIS_16000m --scenario ctrl \
  --scalars --nyears 286 --start-year 2015

# Generate both 3D and scalar variables, including non-mandatory ones
ismip7-generate-test-files --grid GrIS_16000m --scenario ctrl \
  --xyt --scalars --include-non-mandatory --nyears 286 --start-year 2015

# Generate testdata for ismip7-scalar-processing
ismip7-generate-test-files --grid AIS_16000m --scenario historical \
  --set-counter C001 --xyt --include-non-mandatory --nyears 1  --start-year 2014 
ismip7-generate-test-files --grid AIS_16000m --scenario ssp585 \
  --set-counter C007 --xyt --include-non-mandatory --nyears 286 --start-year 2015
ismip7-generate-test-files --grid GrIS_16000m --scenario historical \
  --set-counter C001 --xyt --include-non-mandatory --nyears 55  --start-year 1960
ismip7-generate-test-files --grid GrIS_16000m --scenario ctrl \
  --set-counter C009 --xyt --include-non-mandatory --nyears 286 --start-year 2015
```

## Implemented conventions

- CF-1.7 as baseline.
- Time encoding: `days since 1850-01-01`, `calendar='standard'`.
  - State (ST) variables: timestamp is Jan 1 of year N+1 (end-of-year snapshot). No `time_bounds`.
  - Flux (FL) variables: timestamp is Jul 1 of year N (mid-year), with `time_bounds` = [Jan 1 of N, Jan 1 of N+1].
  - `x,y,z,t` variables (e.g. `litemp`): ST snapshots at a sparse set of nominal years. For `historical`: first year of run, 1900 (if in range), 2000 (if in range), last year of run. For projection scenarios: 2100, 2200, 2300 (each if within the simulation year range). The filename year range reflects the full simulation period, not the first/last snapshot year.
- Single precision (`float32`) for all variables and time.
- `_FillValue` and `missing_value` set to NetCDF4 default `f4` fill value.
- `time` is an unlimited (record) dimension.
- `x` and `y` are 1-D coordinate variables in metres.
- CRS set per domain: GrIS → `EPSG:3413`, AIS → `EPSG:3031`.

## Notes

- Variable metadata is read from `ISMIP7_variable_request.csv` and grid definitions from `gdfs/`, both bundled as package data in `isschecker/data/`. Use `--conventions-dir` to point at a different directory (it must contain the CSV and a `gdfs/` subdirectory).
- `group`, `model`, `contact_name`, and `contact_email` are hardcoded in `create_netcdf_file()` to synthetic defaults — edit there to customise.
- Generated files are synthetic and intended for testing the compliance checker, not for scientific use.
- Data values are drawn from a seeded generator, so a given `--seed` reproduces the same files. With `--multiple`, each file uses `seed + i` so the files differ from one another while the run as a whole stays reproducible.
