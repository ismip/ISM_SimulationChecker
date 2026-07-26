#
# ISMIP7 Compliance Checker — check summary
#
# 1. Naming (_check_naming, _check_file_variables)
#    - Variable field of the filename is a variable of the data request.
#    - The variable named in the filename is present in the file.
#    - The file holds no variables beyond that one, its coordinates, and the
#      companion variables CF lets them name: bounds, grid mapping, cell
#      measures and ancillary variables.  (warning)
#    - The variable's dimensions are the ones the data request asks for, in the
#      conventional (time, z, y, x) order.
#    - Region field in filename matches the region inferred from the grid (AIS/GrIS).
#      An unrecognised region costs only the checks that need it (value range,
#      grid extent and resolution, crs); the rest of the file is still checked.
#    - ISM member id (field 4) matches format mNNN (e.g. m001).
#    - ESM name (field 5) is a recognised CMIP6/CMIP7 model name.
#    - Forcing member id (field 6) matches format fNNN (e.g. f001).
#    - Set counter (field 8) matches format [C|E|P]NNN (e.g. C001, E041, P132).
#    - Year range (field 9) matches format YYYY-YYYY and start <= end.  What the
#      range means -- whether the experiment allows it, and whether the time axis
#      delivers it -- is checked under Time below.
#
# 2. Numerical (_check_numerical)
#    - Variable units match the data request (any UDUNITS spelling of the
#      requested unit is accepted: 'm2', 'm^2' and 'm**2' are all the same).
#    - All values lie within the allowed min/max range for the relevant region,
#      at the severity that variable's 'range_severity' names (error unless the
#      data request says otherwise).
#    - Array is not entirely fill/missing values.
#
# 3. Spatial (_check_spatial)  [xyt variables only]
#    - Lower-left and upper-right grid corners lie within the expected AIS or GrIS extents.
#    - Grid resolution is one of the allowed values (1, 2, 4, 8, 16, 32 km).
#    - x and y resolution are equal (square cells).
#
# 4. Time (_check_time)
#    - Time dimension is present, is an unlimited (record) dimension, and its values are monotonically increasing.
#    - The file name's year range is one the experiment allows.
#    - The time axis is exactly the axis the experiment calls for: the expected
#      nominal years are reconstructed from experiments_ismip7.csv and encoded
#      per the ST/FL convention, then compared with what the file holds.  This is
#      what catches a missing, decimated or gappy axis, which endpoint-and-
#      cadence reasoning cannot see.
#    - For x,y,z,t snapshot variables the axis is instead checked against the
#      required set of snapshot nominal years: the run's last year, the century
#      marks inside it, and (for historical only) the run's first year.  A
#      missing snapshot is an error; an unasked-for one is a warning, since the
#      request specifies the snapshots as a minimum set.  That includes a
#      snapshot at 2000, which the data request does not ask for -- see
#      issue #12.
#
# 5. Attributes (_check_attributes)
#    - Global attributes present: group, model, contact_name, contact_email, crs
#      (epsg:3413 for GrIS, epsg:3031 for AIS).
#    - Coordinate attributes: time has units, calendar, bounds (FL vars); x/y have units (xyt).
#    - Variable standard_name matches data request (if specified).
#    - _FillValue must be present and equal the default netCDF4 fill value for the variable's dtype.
#      If missing_value is also present, it must equal _FillValue.
#    - Main variable is single-precision float (float32 / f4); so is the time
#      coordinate (warning -- one number per record cannot inflate a file).
#    - scale_factor and add_offset are not allowed on the main variable.
#
# A file is checked as far as it can be.  A naming problem stops the other
# checks only when it leaves them nothing to read -- a missing x or y dimension,
# or a file that does not contain the variable its name promises.  Everything
# else (a mistyped ESM name, a malformed year range, an unrecognised region) is
# reported and the file is checked on, so that one run tells a modeller
# everything that is wrong rather than only the first thing.
#
#
# Errors and warnings
# -------------------
#
# One rule, stated here once so that a new check is classified by citing it
# rather than by arguing the case again:
#
#   ERROR   -- the file, as written, is unusable for the intended analysis,
#              departs from the protocol in a way that changes the science, or
#              fails the data-hygiene requirements this archive is committing
#              to.  That last clause is deliberate: the output will be served
#              to the broader community for analysis for years, so uniformity
#              of encoding is a product requirement rather than a stylistic
#              preference, and "a reader could cope with it" is not grounds for
#              a warning.
#
#   WARNING -- the file is usable, the science is unaffected, and nothing
#              downstream has to work around it, but it departs from what the
#              request asked for in a way the modeller should look at and may
#              reasonably have intended.
#
# Three corollaries keep warnings from quietly becoming errors:
#
#   - Warnings never enter the error count and never change a file's verdict.
#     A file with warnings and no errors is compliant, and is told so.
#   - Warnings never affect the exit status.  Errors do.
#   - A check whose failure means the checker could not read something stays an
#     error.  Warnings never suppress later checks.
#
# An optional not_modelled.txt in the source directory silences the warning
# about non-mandatory variables an experiment carries no files for, and nothing
# else -- see _read_not_modelled.


import datetime
import difflib
import os
import re
import subprocess
import argparse
from importlib import metadata, resources
from typing import NamedTuple

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

# A timestamp may sit one day off the date its convention asks for, so that a
# model writing Dec 31 of year N rather than Jan 1 of year N+1 is not failed for
# rounding a boundary the other way.
TIME_STAMP_TOLERANCE = datetime.timedelta(days=1)

# How many individual years or timestamps to name before summarising the rest.
# A wrong time axis is usually wrong in one way repeated many times; printing
# 286 variations of the same finding buries it rather than supporting it.
MAX_REPORTED_TIME_MISMATCHES = 5

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


