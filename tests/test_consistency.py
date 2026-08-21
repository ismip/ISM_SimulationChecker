"""The checks that compare one file against another.

Built by poking holes in the generated ice sheet, which is coherent to start
with -- see tests/test_generate.py for the properties these rules are entitled
to assume of it.
"""

import io
import shutil
from pathlib import Path

import netCDF4
import numpy as np
import pytest
import xarray as xr

from isschecker import checker
from isschecker import generate as generate_test_files


@pytest.fixture(scope="module")
def core_dir(tmp_path_factory):
    root = tmp_path_factory.mktemp("consistency_data")
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


FILL = netCDF4.default_fillvals["f4"]


def dataset_for_variable(case_dir: Path, variable_name: str) -> Path:
    return sorted(case_dir.glob(f"{variable_name}_*.nc"))[0]


def run(case_dir: Path):
    return checker.run_checker(
        source_path=str(case_dir), variable_list="ismip7_xyt", version="tests"
    )


def geometry_of(case_dir: Path):
    path = dataset_for_variable(case_dir, "lithk")
    with xr.open_dataset(path, decode_times=False, mask_and_scale=False) as ds:
        return generate_test_files.ice_sheet_geometry(ds["x"].values, ds["y"].values)


def set_where(file_path: Path, mask, value) -> None:
    """Write `value` into the main variable's cells where `mask` is True."""
    variable_name = file_path.name.split("_")[0]
    with netCDF4.Dataset(file_path, "a") as dataset:
        variable = dataset.variables[variable_name]
        variable.set_auto_mask(False)
        data = variable[:]
        data[..., mask] = value
        variable[:] = data


def test_a_velocity_defined_over_bare_ground_is_an_error(case_dir):
    """The inconsistency issue #23 opens with, stated exactly.

    A value here is not a hole an analyst can spot; it is a number they will
    take at face value over open ocean.
    """
    geometry = geometry_of(case_dir)
    set_where(dataset_for_variable(case_dir, "xvelmean"),
              geometry["sftgif"] == 0.0, 0.0)

    summary = run(case_dir)

    assert summary["total_consistency_errors"] == 1, summary["log_text"]
    assert "holds a value in" in summary["log_text"]
    assert "where 'sftgif' is 0" in summary["log_text"]


def test_a_velocity_missing_under_ice_is_a_warning_for_now(case_dir):
    """The other direction: ice the file says nothing about.

    A warning rather than an error for the trial round, because it is the
    finding a margin convention disagreement produces; see margin_severity.
    """
    geometry = geometry_of(case_dir)
    set_where(dataset_for_variable(case_dir, "xvelmean"),
              geometry["sftgif"] >= 1.0, FILL)

    summary = run(case_dir)

    assert summary["total_consistency_errors"] == 0, summary["log_text"]
    assert summary["total_consistency_warnings"] == 1
    assert "is missing in" in summary["log_text"]
    assert "there is ice the file says nothing about" in summary["log_text"]


class StubCompanion:
    """An ice mask of our choosing, for cases the synthetic sheet cannot pose."""

    variable = "sftgif"

    def __init__(self, fraction):
        self.fraction = np.asarray(fraction, dtype=np.float32)
        self.dataset = xr.Dataset(
            {
                self.variable: xr.DataArray(
                    self.fraction,
                    dims=("y", "x"),
                    attrs={"_FillValue": np.float32(FILL)},
                )
            }
        )

    def slice_at(self, step):
        return self.fraction


def one_step_dataset(values):
    array = xr.DataArray(
        np.asarray(values, dtype=np.float32)[np.newaxis, :, :],
        dims=("time", "y", "x"),
        attrs={"_FillValue": np.float32(FILL)},
    )
    return xr.Dataset({"v": array})


