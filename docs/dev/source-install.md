# Installing from source

You only need this to work *on* the checker — to test a change that has not
been released yet, or to develop one. For checking a submission, install from
conda-forge instead (see {doc}`../user/installation`).

Create the conda environment and install the package into it:

```bash
conda env create -f isschecker_env.yml
conda activate isschecker
python -m pip install --no-deps --no-build-isolation .
```

Note that `isschecker_env.yml` installs the dependencies but not the checker
itself, so the environment it creates is not the one conda-forge gives you: an
`isschecker` environment made this way holds no `isschecker` package until the
`pip install` runs. If you already have an environment of that name from
conda-forge, `conda env create` will refuse to create another over it; give
this one a different name with
`conda env create -n isschecker-dev -f isschecker_env.yml` and keep both.

```{warning}
**Use those pip flags.** All dependencies come from conda-forge, and a plain
`pip install .` can silently replace them with PyPI wheels — `netCDF4` in
particular bundles its own copy of the netCDF C library — which is exactly how
two people end up with different results from the same files. `--no-deps`
keeps pip from resolving anything, and `--no-build-isolation` builds with the
environment's `setuptools` instead of downloading one from PyPI. Add
`--no-index` if you want any accidental network fetch to fail loudly rather
than succeed quietly.
```

For development, add `-e` for an editable install:

```bash
python -m pip install --no-deps --no-build-isolation -e .
```

(`pytest` comes from the conda environment, so the `[test]` extra is not
needed.) An editable install is worth having while developing, because the
tests import the installed package: after a non-editable install, edits to the
source tree do not affect a test run until you reinstall.

If a rebuild ever behaves as though it were still running older code, delete
the `build/` directory: `setuptools` reuses its contents, so files that have
since been renamed or removed can otherwise end up back in the installed
package.

## Dependencies

Installing from conda-forge pulls these in for you, and you can skip this
section. It matters when you install from source, where the environment is
yours to create.

Versions are constrained in `isschecker_env.yml`; the same constraints appear
in `pyproject.toml`. The suite is tested at both ends of every range, so
results should agree across machines and operating systems within these bounds.

| Package | Constraint | Why bounded |
|---|---|---|
| `python` | `>=3.11,<3.15` | `str \| None` annotations need ≥3.10; 3.10 is EOL in Oct 2026 |
| `numpy` | `>=2.1,<3` | what recent `pandas`/`xarray` are built against |
| `pandas` | `>=2.2,<4` | reads the criteria CSVs; 3.0 changed the default string dtype |
| `xarray` | `>=2025.1.2,<2027` | `xarray.coders.CFDatetimeCoder` (public API in 2025.1.1) and non-nanosecond datetime decoding, both used by the time checks |
| `cftime` | `>=1.6.4,<2` | date arithmetic in the start/end/duration checks |
| `netCDF4` | `>=1.7,<2` | `_FillValue` checks compare against `netCDF4.default_fillvals` |
| `tqdm` | `>=4.66` | progress bar only; never affects the log |

If you report a problem with the checker, please include the output of
`conda list` for your `isschecker` environment.
