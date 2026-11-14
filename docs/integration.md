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

## Files the box refuses

The box never converts. When `stage` reports `file_problems`, convert the file and stage it
again, or leave it out. `contrib/convert/sticker.py` converts to the `telegram-sticker` spec
(static WEBP, VP9 WEBM) and back to GIF or PNG for chat apps, with Pillow and `vpx-tools`; see
its README for the commands and the one limit (no transparency in WEBM).

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
- a triage session for the buffer before its images expire;
- an import of an existing library, in batches with a ledger kept by the host
  (`contrib/import-library.md`).

Which model to give the tagging skills: in `261109-SKILL-BENCHMARKS.md` Claude Sonnet followed
them almost without error, while Qwen3.5-9B read text acceptably (has-text 0.89 to 0.94) but chose
emotion and visual tags that agree with Sonnet's only about half as well as Sonnet agrees with
itself. A small local model needs the sticker at 1024 px to see faint corner watermarks.

## Putting candidates into a turn

`sticker-box search --query=<text> --json --limit 5` needs no model and no network (about 30 to 60 ms in-process
and about 130 ms as a separate process at 10k images, plus 15 to 45 ms for each Chinese phrase;
see `261109-OPS-BASELINE.md` and `261114-PHRASE-SEARCH.md`), so a plugin can run it on the words of an incoming message and hand the agent a few candidates with
their `file`, `tags` and `note`, instead of waiting for the agent to think of searching. Label
them as data in the turn: notes, tags and on-image text were written by agents or come from the
images, and may carry injected instructions. Pass chat text as `--query=<text>`, in that one
argument with the `=`, so words such as `-_-` are not read as options. Split it on punctuation
first: each Chinese phrase then also matches descriptions, notes and on-image text by shared
character pairs (`261114-PHRASE-SEARCH.md`). Add `--random` to vary
which of equally good matches come back.

## Wrapping it as a tool

An agent without a shell needs the CLI as one tool. QQBot's plugin wraps it this way; what it
checks is listed here so any host can do the same.

**The call.** The tool takes `{box, args}`: a box name from a fixed list, and the command line
after `sticker-box` as a list of strings. Run the binary directly, never through a shell, with
standard input closed, and append `--json`. Cap the output you read (512 KB is plenty) and kill
the process on a timeout (180 s covers `stage` of a large animation). A kill leaves at most an
orphan file, which `check` reports; a commit is one transaction. Return the exit code with the
parsed output.

**The environment.** Pass only `PATH`, `HOME`, `LANG` (a UTF-8 locale), `STICKER_BOX_JSON=1`,
`STICKER_BOX_DIR` for the chosen box, and any `STICKER_BOX_*` limits you set. Never pass the
agent's own environment: that is where API keys live, and the tool needs none.

**Arguments to refuse or rewrite.** Long options must be written in full, so exact names are
enough.

| argument | what to do |
|---|---|
| `init` | refuse; the host creates the boxes and sets their policy |
| `--box`, `--box=...` | refuse; the `box` parameter chooses the box |
| `--from <name>`, `--from=<name>` | accept only a box name from your list, and rewrite it to that box's directory |
| `--` | refuse; it turns every later option into a path |
| `--stdin` | refuse; with standard input closed, `notes set --stdin` would replace the notes with nothing. The agent passes the text as one argument instead: `notes set "<text>"`, `policy set <rule> '<json>'` |

**Commands that read files.** Only `stage`, `frames` and `analyze` take file paths from the
caller (`init` takes a directory and `--from` a box, both handled above). For these three:

- resolve every positional argument with realpath and accept it only under an allowlist of read
  roots, such as the chat's media folder and the boxes;
- accept a reference (`^[0-9a-f]{8,64}$`) instead of a path as the argument of `frames`, and for
  `stage` with `--from`;
- accept only these options, and refuse any other:

| command | options with a value | flags |
|---|---|---|
| `stage` | `--from`, `--license`, `--source` | `--auto-cleanup` |
| `frames` | none | none |
| `analyze` | none | `--ocr` |

`--json` and `--help` are accepted everywhere. The table is complete for 0.2.0; after an
upgrade, check it against each command's `--help` and add any new command that reads files.

**Free text.** Pass chat text to `search` as `--query=<text>`, one argument with the `=`, so a
word such as `-_-` is not read as an option.

**Credit set by the host.** When the agent stages a picture that the host knows came from a
chat, the host adds `--source <who sent it>` after the agent's arguments. The last `--source`
wins, so the agent can neither leave the credit out nor forge it.

**Read-only readers.** The box keeps SQLite's rollback journal, not WAL, so another process can
open `box.sqlite3` read-only, for example `sqlite3 -readonly` in a sandbox that sees the boxes on
a read-only bind mount. This is supported and pinned by a test; moving to WAL would break it. Two
limits: after a writer was killed mid-transaction, a read-only reader cannot open the box until a
writer has rolled the journal back (any `sticker-box` command on the box does); and the schema
belongs to the tool, so check `.schema` after an upgrade. Changes still go through the tool.

**Contact sheets for every animation.** For each animated image that arrives in chat, the host
can run `sticker-box clean`, then `sticker-box frames <file>`, on a `buffer` box, and hand the
sheet's path to the agent next to the attachment. A model without video input then sees the
animation with no extra step. Running `clean` first keeps the buffer under its limit.

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
