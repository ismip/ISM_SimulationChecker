# Ice Sheet Simulation Compliance Checker

Checks ISMIP7 NetCDF simulation datasets for compliance with the [ISMIP7 data request conventions](https://www.ismip.org/). The following categories are validated for every file:

1. **Naming** — variable name, region field, ISM member id (`mNNN`), ESM name (CMIP6/CMIP7 registry), forcing member id (`fNNN`), set counter (`[C|E|P]NNN`), and year range (`YYYY-YYYY` matching the actual time axis).
2. **Numerical** — units match the data request; all values lie within the allowed min/max range for the relevant region; array is not entirely fill values.
3. **Spatial** *(xyt variables only)* — grid corners lie within the expected AIS or GrIS extents; resolution is one of the allowed values; x and y cell size are equal.
4. **Time** — time dimension is present, unlimited, and monotonically increasing; annual cadence; experiment start/end dates and duration match `experiments_ismip7.csv`, accounting for the variable type (ST or FL, see [Time encoding](#time-encoding)).
5. **Attributes** — required global and coordinate attributes are present and have correct values; `standard_name` matches data request; `_FillValue` equals the NetCDF4 default for the variable's dtype; variable and time are float32; `scale_factor` and `add_offset` are not allowed.

Compliance criteria are defined in `conventions/ISMIP7_variable_request.csv` (variable metadata) and `experiments_ismip7.csv` (valid experiment year ranges and durations).

---

## Time encoding

ISMIP7 uses the standard (Gregorian) CF calendar with time recorded as **days since 1850-01-01 00:00:00**. The encoding convention differs by variable type:

| Variable type | Time coordinate | Time bounds |
|---|---|---|
| **State (ST)** — snapshots | Jan 1 of year N+1 (= end of year N) | none |
| **Flux (FL)** — annual averages | Jul 1 of year N (mid-year) | Jan 1 of year N → Jan 1 of year N+1 |

For example, a 286-year `ctrl` simulation covering nominal years 2015–2300:
- ST files carry timestamps `2016-01-01` … `2301-01-01`
- FL files carry timestamps `2015-07-01` … `2300-07-01`, with bounds `[2015-01-01, 2016-01-01]` … `[2300-01-01, 2301-01-01]`

The filename year range (`YYYY-YYYY`) always refers to the **nominal simulation years** (2015–2300 in the example above), regardless of variable type. The checker accounts for this when validating the filename against the time axis.

Reference lookup tables are available in the companion repository [`ismip7-time-encoding`](https://github.com/ismip/ismip7-time-encoding).

---

## Setup

```bash
conda env create -f isschecker_env.yml
conda activate isschecker
```

Dependencies: Python 3.14, `numpy` 2.4, `pandas` 3.0, `xarray` 2026.4, `cftime` 1.6, `netCDF4` 1.7, `tqdm` 4.67.

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

`experiments_ismip7.csv` defines the allowed nominal year ranges and durations for each experiment. The checker derives the expected FL and ST timestamps from these year values at runtime (see [Time encoding](#time-encoding)).

---

## Generating synthetic test files

`generate/generate_test_files.py` creates ISMIP7-style NetCDF test files with synthetic data. See [generate/README.md](generate/README.md) for full options and examples.

```bash
conda activate isschecker

# Generate 286-year GrIS ctrl xyt variables
python generate/generate_test_files.py --grid GrIS_16000m --scenario ctrl --xyt --nyears 286 --start-year 2015

# Generate 286-year AIS ctrl scalar variables
python generate/generate_test_files.py --grid AIS_16000m --scenario ctrl --scalars --nyears 286 --start-year 2015

# List available grids
python generate/generate_test_files.py --list-grids
```

---

## Running Tests

The regression suite uses `pytest` and creates temporary synthetic datasets, then mutates them to verify expected checker failures for naming, missing variables, time-axis problems, and missing attributes.

```bash
pytest -v tests/test_compliance_checker.py
```

If you want to retain the files generated during testing you can use:
```
pytest -v tests/test_compliance_checker.py --basetemp=/tmp/pytest_tmp
```
The files will then be left in `/tmp/pytest_tmp`.  Otherwise, they are cleaned up once tests pass.
