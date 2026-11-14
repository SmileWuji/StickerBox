from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

import factory
from sticker_box import analysis, contact, keyframes, media, ocr, phash
from sticker_box.errors import BoxError

GENERIC = Path(__file__).resolve().parent.parent / "testdata" / "generic"


def gradient_with_square() -> np.ndarray:
    x = np.linspace(0, 255, 64).astype(np.uint8)
    rgb = np.repeat(np.tile(x, (64, 1))[..., None], 3, axis=2).copy()
    rgb[8:24, 8:24] = 20
    return rgb


def test_phash_known_vector_matches_bootcamp():
    assert phash.to_hex(phash.phash(gradient_with_square())) == "a83c00c3c3c3003c"


def test_phash_survives_recompression_and_resize():
    rgb = factory.picture(7)[:, :, :3]
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 40])
    small = cv2.resize(cv2.imdecode(buf, cv2.IMREAD_COLOR), (200, 200))
    again = phash.phash(cv2.cvtColor(small, cv2.COLOR_BGR2RGB))
    assert phash.distance(phash.phash(rgb), again) <= 6
    assert phash.distance(phash.phash(rgb), phash.phash(factory.picture(8)[:, :, :3])) > 12


def test_vectorised_distances_agree():
    values = [phash.phash(factory.picture(i)[:, :, :3]) for i in range(5)]
    got = phash.distances(values[0], np.array(values, dtype=np.uint64))
    assert list(got) == [phash.distance(values[0], v) for v in values]


def test_keyframes_collapse_identical_and_cap():
    a, b = factory.picture(1)[:, :, :3], factory.picture(2)[:, :, :3]
    assert len(keyframes.extract([(0, 0, a), (1, 10, a), (2, 20, a)], 0.10, 64)) == 1
    alternating = [(i, i * 10, a if i % 2 else b) for i in range(10)]
    assert len(keyframes.extract(alternating, 0.10, 64)) == 10
    capped = keyframes.extract(alternating, 0.10, 4)
    assert len(capped) == 4 and capped[0].frame_no == 0
    assert [k.frame_no for k in capped] == sorted(k.frame_no for k in capped)


def test_sniff():
    assert media.sniff(b"RIFF\0\0\0\0WEBPVP8 ") == "webp"
    assert media.sniff(b"\x89PNG\r\n\x1a\n") == "png"
    assert media.sniff(b"\xff\xd8\xff\xe0") == "jpeg"
    assert media.sniff(b"GIF89a") == "gif"
    assert media.sniff(b"\x1a\x45\xdf\xa3" + b"\x00" * 20 + b"webm") == "webm"
    assert media.sniff(b"hello") is None


@pytest.mark.parametrize(
    "name, fmt, animated, size",
    [
        ("sticker-static.webp", "webp", False, (512, 512)),
        ("sticker-wide.webp", "webp", False, (512, 320)),
        ("sticker-video.webm", "webm", True, (512, 512)),
        ("oversize.png", "png", False, (800, 600)),
        ("photo-with-text.jpg", "jpeg", False, (640, 480)),
        ("animated.webp", "webp", True, (256, 256)),
        ("animated.gif", "gif", True, (200, 200)),
    ],
)
def test_probe_generic_files(name, fmt, animated, size):
    info = media.probe(GENERIC / name)
    assert (info.format, info.animated, (info.width, info.height)) == (fmt, animated, size)
    if fmt == "webm":
        assert info.codec == "vp9" and info.audio is False and info.frames == 24 and info.fps == 24
        assert 900 <= info.duration_ms <= 1100


def test_webm_with_audio_is_detected(tmp_path):
    path = factory.write_webm_with_audio(tmp_path / "a.webm", factory.animation(3, n=8, size=(128, 128)))
    if path is None:
        pytest.skip("no ffmpeg binary")
    assert media.probe(path).audio is True


def test_animated_png_is_animated(tmp_path):
    frames = [Image.fromarray(f, "RGBA") for f in factory.animation(5, n=4, size=(64, 64))]
    frames[0].save(tmp_path / "a.png", save_all=True, append_images=frames[1:], duration=100)
    info = media.probe(tmp_path / "a.png")
    assert info.animated and info.frames == 4 and info.duration_ms == 400


def test_alpha_is_composited_onto_white(tmp_path):
    rgba = np.zeros((32, 32, 4), np.uint8)
    path = factory.write_webp(tmp_path / "t.webp", rgba)
    info = media.probe(path)
    (_, _, rgb), = list(media.frames(path, info))
    assert rgb.min() >= 250


