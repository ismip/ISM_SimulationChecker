---
name: review-comments
description: Write a review comment, review findings, or a reply to review feedback on a GitHub pull request. Use when reviewing code, reporting what testing someone else's branch turned up, or answering a reviewer's question.
---

# Review comments

The reader is deciding what to change.

- Put each finding as an inline comment on the line it concerns, one point
  each. That is where colleagues put them, and it is why their review
  bodies are short.
- The review body summarizes: what you ran, and the verdict. Two or three
  sentences.
- Use a list in the body only for requests that span files.
- No section on what already works. One line for all of it, if any.
- Say what you could not check.
- A reply answers the question asked. Quote the question only when the
  thread has moved on since it was put.

## Calibration

Colleagues' review bodies here run 3 to 99 words, 8 at the median: most
are one line of approval, and anything of substance is a comment in the
conversation. That is too few to measure a tail, so take the rule of thumb
from [polaris]: review bodies at 14 words at the median, 55 at the
ninetieth percentile and 239 at the longest; inline comments at 22 to 32
words at the median and 170 at the longest.

[polaris]: https://github.com/E3SM-Project/polaris

## Enough

One request, and the judgment left to the author (#3):

> It may be that 'tests' is the default location for this, but having
> both 'test' and 'tests' seems a bit confusing on first look. Any chance
> we can resolve that. If 'tests' is indeed the standard, we may rename
> 'test' to 'generate' or similar.

An approval that raises a question without blocking on it (#7):

> Hi Xylar, I think this is good to go. We may get some more feedback
> from groups as we go ahead as some bounds are dependent on the forcing,
> input data and model implementation. We could try to give more context
> to the checker stating which checks are hard limits, while others are
> more like yellow flags for the modellers to take a second look at their
> submission.

## Too much

A bot review on #25 spent 455 words on "Pull request overview",
"Changes" and "Reviewed changes", all restating the pull request, before
its two inline findings. One of the two was wrong:

> The comment above `FILL_POLICY_MEANINGS` refers to a "Missing values
> and masks" section in `/user/errors-and-warnings`, but that section
> doesn't exist in this docs tree. This can mislead future maintainers
> when they try to update the generated tables.

The section existed. A finding is checked before it is written, and the
overview is what the pull request description is for.
