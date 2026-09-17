# Errors and warnings

Findings come at two severities.

**ERROR**: the file, as written, cannot be used for the intended analysis,
departs from the protocol in a way that changes the science, or breaks the
uniform encoding the archive commits to. The output will be served to the
community for years, so "a reader could cope with it" is not grounds for a
warning.

**WARNING**: the file is usable and the science is unaffected, but it departs
from what the data request asked for in a way you should look at and may
have intended.

That makes a warning safe to leave alone:

- Warnings never enter the error count or change a file's verdict. A file
  with warnings and no errors is compliant, and the log says so: "No errors.
  Good job !", then the number of warnings to review.
- Warnings never affect the exit status. Errors do.
- Anything the checker could not read is an error. A warning never stops a
  later check from running.

The block at the top of the log counts both severities by category.

## Variables your model does not represent

An experiment with no files for a non-mandatory variable gets one warning
naming all of them:

```
WARNING: experiment ctrl carries no files for the non-mandatory variable(s): ['hfgeoubed', 'xvelsurf', 'yvelsurf', ...]. This is expected if your model does not represent them; it is listed only so that a variable lost from a submission does not pass unnoticed.
```

It covers only the variables in the `--variable-list` you chose, so a run
over the scalars says nothing about the gridded variables.

To quiet it, put a not_modelled.txt in the source directory with one variable
name per line. Blank lines are ignored and `#` starts a comment, so you can
record why each variable is absent:

```
# ISMIP7: variables this model does not represent.
dlithkdt      # no GIA in this configuration
litemp
```

Two things in the file are errors, so that it cannot hide a problem:

- A **mandatory** variable. It is still reported missing, and the claim
  itself is a further error; a submission cannot opt out of the data request
  this way.
- A name that is **not in the data request**. It is a typo or a
  misunderstanding, and either is better said plainly.

What the file declares is echoed into the log, so the archived record shows
what was claimed. If there is no file, nothing changes.

## Missing values and masks

Submissions have disagreed about where a field should hold a value and where
a fill value ([issue #23]): zero or missing thickness outside the ice, a
mask of zeros or a mask with holes in it. The data request answers this for
every variable in its fill_policy column; the table is under
[Missing values](data-request.md#missing-values).

Two points modelers ask about. **Ice thickness is zero where there is no
ice**, not missing, including outside your computational domain, and so are
the three masks and the calving, grounding-line and ice-front fluxes. **The
masks are not restricted to 0 and 1**: any fraction in [0, 1] is accepted,
because conservative interpolation from your native grid legitimately
produces intermediate values.

A `forbidden` variable holding any fill value is an error. The other
policies say where a field sits relative to the ice masks, which takes more
than one file to check; see
[Checks that compare files](#checks-that-compare-files).

**However a variable spells "missing", it must spell it the NetCDF way.**
Every value is either a finite number or exactly the _FillValue the file
declares. A bare NaN or an infinity is an error: a reader filtering on
_FillValue, as the request tells them to, would treat those cells as data.
If your model writes NaN where it means missing, this is the one change it
needs.

A variable whose fill_policy cell is blank is unconstrained, and nothing
about its missing values is checked. No shipped row is blank today.

[issue #23]: https://github.com/ismip/ISM_SimulationChecker/issues/23

## Checks that compare files

Most fill policies cannot be checked from one file alone. The checker looks
for the companion it needs in the same directory, matching every field of
the name but the variable, and compares the two.

- A `no_ice`, `no_grounded_ice` or `no_floating_ice` variable is missing
  **exactly** where its mask is zero. Ice is sftgif > 0, so a cell holding
  any fraction of ice is one the variable must be defined in. The two
  directions are reported separately: holding a value where there is no ice
  is an error; being missing where there is ice is, for now, a warning (see
  below).
- An `outside_domain` variable is defined wherever there is ice; otherwise
  the submission has ice outside its own computational domain, which is an
  error. These variables should also agree with each other about where the
  domain is. That is a warning, because a field taken from a forcing or
  reference dataset may legitimately cover more of the grid than the ice
  model does.
- sftgrf + sftflf equals sftgif; lithk is greater than zero exactly where
  sftgif is; orog equals base + lithk; and the ice base rests on the bed
  where sftgrf is 1 and lies above it where sftflf is 1. None of these needs
  an assumed density.

**If a file a check needs is not there, the check says so and is skipped**,
so a run scoped to the scalars, or a model that does not produce a mask yet,
needs no flag.

**The value identities are checked in every cell**, including partly
glaciated ones, and assume that the fields use the same averaging convention
there. The grounded and floating comparisons against the bed are the
exception: they are made only in cells that are wholly one or the other,
since in a half-and-half cell the mean ice base sits somewhere between.

### One severity that will change

Two findings turn on where a model puts the ice margin: a variable being
*missing where there is ice*, and thickness disagreeing with the ice mask. A
conservatively interpolated mask puts fractions like 1e-6 in a ring along
the edge, and a model that writes fill from its own native-grid mask will
disagree in every one of those cells.

One round of real submissions will settle which is right, so **those two
findings are warnings for the first round and will become errors
afterwards**. The definitions above are fixed, and a model can be written to
them today. The finding reports how much of itself is margin, "300 of them
have sftgif below 0.01", so the decision can be made on evidence.

## Value ranges

The bounds in the data request are sanity limits. A field that is largely
outside them is not a plausible ice sheet: the `units` attribute says `m s-1`
over data in m yr⁻¹, a temperature is in Celsius, a mask is in percent, a
flux has its sign flipped. The units check reads the attribute, not the data,
so this is the only check that catches those, and they are errors.

But a few cells outside the bounds are routine in a legitimate simulation. A
stress-balance solver can put a few grid points of very high speed at the ice
margin, bedrock that has just lost its ice can carry a heat flux the bounds
do not allow for, and a calving event can put one year's flux far past the
bound ([discussion #46]). There is nothing a modeler can do about any of
those, and failing a file on them would have valid runs discarded.

So the severity depends on how much of the field is outside. Fewer than 1% of
the values that hold a number is a **warning**; 1% or more is an **error**.
Either way the finding says how many, "3 of 38372 value(s) (0.00782%) are
below it", so the decision can be checked against the evidence: a handful of
cells at the margin is one thing, and a third of the ice sheet is another.
The share is of the values that hold a number, not of the grid, so a variable
defined only where there is ice is judged against the ice and not against the
ocean around it.

Some bounds may turn out to be soft everywhere, not just at a few cells
([issue #10]). For those the `range_severity` column of the data request can
be set to `warning`, and the finding is then a warning however much of the
field is outside. No shipped row says so today; a blank cell means the graded
rule above.

The bounds are listed under [Value ranges](data-request.md#value-ranges).

[issue #10]: https://github.com/ismip/ISM_SimulationChecker/issues/10
[discussion #46]: https://github.com/orgs/ismip/discussions/46
