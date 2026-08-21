# Developer guide

Guidance for contributing to the checker and for maintaining its releases. If
you only want to check a submission, you do not need any of this — install from
conda-forge as described in {doc}`../getting-started`.

The repository is laid out like this:

`isschecker/checker.py`
: the checker itself, and the `ismip7-compliance-checker` entry point.

`isschecker/generate.py`
: the synthetic file generator, and the `ismip7-generate-test-files` entry
  point.

`isschecker/data/`
: the data request CSVs and the grid definition files (`gdfs/`), bundled with
  the package as package data.

`tests/`
: the regression suite, including the reference log that pins the checker's
  output.

`docs/`
: these pages.

```{toctree}
:maxdepth: 2
:caption: Contents

source-install
generating-test-files
testing
building-docs
releasing
```
