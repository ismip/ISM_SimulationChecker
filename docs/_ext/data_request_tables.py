"""
Turn the bundled data request CSVs into Markdown tables at build time.

The compliance criteria live in ``isschecker/data/ISMIP7_variable_request.csv``
and ``isschecker/data/experiments_ismip7.csv``, which are the files the checker
itself reads.  Rather than transcribe them into a page that would then have to
be kept in step by hand, this extension writes the tables into
``docs/_generated`` at the start of each build and the pages pull them in with
``{include}``.  The docs therefore describe the criteria the installed checker
actually applies.

Columns the CSV does not have are skipped rather than reported as an error, so
that the docs build against a data request from before a column was added --
``fill_policy``, say -- and gain the section by themselves once it arrives.
"""

from __future__ import annotations

import csv
from pathlib import Path

from sphinx.application import Sphinx
from sphinx.util import logging

logger = logging.getLogger(__name__)

#: Headings for the groups of variables, keyed by the ``Dim`` column.  A value
#: of ``Dim`` that is not listed here still gets a section, headed by the
#: dimensions themselves.
DIM_HEADINGS = {
    'x,y,t': 'Gridded variables (`x,y,t`)',
    'x,y,z,t': 'Three-dimensional variables (`x,y,z,t`)',
    'x,y': 'Time-independent gridded variables (`x,y`)',
    't': 'Scalar variables (`t`)',
}

#: What each value of the ``fill_policy`` column means, in one line.  The full
#: statement of the rules is in the "Missing values and masks" section of
#: {doc}`/user/errors-and-warnings`; this is the reminder that belongs beside
#: the table.
FILL_POLICY_MEANINGS = {
    'forbidden': 'defined everywhere; no missing values anywhere',
    'outside_domain': 'defined throughout the computational domain, including '
    'where there is no ice; missing outside it',
    'no_ice': 'defined only where there is ice (`sftgif > 0`)',
    'no_grounded_ice': 'defined only where there is grounded ice '
    '(`sftgrf > 0`)',
    'no_floating_ice': 'defined only where there is floating ice '
    '(`sftflf > 0`)',
}

#: Written into an empty cell, so that a row never collapses into ambiguity
#: about which column a value belongs to.
EMPTY = '&mdash;'


def _escape(text: str) -> str:
    """Make ``text`` safe to put in a Markdown table cell."""
    return text.strip().replace('|', r'\|')


def _plain(text: str) -> str:
    """Format ``text`` as a table cell, or as an empty one."""
    return _escape(text) or EMPTY


def _code(text: str) -> str:
    """Format ``text`` as a literal in a table cell, or as an empty one."""
    text = _escape(text)
    return f'`{text}`' if text else EMPTY


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    """Build a Markdown table as a list of lines."""
    lines = [
        '| ' + ' | '.join(headers) + ' |',
        '|' + '|'.join(['---'] * len(headers)) + '|',
    ]
    lines += ['| ' + ' | '.join(row) + ' |' for row in rows]
    lines.append('')
    return lines


def _read_csv(path: Path, delimiter: str = ',') -> list[dict[str, str]]:
    with open(path, newline='', encoding='utf-8') as csv_file:
        return [
            {key: (value or '') for key, value in row.items()}
            for row in csv.DictReader(csv_file, delimiter=delimiter)
        ]


def _variable_tables(rows: list[dict[str, str]]) -> list[str]:
    """One table of metadata per group of variables, plus its comments."""
    # The groups the docs know about come first, in the order a reader is
    # likely to want them; any others follow in the order the CSV gives.
    dims = [dim for dim in DIM_HEADINGS if any(r['Dim'] == dim for r in rows)]
    dims += [
        dim
        for dim in dict.fromkeys(row['Dim'] for row in rows)
        if dim not in DIM_HEADINGS
    ]

    lines: list[str] = []
    for dim in dims:
        in_group = [row for row in rows if row['Dim'] == dim]
        heading = DIM_HEADINGS.get(dim, f'Variables with dimensions `{dim}`')
        lines += [f'### {heading}', '']
        lines += _table(
            ['Variable', 'Long name', 'Type', 'Units', 'Mandatory',
             '`standard_name`'],
            [
                [
                    _code(row['Variable Name']),
                    _plain(row['long_name']),
                    _plain(row['Type']),
                    _code(row['units']),
                    _plain(row.get('Mandatory (yes/no)', '')),
                    _code(row['standard_name']),
                ]
                for row in in_group
            ],
        )

        commented = [row for row in in_group if row.get('Comment', '').strip()]
        if not commented:
            continue
        lines += [':::{dropdown} Comments from the data request', '']
        for row in commented:
            lines += [
                _code(row['Variable Name']),
                f': {_escape(row["Comment"])}',
                '',
            ]
        lines += [':::', '']
    return lines


