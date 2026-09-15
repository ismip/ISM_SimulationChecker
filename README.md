# Ice Sheet Simulation Compliance Checker

Checks ISMIP7 NetCDF model output against the
[ISMIP7 data request](https://www.ismip.org/), so that a submission can be
corrected before it is archived rather than after. Point it at a directory of
files and it writes a log saying, file by file, what is wrong and how serious
it is.

**Documentation: <https://ismip.github.io/ISM_SimulationChecker/>**

## Install and run

```bash
conda create -n isschecker -c conda-forge isschecker
conda activate isschecker
ismip7-compliance-checker \
    --source-path Models/GrIS/VUW/PISM1/CORE/C001 \
    --variable-list ismip7
```

The source path is one set counter directory: the one holding the .nc files
for a model's C001 (or E003, P012, ...) runs. The variable list says which
files to look for: `ismip7_xyt` for the gridded variables, `ismip7_scalars`
for the time series, `ismip7` for both.

Findings are printed as the checker runs and written to
compliance_checker_log.txt beside the files, or under `--output-path` if the
files are somewhere you cannot write. An **error** means the file cannot be
used as submitted. A **warning** means it is usable but departs from what was
asked for. Only errors make the command exit non-zero, so it can be run from
a script.

## Where to read more

| | |
|---|---|
| [Getting started](https://ismip.github.io/ISM_SimulationChecker/getting-started.html) | install, lay out the files, run the checker, read the log |
| [Running the checker](https://ismip.github.io/ISM_SimulationChecker/user/running.html) | every option |
| [What the checker checks](https://ismip.github.io/ISM_SimulationChecker/user/checks.html) | the six categories |
| [Errors and warnings](https://ismip.github.io/ISM_SimulationChecker/user/errors-and-warnings.html) | what each severity means, and the warnings you can quiet |
| [Time encoding](https://ismip.github.io/ISM_SimulationChecker/user/time-encoding.html) | the timestamps and bounds each variable type needs |
| [The data request](https://ismip.github.io/ISM_SimulationChecker/user/data-request.html) | units, value ranges and experiments, variable by variable |
| [Developer guide](https://ismip.github.io/ISM_SimulationChecker/dev/index.html) | source install, test files, tests, releases |

## Contributing

Problems and questions go in
[the issue tracker](https://github.com/ismip/ISM_SimulationChecker/issues).
Pull requests are welcome; the
[developer guide](https://ismip.github.io/ISM_SimulationChecker/dev/index.html)
covers the source install, the tests and the release process.

Distributed under the MIT License; see [LICENSE](LICENSE).
