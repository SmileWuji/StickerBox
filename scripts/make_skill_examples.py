"""Builds skills/sticker-box/examples/<task>/: draws the images (owned by this project), builds
the boxes in before/ under a fixed clock, runs commands.sh on a copy and writes after/ and
transcript.md. commands.sh is written by hand and is the source of each example.

    python3 scripts/make_skill_examples.py            # rebuild every example
    python3 scripts/make_skill_examples.py --only add-stickers
"""

import argparse
import contextlib
import io
import json
import math
import random
import re
import shlex
import shutil
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import numpy as np  # noqa: E402
from PIL import Image, ImageDraw, ImageFilter, ImageFont  # noqa: E402

import factory  # noqa: E402
from sticker_box import clock  # noqa: E402
from sticker_box.cli import main  # noqa: E402

EXAMPLES = ROOT / "skills" / "sticker-box" / "examples"
BUILD_AT = datetime(2026, 1, 15, 9, 30, tzinfo=timezone.utc)
RUN_AT = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
LATER = re.compile(r"^# \.\.\. (\d+) minutes later \.\.\.$")


def font(size: int):
    return ImageFont.load_default(size=size)


def caption(d: ImageDraw.ImageDraw, text: str, xy: tuple[int, int], size: int = 64) -> None:
    d.text(xy, text, font=font(size), fill=(255, 255, 255, 255), stroke_width=6, stroke_fill=(30, 30, 30, 255), anchor="mm")


def face(mood: str, color, center=(256, 220), r=160, text: str | None = None, text_at=(256, 450), extras=()) -> Image.Image:
    im = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx, cy = center
    if "body" in extras:
        d.rounded_rectangle([cx - r * 0.8, cy + r * 0.7, cx + r * 0.8, min(505, cy + r * 1.9)], radius=40, fill=color, outline=(40, 40, 40, 255), width=8)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color, outline=(40, 40, 40, 255), width=8)
    ex, ey, k = r * 0.38, cy - r * 0.15, r * 0.12
    for sx in (cx - ex, cx + ex):
        if mood in ("happy", "laugh"):
            d.arc([sx - k * 1.4, ey - k, sx + k * 1.4, ey + k * 1.6], 200, 340, fill=(30, 30, 30, 255), width=9)
        elif mood == "flat":
            d.line([sx - k * 1.3, ey, sx + k * 1.3, ey], fill=(30, 30, 30, 255), width=10)
        elif mood == "angry":
            d.ellipse([sx - k * 0.7, ey - k * 0.4, sx + k * 0.7, ey + k], fill=(30, 30, 30, 255))
            tilt = 1 if sx < cx else -1
            d.line([sx - k * 1.6, ey - k * 2 - tilt * k * 0.8, sx + k * 1.6, ey - k * 2 + tilt * k * 0.8], fill=(30, 30, 30, 255), width=12)
        else:
            d.ellipse([sx - k * 0.8, ey - k * 0.8, sx + k * 0.8, ey + k * 0.8], fill=(30, 30, 30, 255))
    my = cy + r * 0.38
    if mood == "laugh":
        d.chord([cx - r * 0.45, my - r * 0.25, cx + r * 0.45, my + r * 0.35], 0, 180, fill=(120, 20, 30, 255), outline=(30, 30, 30, 255), width=8)
    elif mood == "happy":
        d.arc([cx - r * 0.4, my - r * 0.3, cx + r * 0.4, my + r * 0.2], 20, 160, fill=(30, 30, 30, 255), width=10)
    elif mood in ("sad", "cry"):
        d.arc([cx - r * 0.35, my, cx + r * 0.35, my + r * 0.4], 200, 340, fill=(30, 30, 30, 255), width=10)
    elif mood == "angry":
        d.line([cx - r * 0.35, my + r * 0.1, cx + r * 0.35, my + r * 0.1], fill=(30, 30, 30, 255), width=12)
    else:
        d.line([cx - r * 0.25, my, cx + r * 0.25, my], fill=(30, 30, 30, 255), width=10)
    if "sweat" in extras:
        sx, sy = cx + r * 0.85, cy - r * 0.75
        d.polygon([(sx, sy - 45), (sx - 22, sy + 10), (sx + 22, sy + 10)], fill=(110, 180, 255, 255))
        d.ellipse([sx - 22, sy - 12, sx + 22, sy + 32], fill=(110, 180, 255, 255))
    if "tears" in extras or mood == "cry":
        for sx in (cx - ex, cx + ex):
            d.rectangle([sx - 10, ey + k, sx + 10, cy + r * 0.9], fill=(110, 180, 255, 255))
    if "blush" in extras:
        for sx in (cx - r * 0.6, cx + r * 0.6):
            d.ellipse([sx - 30, my - 40, sx + 30, my - 10], fill=(255, 140, 160, 255))
    if "anger" in extras:
        ax, ay = cx + r * 0.75, cy - r * 0.85
        for a in (45, 135):
            t = math.radians(a)
            d.line([ax - 40 * math.cos(t), ay - 40 * math.sin(t), ax + 40 * math.cos(t), ay + 40 * math.sin(t)], fill=(230, 40, 40, 255), width=14)
    if "hat" in extras:
        d.polygon([(cx - r * 0.7, cy - r * 0.75), (cx + r * 0.7, cy - r * 0.75), (cx, cy - r * 1.6)], fill=(250, 210, 60, 255), outline=(40, 40, 40, 255))
    if "question" in extras:
        d.text((cx - r * 1.05, cy - r * 0.9), "?", font=font(130), fill=(80, 80, 230, 255), stroke_width=5, stroke_fill=(255, 255, 255, 255), anchor="mm")
    if text:
        caption(d, text, text_at)
    return im


