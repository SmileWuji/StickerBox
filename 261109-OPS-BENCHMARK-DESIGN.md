# Operations benchmark: design (2026-11-09)

A hard benchmark of the tool's own operations, no agents involved: how long lookups, additions,
removals and maintenance take as a box grows, so that a baseline is on record and any index or
algorithm change can be justified by numbers. Not built yet; the backlog item in `AGENTS.md`
points here. Measured so far, for comparison: analysis per file (`261108-CORPUS-ANALYSIS.md`)
and SIFT matching at 3,000 stored images (`261108-SIFT-TUNING.md`). Nothing else.

## What to time

| group | operations |
|---|---|
| start-up | process start (`--version`), `info` on an empty box, each as a subprocess |
| lookups | `search --tag` (one tag), `search` by a tag value, an alias, a definition word, a word in on-image text, five words, no words; `show`; `tag list`; `info` |
| additions | `stage` with and without the OCR hint, `commit` in a sticker box (pHash path) and in a gallery (SIFT path), `stage --from` |
| changes | `edit` (add and remove a tag), `tag merge`, `tag rename`, `remove` |
| maintenance | `vocab review`, `dupes`, `check`, `check --deep`, `clean`, `reindex` (smaller sizes only) |
| concurrency | 2 and 4 sessions committing into one box at once: wall time and lock waits |

## Dimensions

- Items: 1k, 3k, 10k, 30k in a sticker box; 1k, 3k, 10k in a gallery (with features).
- Vocabulary: 100, 500, 2,000 tags; aliases up to the cap.
- Shape: 30% animated with 2 to 12 keyframes; half with on-image text; 3 to 6 tags per item with
  Zipf popularity; about 2% of items with a relation.
- Storage: local ext4, the NTFS mount of the dev container, and the droplet's disk.

## Data

All synthetic, so results can be published: rows written straight into SQLite with fixed seeds
(placeholder files in `persistent/`, random pHashes and keyframes, tags and text drawn from a pool
of common Chinese characters, random SIFT descriptors of realistic size), plus freshly generated
512 px stickers for the stage and commit timings. Random descriptors cost the same to vote over
as real ones but never shortlist, so SIFT verification time is measured separately on real
images. If a private corpus is ever used, it is referred to only by a code name (`corpus-A`,
`pack-B`, ...), with the mapping kept in the git-ignored `testdata/private`.

## Method

- Time in-process through `cli.main` (one warm-up, then median, p95 and max of at least 7 runs),
  and as subprocesses for start-up. Record peak memory per operation and database size.
- Record hardware, OS, Python, SQLite (3.45 on the dev container) and library versions.
- Run `EXPLAIN QUERY PLAN` on every query in the hot paths to see which ones scan.
- Results as JSON plus a dated note with tables: numbers and code names only. Commit messages
  state results, never dataset names.

## Suspects to confirm or clear

From reading the code; the benchmark decides which matter:

- Search loads every tag and alias into Python for each query word, and scans `item.text`,
  `note`, `description` and `item_field.value` with `LIKE`. Options: cache the vocabulary per
  process; an FTS5 trigram index for words of three or more characters (two-character Chinese
  words still need `LIKE`, design notes §4).
- Every `stage` and `commit` loads all keyframe hashes for the pHash comparison. Option:
  multi-index hashing columns (design notes §8).
- SIFT voting scans every stored descriptor. Option: visual words (design notes §8).
- Every write regenerates `README.md`, counting uses per tag with a subquery each. Option:
  regenerate less often, or keep counts.
- Limits sum `item.bytes` on every write. Option: a running total in `meta`.
- `check` issues several queries per item.
- Process start imports OpenCV, NumPy and Pillow for every command, even `search`. Option: import
  them only in the commands that decode images.

## Proposed targets (for the owner to confirm)

At 10k stickers on the droplet: lookups under 100 ms in-process; `remove` under 100 ms; `stage`
plus `commit` under 1 s without OCR; process start reported separately, since it likely
dominates every short command.
