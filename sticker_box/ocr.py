"""RapidOCR as a hint for the agent that reads the image. The result is never written to the box
by the tool; the agent passes text to `commit` itself. The noise gate is ported from
GuidedStickerObservatory without its pack-specific watermark rule: any @handle passes, because a
watermark is attribution."""

import re

import cv2
import numpy as np

_PUNCT = re.compile(r"[\s、。，,\.!！?？~～…·・「」『』“”\"'’‘《》〈〉<>()（）【】\[\]{}\-_=+*#@^|/\\:;★♪♥]+")
HANDLE = re.compile(r"@\w{3,}")
MIN_SCORE = 0.5

_engine = None


def norm(s: str) -> str:
    return _PUNCT.sub("", (s or "").casefold())


def is_noise(text: str) -> bool:
    if HANDLE.search(text or ""):
        return False
    n = norm(text)
    if not n:
        return True
    digits = sum(ch.isdigit() for ch in n)
    if digits / len(n) >= 0.6:
        return True
    cjk = sum(1 for ch in n if "一" <= ch <= "鿿" or "぀" <= ch <= "ヿ" or "가" <= ch <= "힣")
    if cjk >= 3:
        return False
    if len(n) <= 2:
        return True
    return cjk == 0 and len(n) <= 6


def _get_engine():
    global _engine
    if _engine is None:
        import logging

        from rapidocr_onnxruntime import RapidOCR

        _engine = RapidOCR()
        logging.getLogger("RapidOCR").setLevel(logging.ERROR)
    return _engine


def _lines(rgb: np.ndarray) -> list[str]:
    result, _ = _get_engine()(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    if not result:
        return []
    boxes = []
    for box, text, score in result:
        if float(score) < MIN_SCORE or not str(text).strip():
            continue
        ys = [p[1] for p in box]
        xs = [p[0] for p in box]
        boxes.append((min(ys), min(xs), max(ys) - min(ys), str(text).strip()))
    boxes.sort(key=lambda b: (round(b[0] / max(1.0, b[2] * 0.6)), b[1]))
    return [b[3] for b in boxes]


def hint(images: list[np.ndarray]) -> dict:
    """Text RapidOCR finds on the given frames, lines merged in reading order without repeats."""
    seen, lines = set(), []
    for rgb in images:
        for line in _lines(rgb):
            key = norm(line)
            if key and key not in seen:
                seen.add(key)
                lines.append(line)
    text = " ".join(" ".join(lines).split())
    return {"text": text, "noise": is_noise(text), "engine": "rapidocr"}


def pick_frames(count: int, limit: int = 3) -> list[int]:
    if count <= limit:
        return list(range(count))
    return sorted({0, count // 2, count - 1})
