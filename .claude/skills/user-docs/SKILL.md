---
name: user-docs
description: Write or revise anything a modeler reads. That is docs/user/, docs/getting-started.md, README.md, the --help strings and the checker's messages. Use when documenting a check, an option or a convention, or wording a finding. Not for docs/dev/.
---

# User documentation

The reader is a modeler with a submission to check and a log in front of
them. They do not read the code, and English may not be their first
language.

- Say what to do, then show what they will see: the command, then the
  log lines it produces. The natural mistake, shown with the output it
  gives, teaches more than a rule against it.
- Show a path or a file name as it is, annotated, not as a template with
  field names. A template is how a modeler came to pass the wrong
  directory (ismip/ismip7-scalar-processing#10).
- Backticks are for what the reader types: commands, options and their
  values. Paths, file names, variable names and attribute names go in
  plain text.
- Say what the checker does, not why it was designed that way. Cut any
  sentence whose job is to justify the one before it.
- Each thing is explained on one page. Other pages link to it with
  `{doc}` rather than explaining it again.
- Pages go in the order the reader meets things: install, lay out the
  files, run, read the log.
- A `--help` string says what the option takes, gives an example value
  where the form is not obvious, and ends with the default in
  parentheses.
- A finding names what is wrong and what was expected, in the vocabulary
  of the data request, then stops. At most one thing to check.

## Calibration

#30 rewrote these pages to this standard. Outside code blocks, the README
and the user pages went from 4800 words to 3900, from 186 backticked
spans to 65, and from 27 words per sentence to 23, and they gained three
blocks of checker output. Hold those.

## Enough

The installation note, after #30:

> `mamba` and `micromamba` work the same way. If your conda is set up
> with the `defaults` channel, add `--override-channels`; packages from
> the two channels do not mix.

The natural mistake, with what it produces:

> Pointing the checker at the model directory instead,
> Models/GrIS/VUW/PISM1, gets you:
>
> ```
> ERROR: No .nc files found in directory 'Models/GrIS/VUW/PISM1'. Please check your --source-path argument.
> ```

A help string:

> Which files to look for: ismip7_xyt for the gridded variables,
> ismip7_scalars for the time series, ismip7 for both (default:
> ismip7_scalars).

## Too much

The same installation note before #30, each instruction followed by its
justification:

> `mamba` and `micromamba` work the same way; substitute either for
> `conda` if you prefer. If your conda is configured with the `defaults`
> channel, add `--override-channels` so a package cannot be pulled from
> it: builds from the two channels are not interchangeable, and mixing
> them is a good way for two people to get different results from the
> same files.

## Described, not shown

The layout before #30, as a template the reader has to fill in:

> The `--source-path` is one set-counter directory — the leaf of the
> `Models/{GrIS|AIS}/ISMIP7/{group}/{model}/{set_counter}` layout —
> because that is the unit a submission is checked in.

After, as a tree the reader can hold beside their own:

> ```
> Models/GrIS/
> └── VUW/                       <-- group
>     └── PISM1/                 <-- model
>         └── CORE/              <-- experiment group
>             └── C001/          <-- set counter: this is --source-path
>                 ├── lithk_GrIS_VUW_PISM1_m001_CESM2-WACCM_f001_historical_C001_1960-2014.nc
>                 └── ...
> ```

The same help string before #30, which names the values and says nothing
about which to pick:

> Variable list to apply: ismip7_xyt, ismip7_scalars, or ismip7 (both).
