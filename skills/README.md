# Skills for agents that use sticker-box

Generic instructions to copy into an agent's skill folder and adapt (translate them, rename
paths, drop what the agent does not need).

| skill | for | needs |
|---|---|---|
| `sticker-box` | operating the tool: find, add, change, remove, read animations; its `workflows/` cover tagging, buffer triage, gallery maintenance, vocabulary cleanup and policy changes, and `examples/` shows each on real boxes | every agent |
| `tag-text` | reading the text on an image, with the JSON answer it must produce | agents that tag |
| `tag-emotion` | the `emotion` category | agents that tag |
| `tag-character-series` | the `character` and `series` categories, with reference sources | agents that tag |
| `tag-visual` | the `visual` category | agents that tag |

The `tag-*` skills are each the whole prompt of one narrow question, which is how they were
benchmarked (`261109-SKILL-BENCHMARKS.md`); keep them separate. They follow the
`telegram-sticker` preset. A box with other categories needs its own category skills; write them
the same way: what the category is for, how to decide, what to avoid, examples.

`sticker-box/examples/` is built by `scripts/make_skill_examples.py` from each `commands.sh`
with images drawn for it, and `tests/test_skill_examples.py` re-runs every example.
