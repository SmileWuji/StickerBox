---
name: tag-character-series
description: Name who is pictured and the work they come from, with the character and series categories. Use when adding stickers that show a recognisable character; covers reference sources and when to leave the tags out.
---

# Character and series

`character` is who is pictured; `series` is the work or franchise they come from. Both are
optional. A wrong name is worse than none: it sends every later search astray.

## Where names come from, in this order

1. **The source.** The pack's title or page, the artist's caption, the file's origin. A pack
   named after a character settles it.
2. **The reference sources listed in the sticker-tagging skill**, in the order the box's notes
   give: [bangumi-data](https://github.com/bangumi-data/bangumi-data) for anime, games and related
   subculture, then Wikipedia, then IMDb for live action. Never a site the notes add. Use the source's canonical name in the
   box's language; put other spellings in as aliases (`tag alias`).
3. **What you see**, only when you recognise the character for certain. Vision is unreliable at
   naming characters: in testing, a capable model named the wrong character far more often than
   the right one. Hair colour and outfit are not enough.

When unsure, leave both tags out and mention the guess in `--description` ("looks like a
character from …, unconfirmed").

## Rules

- One tag per character, by canonical name; nicknames become aliases.
- `series` is the original work, not a season or a spin-off, unless the box's notes say
  otherwise.
- Original characters of an artist or a sticker pack: use the name the pack gives, and
  `series` only if the pack names one.
- Real people: only if the source names them, and only public figures in public roles.

## Examples

- A pack page titled after a game's mascot, sticker shows that mascot → `character=<name>`,
  `series=<game>`
- An unnamed chibi girl with cat ears, no source → no character or series tags