class Reporter:
    """Writes the log and counts what it wrote, by severity and category.

    Every finding has to reach two places at once: the line a modeller reads in
    the log, and the counter the synthesis block at the top of that log adds up.
    Keeping those in step by hand meant every check returning a count and every
    caller adding it on, sixty call sites of bookkeeping running in parallel with
    sixty writes.  Here the write is the count: a check says what it found, at
    the severity it means, and the arithmetic follows from that alone.

    Reporters nest.  :meth:`category` scopes findings to one of the checker's
    reporting categories, and :meth:`child` opens a sub-total -- one file's
    worth, say -- that still rolls up into its parent, so a file's own footer and
    the run-wide synthesis count the same events rather than counting separately
    and hoping to agree.
    """

    def __init__(
        self,
        log_file,
        parent: "Reporter | None" = None,
        category: str = "",
        qualifier: str | None = None,
        bullet: str = " - ",
    ):
        self.log_file = log_file
        self._parent = parent
        self._category = category
        # _check_attributes has always labelled its findings 'ERROR
        # (attributes)'.  The qualifier reproduces that without every other
        # check growing a label of its own.
        self._qualifier = qualifier
        # File-level findings are bulleted list items under the file's heading;
        # experiment-level ones are written flush left.
        self._bullet = bullet
        self.errors: dict[str, int] = {}
        self.warnings: dict[str, int] = {}

    def category(
        self, name: str, qualifier: str | None = None, bullet: str = " - "
    ) -> "Reporter":
        """A reporter that counts what it writes under reporting category `name`."""
        return Reporter(
            self.log_file,
            parent=self,
            category=name,
            qualifier=qualifier,
            bullet=bullet,
        )

    def child(self) -> "Reporter":
        """A reporter with its own sub-totals that still roll up into this one."""
        return Reporter(
            self.log_file,
            parent=self,
            category=self._category,
            qualifier=self._qualifier,
            bullet=self._bullet,
        )

    @property
    def total_errors(self) -> int:
        return sum(self.errors.values())

    @property
    def total_warnings(self) -> int:
        return sum(self.warnings.values())

    def error_count(self, category: str) -> int:
        return self.errors.get(category, 0)

    def warning_count(self, category: str) -> int:
        return self.warnings.get(category, 0)

    def write(self, text: str) -> None:
        """Write to the log without reporting a finding: headings and footers."""
        self.log_file.write(text)

    def error(self, message: str, count: int = 1) -> None:
        """Report a file that is unusable, or that departs from the protocol.

        `count` is for the findings that read better as one line than as
        several -- four mandatory variables missing from an experiment, say --
        but that are still four findings and not one.
        """
        self._report("ERROR", message, count)

    def warning(self, message: str, count: int = 1) -> None:
        """Report a departure from the request that leaves the file usable.

        Warnings do not enter the error count, do not change a file's verdict
        and do not affect the exit status; they say 'look at this', not 'fix
        this'.  See the policy note at the top of this module.
        """
        self._report("WARNING", message, count)

    def ok(self, message: str) -> None:
        """Record a check that passed."""
        self.write(f"{self._bullet}{message}\n")

    def note(self, message: str) -> None:
        """Record a check that did not run: not applicable, or nothing to read."""
        self.write(f"{self._bullet}{message}\n")

    def _report(self, label: str, message: str, count: int) -> None:
        prefix = label if self._qualifier is None else f"{label} ({self._qualifier})"
        self.write(f"{self._bullet}{prefix}: {message}\n")
        self._count(label, self._category, count)

    def _count(self, label: str, category: str, count: int) -> None:
        counter = self.errors if label == "ERROR" else self.warnings
        counter[category] = counter.get(category, 0) + count
        if self._parent is not None:
            self._parent._count(label, category, count)


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
    (
        ismip_meta,
        ismip_var,
        mandatory_variables,
        all_request_variables,
        all_mandatory_variables,
    ) = _load_criteria(variable_list)

    summary = _run_compliance_checker(
        source_path=source_path,
        version=version,
        ismip_meta=ismip_meta,
        ismip_var=ismip_var,
        mandatory_variables=mandatory_variables,
        all_request_variables=all_request_variables,
        all_mandatory_variables=all_mandatory_variables,
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


def _range_severity(value) -> str:
    """How a value outside a variable's min/max range should be reported.

    Issue #10 is that some of these bounds "are dependent on the forcing, input
    data and model implementation", so failing a run on them is too strong --
    but which ones is a per-variable question that the checker cannot answer
    from its side.  So the severity lives in the data request, one cell per
    variable row, and switching a variable is a data-only diff that needs no
    reasoning about the checker.

    Anything the column does not say is an error, which is what makes the
    column safe to add before it is filled in: a blank cell, a missing column
    and an unrecognised value all mean what the checker did before.
    """
    if value is not None and pd.notna(value) and str(value).strip().lower() == "warning":
        return "warning"
    return "error"


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

    # The whole request, before --variable-list narrows it below.  A file whose
    # variable is in the request but outside the selected list is skipped
    # rather than reported: checking the scalars of a directory says nothing
    # about the x,y,t files sitting beside them.
    all_request_variables = set(df["Variable Name"])
    # Which of them are mandatory, before the narrowing too: not_modelled.txt is
    # a statement about the submission rather than about one run of the checker,
    # so a mandatory variable named in it has to be caught whichever list the
    # run happens to have selected.
    all_mandatory_variables = set(
        df.loc[
            df["Mandatory (yes/no)"].astype(str).str.lower() == "yes", "Variable Name"
        ]
    )

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
            "range_severity": _range_severity(row.get("range_severity")),
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
    return (
        ismip_meta,
        ismip_var,
        ismip_mandatory_var,
        all_request_variables,
        all_mandatory_variables,
    )


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


def _timestamp_to_nominal_year(timestamp, var_type: str) -> int:
    """Return the nominal simulation year a timestamp encodes.

    The inverse of :func:`_nominal_to_timestamp`, tolerant of the same one-day
    slack: an ST timestamp is Jan 1 of the year after its nominal year, so
    Dec 31 of the nominal year has to land in the same place.
    """
    if var_type == "ST":
        return (timestamp + TIME_STAMP_TOLERANCE).year - 1
    return timestamp.year


def _expected_nominal_years(exp: dict, start_year: int) -> list[int]:
    """The nominal simulation years a file for this experiment should carry.

    Every experiment but 'historical' pins its start year in
    experiments_ismip7.csv, so the whole axis follows from the table alone.
    'historical' may start anywhere in [start_year_min, start_year_max] (which
    is what a duration of -1 records), so it needs one number from the file --
    see :func:`_axis_start_year`.
    """
    if exp["duration"] != -1:
        start_year = exp["start_year_min"]
    return list(range(start_year, exp["end_year"] + 1))


def _format_year_runs(years: list[int]) -> str:
    """Render a sorted year list compactly, collapsing consecutive runs.

    A gap of 99 years is one fact about a file, not 99 of them, so it is
    reported as '2101-2199' rather than as every year in between.
    """
    runs: list[list[int]] = []
    for year in years:
        if runs and year == runs[-1][1] + 1:
            runs[-1][1] = year
        else:
            runs.append([year, year])
    text = ", ".join(str(lo) if lo == hi else f"{lo}-{hi}" for lo, hi in runs[:MAX_REPORTED_TIME_MISMATCHES])
    if len(runs) > MAX_REPORTED_TIME_MISMATCHES:
        text += f", and {len(runs) - MAX_REPORTED_TIME_MISMATCHES} further run(s)"
    return text


def _check_filename_year_range(exp: dict, filename_years) -> list[str]:
    """Messages for a file name whose year range disagrees with the experiment."""
    if filename_years is None:
        return []

    start_year, end_year = filename_years
    messages = []
    if not (exp["start_year_min"] <= start_year <= exp["start_year_max"]):
        if exp["start_year_min"] == exp["start_year_max"]:
            expected = f"must be {exp['start_year_min']}"
        else:
            expected = f"must be between {exp['start_year_min']} and {exp['start_year_max']}"
        messages.append(
            f"the file name starts at year {start_year}, but experiment"
            f" '{exp['experiment']}' {expected}."
        )
    if end_year != exp["end_year"]:
        messages.append(
            f"the file name ends at year {end_year}, but experiment"
            f" '{exp['experiment']}' must end at {exp['end_year']}."
        )
    return messages


def _compare_time_axis(actual: list, expected_years: list[int], var_type: str) -> list[str]:
    """Compare a file's time axis with the one its experiment calls for.

    Three things can be wrong independently, and saying which one it is matters
    more than counting them: the file may hold the wrong set of nominal years
    (missing some, or carrying extra ones), or hold the right years with the
    wrong timestamps on them -- an FL file written with the ST convention, say.
    """
    expected_at = {year: _nominal_to_timestamp(year, var_type) for year in expected_years}

    # An axis that is entirely the other convention is one mistake, not several
    # hundred, and every other message below would be a confusing way to say so.
    other_type = "FL" if var_type == "ST" else "ST"
    other_at = [_nominal_to_timestamp(year, other_type) for year in expected_years]
    if len(actual) == len(other_at) and all(
        abs(a - e) <= TIME_STAMP_TOLERANCE for a, e in zip(actual, other_at)
    ):
        return [
            f"the time axis follows the {other_type} convention"
            f" ({_describe_convention(other_type)}), but this variable is"
            f" {var_type}, whose timestamps are"
            f" {_describe_convention(var_type)}."
        ]

    actual_at = _nominal_year_index(actual, var_type)

    messages = []
    if len(actual) != len(expected_years):
        messages.append(
            f"the time axis has {len(actual)} time step(s);"
            f" {len(expected_years)} expected for nominal years"
            f" {expected_years[0]}-{expected_years[-1]}."
        )

    missing = sorted(set(expected_at) - set(actual_at))
    if missing:
        messages.append(
            f"nominal year(s) missing from the time axis:"
            f" {_format_year_runs(missing)} ({len(missing)} year(s))."
        )

    unexpected = sorted(set(actual_at) - set(expected_at))
    if unexpected:
        messages.append(
            f"nominal year(s) on the time axis that the experiment does not"
            f" call for: {_format_year_runs(unexpected)}"
            f" ({len(unexpected)} year(s))."
        )

    mismatch = _timestamp_mismatch_message(
        actual_at, sorted(set(expected_at) & set(actual_at)), var_type
    )
    if mismatch:
        messages.append(mismatch)

    return messages


def _nominal_year_index(actual: list, var_type: str) -> dict:
    """Index a file's timestamps by the nominal year each one encodes."""
    index: dict[int, object] = {}
    for timestamp in actual:
        index.setdefault(_timestamp_to_nominal_year(timestamp, var_type), timestamp)
    return index


def _timestamp_mismatch_message(actual_at: dict, years: list[int], var_type: str):
    """Report years whose timestamp does not sit where the convention puts it.

    The years themselves are right here -- it is the date written against them
    that is wrong, which is a different mistake from a missing or extra year and
    reads badly if the two are merged.
    """
    misencoded = [
        year
        for year in years
        if abs(actual_at[year] - _nominal_to_timestamp(year, var_type))
        > TIME_STAMP_TOLERANCE
    ]
    if not misencoded:
        return None

    shown = ", ".join(
        f"{year} is {actual_at[year].strftime('%Y-%m-%d')}"
        f" (expected {_nominal_to_timestamp(year, var_type).strftime('%Y-%m-%d')})"
        for year in misencoded[:MAX_REPORTED_TIME_MISMATCHES]
    )
    if len(misencoded) > MAX_REPORTED_TIME_MISMATCHES:
        shown += f", and {len(misencoded) - MAX_REPORTED_TIME_MISMATCHES} more"
    return (
        f"{len(misencoded)} timestamp(s) do not match the {var_type}"
        f" convention ({_describe_convention(var_type)}): {shown}."
    )


def _describe_convention(var_type: str) -> str:
    if var_type == "ST":
        return "Jan 1 of the year after the nominal year"
    return "Jul 1 of the nominal year"


# The nominal years an x,y,z,t variable (litemp) must carry a snapshot for,
# whenever they fall inside the run.  Taken from the litemp Comment column of
# ISMIP7_variable_request.csv: "(1900 if in historical), initial state, 2014,
# 2100, 2200, and 2300".  The 2014 there is the last year of the historical
# experiment, so it is covered by requiring the run's final year rather than by
# naming a literal.
CENTURY_SNAPSHOT_YEARS = frozenset({1900, 2100, 2200, 2300})


def _required_snapshot_years(exp: dict, run_years: list[int]) -> set[int]:
    """The snapshot nominal years an x,y,z,t file must carry.

    The final year of the run is always reported, as are the century marks
    inside it.  The *first* year is only required where the protocol leaves it
    open -- that is, for 'historical', whose start year is the modeller's choice
    (duration -1) and so is not recorded anywhere else.  A projection's initial
    state is the historical run's final state, already reported as historical's
    last-year snapshot, so requiring it again in every projection would ask for
    the same field twice.
    """
    required = {run_years[-1]}
    required |= {y for y in CENTURY_SNAPSHOT_YEARS if run_years[0] <= y <= run_years[-1]}
    if exp["duration"] == -1:
        required.add(run_years[0])
    return required


def _run_compliance_checker(
    source_path: str,
    version: str,
    ismip_meta,
    ismip_var,
    mandatory_variables,
    all_request_variables,
    all_mandatory_variables,
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
                reporter=Reporter(f),
                source_path=source_path,
                experiment_groups=experiment_groups,
                mandatory_variables=mandatory_variables,
                all_request_variables=all_request_variables,
                all_mandatory_variables=all_mandatory_variables,
                experiments=experiments,
                ismip_var=ismip_var,
                ismip_meta=ismip_meta,
            )

        _insert_synthesis(source_path=source_path, summary=summary)
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
        "total_warnings": 0,
        "total_naming_warnings": 0,
        "total_num_warnings": 0,
        "total_spatial_warnings": 0,
        "total_time_warnings": 0,
        "total_attr_warnings": 0,
        "total_file_warnings": 0,
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
    reporter: Reporter,
    source_path: str,
    experiment_groups: dict,
    mandatory_variables,
    all_request_variables,
    all_mandatory_variables,
    experiments,
    ismip_var,
    ismip_meta,
):
    report_naming_issues = []

    # A declaration is about the submission as a whole, so it is read and
    # reported once, before the first experiment.
    declared = _read_not_modelled(source_path)
    not_modelled = (
        set()
        if declared is None
        else _report_not_modelled(
            reporter.category("file", bullet=""),
            declared,
            all_mandatory_variables,
            all_request_variables,
        )
    )

    file_counter = 0
    exp_counter = 0
    for experiment_name, exp_files in experiment_groups.items():
        exp_counter += 1

        exp_reporter = reporter.child()
        file_counter += _process_single_experiment(
            reporter=exp_reporter,
            source_path=source_path,
            experiment_name=experiment_name,
            exp_files=exp_files,
            mandatory_variables=mandatory_variables,
            not_modelled=not_modelled,
            all_request_variables=all_request_variables,
            experiments=experiments,
            ismip_var=ismip_var,
            ismip_meta=ismip_meta,
            report_naming_issues=report_naming_issues,
        )

        _print_experiment_summary(
            experiment_name=experiment_name,
            exp_errors=exp_reporter.total_errors,
            exp_warnings=exp_reporter.total_warnings,
        )

    _print_total_summary(
        source_path=source_path,
        total_errors=reporter.total_errors,
        total_warnings=reporter.total_warnings,
    )

    return {
        "exp_counter": exp_counter,
        "file_counter": file_counter,
        "total_errors": reporter.total_errors,
        "total_naming_errors": reporter.error_count("naming"),
        "total_num_errors": reporter.error_count("num"),
        "total_spatial_errors": reporter.error_count("spatial"),
        "total_time_errors": reporter.error_count("time"),
        "total_attr_errors": reporter.error_count("attr"),
        "total_file_errors": reporter.error_count("file"),
        "total_warnings": reporter.total_warnings,
        "total_naming_warnings": reporter.warning_count("naming"),
        "total_num_warnings": reporter.warning_count("num"),
        "total_spatial_warnings": reporter.warning_count("spatial"),
        "total_time_warnings": reporter.warning_count("time"),
        "total_attr_warnings": reporter.warning_count("attr"),
        "total_file_warnings": reporter.warning_count("file"),
        "report_naming_issues": report_naming_issues,
    }


