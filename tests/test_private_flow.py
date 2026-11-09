"""Milestone exit checks on the owner's corpora. Tags here are placeholders written by the test;
nothing about the images is asserted beyond what the tool computes."""

from pathlib import Path

import pytest
from PIL import Image

pytestmark = pytest.mark.private
STICKER = ["--license", "unknown", "--text", "", "--note", "test"]


def corpus_files(sources: list[Path], suffix: str) -> list[Path]:
    return sorted(p for src in sources for p in src.rglob(f"*{suffix}"))


def test_m3_twenty_stickers_a_duplicate_and_a_refusal(private_data, tmp_path, run_cli):
    root = tmp_path / "stickers"
    run_cli("init", str(root), "--preset", "telegram-sticker", "--language", "zh-Hans")
    box = ["--box", str(root)]
    candidates = corpus_files(private_data, ".webp")[::7] + corpus_files(private_data, ".webm")[::11]
    stored = []
    for path in candidates:
        if len(stored) == 20:
            break
        (result,) = run_cli("stage", str(path), *box)["results"]
        if result["status"] != "staged" or result["file_problems"] or result["duplicates"]:
            continue
        mood = f"情绪{len(stored) % 4}"
        defined = any(s[1] == mood for s in stored)
        tag = ["--tag", f"emotion={mood}"] if defined else ["--define", f"emotion={mood}", f"测试用的情绪 {mood}"]
        out = run_cli("commit", result["ref"], *box, *STICKER, *tag)
        stored.append((out["file"], mood))
    assert len(stored) == 20
    assert run_cli("info", *box)["items"] == 20

    original = next(Path(f) for f, _ in stored if f.endswith(".webp"))
    copy = tmp_path / "copy.webp"
    with Image.open(original) as im:
        im.save(copy, "WEBP", quality=35)
    (dup,) = run_cli("stage", str(copy), *box)["results"]
    assert dup["duplicates"] and dup["duplicates"][0]["kind"] == "near_duplicate" and dup["duplicates"][0]["suggested"]
    run_cli("remove", dup["ref"], *box)

    big = tmp_path / "big.png"
    with Image.open(original) as im:
        im.convert("RGBA").resize((700, 300)).save(big)
    (bad,) = run_cli("stage", str(big), *box)["results"]
    refused = run_cli("commit", bad["ref"], *box, expect=1)
    problems = sorted(p.get("rule") or p.get("field") or p.get("category") or p["problem"] for p in refused["problems"])
    assert problems == ["emotion", "license", "note", "png.max_side", "png.one_side", "text"]


MOODS = {"无语": "说不出话", "无语了": "说不出话了", "开心": "高兴", "开心！": "很高兴", "哭": "流泪", "大哭": "哭得厉害",
         "生气": "发火", "害羞": "不好意思", "震惊": "吓一跳", "得意": "自鸣得意"}


def test_m4_bootstrap_review_merge_lock(private_data, tmp_path, run_cli):
    root = tmp_path / "stickers"
    run_cli("init", str(root), "--preset", "telegram-sticker", "--language", "zh-Hans")
    box = ["--box", str(root)]
    files = corpus_files(private_data, ".webp")
    moods = list(MOODS)
    defined, stored = set(), 0
    for path in files[::5]:
        if stored == 50:
            break
        (result,) = run_cli("stage", str(path), *box)["results"]
        if result["status"] != "staged" or result["file_problems"] or result["duplicates"]:
            continue
        mood = moods[stored % len(moods)]
        tag = ["--tag", f"emotion={mood}"] if mood in defined else ["--define", f"emotion={mood}", MOODS[mood]]
        out = run_cli("commit", result["ref"], *box, *STICKER, *tag)
        defined.add(mood)
        stored += 1
    assert stored == 50
    review = run_cli("vocab", "review", *box)
    pairs = {frozenset((p["a"]["value"], p["b"]["value"])) for p in review["similar_pairs"]}
    assert {frozenset(("无语", "无语了")), frozenset(("哭", "大哭"))} <= pairs
    names = {t["value"] for t in run_cli("tag", "list", *box)["tags"]}
    assert "开心！" not in names
    run_cli("tag", "merge", "emotion", "无语了", "无语", *box)
    run_cli("tag", "parent", "emotion", "大哭", "哭", *box)
    run_cli("vocab", "lock", *box)
    tags = {t["value"]: t for t in run_cli("tag", "list", *box)["tags"]}
    assert tags["无语"]["uses"] == 10 and tags["无语"]["aliases"] == ["无语了"] and tags["大哭"]["parent"] == "哭"
    readme = (root / "README.md").read_text()
    assert "Vocabulary is locked" in readme and "| 无语 | 说不出话 | 无语了 |  | 10 |" in readme
