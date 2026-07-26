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


@pytest.fixture(scope="session")
def baseline_xyt_core_dir(tmp_path_factory):
    """A spatial baseline, for the cases a time-only variable cannot express.

    Dimension order, in particular, needs a variable that has more than one.
    Non-mandatory variables are included because refgeoid (x,y) and litemp
    (x,y,z,t) are the only variables of their shape in the data request, and
    without them two of the four dimension forms would go unexercised.
    """
    baseline_root = tmp_path_factory.mktemp("baseline_xyt_checker_data")
    created_files = generate_test_files.create_netcdf_file(
        None,
        grid_name="GrIS_16000m",
        scenario="historical",
        start_year=2013,
        nyears=2,
        include_scalars=False,
        include_xyt=True,
        include_non_mandatory=True,
        output_root=baseline_root,
    )
    assert created_files, "Synthetic baseline generation did not create any files."

    core_dir = baseline_root / "GrIS" / "ISMIP7" / "SYNTH1" / "CORE" / "C001"
    baseline_summary = checker.run_checker(
        source_path=str(core_dir),
        variable_list="ismip7_xyt",
        version="tests",
    )
    assert baseline_summary["total_errors"] == 0, (
        "Synthetic baseline files should pass the checker, but found "
        f"{baseline_summary['total_errors']} errors.\n{baseline_summary['log_text']}"
    )
    return core_dir


@pytest.fixture(scope="session")
def baseline_ctrl_core_dir(tmp_path_factory):
    """A full-length ctrl baseline: 286 nominal years, 2015-2300.

    The short historical runs the other fixtures use cannot express a decimated
    or sparsely sampled axis, which is the failure the endpoint-based checks
    used to miss. This is also the only fixture that exercises the real ISMIP7
    projection length end to end.
    """
    baseline_root = tmp_path_factory.mktemp("baseline_ctrl_checker_data")
    created_files = generate_test_files.create_netcdf_file(
        None,
        grid_name="GrIS_16000m",
        scenario="ctrl",
        start_year=2015,
        nyears=286,
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
        "A full-length ctrl run should pass the checker, but found "
        f"{baseline_summary['total_errors']} errors.\n{baseline_summary['log_text']}"
    )
    return core_dir


@pytest.fixture
def ctrl_case_dir(tmp_path, baseline_ctrl_core_dir):
    case_root = tmp_path / "CORE" / "C001"
    shutil.copytree(baseline_ctrl_core_dir, case_root)
    return case_root


@pytest.fixture
def case_dir(tmp_path, baseline_core_dir):
    case_root = tmp_path / "CORE" / "C001"
    shutil.copytree(baseline_core_dir, case_root)
    return case_root


@pytest.fixture
def xyt_case_dir(tmp_path, baseline_xyt_core_dir):
    case_root = tmp_path / "CORE" / "C001"
    shutil.copytree(baseline_xyt_core_dir, case_root)
    return case_root


def run_checker(case_dir: Path):
    return checker.run_checker(
        source_path=str(case_dir),
        variable_list="ismip7_scalars",
        version="tests",
    )


