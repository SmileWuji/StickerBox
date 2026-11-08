"""Perceptual dedup of an animation, ported from GuidedStickerBootCamp: keep a frame when its pHash
differs from the last kept frame by more than drop_thr (normalized Hamming). Frame 0 is always
kept. Over max_keyframes, keep frame 0 plus the frames that changed most from their predecessor
(ties to the earlier frame), restored to source order; that is where the animation moves.

The selection is made while streaming: only frame 0 and the current best max_keyframes - 1 hold
pixels, so memory stays bounded however long the animation is. The result is the same as
keeping every changed frame and trimming at the end, as BootCamp did."""

import heapq
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
    first: Keyframe | None = None
    last_bits: np.ndarray | None = None
    best: list[tuple[float, int, Keyframe]] = []
    room = max_keyframes - 1
    for frame_no, t_ms, rgb in frames:
        bits = bits64(rgb)
        if first is None:
            first = Keyframe(frame_no, t_ms, rgb, bits, 0.0)
            last_bits = bits
            continue
        dist = norm_hamming(bits, last_bits)
        if dist <= drop_thr:
            continue
        last_bits = bits
        if room <= 0:
            continue
        entry = (dist, -frame_no, Keyframe(frame_no, t_ms, rgb, bits, dist))
        if len(best) < room:
            heapq.heappush(best, entry)
        elif entry[:2] > best[0][:2]:
            heapq.heapreplace(best, entry)
    if first is None:
        return []
    return [first] + sorted((k for _, _, k in best), key=lambda k: k.frame_no)
