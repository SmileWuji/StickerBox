---
name: sticker-tagging
description: How to add a sticker to a sticker box with good tags. Use when adding stickers, for the order of work, the vocabulary rules, and which reference sources to use; the category skills (tag-text, tag-emotion, tag-character-series, tag-visual) hold the details.
---

# Adding a sticker, with tags

The `sticker-box` skill covers the commands. This skill covers what to write.

## Order of work

1. Read the box's `README.md`: required fields and tags, the vocabulary, the "To agents" notes.
2. `sticker-box stage <file> --json`. If `file_problems` or a `duplicate` is reported, stop:
   convert the file or skip it.
3. Look at the image. For an animation, look at `sticker-box frames <ref> --json` instead.
4. Fill each part with its skill: the text on the image (`tag-text`), the feeling
   (`tag-emotion`), who and from what (`tag-character-series`), what is shown (`tag-visual`).
5. Write the `note`: one sentence on when you would send it, in the box's language. This is what
   a later search for a reply will hit, so name the situation: "when someone asks a question
   that answers itself", not "funny".
6. `sticker-box commit <ref> ... --json`. Fix every reported problem and commit again.

## Vocabulary

The box keeps one vocabulary, in one language (the README says which). The goal is that the
same idea always gets the same tag.

- Reuse an existing tag whenever one fits; look it up in the README's vocabulary. A tag that
  differs only by a particle or punctuation (无语 and 无语了) is the same tag.
- A new tag needs a definition: `--define emotion=嫌弃 "看不上对方，带点鄙视"`. Write the
  definition so another agent would pick the same tag for the same image.
- When `commit` refuses an unknown tag it lists `suggestions`; take one if it fits.
- In a locked vocabulary, new tags need `sticker-box tag new` and should be rare.
- Text on the image stays in its original language. A meme phrase that only exists in another
  language may stay in it (`tag new ... --lang ja`).

## Reference sources

Use only a few sources, in a fixed order, and write the box's choice into its notes when you
bootstrap it (`sticker-box notes set --stdin`), so every agent uses the same ones:

- Names of works and characters: [bangumi-data](https://github.com/bangumi-data/bangumi-data)
  first for anime, games and related subculture (it has no memes), then Wikipedia, then IMDb
  for live action.
- Example images, when you are unsure what something looks like (not reverse image search):
  Safebooru, Giphy, Pinterest, in the order the box's notes give.

## Licence and source

`--license` is required: the pack's or artist's licence if stated, otherwise `unknown`. Put the
pack link or page in `--source` when you have it. A pack the sticker came from is also a tag
(`pack=<name>`).
