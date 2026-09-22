---
name: pr-descriptions
description: Write or update a pull request description. Use when opening a pull request or editing its body.
---

# Pull request descriptions

The reader is deciding whether to review.

- What changed and why, in a few sentences. Not how.
- Anything needing a reviewer decision goes in its own short list near the
  top, never mid-paragraph.
- A list of changed behaviors is fine. A trace of the mechanism is not.
- No commit list. No testing; that goes in a separate `Testing` comment.
- Link the issue that gives context, with a closing keyword if the pull
  request fixes it.
- Several fixes usually means several pull requests.

## Calibration

Eight descriptions here were written by hand, before any agent wrote in
this repository: 20 to 155 words, 50 at the median. Agent-written ones
since have run from 11 to 2070 words. Eight is too few to measure a tail,
so take the rule of thumb from [polaris], a larger repository with the
same maintainer: 27 words at the median, 45 to 62 at the seventy-fifth
percentile, 103 to 110 at the ninetieth, 354 at the longest.

[polaris]: https://github.com/E3SM-Project/polaris

## Enough

A convention change, stated and done (#6):

> The update includes 4d variable litemp with specific snapshot years on
> the time axis and variable refgeoid without time axis.

A change in behavior, with the parts a reviewer needs to know about (#4):

> State variable (ST) timestamps now follow the ismip7-time-encoding
> reference: end-of-year snapshots are encoded as Jan 1 of the following
> year (e.g. simulation year 2015 → 2016-01-01), not Dec 31.
>
> Flux variable (FL) encoding is unchanged: mid-year timestamp Jul 1 with
> time bounds [Jan 1, Jan 1 next year].
>
> experiments_ismip7.csv is redesigned to store nominal simulation years
> (start_year_min, start_year_max, end_year) instead of raw date strings.

A restructuring, with the changes as a list (#9):

> Convert the flat compliance_checker.py module into a proper package so
> `pip install .` works and the checker runs from any directory.
>
> - Move compliance_checker.py to compliance_checker/__init__.py and add
>   __main__.py (enables `python -m compliance_checker`).
> - Move the runtime CSVs into compliance_checker/data/ as the single
>   source of truth; load them via importlib.resources instead of paths
>   relative to the working directory.
> - Add pyproject.toml declaring the package, data files, dependencies,
>   and the `ismip7-compliance-checker` console script.

## Too much

The description of #18 ran 2070 words. It opened by tracing why the old
code could not do what the change does:

> Everything else was an error, because there was no other severity in
> the counting path — each `_check_*` function wrote `" - ERROR: ..."`
> and returned an `int` that its caller added on, and there was nowhere
> for a second severity to live.

Someone deciding whether to review does not need the old counting path
traced. "The checker had no warning severity; this adds one" would do,
and the rest belongs in the commit message.