NOT_MODELLED_FILENAME = "not_modelled.txt"


def _read_not_modelled(source_path: str) -> list[str] | None:
    """The variable names declared in not_modelled.txt, or None if there is none.

    Groups already submit a README explaining what they have submitted and why
    some variables are absent, so the checker has no need to ask for that list
    again -- and an explanatory list does not belong on a command line, where it
    would be long and would have to be retyped for every run.  What is worth
    offering is a way to make the 'not submitted' warning go quiet once.

    One name per line; blank lines are ignored and '#' starts a comment, so a
    group can say alongside each name why the variable is absent.  An absent
    file changes nothing.
    """
    path = os.path.join(source_path, NOT_MODELLED_FILENAME)
    if not os.path.isfile(path):
        return None

    declared = []
    with open(path, "r") as f:
        for line in f:
            name = line.split("#", 1)[0].strip()
            if name:
                declared.append(name)
    return declared


def _report_not_modelled(
    reporter: Reporter,
    declared: list[str],
    all_mandatory_variables,
    all_request_variables,
) -> set[str]:
    """Echo the declaration, fault what it should not contain, return what it silences.

    Two rules keep the file from becoming a way to hide problems.  A mandatory
    variable named in it is still a missing-mandatory error, and the claim
    itself is reported as a further error rather than honoured: the list is a
    statement about optional variables, and a group cannot opt out of the data
    request with it.  A name that is not in the data request at all is an error
    too -- it is either a typo or a misunderstanding, and both are better said
    plainly than left to be inferred from a warning that did not go away, which
    would protect nothing while looking like protection.

    What was declared is echoed either way, so the archived record of a run
    shows what was claimed rather than merely that a warning did not appear.
    """
    reporter.write(
        f"Declared not modelled ({NOT_MODELLED_FILENAME}): {declared}\n"
    )

    suppressed = set()
    for name in declared:
        if name in all_mandatory_variables:
            reporter.error(
                f"{NOT_MODELLED_FILENAME} lists '{name}', which the data request"
                f" makes mandatory. A submission cannot opt out of a mandatory"
                f" variable, so the declaration is not honoured and the missing"
                f" files are still reported."
            )
        elif name not in all_request_variables:
            message = (
                f"{NOT_MODELLED_FILENAME} lists '{name}', which is not a"
                f" variable of the data request {VARIABLE_REQUEST_CSV}."
            )
            # Sorted, so that two equally close names do not resolve by set
            # iteration order and give one log on one run and another on the next.
            near_misses = difflib.get_close_matches(
                name, sorted(all_request_variables), n=1
            )
            if near_misses:
                message += f" The closest requested name is '{near_misses[0]}'."
            reporter.error(message)
        else:
            suppressed.add(name)

    reporter.write(" \n")
    return suppressed


