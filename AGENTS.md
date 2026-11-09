# StickerBoxAICapability

`sticker-box`: a standalone CLI that keeps a directory of images (stickers, a gallery, a short-lived
buffer) with a SQLite database, a generated manual, and policy rules it enforces. An AI agent
operates it; a human can read and use the same directory. QQBot (`../QQBot`) is the first user and
the owner wires it in on that side; nothing in this repo depends on QQBot.

This file is the plan and the progress record. The reasoning behind each decision is in
`261108-DESIGN-NOTES.md`; notes are `YYMMDD-XXX.md` and the newest wins when two disagree.

## Working on a low budget

The host runs on a tight budget and a session can end at any time. Work so the project can resume
from disk alone:

- Work in small steps and commit after each one; never hold finished work only in the session.
- Tick the checklist box in the same commit as the work. If a task is half done, add a short
  indented line under its box saying what is done and what is next.
- Decisions and measurements go into a dated note as soon as they are made, not at the end.
- A new session starts by reading this file and `git log --oneline | head`, then continues from
  the first unticked box.

## For the owner

Decisions taken while you were away, each with its reason and how to undo it, are in
`261108-BUILD-DECISIONS.md`. Nothing there is hard to reverse.

## Checklist

Tick a box in the same commit as the work. Bold lines are a milestone's exit criterion.

### M0. Scaffold
- [x] `pyproject.toml` (Python 3.12, console script `sticker-box`, pytest settings), package `sticker_box/`
- [x] `LICENSE`, `.gitignore` (including `testdata/private/`)
- [x] CLI skeleton: global `--box`, `--json`; error envelope and exit codes (§4)
- [x] Test data layout (§11): `testdata/generic/` committed, `testdata/private/` git-ignored and filled by `scripts/link-private-testdata.sh` from the owner's corpora; private tests skip when it is empty
- [x] Test helpers: synthetic image factory (static WebP, animated WebP, WebM, GIF, PNG, JPG) in `tests/factory.py`; the temp box fixture lands with `init` in M1
- [x] `README.md` for humans (install, quick start); this file kept current
- [x] **`pip install -e . && sticker-box --help && python3 -m pytest -q` all work on a fresh clone**

### M1. Instance, schema, policy
- [x] `init <dir> --preset ... --language ...`: the tree of §3, schema of §5, policy from the preset
- [x] Presets `telegram-sticker`, `gallery`, `buffer` (§6); Telegram numbers verified against https://core.telegram.org/stickers and the source recorded in the preset
- [x] `info`; `policy show`; `policy set <rule> <json>` validated and logged in `policy_log`
- [x] `README.md` in the instance generated from the policy (warning, description, rules in words); `manual` regenerates it
- [x] `notes show | set`: free text for the agents using the box, stored in `meta.agent_notes`, rendered as the README's "To agents" section; the tool never interprets it (§6)
- [x] Opening a box checks `schema_version` and refuses a newer one
- [x] **A box of each preset can be created, inspected, and have a rule changed, and its `README.md` states the change**

### M2. Media analysis
- [x] `media.py`: sniff format, dimensions, animated, frame count, duration, fps, audio, bytes
- [x] pHash and keyframes ported from `../GuidedStickerBootCamp/app/` (`phash.py`, `keyframes.py`, `media.py`), defaults kept (`drop_thr 0.10`, cap 64); BootCamp's numbers reproduced on a corpus subset
- [x] RapidOCR hint with the noise gate ported from `../GuidedStickerObservatory/service/noise.py`; on animations, run on keyframes and merge
- [x] `frames <ref>`: contact sheet of keyframes, labelled with index and time, written to `temporary/` (or `--out`); `analyze <path>` prints the analysis without a box
- [x] **`stage`-less analysis of every file in the corpus finishes without error, and contact sheets of five animations read correctly by eye**

### M3. Stage and commit
- [x] `stage <file>...`: copy into `temporary/`, analysis sidecar, file rules reported early, duplicates by sha256 and pHash; no database write
- [x] `staged`: list staged files with their sidecar summary
- [x] `commit <ref>`: fields, tags, text, description, note; every rule checked, all failures returned at once; file moved to `persistent/<yyyymm>/<yyyymmdd>-<sha256>.<ext>` and row written
- [x] `show <ref>`, `edit <ref>`, `remove <ref>`; references are a full sha256 or a unique prefix of at least 8
- [x] On-duplicate behaviour per policy (reject, report, link); `relation` rows written at commit, including still-to-keyframe links
- [x] Crash safety: file move and row insert ordered so a crash leaves at most an orphan file, which `check` reports (the report itself lands with `check` in M7)
- [x] **Twenty corpus stickers staged and committed into a `telegram-sticker` box with tags; a recompressed copy of one is reported as a duplicate; a non-compliant file is refused with every reason**

