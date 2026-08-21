"""The synthetic ice sheet, and the promises the cross-file checks rest on.

Drawing every variable from its own uniform distribution is enough while each
file is checked alone.  It is not enough for a check that compares two files: a
random thickness and a random mask do not agree about where the ice is, and a
random velocity is defined everywhere, which is what the data request forbids.
So the generator has a geometry, and these are the properties of it that the
checks are entitled to assume -- stated here rather than left to be rediscovered
when a rule mysteriously passes on data that could never have failed it.
"""

import netCDF4
import numpy as np
import pytest
import xarray as xr

from isschecker import generate

# Two grids of quite different aspect ratio, because the geometry is laid out
# relative to the shorter side and a square grid would not show that up.
GRIDS = {
    "GrIS": (np.arange(-720000.0, 960001.0, 16000.0),
             np.arange(-3450000.0, -569999.0, 16000.0)),
    "AIS": (np.arange(-3040000.0, 3040001.0, 32000.0),
            np.arange(-3040000.0, 3040001.0, 32000.0)),
}


@pytest.fixture(params=sorted(GRIDS))
def geometry(request):
    return generate.ice_sheet_geometry(*GRIDS[request.param])


def test_thickness_and_ice_mask_agree(geometry):
    """`lithk > 0` exactly where `sftgif > 0`, with nothing in between."""
    assert ((geometry["lithk"] > 0.0) == (geometry["sftgif"] > 0.0)).all()


def test_the_masks_partition_the_ice(geometry):
    """Grounded fraction plus floating fraction is the ice fraction, exactly."""
    total = geometry["sftgrf"] + geometry["sftflf"]
    assert np.array_equal(total, geometry["sftgif"])
    for name in ("sftgif", "sftgrf", "sftflf"):
        assert geometry[name].min() >= 0.0 and geometry[name].max() <= 1.0


def test_surface_is_base_plus_thickness(geometry):
    """The identity holds exactly, not to a tolerance."""
    assert np.array_equal(geometry["orog"], geometry["base"] + geometry["lithk"])


def test_the_ice_base_never_lies_below_the_bed(geometry):
    assert (geometry["base"] >= geometry["topg"]).all()


def test_grounded_ice_rests_on_the_bed_and_floating_ice_does_not(geometry):
    grounded = geometry["sftgrf"] == 1.0
    floating = geometry["sftflf"] == 1.0
    assert np.array_equal(
        geometry["base"][grounded], geometry["topg"][grounded]
    )
    assert (geometry["base"][floating] > geometry["topg"][floating]).all()


def test_all_the_ice_is_inside_the_computational_domain(geometry):
    """Otherwise the domain-covers-ice rule would fail on our own test data."""
    assert not (geometry["sftgif"] > 0.0)[~geometry["domain"]].any()


def test_every_region_holds_some_cells(geometry):
    """A region that came out empty would make its variables entirely missing.

    The checker reports that as an error of its own, so an empty floating ring
    would not merely leave a rule untested -- it would break the baseline.
    """
    assert geometry["domain"].sum() > 0
    assert (geometry["sftgif"] > 0.0).sum() > 0
    assert (geometry["sftgrf"] == 1.0).sum() > 0
    assert (geometry["sftflf"] == 1.0).sum() > 0
    assert (geometry["sftgif"] == 0.0).sum() > 0


def test_the_margin_holds_partly_glaciated_cells(geometry):
    """Conservative interpolation produces these, and the request allows them."""
    fraction = geometry["sftgif"]
    assert np.logical_and(fraction > 0.0, fraction < 1.0).any()


@pytest.mark.parametrize(
    "fill_policy, field, absent",
    [
        ("outside_domain", "domain", False),
        ("no_ice", "sftgif", True),
        ("no_grounded_ice", "sftgrf", True),
        ("no_floating_ice", "sftflf", True),
    ],
)
def test_missing_where_follows_the_policy(geometry, fill_policy, field, absent):
    missing = generate.missing_where(fill_policy, geometry)
    expected = (geometry[field] == 0.0) if absent else ~geometry["domain"]
    assert np.array_equal(missing, expected)


def test_a_variable_the_request_does_not_constrain_is_missing_nowhere(geometry):
    assert generate.missing_where("forbidden", geometry) is None
    assert generate.missing_where(None, geometry) is None


def test_generated_files_are_missing_exactly_where_their_policy_says(tmp_path):
    """The end of the chain: what actually lands in the files on disk."""
    created = generate.create_netcdf_file(
        None,
        grid_name="GrIS_16000m",
        scenario="historical",
        start_year=2013,
        nyears=2,
        include_scalars=False,
        include_xyt=True,
        include_non_mandatory=True,
        output_root=tmp_path,
    )
    assert created

    core_dir = tmp_path / "GrIS" / "ISMIP7" / "SYNTH1" / "CORE" / "C001"
    fill = netCDF4.default_fillvals["f4"]

    def read(variable_name):
        path = sorted(core_dir.glob(f"{variable_name}_*.nc"))[0]
        with xr.open_dataset(
            path, decode_times=False, mask_and_scale=False
        ) as dataset:
            return dataset[variable_name].values, dataset["x"].values, dataset["y"].values

    _, x, y = read("lithk")
    geometry = generate.ice_sheet_geometry(x, y)

    expected_missing = {
        "lithk": np.zeros_like(geometry["domain"]),
        "sftgif": np.zeros_like(geometry["domain"]),
        "topg": ~geometry["domain"],
        "orog": ~geometry["domain"],
        "xvelmean": geometry["sftgif"] == 0.0,
        "libmassbfgr": geometry["sftgrf"] == 0.0,
        "libmassbffl": geometry["sftflf"] == 0.0,
    }
    for variable_name, expected in expected_missing.items():
        values, _, _ = read(variable_name)
        missing = values == fill
        assert np.array_equal(
            missing, np.broadcast_to(expected, missing.shape)
        ), variable_name
