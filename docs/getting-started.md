# Getting started

## Install

```bash
conda create -n isschecker -c conda-forge isschecker
conda activate isschecker
ismip7-compliance-checker --version
```

`mamba` and `micromamba` work the same way. If your conda is set up with the
`defaults` channel, add `--override-channels`; packages from the two channels
do not mix.

You get two commands: `ismip7-compliance-checker`, the checker, and
`ismip7-generate-test-files`, which writes synthetic files the checker passes.
{doc}`user/installation` covers updating and installing from source.

## Lay out your files

Suppose your group is VUW, your model is PISM1, and you have run the
Greenland historical and ctrl experiments. The checker expects the layout of
an ISMIP7 submission:

```
Models/GrIS/
└── VUW/                       <-- group
    └── PISM1/                 <-- model
        └── CORE/              <-- experiment group
            └── C001/          <-- set counter: this is --source-path
                ├── lithk_GrIS_VUW_PISM1_m001_CESM2-WACCM_f001_historical_C001_1960-2014.nc
                ├── lithk_GrIS_VUW_PISM1_m001_CESM2-WACCM_f001_ctrl_C001_2015-2300.nc
                ├── orog_GrIS_VUW_PISM1_m001_CESM2-WACCM_f001_historical_C001_1960-2014.nc
                ├── orog_GrIS_VUW_PISM1_m001_CESM2-WACCM_f001_ctrl_C001_2015-2300.nc
                └── ...
```

The checker looks at one set counter directory at a time, C001 here, and
that is the directory you give it. Inside, files are grouped by the
experiment in their names, so the historical run and the ctrl run above are
checked as two experiments. Pointing the checker at the model directory
instead, Models/GrIS/VUW/PISM1, gets you:

```
ERROR: No .nc files found in directory 'Models/GrIS/VUW/PISM1'. Please check your --source-path argument.
```

## Run it

```bash
ismip7-compliance-checker \
    --source-path Models/GrIS/VUW/PISM1/CORE/C001 \
    --variable-list ismip7
```

The variable list says which files to look for: `ismip7_xyt` for the gridded
variables, `ismip7_scalars` for the time series, `ismip7` for both. The
default is `ismip7_scalars`, so a directory of gridded files checked without
the option reports every scalar missing:

```
ERROR: In experiment ctrl, these mandatory variable(s) is (are) missing: ['lim', 'limnsw', 'iareagr', ...]
```

Every option is in {doc}`user/running`.

## Read the log

Findings are printed as the run goes and written to
compliance_checker_log.txt in the source directory, so the log can be
archived with the submission or attached to an issue. If you cannot write
there, add `--output-path` to send it elsewhere.

The log opens with the counts by category, then gives one block per file:

```
1 experiments checked.
27 files checked.

0 error(s) detected.
  - Variable presence  : 0 error(s)
  - Naming Tests       : 0 error(s)
  ...

1 warning(s) detected.
  - Variable presence  : 1 warning(s)
  - Naming Tests       : 0 warning(s)
  ...

WARNING: experiment ctrl carries no files for the non-mandatory variable(s): ['hfgeoubed', 'xvelsurf', ...]

Experiment: ctrl - File: acabf_GrIS_VUW_PISM1_m001_CESM2-WACCM_f001_ctrl_C001_2015-2300.nc

NAMING Tests
 - Filename year range 2015-2300 is well formed: OK
 - Variable 'acabf' from the file name is present in the file: OK
 ...
```

An **error** means the file, as submitted, cannot be used for the analysis
it was submitted for. A **warning** means the file is usable, but something
in it is worth a look. Only errors change the exit status, so the checker can
be run from a script. {doc}`user/errors-and-warnings` says what separates the
two and what to do about the common warnings; the one above, for instance,
is quieted by listing the variables your model does not have.

## No files to check yet?

`ismip7-generate-test-files` writes synthetic files that the checker passes,
which is a quick way to see what compliant output looks like before your own
is ready:

```bash
ismip7-generate-test-files --grid GrIS_16000m --scenario ctrl --xyt \
    --nyears 286 --start-year 2015
```

They go under Models/GrIS/ISMIP7/SYNTH1/CORE/C001 in the current directory.
See {doc}`dev/generating-test-files` for the options.

## Where to go next

- {doc}`user/checks`: what the checker looks at.
- {doc}`user/time-encoding`: the timestamps and bounds each variable type
  needs, which is the most common thing to get wrong.
- {doc}`user/data-request`: the units, value ranges and other criteria,
  variable by variable.
