"""Synthetic images for tests and for testdata/generic. Everything is drawn from a seed, so the
same call always gives the same pixels, and nothing here comes from a third party."""

import shutil
import subprocess
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def picture(seed: int, size: tuple[int, int] = (512, 512), alpha: bool = False, text: str | None = None) -> np.ndarray:
    """RGBA uint8 (alpha all 255 unless alpha=True, which leaves a transparent background)."""
    w, h = size
    rng = np.random.default_rng(seed)
    bg = rng.integers(0, 256, 3)
    img = np.zeros((h, w, 4), np.uint8)
    img[:, :, :3] = bg
    img[:, :, 3] = 0 if alpha else 255
    for _ in range(int(rng.integers(6, 12))):
        color = [int(c) for c in rng.integers(0, 256, 3)] + [255]
        kind = rng.integers(0, 3)
        cx, cy = int(rng.integers(0, w)), int(rng.integers(0, h))
        r = int(rng.integers(min(w, h) // 12, min(w, h) // 4))
        if kind == 0:
            cv2.circle(img, (cx, cy), r, color, -1)
        elif kind == 1:
            cv2.rectangle(img, (cx - r, cy - r // 2), (cx + r, cy + r // 2), color, -1)
        else:
            pts = rng.integers(0, [w, h], (5, 2)).astype(np.int32)
            cv2.fillPoly(img, [pts], color)
    for _ in range(40):
        p1 = tuple(int(v) for v in rng.integers(0, [w, h]))
        p2 = tuple(int(v) for v in rng.integers(0, [w, h]))
        color = [int(c) for c in rng.integers(0, 256, 3)] + [255]
        cv2.line(img, p1, p2, color, int(rng.integers(1, 4)))
    if text:
        scale = max(w, h) / 400
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, 3)
        x, y = max(4, (w - tw) // 2), h - max(8, th)
        cv2.rectangle(img, (x - 8, y - th - 12), (x + tw + 8, y + 12), (255, 255, 255, 255), -1)
        cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0, 255), 3, cv2.LINE_AA)
    return img


def animation(seed: int, n: int = 12, size: tuple[int, int] = (512, 512)) -> list[np.ndarray]:
    """A static scene with a disc that moves across it, RGBA frames."""
    base = picture(seed, size)
    w, h = size
    frames = []
    for i in range(n):
        frame = base.copy()
        x = int(w * (0.15 + 0.7 * i / max(1, n - 1)))
        cv2.circle(frame, (x, h // 2), min(w, h) // 6, (255, 255, 255, 255), -1)
        cv2.circle(frame, (x, h // 2), min(w, h) // 10, (20, 20, 200, 255), -1)
        frames.append(frame)
    return frames


def _pil(rgba: np.ndarray) -> Image.Image:
    return Image.fromarray(rgba, "RGBA")


def write_png(path: Path, rgba: np.ndarray) -> Path:
    _pil(rgba).save(path, "PNG")
    return path


def write_jpg(path: Path, rgba: np.ndarray, quality: int = 90) -> Path:
    _pil(rgba).convert("RGB").save(path, "JPEG", quality=quality)
    return path


def write_webp(path: Path, rgba: np.ndarray, quality: int = 90) -> Path:
    _pil(rgba).save(path, "WEBP", quality=quality)
    return path


def write_animated_webp(path: Path, frames: list[np.ndarray], duration_ms: int = 80) -> Path:
    images = [_pil(f) for f in frames]
    images[0].save(path, "WEBP", save_all=True, append_images=images[1:], duration=duration_ms, loop=0, quality=85)
    return path


def write_gif(path: Path, frames: list[np.ndarray], duration_ms: int = 80) -> Path:
    images = [_pil(f).convert("RGB") for f in frames]
    images[0].save(path, "GIF", save_all=True, append_images=images[1:], duration=duration_ms, loop=0)
    return path


def write_webm(path: Path, frames: list[np.ndarray], fps: int = 15) -> Path:
    h, w = frames[0].shape[:2]
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"VP90"), fps, (w, h))
    for f in frames:
        writer.write(cv2.cvtColor(f, cv2.COLOR_RGBA2BGR))
    writer.release()
    return path


def write_webm_with_audio(path: Path, frames: list[np.ndarray], fps: int = 15) -> Path | None:
    """Needs the ffmpeg binary; returns None when it is missing."""
    if not shutil.which("ffmpeg"):
        return None
    silent = path.with_suffix(".silent.webm")
    write_webm(silent, frames, fps)
    subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-y", "-i", str(silent), "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-c:v", "copy", "-c:a", "libopus", "-shortest", str(path)],
        check=True,
    )
    silent.unlink()
    return path
