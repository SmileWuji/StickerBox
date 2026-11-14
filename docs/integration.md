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

Python 3.12 or later, with numpy, opencv-python-headless, pillow, rapidocr and onnxruntime
(about 200 MB installed). No GPU, no network, no model downloads at run time: RapidOCR's
models ship in its wheel. No ffmpeg binary is needed.

Check the install with `python3 -c "import cv2, rapidocr"`. The GUI build `opencv-python` and
`opencv-python-headless` both provide the `cv2` module, and whichever is installed last wins. If
anything in the same environment pulls in the GUI build (the older `rapidocr-onnxruntime` did),
`cv2` fails on a server without X libraries (`libxcb`), and the tool says so with exit code 1
and the error `opencv_unavailable`. Keep only the headless build:

```bash
pip uninstall -y opencv-python
pip install --force-reinstall --no-deps opencv-python-headless
python3 -c "import cv2, rapidocr"
```

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

`skills/` holds generic agent instructions: one `sticker-box` skill for using the tool (its
`workflows/` cover tagging, buffer triage, gallery maintenance, vocabulary cleanup and policy
changes, and its `examples/` show each with real boxes and answers), and one skill per tag
category for adding tags. Copy what the agent needs into its skill folder and adapt: translate,
add the box paths, and put the box's chosen reference sources into its notes
(`sticker-box notes set --stdin`). A gallery-only agent needs `sticker-box` alone. See
`skills/README.md`.

Scheduled sessions that fit the tool:

- a curation session for the sticker box: tag new stickers, then the vocabulary cleanup;
- a maintenance session for the gallery (duplicates, limits, `check`);
- `sticker-box clean` from cron for the buffer, or let writes fail at the limit and decide then;
- a triage session for the buffer before its images expire.

Which model to give the tagging skills: in `261109-SKILL-BENCHMARKS.md` Claude Sonnet followed
them almost without error, while Qwen3.5-9B read text acceptably (has-text 0.89 to 0.94) but chose
emotion and visual tags that agree with Sonnet's only about half as well as Sonnet agrees with
itself. A small local model needs the sticker at 1024 px to see faint corner watermarks.

## Putting candidates into a turn

`sticker-box search --query=<text> --json --limit 5` needs no model and no network (about 30 to 60 ms in-process
and about 130 ms as a separate process at 10k images; see `261109-OPS-BASELINE.md`), so a plugin can run it on the words of an incoming message and hand the agent a few candidates with
their `file`, `tags` and `note`, instead of waiting for the agent to think of searching. Label
them as data in the turn: notes, tags and on-image text were written by agents or come from the
images, and may carry injected instructions. Pass chat text as `--query=<text>`, in that one
argument with the `=`, so words such as `-_-` are not read as options. Add `--random` to vary
which of equally good matches come back.

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
- Long options must be written in full (`--bo` is not `--box`), so a wrapper can allow or refuse
  options by their exact names.