def _report_variables_not_submitted(
    reporter: Reporter, experiment_name: str, not_submitted: list[str]
) -> None:
    """Name the non-mandatory variables an experiment carries no files for.

    Nothing reported this before, so a group that meant to submit litemp and
    lost it in a script got no signal whatsoever.  Everything about how it is
    said is chosen so that it cannot be read as an accusation: not every model
    supports every non-mandatory variable -- GIA is the obvious case -- and a
    deliberate omission is the common case, not the exception.

    Hence one line per experiment naming all of them, rather than one warning
    per variable, which would make a model with a narrow scope look far worse
    than one with a single dropped file; hence the wording, which says 'not
    submitted' rather than 'missing'; and hence its absence from the trailing
    naming-issues report, which is the part of the log that reads as a list of
    faults.

    There is no suppression when an experiment submitted nothing optional at
    all.  For a full submission that is precisely the case worth naming, and
    treating it as self-evidently deliberate would silence the warning for the
    group most likely to have lost something.
    """
    if not not_submitted:
        return
    reporter.warning(
        "experiment "
        + experiment_name
        + " carries no files for the non-mandatory variable(s): "
        + str(not_submitted)
        + ". This is expected if your model does not represent them; it is"
        + " listed only so that a variable lost from a submission does not pass"
        + " unnoticed."
    )


def _process_single_experiment(
    reporter: Reporter,
    source_path: str,
    experiment_name: str,
    exp_files: list,
    mandatory_variables,
    not_modelled,
    all_request_variables,
    experiments,
    ismip_var,
    ismip_meta,
    report_naming_issues,
) -> int:
    """Check one experiment's files; return how many of them there were."""
    # Experiment-level findings are about the submission rather than about any
    # one file, so they are written flush left rather than as list items under
    # a file's heading.
    presence_reporter = reporter.category("file", bullet="")
    naming_reporter = reporter.category("naming", bullet="")

    submitted = {i.split("_")[ISMIP7_FILENAME_VAR_IDX] for i in exp_files}
    temp_mandatory_var = [v for v in mandatory_variables if v not in submitted]
    # Scoped to the selected --variable-list, exactly as the mandatory check is:
    # a run over ismip7_scalars says nothing about the x,y,t variables it was
    # never asked to look at.
    # A declaration in not_modelled.txt silences the warning below, and nothing
    # else: it cannot reach the mandatory-variable check above it.
    not_submitted = [
        v
        for v in ismip_var
        if v not in mandatory_variables
        and v not in submitted
        and v not in not_modelled
    ]

    file_counter = 0
    if experiment_name in [dic["experiment"] for dic in experiments]:
        reporter.write("\n ")
        reporter.write("**********************************************************\n")
        reporter.write(" ** Experiment: " + experiment_name + " \n ")
        reporter.write("**********************************************************\n")
        reporter.write("\n ")
        if not temp_mandatory_var:
            reporter.write(
                "Mandatory variables Test: "
                + experiment_name
                + " : all mandatory variables exist. \n"
            )
        else:
            presence_reporter.error(
                "In experiment "
                + experiment_name
                + ", these mandatory variable(s) is (are) missing: "
                + str(temp_mandatory_var),
                count=len(temp_mandatory_var),
            )
        _report_variables_not_submitted(
            presence_reporter, experiment_name, not_submitted
        )

        for file in tqdm(exp_files):
            file_counter += 1
            _process_single_file(
                reporter=reporter,
                source_path=source_path,
                file=file,
                experiment_name=experiment_name,
                ismip_var=ismip_var,
                ismip_meta=ismip_meta,
                all_request_variables=all_request_variables,
                experiments=experiments,
                report_naming_issues=report_naming_issues,
            )

    else:
        reporter.write("\n ")
        reporter.write("**********************************************************\n")
        reporter.write(" **  Experiment: " + experiment_name + " \n ")
        reporter.write("**********************************************************\n")
        reporter.write("\n ")
        naming_reporter.error(
            "The compliance check is ignored for experiment "
            + experiment_name
            + " as it is not in "
            + str([exp["experiment"] for exp in experiments])
            + ". "
        )
        report_naming_issues.append(
            "Compliance check ignored : experiment "
            + experiment_name
            + " not in the experiments list."
        )

    return file_counter


