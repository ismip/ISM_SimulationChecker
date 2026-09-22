# ISM_SimulationChecker agent instructions

These instructions apply to the whole repository.

## GitHub pull requests and issues

- Do not hard-wrap. Write each paragraph and each bullet as a single
  line, however long. GitHub wraps them for display, and hard breaks
  make later edits show up as reflowed paragraphs in the diff.
- Start with a paragraph summarizing what the pull request or issue is
  about, then use sections for the detail.
- Use closing keywords for any issue the pull request fixes.
- Do not list individual commits in a pull request description. The
  commits are already on the pull request; describe what the change
  accomplishes as a whole instead.
- Do not describe testing in a pull request description. Testing goes
  in its own `Testing` comment on the pull request.
- Drafts of descriptions, comments and plans are not repository
  content. Never commit one.
- An issue should say what happens, what was expected instead, and
  enough to reproduce it: the checker version, the command, and the log
  lines or the file it was run on.

## Writing for human readers

These rules apply to anything a colleague reads: GitHub comments, pull
request descriptions, issues, plans. Not code comments or commit
messages, where a reader who wants the mechanism is already in the right
place. Per-artifact rules and worked examples are in
`.claude/skills/<artifact>/SKILL.md`, as plain markdown; Claude Code
loads the matching one automatically.

There are two readerships. GitHub prose is read by the checker's
maintainers: developers who know the code's structure and the ISMIP7
data request at a high level. The user documentation, the `--help`
strings and the checker's messages are read by modelers preparing a
submission, who never read the code and may not have English as a first
language. The `user-docs` skill has the rules for them.

Never repeat explanations of existing, unchanged features already
explained in `docs`; link to the relevant page instead. Explanations are
appropriate where there is a change, particularly one of a conceptual
nature, and to highlight nuance that informs the current discussion.

Write less; do not pack the same content into denser sentences. Keep
headings, tables and links. Colleagues mostly write unstructured prose,
and structure is an improvement on it. The problem is length.

- **Lead with the answer.** The first two sentences say what you found,
  changed, or propose. Setup and reproduction go last.
- **One point per paragraph, and few paragraphs.** Colleagues here write
  one to three per comment; agent-written descriptions have run to two
  thousand words. That gap is the complaint. Say each thing once.
- **Do not narrate the mechanism.** The chain of calls, and why the fix
  is right, go in the commit message. Here, say what broke and where to
  look.
- **Cut clauses that qualify rather than inform**, and any sentence whose
  only job is to justify the one before it. One clause per sentence where
  one will do.
- **Use backticks about half as often as feels natural.** They are for
  what a reader would type or grep. Code blocks hold artifacts you did
  not write, never authored prose.
- **One document, one decision.** Anything still relevant after this
  merges is an issue, not a comment.

Sign anything posted to GitHub on someone's behalf:

```
---

*Posted by <agent> on @<user>'s behalf. The testing, analysis and wording
above are AI-authored; please check them accordingly.*
```

Name the agent, not the vendor: `Claude Code`, `Codex`, and so on.
