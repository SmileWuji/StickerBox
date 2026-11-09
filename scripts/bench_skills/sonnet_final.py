"""Builds the reference labels from the Sonnet labelling run: the per-sticker lines the
subagents wrote, with tags read back from the box after vocabulary cleanup (merges applied).

    python3 scripts/bench_skills/sonnet_final.py [--labels bench/sonnet/labels.jsonl] [--box bench/sonnet-box]
"""

import argparse
import json
import sqlite3
from pathlib import Path

BENCH = Path(__file__).resolve().parents[2] / "testdata" / "private" / "bench"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default=str(BENCH / "sonnet" / "labels.jsonl"))
    ap.add_argument("--box", default=str(BENCH / "sonnet-box"))
    ap.add_argument("--out", default=str(BENCH / "sonnet" / "final.json"))
    args = ap.parse_args()
    conn = sqlite3.connect(Path(args.box) / "box.sqlite3")
    tags: dict[str, list[str]] = {}
    for sha, cat, value in conn.execute("SELECT it.sha256, t.category, t.value FROM item_tag it JOIN tag t ON t.id = it.tag_id"):
        tags.setdefault(sha, []).append(f"{cat}={value}")
    stored = {r[0]: (r[1], r[2]) for r in conn.execute("SELECT sha256, text, note FROM item")}
    final, missing = {}, 0
    for line in Path(args.labels).read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["ref"] not in stored:
            missing += 1
            continue
        text, note = stored[row["ref"]]
        final[row["id"]] = {"ref": row["ref"], "has_text": bool(text), "text": text or "", "tags": sorted(tags.get(row["ref"], [])),
                            "note": note, "attempts": row.get("attempts", 1)}
    Path(args.out).write_text(json.dumps(final, ensure_ascii=False, indent=1))
    print(f"reference labels {len(final)}  lines without a stored item {missing}")


if __name__ == "__main__":
    main()
