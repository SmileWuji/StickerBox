"""Regressions for the M5 security review (261108-SECURITY-REVIEW-M5.md); numbers refer to it."""

import random
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import factory
from sticker_box import keyframes, media, phash
from sticker_box.errors import BoxError

GENERIC = Path(__file__).resolve().parent.parent / "testdata" / "generic"


@pytest.fixture
def gallery(tmp_path, run_cli):
    root = tmp_path / "g"
    run_cli("init", str(root), "--preset", "gallery", "--language", "en")
    return root


def naive_extract(frames, drop_thr, max_keyframes):
    kept = []
    for frame_no, t_ms, rgb in frames:
        bits = phash.bits64(rgb)
        dist = phash.norm_hamming(bits, kept[-1][2]) if kept else 0.0
        if not kept or dist > drop_thr:
            kept.append((frame_no, t_ms, bits, dist))
    if len(kept) > max_keyframes:
        rest = sorted(kept[1:], key=lambda k: (-k[3], k[0]))[: max_keyframes - 1]
        kept = [kept[0]] + sorted(rest, key=lambda k: k[0])
    return [k[0] for k in kept]


def test_1_streaming_keyframes_match_the_original_selection():
    rng = random.Random(3)
    pics = [factory.picture(i, (64, 64))[:, :, :3] for i in range(12)]
    frames = [(i, i * 10, pics[rng.randrange(12)]) for i in range(200)]
    for cap in (1, 3, 8, 64):
        got = [k.frame_no for k in keyframes.extract(iter(frames), 0.10, cap)]
        assert got == naive_extract(frames, 0.10, cap)


def test_2_no_file_arguments_only_stdin(gallery, run_cli, monkeypatch):
    out = run_cli("notes", "set", "--file", "/proc/self/environ", "--box", str(gallery), expect=2)
    assert out["error"] == "usage"
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO("from stdin"))
    assert run_cli("notes", "set", "--stdin", "--box", str(gallery))["notes"] == "from stdin"


def test_3_frames_cannot_write_outside_the_box(gallery, run_cli, tmp_path):
    out = run_cli("frames", str(GENERIC / "animated.gif"), "--out", str(tmp_path / "victim"), "--box", str(gallery), expect=2)
    assert out["error"] == "usage" and not (tmp_path / "victim").exists()


def test_4_stage_never_deletes_stored_items(gallery, run_cli, tmp_path):
    run_cli("policy", "set", "limits", '{"max_items": 1}', "--box", str(gallery))
    (a,) = run_cli("stage", str(GENERIC / "sticker-static.webp"), "--box", str(gallery))["results"]
    run_cli("commit", a["ref"], "--box", str(gallery), "--license", "unknown")
    junk = tmp_path / "junk.bin"
    junk.write_bytes(b"x" * 5000)
    out = run_cli("stage", str(junk), "--auto-cleanup", "--box", str(gallery), expect=1)
    assert out["results"][0]["error"] == "unsupported_format"
    (b,) = run_cli("stage", str(GENERIC / "animated.gif"), "--auto-cleanup", "--box", str(gallery))["results"]
    assert run_cli("info", "--box", str(gallery))["items"] == 1
    refused = run_cli("commit", b["ref"], "--box", str(gallery), "--auto-cleanup", expect=1)
    assert refused["problems"][0]["field"] == "license"
    assert run_cli("info", "--box", str(gallery))["items"] == 1


def test_5_commit_reports_a_cleaned_staged_file(gallery, run_cli):
    (a,) = run_cli("stage", str(GENERIC / "sticker-static.webp"), "--box", str(gallery))["results"]
    Path(a["file"]).unlink()
    out = run_cli("commit", a["ref"], "--box", str(gallery), "--license", "unknown", expect=1)
    assert out["error"] == "not_found"


@pytest.mark.parametrize("rule, params", [
    ("fields", '{"license": {"required": true}, "x": {"description": "a\\n\\n## Forged heading"}}'),
    ("categories", '{"bad name": {}}'),
    ("categories", '{"ok\\n": {}}'),
    ("files", '{"formats": {"webm": {"codecs": ["vp9`\\n## x"]}}}'),
])
def test_6_policy_text_cannot_forge_readme_structure(gallery, run_cli, rule, params):
    assert run_cli("policy", "set", rule, params, "--box", str(gallery), expect=1)["error"] == "invalid_policy"


