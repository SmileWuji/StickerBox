import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PRIVATE = ROOT / "testdata" / "private"
sys.path.insert(0, str(Path(__file__).resolve().parent))


def private_sources() -> list[Path]:
    """The owner's corpora: directories inside testdata/private (links or copies), plus the
    absolute paths listed in testdata/private/sources.txt. STICKER_BOX_PRIVATE overrides both."""
    override = os.environ.get("STICKER_BOX_PRIVATE")
    root = Path(override) if override else PRIVATE
    if not root.is_dir():
        return []
    found = [p for p in sorted(root.iterdir()) if p.is_dir()]
    listing = root / "sources.txt"
    if listing.is_file():
        for line in listing.read_text().splitlines():
            line = line.strip()
            if line and Path(line).is_dir():
                found.append(Path(line))
    return found


@pytest.fixture
def private_data() -> list[Path]:
    sources = private_sources()
    if not sources:
        pytest.skip("no private corpora in testdata/private")
    return sources


@pytest.fixture
def run_cli(capsys):
    from sticker_box.cli import main

    def run(*argv: str, expect: int = 0) -> dict:
        code = main(["--json", *argv])
        out = capsys.readouterr().out
        assert code == expect, out
        return json.loads(out) if out.strip() else {}

    return run
