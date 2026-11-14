---
name: tag-character-series
description: Name who is pictured and the work they come from, with the character and series categories. Use when adding stickers that show a recognisable character; covers how to find one from the other, the reference sources (bangumi.tv, safebooru), and when to leave the tags out.
---

# Character and series

`character` is who is pictured; `series` is the work or franchise they come from. Both are
optional. A wrong name is worse than none: it sends every later search astray. Find the two
together, because each one narrows the other.

## Sources, in this order

1. **The source of the sticker.** The pack's title or page, the artist's caption, the file's
   origin. A pack named after a character or a work settles that part. Pack and folder names
   are often romanised, shortened or carry an uploader's suffix (`sato_hanako_by_SomeBot`,
   `MGTalk2`): search the likely name on bangumi.tv before deciding the pack names nothing.
2. **The reference sources from the `sticker-box` skill's tagging workflow**, in the order the box's notes give:
   - [bangumi-data](https://github.com/bangumi-data/bangumi-data): anime works only (TV, web,
     film, OVA), each with its original title, translated titles (`titleTranslate`, including
     `zh-Hans`) and a link to its page on bangumi.tv. No characters, no games.
   - [bangumi.tv](https://bgm.tv) (also bgm.tv), the site bangumi-data links to: works of every
     kind (anime, games, manga, novels), each with its cast of characters and their Chinese
     names; each character's page lists the works they appear in.
   - Wikipedia, then IMDb for live action.
   - [safebooru](https://safebooru.org), through the `safebooru` skill: what a character looks like
     and the romanised tag a character goes by there (`booru.py tag <name>` gives the spelling and
     post count; `booru.py search <tag> solo --sheet` shows their usual hair, eyes and outfit).
     It names who is drawn, never the Chinese tag: take that from bangumi.tv.
3. **What you see**, only to choose among names a source already gave you. Naming a character
   from the picture alone is unreliable: in testing, a capable model named the wrong character
   far more often than the right one. Hair colour and outfit are not enough.

## Finding both

- **The work is known** (from the pack, or a title on the sticker): find it in bangumi-data, or
  on bangumi.tv when it is not an anime. Its Chinese title is the `series` tag. Then open the
  work's character list on bangumi.tv and pick who is pictured by comparing the image with the
  listed characters' pictures. Their Chinese name is the `character` tag.
- **The character is known but not the work:** their bangumi.tv page lists the works they
  appear in. The `series` is the original work they come from, not a spin-off or a later
  season, unless the box's notes say otherwise.
- **Neither is known:** leave both out. Mention a guess in `--description` ("looks like a
  character from …, unconfirmed"), never in the tags.

## Looking it up

bangumi.tv has an open API; fetch these URLs with whatever web tool you have (no key needed):

1. Find the work: `https://api.bgm.tv/search/subject/<title or part of it>?type=2&responseGroup=small`
   (`type=2` anime, `4` games, `1` books). Each result has `id`, the original `name` and the
   Chinese `name_cn`, which is the `series` tag.
2. Its cast: `https://api.bgm.tv/v0/subjects/<id>/characters`. Ignore entries whose `relation`
   is `闲角` (unnamed extras); choose among `主角` and `配角` by comparing the picture with them.
   Each entry's `images` has picture URLs; if your web tool shows only text, download one to
   look at it.
3. A character's Chinese name: `https://api.bgm.tv/v0/characters/<character id>`, field
   `infobox`, key `简体中文名`. That is the `character` tag.

Do not guess page URLs; search first. If the search finds nothing that fits, leave the tag out.

## Comparing against reference pictures

Choosing among candidates "by comparing pictures" means putting them side by side, not recalling
what a character looks like. Memory gets hair colours and accessories wrong, and stops at the
first name that comes to mind.

1. **Describe before naming.** Hair colour and style, eye colour, headwear (hat, ribbon, horns,
   ears), outfit, what they hold (instrument, weapon, prop), any mascot or pet, the art style,
   and any text, signature or watermark on the image. A small picture (a 160 px chat thumbnail)
   is enlarged first, e.g. `convert <picture> -filter Lanczos -resize 400% zoom.png`, and looked
   at again; hair is often mistaken for a hat at that size.
2. **Two or three candidates, not one.** From the source, the work's cast on bangumi.tv, or the
   features above. Many characters share a hair colour and a hat.
3. **One contact sheet.** `compare.sh <picture> <tag> [<tag> ...]` in this skill's folder (needs
   curl, jq and ImageMagick) puts the picture in row 0 and, for each candidate, three top-scored
   solo all-ages pictures from safebooru.org in its own row, labelled. Tags are safebooru's
   romanised names, family name first (`komeiji_koishi`, `kirisame_marisa`); a wrong tag prints
   similar ones, or look them up with the `safebooru` skill's `booru.py tag <name>`.
   The sheet goes to `$COMPARE_OUT` (default `./character-id`). bangumi.tv's cast `images` serve
   the same purpose when a work has no safebooru tag.
4. **Compare feature by feature**: hair, eyes, the signature accessory and outfit. Different
   artists draw very differently; the character's own features are what must match. All of
   them match → the name holds. Some do not → it is a guess: for tags, leave `character` out and
   mention it in `--description`; try other candidates if you have them.

## When the pack and the picture disagree

A pack named after one character often contains others. Name a character only when the picture
matches that character; the pack name alone is not enough. When they disagree, leave
`character` out (the pack's `series` may still fit). When the face is not visible (only a body,
an outfit, a hand), leave `character` out too: an outfit matching a cast picture is not enough.

## Writing the tags

- Use the canonical name in the box's language (the `zh-Hans` title or name for a Chinese box);
  add other spellings as aliases (`sticker-box tag alias`). A name known only in another script
  keeps it.
- When you create a character tag, name its series in the definition:
  `--define character=<name> "<name>，出自《<series>》"`. Search matches definitions, so a
  search for the series also finds the character's stickers, and later agents see the link.
- One tag per character; a sticker with two characters gets two.
- Original characters of an artist or a sticker pack: use the name the pack gives, and `series`
  only if the pack names one.
- Real people: only if the source names them, and only public figures in public roles.

## Examples

- Pack page titled after an anime, sticker shows one of its girls → `series` from the anime's
  `zh-Hans` title in bangumi-data; `character` chosen from the work's character list on
  bangumi.tv by comparing pictures; definition links the two.
- Pack named after a game mascot → the game on bangumi.tv gives `series` and the mascot's
  Chinese name.
- An unnamed chibi girl with cat ears, no source → no character or series tags.
