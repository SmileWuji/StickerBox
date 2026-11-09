# Security review at M7 (2026-11-09)

Read-only review by a subagent of `fd48e6e` (M6 and M7: features, dupes, reindex, transfer,
check, limits, the stage and commit changes, and the M5 fixes), with experiments in a scratch
directory. The M5 fixes held (pixel and frame caps, deadline, codec gate, no `--file` or `--out`,
README escaping, bounded vote memory for well-formed rows).

| # | finding | severity | status |
|---|---|---|---|
| 1 | Sidecar JSON was trusted for paths: a planted `<sha>.json` with an absolute `file` made `remove` delete and `commit` move any file into the box; a hostile `sha256` value made the already-staged path write JSON anywhere | high | fixed: every staged and stored path is derived from the 64-hex sha256 and a known extension (`paths.py`); sidecars are validated on load; files are copied in before they are inspected; commit re-hashes and re-probes the staged file (test_1) |
| 2 | A box with symlinked `temporary/` or `persistent/`, or an item row whose `file` points outside, made `clean` and `remove` delete anywhere | medium | fixed: boxes with symlinked `temporary/` or `persistent/` are refused; stored paths must match the tool's own pattern and contain no symlinks before any read or delete; rows pointing elsewhere lose the row, never the file, and `check` reports them (test_2) |
| 3 | `.npz` feature files were not validated: wrong shapes broke every later `stage` until `reindex`; a small file could expand to hundreds of MB | medium | fixed: `.npz` files are checked for size, member sizes, set count, dtypes, shapes and finite values, and re-computed when bad; stored rows whose BLOB lengths disagree with `n` are skipped and reported by `check` (test_3) |
| 4 | SIFT matching had no time limit and the policy allowed about 500 times the default cost (16 keyframes x 2000 keypoints) | medium | fixed: keypoints x SIFT keyframes is capped at 4800 in the policy; matching stops after `STICKER_BOX_SIFT_SECONDS` (default 60) and says so in the sidecar (test_4) |
| 5 | `reindex` deleted every feature and relation before it could fail; one bad file left the box without features, and concurrent stages compared against an empty table | low | fixed: `reindex` replaces each item in its own transaction, skips and reports failures, keeps old data for them; `check` reports items without features (test_5) |
| 6 | `stage --from` containment check could be bypassed with a symlinked `persistent/` in the source box; time-of-check gap before the copy | low | fixed: source boxes go through the same symlink and path checks; the file is copied with `O_NOFOLLOW` from one descriptor (test_6) |
| 7 | A hostile source box could hang `stage --from` (an `item` view over a recursive CTE), crash it (a BLOB in `text`), or pass unbounded text | low | fixed: source boxes are opened read-only (`mode=ro`, `query_only`), must have real tables, and every query stops after 10 s; carried values are type- and length-checked and dropped with a warning (test_6_and_7) |
| 8 | Huge policy integers broke the box (`expire_after_minutes` overflowed datetime; a 321-digit grace period broke `clean`) | low | fixed: upper bounds on every policy integer (test_8) |
| 9 | Races between listing `temporary/` and `stat` raised `FileNotFoundError` and aborted `clean` | low | fixed: `clean` and the temporary quota tolerate files that disappear while listed |
