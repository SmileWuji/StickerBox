---
name: gallery-maintenance
description: Keep a gallery or buffer box tidy: review duplicates and crops, stay under its limits, clean up staged and expired files, and audit it. Use for a scheduled maintenance session or when a box reports a limit.
---

# Gallery maintenance

Read the box's `README.md` for its limits and expiry first.

## Duplicates, crops and rotations

`sticker-box dupes --json` lists groups of related images. Each group has a suggested `keeper`
(the largest, then the oldest), its `members` with paths and sizes, and `links` saying how
they relate:

- `near_duplicate` / `duplicate`: the same picture, re-saved or resized
- `crop_of` / `contains`: one shows part of the other (for example, a screenshot that contains
  the picture)
- `rotation`: the same picture turned
- `frame_of` / `has_frame` / `shares_frames`: a still taken from an animation
- `overlap`: they share part of a picture; often a false alarm, look before acting

Look at the members before removing anything. A zoomed crop of a meme is often a different joke
worth keeping. Remove only true copies: `sticker-box remove <ref> --json`. Links are evidence,
not orders; about one in twenty may be a false alarm.

## Limits and cleanup

- `sticker-box info --json` shows usage against the limits.
- `sticker-box clean --json` removes staged files older than the grace period and expired
  images. It never touches images that have not expired.
- A write that would pass a limit fails with exit 3. Decide what goes: remove some images, or
  retry with `--auto-cleanup`, which removes expired images and then the oldest ones and lists
  every one it removed.

## Audit

`sticker-box check --json` compares every image with the current rules and the folder with the
index. It changes nothing. Fix item problems with `edit`; orphan files and broken staged files
are safe to delete with `clean --all`; `reindex` rebuilds keyframes, features and links after a
tool upgrade (slow on big boxes).
