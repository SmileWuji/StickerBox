"""Draws the skill-benchmark sample from the private corpus and attaches the existing human
labels, writing everything under the git-ignored testdata/private/bench/. Deterministic.

    python3 scripts/bench_skills/sample.py --gold-ocr <dir with gt_*.csv> --gold-tagger <phase_b_gt.json>
"""

import argparse
import csv
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

from conftest import private_sources  # noqa: E402

EXTS = (".webp", ".webm", ".png", ".gif", ".jpg")


def corpus_files() -> dict[str, Path]:
    files = {}
    for src in private_sources():
        for path in sorted(src.rglob("*")):
            if path.suffix.lower() in EXTS:
                files[f"{path.parent.name}/{path.name}"] = path
    return files


def resolve(files: dict[str, Path], pack: str, stem: str) -> str | None:
    for ext in EXTS:
        if f"{pack}/{stem}{ext}" in files:
            return f"{pack}/{stem}{ext}"
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold-ocr", required=True)
    ap.add_argument("--gold-tagger", required=True)
    ap.add_argument("--target", type=int, default=250)
    ap.add_argument("--dev-share", type=float, default=0.6)
    ap.add_argument("--seed", type=int, default=2611)
    ap.add_argument("--out", default=str(ROOT / "testdata" / "private" / "bench" / "sample.json"))
    args = ap.parse_args()
    rng = random.Random(args.seed)
    files = corpus_files()
    packs: dict[str, list[str]] = {}
    for key in files:
        packs.setdefault(key.split("/")[0], []).append(key)
    per_pack = math.ceil(args.target / len(packs))
    sample = []
    for pack in sorted(packs):
        chosen = rng.sample(sorted(packs[pack]), min(per_pack, len(packs[pack])))
        for i, key in enumerate(chosen):
            split = "dev" if i < round(len(chosen) * args.dev_share) else "test"
            sample.append({"id": key, "path": str(files[key]), "split": split})
    ocr = Path(args.gold_ocr)
    has_text, missing = [], 0
    for row in csv.DictReader(open(ocr / "gt_hastext.csv", encoding="utf-8")):
        key = resolve(files, row["pack"], row["image_id"])
        if key is None:
            missing += 1
            continue
        has_text.append({"id": key, "path": str(files[key]), "has_text": row["has_text"] == "1", "watermark": row["watermark"] == "1"})
    transcribe = []
    for row in csv.DictReader(open(ocr / "gt_transcribe.csv", encoding="utf-8")):
        key = resolve(files, row["pack"], row["image_id"])
        if key is None:
            missing += 1
            continue
        transcribe.append({"id": key, "path": str(files[key]), "text": row["gold_text"]})
    characters = []
    for entry in json.load(open(args.gold_tagger, encoding="utf-8")).values():
        key = resolve(files, entry["pack"], entry["image_id"])
        if key is None:
            missing += 1
            continue
        characters.append({"id": key, "path": str(files[key]), "characters": entry.get("characters") or [],
                           "series": entry.get("series") or [], "no_character": bool(entry.get("no_character")),
                           "probe": bool(entry.get("hallucination_probe"))})
    out = {"seed": args.seed, "sample": sample,
           "human": {"has_text": has_text, "transcribe": transcribe, "characters": characters}}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    dev = sum(1 for s in sample if s["split"] == "dev")
    print(f"packs {len(packs)}  sample {len(sample)} (dev {dev}, test {len(sample) - dev})  "
          f"human: has_text {len(has_text)}, transcriptions {len(transcribe)}, characters {len(characters)}  unresolved {missing}")


if __name__ == "__main__":
    main()
