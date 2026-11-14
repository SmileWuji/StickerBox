# sticker-box

A command-line tool that keeps a directory of images (stickers, a gallery, a short-lived buffer)
together with a SQLite index, a generated manual, and a policy it enforces. It is built to be
operated by an AI agent, and the directory stays readable and usable by a human.

```
<box>
┣━ temporary/       files being added; may be emptied at any time
┣━ persistent/      the images, <yyyymm>/<yyyymmdd>-<sha256>.<ext>
┣━ box.sqlite3      index, tags, policy
┗━ README.md        generated manual; change the box only through sticker-box
```

What it does without any model: format and size checks against the box's policy, keyframes and
perceptual hashes (near-duplicates, stills cut from animations), SIFT local features in the
gallery preset (crops, zooms, rotations, pictures inside screenshots), an OCR hint, contact
sheets so models without video input can read an animation in one image, a tag vocabulary with
definitions, aliases, broader tags, near-twin review and locking, and ranked search. What it
leaves to the agent or person using it: reading the image and writing the tags, text and notes.

## Install and try

```bash
pip install -e .                  # Python 3.12 or later
python3 -c "import cv2, rapidocr"  # fails if a GUI OpenCV build shadows the headless one; see docs/integration.md
sticker-box init stickers --preset telegram-sticker --language zh-Hans
sticker-box stage some.webp --box stickers
sticker-box commit <ref> --box stickers --license unknown --text "" --note "when to send it" \
  --define emotion=无语 "说不出话的无奈"
sticker-box search 无语 --box stickers
cat stickers/README.md
```

