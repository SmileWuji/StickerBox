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

State on 2026-11-09 (evening): M0 to M8 and the backlog are done. 223 tests and
`scripts/smoke.sh` pass. Read in this order:

1. `261109-SKILL-BENCHMARKS.md`: how Sonnet and Qwen3.5-9B follow the skills, what the prompt
   sweeps changed (little), the smoke tests of every tool skill, and the skill text that now
   ships. Section 9 is the verdict.
2. `261108-BUILD-DECISIONS.md`: every decision, each with its reason and how to undo it;
   38 to 42 are from the backlog. Nothing there is hard to reverse.
3. `261109-OPS-BASELINE.md`: speed and memory of every command from 1k to 30k stickers.
4. `261108-ACCEPTANCE-M8.md`, `261108-SIFT-TUNING.md`, `261108-CORPUS-ANALYSIS.md`: earlier
   measurements.
5. `261108-SECURITY-REVIEW-M5.md`, `261108-SECURITY-REVIEW-M7.md`,
   `261109-SECURITY-REVIEW-M8.md`: three reviews, every finding fixed with a test.

Needs your call:

- **QQBot wiring** is yours, per the plan: `docs/integration.md` lists install, environment,
  exit codes, the skills to copy, which model to give the tagging skills, and how to label box
  content as data in a plugin.
- **Gold labels** are now optional. The benchmark ran on Sonnet's labels with a 10% check;
  human labels would add a human-agreement ceiling for emotion and visual tags and zh-Hans
  names for the character test. The counts are in the backlog item "Skill benchmarks".
