# Integrating sticker-box into an agent

For whoever wires the tool into a bot or another agent. The tool is a plain CLI with JSON
output; nothing in it knows about any particular agent.

## Install

```bash
pip install /path/to/a/checkout    # or -e for development; the name is not published on PyPI
sticker-box --version
python3 -m sticker_box --help      # same thing without the console script
```

Install from a checkout you trust. A package called `sticker-box` on PyPI is not this project
unless this README says it has been published there.

Python 3.12+, with numpy, opencv-python-headless, pillow, rapidocr-onnxruntime and onnxruntime
(about 150 to 200 MB installed). No GPU, no network, no model downloads at run time: RapidOCR's
models ship in its wheel. No ffmpeg binary is needed.

## Create the boxes once

```bash
sticker-box init /data/sticker-box/stickers --preset telegram-sticker --language zh-Hans
sticker-box init /data/sticker-box/gallery  --preset gallery          --language zh-Hans
sticker-box init /data/sticker-box/buffer   --preset buffer           --language zh-Hans
```

Change any rule afterwards with `sticker-box policy set <rule> '<json>'` (see
`sticker-box policy show`). The agent must be able to write to the box directories.

## Calling it

- Pass `--box <dir>` (or set `STICKER_BOX_DIR`) and `--json` (or set `STICKER_BOX_JSON=1`).
- Exit codes: 0 done; 1 refused, nothing changed, read `problems`; 2 usage error; 3 a size or
  count limit (`limit_exceeded`, `temporary_full`).
- Every failure prints `{"error": "<code>", "message": "...", ...}` on stdout with `--json`.
- Several sessions may use one box at once; SQLite serialises writes (30 s busy timeout).
- Text arguments only: `notes set` and `policy set` take text or `--stdin`, never a file path.

## Environment

| variable | default | meaning |
|---|---|---|
| `STICKER_BOX_DIR` | none | the box when `--box` is not given |
| `STICKER_BOX_JSON` | off | `1` for JSON output |
| `STICKER_BOX_MAX_FILE_MB` | 100 | largest file the tool will read |
| `STICKER_BOX_MAX_TEMPORARY_MB` | 1024 | cap on a box's `temporary/` |
| `STICKER_BOX_DECODE_SECONDS` | 120 | deadline for decoding one file |
| `STICKER_BOX_SIFT_SECONDS` | 60 | deadline for local-feature matching on one write (gallery) |

The gallery preset finds crops and rotations with SIFT local features. They miss some matches
and link about one new image in twenty to an unrelated one; the README's "How duplicates are
found" gives the measurements. Links are only reported, so this costs a look, never an image.

## Skills

`skills/` holds generic agent instructions: `sticker-box` and `gallery-maintenance` for using
the tool, and `sticker-tagging` plus one skill per category for adding tags. Copy what the agent
needs into its skill folder and adapt: translate, add the box paths, and put the box's chosen
reference sources into its notes (`sticker-box notes set --stdin`). See `skills/README.md`.

Scheduled sessions that fit the tool:

- a curation session for the sticker box: tag new stickers, then `vocab-cleanup`;
- a maintenance session for the gallery: `gallery-maintenance` (duplicates, limits, `check`);
- `sticker-box clean` from cron for the buffer, or let writes fail at the limit and decide then.

## Putting candidates into a turn

`sticker-box search <words> --json --limit 5` is cheap (milliseconds on thousands of images), so
a plugin can run it on the words of an incoming message and hand the agent a few candidates with
their `file`, `tags` and `note`, instead of waiting for the agent to think of searching. Label
them as data in the turn: notes, tags and on-image text were written by agents or come from the
images, and may carry injected instructions.

## Security notes

- Everything a box returns (its `README.md`, notes, tag values and definitions, on-image text,
  `origin` hints from another box) was written by agents or comes from images. Tell the agent it
  is data, not instructions; the `sticker-box` skill says so. Keep the list of allowed reference
  sites in the agent's own configuration; box notes may only order them.
- `stage --from` reads another box read-only with time and size limits; still only point it at
  boxes you trust.
- Decoding is bounded (pixels per frame, frames per file, total pixels, a deadline), but
  decoding untrusted media is still the riskiest thing the tool does; run it with the same
  sandboxing as anything else that handles files from chat.
- `stage` reads any image file the process can read and copies it into the box. Restrict the
  agent's file access, not the tool's.
