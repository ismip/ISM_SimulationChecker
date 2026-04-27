#!/usr/bin/env python3
import datetime
import os
import subprocess
import argparse

import numpy as np
import pandas as pd
import xarray as xr
from tqdm import tqdm


DEFAULT_SOURCE_PATH = "./Models/GrIS/ISMIP7/SYNTH1/CORE"
DEFAULT_VARIABLE_LIST = "ismip7_scalars"
VARIABLE_LIST_CHOICES = ("ismip7_scalars", "ismip7_xyt", "ismip7")

VARIABLE_REQUEST_XLSX = os.path.join("conventions", "ISMIP7_variable_request.xlsx")

EXPERIMENTS_ISMIP7_CSV_FILENAME = "experiments_ismip7.csv"

AIS_GRID_EXTENT = [-3040000, -3040000, 3040000, 3040000]
GrIS_GRID_EXTENT = [-720000, -3450000, 960000, -570000]
AIS_POSSIBLE_RESOLUTION = [1, 2, 4, 8, 16, 32]
GrIS_POSSIBLE_RESOLUTION = [1, 2, 4, 8, 16, 32]

TIME_STEP_MIN_DAYS = 365
TIME_STEP_MAX_DAYS = 366

# ISMIP7 CORE file naming convention:
# {var}_{region}_{project}_{submission}_{modelid}_{forcing}_{forcingid}_{experiment}_{configid}_{startyear}-{endyear}.nc
ISMIP7_FILENAME_PARTS = 10
ISMIP7_FILENAME_VAR_IDX = 0
ISMIP7_FILENAME_REGION_IDX = 1
ISMIP7_FILENAME_EXPERIMENT_IDX = 7


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
        print(
            "Commit number associated with this code. Is there a .git in this directory ?"
        )
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
        help="Variable list to apply: ismip7 or ismip7_scalars.",
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
    try:
        with open(os.path.join(source_path, "compliance_checker_log.txt"), "w") as f:
            print("-> Checking " + source_path)
            print()
            today = datetime.date.today()
            _write_log_header(f, commit_num, source_path, today, criteria_file)

            experiment_groups = _group_files_by_experiment(source_path)

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
            report_naming_issues=summary["report_naming_issues"],
        )

    except TypeError as err:
        print(
            "Something went wrong with your dataset. Please, check your file(s) carrefully. Error:",
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

    file_name = os.path.basename(file)
    file_name_split = file_name.split("_")

    considered_variable = file_name_split[ISMIP7_FILENAME_VAR_IDX]
    region = file_name_split[ISMIP7_FILENAME_REGION_IDX]

    try:
        ds = xr.open_dataset(os.path.join(source_path, file), use_cftime=True)
    except (ValueError, TypeError) as e:
        log_file.write(" - ERROR: Cannot open " + file_name + ": " + str(e) + "\n")
        var_naming_errors += 1
        return {
            "var_naming_errors": var_naming_errors,
            "var_num_errors": var_num_errors,
            "var_spatial_errors": var_spatial_errors,
            "var_time_errors": var_time_errors,
        }
    file_variables = list(ds.data_vars)

    # ISMIP7 CORE naming convention:
    # var_region_project_submission_modelid_forcing_forcingid_experiment_configid_startyear-endyear.nc
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
        }

    if considered_variable in ismip_var:
        var_naming_errors, var_num_errors, var_spatial_errors, var_time_errors = (
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

    var_errors = var_naming_errors + var_num_errors + var_spatial_errors + var_time_errors

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
    }


def _check_naming(
    log_file,
    file_name: str,
    region: str,
    dim: set,
    isscalar: bool,
    report_naming_issues: list,
) -> int:
    errors = 0

    if not isscalar and not {"x", "y"}.issubset(dim):
        log_file.write(
            "- ERROR: Compliance check ignored: x or y in the mandatory dimensions (x,y,t) is missing.\n"
        )
        log_file.write(
            "                                   Only " + str(list(dim)) + " has been detected.\n"
        )
        report_naming_issues.append(
            "Compliance check ignored: x or y in the mandatory dimensions (x,y,t) is missing in "
            + file_name
        )
        return errors + 1

    if region not in ["AIS", "GrIS"]:
        log_file.write(
            "- ERROR: Region "
            + region
            + " not recognized. It should be AIS or GrIS. The compliance check has been interrupted for this variable.\n"
        )
        report_naming_issues.append(
            "Compliance check ignored: region (AIS/GrIS) not identified in the file "
            + file_name
            + " due to wrong naming."
        )
        errors += 1

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
            " - ERROR: Upper rigth corner of the grid ["
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
            " - ERROR: The time dimensions is missing. Time Tests have been ignored.\n"
        )
        return errors + 1

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
            " - ERROR: the time serie is not monotonous. Time segments have probably been concatenate in a wrong order.\n"
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

    if duration_years == experiments[index_exp]["duration"]:
        log_file.write(" - Experiment lasts " + str(duration_years) + " years.\n")
        dateformat_start_exp = datetime.datetime(
            start_exp.item().year,
            start_exp.item().month,
            start_exp.item().day,
        )
        if (
            experiments[index_exp]["startinf"]
            <= dateformat_start_exp
            <= experiments[index_exp]["startsup"]
        ):
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
                + experiments[index_exp]["startinf"].strftime("%Y-%m-%d")
                + " and "
                + experiments[index_exp]["startsup"].strftime("%Y-%m-%d")
                + "\n"
            )
            errors += 1

        dateformat_end_exp = datetime.datetime(
            end_exp.item().year,
            end_exp.item().month,
            end_exp.item().day,
        )
        if (
            experiments[index_exp]["endinf"]
            <= dateformat_end_exp
            <= experiments[index_exp]["endsup"]
        ):
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
                + experiments[index_exp]["endinf"].strftime("%Y-%m-%d")
                + " and "
                + experiments[index_exp]["endsup"].strftime("%Y-%m-%d")
                + "\n"
            )
            errors += 1
    else:
        end_date = start_exp + np.timedelta64(experiments[index_exp]["duration"] * 365, "D")
        log_file.write(
            " - ERROR: the experiment lasts "
            + str(duration_years)
            + " years. The duration should be "
            + str(experiments[index_exp]["duration"])
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

    log_file.write(" \n")
    log_file.write("Experiment: " + experiment_name + " - File: " + file_name + "\n")
    log_file.write(" \n")

    header_ds = ds.to_dict(data=False)
    dim = set(list(header_ds["coords"].keys()))

    index = ismip_var.index(considered_variable)
    isscalar = ismip_meta[index]["dim"] == "t"

    n_err = _check_naming(log_file, file_name, region, dim, isscalar, report_naming_issues)
    var_naming_errors += n_err
    if n_err > 0:
        return var_naming_errors, var_num_errors, var_spatial_errors, var_time_errors

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

    return var_naming_errors, var_num_errors, var_spatial_errors, var_time_errors


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
