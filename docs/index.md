---
hide-toc: true
---

# ISMIP7 Compliance Checker

`isschecker` checks ISMIP7 NetCDF simulation datasets against the [ISMIP7 data
request conventions](https://www.ismip.org/), so that a submission can be
corrected before it is archived rather than after. Point it at a directory of
files and it writes a log saying, file by file, what is wrong and how serious
it is.

```bash
conda create -n isschecker -c conda-forge isschecker
conda activate isschecker
ismip7-compliance-checker --source-path ./Models/GrIS/ISMIP7/SYNTH1/CORE/C001 \
    --variable-list ismip7
```

::: {card} Getting started
:link: getting-started
:link-type: doc

Install the checker, run it over a submission, and read what it tells you.
:::

::: {card} User guide
:link: user/index
:link-type: doc

What each check looks at, how errors and warnings differ, how time is encoded,
and the data request the checks come from.
:::

::: {card} Developer guide
:link: dev/index
:link-type: doc

Work on the checker: install from source, generate test files, run the test
suite, build these docs, and cut a release.
:::

## What is checked

Every file is checked in five categories — naming, numerical values, spatial
grid, time axis, and attributes — described in
{doc}`user/checks`. The criteria themselves come from the data request files
bundled with the package and are listed in {doc}`user/data-request`.

Findings come at two severities. An **error** means the file cannot be used as
submitted; a **warning** means it is usable but departs from what was asked
for. Only errors change the exit status, so a run can be wired into a script
without warnings failing it. See {doc}`user/errors-and-warnings`.

## Where things live

The checker is developed at
[ismip/ISM_SimulationChecker](https://github.com/ismip/ISM_SimulationChecker)
and released through
[conda-forge](https://anaconda.org/conda-forge/isschecker). Problems and
questions belong in
[the issue tracker](https://github.com/ismip/ISM_SimulationChecker/issues).

```{toctree}
:hidden:

getting-started
user/index
dev/index
```
