#!/bin/sh
# A vocabulary cleanup after the first stickers, ending with a lock. Run from inside a copy of
# before/: stickers/ holds seven stickers tagged while the vocabulary was open. First read the
# vocabulary in stickers/README.md, category by category.

sticker-box vocab review --box stickers --json

# The review's pairs, read with their definitions:
# - 无语了 / 无语: the same word with a particle. Merge into 无语; 无语了 becomes an alias, so
#   old habits still resolve.
# - 哭 / 大哭: crying, and crying hard. Different enough to keep both; group them instead.
# 困惑 is unused and nothing in this box is likely to need it soon: retire it.
sticker-box tag merge emotion 无语了 无语 --box stickers --json

# The review cannot see synonyms that share no character. Reading the README shows 高兴 means
# the same as 开心, the more used one.
sticker-box tag merge emotion 高兴 开心 --box stickers --json

# Another common way to say 无语, as an alias.
sticker-box tag alias emotion 无语 无言 --box stickers --json

# Group the crying tags under a broader one, created first with a definition.
sticker-box tag new emotion 难过 --means "伤心、不开心的总称" --box stickers --json
sticker-box tag parent emotion 哭 难过 --box stickers --json
sticker-box tag parent emotion 大哭 难过 --box stickers --json

sticker-box tag retire emotion 困惑 --box stickers --json

# Review again: only the deliberate pair is left, and 难过 shows as unused, which is right for a
# parent that groups other tags. Lock the vocabulary.
sticker-box vocab review --box stickers --json
sticker-box vocab lock --box stickers --json

# A search for the broader tag finds the narrower ones; an alias works like the tag.
sticker-box search 难过 --box stickers --json
sticker-box search --tag emotion=无言 --box stickers --json
