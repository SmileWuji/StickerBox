from pathlib import Path

import cv2
import numpy as np
import pytest

import factory
from sticker_box import features


@pytest.fixture
def scene(tmp_path):
    big = factory.picture(500, (1200, 900))[:, :, :3]
    out = tmp_path / "src"
    out.mkdir()

    def save(name, rgb):
        path = out / name
        cv2.imwrite(str(path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
        return path

    crop = cv2.resize(big[200:650, 300:900], (1200, 900))
    rot = cv2.warpAffine(big, cv2.getRotationMatrix2D((600, 450), 25, 0.8), (1200, 900), borderValue=(255, 255, 255))
    shot = np.full((1600, 900, 3), 240, np.uint8)
    shot[300:975, 0:900] = cv2.resize(big, (900, 675))
    cv2.rectangle(shot, (0, 0), (900, 120), (30, 30, 30), -1)
    return {
        "orig": save("orig.jpg", big),
        "crop": save("crop.jpg", crop),
        "rot": save("rot.jpg", rot),
        "shot": save("shot.png", shot),
        "other": save("other.jpg", factory.picture(777, (1200, 900))[:, :, :3]),
    }


@pytest.fixture
def gallery(tmp_path, run_cli, scene):
    root = tmp_path / "g"
    run_cli("init", str(root), "--preset", "gallery", "--language", "en")
    (s,) = run_cli("stage", str(scene["orig"]), "--box", str(root))["results"]
    run_cli("commit", s["ref"], "--box", str(root), "--license", "unknown")
    return root, s["ref"]


@pytest.mark.parametrize("name, kind, fragment", [
    ("crop", "crop_of", "a crop showing 25% of it, zoomed 2.0x"),
    ("rot", "rotation", "rotated by 25 degrees"),
    ("shot", "contains", "contains it, filling 42%"),
])
def test_variants_are_found_and_described(gallery, run_cli, scene, name, kind, fragment):
    root, orig = gallery
    (s,) = run_cli("stage", str(scene[name]), "--box", str(root))["results"]
    (match,) = s["duplicates"]
    assert match["ref"] == orig and match["kind"] == kind and match["method"] == "sift"
    assert fragment in match["summary"]


def test_an_unrelated_picture_matches_nothing(gallery, run_cli, scene):
    root, _ = gallery
    (s,) = run_cli("stage", str(scene["other"]), "--box", str(root))["results"]
    assert s["duplicates"] == []


def test_commit_records_relations_and_dupes_clusters_them(gallery, run_cli, scene):
    root, orig = gallery
    refs = []
    for name in ("crop", "rot", "other"):
        (s,) = run_cli("stage", str(scene[name]), "--box", str(root))["results"]
        run_cli("commit", s["ref"], "--box", str(root), "--license", "unknown")
        refs.append(s["ref"])
    shown = run_cli("show", orig, "--box", str(root))
    assert {r["kind"] for r in shown["relations"]} == {"contains", "rotation"}
    (cluster,) = run_cli("dupes", "--box", str(root))["clusters"]
    assert {m["ref"] for m in cluster["members"]} == {orig, refs[0], refs[1]}
    assert cluster["keeper"] in {orig, refs[0], refs[1]}
    assert all(link["how"] for link in cluster["links"])
    assert cluster["suggested"] == []
    assert run_cli("dupes", "--kind", "near_duplicate", "--box", str(root))["clusters"] == []


def test_dupes_suggests_removing_only_copies_and_never_the_picture_a_screenshot_contains(gallery, run_cli, scene, tmp_path):
    root, orig = gallery
    copy = tmp_path / "copy.jpg"
    cv2.imwrite(str(copy), cv2.imread(str(scene["orig"])), [cv2.IMWRITE_JPEG_QUALITY, 60])
    refs = {}
    for name, path in (("shot", scene["shot"]), ("copy", copy)):
        (s,) = run_cli("stage", str(path), "--box", str(root))["results"]
        run_cli("commit", s["ref"], "--box", str(root), "--license", "unknown")
        refs[name] = s["ref"]
    (cluster,) = run_cli("dupes", "--box", str(root))["clusters"]
    assert cluster["keeper"] == refs["shot"]
    assert [s["command"].split()[2] for s in cluster["suggested"]] == [refs["copy"][:12]]
    assert orig[:12] in cluster["suggested"][0]["effect"]


def test_reindex_rebuilds_the_same_relations(gallery, run_cli, scene):
    root, orig = gallery
    (s,) = run_cli("stage", str(scene["crop"]), "--box", str(root))["results"]
    run_cli("commit", s["ref"], "--box", str(root), "--license", "unknown")
    before = run_cli("show", s["ref"], "--box", str(root))["relations"]
    out = run_cli("reindex", "--box", str(root))
    assert out == {"items": 2, "relations": 1, "with_features": 2, "incomplete_matching": 0, "failed": []}
    after = run_cli("show", s["ref"], "--box", str(root))["relations"]
    assert [(r["ref"], r["kind"]) for r in after] == [(r["ref"], r["kind"]) for r in before]


def test_commit_recomputes_features_when_the_staged_file_was_cleaned(gallery, run_cli, scene):
    root, orig = gallery
    (s,) = run_cli("stage", str(scene["crop"]), "--box", str(root))["results"]
    (root / "temporary" / f"{s['ref']}.features.npz").unlink()
    run_cli("commit", s["ref"], "--box", str(root), "--license", "unknown")
    import sqlite3

    conn = sqlite3.connect(root / "box.sqlite3")
    assert conn.execute("SELECT COUNT(*) FROM feature WHERE sha256 = ?", (s["ref"],)).fetchone()[0] == 1


def test_flat_art_has_no_features():
    flat = np.full((512, 512, 3), 255, np.uint8)
    cv2.circle(flat, (256, 256), 100, (0, 0, 255), -1)
    assert features.extract(flat, (512, 512), 300) is None


def test_classify_reads_the_transform():
    H = np.array([[0.5, 0.0, 300.0], [0.0, 0.5, 200.0], [0.0, 0.0, 1.0]])
    kind, t = features.classify(H, (1200, 900), (1200, 900))
    assert kind == "crop_of" and t["zoom"] == 2.0 and t["region_in_b"] == [0.25, 0.222, 0.75, 0.722]


def test_an_invalid_commit_fails_before_any_sift_matching(gallery, run_cli, scene, monkeypatch):
    root, _ = gallery
    (s,) = run_cli("stage", str(scene["crop"]), "--box", str(root))["results"]

    def no_matching(*args, **kwargs):
        raise AssertionError("matched before validation")

    monkeypatch.setattr(features, "match", no_matching)
    out = run_cli("commit", s["ref"], "--box", str(root), "--license", "unknown", "--field", "nope=1", expect=1)
    assert out["error"] == "invalid"
