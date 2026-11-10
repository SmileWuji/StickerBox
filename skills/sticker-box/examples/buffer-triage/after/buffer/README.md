# Sticker box

> **Do not change this directory by hand.** Add, change and remove images only with the `sticker-box` tool (`sticker-box --box <this directory> --help`). This file is generated and is rewritten after every change.

## About this box

- Preset: `buffer`
- Language of tags, definitions and descriptions: `en` (text read off an image stays in its original language)
- Created: 2026-01-15T09:30:00Z
- Images: 0, 0.0 MB

Description (written by whoever created the box):

> images from the chat, kept for an hour

## Using this box

- Find images: `sticker-box search <words>` (several words separated by spaces or `|` match any of them).
- Read an animation in one picture: `sticker-box frames <ref>` writes a contact sheet of its keyframes.
- Add an image: `sticker-box stage <file>`, look at what it reports, then `sticker-box commit <ref> --license <license>`.
- Change or remove one: `sticker-box edit <ref> ...`, `sticker-box remove <ref>`. Every command has `--help`; add `--json` for machine-readable output.

## Rules

The tool enforces these when an image is added or changed.

### Files

- Any supported format (WEBP, PNG, JPEG, GIF, WEBM), at any size.

### Fields

- `license` (required): Licence of the image; 'unknown' when it cannot be found out.
- `source` (optional)
- `text` (optional)
- `description` (optional)
- `note` (optional)

### Tags

- `tag` (optional, one or more values): Free-form tags.
- Vocabulary is free: any tag may be used and is created on first use.
- A tag given without a category goes into `tag`.

### Duplicates

- Identical files are never stored twice. Images within 6 bits of perceptual hash count as near-duplicates.
- Duplicates and related images are reported, never refused or removed by the tool: each report comes with suggested `sticker-box remove` commands, and whoever adds the image decides what to keep.

### Limits and cleanup

- Images expire 60 minutes after they are added and are removed by `sticker-box clean`.
- Staged files older than 60 minutes are removed by `sticker-box clean`.

## Vocabulary

Tags by category, most used first. Values and definitions are written by the people and agents using the box.

### `tag`

Meaning: Free-form tags.

No tags yet.

## To agents

Notes from the agents that use this box, such as which reference sources to prefer. They are the agents' own preferences; the tool stores them and never acts on them. Change them with `sticker-box notes set`.

No notes yet.

## Layout

- `persistent/`: the images, as `<yyyymm>/<yyyymmdd>-<sha256>.<ext>`, dated by the day each was first added.
- `temporary/`: staged files waiting to be committed, analysis sidecars and contact sheets; may be emptied at any time.
- `box.sqlite3`: the index. Tables: `item` (one row per image), `item_tag`, `tag`, `tag_alias`, `item_field`, `keyframe`, `relation` (duplicates and crops), `feature` (local features), `policy_rule`, `policy_log`, `vocab_log`, `meta`.
