"""Compare the checker's log against a stored reference.

The log file is what the checker actually delivers, so this is the test that
makes "everyone gets the same answer from the same files" checkable rather than
merely intended: it fails on any change in log text, whether that change comes
from us or from a dependency release inside the supported version ranges.  In
CI it runs against both the floor and the latest environment, so a difference
between them shows up as a failure here.

It relies on the generator being seeded, so the input data is fixed too.

There are two references, because a submission of mandatory variables alone
does not reach every check.  litemp -- the data request's only x,y,z,t variable,
and so the only one whose sparse snapshot axis the time checks look at -- is not
mandatory, and neither is the static x,y refgeoid.  The second reference covers
them.

To adopt a change in the log as the new expected output, inspect the diff the
failure prints, then regenerate the references:

    ISSCHECKER_UPDATE_GOLDEN_LOG=1 pytest tests/test_golden_log.py

and commit the updated references alongside the change that caused them.
"""

import difflib
import os
import re
from pathlib import Path

import pytest

from isschecker import checker
from isschecker import generate as generate_test_files

REFERENCE_DIR = Path(__file__).parent / "reference"

# The submissions the references cover: what the generator writes, and where the
# expected log for it is stored.
GOLDEN_CASES = {
    "mandatory": ("compliance_checker_log.txt", False),
    "non_mandatory": ("compliance_checker_log_non_mandatory.txt", True),
}

# Fixed so that the log is reproducible.
GRID_NAME = "GrIS_16000m"
SCENARIO = "historical"
START_YEAR = 2013
NYEARS = 2
SEED = 0
VARIABLE_LIST = "ismip7"
VERSION = "tests"

# Which checker ran, when it ran, and where the data sat: all expected to
# differ between runs and machines, none of them a regression.
VOLATILE_LINES = (
    (re.compile(r"^isschecker version: .*$", re.MULTILINE), "isschecker version: <masked>"),
    (re.compile(r"^date: .*$", re.MULTILINE), "date: <masked>"),
)


def _mask_volatile(text: str, source_path: str) -> str:
    """Replace the parts of a log that are expected to vary between runs.

    The reference is stored in this masked form, so `<masked>` and
    `<source-path>` appear in it literally and masking it again is a no-op.
    """
    for pattern, replacement in VOLATILE_LINES:
        text = pattern.sub(replacement, text)
    return text.replace(source_path, "<source-path>")


@pytest.fixture(scope="module", params=sorted(GOLDEN_CASES))
def golden_case(request, tmp_path_factory) -> tuple[Path, str]:
    """The reference log for one submission, and the log this run produced."""
    reference_name, include_non_mandatory = GOLDEN_CASES[request.param]

    output_root = tmp_path_factory.mktemp(f"golden_log_data_{request.param}")
    created_files = generate_test_files.create_netcdf_file(
        None,
        grid_name=GRID_NAME,
        scenario=SCENARIO,
        start_year=START_YEAR,
        nyears=NYEARS,
        include_scalars=True,
        include_xyt=True,
        include_non_mandatory=include_non_mandatory,
        output_root=output_root,
        seed=SEED,
    )
    assert created_files, "Synthetic generation did not create any files."

    core_dir = output_root / "GrIS" / "ISMIP7" / "SYNTH1" / "CORE" / "C001"
    summary = checker.run_checker(
        source_path=str(core_dir),
        variable_list=VARIABLE_LIST,
        version=VERSION,
    )
    return (
        REFERENCE_DIR / reference_name,
        _mask_volatile(summary["log_text"], str(core_dir)),
    )


def test_log_matches_reference(golden_case):
    reference_log, generated_log = golden_case

    if os.environ.get("ISSCHECKER_UPDATE_GOLDEN_LOG"):
        reference_log.parent.mkdir(parents=True, exist_ok=True)
        reference_log.write_text(generated_log)
        pytest.skip(f"Wrote a new reference log to {reference_log}")

    assert reference_log.exists(), (
        f"No reference log at {reference_log}. Create one with "
        "ISSCHECKER_UPDATE_GOLDEN_LOG=1 pytest tests/test_golden_log.py"
    )

    expected = reference_log.read_text().splitlines(keepends=True)
    actual = generated_log.splitlines(keepends=True)

    if actual != expected:
        diff = "".join(
            difflib.unified_diff(
                expected, actual, fromfile="reference log", tofile="this run"
            )
        )
        pytest.fail(
            "The checker's log differs from the stored reference. If the change "
            "is intended, regenerate the reference with "
            "ISSCHECKER_UPDATE_GOLDEN_LOG=1.\n\n" + diff
        )
