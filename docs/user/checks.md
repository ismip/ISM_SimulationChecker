# What the checker checks

Every file is validated in five categories, and the log reports findings under
these same headings.

## 1. Naming

The file name is parsed and each of its fields checked: variable name, region
field, ISM member id (`mNNN`), ESM name (CMIP6/CMIP7 registry), forcing member
id (`fNNN`), set counter (`[C|E|P]NNN`), and year range (well formed
`YYYY-YYYY`; what the range *means* is checked under [Time](#4-time)).

Inside the file: the variable the file name names is the one the file contains,
with the dimensions the data request asks for, in the conventional
`(time, z, y, x)` order, and the file holds nothing else beyond its coordinates
and the companion variables CF lets them name (`bounds`, `grid_mapping`,
`coordinates`, `cell_measures`, `ancillary_variables`) — anything further is a
warning.

## 2. Numerical

Units match the data request, in any UDUNITS spelling: `m2`, `m^2` and `m**2`
are all accepted, as are `kg m-2 s-1`, `kg.m-2.s-1` and `kg/m2/s`. Every value
is either a finite number or the declared `_FillValue`, so a bare NaN is never
how a file says "missing". All values lie within the allowed min/max range for
the relevant region, and the array is not entirely fill values.

The ranges themselves, per variable and per region, are listed in
{doc}`data-request`.

## 3. Spatial

*(`x,y,t` variables only)* Grid corners lie within the expected AIS or GrIS
extents; the resolution is one of the allowed values; and x and y cell size are
equal.

## 4. Time

The time dimension is present, unlimited, and monotonically increasing; the
file name's year range is one the experiment allows; and the time axis is
**exactly** the axis the experiment calls for.

For `x,y,t` and `t` variables that means every nominal year from
`experiments_ismip7.csv`, each carrying the timestamp its ST/FL convention
prescribes. For `x,y,z,t` variables it means the required set of sparse
snapshots. Both conventions are described in {doc}`time-encoding`.

## 5. Attributes

Required global and coordinate attributes are present and have correct values;
`standard_name` matches the data request; `_FillValue` equals the NetCDF4
default for the variable's dtype; the variable is float32, and so is the time
coordinate (a warning — one number per record cannot inflate a file);
`scale_factor` and `add_offset` are not allowed.

## How far a file gets

Every file is checked as far as it can be. A naming problem stops the other
checks only where it leaves them nothing to read — a missing `x` or `y`
dimension, or a file that does not contain the variable its name promises.
Everything else (a mistyped ESM name, a malformed year range, an unrecognized
region) is reported and the file is checked on, so one run tells you everything
that is wrong rather than only the first thing. An unrecognized region costs
just the checks that depend on it: value range, grid extent and resolution, and
`crs`.

## Where the criteria come from

Compliance criteria are defined in
`isschecker/data/ISMIP7_variable_request.csv` (variable metadata) and
`isschecker/data/experiments_ismip7.csv` (valid experiment year ranges and
durations). Together with the grid definitions in `isschecker/data/gdfs/`,
these files are bundled with the package, so the checker applies the criteria
of the release you installed. {doc}`data-request` lists what they currently
say.
