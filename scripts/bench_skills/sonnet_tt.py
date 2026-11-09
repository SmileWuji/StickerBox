"""Scores Sonnet's tag-text answers on the human-labelled test stickers, per wording, with the
same metrics as qwen.py. Answers are in testdata/private/bench/sonnet-tt/out-<wording>-<n>.jsonl;
wording a is the shipped skill, b the Qwen-tuned v10, c the shipped v11.

    python3 scripts/bench_skills/sonnet_tt.py
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import qwen  # noqa: E402

TT = qwen.BENCH / "sonnet-tt"


def main() -> None:
    key = json.loads((qwen.BENCH / "smoke-keys" / "sonnet-tt-key.json").read_text())
    gold = {i["id"]: i["gold"] for i in qwen.inputs("tag-text", "test") if i["source"] == "human"}
    for wording in sorted({p.name.split("-")[1] for p in TT.glob("out-*-*.jsonl")}):
        answers = {}
        for path in sorted(TT.glob(f"out-{wording}-*.jsonl")):
            for line in path.read_text().splitlines():
                if line.strip():
                    row = json.loads(line)
                    answers[key[row["key"]]] = row
        scored = [(gold[i], a) for i, a in answers.items() if i in gold]
        wm = [(g, a) for g, a in scored if g.get("watermark")]
        texted = [(g, a) for g, a in scored if g.get("text")]
        print(json.dumps({
            "wording": wording, "n": len(scored),
            "has_text_acc_human": round(sum(bool(a["has_text"]) == g["has_text"] for g, a in scored) / max(1, len(scored)), 3),
            "watermark_recall": round(sum(bool(a["has_text"]) and "@" in a.get("text", "") for g, a in wm) / max(1, len(wm)), 3) if wm else None,
            "n_wm": len(wm),
            "cer": round(sum(qwen.cer(a.get("text", ""), g["text"]) for g, a in texted) / max(1, len(texted)), 3),
            "exact": round(sum(qwen.norm_text(a.get("text", "")) == qwen.norm_text(g["text"]) for g, a in texted) / max(1, len(texted)), 3),
            "n_text": len(texted),
        }))


if __name__ == "__main__":
    main()
