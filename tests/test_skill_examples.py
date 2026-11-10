"""Every example in skills/sticker-box/examples still runs as its transcript says: each command in
commands.sh, run on a copy of before/, exits as recorded. Answers are not compared, since OCR
hints and match scores move with library versions."""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import make_skill_examples as examples  # noqa: E402

NAMES = sorted(p.parent.name for p in examples.EXAMPLES.glob("*/commands.sh"))


def test_every_task_in_the_skill_has_an_example():
    linked = set(re.findall(r"`examples/([a-z-]+)/`", (ROOT / "skills" / "sticker-box" / "SKILL.md").read_text()))
    assert linked == set(NAMES) == set(examples.BUILDERS)


@pytest.mark.parametrize("name", NAMES)
def test_example_runs_as_its_transcript_says(name, tmp_path):
    example = examples.EXAMPLES / name
    recorded = [int(code) for code in re.findall(r"^Exit (\d)", (example / "transcript.md").read_text(), re.M)]
    examples.copy_tree(example / "before", tmp_path)
    results = [s for s in examples.execute(example, tmp_path) if "command" in s]
    assert [s["exit"] for s in results] == recorded, [(s["command"], s["output"][:300]) for s in results if s["exit"]]
    assert recorded and set(recorded) <= {0, 1}
