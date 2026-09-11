# Installation

## From conda-forge

The checker is packaged on
[conda-forge](https://anaconda.org/conda-forge/isschecker). Nothing is built
and there is no need to clone the repository:

```bash
conda create -n isschecker -c conda-forge isschecker
conda activate isschecker
ismip7-compliance-checker --version
```

`mamba` and `micromamba` work the same way. If your conda is set up with the
`defaults` channel, add `--override-channels` so nothing is pulled from it;
packages from the two channels do not mix.

The package installs the `ismip7-compliance-checker` and
`ismip7-generate-test-files` commands and bundles the data request, so both
can be run from any directory.

## Updating

```bash
conda activate isschecker
conda update -c conda-forge isschecker
```

The conda-forge package is built from tagged releases, so it can be a release
behind the repository. Quote the output of `--version` when you report a
problem: a finding's wording, and sometimes its severity, depends on the
release.

## From source

You only need a source install to work *on* the checker: to test a change
that has not been released yet, or to develop one. To check a submission,
install from conda-forge as above. {doc}`../dev/source-install` covers the
source install.
