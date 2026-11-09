#!/usr/bin/env bash
# Points testdata/private at the owner's corpora. Symlinks where the filesystem allows them,
# otherwise absolute paths in testdata/private/sources.txt (NTFS mounts refuse symlinks).
# Usage: scripts/link-private-testdata.sh [dir ...]   (defaults to the paths listed one per line in the
# git-ignored testdata/private/sources.default)
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
dest="$root/testdata/private"
mkdir -p "$dest"
if [ "$#" -eq 0 ]; then
  [ -f "$dest/sources.default" ] || { echo "give corpus directories, or list them in $dest/sources.default"; exit 2; }
  mapfile -t defaults < <(grep -v '^\s*$' "$dest/sources.default")
  set -- "${defaults[@]}"
fi
: > "$dest/sources.txt"
for src in "$@"; do
  [ -d "$src" ] || { echo "skip (missing): $src"; continue; }
  abs="$(cd "$src" && pwd)"
  name="$(basename "$abs")"
  if [ -e "$dest/$name" ]; then
    echo "present: $name"
  elif ln -s "$abs" "$dest/$name" 2>/dev/null; then
    echo "linked: $name"
  else
    echo "$abs" >> "$dest/sources.txt"
    echo "listed: $abs"
  fi
done
