import json
import sqlite3

import pytest

from sticker_box import db
from sticker_box.box import Box
from sticker_box.errors import BoxError


@pytest.mark.parametrize("preset", ["telegram-sticker", "gallery", "buffer"])
def test_init_creates_the_tree(tmp_path, run_cli, preset):
    out = run_cli("init", str(tmp_path / "b"), "--preset", preset, "--language", "zh-Hans")
    root = tmp_path / "b"
    assert out["preset"] == preset
    assert sorted(p.name for p in root.iterdir()) == ["README.md", "box.sqlite3", "persistent", "temporary"]
    readme = (root / "README.md").read_text()
    assert "Do not change this directory by hand" in readme
    info = run_cli("info", "--box", str(root))
    assert info["preset"] == preset and info["language"] == "zh-Hans" and info["items"] == 0


def test_init_refuses_existing_box_and_non_empty_dir(tmp_path, run_cli):
    run_cli("init", str(tmp_path / "b"), "--preset", "gallery", "--language", "en")
    assert run_cli("init", str(tmp_path / "b"), "--preset", "gallery", "--language", "en", expect=1)["error"] == "exists"
    (tmp_path / "c").mkdir()
    (tmp_path / "c" / "x").write_text("x")
    assert run_cli("init", str(tmp_path / "c"), "--preset", "gallery", "--language", "en", expect=1)["error"] == "not_empty"


def test_init_validates_language(tmp_path, run_cli):
    assert run_cli("init", str(tmp_path / "b"), "--preset", "gallery", "--language", "中文", expect=1)["error"] == "invalid_language"


def test_box_from_environment_and_cwd(tmp_path, run_cli, monkeypatch):
    run_cli("init", str(tmp_path / "b"), "--preset", "buffer", "--language", "en")
    monkeypatch.setenv("STICKER_BOX_DIR", str(tmp_path / "b"))
    assert run_cli("info")["preset"] == "buffer"
    monkeypatch.delenv("STICKER_BOX_DIR")
    monkeypatch.chdir(tmp_path / "b")
    assert run_cli("info")["preset"] == "buffer"
    monkeypatch.chdir(tmp_path)
    assert run_cli("info", expect=1)["error"] == "no_box"


def test_policy_set_is_validated_logged_and_reaches_the_readme(tmp_path, run_cli):
    root = str(tmp_path / "b")
    run_cli("init", root, "--preset", "gallery", "--language", "en")
    out = run_cli("policy", "set", "limits", '{"max_bytes": 1048576}', "--box", root)
    assert out["params"] == {"max_bytes": 1048576, "max_items": None}
    assert "At most 1 MB of images." in (tmp_path / "b" / "README.md").read_text()
    shown = run_cli("policy", "show", "limits", "--box", root)
    assert shown["params"]["max_bytes"] == 1048576
    conn = sqlite3.connect(tmp_path / "b" / "box.sqlite3")
    log = conn.execute("SELECT name, old, new FROM policy_log").fetchall()
    assert log[0][0] == "limits" and json.loads(log[0][2])["max_bytes"] == 1048576


@pytest.mark.parametrize(
    "rule, params, fragment",
    [
        ("limits", '{"max_bytes": -1}', "max_bytes"),
        ("limits", '{"maxbytes": 1}', "unknown key"),
        ("fields", '{"license": {"required": false}}', "license is always required"),
        ("vocabulary", '{"mode": "open", "default_category": "nope"}', "not a category"),
        ("files", '{"formats": {"bmp": {}}}', "unknown key"),
        ("duplicates", '{"on_duplicate": "explode"}', "on_duplicate"),
    ],
)
def test_policy_set_rejects_bad_params(tmp_path, run_cli, rule, params, fragment):
    root = str(tmp_path / "b")
    run_cli("init", root, "--preset", "gallery", "--language", "en")
    out = run_cli("policy", "set", rule, params, "--box", root, expect=1)
    assert out["error"] == "invalid_policy" and fragment in out["message"]


def test_policy_set_rejects_invalid_json(tmp_path, run_cli):
    root = str(tmp_path / "b")
    run_cli("init", root, "--preset", "gallery", "--language", "en")
    assert run_cli("policy", "set", "limits", "{", "--box", root, expect=1)["error"] == "invalid_json"


def test_telegram_preset_describes_the_spec(tmp_path, run_cli):
    root = tmp_path / "b"
    run_cli("init", str(root), "--preset", "telegram-sticker", "--language", "zh-Hans")
    readme = (root / "README.md").read_text()
    assert "one side exactly 512 px, the other at most 512 px" in readme
    webm = next(line for line in readme.splitlines() if line.startswith("- WEBM:"))
    for piece in ("at most 256 KB", "at most 3 s long", "at most 30 fps", "codec vp9", "no audio"):
        assert piece in webm
    assert "Vocabulary is open" in readme


def test_notes_render_quoted_under_to_agents(tmp_path, run_cli):
    root = tmp_path / "b"
    run_cli("init", str(root), "--preset", "telegram-sticker", "--language", "zh-Hans")
    run_cli("notes", "set", "# Sources\nbangumi-data first", "--box", str(root))
    readme = (root / "README.md").read_text()
    section = readme.split("## To agents", 1)[1]
    assert "> # Sources\n> bangumi-data first" in section
    assert run_cli("notes", "show", "--box", str(root))["notes"].startswith("# Sources")


def test_newer_schema_is_refused(tmp_path, run_cli):
    root = tmp_path / "b"
    run_cli("init", str(root), "--preset", "gallery", "--language", "en")
    conn = sqlite3.connect(root / "box.sqlite3")
    conn.execute("UPDATE meta SET value = ? WHERE key = 'schema_version'", (str(db.SCHEMA_VERSION + 1),))
    conn.commit()
    conn.close()
    with pytest.raises(BoxError) as exc:
        Box.open(root)
    assert exc.value.code == "box_too_new"