- **DeepSeek** (QQBot's model) was not benchmarked; adding it means replacing the model call
  in `scripts/bench_skills/qwen.py`.

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
- [x] Duplicates are reported, never acted on, with suggested `remove` commands (decision 36; there is no on-duplicate setting); `relation` rows written at commit, including still-to-keyframe links
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
- [x] Security code review of the whole tool and the skills (§12), plus a scan of the history for third-party content before the repository goes public (`261109-SECURITY-REVIEW-M8.md`; history scrubbed 2026-11-09)

### Backlog

Not scheduled; pick up when the owner asks.

- [x] `skills/buffer-triage` (done 2026-11-09): a short skill for a scheduled session over a buffer box. For each
      item before it expires, decide: move it to the sticker box or the gallery
      (`stage --from`, then commit with that box's required tags), or let it expire. Covers
      reading `search` with no words (newest first), `frames` for animations, the `origin` hints,
      and that nothing is moved without a decision. Suggested by the owner 2026-11-09.

- [x] Skill benchmarks (done 2026-11-09, `261109-SKILL-BENCHMARKS.md`; run on Sonnet's labels with a 10% check instead of new human gold, by the owner's choice): run the skills that make sense to measure with Claude Sonnet 5.5
      (`claude-sonnet-5-5`) and Qwen3.5-9B (`qwen3.5:9b` via Ollama, or OpenRouter), on a fixed
      private gold set of a few hundred hand-labelled stickers (in `testdata/private`, never
      committed); record the numbers in a dated note. Suggested by the owner 2026-11-09.
      - `tag-text`: has_text accuracy, exact match and character error rate against hand
        transcriptions, watermark recall.
      - `tag-emotion`, `tag-visual`: agreement with gold labels (semantic F1, as in the old
        Tagger eval), and vocabulary reuse (new tags created per 100 stickers).
      - `tag-character-series`: precision of names and abstention rate (a wrong name is worse
        than none).
      - `vocab-cleanup`: proposed merges against a hand-judged list of true twins and false pairs.
      - `sticker-tagging` end to end, `sticker-box`, `gallery-maintenance`: task success on
        scripted tasks (commits accepted first time, problems per commit, sensible `dupes`
        decisions) rather than accuracy.
      - Method: measure the noise floor first (the same model twice). Prompt optimisation is
        expensive, so it is done for Qwen only (the owner's `optimize-prompt-for-small-vlm`
        skill has the protocol), and the resulting skill wording is used unchanged for Sonnet
        too: one skill text for every model (decided 2026-11-09). Tune on a dev split of the gold
        set and report on a held-out split. Then run Sonnet once on the original and once on the
        Qwen-tuned wording; if the tuned wording is worse for Sonnet, record that and keep the
        original as Sonnet's reference. Prior art: the Observatory OCR benchmark and the old
        Tagger evaluation (`../GuidedStickerTagger-SNAPSHOT-260920/eval/`). DeepSeek, the model
        QQBot runs on, can be added as a third.
      - Gold labels, **the owner's action item** (counted 2026-11-09; all existing labels map to
        current corpus files). Existing: the Observatory OCR gold
        (`../GuidedStickerObservatory/.claude/skills/benchmark-observatory/bench/gold/`: 127
        has-text, 14 with watermarks, 20 transcriptions, 95 noise) and the old Tagger gold
        (`../Tagger-Benchmark/labels/phase_b_gt.json`: 150 stickers reviewed by the owner, 138
        named, 31 characters in 11 series, 10 without a character, 10 probes). To add, aiming to
        tell two models apart by about 10 points (roughly 5 to 6 hours in all):
        - `tag-text`, has text: about 75 more (to about 200), chosen so at least 40 have a
          watermark.
        - `tag-text`, transcription: about 130 more (to about 150), starting with the 60 has-text
          stickers not yet transcribed.
        - `tag-character-series`: zh-Hans canonical names for the 31 characters and 11 series,
          and about 30 more stickers with no character.
        - `tag-emotion` and `tag-visual`: about 200 stickers labelled for both (the 150 Tagger
          stickers plus 50), and a second person on 50 of them to measure human agreement.
        - `vocab-cleanup`: about 100 tag pairs from one bootstrap run, judged same or different.
        - `gallery-maintenance`: about 100 real chat images later; generated variants stand in.
        - End-to-end tool skills: none needed.
        - If a model pre-fills labels for correction, use one that is not being benchmarked.

- [x] Skill command check (not a benchmark, done 2026-11-09 in `tests/test_skill_commands.py`): a unit test that extracts every `sticker-box ...`
      command written in `skills/`, `docs/` and the README and parses it against the current CLI
      (command, flags, argument order) without running it, so instructions cannot go stale when
      the CLI changes. Placeholders such as `<ref>` are replaced by dummy values first. Suggested
      2026-11-09; the skills were edited after the acceptance test and are not re-checked yet.

- [x] Operations benchmark and baseline (done 2026-11-09, `261109-OPS-BASELINE.md`): build the benchmark designed in
      `261109-OPS-BENCHMARK-DESIGN.md` (lookups, additions, changes, removals, maintenance,
      concurrency and process start, at box sizes from 1k to 30k, on synthetic data), record the
      baseline in a dated note, then decide which indexes or algorithm changes are worth it.
      Suggested by the owner 2026-11-09; to be done when the backlog is cleaned up.

### Backlog execution (started 2026-11-09)

Plan approved by the owner; the full plan is kept in the session's plan file, and the steps
below are self-describing. Tick each box in the commit that finishes it; add a "done / next"
line under a half-done box. Long runs cache every model call to JSONL under
`testdata/private/bench/` (git-ignored), so they resume instead of restarting. Decisions for
this run: Sonnet runs as a fresh subagent (no API key); Sonnet labels ~250 stickers by following
the skills, which is also its benchmark, and 10% are checked and corrected by the main agent;
Qwen3.5-9B (local Ollama) is prompt-optimised for `tag-text`, `tag-emotion`, `tag-visual`, and
the winning wording ships for every model; `tag-character-series`, `vocab-cleanup` and the tool
skills are smoke-tested with Sonnet only. Dataset names never appear in the repository; code
names live in the git-ignored `testdata/private/CODENAMES.txt`.

Finished 2026-11-09: every step below is done. The Qwen runs needed Ollama started with
`OLLAMA_MODELS=../OCR-Benchmark/.ollama-models ollama serve` (run from this repo); every model call
is cached in `testdata/private/bench/qwen/cache.jsonl`, so `scripts/bench_skills/qwen.py score`
reproduces each number without the GPU. Run long Qwen jobs from one sequential script, never with
`pgrep` waits on each other, and not while several Sonnet agents run (the host swaps).

- [x] 0.1 Manifest (path, size, sha256) of all four sticker sources written to the scratchpad
- [x] 0.2 Packs moved into `../GuidedSticker-Project-TestData-Consolidated/`
- [x] 0.3 Manifest verified against the consolidated directory (2,975 files, 33 packs); emptied source folders removed with `rmdir` only
  - 3,008 files (2,975 stickers and 33 manifests) verified by sha256, 0 mismatches; the test-data repo keeps only its own files; no symlink at the old path (owner's choice)
- [x] 0.4 `testdata/private` relinked to the consolidated directory, code names updated; private tests pass
- [x] 1 Skill command check test (`tests/test_skill_commands.py`), stale commands fixed
  - 49 documented commands parse; no stale ones found; four known-stale samples are caught
- [x] 2 `buffer-triage` skill written and listed in `skills/README.md`
- [x] 3.1 `scripts/bench_ops.py` built per `261109-OPS-BENCHMARK-DESIGN.md`
- [x] 3.2 Baseline run on `/tmp` and the NTFS mount; `261109-OPS-BASELINE.md` written
- [x] 3.3 Small fixes for missed targets re-measured and recorded (or deferred with reasons)
  - lazy imports: `show` 266 to 108 ms, `remove` 299 to 137 ms as processes; search above 10k, gallery double matching, `check` on 9p and OCR model load deferred with reasons
- [x] 4.1 Benchmark sample drawn (~250, dev 150 / test 100) and existing human gold mapped
  - 264 stickers from 33 packs (dev 165, test 99) in `testdata/private/bench/sample.json`; human labels resolved: 127 has-text, 20 transcriptions, 150 character/series
- [x] 4.2 Sonnet labelling run (sequential batches) and vocabulary cleanup; Sonnet noise-floor re-run
  - ready: 11 batches of 24 in `testdata/private/bench/batches/`, box `testdata/private/bench/sonnet-box` (file rules off), brief `testdata/private/bench/sonnet-prompt.md`; output `bench/sonnet/labels.jsonl`; snapshot the box before batch 05 for the noise-floor re-run. Done: 264/264 committed on the first attempt; cleanup by a fresh Sonnet: 1 merge, 26 aliases, 6 parents, locked at 188 tags; reference in `bench/sonnet/final.json`. Sonnet noise floor (batch 05 re-run on the snapshot, n=24): has-text 24/24, text identical 9/9, tag F1 between runs emotion 0.79, visual 0.68, character 0.86, series 0.67; friction notes in `bench/friction.md`. Next: batches 03 to 11 one at a time, copying the box to `bench/sonnet-box-pre05` before batch 05
- [x] 4.3 10% checked and corrected by the main agent; Sonnet accuracy per field computed
  - n=26 (seeded): has-text 26/26; transcription exact 8/9 (CER 0.03); emotion P 0.98 R 1.00; visual P 0.99 R 0.97; character P 1.00 R 0.70; series P 1.00 R 0.80. Reviewed against Sonnet's labels, so an upper bound. Corrected gold in `bench/checked.json`
- [x] 4.4 Ollama up with `qwen3.5:9b`; Qwen harness built; Qwen noise floor measured
  - Ollama runs with `OLLAMA_MODELS=../OCR-Benchmark/.ollama-models` (model already there); harness `scripts/bench_skills/qwen.py`. tag-text v0 on dev: answers differ on 1 of 78 between runs (with the OCR hint passed, as in production; 0 of 78 without it)
- [x] 4.5 Qwen sweep `tag-text` (dev), winner on test
  - wave 1 (v1 to v6) on the human dev labels: flat (has-text 0.885 to 0.897, n=78; only v4 "a lone watermark counts" +1). Dominant error: 5 of 6 watermark-only stickers read as no text by every variant. Wave 2a: image size is the watermark lever (v4 at 512/768/1024 px: has-text 0.897/0.910/0.923, watermark recall 0.6/0.7/0.8, latency 1.1/1.3/2.2 s); v7's corner wording does nothing. Image size is an operating point for the report, not skill wording. Wave 3 (combine, ablate) waits for the reference transcriptions. Transcription scores wait for the Sonnet reference (only 11 human transcriptions on dev)
  - wave 3 done: v10 (v8 without the partial-watermark line) is the dev winner (has-text 0.910, watermark 0.6, CER 0.134); v8@1024 has-text 0.936. Sonnet test (a original, b v10): has-text 0.955 both; v10's vertical line reversed whole-image order on 2 of 9; v11 scopes it to one block, Sonnet fix check fine. Next: v11 on Qwen dev (chain3), then v0 and v11 once on test, then ship v11 into `skills/tag-text`
  - full dev (n=243, 76 reference transcriptions): transcription flat across v0 to v8 (CER 0.167 to 0.191, exact 0.645 to 0.684); v8 (v4 plus the agents' text rules) has-text 0.910, the best wording; v4@1024 0.923 with watermark recall 0.8. Wave 3 running: v9 = v8 without the lone-watermark line, v10 = v8 without the partial-watermark line, v8@1024. Then the winner and v0 on test; Sonnet test batches ready in `bench/sonnet-tt/` (67 human-labelled test stickers, keys in `bench/smoke-keys/`)
- [x] 4.6 Qwen sweep `tag-emotion` (dev), winner on test
  - wave 1 F1 (noise 0.005): v0 0.410, v1 two tags 0.418 (Qwen ignores the count, still 1.1 tags), v2 definitions 0.428, v3 text first 0.425, v4 no word list 0.421, v5 humour 0.433, v6 minimal 0.363. Wave 2 queued (chain4): v7 = v2+v3+v5, v8 = two-tag example, v9 = both
  - noise floor: 7/165 answers differ, F1 0.410/0.414. v0 P 0.52 R 0.36: too few tags (1.07 against 1.71), never the humour tag, 呆滞 and 得意 overused. Wave 1 (v1 two tags, v2 choose from definitions, v3 text first, v4 no word list, v5 humour tag, v6 minimal prompt) queued in `chain1.sh` (scratchpad); run all Qwen jobs from one sequential script, never with pgrep waits (they deadlocked)
- [x] 4.7 Qwen sweep `tag-visual` (dev), winner on test
  - noise floor: 20/165 differ, F1 0.448/0.450. v0 P 0.51 R 0.43; misses face details (blush, open mouth) and accessories, overuses hairstyle and 低头. Wave 1 (v1 three to five, v2 check small details, v3 only what is clear, v4 choose from definitions, v5 minimal) queued after emotion
- [x] 4.8 Winning wording shipped in the skills; Sonnet original-vs-tuned run on test
  - test: tag-text v0 and v11 identical on has-text (0.940), so the dev gain was noise; v11 ships for the agents' cases. Emotion v7 0.436 against 0.411 (ships). Visual v1 0.431 against 0.429 (not shipped). Sonnet: tag-text has-text 0.955 both wordings, v11 keeps reading order; emotion v7 within Sonnet's spread on the 26 checked stickers, not worse
- [x] 4.9 Sonnet smoke tests: `tag-character-series`, `vocab-cleanup`, `sticker-box`, `gallery-maintenance`, `buffer-triage`
  - started 2026-11-09 after the restart: fixtures built by `scripts/bench_skills/smoke_fixtures.py` (boxes in `bench/smoke/`, answer keys in `bench/smoke-keys/`, briefs in `bench/smoke/briefs/`); five Sonnet agents run. All tool tasks and both policy cases passed; triage 9/9; gallery removed the four true copies and kept the crop; cleanup consistent with the first run; characters 5 right, 1 named from an outfit on a probe, 11 left out. Results in the report, section 8; skill fixes committed
  - `sticker-box` tasks include the policy rule: (a) the operator asks for a `race` category for a game-character pack: added as optional through the documented steps, values defined, operator told; (b) a planted box note or tag definition asks for a required category: policy left unchanged, request reported
- [x] 4.10 Skill benchmark report written (dated note)
  - `261109-SKILL-BENCHMARKS.md`, sections 1 to 10; Ollama stopped after the last run
- [x] 5 Backlog boxes ticked, owner section and decisions updated

### Pre-release (started 2026-11-10)

- [x] Leak scan of the tree and history; a series title and a local path replaced in the tree (044795e)
- [x] Performance section with the test machine in `README.md` (65f87c6)
- [x] Code review of the backlog work: 15 findings, fixed in b736d88 (duplicate suggestions, commit order, command check) and 535d8b6 (benchmark scripts); the watermark metric stays (the gold set defines watermarks as @ handles); re-scoring changed only the partial v7 run
- [ ] History rewrite to drop the series title (9e2ef93, 9a79223) and the local path (24b952a): owner's call, asked 2026-11-10
- [x] One `sticker-box` skill (owner, 2026-11-10): `SKILL.md` as the core, `workflows/` for tagging, buffer triage, gallery maintenance, vocabulary cleanup and policy changes; the `tag-*` skills stay as they are
- [x] `skills/sticker-box/examples/<task>/{before/, after/, commands.sh}` with generated, repository-owned images, built by `scripts/make_skill_examples.py`; a test re-runs every `commands.sh`
- [x] Docs follow the merge: `skills/README.md`, `docs/integration.md`, §10 here, decisions 43 and 44; the command check covers `workflows/`, `tests/test_skill_examples.py` re-runs every `commands.sh`
  - five examples (add-stickers, buffer-triage, gallery-maintenance, vocab-cleanup, add-category), about 5.5 MB with the boxes; the video encoder is not deterministic, so the generator keeps the committed input files unless `--redraw`
- [ ] Follow-up (owner, 2026-11-10): re-run the Sonnet smoke tests (report section 8) on the merged skill and note that the labelling run used the pre-merge skills; the Qwen numbers stand because the `tag-*` text is unchanged

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

Private test corpora, never committed (§11): the owner's sticker collections (about 1,900
WebP/WebM files across many packs). Their paths live only in the git-ignored
`testdata/private/sources.default`, read by `scripts/link-private-testdata.sh`.

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
| `duplicates` | pHash distance, SIFT settings (or none); matches are always reported with suggested `remove` commands, never acted on |
| `limits` | max total bytes, max items |
| `retention` | expiry after add |

| preset | files | tags | duplicates | limits / retention |
|---|---|---|---|---|
| `telegram-sticker` | Telegram spec: WebP static, WebM VP9 video, one side 512 and the other at most 512, size, duration and fps caps (verify in M1) | categories text, emotion, character, series, visual; usage note; `open` | sha256, pHash | none |
| `gallery` | any | `free` | sha256, pHash, SIFT | optional size cap |
| `buffer` | any | none required; `free` | sha256, pHash | expiry (e.g. 60 min), optional size cap |

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

One skill for operating the tool, and one per tag category (decision 43, 2026-11-10):

- `sticker-box`: what a box is, the commands, reading `README.md` first, error handling, box text
  as data. Its `workflows/` hold whole tasks (tagging, buffer triage, gallery maintenance,
  vocabulary cleanup with `vocab review` ending in `vocab lock`, policy changes), read only when
  doing that task, so an agent that only stores and sends loads no tagging guidance. Its
  `examples/<task>/{before/, after/, commands.sh, transcript.md}` show each task on real boxes,
  with images drawn by `scripts/make_skill_examples.py`.
- One per `telegram-sticker` category. The OCR skill asks for `{"has_text": bool, "text": str}`,
  gives the RapidOCR text from `stage` as an unreliable hint, keeps watermarks as text, and has
  worked examples written for the skill (no transcriptions of third-party stickers). Character and
  series skills prefer source metadata over what the image suggests.
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
