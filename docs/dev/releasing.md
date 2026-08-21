# Releasing

This page is for maintainers — those with write access to
[the main repository](https://github.com/ismip/ISM_SimulationChecker). If you
are contributing from a fork, nothing here is yours to do; open the pull
request and a maintainer will fold it into the next release.

Modelers get the checker from conda-forge, and conda-forge builds from a tag.
Anything on `main` that has not been tagged therefore does not exist as far as
they are concerned: a check you added, a message you reworded, a variable you
renamed in `ISMIP7_variable_request.csv` — all of it sits in this repository
being invisible to everyone running the tool.

**So tag a release whenever a change reaches `main` that a user would notice.**
That is the rule, and it is deliberately a low bar: new or changed checks, a
change in a finding's severity or wording, a change to the bundled data request
or grid definitions, a new or altered command-line option, a bug fix, or a
widened dependency range. Releases are cheap; a user chasing a discrepancy
against a source checkout that turns out to be six months of untagged changes
is not. Refactorings, tests, CI and documentation-only changes need no release,
though there is no harm in folding them into the next one.

## Cutting a release

1. Bump `version` in `pyproject.toml` following
   [semantic versioning](https://semver.org/) — patch for a fix, minor for a
   new or changed check, major for a change that would fail a submission that
   used to pass — and merge that to `main`.

2. Draft a new
   [GitHub release](https://github.com/ismip/ISM_SimulationChecker/releases/new)
   against `main`. In the tag field, type the new version and choose **Create
   new tag on publish**, so that publishing the release creates the tag: one
   action, and the two can never disagree about which commit they point at.
   Write notes saying what changed for users, then publish.

   The tag is the bare version number — `0.2.0`, no `v` prefix — because the
   feedstock builds its source URL from it, and it must match `version` in
   `pyproject.toml` exactly.

3. Wait for the conda-forge bot to open a version-bump PR on
   [`isschecker-feedstock`](https://github.com/conda-forge/isschecker-feedstock),
   usually within a few hours. Review and merge it; the package appears on
   conda-forge shortly after the build finishes. Merging it needs write access
   to the feedstock, which is separate from write access here — see
   [Maintaining the feedstock](#maintaining-the-feedstock) below.

If the release changed the dependency ranges, edit the feedstock PR before
merging so that the `run:` requirements in `recipe/recipe.yaml` match
`pyproject.toml` and `isschecker_env.yml` — the bot updates the version and
hash, not the requirements. Those three lists are the same constraints written
down three times, and it is worth checking them against one another at each
release.

## Confirming what was published

Finally, and **optionally**, you can confirm what was published rather than
assuming it:

```bash
conda create -n isschecker-test -c conda-forge --override-channels isschecker pytest
conda activate isschecker-test
ismip7-compliance-checker --version    # should print the version you tagged
cd $(mktemp -d) && pytest -v /path/to/ISM_SimulationChecker/tests
```

Run that from a checkout of the tag, not of `main`: the tests come from the
source tree while the package comes from conda-forge, so with `main` checked
out any change made since the tag shows up as a test failure that says nothing
about the release.

It is optional because of the wait. A merged feedstock PR does not put the
package within reach immediately: the build has to finish, and the result then
takes roughly an hour to propagate across the servers `conda` fetches from.
Until it has, `conda create` either cannot find the new version or reports the
old one, and neither means anything is wrong. So this is not a step to sit and
retry — come back to it later in the day, or skip it. The CI in this repository
already runs the full suite against the tagged source at both ends of every
dependency range, and the feedstock runs the recipe's own import and `--help`
tests before the package is published at all, so a release that got that far is
very unlikely to be broken in a way an install check would catch. What it does
catch is the recipe describing something other than what you tagged — wrong
version, a dependency range that never made it into `recipe/recipe.yaml` —
which is worth a few minutes at some point after a release that changed either.

## Maintaining the feedstock

The conda-forge package is built by its own repository,
[`conda-forge/isschecker-feedstock`](https://github.com/conda-forge/isschecker-feedstock),
which is separate from this one and has its own list of maintainers — being a
maintainer here does not make you one there. Only feedstock maintainers can
merge the bot's version-bump PRs, so a release stalls if nobody available has
that access. It is worth having more than one of us on the list.

The list lives in the recipe itself, under `extra: recipe-maintainers:` in
`recipe/recipe.yaml`. To be added, open an **issue** on the feedstock with the
title:

```
@conda-forge-admin, please add user @your-github-username
```

A bot then opens a PR adding you, which an existing feedstock maintainer
merges. GitHub will email you an invitation to the feedstock's team in the
conda-forge organization; **you have to accept it**, or the merge has given you
nothing. This is conda-forge's documented mechanism, described under
[Updating the maintainer list](https://conda-forge.org/docs/maintainer/updating_pkgs/#updating-the-maintainer-list);
leave the bot's PR alone rather than editing it or its commit message, since it
is built to skip a package rebuild.

Those docs also say that asking to be added is not how to introduce yourself to
a feedstock you have no history with — the usual route is to contribute a PR
first. That caveat is about strangers arriving at someone else's package; this
feedstock exists to publish this repository, so a maintainer here asking to be
added to it is expected rather than presumptuous.

[The conda-forge maintainer documentation](https://conda-forge.org/docs/maintainer/)
covers the rest: what the bots do, how to fix a build, and the
[`@conda-forge-admin` commands](https://conda-forge.org/docs/maintainer/infrastructure/#conda-forge-admin-please-add-user-username)
for re-rendering a feedstock and other routine chores. Very little of it is
needed for a package as simple as this one — a pure-Python `noarch` recipe
whose releases are usually nothing more than a version and a hash.
