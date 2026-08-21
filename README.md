# Ice Sheet Simulation Compliance Checker

Checks ISMIP7 NetCDF simulation datasets for compliance with the
[ISMIP7 data request conventions](https://www.ismip.org/), so that a submission
can be corrected before it is archived rather than after. Point it at a
directory of files and it writes a log saying, file by file, what is wrong and
how serious it is.

**Documentation: <https://ismip.github.io/ISM_SimulationChecker/>**

## Install and run

```bash
conda create -n isschecker -c conda-forge isschecker
conda activate isschecker
ismip7-compliance-checker \
    --source-path ./Models/GrIS/ISMIP7/SYNTH1/CORE/C001 \
    --variable-list ismip7
```

`--variable-list` is `ismip7_xyt` for the gridded variables, `ismip7_scalars`
for the time-only ones, or `ismip7` for both. Findings are printed and written
to `compliance_checker_log.txt` in the `--source-path` directory. The checker
exits non-zero if it found errors, so it can be run from a script.

## What is checked

Every file is validated in five categories — naming, numerical values, spatial
grid, time axis, and attributes — against criteria that live in the data
request files bundled with the package,
`isschecker/data/ISMIP7_variable_request.csv` and
`isschecker/data/experiments_ismip7.csv`. Findings come at two severities:
an **error** means the file cannot be used as submitted, a **warning** means it
is usable but departs from what was asked for. Only errors change the exit
status.

## Where to read more

| | |
|---|---|
| [Getting started](https://ismip.github.io/ISM_SimulationChecker/getting-started.html) | install the checker, run it, and read the log |
| [What the checker checks](https://ismip.github.io/ISM_SimulationChecker/user/checks.html) | the five categories, in detail |
| [Errors and warnings](https://ismip.github.io/ISM_SimulationChecker/user/errors-and-warnings.html) | what each severity means, and the warnings you can quiet |
| [Time encoding](https://ismip.github.io/ISM_SimulationChecker/user/time-encoding.html) | the timestamps and bounds each variable type needs |
| [The data request](https://ismip.github.io/ISM_SimulationChecker/user/data-request.html) | units, value ranges and experiments, variable by variable |
| [Developer guide](https://ismip.github.io/ISM_SimulationChecker/dev/index.html) | install from source, generate test files, run the tests, cut a release |

The pages are built from the `docs/` directory of this repository; see
[Building the documentation](https://ismip.github.io/ISM_SimulationChecker/dev/building-docs.html)
to build them locally.

## Contributing

Problems and questions belong in
[the issue tracker](https://github.com/ismip/ISM_SimulationChecker/issues).
Pull requests are welcome; the
[developer guide](https://ismip.github.io/ISM_SimulationChecker/dev/index.html)
covers the source install, the test suite and the release process.

Distributed under the MIT License; see [LICENSE](LICENSE).
