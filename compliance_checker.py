#!/usr/bin/env python3
#
# ISMIP7 Compliance Checker — check summary
#
# 1. Naming (_check_naming)
#    - Variable name matches the expected ISMIP7 name from the data request.
#    - Region field in filename matches the region inferred from the grid (AIS/GrIS).
#    - ISM member id (field 4) matches format mNNN (e.g. m001).
#    - ESM name (field 5) is a recognised CMIP6/CMIP7 model name.
#    - Forcing member id (field 6) matches format fNNN (e.g. f001).
#    - Set counter (field 8) matches format [C|E|P]NNN (e.g. C001, E041, P132).
#    - Year range (field 9) matches format YYYY-YYYY; start <= end; both match the actual time axis.
#
# 2. Numerical (_check_numerical)
#    - Variable units match the data request.
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
import os
import re
import subprocess
import argparse

import numpy as np
import pandas as pd
import xarray as xr
import netCDF4
from tqdm import tqdm


DEFAULT_SOURCE_PATH = "./Models/GrIS/ISMIP7/SYNTH1/CORE"
DEFAULT_VARIABLE_LIST = "ismip7_scalars"
VARIABLE_LIST_CHOICES = ("ismip7_scalars", "ismip7_xyt", "ismip7")

VARIABLE_REQUEST_XLSX = os.path.join("conventions", "ISMIP7_variable_request.xlsx")

EXPERIMENTS_ISMIP7_CSV_FILENAME = "experiments_ismip7.csv"

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
    workdir = os.getcwd()

    commit_num = _get_commit_number()
    experiments_ismip7 = _load_experiments_csv(
        os.path.join(workdir, EXPERIMENTS_ISMIP7_CSV_FILENAME)
    )
    ismip_meta, ismip_var, mandatory_variables = _load_criteria(workdir, variable_list)

    _run_compliance_checker(
        source_path=source_path,
        commit_num=commit_num,
        ismip_meta=ismip_meta,
        ismip_var=ismip_var,
        mandatory_variables=mandatory_variables,
        experiments=experiments_ismip7,
        criteria_file=VARIABLE_REQUEST_XLSX,
    )


def _get_commit_number() -> str:
    try:
        bash_command = "git log --pretty=format:'%h' -n 1"
        process = subprocess.Popen(bash_command.split(), stdout=subprocess.PIPE)
        commit_num, _error = process.communicate()
        return commit_num.decode("UTF-8")
    except Exception:
        print("Could not retrieve git commit number. Is there a .git directory here?")
        return "No commit number identified."


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check simulation NetCDF datasets for ISMIP compliance."
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


def _load_criteria(workdir: str, variable_list: str):
    excel_path = os.path.join(workdir, VARIABLE_REQUEST_XLSX)
    try:
        df = pd.read_excel(excel_path, sheet_name="ISM")
    except IOError:
        print(
            "ERROR: Unable to open the variable request file. Is the path correct? "
            + excel_path
        )
        raise

    df = df.dropna(subset=["Variable Name"])

    if variable_list == "ismip7_xyt":
        df = df[df["Dim"] == "x,y,t"]
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


def _load_experiments_csv(file_path: str):
    experiments = []
    frame = pd.read_csv(file_path, delimiter=";")
    for _, row in frame.iterrows():
        experiments.append(
            {
                "experiment": row["experiment"],
                "startinf": datetime.datetime.strptime(row["startinf"], "%Y-%m-%d"),
                "startsup": datetime.datetime.strptime(row["startsup"], "%Y-%m-%d"),
                "endinf": datetime.datetime.strptime(row["endinf"], "%Y-%m-%d"),
                "endsup": datetime.datetime.strptime(row["endsup"], "%Y-%m-%d"),
                "duration": int(row["duration"]),
            }
        )
    return experiments