### M4. Vocabulary
- [x] `tag list | new | define | alias | rename | merge | retire`, each logged in `vocab_log`
- [x] Modes `free`, `open`, `locked` (§7): inline creation at `commit` in `open`, only `tag new` in `locked`, anything in `free`
- [x] Unknown tag errors carry the nearest existing tags (exact, alias, substring, character-bigram similarity)
- [x] Category cardinality (`one`, `at_least_one`, `any`) and required categories enforced
- [x] Script check of new tags against the instance language, as a warning
- [x] `vocab review`: near-duplicate tag pairs with counts, for a cleanup pass; `vocab lock`, `vocab unlock`
- [x] Generated `README.md` gains the vocabulary: categories, tags, definitions, aliases, parents, counts
- [x] **Bootstrapping a vocabulary from 50 stickers, merging the duplicates `vocab review` finds, and locking it works end to end, and `README.md` reads as a usable manual**

### M5. Search
- [x] `search <query>`: terms split on space and `|`; matches tag values and aliases, OCR text, description, note; `LIKE` for short Chinese terms
- [x] Ranking: exact tag > alias > text > description and note; ties by newest
- [x] Filters: `--tag category=value`, `--category`, `--animated`, `--license`, `--limit`; expired items flagged
- [x] Results carry the absolute file path, tags and note, so a caller can send directly
- [x] **On the tagged box from M4, ten realistic queries (two-character Chinese included) return sensible top-5 results**
- [x] Security code review of M0 to M5 (§12); findings fixed or recorded (`261108-SECURITY-REVIEW-M5.md`: 14 findings and one in M6, all fixed with tests)

### M6. Local features (gallery)
- [x] SIFT extraction, capped keypoints, uint8 descriptors and float32 keypoints into `feature` in `box.sqlite3`; only when the policy enables it
- [x] Insert-time matching: batched vote shortlist, pairwise ratio test and RANSAC on the top candidates (§8); RANSAC fits a similarity transform, not a full homography (see decisions)
- [x] Relation kinds from the homography: duplicate, crop, zoom, rotation, with region, scale and angle in `transform`
- [x] `dupes`: clusters from `relation` with a suggested keeper; `reindex` rebuilds features and relations
- [x] Threshold tuning on real images (crops, rotations, QQ-style screenshots, text-heavy images); numbers and chosen defaults in a dated note (`261108-SIFT-TUNING.md`)
- [x] **On a gallery of a few hundred corpus images plus generated crops, rotations and screenshots, crops and rotations are linked, unrelated images are not, and insert stays under a few seconds at 3,000 images (synthetic scale test)**
  - met with a caveat: 89% of variants linked, 1.7 s median insert at 3,000; about 6% of inserts also get a spurious relation (decision 30)

### M7. Limits, cleanup, transfer, audit
- [x] Limits (size, count) checked on `stage` and `commit`; over the limit fails with usage, limit and the `clean` command (landed with M3)
- [x] Retention: `expires_at` set at commit; expired items stay readable and are flagged (landed with M3)
- [x] `clean` (staged files past the grace period, and expired items), `clean --all` (landed with M3)
- [x] `--auto-cleanup` on writes: expired first, then oldest until under the limit; everything removed is listed (landed with M3)
- [x] `stage --from <box> <ref>`: staged in the destination (analysed again under its policy), licence and source carried over, text, description and note as commit defaults, tags as hints; validated at `commit`
- [x] `check`: every item against the current policy, orphan files, missing files, stale features
- [x] **A buffer fills, refuses a write loudly, recovers with `--auto-cleanup`, and an item transferred from it into a sticker box passes only once the required tags are given**
- [x] Security code review of M6 and M7 (§12); findings fixed or recorded (`261108-SECURITY-REVIEW-M7.md`: 9 findings, all fixed with tests)

### M8. Skills, docs, smoke
- [x] `skills/` (§10): `sticker-box` usage, one skill per `telegram-sticker` tag category including the OCR skill with its JSON shape and examples, `vocab-cleanup`, `gallery-maintenance`
- [x] Example policies in `docs/`: meme library (sticker tag rules, no file rules), capped gallery, day-long buffer, stricter metadata; every command checked
- [x] `scripts/smoke.sh`: init each preset, stage, commit, search, frames, dupes, clean, against `testdata/generic/` and, when present, `testdata/private/`
- [x] Integration notes for consumers: install line, environment variables, how to call it, what to put in a skill (`docs/integration.md`)
- [x] **A new agent given only the skills and an empty box can bootstrap a sticker box from a corpus pack without help** (`261108-ACCEPTANCE-M8.md`; friction fixed)
- [ ] Security code review of the whole tool and the skills (§12), plus a scan of the history for third-party content before the repository goes public

