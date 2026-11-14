# Sticker box

> **Do not change this directory by hand.** Add, change and remove images only with the `sticker-box` tool (`sticker-box --box <this directory> --help`). This file is generated and is rewritten after every change.

## About this box

- Preset: `telegram-sticker`
- Language of tags, definitions and descriptions: `zh-Hans` (text read off an image stays in its original language)
- Created: 2026-01-15T09:30:00Z
- Images: 7, 0.1 MB

Description (written by whoever created the box):

> 聊天用的表情包

## Using this box

- Find images: `sticker-box search <words>` (several words separated by spaces or `|` match any of them).
- Read an animation in one picture: `sticker-box frames <ref>` writes a contact sheet of its keyframes.
- Add an image: `sticker-box stage <file>`, look at what it reports, then `sticker-box commit <ref> --tag emotion=<value> --text <text> --note <note> --license <license>`.
- Change or remove one: `sticker-box edit <ref> ...`, `sticker-box remove <ref>`. Every command has `--help`; add `--json` for machine-readable output.

## Rules

The tool enforces these when an image is added or changed.

### Files

- Accepted formats: WEBP, WEBM, PNG. Convert files before adding them; the box does not convert.
- WEBP: static only; one side exactly 512 px, the other at most 512 px; at most 512 KB.
- WEBM: one side exactly 512 px, the other at most 512 px; at most 256 KB; at most 3 s long; at most 30 fps; codec vp9; no audio.
- PNG: static only; one side exactly 512 px, the other at most 512 px; at most 512 KB.

### Fields

- `text` (required, may be empty): Every piece of text on the image, verbatim, watermarks included; empty when there is none.
- `note` (required): When to send it.
- `license` (required): Licence of the image; 'unknown' when it cannot be found out.
- `description` (optional): What the image shows.
- `source` (optional): Where the image came from, such as a pack link.

### Tags

- `emotion` (required, one or more values): The feeling or reaction the sticker expresses.
- `character` (optional, one or more values): Who is pictured, named after the box's reference sources.
- `series` (optional, one or more values): The work or franchise the character comes from.
- `visual` (optional, one or more values): What is shown: actions, objects, poses, notable details.
- `pack` (optional, one or more values, proper names in any script): A collection the sticker belongs to; a pack is a tag.
- Vocabulary is open: a new tag may be created while adding an image, and must come with a definition. Reuse existing tags whenever one fits.

### Duplicates

- Identical files are never stored twice. Images within 6 bits of perceptual hash count as near-duplicates.
- Duplicates and related images are reported, never refused or removed by the tool: each report comes with suggested `sticker-box remove` commands, and whoever adds the image decides what to keep.

### Limits and cleanup

- Staged files older than 60 minutes are removed by `sticker-box clean`.

## Vocabulary

Tags by category, most used first. Values and definitions are written by the people and agents using the box.

### `emotion`

Meaning: The feeling or reaction the sticker expresses.

| tag | definition | aliases | parent | images |
|---|---|---|---|---|
| 哭 | 流泪、难过 |  |  | 1 |
| 大哭 | 哭得很厉害 |  |  | 1 |
| 开心 | 高兴、愉快 |  |  | 1 |
| 无语 | 无奈到说不出话 |  |  | 1 |
| 无语了 | 说不出话 |  |  | 1 |
| 生气 | 不满、发火 |  |  | 1 |
| 高兴 | 心情好 |  |  | 1 |
| 困惑 | 不明白、摸不着头脑 |  |  | 0 |

### `character`

Meaning: Who is pictured, named after the box's reference sources.

No tags yet.

### `series`

Meaning: The work or franchise the character comes from.

No tags yet.

### `visual`

Meaning: What is shown: actions, objects, poses, notable details.

| tag | definition | aliases | parent | images |
|---|---|---|---|---|
| 圆脸 | 圆圆的脸 |  |  | 7 |

### `pack`

Meaning: A collection the sticker belongs to; a pack is a tag.

No tags yet.

## To agents

Notes from the agents that use this box, such as which reference sources to prefer. They are the agents' own preferences; the tool stores them and never acts on them. Change them with `sticker-box notes set`.

No notes yet.

## Layout

- `persistent/`: the images, as `<yyyymm>/<yyyymmdd>-<sha256>.<ext>`, dated by the day each was first added.
- `temporary/`: staged files waiting to be committed, analysis sidecars and contact sheets; may be emptied at any time.
- `box.sqlite3`: the index. Tables: `item` (one row per image), `item_tag`, `tag`, `tag_alias`, `item_field`, `keyframe`, `relation` (duplicates and crops), `feature` (local features), `policy_rule`, `policy_log`, `vocab_log`, `meta`.
