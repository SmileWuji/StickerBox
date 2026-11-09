"""Runs and scores skill-wording variants on a local Ollama model, following the owner's
optimize-prompt-for-small-vlm protocol: every call cached by (model, skill, variant, input,
repeat) and flushed at once, capped output, thinking off for qwen3.5, a JSON salvage path,
animations shown as contact sheets. Data and cache live in the git-ignored testdata/private/bench/.

    python3 scripts/bench_skills/qwen.py run   --skill tag-text --variant v0 --split dev [--repeat b]
    python3 scripts/bench_skills/qwen.py score --skill tag-text --variants v0,v1 --split dev [--repeat b]
    python3 scripts/bench_skills/qwen.py noise --skill tag-text --variant v0 --split dev
"""

import argparse
import base64
import hashlib
import io
import json
import re
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PIL import Image  # noqa: E402

from sticker_box import analysis, contact, policy  # noqa: E402

BENCH = ROOT / "testdata" / "private" / "bench"
VARIANTS = Path(__file__).resolve().parent / "variants"
HOST = "http://127.0.0.1:11434"
MODEL = "qwen3.5:9b"
SIDE = 512
NUM_PREDICT = 320
FIELD = {"tag-text": None, "tag-emotion": "emotion", "tag-visual": "visual"}


def split_of(key: str, dev_share: float = 0.6) -> str:
    return "dev" if int(hashlib.sha256(key.encode()).hexdigest(), 16) % 100 < dev_share * 100 else "test"


def load_reference() -> dict[str, dict]:
    """Sonnet's labels (its benchmark output, the reference for Qwen), corrected where the main
    agent checked them."""
    ref = {}
    path = BENCH / "sonnet" / "final.json"
    if path.is_file():
        ref = json.loads(path.read_text())
    checked = BENCH / "checked.json"
    if checked.is_file():
        for key, value in json.loads(checked.read_text()).items():
            ref.setdefault(key, {}).update(value, checked=True)
    return ref


def inputs(skill: str, split: str) -> list[dict]:
    data = json.loads((BENCH / "sample.json").read_text())
    ref = load_reference()
    out = []
    if skill == "tag-text":
        for row in data["human"]["has_text"]:
            if split_of(row["id"]) == split:
                out.append({"id": row["id"], "path": row["path"], "gold": {"has_text": row["has_text"], "watermark": row["watermark"]}, "source": "human"})
        human_text = {row["id"]: row["text"] for row in data["human"]["transcribe"]}
        for row in data["human"]["transcribe"]:
            if split_of(row["id"]) == split and row["id"] not in {o["id"] for o in out}:
                out.append({"id": row["id"], "path": row["path"], "gold": {"has_text": True}, "source": "human"})
        for o in out:
            if o["id"] in human_text:
                o["gold"]["text"] = human_text[o["id"]]
    for row in data["sample"]:
        if row["split"] != split or row["id"] not in ref:
            continue
        r = ref[row["id"]]
        gold = {"has_text": r.get("has_text"), "text": r.get("text"), "tags": r.get("tags", []), "checked": r.get("checked", False)}
        out.append({"id": row["id"], "path": row["path"], "gold": gold, "source": "checked" if gold["checked"] else "sonnet",
                    "context_text": r.get("text") or ""})
    return out


def image_b64(item: dict) -> str:
    sheets = BENCH / "sheets"
    sheets.mkdir(parents=True, exist_ok=True)
    cached = sheets / (hashlib.sha256(item["id"].encode()).hexdigest()[:16] + ".jpg")
    if not cached.is_file():
        result = analysis.analyze(Path(item["path"]), policy.DEFAULTS["analysis"])
        if result.info.animated and len(result.keyframes) > 1:
            contact.write(contact.sheet(result.sheet_frames()), cached)
        else:
            im = Image.fromarray(result.keyframes[0].rgb)
            im.thumbnail((SIDE, SIDE))
            im.save(cached, "JPEG", quality=92)
    return base64.b64encode(cached.read_bytes()).decode()


def vocabulary(category: str) -> str:
    db = BENCH / "sonnet-box" / "box.sqlite3"
    if not db.is_file():
        return ""
    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT value, definition FROM tag WHERE category = ? AND retired_at IS NULL ORDER BY value", (category,)).fetchall()
    conn.close()
    return "\n".join(f"- {v}: {d or ''}" for v, d in rows)