def _value_range_table(rows: list[dict[str, str]]) -> list[str]:
    """The per-region bounds, and how hard a bound each of them is."""
    if 'min_value_ais' not in rows[0]:
        return []
    has_severity = 'range_severity' in rows[0]
    headers = [
        'Variable', 'Units', 'AIS min', 'AIS max', 'GrIS min', 'GrIS max',
    ]
    if has_severity:
        headers.append('Severity')

    table_rows = []
    for row in rows:
        cells = [
            _code(row['Variable Name']),
            _code(row['units']),
            _plain(row['min_value_ais']),
            _plain(row['max_value_ais']),
            _plain(row['min_value_gris']),
            _plain(row['max_value_gris']),
        ]
        if has_severity:
            # An unrecognized value means `error`, which is what the checker
            # does with it, so the table says what would actually happen.
            severity = row['range_severity'].strip().lower()
            cells.append(severity if severity == 'warning' else 'error')
        table_rows.append(cells)

    return _table(headers, table_rows)


def _fill_policy_table(rows: list[dict[str, str]]) -> list[str]:
    """Which variables are allowed missing values, and where."""
    if 'fill_policy' not in rows[0]:
        return []

    by_policy: dict[str, list[str]] = {}
    for row in rows:
        policy = row['fill_policy'].strip()
        if policy:
            by_policy.setdefault(policy, []).append(row['Variable Name'])
    if not by_policy:
        return []

    # The heading is part of the generated file rather than of the page that
    # includes it, so that a data request without the column produces no
    # section at all instead of an empty one.
    return [
        '## Missing values',
        '',
        'Where each variable is defined, and so where a fill value is the '
        'right thing to find, is given by the `fill_policy` column of the '
        'data request; what the checker does about it is described in '
        '[Errors and warnings](errors-and-warnings.md).',
        '',
    ] + _table(
        ['`fill_policy`', 'The variable is', 'Variables'],
        [
            [
                _code(policy),
                FILL_POLICY_MEANINGS.get(policy, EMPTY),
                ', '.join(_code(name) for name in names),
            ]
            for policy, names in by_policy.items()
        ],
    )


def _experiments_table(rows: list[dict[str, str]]) -> list[str]:
    """The year ranges each experiment is allowed to cover."""
    return _table(
        ['Experiment', 'Earliest start year', 'Latest start year', 'End year',
         'Duration (years)'],
        [
            [
                _code(row['experiment']),
                _plain(row['start_year_min']),
                _plain(row['start_year_max']),
                _plain(row['end_year']),
                # `historical` carries -1, which is the file's way of saying
                # that its duration follows from the start year the modeler
                # chose rather than being fixed by the protocol.
                'set by the start year'
                if row['duration'].strip() == '-1'
                else _plain(row['duration']),
            ]
            for row in rows
        ],
    )


def _write_if_changed(path: Path, lines: list[str]) -> None:
    """Write ``lines`` to ``path``, leaving the file alone if it matches.

    Sphinx decides what to rebuild from modification times, so rewriting an
    unchanged file would rebuild every page that includes it on every run.
    """
    text = '\n'.join(lines).rstrip('\n') + '\n'
    if path.exists() and path.read_text(encoding='utf-8') == text:
        return
    path.write_text(text, encoding='utf-8')


def generate_tables(app: Sphinx) -> None:
    """Write the generated tables before Sphinx reads any source file."""
    repo_root = Path(app.srcdir).parent
    generated = Path(app.srcdir) / '_generated'
    generated.mkdir(exist_ok=True)

    variables = _read_csv(repo_root / app.config.data_request_variables_csv)
    experiments = _read_csv(
        repo_root / app.config.data_request_experiments_csv, delimiter=';'
    )
    logger.info(
        'data request: %d variables, %d experiments',
        len(variables),
        len(experiments),
    )

    _write_if_changed(generated / 'variables.md', _variable_tables(variables))
    _write_if_changed(
        generated / 'value-ranges.md', _value_range_table(variables)
    )
    _write_if_changed(
        generated / 'fill-policies.md', _fill_policy_table(variables)
    )
    _write_if_changed(
        generated / 'experiments.md', _experiments_table(experiments)
    )


def setup(app: Sphinx) -> dict[str, object]:
    app.add_config_value(
        'data_request_variables_csv',
        'isschecker/data/ISMIP7_variable_request.csv',
        'env',
        str,
    )
    app.add_config_value(
        'data_request_experiments_csv',
        'isschecker/data/experiments_ismip7.csv',
        'env',
        str,
    )
    app.connect('builder-inited', generate_tables)
    return {
        'version': '1.0',
        'parallel_read_safe': True,
        'parallel_write_safe': True,
    }
