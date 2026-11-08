# Build decisions (2026-11-08)

Decisions made while building without the owner, per the agreement of 2026-11-08: pick the option
most consistent with the design notes, record it here with the reason, flag it in `AGENTS.md`
under "For the owner", continue. Each entry says what to change if the owner disagrees.

## M1

1. **Rollback journal, not WAL.** WAL keeps `box.sqlite3-wal` and `-shm` beside the database
   while any connection is open, which breaks the agreed four-entry tree, and WAL misbehaves on
   network and NTFS mounts. The default rollback journal with a 30 s busy timeout handles several
   agent sessions at this scale. To change: one pragma in `db.connect`.
2. **Telegram preset formats.** Telegram's current docs allow static stickers as WEBP or PNG and
   give no size limit for them; the preset accepts both and caps them at 512 KB (the old Bot API
   limit) as this tool's own choice. Animated WebP is not a Telegram sticker format, so the preset
   refuses it; WEBM must be VP9, at most 3 s, 30 fps, 256 KB, no audio. To change:
   `policy set files`.
3. **`text` and `note` are fields, not tag categories.** The design listed "text" and "usage note"
   among the sticker categories, but both are free text, not vocabulary. In `telegram-sticker`,
   `text` is required and may be empty (so the agent must have read the image, and "no text" is
   an explicit answer), and `note` is required. Fields have `required` and `allow_empty`.
4. **Category names are identifiers, in English** (`emotion`, `character`, `series`, `visual`,
   `pack`), and the text the tool itself writes into `README.md` is English. Tag values,
   definitions and descriptions are in the box's language.
5. **An eighth rule kind, `analysis`.** The gallery should not pay for OCR on every image, so
   whether `stage` runs the RapidOCR hint, and the keyframe parameters, are policy:
   `{"ocr_hint", "keyframe_drop_thr", "max_keyframes", "sift_keyframes"}`.
6. **Every tag belongs to a category, even in a free vocabulary.** The gallery and buffer presets
   have one category, `tag`, set as the default, so `--tag 无语` works without a category there.
