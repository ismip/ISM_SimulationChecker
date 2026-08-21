"""Finding the file next door, and lining its time axis up with this one.

The scaffolding the cross-file checks stand on, tested apart from them: a
companion that cannot be found or cannot be aligned has to produce a note and
no finding, because checking a submission a part at a time is something the
checker has to keep supporting.
"""

import io
import shutil
from pathlib import Path

import pytest
import xarray as xr

from isschecker import checker
from isschecker import generate as generate_test_files


@pytest.fixture(scope="module")
def core_dir(tmp_path_factory):
    root = tmp_path_factory.mktemp("companion_data")
    generate_test_files.create_netcdf_file(
        None,
        grid_name="GrIS_16000m",
        scenario="historical",
        start_year=2013,
        nyears=2,
        include_scalars=False,
        include_xyt=True,
        include_non_mandatory=True,
        output_root=root,
    )
    return root / "GrIS" / "ISMIP7" / "SYNTH1" / "CORE" / "C001"


@pytest.fixture
def case_dir(tmp_path, core_dir):
    case = tmp_path / "case"
    shutil.copytree(core_dir, case)
    return case


def name_of(case_dir: Path, variable: str) -> str:
    return sorted(case_dir.glob(f"{variable}_*.nc"))[0].name


def open_companion(case_dir: Path, file_variable: str, companion: str, years):
    """Run the lookup as the checks do, and hand back what it said."""
    log = io.StringIO()
    reporter = checker.Reporter(log).category("consistency")
    ismip_meta, _, _, _, _ = checker._load_criteria("ismip7")
    found = checker._open_companion(
        reporter,
        str(case_dir),
        name_of(case_dir, file_variable),
        companion,
        years,
        ismip_meta,
    )
    return found, log.getvalue()


def test_the_companion_is_found_by_name(case_dir):
    found, log = open_companion(case_dir, "xvelmean", "sftgif", [2013, 2014])
    assert found is not None, log
    assert found.at == [0, 1]
    found.dataset.close()


def test_a_flux_variable_aligns_with_a_state_mask(case_dir):
    """The same simulation year carries two different timestamps.

    A mask is ST, stamped Jan 1 of the following year; a basal mass flux is FL,
    stamped mid-year. Matching raw time values would align nothing, so the
    lookup matches nominal years instead.
    """
    found, log = open_companion(case_dir, "libmassbfgr", "sftgrf", [2013, 2014])
    assert found is not None, log
    assert found.at == [0, 1]
    found.dataset.close()


def test_a_snapshot_variable_picks_out_the_years_it_holds(case_dir):
    """litemp carries a sparse subset of the mask's annual axis."""
    found, log = open_companion(case_dir, "litemp", "sftgif", [2014])
    assert found is not None, log
    assert found.at == [1]
    found.dataset.close()


def test_a_static_variable_is_compared_against_the_whole_run(case_dir):
    """refgeoid has no time axis, so it meets the ice at its greatest extent."""
    found, log = open_companion(case_dir, "refgeoid", "sftgif", None)
    assert found is not None, log
    assert found.at is None
    field = found.slice_at(0)
    assert field.ndim == 2
    found.dataset.close()


def test_an_absent_companion_is_a_note_and_not_a_finding(case_dir):
    for path in case_dir.glob("sftgif_*.nc"):
        path.unlink()

    found, log = open_companion(case_dir, "xvelmean", "sftgif", [2013, 2014])

    assert found is None
    assert "no matching sftgif file" in log
    assert "ERROR" not in log and "WARNING" not in log


def test_a_time_axis_that_does_not_cover_the_years_is_a_note(case_dir):
    found, log = open_companion(case_dir, "xvelmean", "sftgif", [2013, 2099])

    assert found is None
    assert "does not cover nominal year(s) 2099" in log
    assert "ERROR" not in log and "WARNING" not in log


def test_a_companion_file_without_its_variable_is_a_note(case_dir):
    path = sorted(case_dir.glob("sftgif_*.nc"))[0]
    with xr.open_dataset(path, decode_times=False, mask_and_scale=False) as ds:
        renamed = ds.rename({"sftgif": "something_else"}).load()
    renamed.to_netcdf(path)

    found, log = open_companion(case_dir, "xvelmean", "sftgif", [2013, 2014])

    assert found is None
    assert "does not contain it" in log
    assert "ERROR" not in log and "WARNING" not in log
