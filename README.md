# Ice Sheet Simulation Compliance Checker

Checks ISMIP7 NetCDF simulation datasets for compliance with the [ISMIP7 data request conventions](https://www.ismip.org/). The following categories are validated for every file:

1. **Naming** — variable name, region field, ISM member id (`mNNN`), ESM name (CMIP6/CMIP7 registry), forcing member id (`fNNN`), set counter (`[C|E|P]NNN`), and year range (`YYYY-YYYY` matching the actual time axis).
2. **Numerical** — units match the data request; all values lie within the allowed min/max range for the relevant region; array is not entirely fill values.
3. **Spatial** *(xyt variables only)* — grid corners lie within the expected AIS or GrIS extents; resolution is one of the allowed values; x and y cell size are equal.
4. **Time** — time dimension is present, unlimited, and monotonically increasing; annual cadence; experiment end date and duration match `experiments_ismip7.csv`.
5. **Attributes** — required global and coordinate attributes are present and have correct values; `standard_name` matches data request; `_FillValue` equals the NetCDF4 default for the variable's dtype; variable and time are float32; `scale_factor` and `add_offset` are not allowed.

Compliance criteria are defined in `conventions/ISMIP7_variable_request.xlsx` (variable metadata) and `experiments_ismip7.csv` (valid experiment date ranges).

---

## Setup

```bash
conda env create -f isschecker_env.yml
conda activate isschecker
```

Dependencies: Python 3.14, `numpy` 2.4, `pandas` 3.0, `openpyxl` 3.1, `xarray` 2026.4, `cftime` 1.6, `netCDF4` 1.7, `tqdm` 4.67.

---

## Running the checker

The script must be run from the repository root. It writes `compliance_checker_log.txt` into the `--source-path` directory.

```bash
# Check x,y,t (3D spatial) variables
python compliance_checker.py --source-path ./Models/GrIS/ISMIP7/SYNTH1/CORE --variable-list ismip7_xyt

# Check scalar (time-only) variables
python compliance_checker.py --source-path ./Models/AIS/ISMIP7/SYNTH1/CORE --variable-list ismip7_scalars

# Check both
python compliance_checker.py --source-path ./Models/GrIS/ISMIP7/SYNTH1/CORE --variable-list ismip7
```

| Option | Default | Description |
|--------|---------|-------------|
| `--source-path` | `./Models/GrIS/ISMIP7/SYNTH1/CORE` | Directory containing `.nc` files to check |
| `--variable-list` | `ismip7_scalars` | `ismip7_xyt`, `ismip7_scalars`, or `ismip7` (both) |

---

## Generating synthetic test files

`test/generate_test_files.py` creates ISMIP7-style NetCDF test files with synthetic data. See [test/README.md](test/README.md) for full options and examples.

```bash
conda activate isschecker

# Generate 286-year GrIS ctrl xyt variables
python test/generate_test_files.py --grid GrIS_16000m --scenario ctrl --xyt --nyears 286 --start-year 2015

# Generate 286-year AIS ctrl scalar variables
python test/generate_test_files.py --grid AIS_16000m --scenario ctrl --scalars --nyears 286 --start-year 2015

# List available grids
python test/generate_test_files.py --list-grids
```
