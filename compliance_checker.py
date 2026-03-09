import datetime
import os
import subprocess

import cftime
import numpy as np
import pandas as pd
import xarray as xr
from tqdm import tqdm


def main() -> None:
    source_path = "./test"
    workdir = os.getcwd()

    commit_num = _get_commit_number()
    ismip_meta, ismip_var, mandatory_variables = _load_criteria(workdir)

    experiments_ismip6_ext = _load_experiments_csv(
        os.path.join(workdir, "experiments_ismip6_ext.csv")
    )
    experiments_ismip6 = _load_experiments_csv(
        os.path.join(workdir, "experiments_ismip6.csv")
    )

    scalar_variables_ismip6 = [
        "lim",
        "limnsw",
        "iareagr",
        "iareafl",
        "tendacabf",
        "tendlibmassbf",
        "tendlibmassbffl",
        "tendlicalvf",
        "tendlifmassbf",
        "tendligroundf",
    ]
    scalar_variables = scalar_variables_ismip6

    # Set up the experiment list: extension (2300) or ISMIP6 (2100).
    experiments = experiments_ismip6

    _run_compliance_checker(
        source_path=source_path,
        commit_num=commit_num,
        ismip_meta=ismip_meta,
        ismip_var=ismip_var,
        variables=ismip_var,
        mandatory_variables=mandatory_variables,
        experiments=experiments,
        experiments_ismip6_ext=experiments_ismip6_ext,
        scalar_variables=scalar_variables,
    )


def _get_commit_number() -> str:
    try:
        bash_command = "git log --pretty=format:'%h' -n 1"
        process = subprocess.Popen(bash_command.split(), stdout=subprocess.PIPE)
        commit_num, _error = process.communicate()
        return commit_num.decode("UTF-8")
    except Exception:
        print(
            "Commit number associtad with this code. Is there a .git in this directory ?"
        )
        return "No commit number identified."


def _load_criteria(workdir: str):
    try:
        ismip = pd.read_csv(
            workdir + "/ismip6_criteria.csv", delimiter=";", decimal=","
        )
    except IOError:
        print(
            "ERROR: Unable to open the compliance criteria file (.csv required with ; as delimiter and , for decimal.). Is the path to the file correct ? "
            + workdir
            + "ismip6_criteria_v0.csv"
        )
        raise

    ismip_meta = ismip.to_dict("records")
    ismip_var = [dic["variable"] for dic in ismip_meta]
    ismip_mandatory_var = ismip["variable"][ismip.mandatory == 1].tolist()
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
    variables,
    mandatory_variables,
    experiments,
    experiments_ismip6_ext,
    scalar_variables,
) -> None:
    _ = (experiments_ismip6_ext, scalar_variables)

    try:
        with open(os.path.join(source_path, "compliance_checker_log.txt"), "w") as f:
            print("-> Checking " + source_path)
            print()
            experiment_directories, files = _files_and_subdirectories(source_path)
            _ = files
            today = datetime.date.today()

            _write_log_header(f, commit_num, source_path, today)

            summary = _process_experiments(
                log_file=f,
                source_path=source_path,
                experiment_directories=experiment_directories,
                mandatory_variables=mandatory_variables,
                experiments=experiments,
                variables=variables,
                ismip_var=ismip_var,
                ismip_meta=ismip_meta,
            )

            exp_counter = summary["exp_counter"]
            file_counter = summary["file_counter"]
            total_errors = summary["total_errors"]
            total_warnings = summary["total_warnings"]
            total_naming_errors = summary["total_naming_errors"]
            total_num_errors = summary["total_num_errors"]
            total_spatial_errors = summary["total_spatial_errors"]
            total_time_errors = summary["total_time_errors"]
            total_file_errors = summary["total_file_errors"]
            report_naming_issues = summary["report_naming_issues"]

        _insert_synthesis(
            source_path=source_path,
            exp_counter=exp_counter,
            file_counter=file_counter,
            total_errors=total_errors,
            total_file_errors=total_file_errors,
            total_naming_errors=total_naming_errors,
            total_num_errors=total_num_errors,
            total_spatial_errors=total_spatial_errors,
            total_time_errors=total_time_errors,
            total_warnings=total_warnings,
            report_naming_issues=report_naming_issues,
        )

    except TypeError as err:
        print(
            "Something went wrong with your dataset. Please, check your file(s) carrefully. Error:",
            err,
        )