## 1. Scope

In:
- one directory per box, any number of boxes, each with its own policy
- stage, commit, edit, remove, search, contact sheets, duplicates, vocabulary management, limits and cleanup, transfer between boxes
- analysis that needs no model: hashes, keyframes, RapidOCR as a hint, SIFT
- skills that teach an agent to do the parts that need a model (reading text, tagging)

Out:
- filling in tags, text, descriptions or notes; only the caller (an agent or a human) writes them.
  The RapidOCR result is a hint shown at `stage` and kept in the sidecar; it reaches the database
  only if the caller passes it to `commit`
- format conversion of any kind; the caller converts (QQBot turns WebM into GIF before sending)
- any model call; the agent using the tool is the model
- a daemon or background cleanup; nothing happens without a command
- network access, accounts, multi-user sync (the GuidedSticker command center's job, not this one)
- neural embeddings (DINOv2, CLIP); a later option

## 2. Lineage

Port ideas and small modules, never import from sibling repos:

| from | take |
|---|---|
| `../GuidedStickerBootCamp/app/` | pHash, keyframe walk, media decoding; defaults from `260917-CORPUS-NUMBERS.md` |
| `../GuidedStickerObservatory/service/noise.py` | the noise gate for RapidOCR text; watermarks such as a pack's `@handle` are text, not noise |
| `../GuidedStickerTagger-SNAPSHOT-260920/` | one narrow question per tag class; composite on white before reading; character ID by vision is unreliable |
| `../260622-PerceptualHash-Brainstorming.txt` | SIFT/ORB + RANSAC for stills against animation frames |
| `../GuidedStickerPostOffice/260919-Opus-Consultation.md` | short Chinese queries need `LIKE`, not FTS5 trigram |

Private test corpora, never committed (§11): `../GuidedSticker-Project-TestData` (about 1,650
WebP/WebM across many packs), `../private/pack-a/` and `../private/pack-b/`
(120 WebP each, with a `Manifest`).

## 3. A box on disk

```
<box>
┣━ temporary/       staged files and their analysis sidecars; may be emptied at any time
┣━ persistent/      <yyyymm>/<yyyymmdd>-<sha256>.<ext>, dated by first add
┣━ box.sqlite3
┗━ README.md        generated; starts with: modify this directory only through sticker-box
```

The box path comes from `--box`, else `STICKER_BOX_DIR`, else the current directory if it holds a
`box.sqlite3`. SQLite uses its default rollback journal with a 30 s busy timeout (no WAL side
files, see decision 1), so several agent sessions can use one box at once.

## 4. Commands

```
init <dir> --preset P --language L [--description D]
info                                   policy summary, counts, usage against limits
policy show | set <rule> <json>
manual                                 regenerate README.md
notes show | set [--file F]            the README's "To agents" section

stage <file>... [--license L] [--source S] [--auto-cleanup]
stage --from <box> <ref>               transfer
staged
commit <ref> [--tag cat=value]... [--define cat=value="definition"]...
             [--field name=value]... [--text T] [--description D] [--note N] [--auto-cleanup]
show <ref> | edit <ref> ... | remove <ref>
frames <ref>                           contact sheet path
search <query> [filters]

tag list | new | define | alias | rename | merge | retire
vocab review | lock | unlock

dupes
check
clean [--all]
reindex
```

`<ref>` is a sha256 or a unique prefix of at least 8 hex characters; it names a staged file or a
committed item. Text output by default, `--json` (or `STICKER_BOX_JSON=1`) for agents. Every
failure is `{"error": "<code>", "message": "...", ...details}` with a non-zero exit; validation
failures list every broken rule at once, and an unknown tag lists its nearest existing tags.
Warnings (e.g. a tag in an unexpected script) ride along in a `warnings` array without failing.

## 5. Schema (`box.sqlite3`)

```sql
meta(key TEXT PRIMARY KEY, value TEXT)
  -- schema_version, preset, language, description, created_at, vocabulary_mode, agent_notes

policy_rule(name TEXT PRIMARY KEY, params TEXT NOT NULL)          -- JSON
policy_log(at TEXT, name TEXT, old TEXT, new TEXT)

item(
  sha256 TEXT PRIMARY KEY, file TEXT NOT NULL,                    -- path under persistent/
  format TEXT, width INT, height INT, animated INT, frames INT, duration_ms INT, bytes INT,
  phash INT, added_at TEXT, expires_at TEXT,
  license TEXT NOT NULL, source TEXT,
  text TEXT, description TEXT, note TEXT
)
item_field(sha256 TEXT, name TEXT, value TEXT, PRIMARY KEY (sha256, name))   -- policy-declared fields
keyframe(sha256 TEXT, idx INT, t_ms INT, phash INT, PRIMARY KEY (sha256, idx))

tag(id INTEGER PRIMARY KEY, category TEXT, value TEXT, definition TEXT,
    parent_id INT, lang TEXT, created_at TEXT, retired_at TEXT, UNIQUE (category, value))
tag_alias(tag_id INT, alias TEXT, PRIMARY KEY (tag_id, alias))
item_tag(sha256 TEXT, tag_id INT, PRIMARY KEY (sha256, tag_id))
vocab_log(at TEXT, action TEXT, details TEXT)

feature(sha256 TEXT, frame INT, extractor TEXT, n INT, kp BLOB, desc BLOB, PRIMARY KEY (sha256, frame))
relation(a TEXT, b TEXT, kind TEXT, score REAL, transform TEXT, found_at TEXT, PRIMARY KEY (a, b))
```

`tag.lang` is null for the instance language and set only for a meme phrase kept in its original
language. OCR text is verbatim and exempt. Keyframe images are not stored; `frames` re-decodes the
file.

## 6. Policy and presets

The policy is data in `policy_rule`; the checks are code in `sticker_box/policy.py`. A box never
contains scripts. Rule kinds:

| rule | params |
|---|---|
| `fields` | declared fields and which are required (`license` always exists; `unknown` is valid) |
| `categories` | name, description, cardinality `one` / `at_least_one` / `any`, required |
| `files` | formats, side rules (max, min, exact on one side), max bytes per format, duration, fps, audio, animation allowed |
| `vocabulary` | `free` / `open` / `locked` |
| `duplicates` | methods (`sha256`, `phash`, `sift`), thresholds, on-duplicate `reject` / `report` / `link` |
| `limits` | max total bytes, max items |
| `retention` | expiry after add |

| preset | files | tags | duplicates | limits / retention |
|---|---|---|---|---|
| `telegram-sticker` | Telegram spec: WebP static, WebM VP9 video, one side 512 and the other at most 512, size, duration and fps caps (verify in M1) | categories text, emotion, character, series, visual; usage note; `open` | sha256, pHash; reject | none |
| `gallery` | any | `free` | sha256, pHash, SIFT; report | optional size cap |
| `buffer` | any | none required; `free` | sha256, pHash; link | expiry (e.g. 60 min), optional size cap |

The meme library is a documented example (M8): the sticker categories with the file rules off.

What the box's agents prefer (reference sources for tags and their precedence, image banks for
examples) belongs to the agents, not to the box, so it is not policy. It lives in
`meta.agent_notes`, written with `notes set`, and appears in the generated `README.md` under
"To agents". The tool stores and renders it and never acts on it.

