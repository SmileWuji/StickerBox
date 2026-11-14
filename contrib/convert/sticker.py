"""Convert pictures to Telegram sticker specs, and back to formats every chat app shows.

Telegram (https://core.telegram.org/stickers): static WEBP/PNG with one side exactly 512 px and the other at most
512 px; video WEBM VP9, one side 512 px, at most 3 s, 30 fps and 256 KB, no audio. The 512 KB cap on static
stickers is sticker-box's own (the `telegram-sticker` preset).

  sticker.py info FILE
  sticker.py webp IN OUT [--crop X,Y,W,H] [--frame N]
  sticker.py webm IN OUT [--crop X,Y,W,H] [--start S] [--speed F] [--background COLOR]
  sticker.py gif  IN OUT [--crop X,Y,W,H]
  sticker.py png  IN OUT [--crop X,Y,W,H] [--frame N]

Animated input: GIF, animated WEBP or PNG, or WEBM (VP8/VP9, decoded with vpxdec). Needs Pillow,
and vpxenc and vpxdec (Debian package vpx-tools) for WEBM; no ffmpeg. See README.md.
"""
import argparse
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageSequence

SIDE = 512
STATIC_MAX = 512 * 1024
VIDEO_MAX = 256 * 1024
VIDEO_SECONDS = 3.0
VIDEO_FPS = 30
Y4M_420 = {"420jpeg", "420mpeg2", "420paldv", "420"}

output_path, output_before = None, None


def fail(message):
    """A failed run leaves no output it wrote, so a half-made file is never mistaken for a result."""
    if output_path and os.path.exists(output_path):
        st = os.stat(output_path)
        if output_before is None or (st.st_mtime_ns, st.st_size) != output_before:
            os.remove(output_path)
    print(f"failed: {message}", file=sys.stderr)
    sys.exit(1)


def crop_box(text):
    try:
        x, y, w, h = (int(v) for v in text.split(","))
    except ValueError:
        fail("--crop takes X,Y,W,H in pixels: the top-left corner, then width and height")
    if w <= 0 or h <= 0:
        fail("--crop needs a width and height above 0")
    return (x, y, x + w, y + h)


