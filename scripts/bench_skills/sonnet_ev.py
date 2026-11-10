"""Scores emotion and visual tags on the 26 stickers the main agent checked, the only labels
independent of Sonnet's own run: Sonnet with the original (a) and the Qwen-tuned (b) emotion
wording from testdata/private/bench/sonnet-ev/out-<wording>.jsonl, and Qwen's cached answers.

    python3 scripts/bench_skills/sonnet_ev.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qwen  # noqa: E402


def prf(rows: list[tuple[set, set]]) -> dict:
    """Mean per-sticker scores, skipping stickers with no gold tag in the category as
    `qwen.score` does; a missing or unparsable answer counts as no tags."""
    rows = [(gold, pred) for gold, pred in rows if gold]
    p = r = f = 0.0
    for gold, pred in rows:
        hit = len(gold & pred)
        pp, rr = (hit / len(pred) if pred else 0.0), hit / len(gold)
        p, r, f = p + pp, r + rr, f + (2 * pp * rr / (pp + rr) if pp + rr else 0.0)
    n = max(1, len(rows))
    return {"p": round(p / n, 3), "r": round(r / n, 3), "f1": round(f / n, 3), "n": len(rows)}


def main() -> None:
    alias = qwen.aliases()
    checked = json.loads((qwen.BENCH / "checked.json").read_text())
    key = json.loads((qwen.BENCH / "smoke-keys" / "sonnet-ev-key.json").read_text())
    have = qwen.cached()
    answers = {}
    for wording in ("a", "b"):
        path = qwen.BENCH / "sonnet-ev" / f"out-{wording}.jsonl"
        if path.is_file():
            answers[f"sonnet-{wording}"] = {key[row["key"]]: row for row in (json.loads(line) for line in path.read_text().splitlines() if line.strip())}
    for skill, variant in (("tag-emotion", "v0"), ("tag-emotion", "v7"), ("tag-visual", "v0")):
        answers[f"qwen-{skill[4:]}-{variant}"] = {k[3]: v["answer"] or {} for k, v in have.items()
                                                  if k[:3] == (qwen.MODEL, skill, variant) and k[4] == "a" and k[3] in checked}
    asked = {"sonnet-a": ("emotion", "visual"), "sonnet-b": ("emotion", "visual"), "qwen-emotion-v0": ("emotion",),
             "qwen-emotion-v7": ("emotion",), "qwen-visual-v0": ("visual",)}
    for name, got in answers.items():
        out = {"who": name}
        for category in asked[name]:
            rows = [(qwen.tag_set(checked[i]["tags"], category, alias), qwen.tag_set(got.get(i, {}).get(category, []), category, alias))
                    for i in checked]
            out[category] = prf(rows)
        print(json.dumps(out, ensure_ascii=False))


if __name__ == "__main__":
    main()
