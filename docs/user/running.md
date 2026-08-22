# Running the checker

Once installed, run the checker from any directory with the
`ismip7-compliance-checker` command (equivalently, `python -m isschecker`). It
writes `compliance_checker_log.txt` into the `--source-path` directory.

```bash
# Check x,y,t (gridded) variables
ismip7-compliance-checker \
    --source-path ./Models/GrIS/ISMIP7/SYNTH1/CORE/C001 \
    --variable-list ismip7_xyt

# Check scalar (time-only) variables
ismip7-compliance-checker \
    --source-path ./Models/AIS/ISMIP7/SYNTH1/CORE/C001 \
    --variable-list ismip7_scalars

# Check both
ismip7-compliance-checker \
    --source-path ./Models/GrIS/ISMIP7/SYNTH1/CORE/C001 \
    --variable-list ismip7
```

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--source-path` | `./Models/GrIS/ISMIP7/SYNTH1/CORE/C001` | Set-counter subdirectory containing `.nc` files to check |
| `--variable-list` | `ismip7_scalars` | `ismip7_xyt`, `ismip7_scalars`, or `ismip7` (both) |
| `--version` | — | Print the installed version and exit; quote it when reporting a problem |

The `--source-path` is one set-counter directory — the leaf of the
`Models/{GrIS|AIS}/ISMIP7/{group}/{model}/{set_counter}` layout — because that
is the unit a submission is checked in. Within it, the checker groups the
`.nc` files by the experiment their names give, so a directory holding a
`historical` run and a projection is handled as the two runs it is, and each
group is then checked for the variables the data request asks of it as well as
for what is inside each file.

Which variables are expected, and what they must contain, comes from the data
request bundled with the package; `experiments_ismip7.csv` defines the allowed
nominal year ranges and durations for each experiment, from which the checker
derives the expected FL and ST timestamps at runtime (see
{doc}`time-encoding`). Both files are listed in {doc}`data-request`.

## What it writes

Findings are printed as the run goes and collected in
`compliance_checker_log.txt` in the `--source-path` directory. The log begins
with a synthesis block counting errors and warnings by category, so a long run
can be read from the top rather than scrolled through. Because it is written
beside the files it describes, it can be archived with the submission or
attached to an issue as it stands.

## Exit status

The checker exits **non-zero** when it found errors, or when it could not check
anything at all — the `--source-path` does not exist, or holds no `.nc` files.
It exits **zero** when the submission is compliant, including when there are
warnings to review; see {doc}`errors-and-warnings`. Both
`ismip7-compliance-checker` and `python -m isschecker` behave the same way, so
either can be used in a script.
