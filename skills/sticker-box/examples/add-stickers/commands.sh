#!/bin/sh
# Add three stickers to a new sticker box and leave out one that breaks its file rules. Run from
# inside a copy of before/: the box is stickers/, the new files are in inbox/.
#
# First read stickers/README.md. This telegram-sticker box needs `text`, `note` and `license` on
# every image and at least one `emotion` tag. Its vocabulary is open and still empty, so every
# tag is new and needs a definition.

# Stage the first file. Nothing is stored yet; the answer lists what `commit` will need, the
# OCR hint (often wrong) and any file problems or look-alikes (none here).
sticker-box stage inbox/ok.webp --box stickers --json

# The image is a laughing yellow face with "OK!" under it. A first commit without the note and
# with an undefined tag is refused, and the answer lists every problem at once.
sticker-box commit 27e1fa03cc0f --box stickers --text "OK!" --license CC0-1.0 --tag emotion=开心 --json

# Fix all of them and commit again. The note names the situation in words people would type.
sticker-box commit 27e1fa03cc0f --box stickers --text "OK!" --license CC0-1.0 \
  --source "drawn for the sticker-box examples" --note "答应别人、说好、没问题的时候" \
  --define emotion=开心 "高兴、愉快" --define visual=脸红 "脸颊泛红" --json

# The second sticker: a blue face with flat eyes, a sweat drop and "..." under it.
sticker-box stage inbox/speechless.webp --box stickers --json
sticker-box commit b4c8bedcb4b0 --box stickers --text "..." --license CC0-1.0 \
  --source "drawn for the sticker-box examples" --note "对方说了让人无话可说、很无奈的话的时候" \
  --define emotion=无语 "无奈到说不出话" --define visual=流汗 "额头冒汗，尴尬或无奈" --json

# The third is an animation. Look at its contact sheet instead of the video: one picture with
# the keyframes in order. It shows a green face waving, with "HI!" under it.
sticker-box stage inbox/wave.webm --box stickers --json
sticker-box frames fdcaaa075d4f --box stickers --json
sticker-box commit fdcaaa075d4f --box stickers --text "HI!" --license CC0-1.0 \
  --source "drawn for the sticker-box examples" --note "打招呼、见面问好的时候" \
  --tag emotion=开心 --tag visual=脸红 --define visual=挥手 "举起手左右摆动，打招呼或告别" --json

# The last file is 800x800: `file_problems` says one side must be exactly 512. The box does not
# convert files, so drop the staged copy and leave the file out.
sticker-box stage inbox/too-big.png --box stickers --json
sticker-box remove caf28009ff24 --box stickers --json

# Find them again. Search matches words literally; give several, including synonyms.
sticker-box search 无语 无奈 尴尬 --box stickers --json
sticker-box search --tag emotion=开心 --box stickers --json
