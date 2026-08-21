# Errors and warnings

Findings come at two severities, and the difference is worth stating precisely,
because a check that reports at the wrong one either fails a submission that is
fine or waves through one that is not.

**ERROR** — the file, as written, is unusable for the intended analysis,
departs from the protocol in a way that changes the science, or fails the
data-hygiene requirements this archive is committing to. That last clause is
deliberate: the output will be served to the broader community for analysis for
years, so uniformity of encoding is a product requirement rather than a
stylistic preference, and "a reader could cope with it" is not grounds for a
warning.

**WARNING** — the file is usable, the science is unaffected, and nothing
downstream has to work around it, but it departs from what the data request
asked for in a way you should look at and may reasonably have intended.

Three consequences follow, and they are what make a warning safe to leave
alone:

- Warnings never enter the error count and never change a file's verdict. A
  file with warnings and no errors is compliant, and the log says so:
  `No errors. Good job !`, followed by the number of warnings to review.
- Warnings never affect the exit status. Errors do.
- A check whose failure means the checker could not read something is always an
  error. A warning never stops any later check from running.

The synthesis block at the top of the log counts both severities, broken down
by the same categories.

## Variables your model does not represent

An experiment that carries no files for a non-mandatory variable gets one
warning naming all of them. This is expected if your model does not represent
those variables — GIA is the obvious case — and it is listed only so that a
variable lost from a submission does not pass unnoticed. It is scoped to the
`--variable-list` you selected, so a run over `ismip7_scalars` says nothing
about the `x,y,t` variables it was never asked to look at.

To make that warning go quiet, put an optional `not_modelled.txt` in the
`--source-path` directory: one variable name per line, blank lines ignored and
`#` starting a comment, so you can record alongside each name why the variable
is absent.

```
# ISMIP7: variables this model does not represent.
dlithkdt      # no GIA in this configuration
litemp
```

Two rules keep the file from becoming a way to hide problems, and both are
errors rather than silent no-ops:

- A **mandatory** variable named in it is still a missing-mandatory error, and
  the claim itself is reported as a further error. The list is a statement
  about optional variables; a submission cannot opt out of the data request
  with it.
- A name that is **not in the data request** at all is an error. It is either a
  typo or a misunderstanding, and both are better said plainly than left to be
  inferred from a warning that did not go away.

Whatever the file declares is echoed into the log, so the archived record of a
run shows what was claimed rather than merely that a warning did not appear. If
the file is absent, nothing changes.

## Missing values and masks

Submissions have disagreed about where a field should hold a value and where it
should hold a fill value ([issue #23]): zero ice thickness or missing ice
thickness outside the ice, a mask of zeros or a mask with holes in it. That is
a per-variable question, so the data request answers it for every variable, in
the `fill_policy` column — the table is in
[The data request](data-request.md#missing-values).

Two points modelers ask about. **Ice thickness is zero where there is no ice**,
not missing — including outside your computational domain — and so are the
three masks and the calving, grounding-line and ice-front fluxes. **The masks
are not restricted to 0 and 1**: any fraction in `[0, 1]` is accepted, because
conservative interpolation from your native grid to the output grid
legitimately produces intermediate values.

**However a variable spells "missing", it must spell it the netCDF way.**
Every value has to be either a finite number or exactly the `_FillValue` the
file declares, whatever the variable's policy. A bare NaN, or an infinity, is
an error: it is a private convention the archive has not agreed to, and a
reader filtering on `_FillValue` — as the request tells them to — will silently
treat those cells as data. If your model writes NaN where it means missing,
this is the one change it needs.

Anything the column does not say — a blank cell, an unrecognized value, or the
column being absent altogether — means the variable is unconstrained and
nothing about its missing values is checked. No shipped row is blank today; the
default exists so that the column can be extended without breaking older and
newer checkers against each other.

[issue #23]: https://github.com/ismip/ISM_SimulationChecker/issues/23

## Value ranges

Some of the `min_value_*` / `max_value_*` bounds in the data request "are
dependent on the forcing, input data and model implementation"
([issue #10](https://github.com/ismip/ISM_SimulationChecker/issues/10)), and
some are not, so the severity of an out-of-range value is a per-variable
question. It is answered by the `range_severity` column of
`ISMIP7_variable_request.csv`, which holds `error` or `warning` for each
variable row. Anything the column does not say — a blank cell, an unrecognized
value, or the column being absent altogether — means `error`.

Every shipped row is currently `error`, so this changes nothing today. Moving a
variable to `warning` is a one-cell change to the data request that needs no
reasoning about the checker.

The bounds and the severity that goes with each of them are listed under
[Value ranges](data-request.md#value-ranges).
