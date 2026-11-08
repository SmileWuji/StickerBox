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
