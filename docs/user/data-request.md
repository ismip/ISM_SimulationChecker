```{raw} html
<style>
/* Reference tables, not prose: this page earns a wider measure than the
   theme's default, and only this page gets it. */
body { --content-width: 62em; }
/* Long names read badly stacked one word per line, and the browser gives
   them the space left over by the columns that cannot wrap at all. */
.table-wrapper table.docutils td:nth-child(2) { min-width: 11em; }
</style>
```

# The data request

The criteria the checker applies are not written into its code. They live in
two CSV files bundled with the package:

`isschecker/data/ISMIP7_variable_request.csv`
: one row per variable — its dimensions, type, units, `standard_name`, whether
  it is mandatory, and the value range allowed in each region.

`isschecker/data/experiments_ismip7.csv`
: one row per experiment — the nominal start years it may begin at, the year it
  ends, and how long it runs.

The tables on this page are generated from those two files when these pages are
built, so they say what the checker enforces rather than what someone
remembered to copy across. A release of the checker that changes the data
request changes this page with it; if you are chasing a disagreement between
the docs and a run, compare `ismip7-compliance-checker --version` against the
version in the sidebar.

Both files can be inspected directly in the repository
([variable request][var-csv], [experiments][exp-csv]) — they are ordinary CSV
and open in a spreadsheet.

[var-csv]: https://github.com/ismip/ISM_SimulationChecker/blob/main/isschecker/data/ISMIP7_variable_request.csv
[exp-csv]: https://github.com/ismip/ISM_SimulationChecker/blob/main/isschecker/data/experiments_ismip7.csv

## Variables

Variables are grouped by their dimensions, since that is what decides which
checks apply: the gridded variables are checked against the grid extents and
resolutions, the scalars are not, and `x,y,z,t` carries sparse snapshots rather
than an annual time series.

**Type** is `ST` for a state variable — a snapshot — or `FL` for a flux, which
is an annual average; the two are timestamped differently, as described in
{doc}`time-encoding`. **Mandatory** says whether a submission must include the
variable at all: a missing mandatory variable is an error, while a missing
optional one is a warning you can quiet by declaring it, as described in
[Variables your model does not represent](errors-and-warnings.md#variables-your-model-does-not-represent).

```{include} ../_generated/variables.md
```

## Value ranges

Every value in a file must lie within the range its variable and region allow.
The bounds differ between Antarctica and Greenland where the ice sheets differ,
and the severity column says whether exceeding them fails the file or is only
reported — see
[Value ranges](errors-and-warnings.md#value-ranges) for why that is a
per-variable question.

```{include} ../_generated/value-ranges.md
```

```{include} ../_generated/fill-policies.md
```

## Experiments

An experiment's row fixes the nominal years its files may cover, and with them
the time axis every annual file must carry. `historical` is the one experiment
whose start year the modeler chooses, so its duration follows from that choice
rather than being fixed here; every projection runs from 2015 to a fixed end
year.

```{include} ../_generated/experiments.md
```

The nominal years in this table are what a filename's `YYYY-YYYY` range refers
to, and what the timestamps inside the file are derived from — not the same
thing, and {doc}`time-encoding` explains the difference.
