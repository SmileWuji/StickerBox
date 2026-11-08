# sticker-box

A command-line tool that keeps a directory of images (stickers, a gallery, a short-lived buffer)
together with a SQLite index, a generated manual, and a policy it enforces. It is built to be
operated by an AI agent, and the directory stays readable and usable by a human.

**Status: under construction.** The plan and progress are in `AGENTS.md`; the design reasoning
is in `261108-DESIGN-NOTES.md`.

## Install

```bash
pip install -e .            # Python 3.12+; numpy, opencv-python-headless, pillow, rapidocr-onnxruntime
sticker-box --help
```

## A box

```
<box>
┣━ temporary/       staged files, may be emptied at any time
┣━ persistent/      the images, <yyyymm>/<yyyymmdd>-<sha256>.<ext>
┣━ box.sqlite3      index, tags, policy
┗━ README.md        generated manual; modify the box only through sticker-box
```

## Development

```bash
python3 -m venv --system-site-packages ~/.venvs/sticker-box   # on an NTFS mount, keep the venv off it
~/.venvs/sticker-box/bin/pip install -e . --no-deps --no-build-isolation
~/.venvs/sticker-box/bin/python -m pytest -q
python3 scripts/make_generic_testdata.py    # regenerate testdata/generic (synthetic, committed)
scripts/link-private-testdata.sh            # point testdata/private at your own corpora (git-ignored)
```

Tests that need private corpora are marked `private` and skip when `testdata/private` is empty.

## Licence

MIT, see `LICENSE`.
