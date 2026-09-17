# What the checker checks

Every file is checked in six categories, and the log reports findings under
the same headings.

## 1. Naming

The file name has ten fields, separated by underscores:

```
lithk_GrIS_VUW_PISM1_m001_CESM2-WACCM_f001_ctrl_C001_2015-2300.nc
│     │    │   │     │    │           │    │    │    └ nominal years, YYYY-YYYY
│     │    │   │     │    │           │    │    └ set counter, C/E/P + 3 digits
│     │    │   │     │    │           │    └ experiment
│     │    │   │     │    │           └ forcing member id, f + 3 digits
│     │    │   │     │    └ ESM, from the CMIP6/CMIP7 registry
│     │    │   │     └ ISM member id, m + 3 digits
│     │    │   └ model
│     │    └ group
│     └ region, GrIS or AIS
└ variable
```

Each field is checked. What the year range *means* is checked under
[Time](#4-time).

Inside the file, the variable the name promises is present with the
dimensions the data request asks for, in (time, z, y, x) order. Nothing else
is in the file beyond the coordinates and the companion variables CF lets
them name (bounds, grid_mapping, coordinates, cell_measures,
ancillary_variables). Anything further is a warning.

## 2. Numerical

Units match the data request in any UDUNITS spelling: m2, m^2 and m**2 are
all accepted, as are kg m-2 s-1, kg.m-2.s-1 and kg/m2/s, and K and kelvin.
The comparison is UDUNITS's own, so a string it cannot parse is an error, and
so is a unit at another scale, such as m yr-1 for m s-1. Every value is
either a finite number or the declared _FillValue, so a bare NaN is never how
a file says "missing". Values lie within the range allowed for the region: a
few outside it are a warning, a large share of the field is an error. The
array is not entirely fill values. The ranges are listed in
{doc}`data-request`.

## 3. Spatial

Gridded variables only. The grid corners lie within the expected AIS or GrIS
extent, the resolution is one of the allowed values, and the x and y cell
sizes are equal.

## 4. Time

The time dimension is present, unlimited and increasing. The year range in
the file name is one the experiment allows, and the time axis is **exactly**
the one the experiment calls for: every nominal year, each stamped as its
ST or FL convention prescribes. For x,y,z,t variables it is instead the
required set of snapshots. Both are described in {doc}`time-encoding`.

## 5. Consistency

Gridded variables only. Each file is compared against the files beside it: a
variable is missing exactly where its ice mask says there is no ice, the
variables of the computational domain cover the ice, the grounded and
floating fractions sum to the ice fraction, thickness agrees with the ice
mask, and surface elevation, ice base and bed agree with each other. See
[Checks that compare files](errors-and-warnings.md#checks-that-compare-files).

When a file a check needs is not in the directory, the check says so and is
skipped, so a submission can be checked a part at a time.

## 6. Attributes

Required global and coordinate attributes are present with the right values;
standard_name matches the data request; _FillValue is the NetCDF4 default
for the variable's dtype; the variable and the time coordinate are float32
(a warning for time); and scale_factor and add_offset are not used.

## How far a file gets

Every file is checked as far as it can be. A naming problem stops the other
checks only where it leaves them nothing to read: a missing x or y dimension,
or a file that does not contain the variable its name promises. Everything
else, a mistyped ESM name, a malformed year range, an unrecognized region, is
reported and the file is checked on, so one run tells you everything that is
wrong. An unrecognized region costs just the checks that depend on it: value
range, grid extent and resolution, and crs.

## Where the criteria come from

The criteria are in two CSV files bundled with the package,
ISMIP7_variable_request.csv (the variables) and experiments_ismip7.csv (the
experiments and their year ranges), together with the grid definitions. The
checker applies the criteria of the release you installed, and
{doc}`data-request` lists what they currently say.