def run_xyt_checker(case_dir: Path):
    return checker.run_checker(
        source_path=str(case_dir),
        variable_list="ismip7_xyt",
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


def set_time_axis(file_path: Path, datetimes) -> None:
    """Rewrite a file with a different number of time steps.

    netCDF cannot shrink a dimension in place, so the file is rebuilt. Data is
    taken from the first `len(datetimes)` steps of every time-varying variable
    and everything else is copied across unchanged, which is what keeps the
    checks other than the one under test seeing exactly what they saw before.
    """
    rebuilt = file_path.with_name(file_path.name + ".rebuilt")
    with netCDF4.Dataset(file_path) as source, netCDF4.Dataset(rebuilt, "w") as target:
        target.setncatts(source.__dict__)
        for name, dimension in source.dimensions.items():
            target.createDimension(
                name, None if dimension.isunlimited() else len(dimension)
            )
        for name, variable in source.variables.items():
            fill_value = (
                variable.getncattr("_FillValue")
                if "_FillValue" in variable.ncattrs()
                else None
            )
            created = target.createVariable(
                name, variable.datatype, variable.dimensions, fill_value=fill_value
            )
            created.setncatts(
                {k: v for k, v in variable.__dict__.items() if k != "_FillValue"}
            )
            values = variable[:]
            if "time" in variable.dimensions:
                values = values[: len(datetimes)]
            created[:] = values
        target.variables["time"][:] = netCDF4.date2num(
            datetimes,
            units=source.variables["time"].units,
            calendar=getattr(source.variables["time"], "calendar", "standard"),
        )
    rebuilt.replace(file_path)


def state_timestamps(nominal_years):
    """The ST encoding of a list of nominal years: Jan 1 of the year after."""
    return [datetime(year + 1, 1, 1) for year in nominal_years]


def flux_timestamps(nominal_years):
    """The FL encoding of a list of nominal years: Jul 1 of the year itself."""
    return [datetime(year, 7, 1) for year in nominal_years]


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


def add_companion_variable(
    file_path: Path, name: str, attribute: str, value: str
) -> None:
    """Add a variable and have the requested one name it, the CF way."""
    variable_name = file_path.name.split("_")[0]
    with netCDF4.Dataset(file_path, "a") as dataset:
        dataset.createVariable(name, "f4", ("time",))
        dataset.variables[variable_name].setncattr(attribute, value)


def _laid_out_as(values, old_dimensions, new_dimensions):
    """Re-lay values from `old_dimensions` to `new_dimensions`.

    The first index is taken along any dimension being dropped, and what is
    left is transposed, so the result is real data laid out the way the
    rewritten header says it is.
    """
    for index, name in reversed(list(enumerate(old_dimensions))):
        if name not in new_dimensions:
            values = values[(slice(None),) * index + (0,)]
    kept = [name for name in old_dimensions if name in new_dimensions]
    return values.transpose([kept.index(name) for name in new_dimensions])


def set_variable_dimensions(file_path: Path, variable_name: str, dimensions) -> None:
    """Rewrite one variable with a different set or order of dimensions.

    netCDF cannot reshape a variable in place, so the file is rebuilt: every
    other variable, every attribute and the unlimited dimension are copied
    across unchanged, which is what keeps the checks other than the one under
    test seeing exactly what they saw before.
    """
    rebuilt = file_path.with_name(file_path.name + ".rebuilt")
    with netCDF4.Dataset(file_path) as source, netCDF4.Dataset(rebuilt, "w") as target:
        target.setncatts(source.__dict__)
        for name, dimension in source.dimensions.items():
            target.createDimension(
                name, None if dimension.isunlimited() else len(dimension)
            )
        for name, variable in source.variables.items():
            changed = name == variable_name
            fill_value = (
                variable.getncattr("_FillValue")
                if "_FillValue" in variable.ncattrs()
                else None
            )
            created = target.createVariable(
                name,
                variable.datatype,
                tuple(dimensions) if changed else variable.dimensions,
                fill_value=fill_value,
            )
            created.setncatts(
                {k: v for k, v in variable.__dict__.items() if k != "_FillValue"}
            )
            created[:] = (
                _laid_out_as(variable[:], variable.dimensions, tuple(dimensions))
                if changed
                else variable[:]
            )
    rebuilt.replace(file_path)


def test_generated_scalar_dataset_passes_checker(case_dir):
    summary = run_checker(case_dir)

    assert summary["total_errors"] == 0
    assert summary["total_file_errors"] == 0
    assert summary["total_naming_errors"] == 0
    assert summary["total_time_errors"] == 0
    assert "No errors. Good job !" in summary["log_text"]
    assert "match the requested t: OK" in summary["log_text"]


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


def test_checker_still_checks_a_file_with_an_unrecognised_esm(case_dir):
    """A mistyped file name must not hide the problems inside the file.

    A naming error used to abandon the file, so a modeller fixed the name, ran
    again, and only then found out about the time axis. Nothing about an ESM
    name affects whether the rest of the file can be read.
    """
    target_file = dataset_for_variable(case_dir, "lim")
    set_time_values(target_file, state_timestamps([2012, 2013]))
    rename_file_part(
        target_file, checker.ISMIP7_FILENAME_ESM_IDX, "NOT-A-CMIP-MODEL"
    )

    summary = run_checker(case_dir)

    assert summary["total_naming_errors"] == 1
    assert summary["total_time_errors"] >= 1
    assert "is not a recognised CMIP6/CMIP7 model name" in summary["log_text"]
    assert "nominal year(s) missing from the time axis: 2014" in summary["log_text"]


def test_checker_skips_only_region_dependent_checks_for_a_bad_region(xyt_case_dir):
    """An unrecognised region costs the checks that need it, and no others.

    Value range, grid extent/resolution and crs are all defined per ice sheet,
    so they cannot be checked; the time axis does not depend on the region at
    all, and previously went unchecked purely because the region check ran
    first.
    """
    target_file = dataset_for_variable(xyt_case_dir, "lithk")
    set_time_values(target_file, state_timestamps([2012, 2013]))
    renamed = rename_file_part(target_file, checker.ISMIP7_FILENAME_REGION_IDX, "XXX")
    assert renamed.exists()

    summary = run_xyt_checker(xyt_case_dir)

    assert summary["total_naming_errors"] == 1
    assert "Region XXX not recognized" in summary["log_text"]

    # The checks that genuinely depend on the region say so rather than
    # silently falling back to one ice sheet's criteria.
    assert "Value range: not checked" in summary["log_text"]
    assert "the expected grid extent and resolutions depend on" in summary["log_text"]
    assert "Global attribute 'crs': not checked" in summary["log_text"]

    # ... and the ones that do not, still run.
    assert summary["total_time_errors"] >= 1
    assert "nominal year(s) missing from the time axis: 2014" in summary["log_text"]


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
    assert (
        "the file name starts at year 2015, but experiment 'historical' must be"
        " between 1850 and 2014" in summary["log_text"]
    )
    assert (
        "the file name ends at year 2016, but experiment 'historical' must end"
        " at 2014" in summary["log_text"]
    )


def test_checker_reports_time_axis_hollowed_out_between_correct_endpoints(
    ctrl_case_dir,
):
    """The case the old endpoint reasoning could not see, in its purest form.

    2015, 2016, 2299, 2300 starts in the right year, ends in the right year, and
    has a 365-day first interval, so a duration computed from the endpoints and
    a cadence read off the first pair both agreed it was a 286-year run. It is
    282 time steps short.
    """
    set_time_axis(
        dataset_for_variable(ctrl_case_dir, "lim"),
        state_timestamps([2015, 2016, 2299, 2300]),
    )

    summary = run_checker(ctrl_case_dir)

    assert summary["total_time_errors"] >= 1
    assert (
        "the time axis has 4 time step(s); 286 expected for nominal years"
        " 2015-2300" in summary["log_text"]
    )
    assert (
        "nominal year(s) missing from the time axis: 2017-2298 (282 year(s))"
        in summary["log_text"]
    )


def test_checker_reports_decimated_time_axis(ctrl_case_dir):
    """Every tenth year of a ctrl run, which also exercises run summarising.

    257 missing years fall into 29 runs, far more than are worth printing, so
    the message names the first few and counts the rest.
    """
    set_time_axis(
        dataset_for_variable(ctrl_case_dir, "lim"),
        state_timestamps(list(range(2015, 2300, 10))),
    )

    summary = run_checker(ctrl_case_dir)

    assert summary["total_time_errors"] >= 1
    assert (
        "the time axis has 29 time step(s); 286 expected for nominal years"
        " 2015-2300" in summary["log_text"]
    )
    assert (
        "missing from the time axis: 2016-2024, 2026-2034, 2036-2044,"
        " 2046-2054, 2056-2064, and 24 further run(s) (257 year(s))"
        in summary["log_text"]
    )


def test_checker_reports_gap_in_time_axis(case_dir):
    """Correct first and last year, eight years missing in between."""
    target_file = dataset_for_variable(case_dir, "lim")
    set_time_values(target_file, state_timestamps([2005, 2014]))
    rename_file_part(
        target_file, checker.ISMIP7_FILENAME_YEAR_RANGE_IDX, "2005-2014.nc"
    )

    summary = run_checker(case_dir)

    assert summary["total_time_errors"] >= 1
    assert (
        "the time axis has 2 time step(s); 10 expected for nominal years"
        " 2005-2014" in summary["log_text"]
    )
    assert (
        "nominal year(s) missing from the time axis: 2006-2013 (8 year(s))"
        in summary["log_text"]
    )


def test_checker_reports_time_axis_shifted_by_one_year(case_dir):
    """The right number of steps, all of them a year early.

    A count check on its own would pass this, which is why the check compares
    the years themselves rather than just how many there are.
    """
    set_time_values(
        dataset_for_variable(case_dir, "lim"), state_timestamps([2012, 2013])
    )

    summary = run_checker(case_dir)

    assert summary["total_time_errors"] >= 1
    assert (
        "nominal year(s) missing from the time axis: 2014" in summary["log_text"]
    )
    assert (
        "nominal year(s) on the time axis that the experiment does not call"
        " for: 2012" in summary["log_text"]
    )


def test_checker_reports_duplicated_time_steps(case_dir):
    set_time_values(
        dataset_for_variable(case_dir, "lim"), state_timestamps([2013, 2013])
    )

    summary = run_checker(case_dir)

    assert summary["total_time_errors"] >= 1
    assert "not monotonically increasing" in summary["log_text"]


def test_checker_reports_filename_start_year_disagreeing_with_axis(case_dir):
    """The name claims five years of historical; the axis carries two."""
    rename_file_part(
        dataset_for_variable(case_dir, "lim"),
        checker.ISMIP7_FILENAME_YEAR_RANGE_IDX,
        "2010-2014.nc",
    )

    summary = run_checker(case_dir)

    assert summary["total_time_errors"] >= 1
    assert (
        "the time axis has 2 time step(s); 5 expected for nominal years"
        " 2010-2014" in summary["log_text"]
    )


def test_checker_reports_flux_variable_with_state_timestamps(case_dir):
    """An FL file written with the ST convention is one mistake, said once."""
    set_time_values(
        dataset_for_variable(case_dir, "tendacabf"), state_timestamps([2013, 2014])
    )

    summary = run_checker(case_dir)

    assert summary["total_time_errors"] == 1
    assert (
        "the time axis follows the ST convention (Jan 1 of the year after the"
        " nominal year), but this variable is FL" in summary["log_text"]
    )


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
    # The problem is also named in the synthesis at the top of the log, which
    # is where a modeler with a long log looks first.
    synthesis = summary["log_text"].split("DETAILED RESULTS")[0]
    assert "Naming tests errors report:" in synthesis
    assert "does not contain it" in synthesis


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


@pytest.mark.parametrize(
    "attribute, value",
    [
        ("cell_measures", "area: cellarea"),
        ("ancillary_variables", "cellarea"),
    ],
)
def test_checker_accepts_cf_companion_variables(case_dir, attribute, value):
    """A companion the requested variable names is part of the file, not an extra.

    The allowlist already understood bounds, grid_mapping and coordinates, so a
    CF-legal cell_measures or ancillary_variables companion -- carried precisely
    so that the requested variable means what it says -- was reported as a
    violation for no reason.
    """
    add_companion_variable(
        dataset_for_variable(case_dir, "lim"), "cellarea", attribute, value
    )

    summary = run_checker(case_dir)

    assert summary["total_errors"] == 0, summary["log_text"]
    assert "ERROR: unexpected variable" not in summary["log_text"]


def test_generated_xyt_dataset_passes_checker(xyt_case_dir):
    summary = run_xyt_checker(xyt_case_dir)

    assert summary["total_errors"] == 0
    # Every spatial dimension form the data request uses is represented here,
    # so the translation from its 'Dim' column to the dimensions of a file is
    # checked in all of them rather than only the mandatory x,y,t.  The
    # remaining form, t, belongs to the scalar baseline above.
    for requested_dim in ("x,y", "x,y,t", "x,y,z,t"):
        assert f"match the requested {requested_dim}: OK" in summary["log_text"]


def test_checker_reports_litemp_missing_required_snapshot(xyt_case_dir):
    """A single snapshot where two are required.

    This is the snapshot half of issue #12. The old check validated only the
    years a file happened to contain, and treated the file's own last time step
    as valid whatever it was, so this passed.
    """
    set_time_axis(
        dataset_for_variable(xyt_case_dir, "litemp"), state_timestamps([2014])
    )

    summary = run_xyt_checker(xyt_case_dir)

    assert summary["total_time_errors"] >= 1
    assert (
        "required snapshot nominal year(s) missing: 2013" in summary["log_text"]
    )


def test_checker_reports_litemp_snapshot_year_not_requested(xyt_case_dir):
    set_time_values(
        dataset_for_variable(xyt_case_dir, "litemp"), state_timestamps([1975, 2014])
    )

    summary = run_xyt_checker(xyt_case_dir)

    assert summary["total_time_errors"] >= 1
    assert (
        "snapshot nominal year(s) the experiment does not call for: 1975"
        in summary["log_text"]
    )


def test_checker_accepts_litemp_snapshot_at_2000(tmp_path):
    """2000 is tolerated but not required, pending issue #12.

    The generator no longer writes it and the data request does not ask for it,
    but the README did until now, so a group that followed the README must not
    be failed for a year that is still in dispute. Nothing else covers the
    'permitted but not required' path once the generator stops emitting it.
    """
    root = tmp_path / "gen"
    generate_test_files.create_netcdf_file(
        None,
        grid_name="GrIS_16000m",
        scenario="historical",
        start_year=1995,
        nyears=20,
        include_scalars=False,
        include_xyt=True,
        include_non_mandatory=True,
        output_root=root,
    )
    core_dir = root / "GrIS" / "ISMIP7" / "SYNTH1" / "CORE" / "C001"
    litemp = dataset_for_variable(core_dir, "litemp")

    # The generator writes 1995 and 2014; add the disputed 2000 alongside them.
    set_time_axis(litemp, state_timestamps([1995, 2000, 2014]))

    summary = checker.run_checker(
        source_path=str(core_dir), variable_list="ismip7_xyt", version="tests"
    )

    assert summary["total_time_errors"] == 0, summary["log_text"]
    assert "does not call for" not in summary["log_text"]


def test_checker_reports_missing_variable_dimension(xyt_case_dir):
    # lithk is requested as x,y,t; this one loses its y dimension.
    set_variable_dimensions(
        dataset_for_variable(xyt_case_dir, "lithk"), "lithk", ("time", "x")
    )

    summary = run_xyt_checker(xyt_case_dir)

    assert summary["total_naming_errors"] == 1
    assert summary["total_errors"] == 1
    assert (
        "variable 'lithk' has dimensions ('time', 'x'); the data request asks "
        "for x,y,t, that is ('time', 'y', 'x')" in summary["log_text"]
    )


def test_checker_reports_transposed_variable(xyt_case_dir):
    set_variable_dimensions(
        dataset_for_variable(xyt_case_dir, "lithk"), "lithk", ("time", "x", "y")
    )

    summary = run_xyt_checker(xyt_case_dir)

    assert summary["total_naming_errors"] == 1
    assert summary["total_errors"] == 1
    assert (
        "variable 'lithk' has dimensions ('time', 'x', 'y'); the data request "
        "asks for x,y,t in the conventional order ('time', 'y', 'x')"
        in summary["log_text"]
    )


def test_checker_reports_unknown_variable_in_file_name(case_dir):
    rename_file_part(
        dataset_for_variable(case_dir, "lim"),
        checker.ISMIP7_FILENAME_VAR_IDX,
        "bogusvar",
    )

    summary = run_checker(case_dir)

    assert summary["total_naming_errors"] == 1
    assert (
        "'bogusvar' (field 0 of the file name) is not a variable in the data "
        "request" in summary["log_text"]
    )
    # The file no longer supplies lim, so the mandatory-variable check fires
    # too; before this the missing variable was the only sign of the problem.
    assert summary["total_file_errors"] == 1
    assert summary["total_errors"] == 2


def test_checker_ignores_variables_outside_the_selected_list(xyt_case_dir):
    """An x,y,t file is skipped, not faulted, by a scalars-only run.

    The README has modelers check a directory once per variable list, so the
    files belonging to the other list have to pass by in silence.
    """
    summary = checker.run_checker(
        source_path=str(xyt_case_dir),
        variable_list="ismip7_scalars",
        version="tests",
    )

    assert "is not a variable in the data request" not in summary["log_text"]
    assert summary["total_naming_errors"] == 0


def test_checker_reports_missing_contact_email_attribute(case_dir):
    remove_global_attribute(first_dataset(case_dir), "contact_email")

    summary = run_checker(case_dir)

    assert summary["total_attr_errors"] == 1
    assert summary["total_errors"] == 1
    assert "global attribute 'contact_email' is missing" in summary["log_text"]