#!/usr/bin/env bash
# End-to-end run of every preset through the real CLI, on testdata/generic and, when present,
# a few files from testdata/private. Exits non-zero on the first failure.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
SB="${SB:-sticker-box}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
export STICKER_BOX_JSON=1
generic="$root/testdata/generic"
field() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }
step() { printf '%-60s' "$1"; }
ok() { echo ok; }

step "sticker box: init, stage, refuse, commit"
"$SB" init "$work/stickers" --preset telegram-sticker --language zh-Hans >/dev/null
ref=$("$SB" stage "$generic/sticker-static.webp" --box "$work/stickers" | field 'd["results"][0]["ref"]')
code=0; "$SB" commit "$ref" --box "$work/stickers" >/dev/null || code=$?
[ "$code" = 1 ]
"$SB" commit "$ref" --box "$work/stickers" --license unknown --text "" --note "smoke" --define emotion=测试 "冒烟测试" >/dev/null
ok

step "sticker box: search, show, frames, vocab, check"
[ "$("$SB" search 测试 --box "$work/stickers" | field 'd["results"][0]["ref"]')" = "$ref" ]
"$SB" show "${ref:0:10}" --box "$work/stickers" >/dev/null
vref=$("$SB" stage "$generic/sticker-video.webm" --box "$work/stickers" | field 'd["results"][0]["ref"]')
[ -f "$("$SB" frames "$vref" --box "$work/stickers" | field 'd["sheet"]')" ]
"$SB" vocab review --box "$work/stickers" >/dev/null
"$SB" vocab lock --box "$work/stickers" >/dev/null
[ "$("$SB" check --box "$work/stickers" | field 'd["ok"]')" = True ]
ok

step "gallery: stage, commit, dupes, clean"
"$SB" init "$work/gallery" --preset gallery --language en >/dev/null
for f in "$generic"/*; do
  r=$("$SB" stage "$f" --box "$work/gallery" | field 'd["results"][0]["ref"]')
  "$SB" commit "$r" --box "$work/gallery" --license unknown --tag smoke >/dev/null
done
"$SB" dupes --box "$work/gallery" >/dev/null
"$SB" clean --all --box "$work/gallery" >/dev/null
[ "$("$SB" info --box "$work/gallery" | field 'd["items"]')" = "$(ls "$generic" | wc -l)" ]
ok

step "buffer: limit, auto-cleanup, transfer"
"$SB" init "$work/buffer" --preset buffer --language zh-Hans >/dev/null
"$SB" policy set limits '{"max_items": 1}' --box "$work/buffer" >/dev/null
a=$("$SB" stage "$generic/animated.gif" --box "$work/buffer" | field 'd["results"][0]["ref"]')
"$SB" commit "$a" --box "$work/buffer" --license unknown >/dev/null
code=0; "$SB" stage "$generic/sticker-wide.webp" --box "$work/buffer" >/dev/null || code=$?
[ "$code" = 3 ]
b=$("$SB" stage "$generic/sticker-wide.webp" --auto-cleanup --box "$work/buffer" | field 'd["results"][0]["ref"]')
"$SB" commit "$b" --box "$work/buffer" --license unknown --auto-cleanup >/dev/null
t=$("$SB" stage --from "$work/buffer" "$b" --box "$work/stickers" | field 'd["results"][0]["ref"]')
"$SB" commit "$t" --box "$work/stickers" --text "" --note "转存" --tag emotion=测试 >/dev/null
ok

private="$root/testdata/private"
if [ -d "$private" ] && [ -n "$(find -L "$private" -name '*.webp' -print -quit 2>/dev/null)" ]; then
  step "private corpus: stage and commit five stickers"
  "$SB" vocab unlock --box "$work/stickers" >/dev/null
  n=0
  while IFS= read -r f; do
    out=$("$SB" stage "$f" --box "$work/stickers" || true)
    r=$(echo "$out" | field 'd["results"][0]["ref"] if d["results"][0]["status"] == "staged" and not d["results"][0]["file_problems"] and not d["results"][0]["duplicates"] else ""')
    [ -n "$r" ] || continue
    "$SB" commit "$r" --box "$work/stickers" --license unknown --text "" --note smoke --tag emotion=测试 >/dev/null
    n=$((n + 1)); [ "$n" -lt 5 ] || break
  done < <(find -L "$private" -name '*.webp' | sort | awk 'NR % 37 == 1')
  [ "$n" = 5 ]
  ok
fi
echo "smoke passed"
