# Operations baseline (2026-11-09)

`python3 scripts/bench_ops.py` per `261109-OPS-BENCHMARK-DESIGN.md`. Synthetic, seeded data
(rows written straight into SQLite, generated stickers for stage and commit), so every number
here can be shared. One warm-up, then the median of 7 runs (3 for the slow maintenance commands);
p95 and max are in the JSON reports (git-ignored, `testdata/private/bench/ops-*.json`).

Machine: Intel i5-10600KF (12 threads), 16 GB, WSL2 on Windows, Python 3.12.3, SQLite 3.45.1,
NumPy 2.5.3, OpenCV 5.0.0, Pillow 12.3.0. `/tmp` is the container's overlay filesystem; the
"NTFS" runs are on the Windows drive mounted over 9p, where the repository lives. The droplet was
not reachable, so production numbers are still missing.

## Verdict against the design's working targets

- **Lookups under 100 ms at 10k stickers: met.** Every search form, `show`, `tag list` and
  `info` take 6 to 63 ms in-process. At 30k the five-word search reaches 165 ms and a tag-value
  search 108 ms.
- **`remove` under 100 ms: met** (17 ms at 10k, 23 ms at 30k).
- **`stage` + `commit` under 1 s for stickers: met**, even with the OCR hint (175 + 75 ms at
  10k in-process; 698 + 380 ms as separate processes, where loading the OCR model dominates).
- **Gallery inserts are the slow path:** SIFT matching runs at `stage` and again at `commit`,
  about 1.6 s each at 3k and 3.5 s each at 10k, as the SIFT note predicted. Accepted. The
  synthetic descriptors are random, so no candidate passes the vote: these times leave out the
  ratio test and RANSAC that real look-alike images add per shortlisted candidate.
- **Process start-up was the real miss** and is fixed (below).
- **Concurrent writers:** 1, 2 and 4 writers all completed with no failures.
- **The 9p NTFS mount is slower, up to 10 times for lookups** (about 1.6 times for `stage`), and
  `check` (which looks at every file) takes 14 s at 3k there. Boxes belong on a native Linux filesystem.

## Fix made: lazy imports

`show`, `remove`, `edit` and plain `check` never decode an image, but importing `items` or
`check` pulled in NumPy, OpenCV and Pillow (about 190 ms) through `stage` and a `phash` helper.
Those imports now happen only where an image is analysed. As separate processes at 10k stickers:
`show` 266 to 108 ms, `remove` 299 to 137 ms, `commit` 432 to 380 ms. Every agent call that does
not add an image saves about 160 ms.

The first run's peak-memory figures were wrong: on Linux a forked child inherits the parent's
`maxrss` across `exec`. The script now reads `VmHWM`; the memory column below is from the
corrected run.

## Deferred, with reasons

- **Search above 10k items.** It reloads the whole vocabulary for every query word and scans
  `text`, `note` and `description` with `LIKE` (the plans below show `SCAN item`). Within target
  at 10k; at 30k a per-call vocabulary cache would help first, an FTS trigram index for words of
  three or more characters later.
- **Gallery inserts.** Matching twice is the price of decision 33 (commit recomputes everything
  instead of trusting the sidecar). Visual words (design notes §8) are the next step if galleries
  grow past a few thousand.
- **`check` on 9p.** Maintenance only; keep boxes off network or Windows mounts.
- **OCR model load at `stage`** (about 0.5 s per process with the imports). Inherent to running RapidOCR per
  command; the sticker preset can turn the hint off with `policy set analysis`.

## Numbers

### Sticker box, in-process median (ms), /tmp

| operation | 1,000 | 3,000 | 10,000 | 30,000 |
|---|---|---|---|---|
| search --tag (one tag) | 8.3 | 12.5 | 31.6 | 90.8 |
| search: a tag value | 10.8 | 16.2 | 38.5 | 107.8 |
| search: a word in on-image text | 9.2 | 12.1 | 25.6 | 59.8 |
| search: five words | 17 | 24.2 | 62.5 | 164.8 |
| search: no words (newest) | 7.3 | 9.9 | 18.1 | 46.5 |
| show | 5.5 | 5.6 | 5.7 | 5.8 |
| tag list | 9.6 | 9.7 | 10.8 | 13.9 |
| info | 5.7 | 6 | 7.2 | 10 |
| stage | 123.2 | 141.9 | 175.2 | 286.3 |
| commit | 30.3 | 39 | 74.9 | 198.8 |
| edit (note) | 14.2 | 15.7 | 17.4 | 23.4 |
| remove | 14.1 | 15.2 | 17 | 22.7 |
| tag rename | 16.4 | 15.9 | 17.2 | 28.9 |
| tag merge | 21.5 | 39.3 | 125.7 | 324.6 |
| vocab review | 31.8 | 32.4 | 34.6 | 37.2 |
| dupes | 7.2 | 12.2 | 31 | 95.8 |
| check | 126.3 | 373.5 | 1235 | 3717.9 |
| clean (nothing to do) | 5.2 | 5.6 | 5.7 | 5.5 |

### Gallery, in-process median (ms), /tmp