def ocr_hint(item: dict) -> str:
    """The RapidOCR hint `stage` would report for this sticker, cached; production agents see it."""
    path = BENCH / "ocr_hints.json"
    hints = json.loads(path.read_text()) if path.is_file() else {}
    if item["id"] not in hints:
        result = analysis.analyze(Path(item["path"]), policy.DEFAULTS["analysis"], with_ocr=True)
        hints[item["id"]] = result.ocr["text"]
        path.write_text(json.dumps(hints, ensure_ascii=False, indent=0))
    return hints[item["id"]]


def build_messages(skill: str, variant: str, item: dict) -> list[dict]:
    template = (VARIANTS / skill / f"{variant}.md").read_text(encoding="utf-8")
    system = template.replace("{VOCABULARY}", vocabulary(FIELD[skill]) if FIELD[skill] else "")
    user = "Answer with the JSON only."
    if skill == "tag-text":
        hint = ocr_hint(item)
        user = f"ocr_hint from stage: {hint if hint else '(nothing found)'}\n" + user
    if skill != "tag-text" and item.get("context_text"):
        user = f"Text on the sticker: {item['context_text']}\n" + user
    return [{"role": "system", "content": system}, {"role": "user", "content": user, "images": [image_b64(item)]}]


def call(messages: list[dict]) -> tuple[str, float, str]:
    body = {"model": MODEL, "messages": messages, "stream": False, "think": False,
            "options": {"temperature": 0, "num_predict": NUM_PREDICT}}
    req = urllib.request.Request(f"{HOST}/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read())
    return data["message"]["content"], time.time() - t0, data.get("done_reason", "")


def parse(content: str) -> tuple[dict | None, bool]:
    """(answer, malformed). A truncated answer (a runaway repetition hitting the token cap) is
    salvaged field by field, as the protocol advises, and still flagged malformed."""
    text = re.sub(r"^```(?:json)?|```$", "", content.strip(), flags=re.M).strip()
    try:
        return json.loads(text), False
    except ValueError:
        m = re.search(r"\{.*\}", text, re.S)
        if m:
            try:
                return json.loads(m.group(0)), True
            except ValueError:
                pass
    salvaged = {}
    if (m := re.search(r'"has_text"\s*:\s*(true|false)', text)):
        salvaged["has_text"] = m.group(1) == "true"
    if (m := re.search(r'"text"\s*:\s*"((?:[^"\\]|\\.)*)', text)):
        salvaged["text"] = m.group(1)
    for key in ("emotion", "visual"):
        if (m := re.search(rf'"{key}"\s*:\s*\[([^\]]*)', text)):
            salvaged[key] = re.findall(r'"([^"]+)"', m.group(1))
    return (salvaged or None), True


def cache_path() -> Path:
    path = BENCH / "qwen" / "cache.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def cached() -> dict[tuple, dict]:
    out = {}
    if cache_path().is_file():
        for line in cache_path().read_text().splitlines():
            row = json.loads(line)
            out[(row["model"], row["skill"], row["variant"], row["id"], row.get("repeat", "a"))] = row
    return out


def run(skill: str, variant: str, split: str, repeat: str = "a") -> None:
    have = cached()
    todo = [i for i in inputs(skill, split) if (MODEL, skill, variant, i["id"], repeat) not in have]
    print(f"{skill} {variant} {split}/{repeat}: {len(todo)} calls to make", flush=True)
    with open(cache_path(), "a", encoding="utf-8") as fh:
        for item in todo:
            content, latency, reason = call(build_messages(skill, variant, item))
            answer, malformed = parse(content)
            fh.write(json.dumps({"model": MODEL, "skill": skill, "variant": variant, "id": item["id"], "repeat": repeat,
                                 "content": content, "answer": answer, "malformed": malformed, "latency": round(latency, 2),
                                 "done_reason": reason}, ensure_ascii=False) + "\n")
            fh.flush()


def norm_text(s: str) -> str:
    return re.sub(r"\s+", "", (s or "")).casefold()


def cer(pred: str, gold: str) -> float:
    a, b = norm_text(pred), norm_text(gold)
    if not b:
        return 0.0 if not a else 1.0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return min(1.0, prev[-1] / len(b))


def aliases() -> dict[str, str]:
    db = BENCH / "sonnet-box" / "box.sqlite3"
    if not db.is_file():
        return {}
    conn = sqlite3.connect(db)
    rows = conn.execute("SELECT t.category, a.alias, t.value FROM tag_alias a JOIN tag t ON t.id = a.tag_id").fetchall()
    conn.close()
    return {f"{c}={a}": f"{c}={v}" for c, a, v in rows}


def tag_set(values, category: str, alias: dict) -> set[str]:
    out = set()
    for v in values or []:
        label = v if "=" in str(v) else f"{category}={v}"
        out.add(alias.get(label, label))
    return {x for x in out if x.startswith(category + "=")}


def score(skill: str, variant: str, split: str, repeat: str = "a") -> dict:
    have = cached()
    rows = [(i, have.get((MODEL, skill, variant, i["id"], repeat))) for i in inputs(skill, split)]
    rows = [(i, r) for i, r in rows if r is not None]
    malformed = sum(1 for _, r in rows if r["malformed"])
    out = {"variant": variant, "split": split, "n": len(rows), "malformed": malformed,
           "latency_p50": round(sorted(r["latency"] for _, r in rows)[len(rows) // 2], 2) if rows else None}
    if skill == "tag-text":
        human = [(i, r) for i, r in rows if i["source"] == "human"]
        ok = [(i, r) for i, r in human if r["answer"] is not None and "has_text" in r["answer"]]
        out["has_text_acc_human"] = round(sum(bool(r["answer"]["has_text"]) == i["gold"]["has_text"] for i, r in ok) / max(1, len(human)), 3)
        wm = [(i, r) for i, r in ok if i["gold"].get("watermark")]
        out["watermark_recall"] = round(sum(bool(r["answer"].get("has_text")) and "@" in (r["answer"].get("text") or "") for i, r in wm) / max(1, len(wm)), 3) if wm else None
        texted = [(i, r) for i, r in rows if i["gold"].get("text")]
        out["cer"] = round(sum(cer((r["answer"] or {}).get("text", ""), i["gold"]["text"]) for i, r in texted) / max(1, len(texted)), 3)
        out["exact"] = round(sum(norm_text((r["answer"] or {}).get("text", "")) == norm_text(i["gold"]["text"]) for i, r in texted) / max(1, len(texted)), 3)
        out["n_text"] = len(texted)
        return out
    category = FIELD[skill]
    alias = aliases()
    p = rc = f1 = 0.0
    scored = 0
    for i, r in rows:
        gold = tag_set(i["gold"]["tags"], category, alias)
        if not gold:
            continue
        pred = tag_set((r["answer"] or {}).get(category, []), category, alias)
        hit = len(gold & pred)
        pp, rr = (hit / len(pred) if pred else 0.0), hit / len(gold)
        p, rc, f1, scored = p + pp, rc + rr, f1 + (2 * pp * rr / (pp + rr) if pp + rr else 0.0), scored + 1
    out.update({"precision": round(p / max(1, scored), 3), "recall": round(rc / max(1, scored), 3),
                "f1": round(f1 / max(1, scored), 3), "n_scored": scored})
    return out


def noise(skill: str, variant: str, split: str) -> dict:
    have = cached()
    a = {k[3]: v for k, v in have.items() if k[:3] == (MODEL, skill, variant) and k[4] == "a"}
    b = {k[3]: v for k, v in have.items() if k[:3] == (MODEL, skill, variant) and k[4] == "b"}
    both = [k for k in a if k in b]
    differ = sum(1 for k in both if json.dumps(a[k]["answer"], sort_keys=True, ensure_ascii=False) != json.dumps(b[k]["answer"], sort_keys=True, ensure_ascii=False))
    return {"n": len(both), "answers_differ": differ, "rate": round(differ / max(1, len(both)), 3),
            "score_a": score(skill, variant, split, "a"), "score_b": score(skill, variant, split, "b")}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("run", "score", "noise"))
    ap.add_argument("--skill", required=True, choices=tuple(FIELD))
    ap.add_argument("--variant")
    ap.add_argument("--variants")
    ap.add_argument("--split", default="dev")
    ap.add_argument("--repeat", default="a")
    args = ap.parse_args()
    if args.action == "run":
        run(args.skill, args.variant, args.split, args.repeat)
    elif args.action == "score":
        for v in (args.variants or args.variant).split(","):
            print(json.dumps(score(args.skill, v, args.split, args.repeat), ensure_ascii=False))
    else:
        print(json.dumps(noise(args.skill, args.variant, args.split), ensure_ascii=False))


if __name__ == "__main__":
    main()
