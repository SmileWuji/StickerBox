#!/usr/bin/env bash
# Contact sheet for checking who a character is: the picture in question, then one row per candidate
# with a few top-scored solo all-ages pictures from safebooru.org. Needs curl, jq and ImageMagick.
# Usage: compare.sh <picture> <safebooru_tag> [<safebooru_tag> ...]   (sheet written to $COMPARE_OUT, default ./character-id)
set -u
PER="${CID_PER:-3}"
if [ $# -lt 2 ] || [ ! -f "$1" ]; then
    echo "usage: compare.sh <picture> <safebooru_tag> [<safebooru_tag> ...], tags as safebooru writes them, e.g. komeiji_koishi" >&2
    exit 2
fi
query=$1; shift
out_dir="${COMPARE_OUT:-$PWD/character-id}"
mkdir -p "$out_dir"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
api='https://safebooru.org/index.php?page=dapi&s=post&q=index&json=1'

convert "$query[0]" -resize 400x400 -background white -flatten "$work/0-query.png" || { echo "cannot open $query" >&2; exit 1; }
convert "$work/0-query.png" -gravity north -background '#ffe9a8' -splice 0x28 -font DejaVu-Sans -pointsize 18 -annotate +0+4 "0. ?" "$work/0-query.png"
rows=("$work/0-query.png")

# Character tags containing any word of the name, most posts first, so a typo or a swapped name
# order (marisa_kirisame) still leads to the right tag.
similar() {
    local part
    for part in $(tr '_()' '\n\n\n' <<<"$1" | awk 'length >= 3'); do
        curl -s -m 20 "https://safebooru.org/index.php?page=dapi&s=tag&q=index&limit=1000&name_pattern=%25$(printf %s "$part" | jq -sRr @uri)%25" \
            | grep -o 'type="4" count="[0-9]*" name="[^"]*"' | sed -E 's/.*count="([0-9]+)" name="([^"]*)"/\1 \2/'
    done | awk -v t="$1" '$2 != t && !seen[$2]++' | sort -rn | head -6 \
        | awk '{ out = out (NR > 1 ? ", " : " Similar character tags: ") $2 " (" $1 ")" } END { printf "%s", out }' | sed "s/&#039;/'/g"
}

i=0
for tag in "$@"; do
    i=$((i + 1))
    json=$(curl -s -m 20 "$api&limit=$PER&tags=$(printf %s "$tag" | jq -sRr @uri)+solo+-multiple_girls+-comic+rating:general+sort:score")
    count=$(jq 'length' <<<"$json" 2>/dev/null || echo 0)
    if [ "${count:-0}" -eq 0 ]; then
        echo "$tag: nothing on safebooru.$(similar "$tag")"
        continue
    fi
    tiles=()
    j=0
    while read -r url; do
        j=$((j + 1))
        f="$work/$i-$j"
        curl -s -m 30 -o "$f" "$url" && convert "$f[0]" -resize 400x400 -background white -flatten "$f.png" 2>/dev/null && tiles+=("$f.png")
    done < <(jq -r '.[] | .sample_url // .file_url' <<<"$json")
    [ ${#tiles[@]} -eq 0 ] && { echo "$tag: reference pictures failed to download"; continue; }
    convert "${tiles[@]}" -background white -gravity center -extent 400x400 +append \
        -gravity north -background '#d8ecff' -splice 0x28 -font DejaVu-Sans -pointsize 18 -annotate +0+4 "$i. $tag" "$work/row-$i.png"
    rows+=("$work/row-$i.png")
    echo "$i. $tag: ${#tiles[@]} reference pictures, https://safebooru.org/index.php?page=post&s=list&tags=$tag"
done

[ ${#rows[@]} -le 1 ] && { echo "no candidate had reference pictures; no sheet made" >&2; exit 1; }
sheet="$out_dir/$(date +%Y%m%d-%H%M%S).png"
convert "${rows[@]}" -background white -gravity west -append "$sheet"
echo
echo "sheet: $sheet"
echo "Row 0 is the picture in question; each later row is one candidate's reference pictures."
