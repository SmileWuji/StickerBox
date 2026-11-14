"""A contact sheet: the keyframes of an animation tiled into one labelled image, so a model with
no video input can read the whole animation in a single image call."""

import math
import uuid
from pathlib import Path

from .opencv import cv2
import numpy as np

LABEL_H = 28
GAP = 6


def sheet(keyframes: list[tuple[int, int, int, np.ndarray]], cell: int | None = None, cols: int | None = None) -> np.ndarray:
    """keyframes: (index, frame_no, t_ms, RGB). Returns RGB."""
    n = len(keyframes)
    cell = cell or (256 if n <= 16 else 192)
    cols = cols or min(8, max(1, math.ceil(math.sqrt(n))))
    rows = math.ceil(n / cols)
    width = cols * cell + (cols + 1) * GAP
    height = rows * (cell + LABEL_H) + (rows + 1) * GAP
    out = np.full((height, width, 3), 255, np.uint8)
    for i, (idx, frame_no, t_ms, rgb) in enumerate(keyframes):
        r, c = divmod(i, cols)
        x0 = GAP + c * (cell + GAP)
        y0 = GAP + r * (cell + LABEL_H + GAP)
        h, w = rgb.shape[:2]
        scale = cell / max(h, w)
        small = cv2.resize(rgb, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA)
        sh, sw = small.shape[:2]
        ox, oy = x0 + (cell - sw) // 2, y0 + (cell - sh) // 2
        out[oy:oy + sh, ox:ox + sw] = small
        cv2.rectangle(out, (x0 - 1, y0 - 1), (x0 + cell, y0 + cell), (200, 200, 200), 1)
        label = f"#{idx}  frame {frame_no}  {t_ms / 1000:.2f}s"
        cv2.putText(out, label, (x0 + 2, y0 + cell + LABEL_H - 9), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)
    return out


def write(rgb: np.ndarray, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp.jpg")
    cv2.imwrite(str(tmp), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90])
    tmp.replace(path)
    return path
