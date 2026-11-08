# Security review at M5 (2026-11-08)

Read-only review by a subagent of `7daea3f` against `AGENTS.md` §12, with experiments in a
scratch directory. Status is updated as fixes land; each fix has a test unless noted.

| # | finding | severity | status |
|---|---|---|---|
| 1 | Keyframe extraction kept every changed frame's full RGB until the cap was applied at the end: a 14 KB/frame GIF needed about 7 MB of memory per frame (out of memory on long animations) | high | fixed: keyframes are selected while streaming with a bounded heap; animations decode at most 1024 px (test_1) |
| 2 | `notes set --file` and `policy set --file` read any file (`/proc/self/environ` ended up in README.md) | high | fixed: `--file` removed from `notes set` and `policy set`; `--stdin` (capped at 100k characters) instead (test_2) |
| 3 | `frames --out` wrote anywhere, creating directories and overwriting files | high | fixed: `--out` removed; sheets go only into the box's `temporary/` (test_3) |
| 4 | `stage --auto-cleanup` deleted stored items before checking the file; a bogus file emptied the box | medium | fixed: `stage` never deletes; over a limit it fails, or with `--auto-cleanup` lists what commit would remove; `temporary/` has its own cap (test_4) |
| 5 | `commit --auto-cleanup` deleted outside the commit transaction; a concurrent change left items deleted and nothing stored; a cleaned staged file raised a raw `FileNotFoundError` | medium | fixed: removals happen inside the commit transaction after every check, files unlinked after COMMIT; a vanished staged file is a `not_found` error (test_5) |
| 6 | Policy descriptions and codec names were rendered raw into README.md (a field description could forge a heading); `$` in name regexes let a trailing newline pass; `cell()` did not escape backslashes | medium | fixed: one-line descriptions, `fullmatch` names, codec names `[a-z0-9]`, descriptions escaped; `cell()` escapes backslashes, HTML and backticks; `quote()` neutralises HTML (test_6) |
| 7 | The pixel cap was checked once: a GIF canvas growing after `seek()`, or a WEBM whose later frames are larger, bypassed it; flattening in float32 at full size cost gigabytes | medium | fixed: pixel cap checked after every seek and every decoded WEBM frame (size changes refused); frames shrink before compositing; cap lowered to 40M pixels (test_7) |
| 8 | No bound on video decode time (a small 8000x8000 VP9 file took 16 s for 60 frames) | medium | fixed: decode deadline (`STICKER_BOX_DECODE_SECONDS`, default 120) and a 3e9 decoded-pixel budget per file (test_8) |
| 9 | Matroska/WEBM was decoded whatever its codec when the DocType said `webm`, exposing every FFmpeg decoder | low | fixed: every Matroska/WEBM file must carry VP8, VP9 or AV1 before it is decoded (test_9) |
| 10 | Fixed README temp name raced between sessions (a committed write reported failure); same pattern in contact sheets and feature files | low | fixed: unique temp names for README, contact sheets and feature files |
| 11 | Decoder exceptions that are not `BoxError` printed a traceback and left an orphan staged file | low | fixed: any decoder exception becomes `undecodable` (or `image_too_large` for MemoryError) and the staged files are removed (test_11) |
| 12 | Unbounded text input: query terms, tags per commit, quadratic `vocab review` | low | fixed: at most 16 query words of 64 characters, 64 tags per command; `vocab review` only compares tags sharing a character (test_12) |
| 13 | Frames past `MAX_FRAMES` were ignored, so duration and fps rules could be evaded | low | fixed: files with more than 3000 frames are refused (test_8_and_13) |
| 14 | AGENTS.md §3 still says WAL; the rollback journal is the decided mode (decision 1) | doc | fixed: AGENTS.md §3 updated |
| M6 | SIFT vote matrix grows with `keypoints` (2000 keypoints x 200 rows is gigabytes) | medium | fixed: stored descriptors are batched by count (60k) and queries chunked (256 rows) |

Checked and fine: references are hex-validated; stored paths come from the tool; every SQL
query is parameterised and LIKE is escaped; the Matroska parser always advances with bounded
depth; `np.load` refuses pickles; tag values, aliases, notes and the description are escaped.
