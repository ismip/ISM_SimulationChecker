# Running the tests

The regression suite uses `pytest` and creates temporary synthetic datasets,
then mutates them to verify expected checker failures for naming, missing and
misnamed variables, wrong variable dimensions, time-axis problems, and missing
attributes. It imports `isschecker`, so install the package first (see
{doc}`source-install`); the tests then exercise what is actually installed and
can be run from any directory.

Run the suite against the source install you are developing in: run against a
conda-forge install and you are testing the last release with the working
tree's tests, which disagree whenever the working tree has changed anything the
tests look at.

```bash
pytest -v tests/test_compliance_checker.py
```

If you want to retain the files generated during testing you can use:

```bash
pytest -v tests/test_compliance_checker.py --basetemp=/tmp/pytest_tmp
```

The files will then be left in `/tmp/pytest_tmp`. Otherwise, they are cleaned
up once tests pass.

## The reference log

`tests/test_golden_log.py` runs the checker over a fixed, seeded dataset and
compares the resulting log line by line against
`tests/reference/compliance_checker_log.txt`, with the version, date, and
source path masked out. It is what turns "results should agree across machines"
into something CI can check: any difference in log text fails the test, whether
it comes from a change of ours or from a dependency release inside the
supported version ranges.

When a change to the checker is *meant* to change the log, read the diff the
failure prints, then regenerate the reference and commit it alongside the
change:

```bash
ISSCHECKER_UPDATE_GOLDEN_LOG=1 pytest tests/test_golden_log.py
```

## What CI runs

`.github/workflows/pytest.yml` builds the environment two ways — the ranges in
`isschecker_env.yml` solved fresh, and every floor in it pinned exactly by
`ci/isschecker_env_floor.yml` — on both Linux and macOS, installs the package
with the same pip flags the docs give developers, and runs the whole suite from
outside the checkout so that a data file or entry point missing from the wheel
fails there rather than passing against the source tree.
