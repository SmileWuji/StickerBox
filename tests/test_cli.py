import json

import pytest

from sticker_box.cli import main, render_text
from sticker_box.errors import EXIT_USAGE


def test_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    assert "sticker-box" in capsys.readouterr().out


def test_no_command_prints_help(capsys):
    assert main([]) == 0
    assert "usage" in capsys.readouterr().out


def test_unknown_command_is_a_usage_error_in_json(capsys):
    assert main(["--json", "nonsense"]) == EXIT_USAGE
    body = json.loads(capsys.readouterr().out)
    assert body["error"] == "usage"


def test_json_from_environment(capsys, monkeypatch):
    monkeypatch.setenv("STICKER_BOX_JSON", "1")
    assert main(["nonsense"]) == EXIT_USAGE
    assert json.loads(capsys.readouterr().out)["error"] == "usage"


def test_usage_error_goes_to_stderr_as_text(capsys):
    assert main(["nonsense"]) == EXIT_USAGE
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "error (usage)" in captured.err


def test_render_text_nests_and_skips_empty():
    text = render_text({"a": 1, "b": None, "c": [], "d": {"e": "f"}, "g": [1, 2], "h": [{"i": 3}]})
    assert text.splitlines() == ["a: 1", "d:", "  e: f", "g: 1, 2", "h:", "  -", "    i: 3"]