def save_webp(im: Image.Image, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, "WEBP", quality=90, method=6)
    return path


def on_white(im: Image.Image) -> Image.Image:
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    return Image.alpha_composite(bg, im).convert("RGB")


def wave_frames(n: int = 24) -> list[np.ndarray]:
    frames = []
    for i in range(n):
        im = face("happy", (120, 210, 140, 255), center=(230, 250), r=150, extras=("blush",))
        d = ImageDraw.Draw(im)
        a = math.sin(i / n * 4 * math.pi)
        hx, hy = 420 + 40 * a, 170 - 20 * abs(a)
        d.line([(340, 300), (hx, hy)], fill=(40, 40, 40, 255), width=16)
        d.ellipse([hx - 40, hy - 40, hx + 40, hy + 40], fill=(120, 210, 140, 255), outline=(40, 40, 40, 255), width=8)
        caption(d, "HI!", (256, 470))
        frames.append(np.array(on_white(im).convert("RGBA")))
    return frames


def landscape(seed: int, size=(1200, 900)) -> Image.Image:
    rnd = random.Random(seed)
    w, h = size
    im = Image.new("RGB", size)
    d = ImageDraw.Draw(im)
    top, bottom = (rnd.randint(40, 90), rnd.randint(90, 140), rnd.randint(170, 230)), (250, 200, 160)
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
    d.ellipse([w * 0.7, h * 0.12, w * 0.7 + 120, h * 0.12 + 120], fill=(255, 230, 120))
    for _ in range(140):
        x, y = rnd.randrange(w), rnd.randrange(int(h * 0.45))
        s = rnd.randint(2, 6)
        d.ellipse([x - s, y - s, x + s, y + s], fill=(255, 255, 255))
    for layer in range(3):
        pts = [(0, h)]
        for x in range(0, w + 60, 60):
            pts.append((x, int(h * (0.45 + 0.12 * layer) + rnd.randint(-70, 70))))
        pts.append((w, h))
        shade = 60 + 40 * layer
        d.polygon(pts, fill=(shade // 2, shade, shade // 2 + 20))
    for _ in range(90):
        x, y = rnd.randrange(w), rnd.randint(int(h * 0.7), h)
        s = rnd.randint(14, 40)
        d.polygon([(x, y - 2 * s), (x - s, y), (x + s, y)], fill=(20, rnd.randint(80, 140), 40), outline=(10, 40, 10))
    for _ in range(25):
        x, y = rnd.randrange(w), rnd.randint(int(h * 0.55), h)
        d.rectangle([x, y, x + rnd.randint(20, 50), y + rnd.randint(20, 40)], fill=(rnd.randint(150, 240), rnd.randint(60, 120), 50), outline=(40, 20, 10), width=3)
    for _ in range(600):
        x, y = rnd.randrange(w), rnd.randint(int(h * 0.5), h)
        s = rnd.randint(3, 9)
        colour = rnd.choice([(250, 240, 90), (240, 120, 160), (255, 255, 255), (150, 90, 200), (250, 150, 40)])
        d.ellipse([x - s, y - s, x + s, y + s], fill=colour, outline=(30, 30, 30))
    return im


def chat_screenshot(inner: Image.Image | None, lines: list[str], seed: int) -> Image.Image:
    rnd = random.Random(seed)
    im = Image.new("RGB", (1080, 1920), (236, 236, 240))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 1080, 160], fill=(40, 44, 52))
    d.text((540, 95), "Group chat", font=font(48), fill=(255, 255, 255), anchor="mm")
    y = 220
    for i, line in enumerate(lines):
        left = i % 2 == 0
        width = 60 + 26 * len(line)
        x0 = 40 if left else 1040 - width
        d.rounded_rectangle([x0, y, x0 + width, y + 100], radius=30, fill=(255, 255, 255) if left else (150, 220, 120))
        d.text((x0 + 30, y + 50), line, font=font(44), fill=(20, 20, 20), anchor="lm")
        y += 140 + rnd.randint(0, 20)
    if inner is not None:
        pic = inner.resize((900, 675))
        im.paste(pic, (90, y + 20))
    return im