## 7. Vocabulary

- `free`: any tag, created on first use, definition optional (gallery, buffer).
- `open`: `commit` may create a tag inline with `--define`; an unknown tag without a definition is
  refused with suggestions. This is the bootstrap phase.
- `locked`: `commit` takes existing tags only; a new tag needs `tag new` with a definition.

The intended path for a sticker box is `open` while the agent tags its first stickers, then a
cleanup pass driven by `vocab review` (merge, alias, define, set parents), then `vocab lock`. A
dream-style session can later propose further changes through the same verbs.

## 8. Duplicates

Checked at `stage` (reported) and recorded at `commit` (`relation`):

1. sha256: identical file.
2. pHash: Hamming distance over all items and keyframes, vectorised; catches recompression,
   resizing, format change.
3. SIFT (gallery): stream `feature` rows in batches of about 200 images, stack descriptors with an
   owner array, vote by nearest neighbours without a ratio test, keep the top few, then per pair
   ratio test and `cv2.findHomography` with RANSAC. The homography names the relation (crop region,
   zoom, rotation). Images with too few keypoints skip SIFT.

Upgrade paths if a full scan gets slow, both addable by `reindex` without touching images:
multi-index hashing for pHash (four 16-bit indexed chunks) and visual words for SIFT
(`image_word(word, image_id)` with an index). Details in the design notes, §8.

