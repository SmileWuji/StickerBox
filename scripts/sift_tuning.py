"""Measures SIFT duplicate detection on the private corpora and prints numbers only: true
matches for generated crops, rotations, scalings, overlays and fake chat screenshots, false
matches against every other stored image (other stickers of the same packs are the hard
negatives), the inlier counts of both, and insert time with 3,000 stored images."""

import random
import sqlite3
import statistics
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

from conftest import private_sources  # noqa: E402
from sticker_box import analysis, db, features, policy  # noqa: E402

KEYPOINTS = 300
SIFT = {"keypoints": KEYPOINTS, "min_inliers": 6, "ratio": 0.75}


def load_rgb(path: Path) -> np.ndarray:
    result = analysis.analyze(path, policy.DEFAULTS["analysis"])
    return result.keyframes[0].rgb


def transforms(rgb: np.ndarray, rng: random.Random) -> dict[str, np.ndarray]:
    h, w = rgb.shape[:2]
    out = {}
    fw, fh = rng.uniform(0.45, 0.7), rng.uniform(0.45, 0.7)
    x0, y0 = int(rng.uniform(0, 1 - fw) * w), int(rng.uniform(0, 1 - fh) * h)
    out["crop"] = cv2.resize(rgb[y0:y0 + int(fh * h), x0:x0 + int(fw * w)], (w, h))
    angle = rng.choice([-1, 1]) * rng.uniform(12, 40)
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 0.85)
    out["rotation"] = cv2.warpAffine(rgb, m, (w, h), borderValue=(255, 255, 255))
    out["scaled"] = cv2.resize(rgb, (w // 2, h // 2), interpolation=cv2.INTER_AREA)
    over = rgb.copy()
    cv2.rectangle(over, (0, int(h * 0.7)), (w, h), (255, 255, 255), -1)
    cv2.putText(over, "lol same", (10, int(h * 0.9)), cv2.FONT_HERSHEY_SIMPLEX, w / 300, (0, 0, 0), 3)
    out["overlay"] = over
    shot = np.full((int(h * 2.2), int(w * 1.1), 3), 236, np.uint8)
    cv2.rectangle(shot, (0, 0), (shot.shape[1], int(h * 0.18)), (40, 40, 40), -1)
    for i in range(4):
        y = int(h * 0.25) + i * int(h * 0.09)
        cv2.putText(shot, f"message line {i} hello", (20, y), cv2.FONT_HERSHEY_SIMPLEX, w / 700, (20, 20, 20), 2)
    small = cv2.resize(rgb, (int(w * 0.8), int(h * 0.8)))
    top = int(h * 0.7)
    shot[top:top + small.shape[0], 30:30 + small.shape[1]] = small
    out["screenshot"] = shot
    return out


def sets_of(rgb: np.ndarray) -> list:
    got = features.extract(rgb, (rgb.shape[1], rgb.shape[0]), KEYPOINTS)
    return [(0, got[0], got[1])] if got else []


def insert(conn, sha: str, size: tuple[int, int], sets: list) -> None:
    conn.execute("INSERT INTO item (sha256, file, format, width, height, animated, frames, bytes, phash, added_at, updated_at, license) "
                 "VALUES (?, ?, 'png', ?, ?, 0, 1, 1, 0, '', '', 'x')", (sha, sha, size[0], size[1]))
    for idx, kp, desc in sets:
        conn.execute("INSERT INTO feature VALUES (?, ?, ?, ?, ?, ?)", (sha, idx, features.EXTRACTOR, kp.shape[0], kp.tobytes(), desc.tobytes()))


def main() -> None:
    rng = random.Random(7)
    files = sorted(p for src in private_sources() for p in src.rglob("*.webp"))
    rng.shuffle(files)
    conn = db.connect(Path(":memory:"))
    conn.executescript(db.SCHEMA)
    originals = []
    for path in files:
        if len(originals) == 150:
            break
        rgb = load_rgb(path)
        sets = sets_of(rgb)
        if not sets:
            continue
        sha = f"{len(originals):064x}"
        insert(conn, sha, (rgb.shape[1], rgb.shape[0]), sets)
        originals.append((sha, rgb))
    skipped = 0
    true_inl, false_inl, found = {}, [], {}
    for sha, rgb in originals:
        for name, img in transforms(rgb, rng).items():
            sets = sets_of(img)
            if not sets:
                skipped += 1
                continue
            for m in features.match(conn, sets, (img.shape[1], img.shape[0]), SIFT):
                if m["ref"] == sha:
                    true_inl.setdefault(name, []).append(m["inliers"])
                    found.setdefault(name, []).append(m["kind"])
                else:
                    false_inl.append(m["inliers"])
    print(f"originals {len(originals)}  queries per kind {len(originals)}  queries without enough keypoints {skipped}")
    for name in ("crop", "rotation", "scaled", "overlay", "screenshot"):
        inl = sorted(true_inl.get(name, []))
        kinds = found.get(name, [])
        common = max(set(kinds), key=kinds.count) if kinds else "-"
        p10 = inl[len(inl) // 10] if inl else 0
        print(f"{name:10} found {len(inl):3}/{len(originals)}  inliers p10 {p10:3} p50 {statistics.median(inl) if inl else 0:5.0f}  kind {common} ({kinds.count(common) if kinds else 0})")
    fs = sorted(false_inl)
    print(f"false matches (min_inliers 6): {len(fs)}  inliers max {fs[-1] if fs else 0}  p99 {fs[int(len(fs) * 0.99) - 1] if fs else 0}")
    for floor in (10, 12, 15, 20):
        tp = sum(sum(1 for x in v if x >= floor) for v in true_inl.values())
        fp = sum(1 for x in fs if x >= floor)
        print(f"  min_inliers {floor:2}: true {tp}/{len(originals) * 5}  false {fp}")

    pool = [p for p in files if p.suffix == ".webp"]
    n = len(originals)
    while n < 3000:
        rgb = load_rgb(pool[n % len(pool)])
        variant = cv2.flip(rgb, 1) if (n // len(pool)) % 2 else rgb[: rgb.shape[0] * 9 // 10]
        sets = sets_of(np.ascontiguousarray(variant))
        if sets:
            insert(conn, f"{n:064x}", (variant.shape[1], variant.shape[0]), sets)
        n += 1
    stored = conn.execute("SELECT COUNT(*) FROM feature").fetchone()[0]
    times = []
    for sha, rgb in originals[:20]:
        img = transforms(rgb, rng)["crop"]
        sets = sets_of(img)
        t0 = time.time()
        features.match(conn, sets, (img.shape[1], img.shape[0]), {**SIFT, "min_inliers": 12})
        times.append(time.time() - t0)
    print(f"scale: {stored} stored feature sets, match p50 {statistics.median(times):.2f} s  max {max(times):.2f} s")


if __name__ == "__main__":
    main()
