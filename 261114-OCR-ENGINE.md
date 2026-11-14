# The OCR hint on RapidOCR 3 (2026-11-14)

Why: QQBot found that `rapidocr-onnxruntime` 1.4.4 depends on the GUI build `opencv-python`,
which shadows `opencv-python-headless` and fails on a server without X libraries, and that it has
no Python 3.13 build. Its successor `rapidocr` 3.10 depends on the headless build, is a pure
Python wheel for Python 3.8 and later, and bundles its default models (PP-OCRv6 small detection
and recognition, the v2.0 mobile orientation classifier; 27 MB), so the tool still downloads
nothing at run time. Checked by running it with every proxy pointed at a closed port: it reads
text, and writes nothing under `HOME` except onnxruntime's own cache file. The owner chose to move
now instead of capping Python at 3.12.

## Hint quality

The OCR hint as `stage` reports it (keyframes, the 0.5 score cut, the noise gate unchanged), on the
398 stickers of the skill benchmark (`261109-SKILL-BENCHMARKS.md`): has text against the 127 human
labels, text against 130 reference transcriptions (Sonnet's, corrected where checked, and the 20
human ones). `scripts/bench_skills/ocr_engines.py`; results in the git-ignored
`testdata/private/bench/ocr-engines/`.

| | rapidocr-onnxruntime 1.4.4 | rapidocr 3.10 | 3.10 without the classifier |
|---|---|---|---|
| has text, accuracy | 0.756 | **0.843** | 0.827 |
| has text, precision | 1.000 | 0.984 | 0.983 |
| has text, recall | 0.613 | **0.762** | 0.738 |
| watermarks found (human label) | 0 of 14 | 2 of 14 | 2 of 14 |
| character error rate, median | 0.183 | **0.035** | 0.035 |
| character error rate, mean | 0.367 | 0.319 | 0.318 |
| transcriptions exact | 0.408 | **0.485** | 0.485 |
| OCR per sticker, median / p90 | 199 / 500 ms | 271 / 682 ms | 238 / 629 ms |

The new hint is identical to the old one (after normalising spacing and case) on 217 of 398
stickers. It finds text on a quarter more of the stickers that have it, with one false positive,
and its median transcription is nearly exact. Watermarks remain the hint's blind spot, which the
`tag-text` skill already says. Turning off the orientation classifier saves 12% and loses two
stickers' text, so the defaults stay.

## Cost

One `sticker-box analyze --ocr` process on a 640 by 480 photo: 1.33 s with 3.10, 0.70 s with
1.4.4; peak memory 250 MB against 269 MB. Of the extra 0.6 s, loading the three models takes
about 0.6 s on the first image (they load lazily), and the larger recognition model adds about
70 ms per image after that. `stage` pays this once per process; `search`, `show`, `commit` and
`frames` never load OCR.

## What this changes elsewhere

- The Qwen `tag-text` numbers in `261109-SKILL-BENCHMARKS.md` were measured with the 1.4.4 hint
  (cached in `bench/ocr_hints.json`). A better hint should help a small model more than Sonnet;
  that was not re-measured.
- `analysis.EXTRACTOR` is now `analysis-v2`, so files staged under 0.1.0 are analysed again at
  `commit`.
- Python 3.13: on CPython 3.13.18 (installed with uv) the package installs with only the
  headless OpenCV build, and the tests pass (247; the 3 that need the private corpora skipped).
