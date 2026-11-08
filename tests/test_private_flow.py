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
    assert dup["duplicates"] and dup["duplicates"][0]["kind"] == "near_duplicate"
    refused = run_cli("commit", dup["ref"], *box, *STICKER, "--tag", "emotion=情绪0", expect=1)
    assert [p["problem"] for p in refused["problems"]] == ["duplicate"]

    big = tmp_path / "big.png"
    with Image.open(original) as im:
        im.convert("RGBA").resize((700, 300)).save(big)
    (bad,) = run_cli("stage", str(big), *box)["results"]
    refused = run_cli("commit", bad["ref"], *box, expect=1)
    problems = sorted(p.get("rule") or p.get("field") or p.get("category") or p["problem"] for p in refused["problems"])
    assert problems == ["duplicate", "emotion", "license", "note", "png.max_side", "png.one_side", "text"]
