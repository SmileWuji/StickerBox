"""Regenerates testdata/generic from seeds. Every file is drawn by tests/factory.py, so the
directory holds nothing third-party and can be committed."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

import factory  # noqa: E402


def main() -> None:
    out = ROOT / "testdata" / "generic"
    out.mkdir(parents=True, exist_ok=True)
    factory.write_webp(out / "sticker-static.webp", factory.picture(101, (512, 512), alpha=True))
    factory.write_webp(out / "sticker-wide.webp", factory.picture(102, (512, 320), alpha=True))
    factory.write_webm(out / "sticker-video.webm", factory.animation(103, n=24, size=(512, 512)), fps=24)
    factory.write_png(out / "oversize.png", factory.picture(104, (800, 600)))
    factory.write_jpg(out / "photo-with-text.jpg", factory.picture(105, (640, 480), text="HELLO BOX"))
    factory.write_animated_webp(out / "animated.webp", factory.animation(106, n=10, size=(256, 256)))
    factory.write_gif(out / "animated.gif", factory.animation(107, n=10, size=(200, 200)))
    for path in sorted(out.iterdir()):
        print(f"{path.name}\t{path.stat().st_size}")


if __name__ == "__main__":
    main()