@pytest.mark.parametrize("content, code", [(b"", "empty_file"), (b"hello world", "unsupported_format"), (b"RIFF\0\0\0\0WEBPjunkjunk", "undecodable")])
def test_bad_files_raise_box_errors(tmp_path, content, code):
    path = tmp_path / "bad"
    path.write_bytes(content)
    with pytest.raises(BoxError) as exc:
        media.probe(path)
    assert exc.value.code == code


def test_pixel_cap(tmp_path, monkeypatch):
    path = factory.write_png(tmp_path / "big.png", factory.picture(1, (300, 300)))
    monkeypatch.setattr(media, "MAX_PIXELS", 1000)
    with pytest.raises(BoxError) as exc:
        media.probe(path)
    assert exc.value.code == "image_too_large"


def test_matroska_doctype_with_vp9_counts_as_webm(tmp_path):
    import shutil
    import subprocess

    if not shutil.which("ffmpeg"):
        pytest.skip("no ffmpeg binary")
    path = tmp_path / "m.webm"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-i", str(GENERIC / "sticker-video.webm"), "-c", "copy", "-f", "matroska", str(path)], check=True)
    assert media.sniff(path.read_bytes()[:64]) == "matroska"
    assert media.detect(path) == "webm" and media.probe(path).codec == "vp9"


def test_matroska_track_scan_handles_garbage():
    assert media.matroska_tracks(b"\x1a\x45\xdf\xa3\xff\xff") == {"video": None, "audio": []}


@pytest.mark.parametrize(
    "text, noise",
    [("", True), ("a", True), ("12 34 56", True), ("ok", True), ("abcdef", True), ("@someone", False),
     ("今天下雨", False), ("hello world", False), ("去睡觉", False)],
)
def test_noise_gate(text, noise):
    assert ocr.is_noise(text) is noise


def test_ocr_hint_reads_generated_text():
    result = analysis.analyze(GENERIC / "photo-with-text.jpg", {}, with_ocr=True)
    assert "HELLO" in result.ocr["text"].upper() and result.ocr["noise"] is False


def test_contact_sheet_tiles_keyframes(tmp_path):
    result = analysis.analyze(GENERIC / "sticker-video.webm", {"keyframe_drop_thr": 0.10, "max_keyframes": 64})
    rgb = contact.sheet(result.sheet_frames())
    out = contact.write(rgb, tmp_path / "sheet.jpg")
    assert out.is_file() and rgb.shape[1] > 256 and len(result.keyframes) > 1


def test_frames_command_writes_into_the_box(tmp_path, run_cli):
    run_cli("init", str(tmp_path / "b"), "--preset", "gallery", "--language", "en")
    out = run_cli("frames", str(GENERIC / "animated.gif"), "--box", str(tmp_path / "b"))
    assert Path(out["sheet"]).parent == (tmp_path / "b" / "temporary").resolve() and out["animated"] is True


@pytest.mark.private
def test_private_corpus_sample_analyses(private_data):
    files = [p for src in private_data for p in sorted(src.rglob("*")) if p.suffix in (".webp", ".webm")][:: max(1, 1)]
    sample = files[:: max(1, len(files) // 40)][:40]
    for path in sample:
        result = analysis.analyze(path, {"keyframe_drop_thr": 0.10, "max_keyframes": 64})
        assert result.keyframes


def test_opencv_error_names_the_gui_build_to_remove():
    from sticker_box import opencv

    err = opencv.explain(ImportError("libxcb.so.1: cannot open shared object file"), installed=lambda name: True)
    assert err.code == "opencv_unavailable"
    assert "libxcb" in err.message and "pip uninstall -y opencv-python opencv-contrib-python" in err.message
    plain = opencv.explain(ImportError("no module"), installed=lambda name: False)
    assert plain.details["gui_builds"] == [] and "opencv-python-headless" in plain.message


def test_a_broken_cv2_gives_the_opencv_error_on_every_path(tmp_path):
    import json
    import os
    import subprocess
    import sys

    (tmp_path / "cv2.py").write_text("raise ImportError('libxcb.so.1: cannot open shared object file')\n")
    env = {**os.environ, "PYTHONPATH": f"{tmp_path}{os.pathsep}{os.environ.get('PYTHONPATH', '')}"}
    for argv in (["analyze", str(GENERIC / "animated.gif")], ["frames", str(GENERIC / "animated.gif")]):
        done = subprocess.run([sys.executable, "-m", "sticker_box", *argv, "--json"], capture_output=True, text=True, env=env, cwd=tmp_path)
        assert json.loads(done.stdout)["error"] == "opencv_unavailable", done.stdout


def test_the_cli_maps_any_cv2_import_error():
    from sticker_box.cli import unexpected

    assert unexpected(ImportError("libGL.so.1: cannot open shared object file")).code == "opencv_unavailable"
    assert unexpected(ImportError("no module named foo")).code == "internal"
