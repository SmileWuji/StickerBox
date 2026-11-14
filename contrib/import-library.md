# Moving an existing image library into boxes

For a host that already has pictures in folders, perhaps with notes of its own, and wants an
agent to put them into sticker-box boxes with proper tags. It is a recipe, not a command: the
agent does the tagging, the host does the bookkeeping.

QQBot, the tool's first user, moved about 300 pictures this way (2026-11-10): one model
(DeepSeek), about 14 s per picture, 50 minutes in all, no failed batch. Its code is a plugin
outside this repository; what follows is the part any host can reuse.

## Lay the library out by box and pack

```
import/
┣━ stickers/
┃  ┣━ <pack name>/
┃  ┃  ┣━ about.md        optional: what the pack is, its source and licence
┃  ┃  ┗━ *.webp, *.png, *.gif, *.webm, *.jpg
┃  ┗━ <pack name>/
┗━ gallery/
   ┗━ <folder>/
```

Name each pack folder the way the pack should be named in the box, in readable words. A folder
id copied as the pack name (`some-site-id` instead of the pack's title) ends up in every tag.

## Before the first batch

- Create the boxes and set their policy (the host's job, not the agent's).
- Create the pack tags yourself, so every batch uses the same names:
  `sticker-box tag new pack "<pack name>" --means "<one line about the pack>" --box stickers`.
  In a `telegram-sticker` box `pack` is a names category, so a pack name in any script draws no
  warning.

## Batches

Offer about 20 pictures per batch, each batch in a fresh session with no chat history, so the
context stays small and one confused batch cannot spill into the next. The batch prompt carries:

- the file paths, with the target box for each;
- per pack: its name, the `--source` and `--license` to use (`unknown` when nobody knows), and
  `about.md` if there is one;
- any old notes per picture, marked as hints;
- what to read first: the `sticker-box` skill with `workflows/tagging.md`, the four `tag-*`
  skills for a sticker box, and the box's `README.md` (existing tags and the "To agents" notes);
- the steps per picture: `stage`, look at the staged file (or at `frames` for an animation),
  then `commit` with every required field and tag, plus `--tag pack=<name>`;
- that the agent may leave a picture out, decides about reported duplicates as the skill says,
  converts or skips a file with `file_problems` (see `contrib/convert/`), and fixes and retries
  a refused `commit`;
- that old notes are checked against the image and rewritten, never copied: they were written
  for another purpose and are often wrong.

Name the skills in the prompt. In QQBot's logs the agent read the `tag-*` skills in every
session whose prompt named them and almost never on its own.

## Keep a ledger keyed by sha256

The host, not the agent, records progress, keyed by each file's sha256 rather than its path, so
renames and duplicate copies are harmless:

- **stored** once `sticker-box show <sha256> --box <box> --json` exits 0 with a `status` other
  than `staged`;
- **skipped** once a batch that offered it finished without storing it: the agent chose to leave
  it out;
- **pending** otherwise. A batch that timed out leaves its unfinished pictures pending, and the
  run stops when a batch makes no progress, so a broken setup cannot loop.

A picture the agent converted before storing is stored under the converted file's sha256, so
the ledger counts the original as skipped. The picture is in the box; only the per-pack count of
kept pictures is low.

## After the last batch

Run one vocabulary cleanup session (`skills/sticker-box/workflows/vocab-cleanup.md`) over each
box that received pictures. In QQBot's run the agent merged near-twins, decided on its own to
lock the vocabulary, and wrote box notes worth keeping: pack conventions, tag habits, and pairs
of tags it had looked at and deliberately kept apart.

One data point on tag quality, not a benchmark: DeepSeek ended with 39 emotion tags (20
aliases), 108 visual tags (44 used once, somewhat fragmented) and 11 characters.
