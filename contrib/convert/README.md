# Converting images to sticker specs

sticker-box never converts a file. When `stage` reports `file_problems` (wrong format, size,
duration or frame rate), the file has to be converted first or left out. `sticker.py` is one way
to do that for the `telegram-sticker` preset. It is not part of the package and the tool does not
call it.

It needs Pillow, and for WEBM `vpxenc` and `vpxdec` (Debian and Ubuntu: `apt install vpx-tools`).
No ffmpeg. It came from QQBot, the tool's first user, where every output was checked with
`sticker-box stage` against the strict `telegram-sticker` preset.

## Commands

```
python3 contrib/convert/sticker.py <command> <input> [<output>] [options]
```

| command | does |
|---|---|
| `info <file>` | size, frames, duration, bytes, and whether it meets the static sticker spec |
| `webp <in> <out.webp>` | a static sticker: longer side exactly 512 px, at most 512 KB |
| `webm <in> <out.webm>` | a video sticker: VP9, longer side 512 px, at most 3 s, 30 fps and 256 KB, no audio |
| `gif <in> <out.gif>` | an animation back to GIF, for chat apps that cannot show WEBM |
| `png <in> <out.png>` | a still back to PNG, for apps that cannot show WEBP |

`webm` reads GIF, animated WEBP or PNG, and WEBM (decoded by `vpxdec`). It lowers the quality
step by step until the file fits.

Options:

- `--crop X,Y,W,H` (every command but `info`): crop before converting; pixels, top-left corner,
  then width and height. Run `info` first for the size, and look at the result after.
- `--frame N` (`webp`, `png`): which frame of an animation to keep, from 0.
- `--start S`, `--speed F` (`webm`): an animation longer than 3 s keeps its first 3 s; `--start`
  picks another part, `--speed 1.5` fits 4.5 s into 3.
- `--background COLOUR` (`webm`): the colour transparent areas get (default `white`).

## Example: a sticker cut out of a screenshot

```bash
python3 contrib/convert/sticker.py info screenshot.jpg
python3 contrib/convert/sticker.py webp screenshot.jpg cut.webp --crop 120,300,400,400
sticker-box stage cut.webp --box stickers --json     # file_problems should be empty
```

## Known limits

**No transparency in WEBM, in or out.** A VP9 WEBM keeps transparency as a second stream stored
in Matroska `BlockAdditional` (ID 1, with `AlphaMode 1` on the track). Neither `vpxenc` nor
Pillow writes it, and `vpxdec` does not read it. So `webm` fills transparent areas with
`--background`, and a transparent WEBM given as input (most Telegram video stickers) arrives
opaque, usually black behind the character, whatever `--background` says; converting such a
sticker to GIF keeps that black. Ways to keep alpha:

- ffmpeg with `-c:v libvpx-vp9 -pix_fmt yuva420p`;
- PyAV, which wraps the same encoder;
- encoding the alpha plane as a second stream with `vpxenc` and muxing both by hand.

Static WEBP and PNG keep transparency.

**WEBM input must be 8-bit 4:2:0**, as Telegram's are. A 10-bit or 4:4:4 VP9 file is refused
with a message.

A failed conversion removes the output it started writing, so whatever is at the output path
afterwards is a finished file.

## For an agent

Convert only when `stage` reports `file_problems`, or when a chat app cannot show the format.
After converting, `stage` the output and check `file_problems` is empty before `commit`. The
box's `README.md` says which formats it takes.
