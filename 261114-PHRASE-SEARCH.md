# Chat phrases in search (2026-11-14)

Why: QQBot runs `search` on the words of a chat message. Chinese has no spaces, so a term is a
whole phrase such as 今天又要加班到十点, and text, notes and descriptions were matched only with
`LIKE '%term%'`: the whole phrase had to appear verbatim. In the bot's first five hours, 4 of 18
searches got any candidate. Tags already matched both ways (a tag value inside the phrase).

## The rule

A term with at least 3 CJK characters (not `category=value`) also matches an item's text, note
or description when they share at least 2 counted character pairs (bigrams within runs of CJK
characters); a term with fewer than 2 counted pairs gets no phrase match at all. Two kinds of
pair do not count:

- a pair of two grammatical words, from a fixed list of about 60 characters (什么, 不会, 你怎,
  能不); and
- a pair carried by more than 30% of the box's items (at least 3), which says nothing about
  which item is meant: in the bot's box, the pairs of the note template "…的时候发" and of the
  words naming its own character, which nearly every description uses.

The score is three quarters of the column's weight (text 6, note 4, description 2) times the
share of the term's counted pairs that the column holds, so a phrase match always ranks below
the same column holding the whole term, and tags (10, 8, 5) stay ahead. Scores are now
decimals. The `matched` entry
says how many pairs were shared, e.g. `description, 4 of 6 character pairs`.

## Measurements

On a scratch copy of the first consumer's sticker box (301 stickers; descriptions median 35
CJK characters, notes 26), with `scripts/bench_skills/search_phrases.py`:

- **Made-up chat phrases** (200): a 4 to 6 character span from an item's description (70%) or
  note, with a filler character (就, 又, 也, 都, 还) inserted inside half the time, wrapped in
  chat words (昨天, 笑死, 了, 啊). Right answers are the items holding the span.
- **Real chat** (300 incoming lines with at least 4 CJK characters, from the same bot's logs,
  split on punctuation as its plugin does). No answer key: the share of lines that get any
  candidate (the plugin offers up to 3), plus a judged sample.

Every row below has the grammatical-pair list unless it says otherwise, and was measured with
the rule as shipped (re-run after the pre-release review made 2 pairs a hard minimum; before,
a term with a single counted pair matched on that one pair).

| setting | made-up hit@1 | hit@3 | MRR | real lines with a candidate |
|---|---|---|---|---|
| before (`LIKE` only) | 0.025 | 0.035 | 0.032 | 0.133 |
| 1 pair, common above 5% | 0.65 | 0.825 | 0.744 | 0.80 |
| 2 pairs, no grammatical list, common above 10% | 0.775 | 0.83 | 0.804 | 0.407 |
| 2 pairs, common above 3% | 0.64 | 0.68 | 0.662 | 0.26 |
| 2 pairs, common above 5% | 0.695 | 0.75 | 0.724 | 0.273 |
| 2 pairs, common above 10% | 0.71 | 0.78 | 0.746 | 0.28 |
| 2 pairs, common above 20% | 0.715 | 0.785 | 0.752 | 0.327 |
| **2 pairs, common above 30% (shipped)** | **0.72** | **0.79** | **0.756** | **0.33** |
| 2 pairs, no frequency filter | 0.795 | 0.865 | 0.832 | 0.347 |
| 3 pairs, common above 5% | 0.435 | 0.455 | 0.448 | 0.143 |

- The first real-chat run also included the bot's own replies, which are written in the same
  voice as its notes and matched them by its form of address (0.787 of lines with a candidate,
  without either filter); the script now skips lines whose `direction` is not `in`.
- Without the grammatical-pair list most real-chat matches were on 你怎么, 能不能, 不会, 我是.
  With it, 40 real lines whose top candidate came from phrase matching (the "no frequency
  filter" setting) were judged by the main agent: about 14 fit the line well enough to send (a
  sticker whose caption repeats the line's key phrase, a "good model" sticker for a question
  about which drawing model), the rest shared two scattered pairs with a long line. Those lines
  got no candidate before.
- Made-up queries favour no frequency filter because they copy spans verbatim, template words
  included. The 30% cut drops only pairs that cannot tell items apart.
- Requiring a contiguous shared run (or 3 pairs) cost a quarter of the made-up hits (hit@3 0.66,
  measured with the earlier rule) and changed real chat little: an inserted word
  (抱着枕头**就**睡着了) breaks the run.

## Cost

Phrase matching reads text, note and description of every item once per search and scans them
once per qualifying term, in Python: per term about 1 to 4 ms at 1,000 items, 14 to 43 ms at
10,000 and 42 to 107 ms at 30,000 (a 30-character term is the slow end). A query with many
long phrases pays this per phrase: 16 twelve-character phrases take about 0.6 s at 30,000.
Collecting each item's pairs once per search, for all terms together, is the first speed-up; an
index of pairs is the upgrade path if boxes grow.
