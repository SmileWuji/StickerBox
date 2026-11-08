"""Analyses every image in the private corpora and prints numbers only (no image content), for
the M2 exit check and for comparing keyframe counts with GuidedStickerBootCamp's corpus note."""

import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from conftest import private_sources  # noqa: E402
from sticker_box import analysis  # noqa: E402
from sticker_box.errors import BoxError  # noqa: E402

SUFFIXES = {".webp", ".webm", ".png", ".jpg", ".jpeg", ".gif"}
BOOTCAMP_PACKS = {"pack_one", "pack_two", "pack_three"}


def main() -> None:
    files = sorted(p for src in private_sources() for p in src.rglob("*") if p.suffix.lower() in SUFFIXES)
    params = {"keyframe_drop_thr": 0.10, "max_keyframes": 64}
    by_format, errors, walls = defaultdict(int), defaultdict(int), defaultdict(list)
    bootcamp = {"files": 0, "frames": 0, "keyframes": 0, "at_cap": 0}
    per_anim = []
    start = time.time()
    for path in files:
        t0 = time.time()
        try:
            result = analysis.analyze(path, params)
        except BoxError as err:
            errors[err.code] += 1
            continue
        info = result.info
        kind = f"{info.format}-{'animated' if info.animated else 'static'}"
        by_format[kind] += 1
        walls[kind].append((time.time() - t0) * 1000)
        if info.animated:
            per_anim.append(len(result.keyframes))
        if info.format == "webm" and path.parent.name in BOOTCAMP_PACKS:
            bootcamp["files"] += 1
            bootcamp["frames"] += info.frames
            bootcamp["keyframes"] += len(result.keyframes)
            bootcamp["at_cap"] += len(result.keyframes) == params["max_keyframes"]
    print(f"files {len(files)}  analysed {sum(by_format.values())}  errors {dict(errors) or 0}  wall {time.time() - start:.0f}s")
    for kind in sorted(by_format):
        w = sorted(walls[kind])
        print(f"{kind:16} {by_format[kind]:5}  wall p50 {statistics.median(w):.0f} ms  p95 {w[int(len(w) * 0.95) - 1]:.0f} ms")
    if per_anim:
        s = sorted(per_anim)
        print(f"keyframes per animation: min {s[0]} p50 {statistics.median(s):.0f} p95 {s[int(len(s) * 0.95) - 1]} max {s[-1]}")
    if bootcamp["files"]:
        ratio = bootcamp["frames"] / bootcamp["keyframes"]
        print(f"BootCamp subset: {bootcamp['files']} WEBM, {bootcamp['frames']} frames, {bootcamp['keyframes']} keyframes, {ratio:.1f}x, at cap {bootcamp['at_cap']}")


if __name__ == "__main__":
    main()
