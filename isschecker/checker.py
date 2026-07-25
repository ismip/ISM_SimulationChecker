#
# ISMIP7 Compliance Checker — check summary
#
# 1. Naming (_check_naming, _check_file_variables)
#    - Variable name matches the expected ISMIP7 name from the data request.
#    - The variable named in the filename is present in the file.
#    - The file holds no variables beyond that one, its coordinates, and any
#      bounds or grid-mapping variables they refer to.
#    - Region field in filename matches the region inferred from the grid (AIS/GrIS).
#    - ISM member id (field 4) matches format mNNN (e.g. m001).
#    - ESM name (field 5) is a recognised CMIP6/CMIP7 model name.
#    - Forcing member id (field 6) matches format fNNN (e.g. f001).
#    - Set counter (field 8) matches format [C|E|P]NNN (e.g. C001, E041, P132).
#    - Year range (field 9) matches format YYYY-YYYY; start <= end; both match the actual time axis.
#
# 2. Numerical (_check_numerical)
#    - Variable units match the data request (any UDUNITS spelling of the
#      requested unit is accepted: 'm2', 'm^2' and 'm**2' are all the same).
#    - All values lie within the allowed min/max range for the relevant region.
#    - Array is not entirely fill/missing values.
#
# 3. Spatial (_check_spatial)  [xyt variables only]
#    - Lower-left and upper-right grid corners lie within the expected AIS or GrIS extents.
#    - Grid resolution is one of the allowed values (1, 2, 4, 8, 16, 32 km).
#    - x and y resolution are equal (square cells).
#
# 4. Time (_check_time)
#    - Time dimension is present, is an unlimited (record) dimension, and its values are monotonically increasing.
#    - Time step matches the expected annual cadence (within tolerance).
#    - Experiment end date matches experiments_ismip7.csv; duration >= 1 year for historical, exact for others.
#
# 5. Attributes (_check_attributes)
#    - Global attributes present: group, model, contact_name, contact_email, crs
#      (epsg:3413 for GrIS, epsg:3031 for AIS).
#    - Coordinate attributes: time has units, calendar, bounds (FL vars); x/y have units (xyt).
#    - Variable standard_name matches data request (if specified).
#    - _FillValue must be present and equal the default netCDF4 fill value for the variable's dtype.
#      If missing_value is also present, it must equal _FillValue.
#    - Main variable and time coordinate are single-precision float (float32 / f4).
#    - scale_factor and add_offset are not allowed on the main variable.


import datetime
import difflib
import os
import re
import subprocess
import argparse
from importlib import metadata, resources

import numpy as np
import pandas as pd
import xarray as xr
import netCDF4
from tqdm import tqdm


try:
    __version__ = metadata.version("isschecker")
except metadata.PackageNotFoundError:
    # Running from a source tree that has not been installed.
    __version__ = "unknown"

DEFAULT_SOURCE_PATH = "./Models/GrIS/ISMIP7/SYNTH1/CORE/C001"
DEFAULT_VARIABLE_LIST = "ismip7_scalars"
VARIABLE_LIST_CHOICES = ("ismip7_scalars", "ismip7_xyt", "ismip7")

VARIABLE_REQUEST_CSV = "ISMIP7_variable_request.csv"

EXPERIMENTS_ISMIP7_CSV_FILENAME = "experiments_ismip7.csv"


DATA_PACKAGE = f"{__package__}.data"


def _read_data_csv(filename: str, **kwargs) -> pd.DataFrame:
    """Read a CSV bundled as package data in :data:`DATA_PACKAGE`."""
    resource = resources.files(DATA_PACKAGE).joinpath(filename)
    with resources.as_file(resource) as path:
        return pd.read_csv(path, **kwargs)

AIS_GRID_EXTENT = [-3040000, -3040000, 3040000, 3040000]
GrIS_GRID_EXTENT = [-720000, -3450000, 960000, -570000]
AIS_POSSIBLE_RESOLUTION = [2, 4, 8, 16, 32]
GrIS_POSSIBLE_RESOLUTION = [1, 2, 4, 8, 16, 32]

TIME_STEP_MIN_DAYS = 365
TIME_STEP_MAX_DAYS = 366

# ISMIP7 CORE file naming convention:
# {var}_{region}_{group}_{model}_{modelid}_{ESM}_{forcingid}_{experiment}_{configid}_{startyear}-{endyear}.nc
ISMIP7_FILENAME_PARTS = 10
ISMIP7_FILENAME_VAR_IDX = 0
ISMIP7_FILENAME_REGION_IDX = 1
ISMIP7_FILENAME_ISM_MEMBER_IDX = 4
ISMIP7_FILENAME_ESM_IDX = 5
ISMIP7_FILENAME_FORCING_MEMBER_IDX = 6
ISMIP7_FILENAME_EXPERIMENT_IDX = 7
ISMIP7_FILENAME_SET_COUNTER_IDX = 8
ISMIP7_FILENAME_YEAR_RANGE_IDX = 9

# Known CMIP6 and CMIP7 model names valid as ESM forcing identifiers (field 5).
VALID_ESM_NAMES: set[str] = {
    # CMIP6
    "ACCESS-CM2", "ACCESS-ESM1-5",
    "AWI-CM-1-1-MR", "AWI-ESM-1-1-LR",
    "BCC-CSM2-MR", "BCC-ESM1",
    "CAMS-CSM1-0",
    "CAS-ESM2-0",
    "CESM2", "CESM2-FV2", "CESM2-WACCM", "CESM2-WACCM-FV2",
    "CIESM",
    "CMCC-CM2-HR4", "CMCC-CM2-SR5", "CMCC-ESM2",
    "CNRM-CM6-1", "CNRM-CM6-1-HR", "CNRM-ESM2-1",
    "CanESM5", "CanESM5-1", "CanESM5-CanOE",
    "E3SM-1-0", "E3SM-1-1", "E3SM-1-1-ECA", "E3SM-2-0",
    "EC-Earth3", "EC-Earth3-AerChem", "EC-Earth3-CC", "EC-Earth3-Veg", "EC-Earth3-Veg-LR",
    "FGOALS-f3-L", "FGOALS-g3",
    "FIO-ESM-2-0",
    "GFDL-CM4", "GFDL-ESM4",
    "GISS-E2-1-G", "GISS-E2-1-G-CC", "GISS-E2-1-H", "GISS-E2-2-G", "GISS-E2-2-H",
    "HadGEM3-GC31-LL", "HadGEM3-GC31-MM",
    "IITM-ESM",
    "INM-CM4-8", "INM-CM5-0",
    "IPSL-CM5A2-INCA", "IPSL-CM6A-LR", "IPSL-CM6A-LR-INCA",
    "KACE-1-0-G",
    "KIOST-ESM",
    "MCM-UA-1-0",
    "MIROC-ES2H", "MIROC-ES2L", "MIROC6",
    "MPI-ESM-1-2-HAM", "MPI-ESM1-2-HR", "MPI-ESM1-2-LR",
    "MRI-ESM2-0",
    "NESM3",
    "NorCPM1", "NorESM2-LM", "NorESM2-MM",
    "SAM0-UNICON",
    "TaiESM1",
    "UKESM1-0-LL", "UKESM1-1-LL",
    # CMIP7 (extend as models are registered)
    "ACCESS-ESM2-0",
    "CanESM6",
    "CESM3",
    "CNRM-CM7", "CNRM-ESM2-2",
    "EC-Earth4",
    "GFDL-ESM5",
    "GISS-E3",
    "HadGEM4-GC51-LL",
    "IPSL-CM7A-LR",
    "MIROC7",
    "MPI-ESM2-0",
    "MRI-ESM3-0",
    "NorESM3-LM", "NorESM3-MM",
    "UKESM2-0-LL",
}


def main() -> None:
    args = _parse_args()
    source_path = args.source_path
    variable_list = args.variable_list

    run_checker(
        source_path=source_path,
        variable_list=variable_list,
    )