Presets: `telegram-sticker` (Telegram's sticker spec, open vocabulary to be cleaned and locked),
`gallery` (any image, free tags, SIFT duplicates), `buffer` (items expire after an hour). Every
rule can be changed with `sticker-box policy set`. Every command has `--help`; add `--json` for
machine-readable output.

## How duplicates are found

Every image is compared with what the box already holds, in up to three ways. Whatever is
found is reported with suggested `remove` commands; the tool never refuses or removes an image
because of it (only the exact same file is never stored twice).

| method | finds | misses |
|---|---|---|
| sha256 | the identical file | everything else |
| perceptual hash (64-bit DCT pHash, per keyframe) | re-saved, resized or recompressed copies; a still taken from an animation | crops, rotations, large overlays |
| SIFT local features (gallery preset only) | crops, zooms, rotations, a picture inside a screenshot, partial overlays | flat-colour art with few keypoints (skipped), heavy edits |

SIFT (Lowe's scale-invariant feature transform, from OpenCV) matches small distinctive patches
between two images and keeps a match only when enough of them agree on one rotation, zoom and
shift. It has known limitations, measured on real stickers with generated variants
(`261108-SIFT-TUNING.md`):

- it misses some: 89% of variants were linked to their original (about 77% of tight crops and
  of pictures inside screenshots, nearly all rotations, resizes and overlays);
- it raises false links: about 6% of new images also got a link to an unrelated image, mostly
  on flat or repetitive art and look-alike lettering; such links carry low `inliers` counts
  (near the minimum of 12), while true ones are usually far higher;
- it matches pixels, not meaning: the same character drawn in another pose is not linked,
  while stickers that reuse the same drawing are (about 60% of the extra links in the
  measurement); a small shared logo or watermark is usually not enough to link, a large one can
  be;
- it costs time: about 1.7 s per new image with 3,000 stored, capped by
  `STICKER_BOX_SIFT_SECONDS`.

So a link is evidence to look at, not a verdict. Sticker art is expected to be the hard case
and photos and screenshots easier, but only stickers have been measured so far.

## Performance

Measured on 2026-11-09 with `scripts/bench_ops.py` on synthetic, seeded boxes, on a desktop
rather than a server. Every command, p95 and the query plans are in `261109-OPS-BASELINE.md`.

| | test machine |
|---|---|
| CPU | Intel Core i5-10600KF, 6 cores, 12 threads, 4.1 GHz |
| RAM | 16 GB visible to Linux |
| GPU | NVIDIA GeForce RTX 3060, 12 GB; used only by the local model in the skill benchmarks below, the tool itself runs on the CPU |
| OS | Ubuntu 24.04 on WSL2 (Linux 6.18), Windows host |
| Storage | the WSL2 Linux filesystem; one comparison on a Windows NTFS drive mounted over 9p |
| Software | Python 3.12.3, SQLite 3.45.1, NumPy 2.5.3, OpenCV 5.0.0, Pillow 12.3.0, Ollama 0.34.2 |

Median times in milliseconds inside one Python process, for a sticker box of each size:

| operation | 1k | 3k | 10k | 30k |
|---|---|---|---|---|
| search by one tag (`--tag`) | 8.3 | 12.5 | 31.6 | 90.8 |
| search for a tag value | 10.8 | 16.2 | 38.5 | 107.8 |
| search for a word in the image text | 9.2 | 12.1 | 25.6 | 59.8 |
| search with five words | 17 | 24.2 | 62.5 | 164.8 |
| search with no words (newest first) | 7.3 | 9.9 | 18.1 | 46.5 |
| show | 5.5 | 5.6 | 5.7 | 5.8 |
| stage | 123 | 142 | 175 | 286 |
| commit | 30 | 39 | 75 | 199 |
| remove | 14 | 15 | 17 | 23 |

- Lookups stay under 100 ms up to 10,000 stickers. Search grows with the box because it reads
  every row (the vocabulary is reloaded per query and text is matched with `LIKE`); it is the
  first thing to slow down, still under 0.2 s at 30,000. `show` is a primary-key read and stays flat.
- `stage` is image analysis and the near-duplicate scan; `commit` repeats both rather than
  trusting the staged results, so it also grows with the box.
- As separate processes, which is what an agent pays per call, at 10,000 stickers: `show`
  108 ms, `search --tag` 128 ms, `stage` 698 ms (mostly loading the OCR model), `commit` 380 ms.
  Python start-up alone is about 70 ms.
- These numbers are from 0.1.0. Since 0.2.0 the OCR hint runs on RapidOCR 3, which reads text
  better and costs about 0.6 s more per `stage` process and about 70 ms more per image
  (`261114-OCR-ENGINE.md`).
- Gallery inserts are the slow path: SIFT matching runs at `stage` and again at `commit`,
  about 1.6 s each with 3,000 images stored and 3.5 s each with 10,000. The synthetic features
  never resemble each other, so this is the vote over every stored image without the closer
  check of likely matches; a gallery of look-alike images pays that check on top, up to the
  `STICKER_BOX_SIFT_SECONDS` cap.
- `box.sqlite3` takes about 2 MB per 1,000 stickers, and about 43 MB per 1,000 gallery images
  (the SIFT features).
- One, two and four agents adding stickers to one box at the same time all finished without a
  failure; with four, the median was 545 ms per sticker.
- On the NTFS drive mounted over 9p, lookups were up to ten times slower and `check` took 14 s
  at 3,000 items. Keep boxes on a native Linux filesystem.

### Models following the skills

How well a model tags stickers by following `skills/`, on 264 stickers from a private corpus
(dev 165, test 99). Method, every variant and the caveats are in `261109-SKILL-BENCHMARKS.md`.

- **Claude Sonnet 5.5**, as a Claude Code agent: all 264 commits were accepted on the first
  attempt; has-text accuracy 0.955 on 67 human-labelled test stickers; emotion and visual tags
  about 98% right on a 26-sticker check (an upper bound: the check reviewed Sonnet's own labels).
- **Qwen3.5-9B** through Ollama on the RTX 3060 (temperature 0, thinking off): has-text accuracy
  0.94 on the same 67, about 1.0 s per sticker at 512 px and 2.1 s at 1024 px, where it also
  catches faint corner watermarks. Its emotion and visual tags agree with Sonnet's at F1 0.41
  to 0.45, about half of Sonnet's agreement with itself (0.79 and 0.68). About 30 prompt
  wordings were tried; only one emotion change held on the test split.

## For integrators and agents

- `docs/integration.md`: install, calling conventions, exit codes, environment, security notes.
- `docs/example-policies.md`: a meme library, capped gallery, day-long buffer, stricter metadata.
- `skills/`: instructions for agents, for using the tool and for tagging.
- `contrib/convert/`: a script that converts images to the Telegram sticker spec, for files
  `stage` refuses (the tool itself never converts).
- `contrib/import-library.md`: how to have an agent move an existing image library into boxes.

## Development

```bash
python3 -m venv --system-site-packages ~/.venvs/sticker-box   # on an NTFS mount, keep the venv off it
~/.venvs/sticker-box/bin/pip install -e ".[test]" --no-build-isolation
~/.venvs/sticker-box/bin/python -m pytest -q
SB=~/.venvs/sticker-box/bin/sticker-box scripts/smoke.sh
python3 scripts/make_generic_testdata.py    # regenerate testdata/generic (synthetic, committed)
scripts/link-private-testdata.sh            # point testdata/private at your own corpora (git-ignored)
```

Tests that need private corpora are marked `private` and skip when `testdata/private` is empty.
The plan and progress are in `AGENTS.md`; design reasoning, decisions, measurements and security
reviews are in the dated notes (`YYMMDD-*.md`).

## Licence

MIT, see `LICENSE`.
