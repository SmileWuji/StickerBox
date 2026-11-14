"""Tunes phrase matching in `search` (decision 49) on a copy of a real box. Two kinds of query:

- made up from the box: a 4 to 6 character span of an item's description or note, sometimes with
  a filler character inserted inside it, wrapped in chat-like words; the right answers are the
  items that hold the span. Scored by hit@1, hit@3 and MRR.
- real chat lines (`--chat`, JSONL with a `text` field; lines with a `direction` other than
  `in` are the bot's own and skipped), split on punctuation the way a plugin would; there is no
  answer key, so only how many get a candidate is counted, and `--show` prints some to judge.

    python3 scripts/bench_skills/search_phrases.py --box <copy of a box> [--chat a.jsonl ...] [--show N]
"""

import argparse
import json
import random
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from sticker_box import search  # noqa: E402
from sticker_box.box import Box  # noqa: E402

FILLERS = "就又也都还"
PREFIXES = ["", "昨天", "我今天", "刚才", "哈哈", "笑死", "你看", "感觉"]
SUFFIXES = ["", "了", "啊", "吧", "呢", "哈哈哈"]
SPLIT = re.compile(r"[\s，。！？、,.!?~～…：:；;（）()「」“”\"'【】\[\]]+")
CONFIGS = {
    "off": {"PHRASE_MIN_CHARS": 10**6},
    "pairs2-common0.10-nostop": {"PAIRS_NEEDED": 2, "COMMON_SHARE": 0.10, "FUNCTION_CHARS": set()},
    "pairs2-nofilter-stop": {"PAIRS_NEEDED": 2, "COMMON_SHARE": 1.0},
    "pairs2-common0.20": {"PAIRS_NEEDED": 2, "COMMON_SHARE": 0.20},
    "pairs2-common0.30": {"PAIRS_NEEDED": 2, "COMMON_SHARE": 0.30},
    "pairs1-common0.05": {"PAIRS_NEEDED": 1, "COMMON_SHARE": 0.05},
    "pairs2-common0.03": {"PAIRS_NEEDED": 2, "COMMON_SHARE": 0.03},
    "pairs2-common0.05": {"PAIRS_NEEDED": 2, "COMMON_SHARE": 0.05},
    "pairs2-common0.10": {"PAIRS_NEEDED": 2, "COMMON_SHARE": 0.10},
    "pairs2-nofilter": {"PAIRS_NEEDED": 2, "COMMON_SHARE": 1.0},
    "pairs3-common0.05": {"PAIRS_NEEDED": 3, "COMMON_SHARE": 0.05},
}


def made_up(conn, n: int, seed: int) -> list[tuple[str, set[str]]]:
    rng = random.Random(seed)
    rows = conn.execute("SELECT sha256, note, description FROM item").fetchall()
    queries = []
    for row in rng.sample(rows, len(rows)):
        column = "description" if row["description"] and rng.random() < 0.7 else "note"
        runs = [r for r in search._CJK.findall(row[column] or "") if len(r) >= 6]
        if not runs:
            continue
        run = rng.choice(runs)
        size = rng.choice([4, 5, 6])
        start = rng.randrange(len(run) - size + 1)
        span = run[start:start + size]
        phrase = span
        if rng.random() < 0.5:
            cut = rng.randrange(2, size - 1)
            phrase = span[:cut] + rng.choice(FILLERS) + span[cut:]
        query = rng.choice(PREFIXES) + phrase + rng.choice(SUFFIXES)
        right = {r["sha256"] for r in conn.execute(
            "SELECT sha256 FROM item WHERE instr(COALESCE(description, ''), ?) OR instr(COALESCE(note, ''), ?)", (span, span))}
        queries.append((query, right))
        if len(queries) == n:
            break
    return queries


def chat_lines(paths: list[str], n: int, seed: int) -> list[str]:
    lines = set()
    for path in paths:
        for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record.get("direction", "in") != "in":
                continue
            text = record.get("text") or ""
            if len("".join(search._CJK.findall(text))) >= 4:
                lines.add(text)
    lines = sorted(lines)
    random.Random(seed).shuffle(lines)
    return lines[:n]


def as_query(text: str) -> str:
    words = [w for w in SPLIT.split(text) if w and len(w) <= search.MAX_TERM]
    return " ".join(words[:search.MAX_TERMS])


def run(box, config: dict, queries, chats, show: int):
    defaults = {k: getattr(search, k) for k in ("PHRASE_MIN_CHARS", "PAIRS_NEEDED", "COMMON_SHARE", "FUNCTION_CHARS")}
    for key, value in config.items():
        setattr(search, key, value)
    try:
        ranks = []
        for query, right in queries:
            refs = [r["ref"] for r in search.search(box, query, limit=10)["results"]]
            ranks.append(next((i + 1 for i, ref in enumerate(refs) if ref in right), None))
        covered, counts, examples = 0, [], []
        for text in chats:
            results = search.search(box, as_query(text), limit=3)["results"]
            covered += bool(results)
            counts.append(len(results))
            if results and len(examples) < show and "character pairs" in " ".join(results[0]["matched"]):
                examples.append((text, [(r["matched"], r["description"] or r["note"]) for r in results[:1]]))
    finally:
        for key, value in defaults.items():
            setattr(search, key, value)
    out = {
        "made_up_n": len(queries),
        "hit@1": round(sum(r == 1 for r in ranks) / len(ranks), 3),
        "hit@3": round(sum(r is not None and r <= 3 for r in ranks) / len(ranks), 3),
        "mrr": round(statistics.mean(1 / r if r else 0 for r in ranks), 3),
    }
    if chats:
        out["chat_n"] = len(chats)
        out["chat_with_candidate"] = round(covered / len(chats), 3)
        out["chat_mean_candidates"] = round(statistics.mean(counts), 2)
    return out, examples


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--box", required=True)
    ap.add_argument("--chat", nargs="*", default=[])
    ap.add_argument("--queries", type=int, default=200)
    ap.add_argument("--chat-lines", type=int, default=300)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--show", type=int, default=0, help="print this many chat lines whose top candidate came from phrase matching")
    args = ap.parse_args()
    box = Box.open(Path(args.box))
    queries = made_up(box.conn, args.queries, args.seed)
    chats = chat_lines(args.chat, args.chat_lines, args.seed)
    for name, config in CONFIGS.items():
        if args.only and name not in args.only:
            continue
        out, examples = run(box, config, queries, chats, args.show)
        print(json.dumps({"config": name, **out}, ensure_ascii=False))
        for text, top in examples:
            print("   ", text[:60], "->", top)


if __name__ == "__main__":
    main()