def test_a_hole_at_the_margin_says_how_much_of_it_is_margin():
    """The evidence the trial round needs, rather than an argument about it.

    A modeler seeing "1 of them have 'sftgif' below 0.01" knows at a glance
    that this is where their native mask and the interpolated one disagree, not
    that they have lost the interior of their ice sheet. Posed directly because
    a 16 km cell that is under 1% glaciated is finer than the synthetic ice
    sheet resolves.
    """
    ds = one_step_dataset([[FILL, FILL], [1.0, 1.0]])
    companion = StubCompanion([[1.0, 0.005], [1.0, 1.0]])

    log = io.StringIO()
    reporter = checker.Reporter(log).category("consistency")
    checker._check_ice_extent(
        reporter, ds, "v", {"margin_severity": "warning"}, companion
    )

    assert reporter.total_warnings == 1
    assert reporter.total_errors == 0
    assert "is missing in 2 of 4" in log.getvalue()
    assert "1 of them have 'sftgif' below 0.01" in log.getvalue()


def test_the_interior_is_not_described_as_margin():
    """The distribution line is left off when none of the holes are marginal."""
    ds = one_step_dataset([[FILL, FILL], [1.0, 1.0]])
    companion = StubCompanion([[1.0, 1.0], [1.0, 1.0]])

    log = io.StringIO()
    reporter = checker.Reporter(log).category("consistency")
    checker._check_ice_extent(
        reporter, ds, "v", {"margin_severity": "warning"}, companion
    )

    assert "partly glaciated margin" not in log.getvalue()


def test_the_two_directions_are_separate_findings(case_dir):
    """One count each, because they are different mistakes."""
    geometry = geometry_of(case_dir)
    path = dataset_for_variable(case_dir, "xvelmean")
    set_where(path, geometry["sftgif"] == 0.0, 0.0)
    set_where(path, geometry["sftgif"] >= 1.0, FILL)

    summary = run(case_dir)

    assert summary["total_consistency_errors"] == 1, summary["log_text"]
    assert summary["total_consistency_warnings"] == 1
    assert "holds a value in" in summary["log_text"]
    assert "is missing in" in summary["log_text"]


@pytest.mark.parametrize(
    "variable_name, mask_name",
    [("libmassbfgr", "sftgrf"), ("libmassbffl", "sftflf")],
)
def test_grounded_and_floating_variables_use_their_own_mask(
    case_dir, variable_name, mask_name
):
    """A basal flux beneath grounded ice is not checked against all the ice.

    It is also an FL variable against an ST mask, so this is the case where
    matching raw timestamps would have aligned nothing.
    """
    geometry = geometry_of(case_dir)
    set_where(dataset_for_variable(case_dir, variable_name),
              geometry[mask_name] == 0.0, 0.0)

    summary = run(case_dir)

    assert summary["total_consistency_errors"] == 1, summary["log_text"]
    assert f"where '{mask_name}' is 0" in summary["log_text"]


def test_an_absent_mask_leaves_a_note_and_no_finding(case_dir):
    """Checking a submission a part at a time has to keep working."""
    for path in case_dir.glob("sftgif_*.nc"):
        path.unlink()

    summary = run(case_dir)

    assert summary["total_consistency_errors"] == 0, summary["log_text"]
    assert summary["total_consistency_warnings"] == 0
    assert "no matching sftgif file" in summary["log_text"]


def test_ice_outside_the_computational_domain_is_an_error(case_dir):
    """The one thing the domain has to satisfy, since nothing records it.

    With the masks carrying no missing values, `sftgif == 0` covers both
    "inside the domain, ice-free" and "outside it entirely", so there is
    nothing to validate the domain against -- and nothing needs to be. What
    must hold is that the domain contains the ice.
    """
    geometry = geometry_of(case_dir)
    set_where(dataset_for_variable(case_dir, "orog"),
              geometry["sftgif"] > 0.0, FILL)

    summary = run(case_dir)

    assert "has ice outside its own domain" in summary["log_text"]
    assert summary["total_consistency_errors"] >= 1


