# Skills for agents that use sticker-box

Generic instructions to copy into an agent's skill folder and adapt (translate them, rename
paths, drop what the agent does not need). Two kinds:

| skill | for | needs |
|---|---|---|
| `sticker-box` | operating the tool: find, add, change, remove, read animations | every agent |
| `gallery-maintenance` | duplicates, limits and cleanup of a gallery or buffer | agents that keep a gallery |
| `sticker-tagging` | the order of work when adding a sticker, and the vocabulary rules | agents that tag |
| `tag-text` | reading the text on an image, with the JSON answer it must produce | agents that tag |
| `tag-emotion` | the `emotion` category | agents that tag |
| `tag-character-series` | the `character` and `series` categories, with reference sources | agents that tag |
| `tag-visual` | the `visual` category | agents that tag |
| `vocab-cleanup` | the pass that merges near-twin tags and locks the vocabulary | the agent that curates |

The category skills follow the `telegram-sticker` preset. A box with other categories needs its
own category skills; write them the same way: what the category is for, how to decide, what to
avoid, examples.
