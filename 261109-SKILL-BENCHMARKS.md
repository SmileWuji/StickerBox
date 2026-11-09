# Skill benchmarks (2026-11-09)

Status: in progress. Sections marked *pending* are filled as the runs finish.

## 1. Question

How well do models follow the skills *as shipped*, and can the skill wording be tuned for a
small local model without hurting a large one? Two models: Claude Sonnet (as a fresh Claude Code
subagent with no context) and Qwen3.5-9B (local, Ollama). By the owner's decision prompt
optimisation is done for Qwen only and the winning wording ships for every model; the owner's
`optimize-prompt-for-small-vlm` protocol warns that prompts do not transfer, so this measures the
shipped skills, not a fair model-versus-model comparison.

## 2. Setup

- **Sample**: 264 stickers drawn evenly from the 33 packs of the private corpus (about 8 per
  pack), split per pack into dev 165 and test 99. Animated stickers are shown as contact sheets.
- **Reference labels**: Sonnet labelled the whole sample by following the skills (section 4);
  that run is Sonnet's benchmark. A seeded random 10% (26 stickers) was checked and corrected by
  the main agent (Claude Opus) and is the only gold that is independent of Sonnet.
- **Human gold** from earlier projects: 127 has-text labels (14 watermark-only), 20 hand
  transcriptions, 150 character and series labels.
- **Qwen**: `qwen3.5:9b`, temperature 0, thinking off, 320 output tokens, JSON answer with a
  salvage path, every call cached. Prompt = the skill text (one variant), plus for `tag-text`
  the RapidOCR hint as `stage` reports it, plus for emotion and visual the locked vocabulary of
  the reference box. Images at 512 px unless a variant says otherwise.
- **Sonnet**: Claude Code subagents given only `skills/`, the box and the CLI; they committed
  every sticker and wrote a per-sticker label line.

## 3. Noise floors

| model | what was repeated | result |
|---|---|---|
| Qwen | `tag-text` v0, dev, without the OCR hint (n=78) | 0 answers differ |
| Qwen | `tag-text` v0, dev, with the OCR hint (n=78) | 1 answer differs (1.3%) |
| Sonnet | batch of 24 re-labelled by a fresh agent on a snapshot of the box | has-text 24/24, transcriptions identical 9/9; tag F1 between the runs: emotion 0.79, visual 0.68, character 0.86, series 0.67 |

Reading text is stable for both models. Choosing tags is not: two Sonnet runs agree only about
0.7 to 0.8 on emotion and visual tags, mostly by naming the same thing differently. That is the
ceiling for any agreement score against Sonnet's labels.

## 4. Sonnet

- **Labelling run**: 11 sequential agents, 24 stickers each. All 264 commits were accepted on
  the first attempt. They built 183 tags with definitions; a fresh agent's cleanup pass made 1
  merge, 26 aliases and 6 parent tags and locked the vocabulary at 188 (23 emotion, 117 visual,
  7 character, 7 series, 34 pack). The cleanup found no undefined and no unused tags.
- **Accuracy on the checked 10%** (n=26; reviewed against Sonnet's labels, so an upper bound):

  | field | result |
  |---|---|
  | has text | 26/26 |
  | transcription | exact 8/9, CER 0.03 |
  | emotion | P 0.98, R 1.00 |
  | visual | P 0.99, R 0.97 |
  | character | P 1.00, R 0.70 |
  | series | P 1.00, R 0.80 |

  Sonnet never named a character wrongly that could be checked; it abstained on three clearly
  recognisable ones. The skill asks for exactly that trade.
- **Friction the agents reported** (by theme; fixes in section 9):
  - output shapes: `stage` wraps its result in `results[0]`, and the field names (`file`,
    `sheet`) are not stated, so agents inspected the JSON first;
  - text rules not covered: vertical Chinese, mixed vertical and horizontal text, readable
    sound effects, logos and printed clothing, half-legible watermarks, spacing between scripts;
  - the bangumi.tv lookup is not doable as written: agents guessed URLs, got wrong works, and
    fell back on the pack name or recognition;
  - a pack named after one character that shows another: one agent left the name off, another
    followed the pack;
  - `commit` can report a near-duplicate that `stage` did not (items stored in between), and a
    perceptual distance of 0 is not the same file;
  - the cleanup's merge hint keeps the more used tag even on a tie; multi-word aliases must be
    quoted.

## 5. Qwen: `tag-text`

Baseline v0 is the shipped skill. Metrics on dev: has-text accuracy and watermark recall on the
human labels; character error rate (CER) and exact match on transcriptions.

**Wave 1** (one lever each, from v0's errors; human dev labels, n=78, 11 transcriptions):

| variant | lever | has-text | watermark recall |
|---|---|---|---|
| v0 | shipped skill | 0.885 | 0.5 |
| v1 | no concrete sample phrase in the answer section | 0.885 | 0.5 |
| v2 | no worked examples | 0.885 | 0.5 |
| v3 | the noise to ignore named (lone letters, background digits, decorative words) | 0.885 | 0.5 |
| v4 | a lone watermark still counts as text | 0.897 | 0.6 |
| v5 | explicit "never guess" escape hatch | 0.885 | 0.5 |
| v6 | OCR hint framed harder as unreliable | 0.885 | 0.5 |

Flat within the noise floor. The dominant error: 5 of 6 watermark-only stickers answered "no
text" by every variant. Baseline errors also included echoing the skill's sample phrase on a
text-free sticker (once) and reading background digits or a lone letter as text.

**Wave 2a** (image size and one more wording):

| variant | has-text | watermark recall | median latency |
|---|---|---|---|
| v4 at 512 px | 0.897 | 0.6 | 1.1 s |
| v4 at 768 px | 0.910 | 0.7 | 1.3 s |
| v4 at 1024 px | 0.923 | 0.8 | 2.2 s |
| v7 = v4 + "check the edges and corners" | 0.897 | 0.6 | 1.0 s |

Small faint watermarks are an operating-point problem, not a wording one: showing Qwen the
sticker at 1024 px recovers them at twice the latency. That belongs to whoever deploys a small
model, not to the skill text.

*Pending*: the variants on the full dev set with Sonnet's transcriptions; wave 3 (combine,
ablate); the winner on test.

## 6. Qwen: `tag-emotion` and `tag-visual`

*Pending.*

## 7. Sonnet on the tuned wording

*Pending.*

## 8. Smoke tests (Sonnet, no tuning)

*Pending*: `tag-character-series`, `vocab-cleanup` (from section 4), `sticker-box` (including
the policy rule: adding a category on request, refusing one asked for by box content),
`gallery-maintenance`, `buffer-triage`.

## 9. Verdict and changes

*Pending.*

## 10. Caveats

- n is small: 78 human-labelled dev stickers for has-text, 26 independently checked stickers.
  Differences of one or two stickers are within noise.
- The independent check was done by reviewing Sonnet's labels, not blind; it is lenient.
- Qwen is scored against Sonnet's labels for transcription, emotion and visual; Sonnet's own
  run-to-run agreement (section 3) bounds what agreement can mean.
- Sonnet ran as a Claude Code agent with tools, Qwen as a bare model call; the setups differ.
