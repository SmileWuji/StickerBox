#!/bin/sh
# A maintenance session over a gallery. Run from inside a copy of before/: gallery/ holds five
# pictures. First read gallery/README.md for its limits.

sticker-box info --box gallery --json

# Groups of related pictures, with how they relate and suggested commands.
sticker-box dupes --box gallery --json

# One group of four around the lake photo (ff6b96e37fc4):
# - bf39c3eab633 is the same picture re-saved at lower quality: the one suggested removal, and
#   the right one (same size, so the older copy stays);
# - 043e950c43fa is a chat screenshot that contains the photo. It is the group's `keeper` only
#   because it is the largest; keep it for the conversation, but it does not replace the photo;
# - 93a16428dd34 is a zoomed crop: a different framing, worth keeping.
# The hills picture is in no group. Look at the files before acting, then remove only the copy.
sticker-box remove bf39c3eab633 --box gallery --json

# The group is smaller now and no removal is suggested.
sticker-box dupes --box gallery --json

# The audit compares every picture with the rules and the folder with the index; it changes
# nothing. Orphan files would be reported to whoever runs the box, never deleted.
sticker-box check --box gallery --json