def _process_experiments(
    log_file,
    source_path: str,
    experiment_directories,
    mandatory_variables,
    experiments,
    variables,
    ismip_var,
    ismip_meta,
):
    total_warnings = 0
    total_naming_errors = 0
    total_num_errors = 0
    total_spatial_errors = 0
    total_time_errors = 0
    total_file_errors = 0
    report_naming_issues = []

    file_counter = 0
    exp_counter = 0
    for xp in experiment_directories:
        exp_counter += 1

        exp_summary = _process_single_experiment(
            log_file=log_file,
            source_path=source_path,
            xp=xp,
            mandatory_variables=mandatory_variables,
            experiments=experiments,
            variables=variables,
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
        "total_warnings": total_warnings,
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
    xp: str,
    mandatory_variables,
    experiments,
    variables,
    ismip_var,
    ismip_meta,
    report_naming_issues,
):
    exp_dir, exp_files = _files_and_subdirectories(os.path.join(source_path, xp))
    _ = exp_dir
    exp_files = list(filter(lambda file: file.split(".")[-1] == "nc", exp_files))

    exp_errors = 0
    exp_naming_errors = 0
    exp_num_errors = 0
    exp_spatial_errors = 0
    exp_time_errors = 0
    exp_file_errors = 0
    exp_warnings = 0
    exp_naming_warnings = 0
    exp_num_warnings = 0
    exp_spatial_warnings = 0
    exp_time_warnings = 0

    for i in exp_files:
        file_name_split = i.split("_")
        variable = file_name_split[0]
        temp_mandatory_var = mandatory_variables
        if variable in mandatory_variables:
            temp_mandatory_var.remove(variable)

    experiment_chain = xp.split("_")
    if len(experiment_chain) == 2:
        experiment_name = "_".join(experiment_chain[:-1])
        grid_resolution = int(experiment_chain[-1])
    else:
        experiment_name = xp
        grid_resolution = 0
        print(
            "Error in the naming of the experiment ",
            xp,
            ". Should be similar to expXXX_RES",
        )

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
                + xp
                + " : all mandatory variables exist. \n"
            )
        else:
            log_file.write(
                "ERROR: In experiment "
                + xp
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
                xp=xp,
                file=file,
                experiment_name=experiment_name,
                grid_resolution=grid_resolution,
                variables=variables,
                ismip_var=ismip_var,
                ismip_meta=ismip_meta,
                experiments=experiments,
                report_naming_issues=report_naming_issues,
            )

            exp_naming_errors = exp_naming_errors + file_summary["var_naming_errors"]
            exp_num_errors = exp_num_errors + file_summary["var_num_errors"]
            exp_spatial_errors = exp_spatial_errors + file_summary["var_spatial_errors"]
            exp_time_errors = exp_time_errors + file_summary["var_time_errors"]
            exp_errors = (
                exp_time_errors
                + exp_spatial_errors
                + exp_num_errors
                + exp_naming_errors
                + exp_file_errors
            )
            exp_num_warnings = exp_num_warnings + file_summary["var_num_warnings"]
            exp_spatial_warnings = (
                exp_spatial_warnings + file_summary["var_spatial_warnings"]
            )
            exp_time_warnings = exp_time_warnings + file_summary["var_time_warnings"]

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
        exp_errors = (
            exp_time_errors
            + exp_spatial_errors
            + exp_num_errors
            + exp_naming_errors
            + exp_file_errors
        )
        report_naming_issues.append(
            "Compliance check ignored : experiment "
            + experiment_name
            + " not in the experiments list."
        )

    _ = (exp_warnings, exp_naming_warnings)
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
    xp: str,
    file: str,
    experiment_name: str,
    grid_resolution: int,
    variables,
    ismip_var,
    ismip_meta,
    experiments,
    report_naming_issues,
):
    var_errors = 0
    var_warnings = 0
    var_naming_errors = 0
    var_num_errors = 0
    var_spatial_errors = 0
    var_time_errors = 0
    var_warnings = 0
    var_warnings = 0
    var_naming_warnings = 0
    var_num_warnings = 0
    var_spatial_warnings = 0
    var_time_warnings = 0

    split_path = os.path.normpath(file).split(os.sep)
    file_name = split_path[-1]
    file_name_split = file_name.split("_")

    considered_variable = file_name_split[0]
    region = file_name_split[1]
    group = file_name_split[2]
    model = file_name_split[3]
    _ = (group, model)
    file_extention = file_name_split[len(file_name_split) - 1][-2:]

    ds = xr.open_dataset(os.path.join(source_path, xp, file))
    file_variables = list(ds.data_vars)

    if file_extention != "nc":
        log_file.write(
            " !! "
            + file_name
            + " is not a NETCDF file. The compliance check is ignored."
            + "\n"
        )
        return {
            "var_naming_errors": var_naming_errors,
            "var_num_errors": var_num_errors,
            "var_spatial_errors": var_spatial_errors,
            "var_time_errors": var_time_errors,
            "var_num_warnings": var_num_warnings,
            "var_spatial_warnings": var_spatial_warnings,
            "var_time_warnings": var_time_warnings,
        }

    if int(len(file_name_split)) != 5:
        log_file.write(
            " - ERROR: the file name "
            + file_name
            + " do not follow the naming convention.\n"
        )
        report_naming_issues.append(
            "Compliance check ignored: file "
            + file_name
            + " do not follow the naming convention."
        )
        var_naming_errors += 1
        return {
            "var_naming_errors": var_naming_errors,
            "var_num_errors": var_num_errors,
            "var_spatial_errors": var_spatial_errors,
            "var_time_errors": var_time_errors,
            "var_num_warnings": var_num_warnings,
            "var_spatial_warnings": var_spatial_warnings,
            "var_time_warnings": var_time_warnings,
        }

    experiment_varname = file_name_split[4][:-3]
    if experiment_varname != experiment_name:
        log_file.write(
            " - ERROR: in the file name "
            + file_name
            + ", the experiment name ("
            + experiment_varname
            + ") do not match the directory name: "
            + experiment_name
            + ".\n"
        )
        report_naming_issues.append(
            "Compliance check ignored: in the file name "
            + file_name
            + ", the experiment name ("
            + experiment_varname
            + ") do not match the directory name: "
            + experiment_name
            + ".\n"
        )
        var_naming_errors += 1
        return {
            "var_naming_errors": var_naming_errors,
            "var_num_errors": var_num_errors,
            "var_spatial_errors": var_spatial_errors,
            "var_time_errors": var_time_errors,
            "var_num_warnings": var_num_warnings,
            "var_spatial_warnings": var_spatial_warnings,
            "var_time_warnings": var_time_warnings,
        }

    if considered_variable in variables:
        var_naming_errors, var_num_errors, var_spatial_errors, var_time_errors = (
            _run_variable_checks(
                log_file=log_file,
                ds=ds,
                file_name=file_name,
                considered_variable=considered_variable,
                experiment_name=experiment_name,
                grid_resolution=grid_resolution,
                file_variables=file_variables,
                region=region,
                ismip_var=ismip_var,
                ismip_meta=ismip_meta,
                experiments=experiments,
                report_naming_issues=report_naming_issues,
            )
        )

    var_errors = (
        var_errors
        + var_naming_errors
        + var_num_errors
        + var_spatial_errors
        + var_time_errors
    )
    var_warnings = (
        var_warnings + var_num_warnings + var_spatial_warnings + var_time_warnings
    )

    log_file.write("\n")
    log_file.write("----------------------------------------------------------\n")
    log_file.write(
        experiment_name + " - " + considered_variable + " - File:" + file_name + "\n"
    )
    if var_errors > 0:
        log_file.write(
            str(var_errors) + " error(s). Please review before sharing." + "\n"
        )
    else:
        log_file.write("No errors. Good job !" + "\n")
    if var_warnings > 0:
        log_file.write(
            str(var_warnings) + " warning(s). Please review before sharing." + "\n"
        )
    else:
        log_file.write("No warnings." + "\n")
    log_file.write("----------------------------------------------------------\n")

    return {
        "var_naming_errors": var_naming_errors,
        "var_num_errors": var_num_errors,
        "var_spatial_errors": var_spatial_errors,
        "var_time_errors": var_time_errors,
        "var_num_warnings": var_num_warnings,
        "var_spatial_warnings": var_spatial_warnings,
        "var_time_warnings": var_time_warnings,
    }


