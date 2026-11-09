"""Regressions for the M7 security review (261108-SECURITY-REVIEW-M7.md); numbers refer to it."""

import json
import os
import sqlite3
from pathlib import Path

import numpy as np
import pytest

from sticker_box import features

GENERIC = Path(__file__).resolve().parent.parent / "testdata" / "generic"
FAKE = "a" * 64


@pytest.fixture
def gallery(tmp_path, run_cli):
    root = tmp_path / "g"
    run_cli("init", str(root), "--preset", "gallery", "--language", "en")
    return root


def plant_sidecar(root: Path, sha: str, **override) -> None:
    data = {"sha256": sha, "file": f"{sha}.webp", "media": {"format": "webp"}, "keyframes": [{"phash": "0" * 16}], "phash": "0" * 16}
    data.update(override)
    (root / "temporary" / f"{sha}.json").write_text(json.dumps(data))


def test_1_planted_sidecar_cannot_name_outside_files(gallery, run_cli, tmp_path):
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me")
    plant_sidecar(gallery, FAKE, file=str(victim))
    assert run_cli("commit", FAKE[:12], "--box", str(gallery), "--license", "x", expect=1)["error"] == "corrupt_staging"
    run_cli("remove", FAKE[:12], "--box", str(gallery))
    assert victim.read_text() == "keep me"


def test_1_hostile_sha_in_a_sidecar_writes_nothing_outside(gallery, run_cli, tmp_path):
    (s,) = run_cli("stage", str(GENERIC / "animated.gif"), "--box", str(gallery))["results"]
    sidecar = gallery / "temporary" / f"{s['ref']}.json"
    data = json.loads(sidecar.read_text())
    data["sha256"] = str(tmp_path / "outside" / "settings")
    sidecar.write_text(json.dumps(data))
    out = run_cli("stage", str(GENERIC / "animated.gif"), "--license", "CC0", "--box", str(gallery), expect=1)
    assert out["results"][0]["error"] == "corrupt_staging"
    assert not (tmp_path / "outside").exists()


def test_1_commit_rehashes_the_staged_file(gallery, run_cli):
    (s,) = run_cli("stage", str(GENERIC / "animated.gif"), "--box", str(gallery))["results"]
    Path(s["file"]).write_bytes((GENERIC / "animated.webp").read_bytes())
    assert run_cli("commit", s["ref"], "--box", str(gallery), "--license", "x", expect=1)["error"] == "changed"


def test_2_symlinked_box_folders_are_refused(gallery, run_cli, tmp_path):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "precious").write_text("x")
    os.rename(gallery / "temporary", tmp_path / "old-temporary")
    os.symlink(elsewhere, gallery / "temporary")
    assert run_cli("clean", "--all", "--box", str(gallery), expect=1)["error"] == "unsafe_box"
    assert (elsewhere / "precious").exists()


def test_2_rows_pointing_outside_are_never_unlinked(gallery, run_cli, tmp_path):
    (s,) = run_cli("stage", str(GENERIC / "animated.gif"), "--box", str(gallery))["results"]
    run_cli("commit", s["ref"], "--box", str(gallery), "--license", "x")
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me")
    conn = sqlite3.connect(gallery / "box.sqlite3")
    conn.execute("UPDATE item SET file = ?, expires_at = '2000-01-01T00:00:00Z'", (str(victim),))
    conn.commit()
    conn.close()
    assert run_cli("check", "--box", str(gallery))["problem_counts"] == {"bad_path": 1}
    out = run_cli("clean", "--box", str(gallery))
    assert out["expired_removed"][0]["file_left"] and victim.read_text() == "keep me"


def test_3_a_planted_feature_file_is_replaced_not_stored(gallery, run_cli):
    (s,) = run_cli("stage", str(GENERIC / "photo-with-text.jpg"), "--box", str(gallery))["results"]
    npz = gallery / "temporary" / f"{s['ref']}.features.npz"
    np.savez(npz, n=np.array([1]), idx0=np.array([0]), kp0=np.zeros((40, 2), np.float32), desc0=np.zeros((40, 129), np.uint8))
    run_cli("commit", s["ref"], "--box", str(gallery), "--license", "x")
    conn = sqlite3.connect(gallery / "box.sqlite3")
    n, desc = conn.execute("SELECT n, desc FROM feature").fetchone()
    assert len(desc) == n * 128


