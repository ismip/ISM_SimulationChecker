# Ice Sheet Simulation compliance checker

The script checks the compliance of a simulation dataset according to criteria, which are related to:

* naming conventions
* admissible numerical values,
* spatial definition of the grid (different for AIS vs GrIS),
* time recording dependent of the experiments.

The compliance criteria of output variables and experiments are defined in a separate csv files. 

=> For ISMIP7 simulations, the criteria are following the conventions defined on the [ISMIP7 webpage](https://www.ismip.org/). The associated csv file is [ismip7_criteria.csv](https://github.com/ismip/ISM_SimulationChecker/blob/main/ismip7_criteria.csv)

=> For ISMIP6 simulations, the criteria are following the conventions defined in the [ISMIP6 wiki](https://www.climate-cryosphere.org/wiki/index.php?title=ISMIP6-Projections-Antarctica#Appendix_1_.E2.80.93_Output_grid_definition_and_interpolation). The associated csv file is [ismip6_criteria.csv](https://github.com/jbbarre/ISM_SimulationChecker/blob/main/ismip6_criteria.csv)

=> For ISMIP6 2300 file name convention: check carefully the section _A2.1 File name convention_ of the [ISMIP6 2300 wiki](https://www.climate-cryosphere.org/wiki/index.php?title=ISMIP6-Projections2300-Antarctica)

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

### Test the code

1. Conda users: activate the isschecker environnement: `> conda activate isschecker`.
   For others, be sure that the dependencies specified in the YML file [isschecker_env.yml] (https://github.com/ismip/ISM_SimulationChecker/blob/main/isschecker_env.yml) are installed.

2. In a terminal, run the script: `> python compliance_checker.py`. A progression bar appears in the terminal and shows the progression.

3. Without any changes, the script checks the `test` directory, which contains a single file. After processing the check, open the *compliance_checker_log.txt* file created in the `test` directory. The compliance checker raises errors because the test data is just a short extraction of a complete dataset.

*************************************************

### How to launch a compliance check ?

1. In a terminal, run the script with the source path and experiment set:
`> ./compliance_checker.py --source-path ./test --experiment-set ismip6`

2. Use `--experiment-set ismip6_ext` to test the ISMIP6 extension (2300) experiment set.

3. The script creates a *compliance_checker_log.txt* file in the source path, which reports the errors and warnings.
