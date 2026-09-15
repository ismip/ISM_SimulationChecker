# Time encoding

ISMIP7 uses the standard (Gregorian) CF calendar with time recorded as
**days since 1850-01-01 00:00:00**. State and flux variables are stamped
differently:

| Variable type | Time coordinate | Time bounds |
|---|---|---|
| **State (ST)**, snapshots | Jan 1 of year N+1 (the end of year N) | none |
| **Flux (FL)**, annual averages | Jul 1 of year N (mid-year) | Jan 1 of year N to Jan 1 of year N+1 |

For a 286-year ctrl run covering nominal years 2015 to 2300:

- ST files carry timestamps 2016-01-01 to 2301-01-01
- FL files carry timestamps 2015-07-01 to 2300-07-01, with bounds
  [2015-01-01, 2016-01-01] to [2300-01-01, 2301-01-01]

The year range in the file name is always the **nominal** years, 2015-2300
here, whatever the variable type. The checker allows for this when it
compares the name against the time axis.

Which variables are ST and which are FL is given in
[the data request](data-request.md#variables), and the nominal years each
experiment may cover under [Experiments](data-request.md#experiments).

## Snapshot variables (x,y,z,t, such as litemp)

Three-dimensional variables carry a few ST snapshots rather than an annual
series. Which nominal years are required depends on the experiment:

| Experiment | Required snapshots |
|---|---|
| historical | first year of the run, 1900 (if in range), last year of the run (2014) |
| projection (ssp585, ctrl, ...) | 2100, 2200, 2300 (each if within the run) |

Together, a historical run and a projection give snapshots at the first
historical year, 1900, 2014, 2100, 2200 and 2300. A projection's initial
state is the historical run's final state, already reported as historical's
last snapshot.

A **missing** required snapshot is an error. A snapshot the experiment does
not call for is a **warning**: the request gives these years as a minimum,
so over-delivering is not non-compliance, but a year nobody asked for is
usually a sign that something was written by mistake. The annual time axis
is treated the other way round, an extra year there being an error, because
that axis is pinned end to end by the experiment.

The year range in a litemp file name is the full run, 2015-2300 say, not the
first and last snapshot years.

```{note}
**A snapshot at 2000 is not required.** Earlier versions of the
documentation, the checker and the generator all required one; the data
request does not ask for one. A file carrying one is warned about and not
failed, until [issue #12](https://github.com/ismip/ISM_SimulationChecker/issues/12)
settles it. Files written to the earlier guidance still pass.
```

## Lookup tables

Reference lookup tables are in the companion repository
[ismip7-time-encoding](https://github.com/ismip/ismip7-time-encoding).
