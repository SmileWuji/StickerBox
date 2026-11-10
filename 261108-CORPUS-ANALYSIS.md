# Corpus analysis (2026-11-08)

`python3 scripts/corpus_check.py` over the three private corpora (`testdata/private`), no OCR,
on the dev container (12 cores, WSL2). Numbers only; no image content is recorded here.

| kind | files | wall p50 | wall p95 |
|---|---|---|---|
| webm animated | 850 | 101 ms | 195 ms |
| webm single frame | 8 | 52 ms | 59 ms |
| webp static | 1037 | 28 ms | 34 ms |

- 1,896 files; 1,895 analysed; total 128 s.
- The one failure was a `.webm` whose EBML DocType says `matroska` while it carries VP9. Fixed the
  same day: Matroska with a WebM codec (VP8, VP9, AV1) is accepted as WEBM.
- Keyframes per animation: min 1, p50 7, p95 39, max 64 (the cap).
- Port check against GuidedStickerBootCamp's `260917-CORPUS-NUMBERS.md`, same five-pack WEBM
  subset and defaults (`drop_thr 0.10`, cap 64): 172 WEBM, 9,867 frames, 2,045 keyframes, 4.8×,
  1 at the cap. Identical to BootCamp's numbers, so pHash (now `cv2.dct`) and the keyframe walk
  ported unchanged.
- Contact sheets of five animations checked by eye: frames in order, labels legible.
