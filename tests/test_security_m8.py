"""Regressions for the M8 security review (261109-SECURITY-REVIEW-M8.md); numbers refer to it."""

import json
import os
import shutil
import sqlite3
from pathlib import Path

import pytest

import factory
from sticker_box import media
from sticker_box.errors import BoxError

GENERIC = Path(__file__).resolve().parent.parent / "testdata" / "generic"


@pytest.fixture
def gallery(tmp_path, run_cli):
    root = tmp_path / "g"
    run_cli("init", str(root), "--preset", "gallery", "--language", "en")
    return root


def test_3_ffmpeg_protocol_names_in_file_names_mean_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    factory.write_webm(tmp_path / "other.webm", factory.animation(1, n=20, size=(64, 64)))
    shutil.copy(GENERIC / "sticker-video.webm", tmp_path / "concat:other.webm")
    info = media.probe(Path("concat:other.webm"))
    assert info.frames == 24 and info.width == 512


def test_3_the_decoder_ffmpeg_picks_is_checked(monkeypatch):
    monkeypatch.setattr(media, "WEBM_FOURCC", set())
    with pytest.raises(BoxError) as exc:
        media.probe(GENERIC / "sticker-video.webm")
    assert exc.value.code == "unsupported_format"


def test_4_a_source_box_cannot_return_huge_values(gallery, run_cli, tmp_path):
    (s,) = run_cli("stage", str(GENERIC / "animated.gif"), "--box", str(gallery))["results"]
    run_cli("commit", s["ref"], "--box", str(gallery), "--license", "x")
    conn = sqlite3.connect(gallery / "box.sqlite3")
    cols = [r[1] for r in conn.execute("PRAGMA table_info(item)")]
    keep = ", ".join(c for c in cols if c != "text")
    conn.executescript(f"""
        CREATE TABLE item2 AS SELECT * FROM item;
        DROP TABLE item;
        CREATE TABLE item ({", ".join(c if c != "text" else "text TEXT GENERATED ALWAYS AS (zeroblob(5000000)) VIRTUAL" for c in cols)});
        INSERT INTO item ({keep}) SELECT {keep} FROM item2;
    """)
    conn.close()
    dest = tmp_path / "d"
    run_cli("init", str(dest), "--preset", "gallery", "--language", "en")
    assert run_cli("stage", "--from", str(gallery), s["ref"], "--box", str(dest), expect=1)["error"] == "unsafe_box"


def test_5_a_fifo_does_not_hang_stage(gallery, run_cli, tmp_path):
    fifo = tmp_path / "pipe.webp"
    os.mkfifo(fifo)
    out = run_cli("stage", str(fifo), "--box", str(gallery), expect=1)
    assert out["results"][0]["error"] == "not_found" and "regular" in out["results"][0]["message"]


def test_8_frames_refuses_a_symlinked_staged_file(gallery, run_cli, tmp_path):
    (s,) = run_cli("stage", str(GENERIC / "animated.gif"), "--box", str(gallery))["results"]
    staged = Path(s["file"])
    staged.unlink()
    os.symlink(GENERIC / "animated.webp", staged)
    assert run_cli("frames", s["ref"], "--box", str(gallery), expect=1)["error"] == "corrupt_staging"


def test_9_unexpected_errors_are_json(tmp_path, run_cli):
    root = tmp_path / "bad"
    root.mkdir()
    (root / "box.sqlite3").write_bytes(b"not a database at all, just text" * 10)
    out = run_cli("info", "--box", str(root), expect=1)
    assert out["error"] in ("corrupt_box", "not_a_box")


def test_9_a_planted_directory_does_not_break_commit(gallery, run_cli):
    (s,) = run_cli("stage", str(GENERIC / "animated.gif"), "--box", str(gallery))["results"]
    (gallery / "temporary" / f"{s['ref']}.d").mkdir()
    run_cli("commit", s["ref"], "--box", str(gallery), "--license", "x")
    assert (gallery / "temporary" / f"{s['ref']}.d").is_dir()


def test_10_planted_matches_are_not_stored(gallery, run_cli):
    (a,) = run_cli("stage", str(GENERIC / "photo-with-text.jpg"), "--box", str(gallery))["results"]
    run_cli("commit", a["ref"], "--box", str(gallery), "--license", "x")
    (b,) = run_cli("stage", str(GENERIC / "animated.webp"), "--box", str(gallery))["results"]
    path = gallery / "temporary" / f"{b['ref']}.json"
    data = json.loads(path.read_text())
    data["sift_matches"] = [{"ref": a["ref"], "kind": "duplicate", "method": "sift", "inliers": 999, "transform": {}}]
    path.write_text(json.dumps(data))
    out = run_cli("commit", b["ref"], "--box", str(gallery), "--license", "x")
    assert out["relations"] == [] and run_cli("dupes", "--box", str(gallery))["clusters"] == []


def test_11_aliases_are_capped(gallery, run_cli):
    run_cli("tag", "new", "tag", "cat", "--means", "a cat", "--box", str(gallery))
    run_cli("tag", "alias", "tag", "cat", *[f"c{i}" for i in range(32)], "--box", str(gallery))
    assert run_cli("tag", "alias", "tag", "cat", "c32", "--box", str(gallery), expect=1)["error"] == "too_many_aliases"
