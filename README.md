# Ice Sheet Simulation Compliance Checker

Checks ISMIP7 NetCDF simulation datasets for compliance with the [ISMIP7 data request conventions](https://www.ismip.org/). The following categories are validated for every file:

1. **Naming** — variable name, region field, ISM member id (`mNNN`), ESM name (CMIP6/CMIP7 registry), forcing member id (`fNNN`), set counter (`[C|E|P]NNN`), and year range (well formed `YYYY-YYYY`; what the range *means* is checked under **Time**). Inside the file: the variable the file name names is the one the file contains, with the dimensions the data request asks for, in the conventional `(time, z, y, x)` order, and the file holds nothing else beyond its coordinates and the companion variables CF lets them name (`bounds`, `grid_mapping`, `coordinates`, `cell_measures`, `ancillary_variables`) — anything further is a warning.
2. **Numerical** — units match the data request, in any UDUNITS spelling (`m2`, `m^2` and `m**2` are all accepted, as are `kg m-2 s-1`, `kg.m-2.s-1` and `kg/m2/s`); all values lie within the allowed min/max range for the relevant region; array is not entirely fill values.
3. **Spatial** *(xyt variables only)* — grid corners lie within the expected AIS or GrIS extents; resolution is one of the allowed values; x and y cell size are equal.
4. **Time** — time dimension is present, unlimited, and monotonically increasing; the file name's year range is one the experiment allows; and the time axis is **exactly** the axis the experiment calls for. For `x,y,t` and `t` variables that means every nominal year from `experiments_ismip7.csv`, each carrying the timestamp its ST/FL convention prescribes; for `x,y,z,t` variables it means the required set of sparse snapshots (see [Time encoding](#time-encoding)).
5. **Attributes** — required global and coordinate attributes are present and have correct values; `standard_name` matches data request; `_FillValue` equals the NetCDF4 default for the variable's dtype; the variable is float32, and so is the time coordinate (a warning — one number per record cannot inflate a file); `scale_factor` and `add_offset` are not allowed.

Every file is checked as far as it can be. A naming problem stops the other checks only where it leaves them nothing to read — a missing `x` or `y` dimension, or a file that does not contain the variable its name promises. Everything else (a mistyped ESM name, a malformed year range, an unrecognised region) is reported and the file is checked on, so one run tells you everything that is wrong rather than only the first thing. An unrecognised region costs just the checks that depend on it: value range, grid extent and resolution, and `crs`.

Compliance criteria are defined in `isschecker/data/ISMIP7_variable_request.csv` (variable metadata) and `isschecker/data/experiments_ismip7.csv` (valid experiment year ranges and durations). Together with the grid definitions in `isschecker/data/gdfs/`, these files are bundled with the package.

---

## Errors and warnings

Findings come at two severities, and the difference is worth stating precisely, because a check that reports at the wrong one either fails a submission that is fine or waves through one that is not.

**ERROR** — the file, as written, is unusable for the intended analysis, departs from the protocol in a way that changes the science, or fails the data-hygiene requirements this archive is committing to. That last clause is deliberate: the output will be served to the broader community for analysis for years, so uniformity of encoding is a product requirement rather than a stylistic preference, and "a reader could cope with it" is not grounds for a warning.

**WARNING** — the file is usable, the science is unaffected, and nothing downstream has to work around it, but it departs from what the data request asked for in a way you should look at and may reasonably have intended.

Three consequences follow, and they are what make a warning safe to leave alone:

- Warnings never enter the error count and never change a file's verdict. A file with warnings and no errors is compliant, and the log says so: `No errors. Good job !`, followed by the number of warnings to review.
- Warnings never affect the exit status. Errors do.
- A check whose failure means the checker could not read something is always an error. A warning never stops any later check from running.

The synthesis block at the top of the log counts both severities, broken down by the same categories.

### Variables your model does not represent

An experiment that carries no files for a non-mandatory variable gets one warning naming all of them. This is expected if your model does not represent those variables — GIA is the obvious case — and it is listed only so that a variable lost from a submission does not pass unnoticed. It is scoped to the `--variable-list` you selected, so a run over `ismip7_scalars` says nothing about the `x,y,t` variables it was never asked to look at.

To make that warning go quiet, put an optional `not_modelled.txt` in the `--source-path` directory: one variable name per line, blank lines ignored and `#` starting a comment, so you can record alongside each name why the variable is absent.

```
# ISMIP7: variables this model does not represent.
dlithkdt      # no GIA in this configuration
litemp
```

Two rules keep the file from becoming a way to hide problems, and both are errors rather than silent no-ops:

- A **mandatory** variable named in it is still a missing-mandatory error, and the claim itself is reported as a further error. The list is a statement about optional variables; a submission cannot opt out of the data request with it.
- A name that is **not in the data request** at all is an error. It is either a typo or a misunderstanding, and both are better said plainly than left to be inferred from a warning that did not go away.

Whatever the file declares is echoed into the log, so the archived record of a run shows what was claimed rather than merely that a warning did not appear. If the file is absent, nothing changes.

### Value ranges

Some of the `min_value_*` / `max_value_*` bounds in the data request "are dependent on the forcing, input data and model implementation" ([issue #10](https://github.com/ismip/ISM_SimulationChecker/issues/10)), and some are not, so the severity of an out-of-range value is a per-variable question. It is answered by the `range_severity` column of `ISMIP7_variable_request.csv`, which holds `error` or `warning` for each variable row. Anything the column does not say — a blank cell, an unrecognised value, or the column being absent altogether — means `error`.

Every shipped row is currently `error`, so this changes nothing today. Moving a variable to `warning` is a one-cell change to the data request that needs no reasoning about the checker.

---

## Time encoding

ISMIP7 uses the standard (Gregorian) CF calendar with time recorded as **days since 1850-01-01 00:00:00**. The encoding convention differs by variable type:

| Variable type | Time coordinate | Time bounds |
|---|---|---|
| **State (ST)** — snapshots | Jan 1 of year N+1 (= end of year N) | none |
| **Flux (FL)** — annual averages | Jul 1 of year N (mid-year) | Jan 1 of year N → Jan 1 of year N+1 |

For example, a 286-year `ctrl` simulation covering nominal years 2015–2300:
- ST files carry timestamps `2016-01-01` … `2301-01-01`
- FL files carry timestamps `2015-07-01` … `2300-07-01`, with bounds `[2015-01-01, 2016-01-01]` … `[2300-01-01, 2301-01-01]`

The filename year range (`YYYY-YYYY`) always refers to the **nominal simulation years** (2015–2300 in the example above), regardless of variable type. The checker accounts for this when validating the filename against the time axis.

### Snapshot variables (`x,y,z,t`, e.g. `litemp`)

`x,y,z,t` variables carry a sparse set of ST snapshots rather than a full annual time series. The required snapshot nominal years depend on the experiment type:

| Experiment | Required snapshots |
|---|---|
| `historical` | first year of run, 1900 (if in range), last year of run (2014) |
| projection (e.g. `ssp585`, `ctrl`) | 2100, 2200, 2300 (each if within the experiment's year range) |

Together, a `historical` run and a projection provide snapshots at 1900, 2014, 2100, 2200 and 2300, plus the first year of the historical run. The first year is required only for `historical`, whose start year the modeller chooses; a projection's initial state is the historical run's final state, already reported as historical's last-year snapshot.

A **missing** required snapshot is an error. A snapshot the experiment does not call for is a **warning**: the data request specifies these years as a minimum set, so over-delivering 3D temperature is not non-compliance, but a year nobody asked for is usually a sign that something was written by mistake. (The annual time axis is treated the other way round — an extra year there is an error — because that axis is pinned end to end by `experiments_ismip7.csv`, so an extra year means the file does not match the experiment it names.)

The filename year range for `litemp` reflects the full simulation year range (e.g. `2015-2300`), not the first/last snapshot year, and the annual cadence checks do not apply.

> **A snapshot at 2000 is not required.** Earlier versions of this README, the checker and the generator all required one; `ISMIP7_variable_request.csv` does not ask for one. A file carrying one is reported as an unrequested snapshot — that is, warned about and not failed — until [issue #12](https://github.com/ismip/ISM_SimulationChecker/issues/12) settles it. Files written to the earlier guidance still pass.

Reference lookup tables are available in the companion repository [`ismip7-time-encoding`](https://github.com/ismip/ismip7-time-encoding).

---

## Installation

The checker is packaged on [conda-forge](https://anaconda.org/conda-forge/isschecker), and that is how you should install it. Nothing is built, no dependency has to be picked by hand, and there is no need to clone this repository at all:

```bash
conda create -n isschecker -c conda-forge isschecker
conda activate isschecker
```

`mamba` and `micromamba` work the same way; substitute either for `conda` if you prefer. If your conda is configured with the `defaults` channel, add `--override-channels` so a package cannot be pulled from it: builds from the two channels are not interchangeable, and mixing them is a good way for two people to get different results from the same files.

The package registers the `ismip7-compliance-checker` and `ismip7-generate-test-files` commands and bundles the data files, so the checker can be run from any directory. Confirm the installation with:

```bash
ismip7-compliance-checker --version
```

To move to a newer release later:

```bash
conda activate isschecker
conda update -c conda-forge isschecker
```

The conda-forge package is built from the tagged releases of this repository, so it can be behind `main` by a release; `--version` always reports the one you actually have. See [Releasing](#releasing) for when a tag is cut.

### Installing from source

You only need this to work *on* the checker — to test a change that has not been released yet, or to develop one. For checking a submission, install from conda-forge instead.

Create the conda environment and install the package into it:

```bash
conda env create -f isschecker_env.yml
conda activate isschecker
python -m pip install --no-deps --no-build-isolation .
```

Note that `isschecker_env.yml` installs the dependencies but not the checker itself, so the environment it creates is not the one above: an `isschecker` environment made this way holds no `isschecker` package until the `pip install` runs. If you already have an environment of that name from conda-forge, `conda env create` will refuse to create another over it; give this one a different name with `conda env create -n isschecker-dev -f isschecker_env.yml` and keep both.

**Use those pip flags.** All dependencies come from conda-forge, and a plain `pip install .` can silently replace them with PyPI wheels — `netCDF4` in particular bundles its own copy of the netCDF C library — which is exactly how two people end up with different results from the same files. `--no-deps` keeps pip from resolving anything, and `--no-build-isolation` builds with the environment's `setuptools` instead of downloading one from PyPI. Add `--no-index` if you want any accidental network fetch to fail loudly rather than succeed quietly.

For development, add `-e` for an editable install:

```bash
python -m pip install --no-deps --no-build-isolation -e .
```

(`pytest` comes from the conda environment, so the `[test]` extra is not needed.) An editable install is worth having while developing, because the tests import the installed package: after a non-editable install, edits to the source tree do not affect a test run until you reinstall.

If a rebuild ever behaves as though it were still running older code, delete the `build/` directory: `setuptools` reuses its contents, so files that have since been renamed or removed can otherwise end up back in the installed package.

### Dependencies

Installing from conda-forge pulls these in for you, and you can skip this section. It matters when you install from source, where the environment is yours to create.

Versions are constrained in `isschecker_env.yml`; the same constraints appear in `pyproject.toml`. The suite is tested at both ends of every range, so results should agree across machines and operating systems within these bounds.

| Package | Constraint | Why bounded |
|---|---|---|
| `python` | `>=3.11,<3.15` | `str \| None` annotations need ≥3.10; 3.10 is EOL in Oct 2026 |
| `numpy` | `>=2.1,<3` | what recent `pandas`/`xarray` are built against |
| `pandas` | `>=2.2,<4` | reads the criteria CSVs; 3.0 changed the default string dtype |
| `xarray` | `>=2025.1.2,<2027` | `xarray.coders.CFDatetimeCoder` (public API in 2025.1.1) and non-nanosecond datetime decoding, both used by the time checks |
| `cftime` | `>=1.6.4,<2` | date arithmetic in the start/end/duration checks |
| `netCDF4` | `>=1.7,<2` | `_FillValue` checks compare against `netCDF4.default_fillvals` |
| `tqdm` | `>=4.66` | progress bar only; never affects the log |

If you report a problem with the checker, please include the output of `conda list` for your `isschecker` environment.

---

## Running the checker

Once installed, run the checker from any directory with the `ismip7-compliance-checker` command (equivalently, `python -m isschecker`). It writes `compliance_checker_log.txt` into the `--source-path` directory.

```bash
# Check x,y,t (3D spatial) variables
ismip7-compliance-checker --source-path ./Models/GrIS/ISMIP7/SYNTH1/CORE/C001 --variable-list ismip7_xyt

# Check scalar (time-only) variables
ismip7-compliance-checker --source-path ./Models/AIS/ISMIP7/SYNTH1/CORE/C001 --variable-list ismip7_scalars

# Check both
ismip7-compliance-checker --source-path ./Models/GrIS/ISMIP7/SYNTH1/CORE/C001 --variable-list ismip7
```

| Option | Default | Description |
|--------|---------|-------------|
| `--source-path` | `./Models/GrIS/ISMIP7/SYNTH1/CORE/C001` | Set-counter subdirectory containing `.nc` files to check |
| `--variable-list` | `ismip7_scalars` | `ismip7_xyt`, `ismip7_scalars`, or `ismip7` (both) |
| `--version` | — | Print the installed version and exit; quote it when reporting a problem |

`experiments_ismip7.csv` defines the allowed nominal year ranges and durations for each experiment. The checker derives the expected FL and ST timestamps from these year values at runtime (see [Time encoding](#time-encoding)).

### Exit status

The checker exits **non-zero** when it found errors, or when it could not check anything at all — the `--source-path` does not exist, or holds no `.nc` files. It exits **zero** when the submission is compliant, including when there are warnings to review; see [Errors and warnings](#errors-and-warnings). Both `ismip7-compliance-checker` and `python -m isschecker` behave the same way, so either can be used in a script.

---

## Generating synthetic test files

The `ismip7-generate-test-files` command creates ISMIP7-style NetCDF test files with synthetic data, under `Models/` in the current directory. See [docs/generating_test_files.md](docs/generating_test_files.md) for full options and examples.

```bash
conda activate isschecker

# Generate 286-year GrIS ctrl xyt variables
ismip7-generate-test-files --grid GrIS_16000m --scenario ctrl --xyt --nyears 286 --start-year 2015

# Generate 286-year AIS ctrl scalar variables
ismip7-generate-test-files --grid AIS_16000m --scenario ctrl --scalars --nyears 286 --start-year 2015

# List available grids
ismip7-generate-test-files --list-grids
```

---

## Running Tests

The regression suite uses `pytest` and creates temporary synthetic datasets, then mutates them to verify expected checker failures for naming, missing and misnamed variables, wrong variable dimensions, time-axis problems, and missing attributes. It imports `isschecker`, so install the package first (see [Installing from source](#installing-from-source)); the tests then exercise what is actually installed and can be run from any directory. Run the suite against the source install you are developing in: run against a conda-forge install and you are testing the last release with the working tree's tests, which disagree whenever the working tree has changed anything the tests look at.

```bash
pytest -v tests/test_compliance_checker.py
```

If you want to retain the files generated during testing you can use:
```
pytest -v tests/test_compliance_checker.py --basetemp=/tmp/pytest_tmp
```
The files will then be left in `/tmp/pytest_tmp`.  Otherwise, they are cleaned up once tests pass.

### The reference log

`tests/test_golden_log.py` runs the checker over a fixed, seeded dataset and compares the resulting log line by line against `tests/reference/compliance_checker_log.txt`, with the version, date, and source path masked out. It is what turns "results should agree across machines" into something CI can check: any difference in log text fails the test, whether it comes from a change of ours or from a dependency release inside the supported version ranges.

When a change to the checker is *meant* to change the log, read the diff the failure prints, then regenerate the reference and commit it alongside the change:

```bash
ISSCHECKER_UPDATE_GOLDEN_LOG=1 pytest tests/test_golden_log.py
```

---

## Releasing

This section is for maintainers — those with write access to [the main repository](https://github.com/ismip/ISM_SimulationChecker). If you are contributing from a fork, nothing here is yours to do; open the pull request and a maintainer will fold it into the next release.

Modellers get the checker from conda-forge, and conda-forge builds from a tag. Anything on `main` that has not been tagged therefore does not exist as far as they are concerned: a check you added, a message you reworded, a variable you renamed in `ISMIP7_variable_request.csv` — all of it sits in this repository being invisible to everyone running the tool.

**So tag a release whenever a change reaches `main` that a user would notice.** That is the rule, and it is deliberately a low bar: new or changed checks, a change in a finding's severity or wording, a change to the bundled data request or grid definitions, a new or altered command-line option, a bug fix, or a widened dependency range. Releases are cheap; a user chasing a discrepancy against a source checkout that turns out to be six months of untagged changes is not. Refactorings, tests, CI and documentation-only changes need no release, though there is no harm in folding them into the next one.

To cut a release:

1. Bump `version` in `pyproject.toml` following [semantic versioning](https://semver.org/) — patch for a fix, minor for a new or changed check, major for a change that would fail a submission that used to pass — and merge that to `main`.
2. Draft a new [GitHub release](https://github.com/ismip/ISM_SimulationChecker/releases/new) against `main`. In the tag field, type the new version and choose **Create new tag on publish**, so that publishing the release creates the tag: one action, and the two can never disagree about which commit they point at. Write notes saying what changed for users, then publish.

   The tag is the bare version number — `0.2.0`, no `v` prefix — because the feedstock builds its source URL from it, and it must match `version` in `pyproject.toml` exactly.
3. Wait for the conda-forge bot to open a version-bump PR on [`isschecker-feedstock`](https://github.com/conda-forge/isschecker-feedstock), usually within a few hours. Review and merge it; the package appears on conda-forge shortly after the build finishes. Merging it needs write access to the feedstock, which is separate from write access here — see [Maintaining the feedstock](#maintaining-the-feedstock) below.

If the release changed the dependency ranges, edit the feedstock PR before merging so that the `run:` requirements in `recipe/recipe.yaml` match `pyproject.toml` and `isschecker_env.yml` — the bot updates the version and hash, not the requirements. Those three lists are the same constraints written down three times, and it is worth checking them against one another at each release.

Finally, and **optionally**, you can confirm what was published rather than assuming it:

```bash
conda create -n isschecker-test -c conda-forge --override-channels isschecker pytest
conda activate isschecker-test
ismip7-compliance-checker --version    # should print the version you tagged
cd $(mktemp -d) && pytest -v /path/to/ISM_SimulationChecker/tests
```

Run that from a checkout of the tag, not of `main`: the tests come from the source tree while the package comes from conda-forge, so with `main` checked out any change made since the tag shows up as a test failure that says nothing about the release.

It is optional because of the wait. A merged feedstock PR does not put the package within reach immediately: the build has to finish, and the result then takes roughly an hour to propagate across the servers `conda` fetches from. Until it has, `conda create` either cannot find the new version or reports the old one, and neither means anything is wrong. So this is not a step to sit and retry — come back to it later in the day, or skip it. The CI in this repository already runs the full suite against the tagged source at both ends of every dependency range, and the feedstock runs the recipe's own import and `--help` tests before the package is published at all, so a release that got that far is very unlikely to be broken in a way an install check would catch. What it does catch is the recipe describing something other than what you tagged — wrong version, a dependency range that never made it into `recipe/recipe.yaml` — which is worth a few minutes at some point after a release that changed either.

### Maintaining the feedstock

The conda-forge package is built by its own repository, [`conda-forge/isschecker-feedstock`](https://github.com/conda-forge/isschecker-feedstock), which is separate from this one and has its own list of maintainers — being a maintainer here does not make you one there. Only feedstock maintainers can merge the bot's version-bump PRs, so a release stalls if nobody available has that access. It is worth having more than one of us on the list.

The list lives in the recipe itself, under `extra: recipe-maintainers:` in `recipe/recipe.yaml`. To be added, open an **issue** on the feedstock with the title:

```
@conda-forge-admin, please add user @your-github-username
```

A bot then opens a PR adding you, which an existing feedstock maintainer merges. GitHub will email you an invitation to the feedstock's team in the conda-forge organisation; **you have to accept it**, or the merge has given you nothing. This is conda-forge's documented mechanism, described under [Updating the maintainer list](https://conda-forge.org/docs/maintainer/updating_pkgs/#updating-the-maintainer-list); leave the bot's PR alone rather than editing it or its commit message, since it is built to skip a package rebuild.

Those docs also say that asking to be added is not how to introduce yourself to a feedstock you have no history with — the usual route is to contribute a PR first. That caveat is about strangers arriving at someone else's package; this feedstock exists to publish this repository, so a maintainer here asking to be added to it is expected rather than presumptuous.

[The conda-forge maintainer documentation](https://conda-forge.org/docs/maintainer/) covers the rest: what the bots do, how to fix a build, and the [`@conda-forge-admin` commands](https://conda-forge.org/docs/maintainer/infrastructure/#conda-forge-admin-please-add-user-username) for re-rendering a feedstock and other routine chores. Very little of it is needed for a package as simple as this one — a pure-Python `noarch` recipe whose releases are usually nothing more than a version and a hash.
