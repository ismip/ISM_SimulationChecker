---
hide-toc: true
---

# ISMIP7 Compliance Checker

Checks ISMIP7 NetCDF model output against the
[ISMIP7 data request](https://www.ismip.org/), so that a submission can be
corrected before it is archived rather than after. Point it at a directory of
files and it writes a log saying, file by file, what is wrong and how serious
it is.

```bash
conda create -n isschecker -c conda-forge isschecker
conda activate isschecker
ismip7-compliance-checker \
    --source-path Models/GrIS/VUW/PISM1/CORE/C001 \
    --variable-list ismip7
```

::: {card} Getting started
:link: getting-started
:link-type: doc

Install the checker, lay out your files, run it, and read the log.
:::

::: {card} User guide
:link: user/index
:link-type: doc

Every option, what each check looks at, how errors and warnings differ, how
time is encoded, and the data request the checks come from.
:::

::: {card} Developer guide
:link: dev/index
:link-type: doc

Work on the checker: install from source, generate test files, run the tests,
build these docs, and cut a release.
:::

## What is checked

Every file is checked in six categories: naming, numerical values, spatial
grid, time axis, consistency between files, and attributes. {doc}`user/checks`
describes them. The criteria come from the data request files bundled with the
package and are listed in {doc}`user/data-request`.

An **error** means the file cannot be used as submitted. A **warning** means
it is usable but departs from what was asked for. Only errors change the exit
status; see {doc}`user/errors-and-warnings`.

## Where things live

The checker is developed at
[ismip/ISM_SimulationChecker](https://github.com/ismip/ISM_SimulationChecker)
and released through
[conda-forge](https://anaconda.org/conda-forge/isschecker). Problems and
questions go in
[the issue tracker](https://github.com/ismip/ISM_SimulationChecker/issues).

```{toctree}
:hidden:

getting-started
user/index
dev/index
```
