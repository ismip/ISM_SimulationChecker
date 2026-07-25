import shutil
from datetime import datetime
from pathlib import Path

import netCDF4
import pytest

# The installed package is what is tested: run `pip install --no-deps
# --no-build-isolation -e .` (or without -e) before pytest.
from isschecker import checker
from isschecker import generate as generate_test_files


@pytest.fixture(scope="session")
def baseline_core_dir(tmp_path_factory):
    baseline_root = tmp_path_factory.mktemp("baseline_checker_data")
    created_files = generate_test_files.create_netcdf_file(
        None,
        grid_name="GrIS_16000m",
        scenario="historical",
        start_year=2013,
        nyears=2,
        include_scalars=True,
        include_xyt=False,
        output_root=baseline_root,
    )
    assert created_files, "Synthetic baseline generation did not create any files."

    core_dir = baseline_root / "GrIS" / "ISMIP7" / "SYNTH1" / "CORE" / "C001"
    baseline_summary = checker.run_checker(
        source_path=str(core_dir),
        variable_list="ismip7_scalars",
        version="tests",
    )
    assert baseline_summary["total_errors"] == 0, (
        "Synthetic baseline files should pass the checker, but found "
        f"{baseline_summary['total_errors']} errors.\n{baseline_summary['log_text']}"
    )
    return core_dir


@pytest.fixture
def case_dir(tmp_path, baseline_core_dir):
    case_root = tmp_path / "CORE" / "C001"
    shutil.copytree(baseline_core_dir, case_root)
    return case_root


def run_checker(case_dir: Path):
    return checker.run_checker(
        source_path=str(case_dir),
        variable_list="ismip7_scalars",
        version="tests",
    )


def first_dataset(case_dir: Path) -> Path:
    return sorted(case_dir.glob("*.nc"))[0]


def rename_file_part(file_path: Path, index: int, new_value: str) -> Path:
    parts = file_path.name.split("_")
    parts[index] = new_value
    renamed_path = file_path.with_name("_".join(parts))
    file_path.rename(renamed_path)
    return renamed_path


def set_time_values(file_path: Path, datetimes) -> None:
    with netCDF4.Dataset(file_path, "a") as dataset:
        time_var = dataset.variables["time"]
        time_var[:] = netCDF4.date2num(
            datetimes,
            units=time_var.units,
            calendar=getattr(time_var, "calendar", "standard"),
        )


def remove_global_attribute(file_path: Path, attr_name: str) -> None:
    with netCDF4.Dataset(file_path, "a") as dataset:
        dataset.delncattr(attr_name)


def set_variable_units(file_path: Path, units: str) -> None:
    """Rewrite the units of the main (ISMIP7-named) variable of a file."""
    variable_name = file_path.name.split("_")[0]
    with netCDF4.Dataset(file_path, "a") as dataset:
        dataset.variables[variable_name].units = units


def dataset_for_variable(case_dir: Path, variable_name: str) -> Path:
    return sorted(case_dir.glob(f"{variable_name}_*.nc"))[0]


def rename_variable_in_file(file_path: Path, old_name: str, new_name: str) -> None:
    """Rename a variable inside a file, leaving the file name alone."""
    with netCDF4.Dataset(file_path, "a") as dataset:
        dataset.renameVariable(old_name, new_name)


def add_variable_to_file(file_path: Path, name: str) -> None:
    """Add a stray variable, leaving the requested one in place."""
    with netCDF4.Dataset(file_path, "a") as dataset:
        dataset.createVariable(name, "f4", ("time",))


def test_generated_scalar_dataset_passes_checker(case_dir):
    summary = run_checker(case_dir)

    assert summary["total_errors"] == 0
    assert summary["total_file_errors"] == 0
    assert summary["total_naming_errors"] == 0
    assert summary["total_time_errors"] == 0
    assert "No errors. Good job !" in summary["log_text"]


def test_checker_reports_missing_mandatory_variable(case_dir):
    first_dataset(case_dir).unlink()

    summary = run_checker(case_dir)

    assert summary["total_file_errors"] == 1
    assert summary["total_errors"] == 1
    assert "mandatory variable(s) is (are) missing" in summary["log_text"]


def test_checker_reports_invalid_esm_in_filename(case_dir):
    rename_file_part(
        first_dataset(case_dir),
        checker.ISMIP7_FILENAME_ESM_IDX,
        "NOT-A-CMIP-MODEL",
    )

    summary = run_checker(case_dir)

    assert summary["total_naming_errors"] == 1
    assert summary["total_errors"] == 1
    assert "is not a recognised CMIP6/CMIP7 model name" in summary["log_text"]


def test_checker_reports_invalid_year_range_format(case_dir):
    rename_file_part(
        first_dataset(case_dir),
        checker.ISMIP7_FILENAME_YEAR_RANGE_IDX,
        "2013to2014.nc",
    )

    summary = run_checker(case_dir)

    assert summary["total_naming_errors"] == 1
    assert summary["total_errors"] == 1
    assert "does not match expected format YYYY-YYYY" in summary["log_text"]


