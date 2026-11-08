#!/usr/bin/env bash
# Points testdata/private at the owner's corpora. Symlinks where the filesystem allows them,
# otherwise absolute paths in testdata/private/sources.txt (NTFS mounts refuse symlinks).
# Usage: scripts/link-private-testdata.sh [dir ...]   (defaults to the owner's three corpora)
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
dest="$root/testdata/private"
mkdir -p "$dest"
if [ "$#" -eq 0 ]; then
  set -- "$root/../GuidedSticker-Project-TestData" "$root/../private/pack-a" "$root/../private/pack-b"
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