| operation | 1,000 | 3,000 | 10,000 |
|---|---|---|---|
| search --tag (one tag) | 8.6 | 14 | 34.8 |
| search: a tag value | 11.3 | 17.2 | 39.7 |
| search: a word in on-image text | 9.3 | 12.6 | 24.3 |
| search: five words | 17.2 | 24 | 60.1 |
| search: no words (newest) | 7.7 | 10.4 | 17.9 |
| show | 5.9 | 5.7 | 5.7 |
| tag list | 9.4 | 9.2 | 9.9 |
| info | 6.1 | 6.2 | 7.4 |
| stage | 527.9 | 1586.8 | 3518.7 |
| commit | 552.7 | 1569.1 | 3624.7 |
| edit (note) | 23 | 17.7 | 16.2 |
| remove | 19 | 15.8 | 16.5 |
| tag rename | 14.6 | 17 | 19.3 |
| tag merge | 19.1 | 26.8 | 73.7 |
| vocab review | 66.5 | 69.7 | 72 |
| dupes | 8.2 | 13.3 | 32.7 |
| check | 121.3 | 367.2 | 1175.2 |
| clean (nothing to do) | 5.6 | 10.3 | 5.5 |

### NTFS mount (9p), in-process median (ms)

| operation | 1,000 | 3,000 |
|---|---|---|
| search --tag (one tag) | 86.6 | 137.9 |
| search: a tag value | 94.3 | 176 |
| search: a word in on-image text | 67.6 | 87.4 |
| search: five words | 99 | 145.6 |
| search: no words (newest) | 71.8 | 96.6 |
| show | 35 | 35.1 |
| tag list | 33.7 | 37 |
| info | 44.4 | 65.3 |
| stage | 194.6 | 244.4 |
| commit | 124.4 | 184.3 |
| edit (note) | 72.9 | 96.7 |
| remove | 76 | 100.8 |
| tag rename | 67.6 | 91.1 |
| tag merge | 287.7 | 832.4 |
| vocab review | 58 | 61.3 |
| dupes | 94.6 | 282.8 |
| check | 4824.7 | 14322.7 |
| clean (nothing to do) | 28.5 | 28.3 |

### Size of the database

| box | items | box.sqlite3 |
|---|---|---|
| telegram-sticker | 1,000 | 2.2 MB |
| telegram-sticker | 3,000 | 6.1 MB |
| telegram-sticker | 10,000 | 20.0 MB |
| telegram-sticker | 30,000 | 60.5 MB |
| gallery | 1,000 | 42.7 MB |
| gallery | 3,000 | 127.7 MB |
| gallery | 10,000 | 425.5 MB |

### As separate processes, after the import fix: wall time (ms) and peak memory (MB)

| box | search --tag | show | stage | commit | remove | check |
|---|---|---|---|---|---|---|
| telegram-sticker 10,000 | 128.3 / 21.2 | 108.1 / 16.9 | 698.2 / 228.9 | 379.7 / 79.9 | 137.2 / 19 | 1322.6 / 36.3 |
| gallery 3,000 | 119.5 / 19.8 | 105.9 / 16.9 | 1780.1 / 376.1 | 1841.6 / 376.5 | 124.6 / 18.5 | 571.5 / 61 |

Before the import fix (10k sticker box, wall ms): search --tag 124.1, show 265.8, stage 708.4, commit 431.6, remove 299.4, check 1491.2

### Concurrent writers (stage + commit of 6 stickers each)

| where | box | writers | wall | failures | median per sticker | max |
|---|---|---|---|---|---|---|
| /tmp | 3,000 stickers | 1 | 1.6 s | 0 | 174.3 ms | 648.9 ms |
| /tmp | 3,000 stickers | 2 | 2.3 s | 0 | 253.4 ms | 946.4 ms |
| /tmp | 3,000 stickers | 4 | 4.1 s | 0 | 544.7 ms | 1350.4 ms |
| NTFS | 1,000 stickers | 1 | 2.5 s | 0 | 324.6 ms | 805.8 ms |
| NTFS | 1,000 stickers | 2 | 3.1 s | 0 | 393.6 ms | 1107 ms |
| NTFS | 1,000 stickers | 4 | 4.7 s | 0 | 617.5 ms | 1617.4 ms |

### Start-up

- /tmp: --version 71.8 ms, info on an empty box 77.1 ms
- NTFS: --version 73.6 ms, info on an empty box 102.8 ms

### Query plans (30k sticker box)

- search: items with one tag: SEARCH i USING INDEX sqlite_autoindex_item_1 (sha256=?); LIST SUBQUERY 1; SEARCH item_tag USING INDEX item_tag_tag (tag_id=?)
- search: items of matched tags: SEARCH item_tag USING INDEX item_tag_tag (tag_id=?)
- search: text LIKE: SCAN item
- search: field LIKE: SCAN item_field USING INDEX sqlite_autoindex_item_field_1
- write: all keyframe hashes: SCAN k; SEARCH i USING INDEX sqlite_autoindex_item_1 (sha256=?)
- write: usage for limits: SCAN item
- show: relations of an item: MULTI-INDEX OR; INDEX 1; SEARCH relation USING INDEX sqlite_autoindex_relation_1 (a=?); INDEX 2; SEARCH relation USING INDEX relation_b (b=?)
- readme: uses per tag: SEARCH t USING COVERING INDEX sqlite_autoindex_tag_1 (category=?); CORRELATED SCALAR SUBQUERY 1; SEARCH it USING COVERING INDEX item_tag_tag (tag_id=?)
- sift: stored descriptors: SCAN feature