def test_a_wider_footprint_than_its_neighbours_is_only_a_warning(case_dir):
    """acabf may legitimately come from a forcing dataset covering the grid.

    So a footprint wider than the ice model's is worth telling the modeler
    about without failing the run over it.
    """
    set_where(dataset_for_variable(case_dir, "acabf"),
              np.ones_like(geometry_of(case_dir)["domain"]), 0.0)

    summary = run(case_dir)

    assert summary["total_consistency_errors"] == 0, summary["log_text"]
    assert summary["total_consistency_warnings"] >= 1
    assert "disagree about which cells are missing" in summary["log_text"]


def test_a_hole_in_the_mask_is_not_mistaken_for_ice(case_dir):
    """Read undecoded, a fill value is 9.96921e+36 -- greater than zero.

    Taken at face value it would read as ice everywhere the mask is broken, and
    every variable of the domain would be accused of leaving ice outside it.
    The hole is reported against the mask's own file, where it belongs.
    """
    geometry = geometry_of(case_dir)
    set_where(dataset_for_variable(case_dir, "sftgif"),
              geometry["sftgif"] == 0.0, FILL)

    summary = run(case_dir)

    assert "has ice outside its own domain" not in summary["log_text"]
    assert "holds a value in" not in summary["log_text"]
    # The mask's own file still reports the hole, once.
    assert "sftgif' holds a fill value in" in summary["log_text"]


def test_masks_that_do_not_add_up_are_an_error(case_dir):
    """Every ice-covered part of a cell is either grounded or afloat.

    True by definition, which is what makes it worth checking: no geometry, no
    densities, no judgement, and it catches how the masks were built.
    """
    geometry = geometry_of(case_dir)
    set_where(dataset_for_variable(case_dir, "sftgrf"),
              geometry["sftgrf"] == 1.0, 0.5)

    summary = run(case_dir)

    assert "does not equal 'sftgif'" in summary["log_text"]
    assert summary["total_consistency_errors"] >= 1


def test_masks_within_rounding_of_each_other_are_accepted(case_dir):
    """float32 arithmetic must not be reported as a mask-building mistake."""
    geometry = geometry_of(case_dir)
    nudge = geometry["sftgrf"].copy()
    interior = geometry["sftgrf"] == 1.0
    nudge[interior] = 1.0 - 1.0e-7
    set_where(dataset_for_variable(case_dir, "sftgrf"), interior, 1.0 - 1.0e-7)

    summary = run(case_dir)

    assert "does not equal 'sftgif'" not in summary["log_text"]


def test_thickness_without_ice_is_reported(case_dir):
    """The check hgoelzer asked for, in the direction that says too much ice."""
    geometry = geometry_of(case_dir)
    set_where(dataset_for_variable(case_dir, "lithk"),
              geometry["sftgif"] == 0.0, 100.0)

    log = run(case_dir)["log_text"]

    assert "carries ice thickness in cells its own mask says hold no ice" in log


def test_ice_without_thickness_is_reported(case_dir):
    """And in the direction that says too little."""
    geometry = geometry_of(case_dir)
    set_where(dataset_for_variable(case_dir, "lithk"),
              geometry["sftgif"] > 0.0, 0.0)

    log = run(case_dir)["log_text"]

    assert "claims ice the thickness does not account for" in log


def test_a_hole_in_a_mask_is_not_read_as_a_thick_piece_of_ice(case_dir):
    """A fill value is finite and greater than zero when read undecoded.

    So a rule skipping only NaNs would take a hole in lithk for 9.96921e+36
    metres of ice, and report the mask for failing to account for it.
    """
    geometry = geometry_of(case_dir)
    set_where(dataset_for_variable(case_dir, "lithk"),
              geometry["sftgif"] == 0.0, FILL)

    log = run(case_dir)["log_text"]

    assert "carries ice thickness in cells its own mask says hold no ice" not in log
    assert "lithk' holds a fill value in" in log


