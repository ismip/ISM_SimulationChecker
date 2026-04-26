# Ice Sheet Simulation compliance checker

The script checks the compliance of a simulation dataset according to criteria, which are related to:

* naming conventions
* admissible numerical values,
* spatial definition of the grid (different for AIS vs GrIS),
* time recording dependent of the experiments.

The compliance criteria of output variables and experiments are defined in a separate csv files. 

=> For ISMIP7 simulations, the criteria are following the conventions defined on the [ISMIP7 webpage](https://www.ismip.org/). The associated csv file is [ismip7_criteria.csv](https://github.com/ismip/ISM_SimulationChecker/blob/main/ismip7_criteria.csv)

*************************************************

### Python and dependencies

The code has been developed with python 3.9 and the following modules:

* os
* xarray
* cftime
* numpy
* pandas
* datetime
* tqdm

=> Conda users can install the **isscheck** environnment with the YML file [isschecker_env.yml](https://github.com/ismip/ISM_SimulationChecker/blob/main/isschecker_env.yml).
`> conda env create -f isschecker_env.yml`


*************************************************

### How to launch a compliance check

1. Conda users: activate the isschecker environment: `> conda activate isschecker`.

2. Run the checker with the path to your CORE directory and an experiment set:
   ```
   python compliance_checker.py --source-path ./Models/GrIS/ISMIP7/SYNTH1/CORE --experiment-set ismip7_xyt
   ```
   Use `--experiment-set ismip7_scalars` for scalar-only variables, or `ismip7` for both.

3. The script creates a `compliance_checker_log.txt` file in the source path reporting all errors and warnings.


*************************************************

### Generate synthetic test files

`test/generate_test_files.py` creates ISMIP7-style NetCDF test files with synthetic data. See [test/README.md](test/README.md) for full options and examples.

Quick start:
```bash
conda activate isschecker
python test/generate_test_files.py --grid GrIS_16000m --scenario ctrl --xyt --nyears 286 --start-year 2015
```
