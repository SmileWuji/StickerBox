"""contrib/convert/sticker.py makes files a telegram-sticker box accepts. The WEBM path needs
vpxenc and vpxdec and is skipped without them."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import factory

SCRIPT = Path(__file__).resolve().parent.parent / "contrib" / "convert" / "sticker.py"


def convert(*argv: str) -> str:
    done = subprocess.run([sys.executable, str(SCRIPT), *argv], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return done.stdout


@pytest.fixture
def box(tmp_path, run_cli):
    root = tmp_path / "s"
    run_cli("init", str(root), "--preset", "telegram-sticker", "--language", "en")
    return root


def problems(run_cli, box, path: Path) -> list:
    (staged,) = run_cli("stage", str(path), "--box", str(box))["results"]
    return staged["file_problems"]


def test_static_and_cropped_outputs_meet_the_spec(tmp_path, run_cli, box):
    source = factory.write_png(tmp_path / "in.png", factory.picture(5, (300, 200), alpha=True))
    assert "does not meet" in convert("info", str(source))
    convert("webp", str(source), str(tmp_path / "out.webp"))
    convert("png", str(source), str(tmp_path / "crop.png"), "--crop", "10,10,100,150")
    assert "meets the static sticker spec" in convert("info", str(tmp_path / "out.webp"))
    assert problems(run_cli, box, tmp_path / "out.webp") == []
    assert problems(run_cli, box, tmp_path / "crop.png") == []


def test_animation_to_gif_and_one_frame(tmp_path):
    source = factory.write_animated_webp(tmp_path / "in.webp", factory.animation(3, n=6, size=(256, 256)))
    assert "6 frames" in convert("gif", str(source), str(tmp_path / "out.gif"))
    assert "only frame 2 was kept" in convert("webp", str(source), str(tmp_path / "one.webp"), "--frame", "2")


@pytest.mark.skipif(not (shutil.which("vpxenc") and shutil.which("vpxdec")), reason="needs vpxenc and vpxdec (vpx-tools)")
def test_animation_to_webm_meets_the_spec(tmp_path, run_cli, box):
    source = factory.write_gif(tmp_path / "in.gif", factory.animation(4, n=60, size=(300, 240)), duration_ms=80)
    assert "only" in convert("webm", str(source), str(tmp_path / "out.webm"))
    assert problems(run_cli, box, tmp_path / "out.webm") == []


def test_a_failed_conversion_leaves_no_output(tmp_path):
    import numpy as np

    noise = np.random.default_rng(1).integers(0, 256, (512, 512, 4), dtype=np.uint8)
    source = factory.write_png(tmp_path / "noise.png", noise)
    done = subprocess.run([sys.executable, str(SCRIPT), "png", str(source), str(tmp_path / "out.png")], capture_output=True, text=True)
    assert done.returncode == 1 and "over 512 KB" in done.stderr
    assert not (tmp_path / "out.png").exists()
    keep = tmp_path / "keep.png"
    keep.write_bytes(b"not touched")
    done = subprocess.run([sys.executable, str(SCRIPT), "png", str(source), str(keep), "--crop", "bad"], capture_output=True, text=True)
    assert done.returncode == 1 and keep.read_bytes() == b"not touched"
