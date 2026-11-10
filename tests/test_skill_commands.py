"""Every `sticker-box ...` command written in the skills, docs and README must still parse against
the current CLI, so instructions agents copy cannot go stale. Commands are parsed, never run."""

import contextlib
import io
import re
import shlex
from pathlib import Path

import pytest

from sticker_box.cli import build_parser
from sticker_box.errors import BoxError

ROOT = Path(__file__).resolve().parent.parent
SOURCES = sorted(ROOT.glob("skills/**/*.md")) + sorted(ROOT.glob("docs/*.md")) + [ROOT / "README.md"]
SPAN = re.compile(r"`(sticker-box [^`]+)`")
PLACEHOLDER = re.compile(r"<[^<>]+>")
SPECIAL = {"<rule>": "limits", "<json>": "{}", "<words>": "word"}


def _subcommands() -> set[str]:
    names = set()
    parser = build_parser()
    stack = [parser]
    while stack:
        p = stack.pop()
        for action in p._actions:
            if hasattr(action, "choices") and isinstance(action.choices, dict):
                names.update(action.choices)
                stack.extend(action.choices.values())
    return names


SUBCOMMANDS = _subcommands()


def commands_in(path: Path) -> list[tuple[int, str]]:
    found = []
    lines = path.read_text(encoding="utf-8").splitlines()
    in_block = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            in_block = not in_block
        elif in_block and line.strip().startswith("sticker-box "):
            start, text = i + 1, line.strip()
            while text.endswith("\\") and i + 1 < len(lines):
                i += 1
                text = text[:-1] + " " + lines[i].strip()
            found.append((start, re.split(r"\s+#", text)[0].strip()))
        elif not in_block:
            found += [(i + 1, m.group(1)) for m in SPAN.finditer(line)]
        i += 1
    return [(n, c) for n, c in found if not _just_a_name(c)]


def _choices(parser) -> dict:
    for action in parser._actions:
        if hasattr(action, "choices") and isinstance(action.choices, dict):
            return action.choices
    return {}


def _just_a_name(command: str) -> bool:
    """Prose that names a command (`sticker-box tag new`) rather than showing an invocation. Only
    a path that exists in the CLI counts; a misnested or renamed one is parsed and fails."""
    words = command.split()[1:]
    if words == ["skill"]:
        return True
    parser = build_parser()
    for word in words:
        parser = _choices(parser).get(word)
        if parser is None:
            return False
    return bool(words)


def tokens_of(command: str) -> list[str]:
    for key, value in SPECIAL.items():
        command = command.replace(key, value)
    command = PLACEHOLDER.sub("deadbeef01", command).replace('"..."', '"x"').replace("'...'", "'x'")
    out = []
    for token in shlex.split(command)[1:]:
        if token == "...":
            previous = out[-1] if out else ""
            if previous.startswith("-") or previous in SUBCOMMANDS:
                out.append("x")
            continue
        out.append(token)
    return out


def parse_problem(command: str) -> str | None:
    try:
        argv = tokens_of(command)
    except ValueError as err:
        return f"cannot split: {err}"
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            build_parser().parse_args(argv)
    except BoxError as err:
        return err.message
    except SystemExit as exc:
        return None if exc.code in (0, None) else f"exit {exc.code}"
    return None


ALL = [(path.relative_to(ROOT), line, cmd) for path in SOURCES for line, cmd in commands_in(path)]


def test_the_extractor_finds_the_documented_commands():
    assert len(ALL) >= 40
    assert {str(p).split("/")[0] for p, _, _ in ALL} >= {"skills", "docs", "README.md"}


@pytest.mark.parametrize("path, line, command", ALL, ids=[f"{p}:{n}" for p, n, _ in ALL])
def test_documented_command_parses(path, line, command):
    problem = parse_problem(command)
    assert problem is None, f"{path}:{line}: `{command}`: {problem}"


@pytest.mark.parametrize("command", [
    "sticker-box frames <ref> --out x.jpg",
    "sticker-box notes set --file notes.txt",
    "sticker-box policy set on_duplicate reject",
    "sticker-box tag new emotion 无语",
])
def test_the_check_catches_stale_commands(command):
    assert parse_problem(command) is not None


@pytest.mark.parametrize("command", ["sticker-box vocab rename", "sticker-box tag review", "sticker-box policy list", "sticker-box lock"])
def test_a_misnested_command_name_is_not_skipped_as_prose(command):
    assert not _just_a_name(command) and parse_problem(command) is not None


def test_a_real_command_name_is_prose():
    assert _just_a_name("sticker-box tag new") and _just_a_name("sticker-box vocab lock")