def test_6_readme_escapes_agent_text(gallery, run_cli):
    run_cli("policy", "set", "categories", '{"tag": {"description": "<b>bold</b> | pipe `tick`"}}', "--box", str(gallery))
    readme = (gallery / "README.md").read_text()
    assert "<b>" not in readme and "&lt;b&gt;" in readme and "\\| pipe 'tick'" in readme


def _gif_blocks(data: bytes) -> tuple[bytes, list[bytes]]:
    """Header (with any global colour table) and the image blocks of a GIF."""
    flags = data[10]
    pos = 13 + (3 * 2 ** ((flags & 7) + 1) if flags & 0x80 else 0)
    head, blocks = data[:pos], []
    while data[pos] != 0x3B:
        start = pos
        if data[pos] == 0x21:
            pos += 2
        else:
            local = data[pos + 9]
            pos += 10 + (3 * 2 ** ((local & 7) + 1) if local & 0x80 else 0) + 1
        while data[pos]:
            pos += data[pos] + 1
        pos += 1
        if data[start] == 0x2C:
            blocks.append(data[start:pos])
    return head, blocks


def test_7_a_growing_gif_canvas_is_refused(tmp_path, monkeypatch):
    import io

    small, big = io.BytesIO(), io.BytesIO()
    Image.new("P", (40, 40), 1).save(small, "GIF")
    Image.new("P", (400, 400), 2).save(big, "GIF")
    head, (frame0,) = _gif_blocks(small.getvalue())
    _, (frame1,) = _gif_blocks(big.getvalue())
    path = tmp_path / "grow.gif"
    path.write_bytes(head + frame0 + frame1 + b"\x3b")
    with Image.open(path) as im:
        assert im.size == (40, 40) and im.n_frames == 2
    monkeypatch.setattr(media, "MAX_PIXELS", 2000)
    with pytest.raises(BoxError) as exc:
        media.probe(path)
    assert exc.value.code == "image_too_large"


def test_8_and_13_frame_caps_reject_rather_than_truncate(tmp_path, monkeypatch):
    path = factory.write_gif(tmp_path / "long.gif", factory.animation(2, n=12, size=(64, 64)))
    monkeypatch.setattr(media, "MAX_FRAMES", 5)
    with pytest.raises(BoxError) as exc:
        media.probe(path)
    assert exc.value.code == "too_many_frames"


def test_8_decoding_has_a_deadline(tmp_path, monkeypatch):
    path = factory.write_webm(tmp_path / "v.webm", factory.animation(2, n=12, size=(64, 64)))
    monkeypatch.setattr(media, "DECODE_SECONDS", -1.0)
    with pytest.raises(BoxError) as exc:
        media.probe(path)
    assert exc.value.code == "too_slow"


def test_9_matroska_with_another_codec_is_refused(tmp_path):
    if not shutil.which("ffmpeg"):
        pytest.skip("no ffmpeg binary")
    path = tmp_path / "m.webm"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=64x64:rate=5:duration=1",
                    "-c:v", "mjpeg", "-f", "matroska", str(path)], check=True)
    with pytest.raises(BoxError) as exc:
        media.detect(path)
    assert exc.value.code == "unsupported_format"


def test_11_decoder_errors_become_box_errors_and_leave_nothing(gallery, run_cli, tmp_path):
    bad = tmp_path / "bad.gif"
    data = (GENERIC / "animated.gif").read_bytes()
    bad.write_bytes(data[: len(data) // 3])
    out = run_cli("stage", str(bad), "--box", str(gallery), expect=1)
    assert out["results"][0]["status"] == "error"
    assert not [p for p in (gallery / "temporary").iterdir() if not p.name.startswith(".")]


def test_12_query_size_is_capped(gallery, run_cli):
    out = run_cli("search", *[f"w{i}" for i in range(17)], "x" * 100, "--box", str(gallery))
    assert out["query"].endswith("x" * 100) and "first 16 words" in out["warnings"][0]
    out = run_cli("search", f"--query={'猫' * 200}", "--box", str(gallery))
    assert "cut to 64 characters" in out["warnings"][0]
