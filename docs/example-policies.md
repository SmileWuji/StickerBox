# Example policies

Starting points beyond the three presets. Create a box from the nearest preset, then replace
rules with `sticker-box policy set <rule> '<json>'`.

## Meme library

Reaction images of any size and format, tagged like stickers (text, feeling, who, what),
because a meme is found the same way a sticker is. Start from `telegram-sticker` and drop the
file rules:

```bash
sticker-box init memes --preset telegram-sticker --language zh-Hans \
  --description "Reaction images of any size, found by their text and the feeling they carry."
sticker-box policy set files '{"formats": null, "all": {"max_bytes": 10485760}}' --box memes
```

Animated memes are fine: agents read them through `sticker-box frames`.

## A gallery with a size cap

```bash
sticker-box init gallery --preset gallery --language zh-Hans
sticker-box policy set limits '{"max_bytes": 524288000}' --box gallery
```

Writes past 500 MB fail with exit 3 until something is removed or `--auto-cleanup` is passed.

## A buffer that keeps a day

```bash
sticker-box init buffer --preset buffer --language zh-Hans
sticker-box policy set retention '{"expire_after_minutes": 1440, "staged_grace_minutes": 60}' --box buffer
sticker-box policy set limits '{"max_bytes": 209715200, "max_items": null}' --box buffer
```

Move keepers into another box with `sticker-box stage --from buffer <ref> --box stickers`, then
commit them there with that box's required tags.

## Stricter sticker metadata

Require an artist field and exactly one series:

```bash
sticker-box policy set fields '{"text": {"required": true, "allow_empty": true}, "note": {"required": true}, "license": {"required": true}, "artist": {"required": true, "description": "Who drew it, as the source names them."}}' --box stickers
sticker-box policy set categories '{"emotion": {"required": true}, "character": {}, "series": {"multiple": false, "required": true}, "visual": {}, "pack": {}}' --box stickers
```

Custom fields are given at commit with `--field artist=...`.