def test_3_malformed_stored_rows_are_skipped(gallery, run_cli):
    (s,) = run_cli("stage", str(GENERIC / "photo-with-text.jpg"), "--box", str(gallery))["results"]
    run_cli("commit", s["ref"], "--box", str(gallery), "--license", "x")
    conn = sqlite3.connect(gallery / "box.sqlite3")
    conn.execute("UPDATE feature SET n = n + 1")
    conn.commit()
    conn.close()
    (t,) = run_cli("stage", str(GENERIC / "oversize.png"), "--box", str(gallery))["results"]
    assert t["status"] == "staged"
    assert run_cli("check", "--box", str(gallery))["stale_features"] == [s["ref"]]


def test_4_sift_cost_is_capped_and_timed(gallery, run_cli, monkeypatch):
    out = run_cli("policy", "set", "duplicates", '{"sift": {"keypoints": 2000}, "on_duplicate": "report"}', "--box", str(gallery), expect=1)
    assert "limited to" in out["message"]
    monkeypatch.setattr(features, "SIFT_SECONDS", -1.0)
    (s,) = run_cli("stage", str(GENERIC / "photo-with-text.jpg"), "--box", str(gallery))["results"]
    run_cli("commit", s["ref"], "--box", str(gallery), "--license", "x")
    (t,) = run_cli("stage", str(GENERIC / "oversize.png"), "--box", str(gallery))["results"]
    sidecar = json.loads((gallery / "temporary" / f"{t['ref']}.json").read_text())
    assert "stopped" in sidecar["sift_note"]


def test_5_reindex_keeps_the_box_when_one_file_is_bad(gallery, run_cli):
    refs = []
    for name in ("photo-with-text.jpg", "oversize.png"):
        (s,) = run_cli("stage", str(GENERIC / name), "--box", str(gallery))["results"]
        refs.append(run_cli("commit", s["ref"], "--box", str(gallery), "--license", "x")["file"])
    Path(refs[0]).unlink()
    out = run_cli("reindex", "--box", str(gallery))
    assert out["items"] == 1 and out["failed"][0]["error"] == "not_found"
    conn = sqlite3.connect(gallery / "box.sqlite3")
    assert conn.execute("SELECT COUNT(DISTINCT sha256) FROM feature").fetchone()[0] == 2


def test_6_and_7_hostile_source_boxes(gallery, run_cli, tmp_path):
    (s,) = run_cli("stage", str(GENERIC / "animated.gif"), "--box", str(gallery))["results"]
    run_cli("commit", s["ref"], "--box", str(gallery), "--license", "x")
    dest = tmp_path / "d"
    run_cli("init", str(dest), "--preset", "gallery", "--language", "en")

    conn = sqlite3.connect(gallery / "box.sqlite3")
    conn.execute("UPDATE item SET text = ?", (b"\x00binary",))
    conn.commit()
    out = run_cli("stage", "--from", str(gallery), s["ref"], "--box", str(dest))
    assert "text" in out["results"][0]["warnings"][0]
    run_cli("remove", s["ref"], "--box", str(dest))

    conn.execute("ALTER TABLE item RENAME TO item_real")
    conn.execute("CREATE VIEW item AS WITH RECURSIVE r(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM r) SELECT i.* FROM item_real i, r")
    conn.commit()
    conn.close()
    assert run_cli("stage", "--from", str(gallery), s["ref"], "--box", str(dest), expect=1)["error"] == "unsafe_box"


def test_6_symlinked_source_persistent_is_refused(gallery, run_cli, tmp_path):
    dest = tmp_path / "d"
    run_cli("init", str(dest), "--preset", "gallery", "--language", "en")
    os.rename(gallery / "persistent", tmp_path / "p")
    os.symlink("/", gallery / "persistent")
    assert run_cli("stage", "--from", str(gallery), FAKE[:12], "--box", str(dest), expect=1)["error"] == "unsafe_box"


@pytest.mark.parametrize("rule, params", [
    ("retention", '{"expire_after_minutes": 10000000000}'),
    ("retention", '{"staged_grace_minutes": 1' + "0" * 320 + '}'),
    ("limits", '{"max_items": 100000000000}'),
])
def test_8_policy_integers_are_bounded(gallery, run_cli, rule, params):
    assert run_cli("policy", "set", rule, params, "--box", str(gallery), expect=1)["error"] == "invalid_policy"
