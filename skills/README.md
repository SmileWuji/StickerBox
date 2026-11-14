# Skills for agents that use sticker-box

Generic instructions to copy into an agent's skill folder and adapt (translate them, rename
paths, drop what the agent does not need).

| skill | for | needs |
|---|---|---|
| `sticker-box` | operating the tool: find, add, change, remove, read animations; its `workflows/` cover tagging, buffer triage, gallery maintenance, vocabulary cleanup and policy changes, and `examples/` shows each on real boxes | every agent |
| `tag-text` | reading the text on an image, with the JSON answer it must produce | agents that tag |
| `tag-emotion` | the `emotion` category | agents that tag |
| `tag-character-series` | the `character` and `series` categories, with reference sources and a way to compare a picture with reference pictures (`compare.sh`: curl, jq, ImageMagick) | agents that tag |
| `tag-visual` | the `visual` category | agents that tag |
| `safebooru` | searching safebooru.org by tag: how a name is spelled there, what a character looks like, where a picture came from (`booru.py`, standard library; Pillow for sheets) | agents that name characters; network access |

The `tag-*` skills are each the whole prompt of one narrow question, which is how they were
benchmarked (`261109-SKILL-BENCHMARKS.md`); keep them separate. The reference-picture section of
`tag-character-series` and the sources named in its description came later from QQBot and were
not part of that benchmark.

An agent reads a skill only when something makes it think of it. In QQBot's logs the `tag-*`
skills were read in every session whose prompt named them, and two skills it was expected to
find by itself were never read in chat. So name the skills a task needs in the prompt that
starts it (as the `sticker-box` skill's task table does for the `tag-*` skills), and put the
words the agent will be thinking of into each description. They follow the
`telegram-sticker` preset. A box with other categories needs its own category skills; write them
the same way: what the category is for, how to decide, what to avoid, examples.

`sticker-box/examples/` is built by `scripts/make_skill_examples.py` from each `commands.sh`
with images drawn for it, and `tests/test_skill_examples.py` re-runs every example.