def _run_compliance_checker(
    source_path: str,
    commit_num: str,
    ismip_meta,
    ismip_var,
    mandatory_variables,
    experiments,
    criteria_file,
) -> None:
    if not os.path.isdir(source_path):
        print(f"ERROR: Directory not found: '{source_path}'. Please check your --source-path argument.")
        return

    try:
        with open(os.path.join(source_path, "compliance_checker_log.txt"), "w") as f:
            print("-> Checking " + source_path)
            print()
            today = datetime.date.today()
            _write_log_header(f, commit_num, source_path, today, criteria_file)

            experiment_groups = _group_files_by_experiment(source_path)
            if not experiment_groups:
                msg = f"No .nc files found in directory '{source_path}'. Please check your --source-path argument."
                print(f"ERROR: {msg}")
                f.write(f"ERROR: {msg}\n")
                return

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

    except TypeError as err:
        print(
            "Something went wrong with your dataset. Please, check your file(s) carefully. Error:",
            err,
        )


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

        year_range_field = parts[ISMIP7_FILENAME_YEAR_RANGE_IDX].removesuffix(".nc")
        year_range_match = re.fullmatch(r"(\d{4})-(\d{4})", year_range_field)
        if not year_range_match:
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
                actual_start = min(_decoded_time).item().year
                actual_end = max(_decoded_time).item().year
                if fn_start_year != actual_start:
                    log_file.write(
                        f" - ERROR: filename start year {fn_start_year} does not match first time step year {actual_start}.\n"
                    )
                    errors += 1
                if fn_end_year != actual_end:
                    log_file.write(
                        f" - ERROR: filename end year {fn_end_year} does not match last time step year {actual_end}.\n"
                    )
                    errors += 1
                if fn_start_year == actual_start and fn_end_year == actual_end:
                    log_file.write(
                        f" - Filename year range {fn_start_year}-{fn_end_year} matches time axis: OK\n"
                    )

    return errors


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

    if ds[ivar].attrs["units"] == ismip_meta[var_index]["units"]:
        log_file.write(" - The unit is correct: " + ds[ivar].attrs["units"] + "\n")
    else:
        log_file.write(
            " - ERROR: The unit of the variable is "
            + ds[ivar].attrs["units"]
            + " and should be "
            + ismip_meta[var_index]["units"]
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
) -> int:
    errors = 0

    log_file.write("TIME Tests \n")
    if not ({"t"}.issubset(dim) or {"time"}.issubset(dim)):
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

    if len(ds["time"].values) > 1:
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

        dateformat_start_exp = datetime.datetime(
            start_exp.item().year, start_exp.item().month, start_exp.item().day
        )
        if exp["startinf"] <= dateformat_start_exp <= exp["startsup"]:
            log_file.write(
                " - Experiment starts correctly on "
                + start_exp.item().strftime("%Y-%m-%d")
                + ".\n"
            )
        else:
            log_file.write(
                " - ERROR: the experiment starts the "
                + start_exp.item().strftime("%Y-%m-%d")
                + ". The date should be comprised between "
                + exp["startinf"].strftime("%Y-%m-%d")
                + " and "
                + exp["startsup"].strftime("%Y-%m-%d")
                + "\n"
            )
            errors += 1

        if exp["endinf"] <= dateformat_end_exp <= exp["endsup"]:
            log_file.write(
                " - Experiment ends correctly on "
                + end_exp.item().strftime("%Y-%m-%d")
                + ".\n"
            )
        else:
            log_file.write(
                " - ERROR: the experiment ends on "
                + end_exp.item().strftime("%Y-%m-%d")
                + ". The date should be comprised between "
                + exp["endinf"].strftime("%Y-%m-%d")
                + " and "
                + exp["endsup"].strftime("%Y-%m-%d")
                + "\n"
            )
            errors += 1
    else:
        if duration_years == exp["duration"]:
            log_file.write(" - Experiment lasts " + str(duration_years) + " years.\n")
            dateformat_start_exp = datetime.datetime(
                start_exp.item().year,
                start_exp.item().month,
                start_exp.item().day,
            )
            if exp["startinf"] <= dateformat_start_exp <= exp["startsup"]:
                log_file.write(
                    " - Experiment starts correctly on "
                    + start_exp.item().strftime("%Y-%m-%d")
                    + ".\n"
                )
            else:
                log_file.write(
                    " - ERROR: the experiment starts the "
                    + start_exp.item().strftime("%Y-%m-%d")
                    + ". The date should be comprised between "
                    + exp["startinf"].strftime("%Y-%m-%d")
                    + " and "
                    + exp["startsup"].strftime("%Y-%m-%d")
                    + "\n"
                )
                errors += 1

            if exp["endinf"] <= dateformat_end_exp <= exp["endsup"]:
                log_file.write(
                    " - Experiment ends correctly on "
                    + end_exp.item().strftime("%Y-%m-%d")
                    + ".\n"
                )
            else:
                log_file.write(
                    " - ERROR: the experiment ends on "
                    + end_exp.item().strftime("%Y-%m-%d")
                    + ". The date should be comprised between "
                    + exp["endinf"].strftime("%Y-%m-%d")
                    + " and "
                    + exp["endsup"].strftime("%Y-%m-%d")
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
    if time_coord is None:
        log_file.write(" - ERROR (attributes): coordinate 'time' not found.\n")
        coord_errors += 1
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
        for coord in ("x", "y"):
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

    n_err = _check_naming(log_file, ds, file_name, region, dim, isscalar, report_naming_issues)
    var_naming_errors += n_err
    if n_err > 0:
        return var_naming_errors, var_num_errors, var_spatial_errors, var_time_errors, var_attr_errors

    grid_extent = AIS_GRID_EXTENT if region == "AIS" else GrIS_GRID_EXTENT
    possible_resolution = AIS_POSSIBLE_RESOLUTION if region == "AIS" else GrIS_POSSIBLE_RESOLUTION

    for ivar in file_variables:
        if ivar in ismip_var:
            log_file.write("** Tested Variable: " + ivar + "\n")
            log_file.write(" \n")
            var_index = [k for k in range(len(ismip_var)) if ismip_var[k] == ivar][0]

            var_num_errors += _check_numerical(log_file, ds, ivar, ismip_meta, var_index, region, isscalar)

            if not isscalar:
                var_spatial_errors += _check_spatial(log_file, ds, grid_extent, possible_resolution)

            var_time_errors += _check_time(log_file, ds, dim, experiments, experiment_name)

            var_attr_errors += _check_attributes(log_file, ds, ivar, ismip_meta, var_index, isscalar, ismip_meta[var_index].get("type", ""), region)

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
        log_file, commit_num: str, source_path: str, today: datetime.date, criteria_file: str,
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
    log_file.write(f"Commit Number: {commit_num} \n")
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


if __name__ == "__main__":
    main()
