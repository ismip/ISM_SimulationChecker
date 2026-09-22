---
name: testing-comments
description: Write a Testing comment on a pull request, recording what was run and what the results were. Use after running the tests, building the docs or running the checker for a PR.
---

# Testing comments

What you ran, and whether it passed.

- Name the command and where it ran, in one sentence: `pytest tests` in
  the `isschecker` environment, `sphinx-build -W`, the checker on
  generated or real files.
- Say the result: the count that passed, or the log lines that matter.
- If the golden log was regenerated, say so, and what changed in it.
- Paste output only when the reader needs to see it, and then do not
  restate it in prose.
- Failures unrelated to the branch go under their own heading at the end.

## Calibration

The two Testing comments colleagues wrote here (#1, #3) are 40 to 100
words, most of it pasted output. [Polaris] measured its Testing comments
at 21 to 43 words, and a recent agent-written one there at 606.

[polaris]: https://github.com/E3SM-Project/polaris

## Enough

Pasted output and one line of verdict (#3):

> ```
> $ conda activate isschecker
> (isschecker) xylar@katara:~/code/ISM_SimulationChecker/add-ci-and-unit-tests$ pytest tests
> ============================= test session starts ==============================
> collected 6 items
>
> tests/test_compliance_checker.py ......                                  [100%]
>
> ============================== 6 passed in 1.04s ===============================
> ```
> Works locally for me at least.

Three things run, one line each (#30):

> ## Testing
>
> - `sphinx-build -W --keep-going` builds clean
> - `pytest`: 173 passed
> - Ran the checker on generated test files to take the log excerpt and
>   the two error messages in the docs from real output

## Too much

An agent-written comment in polaris put the table in, then said the same
thing again in prose:

> Every task now runs to completion. The five diffs are all of the form
> `File ... does not exist`: `main` crashed before writing those outputs,
> so there is nothing to compare against. Every comparison that had a file
> on both sides passed. A clean like-for-like comparison for those five
> tasks needs a fresh baseline once this lands.