def _process_single_file(
    reporter: Reporter,
    source_path: str,
    file: str,
    experiment_name: str,
    ismip_var,
    ismip_meta,
    all_request_variables,
    experiments,
    report_naming_issues,
) -> None:
    # A sub-total of this file's findings, for the footer below; it still rolls
    # up into the experiment and the run.
    file_reporter = reporter.child()
    naming_reporter = file_reporter.category("naming")

    file_name = os.path.basename(file)
    file_name_split = file_name.split("_")

    considered_variable = file_name_split[ISMIP7_FILENAME_VAR_IDX]
    region = file_name_split[ISMIP7_FILENAME_REGION_IDX]

    try:
        ds = xr.open_dataset(os.path.join(source_path, file),
                             decode_times=False)
    except (ValueError, TypeError) as e:
        naming_reporter.error("Cannot open " + file_name + ": " + str(e))
        return
    file_variables = list(ds.data_vars)

    if len(file_name_split) != ISMIP7_FILENAME_PARTS:
        naming_reporter.error(
            "the file name "
            + file_name
            + " does not follow the naming convention (expected "
            + str(ISMIP7_FILENAME_PARTS)
            + " underscore-separated fields)."
        )
        report_naming_issues.append(
            "Compliance check ignored: file "
            + file_name
            + " does not follow the naming convention."
        )
        return

    experiment_varname = file_name_split[ISMIP7_FILENAME_EXPERIMENT_IDX]
    if experiment_varname != experiment_name:
        naming_reporter.error(
            "in the file name "
            + file_name
            + ", the experiment name ("
            + experiment_varname
            + ") does not match the expected experiment: "
            + experiment_name
            + "."
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
        return

    if considered_variable not in all_request_variables:
        file_reporter.write(" \n")
        file_reporter.write(
            "Experiment: " + experiment_name + " - File: " + file_name + "\n"
        )
        file_reporter.write(" \n")
        file_reporter.write("NAMING Tests \n")
        message = (
            f"'{considered_variable}' (field {ISMIP7_FILENAME_VAR_IDX} of the"
            f" file name) is not a variable in the data request"
            f" {VARIABLE_REQUEST_CSV}."
        )
        near_misses = difflib.get_close_matches(
            considered_variable, sorted(all_request_variables), n=1
        )
        if near_misses:
            message += f" The closest requested name is '{near_misses[0]}'."
        naming_reporter.error(message)
        report_naming_issues.append(f"Compliance check ignored: {message}")
    elif considered_variable in ismip_var:
        _run_variable_checks(
            reporter=file_reporter,
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

    var_errors = file_reporter.total_errors
    var_warnings = file_reporter.total_warnings

    file_reporter.write("\n")
    file_reporter.write("----------------------------------------------------------\n")
    file_reporter.write(
        experiment_name + " - " + considered_variable + " - File:" + file_name + "\n"
    )
    if var_errors > 0:
        file_reporter.write(
            str(var_errors) + " error(s). Please review before sharing.\n"
        )
    else:
        # Warnings never change the verdict: a file with warnings and no errors
        # is compliant, and is told so.
        file_reporter.write("No errors. Good job !\n")
    if var_warnings > 0:
        file_reporter.write(str(var_warnings) + " warning(s). Please review.\n")
    else:
        file_reporter.write("No warnings.\n")
    file_reporter.write("----------------------------------------------------------\n")


class NamingResult(NamedTuple):
    """What the naming checks found, and what the later checks need from them.

    The file name is where the year range under test comes from, so parsing it
    is the naming check's job; comparing it to the time axis is the time
    check's, which decodes the file anyway.

    `can_continue` is what the other checks key off.  Most naming problems say
    nothing about whether a file can be checked -- a mistyped ESM name is worth
    reporting and worth nothing else -- so only the ones that genuinely leave
    the later checks with nothing to read clear it.
    """

    filename_years: tuple[int, int] | None
    can_continue: bool = True


def _check_naming(
    reporter: Reporter,
    file_name: str,
    region: str,
    dim: set,
    isscalar: bool,
    report_naming_issues: list,
) -> NamingResult:
    filename_years = None

    reporter.write("NAMING Tests \n")

    if not isscalar and not {"x", "y"}.issubset(dim):
        reporter.error(
            "Compliance check ignored: x or y in the mandatory dimensions (x,y,t) is missing."
        )
        reporter.write(
            "                                    Only " + str(list(dim)) + " has been detected.\n"
        )
        report_naming_issues.append(
            "Compliance check ignored: x or y in the mandatory dimensions (x,y,t) is missing in "
            + file_name
        )
        # Without x and y there is no grid to check and no spatial variable to
        # read: this is one of the few naming problems that really does stop
        # everything else.
        return NamingResult(filename_years, can_continue=False)

    if region not in ["AIS", "GrIS"]:
        reporter.error(
            "Region "
            + region
            + " not recognized. It should be AIS or GrIS. The checks that depend"
            + " on the region (value range, grid extent and resolution, crs) are"
            + " skipped for this file; the rest still run."
        )
        report_naming_issues.append(
            "Region-dependent checks skipped: region (AIS/GrIS) not identified in the file "
            + file_name
            + " due to wrong naming."
        )

    parts = file_name.split("_")
    if len(parts) == ISMIP7_FILENAME_PARTS:
        ism_member = parts[ISMIP7_FILENAME_ISM_MEMBER_IDX]
        if not re.fullmatch(r"m\d{3}", ism_member):
            reporter.error(
                f"ISM member id '{ism_member}' (field {ISMIP7_FILENAME_ISM_MEMBER_IDX}) does not match expected format mNNN (e.g. m001)."
            )

        esm_name = parts[ISMIP7_FILENAME_ESM_IDX]
        if esm_name not in VALID_ESM_NAMES:
            reporter.error(
                f"ESM name '{esm_name}' (field {ISMIP7_FILENAME_ESM_IDX}) is not a recognised CMIP6/CMIP7 model name."
            )

        forcing_member = parts[ISMIP7_FILENAME_FORCING_MEMBER_IDX]
        if not re.fullmatch(r"f\d{3}", forcing_member):
            reporter.error(
                f"forcing member id '{forcing_member}' (field {ISMIP7_FILENAME_FORCING_MEMBER_IDX}) does not match expected format fNNN (e.g. f001)."
            )

        set_counter = parts[ISMIP7_FILENAME_SET_COUNTER_IDX]
        if not re.fullmatch(r"[CEP]\d{3}", set_counter):
            reporter.error(
                f"set counter '{set_counter}' (field {ISMIP7_FILENAME_SET_COUNTER_IDX}) does not match expected format [C|E|P]NNN (e.g. C001, E041, P132)."
            )

        is_static = not ({"time", "t"} & dim)
        year_range_field = parts[ISMIP7_FILENAME_YEAR_RANGE_IDX].removesuffix(".nc")
        if is_static:
            reporter.note("Filename year range: N/A (static spatial variable)")
        elif not (year_range_match := re.fullmatch(r"(\d{4})-(\d{4})", year_range_field)):
            reporter.error(
                f"year range '{year_range_field}' (field {ISMIP7_FILENAME_YEAR_RANGE_IDX}) does not match expected format YYYY-YYYY (e.g. 2015-2300)."
            )
        else:
            fn_start_year = int(year_range_match.group(1))
            fn_end_year = int(year_range_match.group(2))
            if fn_start_year > fn_end_year:
                reporter.error(
                    f"year range '{year_range_field}': start year {fn_start_year} is after end year {fn_end_year}."
                )
            else:
                # What the range means -- whether the experiment allows it, and
                # whether the time axis delivers it -- is for _check_time, which
                # decodes the file anyway.
                filename_years = (fn_start_year, fn_end_year)
                reporter.ok(
                    f"Filename year range {fn_start_year}-{fn_end_year} is well formed: OK"
                )

    return NamingResult(filename_years)


# The data request writes a variable's dimensions innermost-first and calls the
# time dimension 't' ('x,y,t'); the files write them outermost-first in the
# conventional CF order and call it 'time'.  This is the translation between
# the two, and the four forms here are every 'Dim' the request uses.
REQUESTED_DIMENSIONS: dict[str, tuple[str, ...]] = {
    "t": ("time",),
    "x,y": ("y", "x"),
    "x,y,t": ("time", "y", "x"),
    "x,y,z,t": ("time", "z", "y", "x"),
}


def _check_variable_dimensions(
    reporter: Reporter,
    ds,
    considered_variable: str,
    requested_dim: str,
) -> None:
    """Check a variable's dimensions against the 'Dim' column of the request."""
    expected = REQUESTED_DIMENSIONS.get(requested_dim)
    if expected is None:
        reporter.note(
            f"Variable '{considered_variable}' dimensions: not checked (the"
            f" data request gives Dim '{requested_dim}', which this checker does"
            f" not know)."
        )
        return

    # 't' is an accepted spelling of the time dimension throughout the checker.
    actual = tuple(
        "time" if name == "t" else name for name in ds[considered_variable].dims
    )

    if set(actual) != set(expected):
        reporter.error(
            f"variable '{considered_variable}' has dimensions"
            f" {actual}; the data request asks for {requested_dim}, that is"
            f" {expected}."
        )
        return

    if actual != expected:
        reporter.error(
            f"variable '{considered_variable}' has dimensions"
            f" {actual}; the data request asks for {requested_dim} in the"
            f" conventional order {expected}."
        )
        return

    reporter.ok(
        f"Variable '{considered_variable}' dimensions ({', '.join(actual)})"
        f" match the requested {requested_dim}: OK"
    )


def _allowed_file_variables(ds, considered_variable: str) -> set[str]:
    """The variables a file may hold besides the one it is named for.

    A file carries one variable of the data request, but CF lets that variable
    bring companions: the bounds of a coordinate (which is how 'time_bounds'
    reaches every FL file), the container variable a 'grid_mapping' points at,
    the auxiliary coordinates a variable names, the cell measures it is
    normalised by, and the ancillary variables that qualify it.  Every one of
    those is a variable the file has to carry for the requested variable to
    mean what it says, so none of them is an extra; anything else is something
    the data request did not ask for.
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
    allowed.update(str(attributes.get("ancillary_variables", "")).split())
    # cell_measures names each variable after the measure it supplies
    # ('area: areacello volume: volcello'), so the keywords are dropped.
    allowed.update(
        token
        for token in str(attributes.get("cell_measures", "")).split()
        if not token.endswith(":")
    )

    return allowed


def _check_file_variables(
    reporter: Reporter,
    ds,
    file_name: str,
    considered_variable: str,
    file_variables,
    requested_dim: str,
    report_naming_issues: list,
) -> bool:
    """Check the variables a file contains against the one its name promises.

    The file name states which variable of the data request a file carries, and
    every other check reads that variable, so a file that does not contain it
    has nothing to check: the return value is False, and the caller skips the
    remaining checks for the file rather than reporting a clean bill of health
    on a variable that was never looked at.
    """
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
        reporter.error(message)
        report_naming_issues.append(
            f"Compliance check ignored: in the file {file_name}, {message}"
        )
        return False

    reporter.ok(
        f"Variable '{considered_variable}' from the file name is present in"
        f" the file: OK"
    )

    allowed = _allowed_file_variables(ds, considered_variable)
    unexpected = sorted(name for name in file_variables if name not in allowed)
    for name in unexpected:
        # A warning: the requested variable is present and fully checkable, and
        # a reader taking it out of the file is unaffected by what sits beside
        # it.  What the extra says is that the file was probably not written for
        # this submission, which is worth a look and is not a fault.
        reporter.warning(
            f"unexpected variable '{name}' in the file. A file is expected to"
            f" hold one variable of the data request -- here"
            f" '{considered_variable}' -- along with its coordinates and the"
            f" companion variables CF lets it name (bounds, grid mapping, cell"
            f" measures, ancillary variables). '{considered_variable}' is"
            f" checked as normal."
        )
    if not unexpected:
        reporter.ok("No unexpected variables in the file: OK")

    _check_variable_dimensions(reporter, ds, considered_variable, requested_dim)

    return True


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
    reporter: Reporter,
    ds,
    ivar: str,
    ismip_meta: list,
    var_index: int,
    region: str,
    isscalar: bool,
) -> None:
    reporter.write("NUMERICAL Tests \n")

    var_units = ds[ivar].attrs.get("units")
    expected_units = ismip_meta[var_index]["units"]
    if var_units is None:
        reporter.error(
            f"The variable '{ivar}' has no 'units' attribute. The data"
            f" request asks for '{expected_units}'."
        )
    elif var_units == expected_units:
        reporter.ok("The unit is correct: " + var_units)
    elif _units_match(var_units, expected_units):
        reporter.ok(
            "The unit is correct: "
            + var_units
            + " (equivalent to the requested "
            + expected_units
            + ")"
        )
    else:
        reporter.error(
            "The unit of the variable is "
            + var_units
            + " and should be "
            + expected_units
            + " "
        )

    if not isscalar and region not in ("AIS", "GrIS"):
        reporter.note(
            "Value range: not checked (the allowed range depends on the"
            " region, which the file name does not identify)."
        )
    elif not isscalar:
        # The severity of an out-of-range value is per variable, from the
        # range_severity column of the data request; see _range_severity.
        report_range = (
            reporter.warning
            if ismip_meta[var_index].get("range_severity") == "warning"
            else reporter.error
        )
        if False in ds[ivar].isnull():
            if (
                ds[ivar].min(skipna=True).item()
                >= ismip_meta[var_index]["min_value_" + region.lower()]
            ):
                reporter.ok("The minimum value successfully verified.")
            else:
                report_range(
                    "The minimum value ("
                    + str(ds[ivar].min(skipna=True).values.item(0))
                    + ") is out of range. Min value accepted: "
                    + str(ismip_meta[var_index]["min_value_" + region.lower()])
                )

            if (
                ds[ivar].max(skipna=True).item()
                <= ismip_meta[var_index]["max_value_" + region.lower()]
            ):
                reporter.ok("The maximum value successfully verified.")
            else:
                report_range(
                    "The maximum value ("
                    + str(ds[ivar].max(skipna=True).values.item(0))
                    + ") is out of range. Max value accepted: "
                    + str(ismip_meta[var_index]["max_value_" + region.lower()])
                )
        else:
            reporter.error("The array only contains missing values.")


def _check_spatial(
    reporter: Reporter,
    ds,
    grid_extent: list,
    possible_resolution: list,
) -> None:
    reporter.write("SPATIAL Tests \n")
    coords = ds.coords.to_dataset()
    Xbottomleft = int(min(coords["x"]).values.item())
    Ybottomleft = int(min(coords["y"]).values.item())
    Xtopright = int(max(coords["x"]).values.item())
    Ytopright = int(max(coords["y"]).values.item())

    if Xbottomleft == grid_extent[0] and Ybottomleft == grid_extent[1]:
        reporter.ok("Grid: Lowest left corner is well defined.")
    else:
        reporter.error(
            "Lowest left corner of the grid ["
            + str(Xbottomleft) + "," + str(Ybottomleft)
            + "] is not correctly defined. ["
            + str(grid_extent[0]) + "," + str(grid_extent[1])
            + "] Expected"
        )

    if Xtopright == grid_extent[2] and Ytopright == grid_extent[3]:
        reporter.ok("Grid: Upper right corner is well defined.")
    else:
        reporter.error(
            "Upper right corner of the grid ["
            + str(Xtopright) + "," + str(Ytopright)
            + "] is not correctly defined. ["
            + str(grid_extent[2]) + "," + str(grid_extent[3])
            + "] Expected"
        )

    Xresolution = round((coords["x"][1].values - coords["x"][0].values) / 1000, 0)
    Yresolution = round((coords["y"][1].values - coords["y"][0].values) / 1000, 0)
    if Xresolution in set(possible_resolution) and Yresolution in set(possible_resolution):
        reporter.ok(
            "The grid resolution ("
            + str(int(Xresolution))
            + " km) was successfully verified."
        )
    else:
        reporter.error(
            "resolution x="
            + str(Xresolution)
            + " km, y="
            + str(Yresolution)
            + " km is not an authorized grid resolution. Allowed: "
            + str(possible_resolution)
            + " km"
        )


def _check_time(
    reporter: Reporter,
    ds,
    dim: set,
    experiments: list,
    experiment_name: str,
    var_type: str = "",
    requested_dim: str = "",
    filename_years=None,
) -> None:
    """Check a file's time axis against the one its experiment calls for.

    The axis is checked by reconstructing the axis the file should have had and
    comparing, rather than by measuring its endpoints and its first interval.
    Endpoint reasoning cannot see a decimated or gappy axis: a ctrl file holding
    2015, 2016, 2299, 2300 spans the right years with a 365-day first interval
    and is 282 time steps short of what was asked for.
    """
    reporter.write("TIME Tests \n")
    if not ({"t"}.issubset(dim) or {"time"}.issubset(dim)):
        if {"x", "y"}.issubset(dim):
            # Static spatial variable (x,y) — no time axis is expected.
            reporter.note("Time axis: N/A (static spatial variable)")
            return
        reporter.error(
            "The time dimension is missing. Time Tests have been ignored."
        )
        return

    time_dim = "time" if "time" in ds.dims else "t"
    unlimited_dims = ds.encoding.get("unlimited_dims", set())
    if time_dim in unlimited_dims:
        reporter.ok("Time is a record (unlimited) dimension: OK")
    else:
        reporter.error(
            f"dimension '{time_dim}' is not a record (unlimited) dimension."
        )

    try:
        ds = xr.decode_cf(ds, decode_times=xr.coders.CFDatetimeCoder(use_cftime=True))
    except Exception:
        reporter.error(
            "The time coordinate could not be decoded.  Time checks cannot proceed."
        )
        # we can't proceed because the next steps will crash
        return

    if not _strictly_increasing(ds.coords["time"]):
        reporter.error(
            "the time series is not monotonically increasing. Time segments may have been concatenated in the wrong order."
        )
        return

    index_exp = [dic["experiment"] for dic in experiments].index(experiment_name)
    exp = experiments[index_exp]
    actual = list(ds["time"].values)

    for message in _check_filename_year_range(exp, filename_years):
        reporter.error(message)

    # The nominal years the run as a whole covers.  The annual variables carry
    # one time step for each of them; the snapshot variables carry a few.
    run_years = _expected_nominal_years(
        exp, _axis_start_year(exp, filename_years, actual, var_type)
    )
    if not run_years:
        reporter.error(
            f"the time axis starts in nominal year"
            f" {_timestamp_to_nominal_year(actual[0], var_type)}, after experiment"
            f" '{experiment_name}' ends in {exp['end_year']}. The expected time"
            f" axis cannot be determined."
        )
        return

    if requested_dim == "x,y,z,t":
        _check_snapshot_time_axis(reporter, actual, exp, var_type, run_years)
        return

    messages = _compare_time_axis(actual, run_years, var_type)
    for message in messages:
        reporter.error(message)

    if not messages:
        reporter.ok(
            f"Time axis: {len(actual)} annual {var_type} time step(s) covering"
            f" nominal years {run_years[0]}-{run_years[-1]}, as"
            f" experiment '{experiment_name}' requires: OK"
        )


def _axis_start_year(exp: dict, filename_years, actual: list, var_type: str) -> int:
    """The nominal year the expected time axis should begin at.

    Only 'historical' has a say in the matter -- every other experiment pins its
    start year in experiments_ismip7.csv -- and for it the file name is what
    decides: it is the file's own declared claim about its contents, and any
    start year in [start_year_min, start_year_max] is permitted, so there is
    nothing else to measure the file against.

    Falls back to the axis when the file name cannot supply a usable year, so
    that the cadence and the end year are still checked rather than the file
    being measured against a range nothing supports.
    """
    if filename_years is not None:
        start_year = filename_years[0]
        if exp["start_year_min"] <= start_year <= exp["start_year_max"]:
            return start_year
    return _timestamp_to_nominal_year(actual[0], var_type)


def _check_snapshot_time_axis(
    reporter: Reporter, actual: list, exp: dict, var_type: str, run_years: list[int]
) -> None:
    """Check the sparse snapshot axis of an x,y,z,t variable (e.g. litemp).

    Unlike the annual variables, these carry a handful of snapshots rather than
    every year of the run, so the check is against a required *set* of nominal
    years rather than a contiguous range.  It reports snapshots that should be
    there and are not, which is the gap issue #12 asks about: the previous
    version only validated the years a file happened to contain, and counted the
    file's own last time step as valid whatever it was, so a file holding a
    single snapshot at an arbitrary year passed.
    """
    required = _required_snapshot_years(exp, run_years)
    actual_at = _nominal_year_index(actual, var_type)

    errors_before = reporter.total_errors
    warnings_before = reporter.total_warnings

    missing = sorted(required - set(actual_at))
    if missing:
        reporter.error(
            f"required snapshot nominal year(s) missing:"
            f" {_format_year_runs(missing)}. Experiment '{exp['experiment']}'"
            f" covering {run_years[0]}-{run_years[-1]} requires snapshots at"
            f" {_format_year_runs(sorted(required))}."
        )

    # A warning, not an error: the data request specifies snapshots as a
    # *minimum* set, so over-delivering 3D temperature is not non-compliance.
    # This is also how a snapshot at 2000 is now reported -- the README asked
    # for one until recently and the data request never did, so a file carrying
    # it is named rather than either failed or silently accepted (issue #12).
    # The asymmetry with the annual axis, where an extra year is an error, is
    # deliberate: that axis is pinned end to end by experiments_ismip7.csv, so
    # an extra year there means the file does not match the experiment it names.
    unexpected = sorted(set(actual_at) - required)
    if unexpected:
        reporter.warning(
            f"snapshot nominal year(s) the experiment does not call"
            f" for: {_format_year_runs(unexpected)}. Required:"
            f" {_format_year_runs(sorted(required))}."
        )

    mismatch = _timestamp_mismatch_message(
        actual_at, sorted(set(actual_at) & required), var_type
    )
    if mismatch:
        reporter.error(mismatch)

    if (
        reporter.total_errors == errors_before
        and reporter.total_warnings == warnings_before
    ):
        reporter.ok(
            f"Snapshot time axis: nominal year(s)"
            f" {_format_year_runs(sorted(actual_at))} cover everything experiment"
            f" '{exp['experiment']}' requires: OK"
        )
    reporter.note(
        "Annual cadence checks: N/A (snapshot variable — the time axis holds"
        " sparse snapshots by design)."
    )


def _check_attributes(
    reporter: Reporter,
    ds,
    ivar: str,
    ismip_meta: list,
    var_index: int,
    isscalar: bool,
    var_type: str,
    region: str,
) -> None:
    reporter.write("ATTRIBUTE Tests \n")

    # Sub-test 1: global attributes
    required_global = ["group", "model", "contact_name", "contact_email"]
    errors_before = reporter.total_errors
    for attr in required_global:
        if attr not in ds.attrs:
            reporter.error(f"global attribute '{attr}' is missing.")
    expected_crs = "epsg:3413" if region == "GrIS" else "epsg:3031"
    actual_crs = ds.attrs.get("crs")
    if region not in ("AIS", "GrIS"):
        reporter.note(
            "Global attribute 'crs': not checked (the expected value depends"
            " on the region, which the file name does not identify)."
        )
    elif actual_crs is None:
        reporter.error("global attribute 'crs' is missing.")
    elif actual_crs.lower() != expected_crs:
        reporter.error(
            f"global attribute 'crs' is '{actual_crs}',"
            f" expected '{expected_crs}' (case-insensitive) for region {region}."
        )
    if reporter.total_errors == errors_before:
        reporter.ok("Global attributes: OK")

    # Sub-test 2: coordinate attributes
    errors_before = reporter.total_errors
    time_coord = None
    for name in ("time", "t"):
        if name in ds.coords:
            time_coord = name
            break
    is_static_spatial = time_coord is None and {"x", "y"}.issubset(set(ds.coords))
    if time_coord is None and not is_static_spatial:
        reporter.error("coordinate 'time' not found.")
    elif time_coord is None and is_static_spatial:
        reporter.note("Time coordinate: N/A (static spatial variable)")
    else:
        # xarray decodes 'units' and 'calendar' into .encoding; 'bounds' stays in .attrs
        time_var = ds[time_coord]
        combined = {**time_var.encoding, **time_var.attrs}
        time_attrs_required = ["units", "calendar"]
        if var_type != "ST":
            time_attrs_required.append("bounds")
        for attr in time_attrs_required:
            if attr not in combined:
                reporter.error(
                    f"coordinate '{time_coord}' missing attribute '{attr}'."
                )
        if "units" in combined and combined["units"] != "days since 1850-01-01":
            reporter.error(
                f"time 'units' is '{combined['units']}', expected 'days since 1850-01-01'."
            )
        if "calendar" in combined and combined["calendar"] != "standard":
            reporter.error(
                f"time 'calendar' is '{combined['calendar']}', expected 'standard'."
            )
    if not isscalar:
        spatial_coords = ("x", "y", "z") if "z" in ds.coords else ("x", "y")
        for coord in spatial_coords:
            if coord in ds.coords:
                if "units" not in ds[coord].attrs:
                    reporter.error(
                        f"coordinate '{coord}' missing attribute 'units'."
                    )
            else:
                reporter.error(f"coordinate '{coord}' not found.")
    if reporter.total_errors == errors_before:
        reporter.ok("Coordinate attributes: OK")

    # Sub-test 3: variable standard_name
    errors_before = reporter.total_errors
    expected_standard_name = ismip_meta[var_index].get("standard_name")
    if expected_standard_name is not None and ivar in ds:
        if "standard_name" not in ds[ivar].attrs:
            reporter.error(
                f"variable '{ivar}' missing 'standard_name' attribute."
            )
        elif ds[ivar].attrs["standard_name"] != expected_standard_name:
            reporter.error(
                f"variable '{ivar}' standard_name"
                f" '{ds[ivar].attrs['standard_name']}'"
                f" does not match expected '{expected_standard_name}'."
            )
    if reporter.total_errors == errors_before:
        reporter.ok("Variable attributes: OK")

    # Sub-test 4: _FillValue must equal the default netCDF4 fill value;
    #             if missing_value is also present it must equal _FillValue.
    errors_before = reporter.total_errors
    if ivar in ds:
        dtype = ds[ivar].dtype
        nc4_dtype_key = dtype.kind + str(dtype.itemsize)
        default_fill = netCDF4.default_fillvals.get(nc4_dtype_key)
        fill_value = ds[ivar].encoding.get("_FillValue")
        # xarray moves missing_value from attrs to encoding on read (CF fill-value handling)
        missing_value = ds[ivar].attrs.get("missing_value") or ds[ivar].encoding.get("missing_value")
        if fill_value is None:
            reporter.error(f"variable '{ivar}' missing '_FillValue'.")
        elif default_fill is not None and fill_value != default_fill:
            reporter.error(
                f"variable '{ivar}' _FillValue {fill_value}"
                f" does not match default netCDF4 fill value {default_fill} for dtype {dtype}."
            )
        if fill_value is not None and missing_value is not None and fill_value != missing_value:
            reporter.error(
                f"variable '{ivar}' _FillValue {fill_value}"
                f" and missing_value {missing_value} are not equal."
            )
    if reporter.total_errors == errors_before:
        reporter.ok("Fill value attributes: OK")

    # Sub-test 5: main variable and time must be single-precision float (f4).
    # The two are not the same finding.  A float64 data variable is twice the
    # size it should be, for the archive and for everyone who has to move it,
    # so it is an error.  A time axis is one number per record, so storing it
    # as float64 cannot meaningfully inflate a file and the size argument does
    # not reach it: it is a warning.
    errors_before = reporter.total_errors
    warnings_before = reporter.total_warnings
    if ivar in ds and ds[ivar].dtype != np.float32:
        reporter.error(
            f"variable '{ivar}' dtype is {ds[ivar].dtype},"
            f" expected float32 (f4)."
        )
    if time_coord is not None:
        # xarray decodes CF time to datetime objects in memory; check the on-disk dtype from encoding
        time_encoded_dtype = ds[time_coord].encoding.get("dtype", ds[time_coord].dtype)
        if time_encoded_dtype != np.float32:
            reporter.warning(
                f"coordinate '{time_coord}' on-disk dtype is {time_encoded_dtype},"
                f" expected float32 (f4)."
            )
    if (
        reporter.total_errors == errors_before
        and reporter.total_warnings == warnings_before
    ):
        reporter.ok("Dtype attributes: OK")

    # Sub-test 6: scale_factor and add_offset must not be present
    errors_before = reporter.total_errors
    if ivar in ds:
        # xarray moves these to .encoding on decode; check both locations
        combined = {**ds[ivar].attrs, **ds[ivar].encoding}
        for forbidden in ("scale_factor", "add_offset"):
            if forbidden in combined:
                reporter.error(
                    f"variable '{ivar}' must not have '{forbidden}'."
                )
    if reporter.total_errors == errors_before:
        reporter.ok("Packing attributes: OK")


def _run_variable_checks(
    reporter: Reporter,
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
) -> None:
    naming_reporter = reporter.category("naming")
    num_reporter = reporter.category("num")
    spatial_reporter = reporter.category("spatial")
    time_reporter = reporter.category("time")
    attr_reporter = reporter.category("attr", qualifier="attributes")

    reporter.write(" \n")
    reporter.write("Experiment: " + experiment_name + " - File: " + file_name + "\n")
    reporter.write(" \n")

    header_ds = ds.to_dict(data=False)
    dim = set(list(header_ds["coords"].keys()))

    index = ismip_var.index(considered_variable)
    isscalar = ismip_meta[index]["dim"] == "t"
    var_type = ismip_meta[index].get("type", "")

    naming = _check_naming(
        naming_reporter, file_name, region, dim, isscalar, report_naming_issues
    )
    if not naming.can_continue:
        return

    has_variable = _check_file_variables(
        naming_reporter, ds, file_name, considered_variable, file_variables,
        ismip_meta[index]["dim"], report_naming_issues,
    )
    if not has_variable:
        return

    grid_extent = AIS_GRID_EXTENT if region == "AIS" else GrIS_GRID_EXTENT
    possible_resolution = AIS_POSSIBLE_RESOLUTION if region == "AIS" else GrIS_POSSIBLE_RESOLUTION

    # The checks read the variable the file name promises, and the row of the
    # data request that goes with it.  Reading whatever variable the file
    # happens to contain instead would check a file against the wrong criteria,
    # or -- when nothing in it is a requested name -- against none at all.
    ivar = considered_variable
    var_index = index
    reporter.write("** Tested Variable: " + ivar + "\n")
    reporter.write(" \n")

    _check_numerical(num_reporter, ds, ivar, ismip_meta, var_index, region, isscalar)

    if not isscalar and region not in ("AIS", "GrIS"):
        spatial_reporter.write("SPATIAL Tests \n")
        spatial_reporter.note(
            "Not checked: the expected grid extent and resolutions depend on"
            " the region, which the file name does not identify."
        )
    elif not isscalar:
        _check_spatial(spatial_reporter, ds, grid_extent, possible_resolution)

    _check_time(
        time_reporter, ds, dim, experiments, experiment_name, var_type,
        ismip_meta[index]["dim"], naming.filename_years,
    )

    _check_attributes(
        attr_reporter, ds, ivar, ismip_meta, var_index, isscalar, var_type, region
    )


def _warning_phrase(warnings: int) -> str:
    """How the console mentions warnings, when there are any to mention.

    Phrased so that it cannot be read as a failure: a run that reports only
    warnings has passed.
    """
    if warnings == 0:
        return ""
    return f" ({warnings} warning(s) — see the log)"


def _print_experiment_summary(
    experiment_name: str, exp_errors: int, exp_warnings: int = 0
) -> None:
    print(experiment_name, ": compliance check processed.")
    if exp_errors > 0:
        print(
            "Found",
            exp_errors,
            f"errors{_warning_phrase(exp_warnings)}."
            " Check compliance_checker_log.txt for details.",
        )
    else:
        print("Successfully verified with no errors" + _warning_phrase(exp_warnings))
    print()


def _print_total_summary(
    source_path: str, total_errors: int, total_warnings: int = 0
) -> None:
    print("-------------------------------------------------------------------------")
    print(source_path, ": compliance check processed.")
    if total_errors > 0:
        print(
            "Found a total of",
            total_errors,
            f"errors{_warning_phrase(total_warnings)}."
            " Check compliance_checker_log.txt for details.",
        )
    else:
        print("Successfully verified with no errors" + _warning_phrase(total_warnings))
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


# The reporting categories, in the order the synthesis block lists them, with
# the label each one carries there.
SYNTHESIS_CATEGORIES = (
    # 'Variable presence' rather than 'Mandatory variables': the category now
    # also carries the warning about non-mandatory variables not submitted,
    # which the old label contradicted.
    ("file", "Variable presence  "),
    ("naming", "Naming Tests       "),
    ("num", "Numerical Tests    "),
    ("spatial", "Spatial Tests      "),
    ("time", "Time Tests         "),
    ("attr", "Attribute Tests    "),
)

# The summary key each category's counts live under, by severity.
_SUMMARY_KEYS = {
    "file": "total_file_{severity}s",
    "naming": "total_naming_{severity}s",
    "num": "total_num_{severity}s",
    "spatial": "total_spatial_{severity}s",
    "time": "total_time_{severity}s",
    "attr": "total_attr_{severity}s",
}


def _insert_synthesis(source_path: str, summary: dict) -> None:
    report_naming_issues = summary["report_naming_issues"]

    with open(os.path.join(source_path, "compliance_checker_log.txt"), "r") as f:
        contents = f.readlines()

    iline = 11
    contents.insert(iline, str(summary["exp_counter"]) + " experiments checked.\n")
    iline += 1
    contents.insert(iline, str(summary["file_counter"]) + " files checked.\n")
    iline += 2
    for severity in ("error", "warning"):
        contents.insert(
            iline, str(summary[f"total_{severity}s"]) + f" {severity}(s) detected.\n"
        )
        iline += 1
        for category, label in SYNTHESIS_CATEGORIES:
            count = summary[_SUMMARY_KEYS[category].format(severity=severity)]
            contents.insert(iline, f"  - {label}: {count} {severity}(s)\n")
            iline += 1
        # Step over one of the blank lines the header left behind, so that each
        # block is separated from the next.
        iline += 1
    if report_naming_issues:
        contents.insert(iline, "Naming tests errors report: \n")
        iline += 1
        for issue in report_naming_issues:
            contents.insert(iline, "  - " + issue.rstrip("\n") + "\n")
            iline += 1
        contents.insert(iline, "\n")

    with open(os.path.join(source_path, "compliance_checker_log.txt"), "w") as f:
        f.writelines(contents)