def read_y4m(path):
    with open(path, "rb") as f:
        header = f.readline().decode().split()
        width = height = None
        fps = 30.0
        colourspace = "420jpeg"
        for token in header[1:]:
            if token[0] == "W":
                width = int(token[1:])
            elif token[0] == "H":
                height = int(token[1:])
            elif token[0] == "F":
                num, den = token[1:].split(":")
                fps = int(num) / int(den)
            elif token[0] == "C":
                colourspace = token[1:]
        if colourspace not in Y4M_420:
            fail(f"only 8-bit 4:2:0 WEBM can be read; this one decodes as {colourspace}")
        y_size = width * height
        c_size = ((width + 1) // 2) * ((height + 1) // 2)
        frames = []
        while f.readline():
            y = Image.frombytes("L", (width, height), f.read(y_size))
            u = Image.frombytes("L", ((width + 1) // 2, (height + 1) // 2), f.read(c_size)).resize((width, height))
            v = Image.frombytes("L", ((width + 1) // 2, (height + 1) // 2), f.read(c_size)).resize((width, height))
            y = y.point(lambda p: max(0, min(255, round((p - 16) * 255 / 219))))
            u = u.point(lambda p: max(0, min(255, round((p - 128) * 255 / 224 + 128))))
            v = v.point(lambda p: max(0, min(255, round((p - 128) * 255 / 224 + 128))))
            frames.append(Image.merge("YCbCr", (y, u, v)).convert("RGBA"))
    return frames, 1000.0 / fps


def load(path):
    """Frames as RGBA images and each frame's duration in ms."""
    with open(path, "rb") as f:
        magic = f.read(4)
    if magic == b"\x1a\x45\xdf\xa3":
        with tempfile.TemporaryDirectory() as tmp:
            raw = os.path.join(tmp, "frames.y4m")
            r = subprocess.run(["vpxdec", "-o", raw, os.path.abspath(path)], capture_output=True, text=True)
            if r.returncode != 0:
                fail(f"vpxdec cannot decode this WEBM: {r.stderr.strip()[:200]}")
            frames, ms = read_y4m(raw)
        return frames, [ms] * len(frames)
    image = Image.open(path)
    frames, durations = [], []
    for frame in ImageSequence.Iterator(image):
        frames.append(frame.convert("RGBA"))
        durations.append(float(frame.info.get("duration") or image.info.get("duration") or 100))
    return frames, durations


def fit(frame, box):
    if box:
        frame = frame.crop(box)
    w, h = frame.size
    scale = SIDE / max(w, h)
    size = (max(1, round(w * scale)), max(1, round(h * scale)))
    if w >= h:
        size = (SIDE, size[1])
    else:
        size = (size[0], SIDE)
    return frame.resize(size, Image.LANCZOS)


def save_static(frame, out, fmt):
    if fmt == "png":
        frame.save(out, "PNG", optimize=True)
        if os.path.getsize(out) <= STATIC_MAX:
            return f"PNG {frame.size[0]}x{frame.size[1]}"
        fail(f"the PNG is {os.path.getsize(out) // 1024} KB, over 512 KB; use webp instead")
    for quality in (90, 80, 70, 60, 50, 40, 30):
        frame.save(out, "WEBP", quality=quality, method=6)
        if os.path.getsize(out) <= STATIC_MAX:
            return f"WEBP {frame.size[0]}x{frame.size[1]}, quality {quality}"
    fail("still over 512 KB at quality 30")


def timeline(frames, durations, start_ms, speed, max_ms, fps):
    """Resample to a constant frame rate: the frame shown at each tick."""
    ends, t = [], 0.0
    for d in durations:
        t += max(d, 10) / speed
        ends.append(t)
    total = ends[-1]
    start = start_ms / speed
    if start >= total:
        fail(f"--start is past the end of the animation ({total / 1000:.2f} s)")
    length = min(total - start, max_ms)
    out, i = [], 0
    for n in range(max(1, round(length * fps / 1000))):
        at = start + n * 1000 / fps
        while i < len(ends) - 1 and ends[i] <= at:
            i += 1
        out.append(frames[i])
    return out, total


def write_y4m(frames, path, fps):
    w, h = frames[0].size
    with open(path, "wb") as f:
        f.write(f"YUV4MPEG2 W{w} H{h} F{fps}:1 Ip A1:1 C420jpeg\n".encode())
        for frame in frames:
            y, u, v = frame.convert("YCbCr").split()
            y = y.point(lambda p: round(16 + p * 219 / 255))
            u = u.point(lambda p: round(128 + (p - 128) * 224 / 255)).resize(((w + 1) // 2, (h + 1) // 2), Image.BOX)
            v = v.point(lambda p: round(128 + (p - 128) * 224 / 255)).resize(((w + 1) // 2, (h + 1) // 2), Image.BOX)
            f.write(b"FRAME\n" + y.tobytes() + u.tobytes() + v.tobytes())


def to_webm(args):
    frames, durations = load(args.input)
    box = crop_box(args.crop) if args.crop else None
    background = Image.new("RGBA", (1, 1), args.background).getpixel((0, 0))
    fps = min(VIDEO_FPS, max(1, round(1000 / (sum(durations) / len(durations)))))
    picked, total = timeline(frames, durations, args.start * 1000, args.speed, VIDEO_SECONDS * 1000, fps)
    sized = []
    for frame in picked:
        frame = fit(frame, box)
        if frame.size[0] % 2 or frame.size[1] % 2:
            frame = frame.resize((frame.size[0] - frame.size[0] % 2, frame.size[1] - frame.size[1] % 2), Image.LANCZOS)
        flat = Image.new("RGBA", frame.size, background)
        flat.alpha_composite(frame)
        sized.append(flat.convert("RGB"))
    with tempfile.TemporaryDirectory() as tmp:
        raw = os.path.join(tmp, "in.y4m")
        write_y4m(sized, raw, fps)
        for cq in (24, 32, 40, 48, 56, 63):
            r = subprocess.run(["vpxenc", "--quiet", "--codec=vp9", "--good", "--cpu-used=2", "--passes=1",
                                "--end-usage=q", f"--cq-level={cq}", "--auto-alt-ref=0", "-o", args.output, raw],
                               capture_output=True, text=True)
            if r.returncode != 0:
                fail(f"vpxenc failed: {r.stderr.strip()[:200]}")
            if os.path.getsize(args.output) <= VIDEO_MAX:
                break
        else:
            fail("still over 256 KB at the lowest quality; --crop to the subject, or take a shorter part with --start")
    note = f"; the input is {total / 1000:.2f} s, only {len(sized) / fps:.2f} s taken" if total / 1000 - args.start / args.speed > VIDEO_SECONDS + 0.01 else ""
    print(f"WEBM VP9 {sized[0].size[0]}x{sized[0].size[1]}, {fps} fps, {len(sized)} frames, "
          f"{os.path.getsize(args.output) // 1024} KB, cq {cq}{note}. Transparent areas filled with {args.background}.")


def to_gif(args):
    frames, durations = load(args.input)
    box = crop_box(args.crop) if args.crop else None
    out = []
    for frame in frames:
        if box:
            frame = frame.crop(box)
        out.append(frame)
    if len(out) == 1:
        out[0].save(args.output, "GIF")
    else:
        out[0].save(args.output, "GIF", save_all=True, append_images=out[1:], loop=0, disposal=2,
                    duration=[max(20, round(d)) for d in durations], optimize=True)
    print(f"GIF {out[0].size[0]}x{out[0].size[1]}, {len(out)} frames, {os.path.getsize(args.output) // 1024} KB")


def to_static(args, fmt):
    frames, _ = load(args.input)
    if not 0 <= args.frame < len(frames):
        fail(f"--frame must be between 0 and {len(frames) - 1}")
    if len(frames) > 1:
        print(f"note: an animation of {len(frames)} frames; only frame {args.frame} was kept. Use webm to keep the animation.")
    print(save_static(fit(frames[args.frame], crop_box(args.crop) if args.crop else None), args.output, fmt))


def info(args):
    frames, durations = load(args.input)
    w, h = frames[0].size
    size = os.path.getsize(args.input)
    total = sum(durations)
    print(f"{w}x{h}, {len(frames)} frames, {size // 1024} KB" + (f", {total / 1000:.2f} s" if len(frames) > 1 else ""))
    side_ok = max(w, h) == SIDE
    if len(frames) == 1:
        ok = side_ok and size <= STATIC_MAX and args.input.lower().endswith((".webp", ".png"))
        print("meets the static sticker spec" if ok else "does not meet the static sticker spec: convert with webp (or png)")
    else:
        print("animated: a telegram-sticker box takes WEBM, convert with webm; for an app that cannot show WEBM, convert with gif")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("info")
    p.add_argument("input")
    for name in ("webp", "png", "webm", "gif"):
        p = sub.add_parser(name)
        p.add_argument("input")
        p.add_argument("output")
        p.add_argument("--crop")
        if name in ("webp", "png"):
            p.add_argument("--frame", type=int, default=0)
        if name == "webm":
            p.add_argument("--start", type=float, default=0.0, help="second to start from")
            p.add_argument("--speed", type=float, default=1.0, help="speed-up factor, e.g. 1.5 fits a 4.5 s animation into 3 s")
            p.add_argument("--background", default="white", help="colour for transparent areas (VP9 alpha is not written; see README.md)")
    args = parser.parse_args()
    global output_path, output_before
    if getattr(args, "output", None):
        output_path = args.output
        if os.path.exists(output_path):
            st = os.stat(output_path)
            output_before = (st.st_mtime_ns, st.st_size)
    if not os.path.isfile(args.input):
        fail(f"{args.input} is not a file")
    if getattr(args, "speed", 1.0) <= 0:
        fail("--speed must be above 0")
    if args.command == "info":
        info(args)
    elif args.command == "webm":
        to_webm(args)
    elif args.command == "gif":
        to_gif(args)
    else:
        to_static(args, args.command)


if __name__ == "__main__":
    main()
