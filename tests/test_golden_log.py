"""Compare the checker's log against a stored reference.

The log file is what the checker actually delivers, so this is the test that
makes "everyone gets the same answer from the same files" checkable rather than
merely intended: it fails on any change in log text, whether that change comes
from us or from a dependency release inside the supported version ranges.  In
CI it runs against both the floor and the latest environment, so a difference
between them shows up as a failure here.

It relies on the generator being seeded, so the input data is fixed too.

To adopt a change in the log as the new expected output, inspect the diff the
failure prints, then regenerate the reference:

    ISSCHECKER_UPDATE_GOLDEN_LOG=1 pytest tests/test_golden_log.py

and commit the updated reference alongside the change that caused it.
"""

import difflib
import os
import re
from pathlib import Path

import pytest

from isschecker import checker
from isschecker import generate as generate_test_files

REFERENCE_LOG = Path(__file__).parent / "reference" / "compliance_checker_log.txt"

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


@pytest.fixture(scope="module")
def generated_log(tmp_path_factory) -> str:
    """Return the log of a checker run over a fixed synthetic dataset, masked."""
    output_root = tmp_path_factory.mktemp("golden_log_data")
    created_files = generate_test_files.create_netcdf_file(
        None,
        grid_name=GRID_NAME,
        scenario=SCENARIO,
        start_year=START_YEAR,
        nyears=NYEARS,
        include_scalars=True,
        include_xyt=True,
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
    return _mask_volatile(summary["log_text"], str(core_dir))


def test_log_matches_reference(generated_log):
    if os.environ.get("ISSCHECKER_UPDATE_GOLDEN_LOG"):
        REFERENCE_LOG.parent.mkdir(parents=True, exist_ok=True)
        REFERENCE_LOG.write_text(generated_log)
        pytest.skip(f"Wrote a new reference log to {REFERENCE_LOG}")

    assert REFERENCE_LOG.exists(), (
        f"No reference log at {REFERENCE_LOG}. Create one with "
        "ISSCHECKER_UPDATE_GOLDEN_LOG=1 pytest tests/test_golden_log.py"
    )

    expected = REFERENCE_LOG.read_text().splitlines(keepends=True)
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
