---
name: vocab-cleanup
description: Clean up a sticker box's tag vocabulary by merging near-twin tags and adding definitions, aliases and broader tags, then lock it when it is stable. Use for a scheduled curation session, or after bootstrapping a new box.
---

# Vocabulary cleanup

The vocabulary starts open: tags are created while stickers are added. After the first batch
(fifty to a hundred stickers) run this pass, then lock the vocabulary. Run it again now and then.

## The pass

1. `sticker-box vocab review --json` lists:
   - `similar_pairs`: tags that look alike, with a ready `merge_hint` that keeps the more used
     one. Merge when they mean the same (无语 / 无语了). Keep both when they differ (哭 / 大哭
     may be worth two tags; link them with a parent instead).
   - `undefined`: tags without a definition. Add one: `sticker-box tag define emotion 无语 "..."`.
   - `unused`: tags no image carries. Retire them (`tag retire`) unless they will be used soon.
2. Look for synonyms the review cannot see because they share no characters (生气 / 愤怒,
   开心 / 高兴): read the vocabulary in `README.md` category by category.
3. Merge: `sticker-box tag merge <category> <from> <into>`. Every image moves to the second tag
   and the first becomes an alias, so old habits still resolve.
4. Add aliases for common other spellings and languages: `sticker-box tag alias emotion 无语 无言`.
5. Group: `sticker-box tag parent emotion 嫌弃 负面`. A search for the broader tag finds the
   narrower ones.
6. When the vocabulary has stopped growing much: `sticker-box vocab lock`. From then on a new
   tag needs `sticker-box tag new <category> <value> --means "..."`, which should be rare and
   deliberate. `vocab unlock` reopens it.

Every change is logged and shows up in `README.md`, which is the vocabulary's manual for every
other agent and for humans; write definitions with that reader in mind.

Changing tags is fine at any time; nothing about an image is lost by a merge or a rename.