def run_checker(
    source_path: str,
    variable_list: str = DEFAULT_VARIABLE_LIST,
    version: str | None = None,
):
    version = _describe_version() if version is None else version
    experiments_ismip7 = _load_experiments_csv()
    ismip_meta, ismip_var, mandatory_variables = _load_criteria(variable_list)

    summary = _run_compliance_checker(
        source_path=source_path,
        version=version,
        ismip_meta=ismip_meta,
        ismip_var=ismip_var,
        mandatory_variables=mandatory_variables,
        experiments=experiments_ismip7,
        criteria_file=VARIABLE_REQUEST_CSV,
    )

    log_path = os.path.join(source_path, "compliance_checker_log.txt")
    log_text = ""
    if os.path.exists(log_path):
        with open(log_path, "r") as log_file:
            log_text = log_file.read()

    summary["log_path"] = log_path
    summary["log_text"] = log_text
    return summary


def _describe_version() -> str:
    """Describe which checker produced a log.

    The installed version, plus the git commit when the package is being run
    from a checkout (a source or editable install).
    """
    commit = _git_commit()
    return __version__ if commit is None else f"{__version__} (git {commit})"


def _git_commit() -> str | None:
    """Return the short git commit of the checkout this module lives in.

    Deliberately keyed to the location of this file rather than the working
    directory: the log records which checker ran, not which repository the user
    happened to be standing in.  Returns None for a non-editable install, where
    there is no checkout to describe.
    """
    package_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        process = subprocess.run(
            ["git", "-C", package_dir, "log", "--pretty=format:%h", "-n", "1"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        # git is not installed
        return None
    if process.returncode != 0:
        return None
    return process.stdout.strip() or None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check simulation NetCDF datasets for ISMIP compliance."
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show the installed isschecker version and exit.",
    )
    parser.add_argument(
        "--source-path",
        default=DEFAULT_SOURCE_PATH,
        help="Path to the directory containing the CORE NetCDF files.",
    )
    parser.add_argument(
        "--variable-list",
        choices=VARIABLE_LIST_CHOICES,
        default=DEFAULT_VARIABLE_LIST,
        help="Variable list to apply: ismip7_xyt, ismip7_scalars, or ismip7 (both).",
    )
    return parser.parse_args()


def _load_criteria(variable_list: str):
    try:
        df = _read_data_csv(VARIABLE_REQUEST_CSV)
    except (IOError, ModuleNotFoundError):
        print(
            "ERROR: Unable to open the variable request file "
            + VARIABLE_REQUEST_CSV
            + f" bundled in {DATA_PACKAGE}. Is the package installed correctly?"
        )
        raise

    df = df.dropna(subset=["Variable Name"])

    if variable_list == "ismip7_xyt":
        df = df[df["Dim"].isin(["x,y,t", "x,y,z,t", "x,y"])]
    elif variable_list == "ismip7_scalars":
        df = df[df["Dim"] == "t"]

    ismip_meta = []
    for _, row in df.iterrows():
        entry = {
            "variable": row["Variable Name"],
            "dim": str(row["Dim"]),
            "units": str(row["units"]) if pd.notna(row["units"]) else "",
            "mandatory": 1 if str(row["Mandatory (yes/no)"]).lower() == "yes" else 0,
            "standard_name": str(row["standard_name"]) if pd.notna(row["standard_name"]) else None,
            "type": str(row["Type"]) if pd.notna(row["Type"]) else "",
        }
        for col in df.columns:
            lc = str(col).lower()
            if lc.startswith("min_") or lc.startswith("max_"):
                try:
                    val = row[col]
                    entry[lc] = None if pd.isna(val) else float(val)
                except Exception:
                    entry[lc] = None
        ismip_meta.append(entry)

    ismip_var = [d["variable"] for d in ismip_meta]
    ismip_mandatory_var = [d["variable"] for d in ismip_meta if d["mandatory"] == 1]
    return ismip_meta, ismip_var, ismip_mandatory_var


def _load_experiments_csv(filename: str = EXPERIMENTS_ISMIP7_CSV_FILENAME):
    experiments = []
    frame = _read_data_csv(filename, delimiter=";")
    for _, row in frame.iterrows():
        experiments.append(
            {
                "experiment":    row["experiment"],
                "start_year_min": int(row["start_year_min"]),
                "start_year_max": int(row["start_year_max"]),
                "end_year":      int(row["end_year"]),
                "duration":      int(row["duration"]),
            }
        )
    return experiments


def _nominal_to_timestamp(year: int, var_type: str) -> datetime.datetime:
    """Return the expected encoded timestamp for a nominal simulation year.

    ST variables: Jan 1 of the following year (end-of-year snapshot).
    FL variables: Jul 1 of the same year (mid-year average).
    """
    if var_type == "ST":
        return datetime.datetime(year + 1, 1, 1)
    return datetime.datetime(year, 7, 1)


def _run_compliance_checker(
    source_path: str,
    version: str,
    ismip_meta,
    ismip_var,
    mandatory_variables,
    experiments,
    criteria_file,
):
    if not os.path.isdir(source_path):
        print(f"ERROR: Directory not found: '{source_path}'. Please check your --source-path argument.")
        return _empty_summary()

    try:
        with open(os.path.join(source_path, "compliance_checker_log.txt"), "w") as f:
            print("-> Checking " + source_path)
            print()
            today = datetime.date.today()
            _write_log_header(f, version, source_path, today, criteria_file)

            experiment_groups = _group_files_by_experiment(source_path)
            if not experiment_groups:
                msg = f"No .nc files found in directory '{source_path}'. Please check your --source-path argument."
                print(f"ERROR: {msg}")
                f.write(f"ERROR: {msg}\n")
                return _empty_summary()

            summary = _process_experiments(
                log_file=f,
                source_path=source_path,
                experiment_groups=experiment_groups,
                mandatory_variables=mandatory_variables,
                experiments=experiments,
                ismip_var=ismip_var,
                ismip_meta=ismip_meta,
            )

        _insert_synthesis(
            source_path=source_path,
            exp_counter=summary["exp_counter"],
            file_counter=summary["file_counter"],
            total_errors=summary["total_errors"],
            total_file_errors=summary["total_file_errors"],
            total_naming_errors=summary["total_naming_errors"],
            total_num_errors=summary["total_num_errors"],
            total_spatial_errors=summary["total_spatial_errors"],
            total_time_errors=summary["total_time_errors"],
            total_attr_errors=summary["total_attr_errors"],
            report_naming_issues=summary["report_naming_issues"],
        )
        return summary

    except TypeError as err:
        print(
            "Something went wrong with your dataset. Please, check your file(s) carefully. Error:",
            err,
        )
        return _empty_summary()


def _empty_summary() -> dict:
    return {
        "exp_counter": 0,
        "file_counter": 0,
        "total_errors": 0,
        "total_naming_errors": 0,
        "total_num_errors": 0,
        "total_spatial_errors": 0,
        "total_time_errors": 0,
        "total_attr_errors": 0,
        "total_file_errors": 0,
        "report_naming_issues": [],
    }


def _group_files_by_experiment(source_path: str) -> dict:
    groups = {}
    for f in sorted(os.listdir(source_path)):
        if not f.endswith(".nc"):
            continue
        parts = f.split("_")
        exp_name = parts[ISMIP7_FILENAME_EXPERIMENT_IDX] if len(parts) == ISMIP7_FILENAME_PARTS else "_unknown"
        if exp_name not in groups:
            groups[exp_name] = []
        groups[exp_name].append(f)
    return groups


def _process_experiments(
    log_file,
    source_path: str,
    experiment_groups: dict,
    mandatory_variables,
    experiments,
    ismip_var,
    ismip_meta,
):
    total_naming_errors = 0
    total_num_errors = 0
    total_spatial_errors = 0
    total_time_errors = 0
    total_attr_errors = 0
    total_file_errors = 0
    report_naming_issues = []

    file_counter = 0
    exp_counter = 0
    for experiment_name, exp_files in experiment_groups.items():
        exp_counter += 1

        exp_summary = _process_single_experiment(
            log_file=log_file,
            source_path=source_path,
            experiment_name=experiment_name,
            exp_files=exp_files,
            mandatory_variables=mandatory_variables,
            experiments=experiments,
            ismip_var=ismip_var,
            ismip_meta=ismip_meta,
            report_naming_issues=report_naming_issues,
        )

        file_counter += exp_summary["file_counter"]
        total_naming_errors += exp_summary["exp_naming_errors"]
        total_num_errors += exp_summary["exp_num_errors"]
        total_spatial_errors += exp_summary["exp_spatial_errors"]
        total_time_errors += exp_summary["exp_time_errors"]
        total_attr_errors += exp_summary["exp_attr_errors"]
        total_file_errors += exp_summary["exp_file_errors"]

        _print_experiment_summary(
            experiment_name=exp_summary["experiment_name"],
            exp_errors=exp_summary["exp_errors"],
        )

    total_errors = (
        total_naming_errors
        + total_num_errors
        + total_spatial_errors
        + total_time_errors
        + total_attr_errors
        + total_file_errors
    )
    _print_total_summary(source_path=source_path, total_errors=total_errors)

    return {
        "exp_counter": exp_counter,
        "file_counter": file_counter,
        "total_errors": total_errors,
        "total_naming_errors": total_naming_errors,
        "total_num_errors": total_num_errors,
        "total_spatial_errors": total_spatial_errors,
        "total_time_errors": total_time_errors,
        "total_attr_errors": total_attr_errors,
        "total_file_errors": total_file_errors,
        "report_naming_issues": report_naming_issues,
    }


def _process_single_experiment(
    log_file,
    source_path: str,
    experiment_name: str,
    exp_files: list,
    mandatory_variables,
    experiments,
    ismip_var,
    ismip_meta,
    report_naming_issues,
):
    exp_naming_errors = 0
    exp_num_errors = 0
    exp_spatial_errors = 0
    exp_time_errors = 0
    exp_attr_errors = 0
    exp_file_errors = 0

    temp_mandatory_var = list(mandatory_variables)
    for i in exp_files:
        variable = i.split("_")[ISMIP7_FILENAME_VAR_IDX]
        if variable in temp_mandatory_var:
            temp_mandatory_var.remove(variable)

    file_counter = 0
    if experiment_name in [dic["experiment"] for dic in experiments]:
        log_file.write("\n ")
        log_file.write("**********************************************************\n")
        log_file.write(" ** Experiment: " + experiment_name + " \n ")
        log_file.write("**********************************************************\n")
        log_file.write("\n ")
        if not temp_mandatory_var:
            log_file.write(
                "Mandatory variables Test: "
                + experiment_name
                + " : all mandatory variables exist. \n"
            )
        else:
            log_file.write(
                "ERROR: In experiment "
                + experiment_name
                + ", these mandatory variable(s) is (are) missing: "
                + str(temp_mandatory_var)
                + "\n"
            )
            exp_file_errors += len(temp_mandatory_var)

        for file in tqdm(exp_files):
            file_counter += 1
            file_summary = _process_single_file(
                log_file=log_file,
                source_path=source_path,
                file=file,
                experiment_name=experiment_name,
                ismip_var=ismip_var,
                ismip_meta=ismip_meta,
                experiments=experiments,
                report_naming_issues=report_naming_issues,
            )

            exp_naming_errors += file_summary["var_naming_errors"]
            exp_num_errors += file_summary["var_num_errors"]
            exp_spatial_errors += file_summary["var_spatial_errors"]
            exp_time_errors += file_summary["var_time_errors"]
            exp_attr_errors += file_summary["var_attr_errors"]

    else:
        log_file.write("\n ")
        log_file.write("**********************************************************\n")
        log_file.write(" **  Experiment: " + experiment_name + " \n ")
        log_file.write("**********************************************************\n")
        log_file.write("\n ")
        log_file.write(
            "ERROR: The compliance check is ignored for experiment "
            + experiment_name
            + " as it is not in "
            + str([exp["experiment"] for exp in experiments])
            + ". \n"
        )
        exp_naming_errors += 1
        report_naming_issues.append(
            "Compliance check ignored : experiment "
            + experiment_name
            + " not in the experiments list."
        )

    exp_errors = (
        exp_time_errors
        + exp_spatial_errors
        + exp_num_errors
        + exp_naming_errors
        + exp_attr_errors
        + exp_file_errors
    )
    return {
        "file_counter": file_counter,
        "experiment_name": experiment_name,
        "exp_errors": exp_errors,
        "exp_naming_errors": exp_naming_errors,
        "exp_num_errors": exp_num_errors,
        "exp_spatial_errors": exp_spatial_errors,
        "exp_time_errors": exp_time_errors,
        "exp_attr_errors": exp_attr_errors,
        "exp_file_errors": exp_file_errors,
    }


def _process_single_file(
    log_file,
    source_path: str,
    file: str,
    experiment_name: str,
    ismip_var,
    ismip_meta,
    experiments,
    report_naming_issues,
):
    var_naming_errors = 0
    var_num_errors = 0
    var_spatial_errors = 0
    var_time_errors = 0
    var_attr_errors = 0

    file_name = os.path.basename(file)
    file_name_split = file_name.split("_")

    considered_variable = file_name_split[ISMIP7_FILENAME_VAR_IDX]
    region = file_name_split[ISMIP7_FILENAME_REGION_IDX]

    try:
        ds = xr.open_dataset(os.path.join(source_path, file),
                             decode_times=False)
    except (ValueError, TypeError) as e:
        log_file.write(" - ERROR: Cannot open " + file_name + ": " + str(e) + "\n")
        var_naming_errors += 1
        return {
            "var_naming_errors": var_naming_errors,
            "var_num_errors": var_num_errors,
            "var_spatial_errors": var_spatial_errors,
            "var_time_errors": var_time_errors,
            "var_attr_errors": var_attr_errors,
        }
    file_variables = list(ds.data_vars)

    if len(file_name_split) != ISMIP7_FILENAME_PARTS:
        log_file.write(
            " - ERROR: the file name "
            + file_name
            + " does not follow the naming convention (expected "
            + str(ISMIP7_FILENAME_PARTS)
            + " underscore-separated fields).\n"
        )
        report_naming_issues.append(
            "Compliance check ignored: file "
            + file_name
            + " does not follow the naming convention."
        )
        var_naming_errors += 1
        return {
            "var_naming_errors": var_naming_errors,
            "var_num_errors": var_num_errors,
            "var_spatial_errors": var_spatial_errors,
            "var_time_errors": var_time_errors,
            "var_attr_errors": var_attr_errors,
        }

    experiment_varname = file_name_split[ISMIP7_FILENAME_EXPERIMENT_IDX]
    if experiment_varname != experiment_name:
        log_file.write(
            " - ERROR: in the file name "
            + file_name
            + ", the experiment name ("
            + experiment_varname
            + ") does not match the expected experiment: "
            + experiment_name
            + ".\n"
        )
        report_naming_issues.append(
            "Compliance check ignored: in the file name "
            + file_name
            + ", the experiment name ("
            + experiment_varname
            + ") does not match the expected experiment: "
            + experiment_name
            + ".\n"
        )
        var_naming_errors += 1
        return {
            "var_naming_errors": var_naming_errors,
            "var_num_errors": var_num_errors,
            "var_spatial_errors": var_spatial_errors,
            "var_time_errors": var_time_errors,
            "var_attr_errors": var_attr_errors,
        }

    if considered_variable in ismip_var:
        var_naming_errors, var_num_errors, var_spatial_errors, var_time_errors, var_attr_errors = (
            _run_variable_checks(
                log_file=log_file,
                ds=ds,
                file_name=file_name,
                considered_variable=considered_variable,
                experiment_name=experiment_name,
                file_variables=file_variables,
                region=region,
                ismip_var=ismip_var,
                ismip_meta=ismip_meta,
                experiments=experiments,
                report_naming_issues=report_naming_issues,
            )
        )

    var_errors = var_naming_errors + var_num_errors + var_spatial_errors + var_time_errors + var_attr_errors

    log_file.write("\n")
    log_file.write("----------------------------------------------------------\n")
    log_file.write(
        experiment_name + " - " + considered_variable + " - File:" + file_name + "\n"
    )
    if var_errors > 0:
        log_file.write(str(var_errors) + " error(s). Please review before sharing.\n")
    else:
        log_file.write("No errors. Good job !\n")
    log_file.write("No warnings.\n")
    log_file.write("----------------------------------------------------------\n")

    return {
        "var_naming_errors": var_naming_errors,
        "var_num_errors": var_num_errors,
        "var_spatial_errors": var_spatial_errors,
        "var_time_errors": var_time_errors,
        "var_attr_errors": var_attr_errors,
    }


def _check_naming(
    log_file,
    ds,
    file_name: str,
    region: str,
    dim: set,
    isscalar: bool,
    report_naming_issues: list,
    var_type: str = "",
) -> int:
    errors = 0

    log_file.write("NAMING Tests \n")

    if not isscalar and not {"x", "y"}.issubset(dim):
        log_file.write(
            " - ERROR: Compliance check ignored: x or y in the mandatory dimensions (x,y,t) is missing.\n"
        )
        log_file.write(
            "                                    Only " + str(list(dim)) + " has been detected.\n"
        )
        report_naming_issues.append(
            "Compliance check ignored: x or y in the mandatory dimensions (x,y,t) is missing in "
            + file_name
        )
        return errors + 1

    if region not in ["AIS", "GrIS"]:
        log_file.write(
            " - ERROR: Region "
            + region
            + " not recognized. It should be AIS or GrIS. The compliance check has been interrupted for this variable.\n"
        )
        report_naming_issues.append(
            "Compliance check ignored: region (AIS/GrIS) not identified in the file "
            + file_name
            + " due to wrong naming."
        )
        errors += 1

    parts = file_name.split("_")
    if len(parts) == ISMIP7_FILENAME_PARTS:
        ism_member = parts[ISMIP7_FILENAME_ISM_MEMBER_IDX]
        if not re.fullmatch(r"m\d{3}", ism_member):
            log_file.write(
                f" - ERROR: ISM member id '{ism_member}' (field {ISMIP7_FILENAME_ISM_MEMBER_IDX}) does not match expected format mNNN (e.g. m001).\n"
            )
            errors += 1

        esm_name = parts[ISMIP7_FILENAME_ESM_IDX]
        if esm_name not in VALID_ESM_NAMES:
            log_file.write(
                f" - ERROR: ESM name '{esm_name}' (field {ISMIP7_FILENAME_ESM_IDX}) is not a recognised CMIP6/CMIP7 model name.\n"
            )
            errors += 1

        forcing_member = parts[ISMIP7_FILENAME_FORCING_MEMBER_IDX]
        if not re.fullmatch(r"f\d{3}", forcing_member):
            log_file.write(
                f" - ERROR: forcing member id '{forcing_member}' (field {ISMIP7_FILENAME_FORCING_MEMBER_IDX}) does not match expected format fNNN (e.g. f001).\n"
            )
            errors += 1

        set_counter = parts[ISMIP7_FILENAME_SET_COUNTER_IDX]
        if not re.fullmatch(r"[CEP]\d{3}", set_counter):
            log_file.write(
                f" - ERROR: set counter '{set_counter}' (field {ISMIP7_FILENAME_SET_COUNTER_IDX}) does not match expected format [C|E|P]NNN (e.g. C001, E041, P132).\n"
            )
            errors += 1

        is_static = not ({"time", "t"} & dim)
        year_range_field = parts[ISMIP7_FILENAME_YEAR_RANGE_IDX].removesuffix(".nc")
        if is_static:
            log_file.write(f" - Filename year range: N/A (static spatial variable)\n")
        elif not (year_range_match := re.fullmatch(r"(\d{4})-(\d{4})", year_range_field)):
            log_file.write(
                f" - ERROR: year range '{year_range_field}' (field {ISMIP7_FILENAME_YEAR_RANGE_IDX}) does not match expected format YYYY-YYYY (e.g. 2015-2300).\n"
            )
            errors += 1
        else:
            fn_start_year = int(year_range_match.group(1))
            fn_end_year = int(year_range_match.group(2))
            if fn_start_year > fn_end_year:
                log_file.write(
                    f" - ERROR: year range '{year_range_field}': start year {fn_start_year} is after end year {fn_end_year}.\n"
                )
                errors += 1
            elif "time" in ds.coords:
                _decoded_time = xr.decode_cf(ds, decode_times=xr.coders.CFDatetimeCoder(use_cftime=True))["time"]
                # ST timestamps are Jan 1 of year+1; subtract 1 to recover the nominal simulation year.
                _yr_offset = 1 if var_type == "ST" else 0
                actual_start = min(_decoded_time).item().year - _yr_offset
                actual_end = max(_decoded_time).item().year - _yr_offset
                is_snapshot = "z" in dim
                yr_range_ok = True
                if not is_snapshot:
                    # For regular time-series variables the filename start year must match the first time step.
                    if fn_start_year != actual_start:
                        log_file.write(
                            f" - ERROR: filename start year {fn_start_year} does not match first time step year {actual_start}.\n"
                        )
                        errors += 1
                        yr_range_ok = False
                if fn_end_year != actual_end:
                    log_file.write(
                        f" - ERROR: filename end year {fn_end_year} does not match last time step year {actual_end}.\n"
                    )
                    errors += 1
                    yr_range_ok = False
                if yr_range_ok:
                    log_file.write(
                        f" - Filename year range {fn_start_year}-{fn_end_year} matches time axis: OK\n"
                    )

    return errors


def _allowed_file_variables(ds, considered_variable: str) -> set[str]:
    """The variables a file may hold besides the one it is named for.

    A file carries one variable of the data request, but CF lets that variable
    bring companions: the bounds of a coordinate (which is how 'time_bounds'
    reaches every FL file), the container variable a 'grid_mapping' points at,
    and any auxiliary coordinates the variable names.  Those belong in the
    file; anything else is something the data request did not ask for.
    """
    allowed = {considered_variable} | set(ds.coords)

    # xarray moves CF attributes into .encoding as it decodes, so both places
    # have to be looked at to find what a file actually declares.
    for coord in ds.coords.values():
        bounds = {**coord.attrs, **coord.encoding}.get("bounds")
        if bounds:
            allowed.add(str(bounds))

    attributes = {**ds[considered_variable].attrs, **ds[considered_variable].encoding}
    grid_mapping = attributes.get("grid_mapping")
    if grid_mapping:
        allowed.add(str(grid_mapping))
    allowed.update(str(attributes.get("coordinates", "")).split())

    return allowed


def _check_file_variables(
    log_file,
    ds,
    file_name: str,
    considered_variable: str,
    file_variables,
    report_naming_issues: list,
) -> tuple[int, bool]:
    """Check the variables a file contains against the one its name promises.

    The file name states which variable of the data request a file carries, and
    every other check reads that variable, so a file that does not contain it
    has nothing to check: the second element of the return value is False, and
    the caller skips the remaining checks for the file rather than reporting a
    clean bill of health on a variable that was never looked at.
    """
    errors = 0

    if considered_variable not in file_variables:
        message = (
            f"the file name promises variable '{considered_variable}', but the"
            f" file does not contain it. Data variables found:"
            f" {sorted(file_variables)}."
        )
        near_misses = difflib.get_close_matches(
            considered_variable, file_variables, n=1
        )
        if near_misses:
            message += (
                f" '{near_misses[0]}' may be a misspelling of"
                f" '{considered_variable}'."
            )
        log_file.write(f" - ERROR: {message}\n")
        report_naming_issues.append(
            f"Compliance check ignored: in the file {file_name}, {message}"
        )
        return errors + 1, False

    log_file.write(
        f" - Variable '{considered_variable}' from the file name is present in"
        f" the file: OK\n"
    )

    allowed = _allowed_file_variables(ds, considered_variable)
    unexpected = sorted(name for name in file_variables if name not in allowed)
    for name in unexpected:
        log_file.write(
            f" - ERROR: unexpected variable '{name}' in the file. A file holds"
            f" one variable of the data request -- here '{considered_variable}'"
            f" -- along with its coordinates and any bounds or grid-mapping"
            f" variables, and nothing else.\n"
        )
        errors += 1
    if not unexpected:
        log_file.write(" - No unexpected variables in the file: OK\n")

    return errors, True


# CF requires only that the units attribute be "a string that can be recognized
# by the UDUNITS package", and UDUNITS recognises several spellings of the same
# unit: the exponent in 'm2' may equally be written 'm^2' or 'm**2', the factors
# of a product may be separated by a space, a '.', a '*' or a middle dot, and a
# '/' introduces factors with negated exponents.  The data request writes one
# spelling per variable, but a model that writes another is just as compliant
# (PISM writes 'm^2' because pint does not recognise 'm2'), so the checker
# compares what units mean rather than how they are spelled.

# One factor of a product: a base name, then an exponent written with a caret
# ('m^2'), a double star ('m**2', normalised to a caret first) or bare ('m2').
# Digits and signs are kept out of the base so that the exponent is what is
# left over.
_UNIT_FACTOR_RE = re.compile(r"^(?P<base>[^\d\s^/*.()+-]+)\^?(?P<exponent>[+-]?\d+)?$")

# Whitespace, '.', '*' and the middle dot all multiply in UDUNITS.
_UNIT_PRODUCT_SEPARATORS = r"[\s.*·×]+"
_UNIT_PRODUCT_SEPARATOR_RE = re.compile(_UNIT_PRODUCT_SEPARATORS)

# Splits a units string into factors and the operators between them, keeping
# the operators so that '/' can be told from the multiplications.
_UNIT_TOKEN_RE = re.compile(rf"(/|{_UNIT_PRODUCT_SEPARATORS})")


def _parse_units(units: str):
    """Return a canonical (scale, factors) form of a UDUNITS string.

    `factors` is the sorted tuple of (base unit, exponent) pairs, so that
    equivalent spellings of the same unit give equal results.  Returns None for
    the strings this deliberately small parser does not claim to understand:
    empty units, parentheses, timestamp offsets such as 'days since
    1850-01-01', and decimal scale factors (where '.' is a decimal point rather
    than a multiplication).  Callers fall back to comparing such strings
    literally.
    """
    text = units.strip()
    if (
        not text
        or "(" in text
        or ")" in text
        or re.search(r"\d\.\d", text)
        or re.search(r"\b(since|after|from|ref)\b", text)
    ):
        return None

    text = text.replace("**", "^")
    scale = 1.0
    exponents: dict[str, int] = {}
    # UDUNITS multiplies and divides left to right, so a '/' inverts only the
    # factor that follows it: 'kg/m2 s' is kg m-2 s, not kg m-2 s-1.
    sign = 1
    factor_count = 0
    for token in _UNIT_TOKEN_RE.split(text):
        if not token:
            continue
        if token == "/":
            sign = -1
            continue
        if _UNIT_PRODUCT_SEPARATOR_RE.fullmatch(token):
            sign = 1
            continue
        match = _UNIT_FACTOR_RE.match(token)
        if match is None:
            # Not a named unit: the only other thing it can be is a numerical
            # factor, such as the '1' of a dimensionless unit.
            try:
                scale *= float(token) ** sign
            except ValueError:
                return None
        else:
            base = match.group("base")
            exponent = int(match.group("exponent") or 1) * sign
            exponents[base] = exponents.get(base, 0) + exponent
        sign = 1
        factor_count += 1

    if factor_count == 0:
        return None

    factors = tuple(sorted((b, e) for b, e in exponents.items() if e != 0))
    return scale, factors


def _units_match(actual: str, expected: str) -> bool:
    """Whether two units strings denote the same unit, however each is spelled."""
    if actual == expected:
        return True
    parsed_actual = _parse_units(actual)
    return parsed_actual is not None and parsed_actual == _parse_units(expected)


def _check_numerical(
    log_file,
    ds,
    ivar: str,
    ismip_meta: list,
    var_index: int,
    region: str,
    isscalar: bool,
) -> int:
    errors = 0

    log_file.write("NUMERICAL Tests \n")

    var_units = ds[ivar].attrs["units"]
    expected_units = ismip_meta[var_index]["units"]
    if var_units == expected_units:
        log_file.write(" - The unit is correct: " + var_units + "\n")
    elif _units_match(var_units, expected_units):
        log_file.write(
            " - The unit is correct: "
            + var_units
            + " (equivalent to the requested "
            + expected_units
            + ")\n"
        )
    else:
        log_file.write(
            " - ERROR: The unit of the variable is "
            + var_units
            + " and should be "
            + expected_units
            + " \n"
        )
        errors += 1

    if not isscalar:
        if False in ds[ivar].isnull():
            if (
                ds[ivar].min(skipna=True).item()
                >= ismip_meta[var_index]["min_value_" + region.lower()]
            ):
                log_file.write(" - The minimum value successfully verified.\n")
            else:
                log_file.write(
                    " - ERROR: The minimum value ("
                    + str(ds[ivar].min(skipna=True).values.item(0))
                    + ") is out of range. Min value accepted: "
                    + str(ismip_meta[var_index]["min_value_" + region.lower()])
                    + "\n"
                )
                errors += 1

            if (
                ds[ivar].max(skipna=True).item()
                <= ismip_meta[var_index]["max_value_" + region.lower()]
            ):
                log_file.write(" - The maximum value successfully verified.\n")
            else:
                log_file.write(
                    " - ERROR: The maximum value ("
                    + str(ds[ivar].max(skipna=True).values.item(0))
                    + ") is out of range. Max value accepted: "
                    + str(ismip_meta[var_index]["max_value_" + region.lower()])
                    + "\n"
                )
                errors += 1
        else:
            log_file.write(" - ERROR: The array only contains missing values.\n")
            errors += 1

    return errors


def _check_spatial(
    log_file,
    ds,
    grid_extent: list,
    possible_resolution: list,
) -> int:
    errors = 0

    log_file.write("SPATIAL Tests \n")
    coords = ds.coords.to_dataset()
    Xbottomleft = int(min(coords["x"]).values.item())
    Ybottomleft = int(min(coords["y"]).values.item())
    Xtopright = int(max(coords["x"]).values.item())
    Ytopright = int(max(coords["y"]).values.item())

    if Xbottomleft == grid_extent[0] and Ybottomleft == grid_extent[1]:
        log_file.write(" - Grid: Lowest left corner is well defined.\n")
    else:
        log_file.write(
            " - ERROR: Lowest left corner of the grid ["
            + str(Xbottomleft) + "," + str(Ybottomleft)
            + "] is not correctly defined. ["
            + str(grid_extent[0]) + "," + str(grid_extent[1])
            + "] Expected\n"
        )
        errors += 1

    if Xtopright == grid_extent[2] and Ytopright == grid_extent[3]:
        log_file.write(" - Grid: Upper right corner is well defined.\n")
    else:
        log_file.write(
            " - ERROR: Upper right corner of the grid ["
            + str(Xtopright) + "," + str(Ytopright)
            + "] is not correctly defined. ["
            + str(grid_extent[2]) + "," + str(grid_extent[3])
            + "] Expected\n"
        )
        errors += 1

    Xresolution = round((coords["x"][1].values - coords["x"][0].values) / 1000, 0)
    Yresolution = round((coords["y"][1].values - coords["y"][0].values) / 1000, 0)
    if Xresolution in set(possible_resolution) and Yresolution in set(possible_resolution):
        log_file.write(
            " - The grid resolution ("
            + str(int(Xresolution))
            + " km) was successfully verified.\n"
        )
    else:
        log_file.write(
            " - ERROR: resolution x="
            + str(Xresolution)
            + " km, y="
            + str(Yresolution)
            + " km is not an authorized grid resolution. Allowed: "
            + str(possible_resolution)
            + " km\n"
        )
        errors += 1

    return errors


def _check_time(
    log_file,
    ds,
    dim: set,
    experiments: list,
    experiment_name: str,
    var_type: str = "",
) -> int:
    errors = 0

    log_file.write("TIME Tests \n")
    if not ({"t"}.issubset(dim) or {"time"}.issubset(dim)):
        if {"x", "y"}.issubset(dim):
            # Static spatial variable (x,y) — no time axis is expected.
            log_file.write(" - Time axis: N/A (static spatial variable)\n")
            return errors
        log_file.write(
            " - ERROR: The time dimension is missing. Time Tests have been ignored.\n"
        )
        return errors + 1

    time_dim = "time" if "time" in ds.dims else "t"
    unlimited_dims = ds.encoding.get("unlimited_dims", set())
    if time_dim in unlimited_dims:
        log_file.write(" - Time is a record (unlimited) dimension: OK\n")
    else:
        log_file.write(
            f" - ERROR: dimension '{time_dim}' is not a record (unlimited) dimension.\n"
        )
        errors += 1

    try:
        ds = xr.decode_cf(ds, decode_times=xr.coders.CFDatetimeCoder(use_cftime=True))
    except Exception as err:
        log_file.write(
            " - ERROR: The time coordinate could not be decoded.  Time checks cannot proceed.\n"
        )
        errors += 1
        # we can't proceed because the next steps will crash
        return errors
      
    start_exp = min(ds["time"]).values.astype("datetime64[D]")
    end_exp = max(ds["time"]).values.astype("datetime64[D]")
    duration_years = end_exp.item().year - start_exp.item().year + 1

    index_exp = [dic["experiment"] for dic in experiments].index(experiment_name)
    if not (
        np.issubdtype(start_exp.dtype, np.datetime64)
        & np.issubdtype(end_exp.dtype, np.datetime64)
    ):
        log_file.write(
            " - ERROR: the time format of the Netcdf file is not recognized. Time Tests have been ignored.\n"
        )
        return errors + 1

    if not _strictly_increasing(ds.coords["time"]):
        log_file.write(
            " - ERROR: the time series is not monotonically increasing. Time segments may have been concatenated in the wrong order.\n"
        )
        return errors + 1

    is_snapshot_var = "z" in dim
    if is_snapshot_var:
        # x,y,z,t variable (e.g. litemp): sparse snapshot time axis.
        # Each time value must be an ST-encoded timestamp for one of the known snapshot nominal years.
        _LITEMP_SNAPSHOT_NOMINAL_YEARS = {1900, 2000, 2100, 2200, 2300}
        _yr_offset = 1 if var_type == "ST" else 0
        nominal_years = [t.year - _yr_offset for t in ds["time"].values]
        exp_for_snaps = experiments[index_exp]
        valid_snapshot_years = {nominal_years[-1]} | {
            y for y in _LITEMP_SNAPSHOT_NOMINAL_YEARS
            if exp_for_snaps["start_year_min"] <= y <= exp_for_snaps["end_year"]
        }
        if exp_for_snaps["experiment"] == "historical":
            valid_snapshot_years.add(nominal_years[0])
        snap_errors = 0
        for ny in nominal_years:
            if ny not in valid_snapshot_years:
                log_file.write(
                    f" - ERROR: time snapshot nominal year {ny} is not in the valid"
                    f" snapshot set {sorted(valid_snapshot_years)}.\n"
                )
                snap_errors += 1
        if snap_errors == 0:
            log_file.write(
                f" - Snapshot time axis nominal years {nominal_years} are all valid: OK\n"
            )
        errors += snap_errors
    elif len(ds["time"].values) > 1:
        if isinstance(ds["time"].values[1] - ds["time"].values[0], datetime.timedelta):
            time_step = (ds["time"].values[1] - ds["time"].values[0]).days
        elif isinstance(ds["time"].values[1] - ds["time"].values[0], np.timedelta64):
            time_step = np.timedelta64(
                ds["time"].values[1] - ds["time"].values[0], "D"
            ) / np.timedelta64(1, "D")
        else:
            time_step = ds["time"].values[1] - ds["time"].values[0]

        if TIME_STEP_MIN_DAYS <= time_step <= TIME_STEP_MAX_DAYS:
            log_file.write(" - Time step: " + str(time_step) + " days\n")
        else:
            log_file.write(
                " - ERROR: the time step ("
                + str(time_step)
                + ") should be comprised between ["
                + str(TIME_STEP_MIN_DAYS)
                + " and "
                + str(TIME_STEP_MAX_DAYS)
                + "].\n"
            )
            errors += 1
    else:
        log_file.write(" - Only one time step present; time step check skipped.\n")

    exp = experiments[index_exp]
    dateformat_end_exp = datetime.datetime(
        end_exp.item().year, end_exp.item().month, end_exp.item().day
    )

    if is_snapshot_var:
        log_file.write(
            " - Duration / start / end timestamp checks: N/A (snapshot variable — time axis holds sparse snapshots only).\n"
        )
        return errors

    # Compute expected timestamp windows from nominal years + var_type (±1 day tolerance).
    _tol = datetime.timedelta(days=1)
    startinf = _nominal_to_timestamp(exp["start_year_min"], var_type) - _tol
    startsup  = _nominal_to_timestamp(exp["start_year_max"], var_type) + _tol
    endinf    = _nominal_to_timestamp(exp["end_year"],       var_type) - _tol
    endsup    = _nominal_to_timestamp(exp["end_year"],       var_type) + _tol

    if exp["duration"] == -1:
        # Undetermined length: only require >= 1 year, start and end date in range
        if duration_years >= 1:
            log_file.write(
                " - Experiment lasts " + str(duration_years) + " years (>= 1 year required): OK\n"
            )
        else:
            log_file.write(
                " - ERROR: the experiment lasts "
                + str(duration_years)
                + " years but must be at least 1 year long.\n"
            )
            errors += 1

        _yr_off = 1 if var_type == "ST" else 0
        dateformat_start_exp = datetime.datetime(
            start_exp.item().year, start_exp.item().month, start_exp.item().day
        )
        if startinf <= dateformat_start_exp <= startsup:
            log_file.write(
                " - First time stamp correctly set to "
                + start_exp.item().strftime("%Y-%m-%d")
                + f" (nominal year {start_exp.item().year - _yr_off}).\n"
            )
        else:
            log_file.write(
                " - ERROR: the experiment starts the "
                + start_exp.item().strftime("%Y-%m-%d")
                + ". The date should be comprised between "
                + startinf.strftime("%Y-%m-%d")
                + " and "
                + startsup.strftime("%Y-%m-%d")
                + "\n"
            )
            errors += 1

        if endinf <= dateformat_end_exp <= endsup:
            log_file.write(
                " - Last time stamp correctly set to "
                + end_exp.item().strftime("%Y-%m-%d")
                + f" (nominal year {end_exp.item().year - _yr_off}).\n"
            )
        else:
            log_file.write(
                " - ERROR: the experiment ends on "
                + end_exp.item().strftime("%Y-%m-%d")
                + ". The date should be comprised between "
                + endinf.strftime("%Y-%m-%d")
                + " and "
                + endsup.strftime("%Y-%m-%d")
                + "\n"
            )
            errors += 1
    else:
        if duration_years == exp["duration"]:
            log_file.write(" - Experiment lasts " + str(duration_years) + " years.\n")
            _yr_off = 1 if var_type == "ST" else 0
            dateformat_start_exp = datetime.datetime(
                start_exp.item().year,
                start_exp.item().month,
                start_exp.item().day,
            )
            if startinf <= dateformat_start_exp <= startsup:
                log_file.write(
                    " - First time stamp correctly set to "
                    + start_exp.item().strftime("%Y-%m-%d")
                    + f" (nominal year {start_exp.item().year - _yr_off}).\n"
                )
            else:
                log_file.write(
                    " - ERROR: the experiment starts the "
                    + start_exp.item().strftime("%Y-%m-%d")
                    + ". The date should be comprised between "
                    + startinf.strftime("%Y-%m-%d")
                    + " and "
                    + startsup.strftime("%Y-%m-%d")
                    + "\n"
                )
                errors += 1

            if endinf <= dateformat_end_exp <= endsup:
                log_file.write(
                    " - Last time stamp correctly set to "
                    + end_exp.item().strftime("%Y-%m-%d")
                    + f" (nominal year {end_exp.item().year - _yr_off}).\n"
                )
            else:
                log_file.write(
                    " - ERROR: the experiment ends on "
                    + end_exp.item().strftime("%Y-%m-%d")
                    + ". The date should be comprised between "
                    + endinf.strftime("%Y-%m-%d")
                    + " and "
                    + endsup.strftime("%Y-%m-%d")
                    + "\n"
                )
                errors += 1
        else:
            end_date = start_exp + np.timedelta64(exp["duration"] * 365, "D")
            log_file.write(
                " - ERROR: the experiment lasts "
                + str(duration_years)
                + " years. The duration should be "
                + str(exp["duration"])
                + " years\n"
            )
            log_file.write(
                " - As the experiment started on "
                + start_exp.item().strftime("%Y-%m-%d")
                + " , it should end on "
                + end_date.item().strftime("%Y-%m-%d")
                + "\n"
            )
            errors += 1

    return errors


def _check_attributes(
    log_file,
    ds,
    ivar: str,
    ismip_meta: list,
    var_index: int,
    isscalar: bool,
    var_type: str,
    region: str,
) -> int:
    errors = 0

    log_file.write("ATTRIBUTE Tests \n")

    # Sub-test 1: global attributes
    required_global = ["group", "model", "contact_name", "contact_email"]
    global_errors = 0
    for attr in required_global:
        if attr not in ds.attrs:
            log_file.write(f" - ERROR (attributes): global attribute '{attr}' is missing.\n")
            global_errors += 1
    expected_crs = "epsg:3413" if region == "GrIS" else "epsg:3031"
    actual_crs = ds.attrs.get("crs")
    if actual_crs is None:
        log_file.write(" - ERROR (attributes): global attribute 'crs' is missing.\n")
        global_errors += 1
    elif actual_crs.lower() != expected_crs:
        log_file.write(
            f" - ERROR (attributes): global attribute 'crs' is '{actual_crs}',"
            f" expected '{expected_crs}' (case-insensitive) for region {region}.\n"
        )
        global_errors += 1
    if global_errors == 0:
        log_file.write(" - Global attributes: OK\n")
    errors += global_errors

    # Sub-test 2: coordinate attributes
    coord_errors = 0
    time_coord = None
    for name in ("time", "t"):
        if name in ds.coords:
            time_coord = name
            break
    is_static_spatial = time_coord is None and {"x", "y"}.issubset(set(ds.coords))
    if time_coord is None and not is_static_spatial:
        log_file.write(" - ERROR (attributes): coordinate 'time' not found.\n")
        coord_errors += 1
    elif time_coord is None and is_static_spatial:
        log_file.write(" - Time coordinate: N/A (static spatial variable)\n")
    else:
        # xarray decodes 'units' and 'calendar' into .encoding; 'bounds' stays in .attrs
        time_var = ds[time_coord]
        combined = {**time_var.encoding, **time_var.attrs}
        time_attrs_required = ["units", "calendar"]
        if var_type != "ST":
            time_attrs_required.append("bounds")
        for attr in time_attrs_required:
            if attr not in combined:
                log_file.write(
                    f" - ERROR (attributes): coordinate '{time_coord}' missing attribute '{attr}'.\n"
                )
                coord_errors += 1
        if "units" in combined and combined["units"] != "days since 1850-01-01":
            log_file.write(
                f" - ERROR (attributes): time 'units' is '{combined['units']}', expected 'days since 1850-01-01'.\n"
            )
            coord_errors += 1
        if "calendar" in combined and combined["calendar"] != "standard":
            log_file.write(
                f" - ERROR (attributes): time 'calendar' is '{combined['calendar']}', expected 'standard'.\n"
            )
            coord_errors += 1
    if not isscalar:
        spatial_coords = ("x", "y", "z") if "z" in ds.coords else ("x", "y")
        for coord in spatial_coords:
            if coord in ds.coords:
                if "units" not in ds[coord].attrs:
                    log_file.write(
                        f" - ERROR (attributes): coordinate '{coord}' missing attribute 'units'.\n"
                    )
                    coord_errors += 1
            else:
                log_file.write(
                    f" - ERROR (attributes): coordinate '{coord}' not found.\n"
                )
                coord_errors += 1
    if coord_errors == 0:
        log_file.write(" - Coordinate attributes: OK\n")
    errors += coord_errors

    # Sub-test 3: variable standard_name
    var_errors = 0
    expected_standard_name = ismip_meta[var_index].get("standard_name")
    if expected_standard_name is not None and ivar in ds:
        if "standard_name" not in ds[ivar].attrs:
            log_file.write(
                f" - ERROR (attributes): variable '{ivar}' missing 'standard_name' attribute.\n"
            )
            var_errors += 1
        elif ds[ivar].attrs["standard_name"] != expected_standard_name:
            log_file.write(
                f" - ERROR (attributes): variable '{ivar}' standard_name"
                f" '{ds[ivar].attrs['standard_name']}'"
                f" does not match expected '{expected_standard_name}'.\n"
            )
            var_errors += 1
    if var_errors == 0:
        log_file.write(" - Variable attributes: OK\n")
    errors += var_errors

    # Sub-test 4: _FillValue must equal the default netCDF4 fill value;
    #             if missing_value is also present it must equal _FillValue.
    fill_errors = 0
    if ivar in ds:
        dtype = ds[ivar].dtype
        nc4_dtype_key = dtype.kind + str(dtype.itemsize)
        default_fill = netCDF4.default_fillvals.get(nc4_dtype_key)
        fill_value = ds[ivar].encoding.get("_FillValue")
        # xarray moves missing_value from attrs to encoding on read (CF fill-value handling)
        missing_value = ds[ivar].attrs.get("missing_value") or ds[ivar].encoding.get("missing_value")
        if fill_value is None:
            log_file.write(f" - ERROR (attributes): variable '{ivar}' missing '_FillValue'.\n")
            fill_errors += 1
        elif default_fill is not None and fill_value != default_fill:
            log_file.write(
                f" - ERROR (attributes): variable '{ivar}' _FillValue {fill_value}"
                f" does not match default netCDF4 fill value {default_fill} for dtype {dtype}.\n"
            )
            fill_errors += 1
        if fill_value is not None and missing_value is not None and fill_value != missing_value:
            log_file.write(
                f" - ERROR (attributes): variable '{ivar}' _FillValue {fill_value}"
                f" and missing_value {missing_value} are not equal.\n"
            )
            fill_errors += 1
    if fill_errors == 0:
        log_file.write(" - Fill value attributes: OK\n")
    errors += fill_errors

    # Sub-test 5: main variable and time must be single-precision float (f4)
    dtype_errors = 0
    if ivar in ds and ds[ivar].dtype != np.float32:
        log_file.write(
            f" - ERROR (attributes): variable '{ivar}' dtype is {ds[ivar].dtype},"
            f" expected float32 (f4).\n"
        )
        dtype_errors += 1
    if time_coord is not None:
        # xarray decodes CF time to datetime objects in memory; check the on-disk dtype from encoding
        time_encoded_dtype = ds[time_coord].encoding.get("dtype", ds[time_coord].dtype)
        if time_encoded_dtype != np.float32:
            log_file.write(
                f" - ERROR (attributes): coordinate '{time_coord}' on-disk dtype is {time_encoded_dtype},"
                f" expected float32 (f4).\n"
            )
            dtype_errors += 1
    if dtype_errors == 0:
        log_file.write(" - Dtype attributes: OK\n")
    errors += dtype_errors

    # Sub-test 6: scale_factor and add_offset must not be present
    pack_errors = 0
    if ivar in ds:
        # xarray moves these to .encoding on decode; check both locations
        combined = {**ds[ivar].attrs, **ds[ivar].encoding}
        for forbidden in ("scale_factor", "add_offset"):
            if forbidden in combined:
                log_file.write(
                    f" - ERROR (attributes): variable '{ivar}' must not have '{forbidden}'.\n"
                )
                pack_errors += 1
    if pack_errors == 0:
        log_file.write(" - Packing attributes: OK\n")
    errors += pack_errors

    return errors


def _run_variable_checks(
    log_file,
    ds,
    file_name: str,
    considered_variable: str,
    experiment_name: str,
    file_variables,
    region: str,
    ismip_var,
    ismip_meta,
    experiments,
    report_naming_issues,
):
    var_naming_errors = 0
    var_num_errors = 0
    var_spatial_errors = 0
    var_time_errors = 0
    var_attr_errors = 0

    log_file.write(" \n")
    log_file.write("Experiment: " + experiment_name + " - File: " + file_name + "\n")
    log_file.write(" \n")

    header_ds = ds.to_dict(data=False)
    dim = set(list(header_ds["coords"].keys()))

    index = ismip_var.index(considered_variable)
    isscalar = ismip_meta[index]["dim"] == "t"
    var_type = ismip_meta[index].get("type", "")

    n_err = _check_naming(log_file, ds, file_name, region, dim, isscalar, report_naming_issues, var_type)
    var_naming_errors += n_err
    if n_err > 0:
        return var_naming_errors, var_num_errors, var_spatial_errors, var_time_errors, var_attr_errors

    file_var_errors, has_variable = _check_file_variables(
        log_file, ds, file_name, considered_variable, file_variables, report_naming_issues
    )
    var_naming_errors += file_var_errors
    if not has_variable:
        return var_naming_errors, var_num_errors, var_spatial_errors, var_time_errors, var_attr_errors

    grid_extent = AIS_GRID_EXTENT if region == "AIS" else GrIS_GRID_EXTENT
    possible_resolution = AIS_POSSIBLE_RESOLUTION if region == "AIS" else GrIS_POSSIBLE_RESOLUTION

    # The checks read the variable the file name promises, and the row of the
    # data request that goes with it.  Reading whatever variable the file
    # happens to contain instead would check a file against the wrong criteria,
    # or -- when nothing in it is a requested name -- against none at all.
    ivar = considered_variable
    var_index = index
    log_file.write("** Tested Variable: " + ivar + "\n")
    log_file.write(" \n")

    var_num_errors += _check_numerical(log_file, ds, ivar, ismip_meta, var_index, region, isscalar)

    if not isscalar:
        var_spatial_errors += _check_spatial(log_file, ds, grid_extent, possible_resolution)

    var_time_errors += _check_time(log_file, ds, dim, experiments, experiment_name, var_type)

    var_attr_errors += _check_attributes(log_file, ds, ivar, ismip_meta, var_index, isscalar, var_type, region)

    return var_naming_errors, var_num_errors, var_spatial_errors, var_time_errors, var_attr_errors


def _print_experiment_summary(experiment_name: str, exp_errors: int) -> None:
    print(experiment_name, ": compliance check processed.")
    if exp_errors > 0:
        print(
            "Found", exp_errors, "errors. Check compliance_checker_log.txt for details."
        )
    else:
        print("Successfully verified with no errors")
    print()


def _print_total_summary(source_path: str, total_errors: int) -> None:
    print("-------------------------------------------------------------------------")
    print(source_path, ": compliance check processed.")
    if total_errors > 0:
        print(
            "Found a total of",
            total_errors,
            "errors. Check compliance_checker_log.txt for details.",
        )
    else:
        print("Successfully verified with no errors")
    print("-------------------------------------------------------------------------")


def _strictly_increasing(values) -> bool:
    return all(x < y for x, y in zip(values, values[1:]))


def _write_log_header(
        log_file, version: str, source_path: str, today: datetime.date, criteria_file: str,
) -> None:
    log_file.write(
        "************************************************************************************\n"
    )
    log_file.write(
        "*************     Ice Sheet Model Simulations - Compliance Checker     *************\n"
    )
    log_file.write(
        "************************************************************************************\n"
    )
    log_file.write(f"isschecker version: {version} \n")
    log_file.write("verification criteria: " + criteria_file + "\n")
    log_file.write("date: " + today.strftime("%Y/%m/%d") + "\n")
    log_file.write("source: https://github.com/ismip/ISM_SimulationChecker \n")
    log_file.write(" \n")
    log_file.write(
        "------------------------------------------------------------------------------------\n"
    )
    log_file.write("Verified directory: " + source_path + " \n")
    log_file.write(
        "------------------------------------------------------------------------------------\n"
    )
    log_file.write(" \n")
    log_file.write(" \n")
    log_file.write(" \n")
    log_file.write(" \n")
    log_file.write(
        "====================================================================================\n"
    )
    log_file.write(
        "================                DETAILED RESULTS                    ================\n"
    )
    log_file.write(
        "====================================================================================\n"
    )
    log_file.write("Hint: Use Cltr+F to look for specific problems. \n")
    log_file.write(" \n")


def _insert_synthesis(
    source_path: str,
    exp_counter: int,
    file_counter: int,
    total_errors: int,
    total_file_errors: int,
    total_naming_errors: int,
    total_num_errors: int,
    total_spatial_errors: int,
    total_time_errors: int,
    total_attr_errors: int,
    report_naming_issues,
) -> None:
    with open(os.path.join(source_path, "compliance_checker_log.txt"), "r") as f:
        contents = f.readlines()

    iline = 11
    contents.insert(iline, str(exp_counter) + " experiments checked.\n")
    iline += 1
    contents.insert(iline, str(file_counter) + " files checked.\n")
    iline += 2
    contents.insert(iline, str(total_errors) + " error(s) detected.\n")
    iline += 1
    contents.insert(iline, "  - Mandatory variables: " + str(total_file_errors) + " error(s)\n")
    iline += 1
    contents.insert(iline, "  - Naming Tests       : " + str(total_naming_errors) + " error(s)\n")
    iline += 1
    contents.insert(iline, "  - Numerical Tests    : " + str(total_num_errors) + " error(s)\n")
    iline += 1
    contents.insert(iline, "  - Spatial Tests      : " + str(total_spatial_errors) + " error(s)\n")
    iline += 1
    contents.insert(iline, "  - Time Tests         : " + str(total_time_errors) + " error(s)\n")
    iline += 1
    contents.insert(iline, "  - Attribute Tests    : " + str(total_attr_errors) + " error(s)\n")
    iline += 2
    contents.insert(iline, "0 warning(s) detected.\n")
    iline += 2
    if total_naming_errors > 0:
        contents.insert(iline, "Naming tests errors report: \n")
        iline += 1
        for i in range(iline, len(report_naming_issues)):
            contents.insert(i, "  - " + report_naming_issues[i - 24] + "\n")
        contents.insert(iline + len(report_naming_issues), "\n")

    with open(os.path.join(source_path, "compliance_checker_log.txt"), "w") as f:
        f.writelines(contents)