def test_checker_reports_historical_time_range_violation(case_dir):
    target_file = first_dataset(case_dir)
    set_time_values(
        target_file,
        [
            datetime(2016, 1, 1),
            datetime(2017, 1, 1),
        ],
    )
    rename_file_part(
        target_file,
        checker.ISMIP7_FILENAME_YEAR_RANGE_IDX,
        "2015-2016.nc",
    )

    summary = run_checker(case_dir)

    assert summary["total_time_errors"] >= 2
    assert summary["total_naming_errors"] == 0
    assert "The date should be comprised between" in summary["log_text"]


@pytest.mark.parametrize(
    "variable_name, units",
    [
        # The data request asks for 'm^2' here and 'kg s-1' there, so both
        # directions of the caret spelling are covered.
        ("iareagr", "m2"),
        ("iareagr", "m**2"),
        ("tendacabf", "kg s^-1"),
        ("tendacabf", "kg/s"),
        ("tendacabf", "kg.s-1"),
    ],
)
def test_checker_accepts_equivalent_units_spellings(case_dir, variable_name, units):
    set_variable_units(dataset_for_variable(case_dir, variable_name), units)

    summary = run_checker(case_dir)

    assert summary["total_num_errors"] == 0
    assert summary["total_errors"] == 0
    assert f" - The unit is correct: {units} (equivalent to the requested " in (
        summary["log_text"]
    )


def test_checker_reports_wrong_units(case_dir):
    set_variable_units(dataset_for_variable(case_dir, "iareagr"), "m^3")

    summary = run_checker(case_dir)

    assert summary["total_num_errors"] == 1
    assert summary["total_errors"] == 1
    assert "The unit of the variable is m^3 and should be m^2" in summary["log_text"]


@pytest.mark.parametrize(
    "actual, expected, matches",
    [
        ("m^2", "m2", True),
        ("m**2", "m2", True),
        ("kg m^-2 s^-1", "kg m-2 s-1", True),
        ("kg.m-2.s-1", "kg m-2 s-1", True),
        ("kg/m2/s", "kg m-2 s-1", True),
        ("s-1 kg m-2", "kg m-2 s-1", True),
        ("kg  m-2   s-1", "kg m-2 s-1", True),
        ("1", "1", True),
        ("m3", "m2", False),
        ("kg m-2", "kg m-2 s-1", False),
        ("km", "m", False),
        ("M", "m", False),
        # UDUNITS divides left to right, so the '/' inverts only 'm2' here.
        ("kg/m2*s", "kg m-2 s-1", False),
        ("kg/m2 s", "kg m-2 s-1", False),
        # Not understood, so compared as strings rather than guessed at.
        ("", "1", False),
        ("kg/(m2 s)", "kg m-2 s-1", False),
        ("days since 1850-01-01", "days since 1850-01-01", True),
        ("days since 1850-01-01", "days since 2000-01-01", False),
    ],
)
def test_units_match(actual, expected, matches):
    assert checker._units_match(actual, expected) is matches


def test_checker_reports_variable_missing_from_file(case_dir):
    rename_variable_in_file(dataset_for_variable(case_dir, "lim"), "lim", "limm")

    summary = run_checker(case_dir)

    assert summary["total_naming_errors"] == 1
    assert summary["total_errors"] == 1
    assert (
        "the file name promises variable 'lim', but the file does not contain it"
        in summary["log_text"]
    )
    assert "'limm' may be a misspelling of 'lim'" in summary["log_text"]


def test_checker_reports_swapped_variable_in_file(case_dir):
    rename_variable_in_file(dataset_for_variable(case_dir, "lim"), "lim", "limnsw")

    summary = run_checker(case_dir)

    assert summary["total_naming_errors"] == 1
    assert summary["total_errors"] == 1
    # The variable that was swapped in is no longer checked against its own row
    # of the data request, so the standard_name mismatch that used to be the
    # only -- and incidental -- sign of this file's problem is gone.
    assert summary["total_attr_errors"] == 0
    assert "does not match expected 'land_ice_mass" not in summary["log_text"]


def test_checker_reports_unexpected_variable_in_file(case_dir):
    add_variable_to_file(dataset_for_variable(case_dir, "lim"), "mask")

    summary = run_checker(case_dir)

    assert summary["total_naming_errors"] == 1
    assert summary["total_errors"] == 1
    assert "unexpected variable 'mask' in the file" in summary["log_text"]
    # An extra variable does not make the file uncheckable, so the requested
    # one is still checked.
    assert "** Tested Variable: lim\n" in summary["log_text"]


def test_checker_reports_missing_contact_email_attribute(case_dir):
    remove_global_attribute(first_dataset(case_dir), "contact_email")

    summary = run_checker(case_dir)

    assert summary["total_attr_errors"] == 1
    assert summary["total_errors"] == 1
    assert "global attribute 'contact_email' is missing" in summary["log_text"]