def junk_photo() -> Image.Image:
    im = Image.new("RGB", (1024, 768))
    d = ImageDraw.Draw(im)
    for y in range(768):
        d.line([(0, y), (1024, y)], fill=(70 + y // 12, 65 + y // 14, 60 + y // 16))
    d.ellipse([300, 200, 700, 600], fill=(40, 38, 36))
    return im.filter(ImageFilter.GaussianBlur(40))


def write(im: Image.Image, path: Path, **kw) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path, **kw)
    return path


class Clock:
    def __init__(self, start: datetime):
        self.t = start

    def now(self) -> datetime:
        return self.t

    def tick(self, minutes: int = 1) -> None:
        self.t += timedelta(minutes=minutes)


def run(argv: list[str], cwd: Path, fake: Clock, stdin: str | None = None) -> tuple[int, str]:
    out = io.StringIO()
    with mock.patch.object(clock, "now", fake.now), contextlib.chdir(cwd), \
            mock.patch.object(sys, "stdin", io.StringIO(stdin or "")), \
            contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = main(argv)
    fake.tick()
    return code, out.getvalue()


def sb(cwd: Path, fake: Clock, *argv: str, stdin: str | None = None) -> dict:
    code, out = run(["--json", *argv], cwd, fake, stdin)
    if code != 0:
        raise SystemExit(f"setup command failed ({code}): {' '.join(argv)}\n{out}")
    return json.loads(out) if out.strip() else {}


def add(cwd: Path, fake: Clock, box: str, path: str, *commit_args: str) -> str:
    (staged,) = sb(cwd, fake, "stage", path, "--box", box)["results"]
    sb(cwd, fake, "commit", staged["ref"], "--box", box, *commit_args)
    return staged["ref"]


STICKER = ("--license", "CC0-1.0", "--source", "drawn for the sticker-box examples")


def build_add_stickers(before: Path, fake: Clock) -> None:
    inbox = before / "inbox"
    save_webp(face("laugh", (255, 205, 80, 255), text="OK!", extras=("blush",)), inbox / "ok.webp")
    save_webp(face("flat", (170, 200, 255, 255), center=(220, 230), r=170, text="...", text_at=(256, 455), extras=("sweat",)), inbox / "speechless.webp")
    factory.write_webm(inbox / "wave.webm", wave_frames(), fps=12)
    write(on_white(face("happy", (255, 160, 200, 255), text="BIG")).resize((800, 800)), inbox / "too-big.png")
    sb(before, fake, "init", "stickers", "--preset", "telegram-sticker", "--language", "zh-Hans",
       "--description", "聊天用的表情包")


def build_buffer_triage(before: Path, fake: Clock) -> None:
    src = before / "incoming"
    save_webp(face("laugh", (255, 150, 90, 255), center=(256, 240), r=175, text="LOL", text_at=(256, 470), extras=("tears",)), src / "lol.webp")
    write(chat_screenshot(landscape(21), ["see you at the lake", "the view is amazing", "photo below"], 3), src / "trip-chat.png")
    write(junk_photo(), src / "pocket-shot.jpg", quality=85)
    sb(before, fake, "init", "buffer", "--preset", "buffer", "--language", "en", "--description", "images from the chat, kept for an hour")
    sb(before, fake, "init", "stickers", "--preset", "telegram-sticker", "--language", "zh-Hans", "--description", "聊天用的表情包")
    sb(before, fake, "init", "gallery", "--preset", "gallery", "--language", "en", "--description", "pictures worth finding again")
    sb(before, fake, "tag", "new", "emotion", "开心", "--means", "高兴、愉快", "--box", "stickers")
    for name, note in (("lol.webp", "posted after a joke"), ("trip-chat.png", "shared by a friend"), ("pocket-shot.jpg", "sent by accident")):
        add(before, fake, "buffer", f"incoming/{name}", "--license", "unknown", "--note", note)
    shutil.rmtree(src)


def build_gallery(before: Path, fake: Clock) -> None:
    src = before / "incoming"
    photo = landscape(7)
    write(photo, src / "lake.jpg", quality=92)
    write(photo, src / "lake-resaved.jpg", quality=40)
    write(chat_screenshot(photo, ["look where we are", "wow"], 5), src / "lake-in-chat.png")
    write(photo.crop((150, 300, 1050, 900)).resize((1200, 800)), src / "lake-zoomed.jpg", quality=90)
    write(landscape(99), src / "hills.jpg", quality=92)
    sb(before, fake, "init", "gallery", "--preset", "gallery", "--language", "en", "--description", "pictures worth finding again")
    for name, tag in (("lake.jpg", "lake"), ("hills.jpg", "hills"), ("lake-resaved.jpg", "lake"), ("lake-in-chat.png", "screenshot"), ("lake-zoomed.jpg", "lake")):
        add(before, fake, "gallery", f"incoming/{name}", "--license", "unknown", "--tag", tag)
    shutil.rmtree(src)


VOCAB_STICKERS = [
    ("flat", (170, 200, 255, 255), ("sweat",), "...", "emotion=无语", "无奈到说不出话"),
    ("flat", (200, 170, 255, 255), ("sweat", "body"), None, "emotion=无语了", "说不出话"),
    ("laugh", (255, 205, 80, 255), ("blush",), "YAY", "emotion=开心", "高兴、愉快"),
    ("happy", (140, 230, 160, 255), ("hat",), None, "emotion=高兴", "心情好"),
    ("angry", (255, 120, 100, 255), ("anger",), "GRR", "emotion=生气", "不满、发火"),
    ("cry", (150, 190, 230, 255), (), None, "emotion=哭", "流泪、难过"),
    ("cry", (120, 160, 220, 255), ("body",), "WAH", "emotion=大哭", "哭得很厉害"),
]


def build_vocab(before: Path, fake: Clock) -> None:
    src = before / "incoming"
    sb(before, fake, "init", "stickers", "--preset", "telegram-sticker", "--language", "zh-Hans", "--description", "聊天用的表情包")
    sb(before, fake, "tag", "new", "emotion", "困惑", "--means", "不明白、摸不着头脑", "--box", "stickers")
    for i, (mood, color, extras, text, tag, meaning) in enumerate(VOCAB_STICKERS):
        center = (200 + 25 * (i % 5), 190 + 15 * (i % 3))
        path = save_webp(face(mood, color, center=center, r=140 + 8 * i, text=text, text_at=(300, 455), extras=extras), src / f"s{i}.webp")
        args = ["--text", text or "", "--note", "示例", *STICKER]
        args += ["--define", "visual=圆脸", "圆圆的脸"] if i == 0 else ["--tag", "visual=圆脸"]
        args += ["--define", tag, meaning] if meaning else ["--tag", tag]
        add(before, fake, "stickers", str(path.relative_to(before)), *args)
    shutil.rmtree(src)


def build_add_category(before: Path, fake: Clock) -> None:
    src = before / "incoming"
    sb(before, fake, "init", "stickers", "--preset", "telegram-sticker", "--language", "zh-Hans", "--description", "游戏角色表情包")
    robot = face("happy", (190, 190, 200, 255), center=(256, 230), r=165, text="BEEP", extras=("hat",))
    cat = face("laugh", (250, 180, 110, 255), center=(240, 240), r=170, text="NYA", extras=("blush", "body"))
    for name, im, text, meaning in (("robot.webp", robot, "BEEP", "机器人"), ("cat.webp", cat, "NYA", "猫")):
        path = save_webp(im, src / name)
        tags = ["--define", "emotion=开心", "高兴、愉快"] if name == "robot.webp" else ["--tag", "emotion=开心", "--define", "visual=猫耳", "头上有猫耳朵"]
        add(before, fake, "stickers", str(path.relative_to(before)), "--text", text, "--note", "打招呼的时候", *STICKER, *tags)
    shutil.rmtree(src)


BUILDERS = {
    "add-stickers": build_add_stickers,
    "buffer-triage": build_buffer_triage,
    "gallery-maintenance": build_gallery,
    "vocab-cleanup": build_vocab,
    "add-category": build_add_category,
}


def steps(script: str) -> list[dict]:
    """commands.sh as steps: comment lines are the narration, `sticker-box` lines (with `\\`
    continuations and an optional heredoc on standard input) are commands."""
    lines = script.splitlines()
    out, prose, i = [], [], 0
    while i < len(lines):
        line = lines[i]
        later = LATER.match(line.strip())
        if later:
            out.append({"prose": prose, "later": int(later.group(1))})
            prose = []
        elif line.startswith("#!"):
            pass
        elif line.startswith("#"):
            prose.append(line[1:].strip())
        elif line.startswith("sticker-box "):
            text = line
            while text.endswith("\\"):
                i += 1
                text = text[:-1].rstrip() + " " + lines[i].strip()
            stdin = None
            heredoc = re.search(r"\s*<<'EOF'$", text)
            if heredoc:
                text = text[:heredoc.start()]
                body = []
                i += 1
                while lines[i] != "EOF":
                    body.append(lines[i])
                    i += 1
                stdin = "\n".join(body) + "\n"
            out.append({"prose": prose, "command": text, "stdin": stdin})
            prose = []
        elif line.strip() and not line.startswith(("set -", "cd ")):
            raise SystemExit(f"commands.sh: unsupported line: {line}")
        i += 1
    if prose:
        out.append({"prose": prose})
    return out


def trim(value, depth: int = 0):
    if isinstance(value, list):
        if len(value) > 4 and depth > 0:
            return [trim(v, depth + 1) for v in value[:3]] + [f"... {len(value) - 3} more"]
        return [trim(v, depth + 1) for v in value]
    if isinstance(value, dict):
        return {k: trim(v, depth + 1) for k, v in value.items()}
    return value


def execute(example: Path, work: Path) -> list[dict]:
    fake = Clock(RUN_AT)
    results = []
    for step in steps((example / "commands.sh").read_text(encoding="utf-8")):
        if "later" in step:
            fake.tick(step["later"])
        if "command" in step:
            code, out = run(shlex.split(step["command"])[1:], work, fake, step["stdin"])
            text = out.replace(str(work.resolve()) + "/", "").replace(str(work.resolve()), ".")
            step = {**step, "exit": code, "output": text}
        results.append(step)
    return results


def prose_markdown(lines: list[str]) -> list[str]:
    """Comment lines as Markdown: an empty comment ends a paragraph, `- ` starts a list item,
    anything else continues the current paragraph or item."""
    out: list[str] = []
    for line in lines:
        if not line:
            if out and out[-1]:
                out.append("")
        elif line.startswith("- ") or not out or not out[-1]:
            out.append(line)
        else:
            out[-1] += " " + line.strip()
    while out and not out[-1]:
        out.pop()
    return out


def transcript(name: str, results: list[dict]) -> str:
    out = [f"# Example: {name}", "", "Generated by `scripts/make_skill_examples.py` from `commands.sh`, run inside a copy of",
           "`before/`. Paths are relative to that folder; long lists are cut to three entries.", ""]
    for step in results:
        if step["prose"]:
            out += prose_markdown(step["prose"]) + [""]
        if "later" in step:
            out += [f"*{step['later']} minutes later.*", ""]
        if "command" in step:
            out += ["```sh", f"$ {step['command']}" + (" <<'EOF'" if step["stdin"] else "")]
            if step["stdin"]:
                out += [step["stdin"].rstrip("\n"), "EOF"]
            out += ["```", "", f"Exit {step['exit']}{' (refused, nothing changed)' if step['exit'] == 1 else ''}:", ""]
            try:
                body = json.dumps(trim(json.loads(step["output"])), ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                body = step["output"].rstrip()
            out += ["```json", body, "```", ""]
    return "\n".join(out).rstrip() + "\n"


def copy_tree(src: Path, dest: Path) -> None:
    for path in sorted(src.rglob("*")):
        target = dest / path.relative_to(src)
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)


def fresh_before(name: str, redraw: bool) -> tuple[Path, Clock]:
    """Rebuilds before/. The incoming files already there are kept unless redraw is set: the
    video encoder is not deterministic, and commands.sh names files by their sha256."""
    example = EXAMPLES / name
    inbox = example / "before" / "inbox"
    kept = {} if redraw or not inbox.is_dir() else {p.name: p.read_bytes() for p in inbox.iterdir()}
    for part in ("before", "after"):
        if (example / part).exists():
            shutil.rmtree(example / part)
    before = example / "before"
    before.mkdir(parents=True)
    fake = Clock(BUILD_AT)
    BUILDERS[name](before, fake)
    for file_name, data in kept.items():
        (inbox / file_name).write_bytes(data)
    return before, fake


def rebuild(name: str, scratch: Path, redraw: bool) -> None:
    example = EXAMPLES / name
    before, _ = fresh_before(name, redraw)
    work = scratch / name
    if work.exists():
        shutil.rmtree(work)
    copy_tree(before, work)
    results = execute(example, work)
    copy_tree(work, example / "after")
    (example / "transcript.md").write_text(transcript(name, results), encoding="utf-8")
    failed = [s for s in results if s.get("exit") not in (None, 0, 1)]
    print(f"{name}: {sum('command' in s for s in results)} commands, exits {[s['exit'] for s in results if 'command' in s]}")
    if failed:
        raise SystemExit(f"{name}: unexpected exit codes: {[(s['command'], s['exit']) for s in failed]}")


def list_before(name: str, redraw: bool) -> None:
    before, fake = fresh_before(name, redraw)
    for box in sorted(p.parent for p in before.glob("*/box.sqlite3")):
        for r in sb(before, fake, "search", "--box", box.name, "--limit", "50")["results"]:
            print(name, box.name, r["ref"][:12], r.get("tags"), (r.get("text") or "")[:20])
    for f in sorted(before.glob("inbox/*")):
        print(name, "inbox", f.name)


def main_() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--before-only", action="store_true", help="build before/ and list its refs, to write commands.sh")
    ap.add_argument("--redraw", action="store_true", help="draw the incoming files again (their sha256 may change)")
    args = ap.parse_args()
    scratch = Path(tempfile.mkdtemp(prefix="sticker-box-examples-"))
    try:
        for name in ([args.only] if args.only else BUILDERS):
            if args.before_only:
                list_before(name, args.redraw)
            else:
                rebuild(name, scratch, args.redraw)
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


if __name__ == "__main__":
    main_()
