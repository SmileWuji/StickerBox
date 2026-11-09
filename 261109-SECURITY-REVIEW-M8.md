# Final security review at M8 (2026-11-09)

Read-only review by a subagent of `2e7cda0`: the whole tool with fresh eyes, the skills and docs,
and the git history for open-source readiness. Experiments in a scratch directory.

| # | finding | severity | status |
|---|---|---|---|
| 0 | A bad edit of mine (commit `d0ee5a6`) had replaced AGENTS.md with 30 MB of repeated text | process | fixed: the commit was undone (`git reset --soft`, never pushed) and AGENTS.md restored |
| 1 | Tests and one skill contained phrases transcribed from real third-party stickers, added from context by me | high | fixed in the tree: replaced by invented phrases; **still in history**, see below |
| 2 | Third-party pack names (folder names, one watermark handle) in the tree and history | medium | fixed in the tree: corpus paths moved to the git-ignored `testdata/private/sources.default`; **still in history** |
| 3 | The WEBM codec gate checked the Matroska header, but FFmpeg picks a container by probing, so a crafted file decoded as MPEG-2; relative names like `concat:x` were FFmpeg protocols | medium | fixed: captures open by absolute path with only the `file` protocol, and the FOURCC FFmpeg actually chose must be VP8, VP9 or AV1 (test_3) |
| 4 | A hostile `--from` box could return huge generated values (3 GB of memory) | medium | fixed: source databases have a 1 MB value limit and only named columns are read (test_4) |
| 5 | FIFOs hung the tool (as the file to stage, as a source box's stored file, as a source box's journal) | medium | fixed: files are opened non-blocking and checked regular before reading; source databases are opened `immutable=1` (test_5) |
| 6 | Skills told agents to follow box notes, distrusted only part of the README, and error messages repeated agent-written policy descriptions | medium | fixed: the `sticker-box` skill says everything a box returns is data, never instructions; reference sources come from the skill's fixed list, notes may only order them; error messages no longer quote descriptions; integration docs say the same for plugins |
| 7 | `stage --from` silently carried the source's text, description, note and fields into the commit | low to medium | fixed: only licence and source carry over; the rest is shown under `origin` as hints, documented in the skill |
| 8 | `frames <staged ref>` read through a symlink planted in `temporary/` | low | fixed: staged files that are symlinks are refused (test_8) |
| 9 | Raw tracebacks for a non-SQLite database, a bad schema version, long or non-UTF-8 names, a locked database, a planted directory, a sidecar with empty media | low | fixed: the CLI turns any unexpected error into a JSON error, output encoding is safe, sidecar media are type-checked, cleanup skips directories (test_9) |
| 10 | Sidecars were trusted for keyframe hashes and SIFT matches, so a forged relation could be stored | low | fixed: commit recomputes metadata, keyframes, features and matches from the staged file (test_10) |
| 11 | `vocab review` was quadratic in aliases, which were unlimited | low | fixed: at most 32 aliases per tag (test_11) |
| 12 | A just-committed file could be listed as an orphan, and the skill called orphans safe to delete with a command that never deletes them | low | fixed: orphan candidates are re-checked against the index; the skill says to report them |
| 13 | The docs said `pip install sticker-box`, a name nobody has registered on PyPI | low | fixed: install from a checkout; the docs warn about the unregistered name |

## History (scrubbed 2026-11-09)

The transcribed phrases and the third-party pack and watermark names were in early commits.
With the owner's approval every commit was rewritten (`git filter-branch --index-filter` with a
fixed replacement map, the same substitutions as the tree fix; commit messages and the synthetic
test images untouched), then the old refs, reflogs and unreachable objects were purged. Checks
afterwards: the final tree is byte-identical to before, all 17 commits remain, a search of every
object in the repository finds none of the strings, and nothing unreachable is left. Commit hashes
changed; nothing had been pushed. The rows marked "still in history" above no longer apply.