## 9. Lifecycle

- `stage` is the upload step: the file is in `temporary/`, referenceable, with a sidecar holding
  the analysis and the extractor version; no row exists. `commit` reuses the sidecar or recomputes
  when it is missing or stale.
- `commit` checks fields, categories, vocabulary and file rules, then moves the file and writes the
  row in one transaction.
- Nothing is cleaned implicitly. `clean` removes staged files older than a grace period and expired
  items; `--all` removes every staged file.
- A write that would exceed a limit fails with usage, limit and the `clean` command. Reads and
  search never fail on a limit. `--auto-cleanup` on a write removes expired items, then the oldest
  until under the limit, and lists what it removed.
- Transfer is `stage --from`; the destination validates at `commit` like anything else.

## 10. Skills

Shipped in `skills/` as generic agent instructions; a consumer copies and adapts them (QQBot
translates its bot-facing skills into Chinese).

Two kinds, kept apart: skills for operating the tool, and skills for adding tags. An agent that
only stores and sends (a gallery) needs the first kind alone.

Using the tool:

- `sticker-box`: what a box is, the commands, reading `README.md` first, error handling.
- `gallery-maintenance`: working through `dupes` and limits.

Adding tags:

- One per `telegram-sticker` category. The OCR skill asks for `{"has_text": bool, "text": str}`,
  gives the RapidOCR text from `stage` as an unreliable hint, keeps watermarks as text, and has
  worked examples written for the skill (no transcriptions of third-party stickers). Character and
  series skills prefer source metadata over what the image suggests.
- `vocab-cleanup`: a pass over `vocab review` ending in `vocab lock`.
- Reference sources: a box should use only a few, in a clear precedence, recorded in the box's
  agent notes at bootstrap.
  - Dictionary for names (series, characters): [bangumi-data](https://github.com/bangumi-data/bangumi-data)
    first for anime and subculture (it has no memes), then Wikipedia, IMDb and the like.
  - Image banks, for examples or when unsure what something looks like (not reverse image
    search): Safebooru, Giphy, Pinterest, in an order the box chooses.

## 11. Conventions

- Python 3.12, `python3` everywhere; dependencies: `numpy`, `scipy`, `opencv-python-headless`,
  `pillow`, `rapidocr-onnxruntime`, `onnxruntime`; `pytest` for tests.
- Layering: `cli.py` parses and prints; modules own the rules; `db.py` owns SQL and migrations.
- The repository will be open source. Never commit third-party or confidential content: no
  sticker or corpus images, no OCR transcriptions or descriptions of them, no QQBot chat or memory
  data, no keys. The owner's name SmileWuji and email are fine. Measurement notes report numbers,
  not image content.
- Test data, two directories:
  - `testdata/generic/`: committed; only images this repo generates or owns outright.
  - `testdata/private/`: git-ignored; links to or copies of the private corpora (§2), plus any gold
    labels for them. Tests that need it are marked and skip when it is empty.
  Most tests build their own images in code and need neither.
- Comments only where the code cannot say it. Commit messages: one-line summary, then Problem,
  Solution, Testing sections in brief prose.
- Dated notes (`YYMMDD-XXX.md`) for measurements and decisions; the newest wins.
- This workspace sits on an NTFS mount: `git config` writes fail, so edit `.git/config` by hand;
  a venv cannot be created on it, so the dev venv is `~/.venvs/sticker-box`
  (`--system-site-packages`, then `pip install -e . --no-deps --no-build-isolation`); the pytest
  cache plugin is off for the same reason. Run tests with `~/.venvs/sticker-box/bin/python -m pytest -q`.

## 12. Security reviews

At the end of M5, M7 and M8. The tool takes untrusted files and text from agents that may
themselves be acting on untrusted chat input. Look at least at:

- paths: `<ref>` and `--from` resolution, symlinks and `..` in staged files, writes staying inside
  the box, the box path from the environment
- decoders: oversized and malformed images and videos (pixel and frame caps before decoding,
  Pillow's decompression-bomb guard, timeouts on video decode)
- SQL: parameters everywhere, no string-built queries from tag text or search terms
- the generated `README.md`: tag text, definitions and agent notes are written by agents and read
  by other agents, so it is a prompt-injection surface; render it as quoted data under clear
  headings, and say so in the skills
- concurrency: two sessions committing the same file, `clean` racing a `commit`
- limits: a policy or `--auto-cleanup` that deletes more than intended
- the repository itself: no third-party or confidential content (§11)
