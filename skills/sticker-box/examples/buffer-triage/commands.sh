#!/bin/sh
# A triage session over a buffer before its images expire. Run from inside a copy of before/:
# buffer/ holds three images from a chat, stickers/ is a sticker box and gallery/ a gallery.
#
# First read the three README.md files: the buffer keeps images for 60 minutes; the sticker box
# takes 512 px WEBP or WEBM only and needs text, note, licence and an emotion tag; the gallery
# takes anything and needs only a licence.

# List the buffer. With no words the newest come first; the last ones expire soonest.
sticker-box search --box buffer --limit 50 --json

# Look at each image (the `file` path) and decide. The oldest: a laughing orange face with tears
# and "LOL". Someone would send it in a chat, so it is a sticker. Stage it into the sticker box.
sticker-box stage --from buffer e26ecca836fc --box stickers --json

# It passes the file rules. `origin` holds the buffer's note as a hint written by someone else;
# check it against the image. The licence came along. Tag it and commit.
sticker-box commit e26ecca836fc --box stickers --text LOL --note "有人讲了好笑的笑话、笑到流泪的时候" \
  --tag emotion=开心 --define visual=笑出眼泪 "笑得流出眼泪" --json

# The next: a chat screenshot with a lake photo in it. Not a sticker, but worth finding again,
# so it goes to the gallery.
sticker-box stage --from buffer d72ff021c680 --box gallery --json
sticker-box commit d72ff021c680 --box gallery --tag screenshot --tag lake \
  --note "the lake trip photo shared in the group chat" --json

# The newest: a dark, blurred photo, sent by accident. Nothing to keep, so do nothing; it
# expires on schedule. Moving copies: the buffer's own copies expire too.

# ... 40 minutes later ...

# Every buffer image is now past its expiry. `clean` removes them (never `--auto-cleanup`
# during triage: it removes the oldest images, which are the ones not looked at yet).
sticker-box clean --box buffer --json
sticker-box info --box buffer --json
