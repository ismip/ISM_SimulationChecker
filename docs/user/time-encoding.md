# Time encoding

ISMIP7 uses the standard (Gregorian) CF calendar with time recorded as **days
since 1850-01-01 00:00:00**. The encoding convention differs by variable type:

| Variable type | Time coordinate | Time bounds |
|---|---|---|
| **State (ST)** — snapshots | Jan 1 of year N+1 (= end of year N) | none |
| **Flux (FL)** — annual averages | Jul 1 of year N (mid-year) | Jan 1 of year N → Jan 1 of year N+1 |

For example, a 286-year `ctrl` simulation covering nominal years 2015–2300:

- ST files carry timestamps `2016-01-01` … `2301-01-01`
- FL files carry timestamps `2015-07-01` … `2300-07-01`, with bounds
  `[2015-01-01, 2016-01-01]` … `[2300-01-01, 2301-01-01]`

The filename year range (`YYYY-YYYY`) always refers to the **nominal simulation
years** (2015–2300 in the example above), regardless of variable type. The
checker accounts for this when validating the filename against the time axis.

Which variables are ST and which are FL is given in
[the data request](data-request.md#variables), and the nominal year range each
experiment may cover is given under
[Experiments](data-request.md#experiments).

## Snapshot variables (`x,y,z,t`, e.g. `litemp`)

`x,y,z,t` variables carry a sparse set of ST snapshots rather than a full
annual time series. The required snapshot nominal years depend on the
experiment type:

| Experiment | Required snapshots |
|---|---|
| `historical` | first year of run, 1900 (if in range), last year of run (2014) |
| projection (e.g. `ssp585`, `ctrl`) | 2100, 2200, 2300 (each if within the experiment's year range) |

Together, a `historical` run and a projection provide snapshots at 1900, 2014,
2100, 2200 and 2300, plus the first year of the historical run. The first year
is required only for `historical`, whose start year the modeler chooses; a
projection's initial state is the historical run's final state, already
reported as historical's last-year snapshot.

A **missing** required snapshot is an error. A snapshot the experiment does not
call for is a **warning**: the data request specifies these years as a minimum
set, so over-delivering 3D temperature is not non-compliance, but a year nobody
asked for is usually a sign that something was written by mistake. (The annual
time axis is treated the other way round — an extra year there is an error —
because that axis is pinned end to end by `experiments_ismip7.csv`, so an extra
year means the file does not match the experiment it names.)

The filename year range for `litemp` reflects the full simulation year range
(e.g. `2015-2300`), not the first/last snapshot year, and the annual cadence
checks do not apply.

```{note}
**A snapshot at 2000 is not required.** Earlier versions of the documentation,
the checker and the generator all required one; `ISMIP7_variable_request.csv`
does not ask for one. A file carrying one is reported as an unrequested
snapshot — that is, warned about and not failed — until
[issue #12](https://github.com/ismip/ISM_SimulationChecker/issues/12) settles
it. Files written to the earlier guidance still pass.
```

## Lookup tables

Reference lookup tables are available in the companion repository
[`ismip7-time-encoding`](https://github.com/ismip/ismip7-time-encoding).
