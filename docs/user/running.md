# Running the checker

```bash
ismip7-compliance-checker \
    --source-path Models/GrIS/VUW/PISM1/CORE/C001 \
    --variable-list ismip7
```

`python -m isschecker` does the same. Findings are printed as the run goes
and written to compliance_checker_log.txt in the source directory.

## Options

| Option | Meaning | Default |
|---|---|---|
| `--source-path` | the set counter directory holding the .nc files to check | Models/GrIS/ISMIP7/SYNTH1/CORE/C001 |
| `--variable-list` | which files to look for: `ismip7_xyt` for the gridded variables, `ismip7_scalars` for the time series, `ismip7` for both | ismip7_scalars |
| `--output-path` | where to write the log; created if missing | the source directory |
| `--version` | print the installed version and exit; quote it when reporting a problem | |

## The source path

One set counter directory at a time, the C001 (or E003, P012, ...) directory
of an ISMIP7 submission tree:

```
Models/GrIS/
└── VUW/                       <-- group
    └── PISM1/                 <-- model
        └── CORE/              <-- experiment group
            └── C001/          <-- --source-path
                ├── lithk_GrIS_VUW_PISM1_m001_CESM2-WACCM_f001_historical_C001_1960-2014.nc
                ├── lithk_GrIS_VUW_PISM1_m001_CESM2-WACCM_f001_ctrl_C001_2015-2300.nc
                └── ...
```

Inside it, files are grouped by the experiment in their names. A directory
holding a historical run and a projection is checked as the two experiments
it holds, each against the variables the data request asks of that
experiment. Any directory higher up holds no .nc files and is refused:

```
ERROR: No .nc files found in directory 'Models/GrIS/VUW/PISM1'. Please check your --source-path argument.
```

## The variable list

Which variables the checker expects to find, so that the gridded variables
and the scalars can be checked separately. The default is `ismip7_scalars`;
checking a directory of gridded files without `--variable-list ismip7_xyt`
reports every mandatory scalar missing:

```
ERROR: In experiment ctrl, these mandatory variable(s) is (are) missing: ['lim', 'limnsw', 'iareagr', ...]
```

## The log

The log is written beside the files it describes, so it can be archived with
the submission or attached to an issue. For an archive you cannot write to,
give `--output-path` a directory; it is created if it does not exist. The
log is always named compliance_checker_log.txt, so two runs sharing an
output directory overwrite each other.

The log opens with the counts of errors and warnings by category, so a long
run can be read from the top. One block per file follows; see
{doc}`../getting-started` for an excerpt.

## Exit status

| Code | Meaning |
|---|---|
| 0 | no errors; there may be warnings to review |
| non-zero | errors were found, or nothing could be checked: the source path does not exist, holds no .nc files, or the log could not be written |

Warnings never change the exit status, so the checker can be run from a
script; see {doc}`errors-and-warnings`.
