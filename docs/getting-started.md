# Getting started

## Install

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

Everything about keeping an installation current — updating, what a release
means, and how to install from a source checkout instead — is in
{doc}`user/installation`.

## Run a check

The checker looks at one set-counter directory at a time, and you tell it which
family of variables to look for:

```bash
ismip7-compliance-checker \
    --source-path ./Models/GrIS/ISMIP7/SYNTH1/CORE/C001 \
    --variable-list ismip7
```

`--variable-list` is `ismip7_xyt` for the gridded variables, `ismip7_scalars`
for the time-only ones, or `ismip7` for both. The full set of options is in
{doc}`user/running`.

## Read the result

Findings are printed as the run goes and written to
`compliance_checker_log.txt` in the `--source-path` directory, so the log can
be archived alongside the submission or attached to an issue. Add
`--output-path` to send it elsewhere, which is what an archive you cannot write
to needs. The log opens with a synthesis block counting errors and warnings by
category, and the two severities mean quite different things:

- an **error** means the file, as submitted, cannot be used for the analysis it
  was submitted for;
- a **warning** means the file is usable, but something in it is worth a look.

Only errors change the exit status, so `ismip7-compliance-checker` can be run
from a script and trusted to fail only when something is actually wrong. What
separates the two, and what to do about the common warnings, is described in
{doc}`user/errors-and-warnings`.

## No files to check yet?

`ismip7-generate-test-files` writes synthetic ISMIP7-style files that the
checker passes, which is a quick way to see what compliant output looks like
before your own is ready:

```bash
ismip7-generate-test-files --grid GrIS_16000m --scenario ctrl --xyt \
    --nyears 286 --start-year 2015
```

See {doc}`dev/generating-test-files` for the options.

## Where to go next

- {doc}`user/checks` — what the checker actually looks at.
- {doc}`user/time-encoding` — the timestamps and bounds each variable type
  needs, which is the most common thing to get wrong.
- {doc}`user/data-request` — the units, value ranges and other criteria, listed
  variable by variable.
