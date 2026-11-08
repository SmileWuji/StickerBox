# M8 acceptance test (2026-11-08)

A fresh general-purpose agent was given only `skills/`, an empty `telegram-sticker` box
(zh-Hans) and 12 stickers from one private pack (with the pack link and "licence unknown"). It
was told not to read source code. Its box stayed in the scratchpad; no image content is recorded
here.

## Result: passed

- Reference-source notes set at bootstrap, as the skills ask.
- 12 of 12 stickers stored, each with text, emotion, character, visual tags, note, description,
  licence, source and a pack tag. No commit was refused.
- 37 tags created; cleanup merged 1 pair, added 4 parent links and 20 aliases; vocabulary locked.
- `check` reported `ok: true`.
- Three reply-style searches: one found the right sticker, one a thin but usable match, one
  correctly found nothing (the pack has no such sticker).

## Friction it reported, and what changed

| friction | change |
|---|---|
| Reference-source notes were circular at bootstrap ("in the order the box's notes give") | sticker-tagging: follow the notes if present, otherwise choose (defaults given) and write them, in the box's language |
| A Latin-only pack and character name drew a script warning, and mixed names like "X酱" did too | the script check warns only when none of the text is in the box language's script; the skill says proper names keep their script and the warning is expected |
| `ocr_hint.noise` was unexplained | tag-text explains it |
| Full- or half-width punctuation and spacing in drawn text were unspecified | tag-text gives the rule |
| "Main reaction first" while the tool stores tags as a set | removed; the skill says order does not matter |
| `tag parent` example failed because the parent did not exist; review then listed the parent as unused and the skill said to retire unused tags | vocab-cleanup creates the parent first and keeps unused parents |
| Low review thresholds produce false pairs with ready merge hints | vocab-cleanup: never run a hint without reading both definitions; an empty list is normal |
| An alias resolved silently | commit and edit warn which tag an alias resolved to |
| A merge reported 0 items retagged when the item already had the target | merge reports `items_already_tagged` and a sentence |
| Searches with words not in the note found nothing | search also matches tag definitions; the note and search guidance say to use the words people would type, with synonyms |
| Search returned `text: null` for an explicitly empty text | search keeps `""` |
| On-image text ranked below every tag match although the skills call it the most important field | text and note matches now score 6 and 4 (exact tag 10, alias 8, partial tag 5) |
| `tag list --help` said "counts", the JSON says `uses` | help text fixed; search help says no words means newest first |

Not changed: search stays literal (no synonyms or meaning). Semantic search would need a model,
which the design leaves to the agent; better notes and aliases are the lever.
