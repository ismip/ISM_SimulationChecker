# Installation

## From conda-forge

The checker is packaged on
[conda-forge](https://anaconda.org/conda-forge/isschecker), and that is how you
should install it. Nothing is built, no dependency has to be picked by hand,
and there is no need to clone the repository at all:

```bash
conda create -n isschecker -c conda-forge isschecker
conda activate isschecker
```

`mamba` and `micromamba` work the same way; substitute either for `conda` if
you prefer. If your conda is configured with the `defaults` channel, add
`--override-channels` so a package cannot be pulled from it: builds from the
two channels are not interchangeable, and mixing them is a good way for two
people to get different results from the same files.

The package registers the `ismip7-compliance-checker` and
`ismip7-generate-test-files` commands and bundles the data files, so the checker
can be run from any directory. Confirm the installation with:

```bash
ismip7-compliance-checker --version
```

## Updating

To move to a newer release later:

```bash
conda activate isschecker
conda update -c conda-forge isschecker
```

The conda-forge package is built from the tagged releases of the repository, so
it can be behind `main` by a release; `--version` always reports the one you
actually have. Quote it when you report a problem — a finding's wording, and
sometimes its severity, depends on which release produced it. See
{doc}`../dev/releasing` for when a tag is cut.

## From source

You only need a source install to work *on* the checker — to test a change
that has not been released yet, or to develop one. For checking a submission,
install from conda-forge as above. The source install, the pip flags it needs
and the dependency ranges it has to satisfy are described in
{doc}`../dev/source-install`.
