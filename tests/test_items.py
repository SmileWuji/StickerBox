import os
import sqlite3
import time
from datetime import timedelta
from pathlib import Path

import pytest

import factory
from sticker_box import clock

GENERIC = Path(__file__).resolve().parent.parent / "testdata" / "generic"
STICKER = ["--license", "unknown", "--text", "", "--note", "when testing"]


@pytest.fixture
def box(tmp_path, run_cli):
    def make(preset="telegram-sticker", language="zh-Hans"):
        root = tmp_path / preset
        run_cli("init", str(root), "--preset", preset, "--language", language)
        return root

    return make


def stage(run_cli, root, *paths, expect=0, extra=()):
    return run_cli("stage", *map(str, paths), "--box", str(root), *extra, expect=expect)["results"]


def rows(root, sql):
    conn = sqlite3.connect(root / "box.sqlite3")
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def test_stage_reports_early_and_writes_no_row(box, run_cli):
    root = box()
    ok, bad = stage(run_cli, root, GENERIC / "sticker-static.webp", GENERIC / "oversize.png")
    assert ok["status"] == "staged" and ok["file_problems"] == []
    assert ok["requires"] == {"fields": ["license", "note", "text"], "categories": ["emotion"], "vocabulary": "open"}
    assert ok["ocr_hint"]["engine"] == "rapidocr"
    assert {p["rule"] for p in bad["file_problems"]} == {"png.one_side", "png.max_side"}
    assert rows(root, "SELECT COUNT(*) FROM item") == [(0,)]
    assert (root / "temporary" / f"{ok['ref']}.webp").is_file() and (root / "temporary" / f"{ok['ref']}.json").is_file()
    listed = run_cli("staged", "--box", str(root))["staged"]
    assert {s["ref"] for s in listed} == {ok["ref"], bad["ref"]}


def test_stage_reports_a_missing_file_without_stopping(box, run_cli):
    root = box()
    results = stage(run_cli, root, "nope.webp", GENERIC / "sticker-static.webp", expect=1)
    assert results[0]["status"] == "error" and results[1]["status"] == "staged"


def test_commit_returns_every_problem_at_once(box, run_cli):
    root = box()
    (bad,) = stage(run_cli, root, GENERIC / "oversize.png")
    out = run_cli("commit", bad["ref"][:10], "--box", str(root), expect=1)
    kinds = sorted(p["problem"] for p in out["problems"])
    assert kinds == ["file_rule", "file_rule", "missing_category", "missing_field", "missing_field", "missing_field"]
    assert rows(root, "SELECT COUNT(*) FROM item") == [(0,)]


def test_commit_stores_the_file_and_the_row(box, run_cli):
    root = box()
    (s,) = stage(run_cli, root, GENERIC / "sticker-static.webp")
    out = run_cli("commit", s["ref"][:12], "--box", str(root), *STICKER, "--define", "emotion=无语", "说不出话", "--define", "visual=圆", "圆形")
    assert out["status"] == "stored"
    out_unknown = run_cli("commit", s["ref"][:12], "--box", str(root), expect=1)
    assert out_unknown["error"] == "already_stored"
    path = Path(out["file"])
    assert path.is_file() and path.parent.parent.name == "persistent" and path.name.endswith(f"-{s['ref']}.webp")
    assert not (root / "temporary" / f"{s['ref']}.json").exists()
    shown = run_cli("show", s["ref"][:8], "--box", str(root))
    assert shown["tags"] == ["emotion=无语", "visual=圆"] and shown["license"] == "unknown" and shown["text"] == ""
    assert "说不出话" in (root / "README.md").read_text()
    again = stage(run_cli, root, GENERIC / "sticker-static.webp")[0]
    assert again["status"] == "already_stored"


def test_open_vocabulary_refuses_undefined_tags_with_suggestions(box, run_cli):
    root = box()
    (a,) = stage(run_cli, root, GENERIC / "sticker-static.webp")
    run_cli("commit", a["ref"], "--box", str(root), *STICKER, "--define", "emotion=无语", "说不出话")
    (b,) = stage(run_cli, root, GENERIC / "sticker-wide.webp")
    out = run_cli("commit", b["ref"], "--box", str(root), *STICKER, "--tag", "emotion=无语了", expect=1)
    (problem,) = out["problems"]
    assert problem["problem"] == "unknown_tag" and problem["suggestions"] == ["emotion=无语"]


def recompressed(tmp_path, source: Path) -> Path:
    from PIL import Image

    out = tmp_path / "copy.webp"
    with Image.open(source) as im:
        im.save(out, "WEBP", quality=40)
    return out


def test_near_duplicate_is_refused_in_a_sticker_box(box, run_cli, tmp_path):
    root = box()
    (a,) = stage(run_cli, root, GENERIC / "sticker-static.webp")
    run_cli("commit", a["ref"], "--box", str(root), *STICKER, "--define", "emotion=无语", "说不出话")
    (b,) = stage(run_cli, root, recompressed(tmp_path, GENERIC / "sticker-static.webp"))
    assert b["duplicates"][0]["ref"] == a["ref"] and b["duplicates"][0]["kind"] == "near_duplicate"
    out = run_cli("commit", b["ref"], "--box", str(root), *STICKER, "--tag", "emotion=无语", expect=1)
    assert [p["problem"] for p in out["problems"]] == ["duplicate"]


