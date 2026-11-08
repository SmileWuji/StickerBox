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

## M2

7. **Matroska files carrying a WebM codec count as WEBM.** One corpus sticker has the DocType
   `matroska` but VP9 video; it is WebM in all but the label. Matroska with VP8, VP9 or AV1 is
   accepted and stored as `.webm`; anything else is refused.
8. **The noise gate drops the Observatory's pack-specific watermark rule** (one third-party
   handle and its OCR misspellings). Any `@handle` still passes, which covers watermarks in
   general without naming a pack in an open-source repo.
9. **Contact sheets are JPEG** (quality 90), cells 256 px up to 16 keyframes and 192 px beyond,
   at most 8 columns. `analyze <path>` exists as a box-free command so an agent can inspect a
   file before staging it.
10. **Frames are worked on at most 1600 px on the long side**, which keeps memory bounded for big
    gallery images; pHash is unaffected (it shrinks to 32 px anyway).

## M3

11. **Four kinds of pHash relation.** `near_duplicate` (still and still, or two animations whose
    first frames match), `frame_of` / `has_frame` (a still that is a frame of an animation),
    `shares_frames` (two animations sharing at least 30% of the new one's keyframes, and at least
    two). Only `near_duplicate` counts as a duplicate for `on_duplicate: reject`; the others are
    links the design asked for ("动图+抽帧"). Near-uniform frames (at most 4 or at least 60 bits
    set) are ignored, since every blank frame matches every other.
12. **Relations are always recorded at commit.** They are facts about the box. So `report` and
    `link` currently behave the same (stored, listed in the commit result); only `reject`
    differs. Collapse the two values later if no difference is wanted.
13. **`--auto-cleanup` on `commit` plans its removals first and runs them only after every other
    check has passed,** so a commit refused for a missing tag never deletes anything. On `stage`
    (which writes no row) it removes right away, as the caller asked.
14. **`stage` with several files keeps going** past a bad one, reports each file's status, and
    exits 1 if any failed. A limit error stops it at once (exit 3).
15. **Tag values** are one line, at most 64 characters, without `|` (the search separator). An
    input that differs from an existing tag only in case, width or punctuation reuses that tag
    with a warning instead of creating a near-twin. `--define CATEGORY=VALUE DEFINITION` both
    creates the tag and puts it on the item.
16. **A missing required category is not reported** when a tag in that category was given but
    refused (for example an undefined new tag), to keep the problem list to the real cause.
