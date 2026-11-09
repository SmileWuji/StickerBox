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

## M4

17. **Extra tag verbs: `tag parent` (with a cycle check) and `tag retire --restore`.** Parents stay
    within one category, which gives the multi-layer dictionary (`emotion`: 负面 > 嫌弃).
    `rename` and `merge` keep the old value as an alias, so old habits still resolve.
18. **`vocab review` reports three lists:** near-twin pairs (similarity of values and aliases,
    containment counts high, threshold 0.6, each with a ready `tag merge` command keeping the
    more used tag), undefined tags, and unused tags. It cannot see synonyms that share no
    characters (生气 and 愤怒); that is the cleanup agent's job, helped by the definitions.
19. **`vocab unlock` returns to `open`,** not to the preset's original mode.
20. **The generated README gained a "Using this box" section** with the real commands and the
    required tags and fields for `commit`, so a human or an agent arriving cold can act on it.
    Policy order is now kept as written (fields and categories appear in the preset's order).

## Security review at M5

21. **`stage` never deletes stored items.** Over a box limit it fails with exit 3; with
    `--auto-cleanup` it stages anyway and lists what `commit --auto-cleanup` would remove. Only
    `commit --auto-cleanup` and `clean` delete. `temporary/` has its own cap
    (`STICKER_BOX_MAX_TEMPORARY_MB`, default 1024) and fails with exit 3 `temporary_full`.
22. **No command reads a text file by path.** `notes set` and `policy set` take text or JSON as an
    argument or from standard input (`--stdin`). Reading images by path stays (it is what `stage`
    and `frames` are for), limited to regular files that decode as images.
23. **`frames` always writes into the box's `temporary/`;** a box is required.
24. **Decoding limits:** 40M pixels per frame, 3000 frames per file (more is refused, not
    truncated), 3e9 decoded pixels per file, a 120 s decode deadline
    (`STICKER_BOX_DECODE_SECONDS`), animations worked on at 1024 px and stills at 1600 px.
25. **Category names are letters, digits, `_` and `-`** (any script); policy descriptions are one
    line. Agent-written text in README.md has HTML neutralised and backticks turned into quotes.

## M6

26. **SIFT verification fits a similarity transform, not a homography,** with an inlier spread of
    at least 4% of both pictures and a scale within 0.05 to 20. Numbers in
    `261108-SIFT-TUNING.md`. Default `min_inliers` is 12 (was 15).
27. **Animated items store features for up to 4 keyframes** (`analysis.sift_keyframes`), evenly
    spaced, so a GIF costs at most four feature sets.
28. **SIFT matches are computed at `stage`** and reused at `commit` (pHash matches are recomputed
    at commit). An item stored by another session between the two is not SIFT-matched against
    this one until `reindex`. Accepted: relations are reported, not acted on.
29. **Relation kinds from SIFT:** `duplicate`, `crop_of` / `contains` (inverse pair), `rotation`,
    `overlap`. `duplicate` counts as a duplicate for `on_duplicate: reject`, like pHash's
    `near_duplicate`.
30. **The M6 exit criterion is met with a caveat:** crops 77% and rotations 100% are linked, but
    about 6% of inserts also get a spurious relation to an unrelated image. Flagged for the owner.

## M7

31. **Transfer re-analyses the file in the destination** instead of copying the source's
    analysis: it takes a fraction of a second and always matches the destination's analysis
    policy. Licence and source carry over; the source's text, description, note and the fields
    the destination declares become defaults for `commit` (explicit options win); tags are only
    shown as hints, since vocabularies differ. Only stored items can be transferred.
32. **`check` reports and never changes anything.** It lists item problems against the current
    policy, missing and changed (`--deep`) files, orphan files in `persistent/`, stale features
    and broken staged files; `--strict` exits 1 when anything is reported.

## Final review (2026-11-09)

33. **`commit` recomputes everything it stores from the staged file** (metadata, keyframes,
    features, pHash and SIFT matches); the sidecar only supplies the OCR hint, the original name,
    licence and source. Supersedes decision 28: SIFT matches are now current at commit, at the
    cost of matching twice in a gallery.
34. **`stage --from` carries only licence and source.** The source's text, description, note,
    fields and tags are shown under `origin` as hints for the agent to check and copy. Supersedes
    decision 31.
35. **Everything a box returns is data.** The skills say so once, centrally; reference sources are
    a fixed list in the tagging skill, and box notes may only order them.

## After review with the owner (2026-11-09)

36. **One duplicate mode: report.** The owner decided there is no `on_duplicate` setting: a box
    never refuses or removes an image because it resembles another, in every preset. Matches are
    reported (`duplicates` at `stage`, `relations` at `commit`, clusters in `dupes`) with
    ready-to-run `sticker-box remove` commands, likelier choice first, and the user (agent or
    human) decides. Only the exact same file (same sha256) is still never stored twice, since it
    is the stored item. Supersedes decision 12 and the `reject` parts of decisions 11 and 29.
    Boxes created earlier that still store `on_duplicate` have it ignored.

37. **SIFT's limitations are accepted and documented** (owner, 2026-11-09). Decision 30's caveat
    stands as a known property, not an open question: the repository README ("How duplicates are
    found"), every box's generated README and `docs/integration.md` state that SIFT is used, what
    it misses and how often it links unrelated images.