def test_near_duplicate_is_reported_and_linked_in_a_gallery(box, run_cli, tmp_path):
    root = box("gallery", "en")
    (a,) = stage(run_cli, root, GENERIC / "sticker-static.webp")
    run_cli("commit", a["ref"], "--box", str(root), "--license", "unknown")
    (b,) = stage(run_cli, root, recompressed(tmp_path, GENERIC / "sticker-static.webp"))
    out = run_cli("commit", b["ref"], "--box", str(root), "--license", "unknown", "--tag", "copy")
    assert out["relations"][0]["kind"] == "near_duplicate"
    assert run_cli("show", a["ref"], "--box", str(root))["relations"][0]["ref"] == b["ref"]


def test_a_still_cut_from_an_animation_is_linked_as_frame_of(box, run_cli, tmp_path):
    root = box("gallery", "en")
    frames = factory.animation(31, n=12, size=(320, 320))
    anim = factory.write_webm(tmp_path / "anim.webm", frames)
    still = factory.write_png(tmp_path / "still.png", frames[0])
    (a,) = stage(run_cli, root, anim)
    run_cli("commit", a["ref"], "--box", str(root), "--license", "unknown")
    (b,) = stage(run_cli, root, still)
    assert b["duplicates"] and b["duplicates"][0]["kind"] == "frame_of" and b["duplicates"][0]["ref"] == a["ref"]


def test_edit_changes_tags_and_keeps_required_categories(box, run_cli):
    root = box()
    (a,) = stage(run_cli, root, GENERIC / "sticker-static.webp")
    run_cli("commit", a["ref"], "--box", str(root), *STICKER, "--define", "emotion=无语", "说不出话")
    out = run_cli("edit", a["ref"], "--box", str(root), "--define", "emotion=开心", "高兴", "--remove-tag", "emotion=无语", "--note", "新的")
    assert out["tags"] == ["emotion=开心"] and out["note"] == "新的"
    out = run_cli("edit", a["ref"], "--box", str(root), "--remove-tag", "emotion=开心", expect=1)
    assert out["problems"][0]["problem"] == "missing_category"
    out = run_cli("edit", a["ref"], "--box", str(root), "--clear", "license", expect=1)
    assert out["problems"][0]["field"] == "license"


def test_remove_deletes_rows_and_files(box, run_cli):
    root = box("gallery", "en")
    a, b = stage(run_cli, root, GENERIC / "sticker-static.webp", GENERIC / "animated.gif")
    stored = run_cli("commit", a["ref"], "--box", str(root), "--license", "unknown")
    run_cli("remove", a["ref"], b["ref"], "--box", str(root))
    assert not Path(stored["file"]).exists()
    assert rows(root, "SELECT COUNT(*) FROM item") == [(0,)]
    assert rows(root, "SELECT COUNT(*) FROM keyframe") == [(0,)]
    assert not list((root / "temporary").glob(f"{b['ref']}*"))


def test_refs_are_checked(box, run_cli):
    root = box()
    assert run_cli("show", "xyz", "--box", str(root), expect=1)["error"] == "invalid_ref"
    assert run_cli("show", "abcdef12", "--box", str(root), expect=1)["error"] == "not_found"


def test_clean_respects_the_grace_period(box, run_cli):
    root = box()
    a, b = stage(run_cli, root, GENERIC / "sticker-static.webp", GENERIC / "sticker-wide.webp")
    old = time.time() - 3 * 3600
    for path in (root / "temporary").glob(f"{a['ref']}*"):
        os.utime(path, (old, old))
    out = run_cli("clean", "--box", str(root))
    assert out["staged_removed"] == [a["ref"]]
    assert run_cli("clean", "--all", "--box", str(root))["staged_removed"] == [b["ref"]]


def test_limits_fail_loudly_and_auto_cleanup_makes_room(box, run_cli):
    root = box("gallery", "en")
    run_cli("policy", "set", "limits", '{"max_items": 1}', "--box", str(root))
    (a,) = stage(run_cli, root, GENERIC / "sticker-static.webp")
    run_cli("commit", a["ref"], "--box", str(root), "--license", "unknown")
    out = run_cli("stage", str(GENERIC / "animated.gif"), "--box", str(root), expect=3)
    assert out["error"] == "limit_exceeded" and out["items"] == 1 and out["max_items"] == 1
    (b,) = stage(run_cli, root, GENERIC / "animated.gif", extra=("--auto-cleanup",))
    assert b["removed"][0]["ref"] == a["ref"] and b["removed"][0]["reason"] == "oldest"
    run_cli("commit", b["ref"], "--box", str(root), "--license", "unknown")
    assert rows(root, "SELECT COUNT(*) FROM item") == [(1,)]


def test_buffer_items_expire_and_clean_removes_them(box, run_cli, monkeypatch):
    root = box("buffer", "en")
    (a,) = stage(run_cli, root, GENERIC / "animated.webp")
    out = run_cli("commit", a["ref"], "--box", str(root), "--license", "unknown")
    assert out["expires_at"]
    later = clock.now() + timedelta(minutes=61)
    monkeypatch.setattr(clock, "now", lambda: later)
    assert run_cli("show", a["ref"], "--box", str(root))["expired"] is True
    removed = run_cli("clean", "--box", str(root))["expired_removed"]
    assert [r["ref"] for r in removed] == [a["ref"]]
    assert not Path(out["file"]).exists()
