"""Perceptual dedup of an animation, ported from GuidedStickerBootCamp: keep a frame when its pHash
differs from the last kept frame by more than drop_thr (normalized Hamming). Frame 0 is always
kept. Over max_keyframes, keep frame 0 plus the frames that changed most from their predecessor
(ties to the earlier frame), restored to source order; that is where the animation moves."""

from collections.abc import Iterable
from dataclasses import dataclass

import numpy as np

from .phash import bits64, norm_hamming, to_int


@dataclass
class Keyframe:
    frame_no: int
    t_ms: int
    rgb: np.ndarray
    bits: np.ndarray
    dist: float

    @property
    def phash(self) -> int:
        return to_int(self.bits)


def extract(frames: Iterable[tuple[int, int, np.ndarray]], drop_thr: float, max_keyframes: int) -> list[Keyframe]:
    kept: list[Keyframe] = []
    for frame_no, t_ms, rgb in frames:
        bits = bits64(rgb)
        dist = norm_hamming(bits, kept[-1].bits) if kept else 0.0
        if not kept or dist > drop_thr:
            kept.append(Keyframe(frame_no, t_ms, rgb, bits, dist))
    if len(kept) > max_keyframes:
        rest = sorted(kept[1:], key=lambda k: (-k.dist, k.frame_no))[: max_keyframes - 1]
        kept = [kept[0]] + sorted(rest, key=lambda k: k.frame_no)
    return kept
