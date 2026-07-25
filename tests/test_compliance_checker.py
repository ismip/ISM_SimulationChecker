import importlib.util
import shutil
import sys
from datetime import datetime
from pathlib import Path

import netCDF4
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

checker = importlib.import_module("isschecker.checker")


def _load_generator_module():
    generator_path = REPO_ROOT / "generate" / "generate_test_files.py"
    spec = importlib.util.spec_from_file_location("generate_test_files", generator_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


generate_test_files = _load_generator_module()


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
        commit_num="tests",
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
        commit_num="tests",
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


def test_checker_reports_missing_contact_email_attribute(case_dir):
    remove_global_attribute(first_dataset(case_dir), "contact_email")

    summary = run_checker(case_dir)

    assert summary["total_attr_errors"] == 1
    assert summary["total_errors"] == 1
    assert "global attribute 'contact_email' is missing" in summary["log_text"]