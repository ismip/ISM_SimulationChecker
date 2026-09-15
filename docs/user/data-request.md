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

ISMIP7_variable_request.csv
: one row per variable: its dimensions, type, units, standard_name, whether
  it is mandatory, and the value range allowed in each region.

experiments_ismip7.csv
: one row per experiment: the nominal start years it may begin at, the year
  it ends, and how long it runs.

The tables on this page are generated from those files when the pages are
built, so they say what the checker enforces. If the docs and a run disagree,
compare `ismip7-compliance-checker --version` against the version in the
sidebar.

Both files are ordinary CSV and open in a spreadsheet:
[variable request][var-csv], [experiments][exp-csv].

[var-csv]: https://github.com/ismip/ISM_SimulationChecker/blob/main/isschecker/data/ISMIP7_variable_request.csv
[exp-csv]: https://github.com/ismip/ISM_SimulationChecker/blob/main/isschecker/data/experiments_ismip7.csv

## Variables

Variables are grouped by their dimensions, since that decides which checks
apply: the gridded variables are checked against the grid extents and
resolutions, the scalars are not, and x,y,z,t variables carry snapshots
rather than an annual series.

**Type** is ST for a state variable, a snapshot, or FL for a flux, an annual
average; the two are timestamped differently, as described in
{doc}`time-encoding`. **Mandatory** says whether a submission must include
the variable: a missing mandatory variable is an error, and a missing
optional one is a warning you can quiet by declaring it, as described in
[Variables your model does not represent](errors-and-warnings.md#variables-your-model-does-not-represent).

```{include} ../_generated/variables.md
```

## Value ranges

Every value in a file must lie within the range its variable and region
allow. The bounds differ between Antarctica and Greenland where the ice
sheets differ, and the severity column says whether exceeding them fails the
file or only reports it; see
[Value ranges](errors-and-warnings.md#value-ranges).

```{include} ../_generated/value-ranges.md
```

```{include} ../_generated/fill-policies.md
```

## Experiments

An experiment's row fixes the nominal years its files may cover, and with
them the time axis every annual file must carry. The historical run is the
one experiment whose start year the modeler chooses; every projection runs
from 2015 to a fixed end year.

```{include} ../_generated/experiments.md
```

The nominal years here are what a file name's year range refers to. The
timestamps inside the file are derived from them and are not the same
thing; {doc}`time-encoding` explains the difference.
