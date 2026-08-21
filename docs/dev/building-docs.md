# Building the documentation

These pages are [Sphinx](https://www.sphinx-doc.org/) with
[MyST](https://myst-parser.readthedocs.io/), so the sources are ordinary
Markdown, and are published to
<https://ismip.github.io/ISM_SimulationChecker/> by GitHub Actions.

## Build them locally

The docs build needs Sphinx and its extensions, but not the checker itself or
any of its dependencies, so it gets its own small environment:

```bash
conda env create -f ci/docs_env.yml
conda activate isschecker-docs
sphinx-build -W --keep-going -b html docs docs/_build/html
```

Then open `docs/_build/html/index.html`. `-W` turns warnings into errors, which
is what CI does, so a build that is clean here will not fail there; drop it
while you are iterating if you prefer.

## Layout

```
docs/
├── conf.py               Sphinx configuration
├── index.md              landing page
├── getting-started.md    install and first run
├── user/                 for modelers checking a submission
├── dev/                  for people working on the checker
├── _ext/                 Sphinx extensions local to this project
└── _generated/           tables written during the build (not in git)
```

Adding a page means writing the Markdown file and adding it to the `toctree` in
`user/index.md` or `dev/index.md`. A page in neither is a warning, and so a
failed build in CI, which is deliberate: a page nothing links to is a page
nobody reads.

Cross-references between pages use `{doc}` for a whole page — ``{doc}`../user/running` `` — and an
ordinary Markdown link with an anchor for a section within one:
`[Value ranges](errors-and-warnings.md#value-ranges)`. Anchors exist for
headings down to `<h3>`, and are the heading text lowercased with spaces
replaced by hyphens.

## The generated tables

{doc}`../user/data-request` does not contain any tables of its own. They are
written into `docs/_generated/` at the start of every build by
`docs/_ext/data_request_tables.py`, which reads the same two CSV files the
checker reads, and the page pulls them in with `{include}`. Editing the data
request is therefore all it takes to update the documentation of it, and the
two cannot drift apart.

The extension skips a column the CSV does not have rather than failing, so the
docs still build against an older or newer data request; a section that has
nothing to say — the missing-value policies, before that column existed —
simply does not appear.

If you add a column that deserves documenting, add a section to that extension
rather than a table to the page.

## How it is published

`.github/workflows/docs.yml` builds the docs on every push and pull request,
and deploys them to GitHub Pages on pushes to `main`. A pull request therefore
fails if it breaks the docs, but only `main` is ever published.

```{note}
Publishing requires that **Settings → Pages → Build and deployment → Source**
be set to **GitHub Actions** in the repository settings, which needs admin
rights on the repository. Until it is, the build job still runs and still
catches broken docs; the deploy job is what fails.
```