def test_a_surface_that_is_not_base_plus_thickness_is_an_error(case_dir):
    """A pure identity, so a failure is a real contradiction and not a matter
    of degree. Checked in every cell, which is sound because the identity is
    linear and so survives cell-mean averaging."""
    geometry = geometry_of(case_dir)
    set_where(dataset_for_variable(case_dir, "orog"),
              geometry["sftgif"] >= 1.0, 0.0)

    summary = run(case_dir)

    assert "does not equal 'base' + 'lithk'" in summary["log_text"]
    assert summary["total_consistency_errors"] >= 1


def test_an_ice_base_below_the_bed_is_an_error(case_dir):
    """Impossible whatever the masks say, so it is checked everywhere."""
    geometry = geometry_of(case_dir)
    grounded = geometry["sftgrf"] == 1.0
    set_where(dataset_for_variable(case_dir, "base"), grounded,
              geometry["topg"][grounded] - 100.0)

    log = run(case_dir)["log_text"]

    assert "lies below 'topg'" in log
    assert "The ice base cannot be under the bed" in log


def test_grounded_ice_that_does_not_rest_on_the_bed_is_an_error(case_dir):
    """No densities needed: this is submitted geometry disagreeing with itself."""
    geometry = geometry_of(case_dir)
    grounded = geometry["sftgrf"] == 1.0
    set_where(dataset_for_variable(case_dir, "base"), grounded,
              geometry["topg"][grounded] + 50.0)

    log = run(case_dir)["log_text"]

    assert "that 'sftgrf' says are wholly grounded" in log


def test_floating_ice_that_rests_on_the_bed_is_an_error(case_dir):
    """The other half of the same comparison."""
    geometry = geometry_of(case_dir)
    floating = geometry["sftflf"] == 1.0
    set_where(dataset_for_variable(case_dir, "base"), floating,
              geometry["topg"][floating])

    log = run(case_dir)["log_text"]

    assert "that 'sftflf' says are wholly floating" in log


def test_a_partly_grounded_cell_is_left_alone(case_dir):
    """In a half-and-half cell the mean ice base sits somewhere between the bed
    and the flotation level, and nothing follows from where exactly. Only
    wholly grounded and wholly floating cells are compared."""
    geometry = geometry_of(case_dir)
    partial = np.logical_and(
        geometry["sftflf"] > 0.0, geometry["sftflf"] < 1.0
    )
    assert partial.any(), "the synthetic ice sheet should have partial cells"
    set_where(dataset_for_variable(case_dir, "base"), partial,
              geometry["topg"][partial] + 1.0)

    log = run(case_dir)["log_text"]

    assert "wholly grounded" not in log
    assert "wholly floating" not in log


@pytest.mark.parametrize(
    "value, expected",
    [("warning", "warning"), ("error", "error"), (None, "error"),
     ("nonsense", "error")],
)
def test_margin_severity_defaults_to_error(value, expected):
    assert checker._margin_severity(value) == expected


def test_the_variables_on_trial_are_the_ones_that_meet_the_margin():
    """Only the rules that compare against a mask cell by cell are on trial.

    Everything else ships as an error, so a promotion later is a one-cell diff
    to the request rather than a change of heart about a rule.
    """
    ismip_meta, _, _, _, _ = checker._load_criteria("ismip7")
    on_trial = {
        entry["variable"] for entry in ismip_meta
        if entry["margin_severity"] == "warning"
    }

    assert on_trial == {
        "xvelsurf", "yvelsurf", "zvelsurf", "xvelbase", "yvelbase", "zvelbase",
        "xvelmean", "yvelmean", "strbasemag", "litemptop", "litempavg",
        "litemp", "litempbotgr", "libmassbfgr", "litempbotfl", "libmassbffl",
        "lithk",
    }
