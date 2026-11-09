import sqlite3
from pathlib import Path

import factory

GENERIC = Path(__file__).resolve().parent.parent / "testdata" / "generic"


def init(run_cli, root, preset, language="zh-Hans"):
    run_cli("init", str(root), "--preset", preset, "--language", language)
    return ["--box", str(root)]


def sticker(tmp_path, seed):
    return factory.write_webp(tmp_path / f"s{seed}.webp", factory.picture(seed, (512, 512), alpha=True))


def test_m7_buffer_fills_refuses_recovers_and_transfers(tmp_path, run_cli):
    buf = init(run_cli, tmp_path / "buffer", "buffer")
    run_cli("policy", "set", "limits", '{"max_items": 2}', *buf)
    refs = []
    for seed in (1, 2):
        (s,) = run_cli("stage", str(sticker(tmp_path, seed)), *buf)["results"]
        run_cli("commit", s["ref"], *buf, "--license", "CC0", "--note", f"刚收到的第{seed}张", "--tag", "群友发的")
        refs.append(s["ref"])

    refused = run_cli("stage", str(sticker(tmp_path, 3)), *buf, expect=3)
    assert refused["error"] == "limit_exceeded" and "sticker-box clean" in refused["message"]
    (s3,) = run_cli("stage", str(sticker(tmp_path, 3)), "--auto-cleanup", *buf)["results"]
    assert s3["commit_would_remove"] == [refs[0]]
    out = run_cli("commit", s3["ref"], *buf, "--license", "unknown", "--auto-cleanup")
    assert [r["ref"] for r in out["removed"]] == [refs[0]]

    stickers = init(run_cli, tmp_path / "stickers", "telegram-sticker")
    (t,) = run_cli("stage", "--from", str(tmp_path / "buffer"), refs[1][:10], *stickers)["results"]
    assert t["origin"]["tags"] == ["tag=群友发的"] and t["license"] == "CC0"
    refused = run_cli("commit", t["ref"], *stickers, expect=1)
    assert {p.get("field") or p.get("category") for p in refused["problems"]} == {"text", "note", "emotion"}
    assert t["origin"]["note"] == "刚收到的第2张"
    out = run_cli("commit", t["ref"], *stickers, "--text", "", "--note", t["origin"]["note"], "--define", "emotion=开心", "高兴")
    shown = run_cli("show", out["ref"], *stickers)
    assert shown["license"] == "CC0" and shown["note"] == "刚收到的第2张" and shown["tags"] == ["emotion=开心"]
    assert run_cli("show", refs[1], *buf)["ref"] == refs[1]


def test_transfer_refuses_this_same_box_and_staged_refs(tmp_path, run_cli):
    gal = init(run_cli, tmp_path / "g", "gallery", "en")
    (s,) = run_cli("stage", str(GENERIC / "animated.gif"), *gal)["results"]
    assert run_cli("stage", "--from", str(tmp_path / "g"), s["ref"], *gal, expect=1)["error"] == "usage"
    other = init(run_cli, tmp_path / "o", "gallery", "en")
    assert run_cli("stage", "--from", str(tmp_path / "g"), s["ref"], *other, expect=1)["error"] == "not_found"


def test_check_reports_drift_without_changing_anything(tmp_path, run_cli):
    box = init(run_cli, tmp_path / "s", "telegram-sticker")
    (a,) = run_cli("stage", str(GENERIC / "sticker-static.webp"), *box)["results"]
    stored = run_cli("commit", a["ref"], *box, "--license", "unknown", "--text", "", "--note", "x", "--define", "emotion=无语", "说不出话")
    (b,) = run_cli("stage", str(GENERIC / "sticker-wide.webp"), *box)["results"]
    run_cli("commit", b["ref"], *box, "--license", "unknown", "--text", "", "--note", "y", "--tag", "emotion=无语")
    assert run_cli("check", *box)["ok"] is True

    run_cli("policy", "set", "fields", '{"license": {"required": true}, "artist": {"required": true}}', *box)
    run_cli("tag", "retire", "emotion", "无语", *box)
    Path(stored["file"]).unlink()
    (tmp_path / "s" / "persistent" / "stray.webp").write_bytes(b"x")
    out = run_cli("check", "--strict", *box, expect=1)
    assert out["problem_counts"] == {"missing_file": 1, "missing_field": 2, "retired_tag": 2}
    assert out["orphan_files"] == ["persistent/stray.webp"]
    conn = sqlite3.connect(tmp_path / "s" / "box.sqlite3")
    assert conn.execute("SELECT COUNT(*) FROM item").fetchone()[0] == 2


def test_check_deep_notices_a_changed_file(tmp_path, run_cli):
    box = init(run_cli, tmp_path / "g", "gallery", "en")
    (a,) = run_cli("stage", str(GENERIC / "animated.gif"), *box)["results"]
    stored = run_cli("commit", a["ref"], *box, "--license", "unknown")
    Path(stored["file"]).write_bytes((GENERIC / "animated.webp").read_bytes())
    assert run_cli("check", *box)["problem_counts"] == {}
    assert run_cli("check", "--deep", *box)["problem_counts"] == {"changed_file": 1}
