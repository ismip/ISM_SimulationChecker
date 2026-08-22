# Configuration file for the Sphinx documentation builder.
from __future__ import annotations

import sys
import tomllib
from datetime import datetime
from pathlib import Path

_docs_dir = Path(__file__).parent
_repo_root = _docs_dir.parent

# The extension that turns the bundled data request CSVs into tables lives
# beside this file rather than in the package: it is a documentation tool, and
# nothing installed alongside the checker should depend on it.
sys.path.insert(0, str(_docs_dir / '_ext'))

# -- Project information -----------------------------------------------------

project = 'ISMIP7 Compliance Checker'
author = 'ISMIP contributors'
copyright = f'{datetime.now().year}, {author}'

# Read the version from pyproject.toml rather than from the installed package,
# so that the docs can be built from a checkout without installing anything.
with open(_repo_root / 'pyproject.toml', 'rb') as _pyproject:
    release = tomllib.load(_pyproject)['project']['version']
version = release

# -- General configuration ---------------------------------------------------

extensions = [
    'myst_parser',
    'sphinx_copybutton',
    'sphinx_design',
    'data_request_tables',
]

myst_enable_extensions = [
    'colon_fence',
    'deflist',
    'substitution',
]

# Give every heading down to <h3> an anchor, so that one page can link to a
# section of another page and not merely to its top.
myst_heading_anchors = 3

root_doc = 'index'
templates_path = ['_templates']

# `_generated` holds the tables written by the `data_request_tables` extension.
# They are pulled into a page with `{include}`, so Sphinx must not also build
# them as documents in their own right -- that would warn about a file missing
# from every toctree, and `-W` in CI would turn that warning into a failure.
exclude_patterns = ['_build', '_generated', 'Thumbs.db', '.DS_Store']

# -- Options for HTML output -------------------------------------------------

html_theme = 'furo'
html_title = f'{project} {release}'
html_static_path = ['_static']
html_css_files = ['custom.css']
html_theme_options = {
    'source_repository': 'https://github.com/ismip/ISM_SimulationChecker/',
    'source_branch': 'main',
    'source_directory': 'docs/',
}

# -- Options for the data request tables -------------------------------------

# Both paths are relative to the repository root.
data_request_variables_csv = 'isschecker/data/ISMIP7_variable_request.csv'
data_request_experiments_csv = 'isschecker/data/experiments_ismip7.csv'
