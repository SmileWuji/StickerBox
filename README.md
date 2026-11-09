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
pip install -e .                  # Python 3.12+
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

## For integrators and agents

- `docs/integration.md`: install, calling conventions, exit codes, environment, security notes.
- `docs/example-policies.md`: a meme library, capped gallery, day-long buffer, stricter metadata.
- `skills/`: instructions for agents, for using the tool and for tagging.

## Development

```bash
python3 -m venv --system-site-packages ~/.venvs/sticker-box   # on an NTFS mount, keep the venv off it
~/.venvs/sticker-box/bin/pip install -e . --no-deps --no-build-isolation
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