def _run_variable_checks(
    log_file,
    ds,
    file_name: str,
    considered_variable: str,
    experiment_name: str,
    grid_resolution: int,
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

    if not set(["x", "y"]).issubset(dim):
        log_file.write(
            "- ERROR: Compliance check ignored: x or y in the mandatory dimensions (x,y,t) is missing.\n"
        )
        log_file.write(
            "                                   Only "
            + str(list(header_ds["coords"].keys()))
            + " has been detected.\n"
        )
        report_naming_issues.append(
            "Compliance check ignored: x or y in the mandatory dimensions (x,y,t) is missing in "
            + file_name
        )
        var_naming_errors += 1
        return var_naming_errors, var_num_errors, var_spatial_errors, var_time_errors

    if region.upper() not in ["AIS", "GIS"]:
        log_file.write(
            "- ERROR: Region "
            + region
            + " not recognized. It should be AIS or GIS. The compliance check has been interrupted for this variable.\n"
        )
        report_naming_issues.append(
            "Compliance check ignored: region (AIS/GIS) not identified in the file "
            + file_name
            + " due to wrong naming."
        )
        var_naming_errors += 1
        return var_naming_errors, var_num_errors, var_spatial_errors, var_time_errors

    if region == "AIS":
        grid_extent = [-3040000, -3040000, 3040000, 3040000]
        possible_resolution = [1, 2, 4, 8, 16, 32]
    else:
        grid_extent = [-720000, -3450000, 960000, -570000]
        possible_resolution = [1, 2, 4, 5, 10, 20]

    for ivar in file_variables:
        if ivar in ismip_var:
            log_file.write("** Tested Variable: " + ivar + "\n")
            log_file.write(" \n")
            var_index = [k for k in range(len(ismip_var)) if ismip_var[k] == ivar]

            log_file.write("NUMERICAL Tests \n")
            if ds[ivar].attrs["units"] == ismip_meta[var_index[0]]["units"]:
                log_file.write(
                    " - The unit is correct: " + ds[ivar].attrs["units"] + "\n"
                )
            else:
                log_file.write(
                    " - ERROR: The unit of the variable is "
                    + ds[ivar].attrs["units"]
                    + " and should be "
                    + ismip_meta[var_index[0]]["units"]
                    + " \n"
                )
                var_num_errors += 1

            if False in ds[ivar].isnull():
                if (
                    ds[ivar].min(skipna=True).item()
                    >= ismip_meta[var_index[0]]["min_value_" + region.lower()]
                ):
                    log_file.write(" - The minimum value successfully verified.\n")
                else:
                    log_file.write(
                        " - ERROR: The minimum value ("
                        + str(ds[ivar].min(skipna=True).values.item(0))
                        + ") is out of range. Min value accepted: "
                        + str(ismip_meta[var_index[0]]["min_value_" + region.lower()])
                        + "\n"
                    )
                    var_num_errors += 1

                if (
                    ds[ivar].max(skipna=True).item()
                    <= ismip_meta[var_index[0]]["max_value_" + region.lower()]
                ):
                    log_file.write(" - The maximum value successfully verified.\n")
                else:
                    log_file.write(
                        " - ERROR: The maximum value ("
                        + str(ds[ivar].max(skipna=True).values.item(0))
                        + ") is out of range. Max value accepted: "
                        + str(ismip_meta[var_index[0]]["max_value_" + region.lower()])
                        + "\n"
                    )
                    var_num_errors += 1
            else:
                log_file.write(" - ERROR: The array only contains Nan values.\n")
                var_num_errors += 1

            (
                var_spatial_errors,
                var_time_errors,
            ) = _run_spatial_and_time_checks(
                log_file=log_file,
                ds=ds,
                dim=dim,
                region=region,
                experiments=experiments,
                experiment_name=experiment_name,
                grid_extent=grid_extent,
                possible_resolution=possible_resolution,
                grid_resolution=grid_resolution,
                var_spatial_errors=var_spatial_errors,
                var_time_errors=var_time_errors,
            )

    return var_naming_errors, var_num_errors, var_spatial_errors, var_time_errors


def _run_spatial_and_time_checks(
    log_file,
    ds,
    dim,
    region: str,
    experiments,
    experiment_name: str,
    grid_extent,
    possible_resolution,
    grid_resolution: int,
    var_spatial_errors: int,
    var_time_errors: int,
):
    log_file.write("SPATIAL Tests \n")
    coords = ds.coords.to_dataset()
    Xbottomleft = int(min(coords["x"]).values.item())
    Ybottomleft = int(min(coords["y"]).values.item())
    Xtopright = int(max(coords["x"]).values.item())
    Ytopright = int(max(coords["y"]).values.item())

    if Xbottomleft == grid_extent[0] & Ybottomleft == grid_extent[1]:
        log_file.write(" - Grid: Lowest left corner is well defined.\n")
    else:
        log_file.write(
            " - ERROR: Lowest left corner of the grid ["
            + str(Xbottomleft)
            + ","
            + str(Ybottomleft)
            + "] is not correctly defined. ["
            + str(grid_extent[0])
            + ","
            + str(grid_extent[1])
            + "] Expected\n"
        )
        var_spatial_errors += 1
    if Xtopright == grid_extent[2] & Ytopright == grid_extent[3]:
        log_file.write(" - Grid: Upper right corner is well defined.\n")
    else:
        log_file.write(
            " - ERROR: Upper rigth corner of the grid ["
            + str(Xtopright)
            + ","
            + str(Ytopright)
            + "] is not correctly defined. ["
            + str(grid_extent[0])
            + ","
            + str(grid_extent[1])
            + "] Expected\n"
        )
        var_spatial_errors += 1

    Xresolution = round((coords["x"][1].values - coords["x"][0].values) / 1000, 0)
    Yresolution = round((coords["y"][1].values - coords["y"][0].values) / 1000, 0)
    if Xresolution in set(possible_resolution) and Yresolution in set(
        possible_resolution
    ):
        if Xresolution == grid_resolution and Yresolution == grid_resolution:
            log_file.write(
                " - The grid resolution ("
                + str(Xresolution)
                + ") was successfully verified.\n"
            )
        else:
            log_file.write(
                " - ERROR: The grid resolution ( "
                + str(Xresolution)
                + " or "
                + str(Yresolution)
                + ") is different of "
                + str(grid_resolution)
                + "declared in the file name.\n"
            )
            var_spatial_errors += 1
    else:
        log_file.write(
            " - Error: x: "
            + str(Xresolution)
            + ",y: "
            + str(Yresolution)
            + " is not an authorized grid resolution.\n"
        )
        var_spatial_errors += 1

    var_time_errors = _run_time_checks(
        log_file=log_file,
        ds=ds,
        dim=dim,
        experiments=experiments,
        experiment_name=experiment_name,
        var_time_errors=var_time_errors,
    )
    return var_spatial_errors, var_time_errors


def _run_time_checks(
    log_file,
    ds,
    dim,
    experiments,
    experiment_name: str,
    var_time_errors: int,
):
    log_file.write("TIME Tests \n")
    if not (set(["t"]).issubset(dim) or set(["time"]).issubset(dim)):
        log_file.write(
            " - ERROR: The time dimensions is missing. Time Tests have been ignored.\n"
        )
        return var_time_errors + 1

    iteration = len(ds.coords["time"])
    start_exp = min(ds["time"]).values.astype("datetime64[D]")
    end_exp = max(ds["time"]).values.astype("datetime64[D]")
    avgyear = 365
    duration_days = end_exp - start_exp
    duration_years = duration_days.astype("timedelta64[Y]") / np.timedelta64(1, "Y")
    _ = duration_years

    index_exp = [dic["experiment"] for dic in experiments].index(experiment_name)
    if not (
        np.issubdtype(start_exp.dtype, np.datetime64)
        & np.issubdtype(start_exp.dtype, np.datetime64)
    ):
        log_file.write(
            " - ERROR: the time format of the Netcdf file is not recognized.Time Tests have been ignored.\n"
        )
        return var_time_errors + 1

    if not _strictly_increasing(ds.coords["time"]):
        log_file.write(
            " - ERROR: the time serie is not monotonous. Time segments have probably been concatenate in a wrong order.\n"
        )
        return var_time_errors + 1

    if isinstance(ds["time"].values[1] - ds["time"].values[0], datetime.timedelta):
        time_step = (ds["time"].values[1] - ds["time"].values[0]).days
    else:
        if isinstance(ds["time"].values[1] - ds["time"].values[0], np.timedelta64):
            time_step = np.timedelta64(
                ds["time"].values[1] - ds["time"].values[0],
                "D",
            ) / np.timedelta64(1, "D")
        else:
            time_step = ds["time"].values[1] - ds["time"].values[10]

    if 360 <= time_step <= 367:
        log_file.write(" - Time step: " + str(time_step) + " days" + "\n")
    else:
        log_file.write(
            " - ERROR: the time step("
            + str(time_step)
            + ") should be comprised between [360,367].\n"
        )
        var_time_errors += 1

    duration_days = pd.to_timedelta(time_step * iteration, "D")
    duration_years = round(pd.to_numeric(duration_days.days / avgyear))
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
            var_time_errors += 1

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
            var_time_errors += 1
    else:
        end_date = start_exp + np.timedelta64(experiments[2]["duration"] * 365, "D")
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
        var_time_errors += 1

    return var_time_errors


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


def _files_and_subdirectories(path: str):
    files = []
    directories = []
    for f in os.listdir(path):
        if os.path.isfile(os.path.join(path, f)):
            files.append(f)
        elif os.path.isdir(os.path.join(path, f)):
            directories.append(f)
    return directories, files


def _strictly_increasing(values) -> bool:
    return all(x < y for x, y in zip(values, values[1:]))


def _write_log_header(
    log_file, commit_num: str, source_path: str, today: datetime.date
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
    log_file.write("verification criteria: ismip6_criteria.csv \n")
    log_file.write("date: " + today.strftime("%Y/%m/%d") + "\n")
    log_file.write("source: https://github.com/jbbarre/ISM_SimulationChecker \n")
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
    log_file.write("Tips: Use Cltr+F to look for specific problems. \n")
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
    total_warnings: int,
    report_naming_issues,
) -> None:
    with open(os.path.join(source_path, "compliance_checker_log.txt"), "r") as f:
        contents = f.readlines()

    iline = 11
    contents.insert(iline, str(exp_counter) + " experiments checked.\n")
    iline += 1
    contents.insert(
        iline, str(file_counter) + " files checked (Scalar files are ignored).\n"
    )
    iline += 2
    contents.insert(iline, str(total_errors) + " error(s) detected.\n")
    iline += 1
    contents.insert(
        iline, "  - Mandatory variables: " + str(total_file_errors) + " error(s)\n"
    )
    iline += 1
    contents.insert(
        iline, "  - Naming Tests       : " + str(total_naming_errors) + " error(s)\n"
    )
    iline += 1
    contents.insert(
        iline, "  - Numerical Tests    : " + str(total_num_errors) + " error(s)\n"
    )
    iline += 1
    contents.insert(
        iline, "  - Spatial Tests      : " + str(total_spatial_errors) + " error(s)\n"
    )
    iline += 1
    contents.insert(
        iline, "  - Time Tests         : " + str(total_time_errors) + " error(s)\n"
    )
    iline += 2
    contents.insert(iline, str(total_warnings) + " warning(s) detected.\n")
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
