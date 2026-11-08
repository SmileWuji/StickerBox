"""Near-duplicates by perceptual hash, over every stored item's keyframes (a still has one).
Classifies each match by what is matched against what, so a still cut from an animation is linked
to it rather than called a duplicate."""

import math
import sqlite3

import numpy as np

from . import db
from .phash import to_hex

DEGENERATE_BITS = 4


def _usable(value: int) -> bool:
    bits = (value & 0xFFFFFFFFFFFFFFFF).bit_count()
    return DEGENERATE_BITS < bits < 64 - DEGENERATE_BITS


def find(conn: sqlite3.Connection, hashes: list[int], animated: bool, max_distance: int, exclude: str | None = None) -> list[dict]:
    """hashes: the new image's keyframe pHashes, frame 0 first. Returns one match per stored item:
    {ref, kind, distance}; kind is near_duplicate, frame_of (the new still is a frame of that
    animation), has_frame (that still is a frame of the new animation) or shares_frames."""
    rows = conn.execute(
        "SELECT k.sha256, k.idx, k.phash, i.animated FROM keyframe k JOIN item i ON i.sha256 = k.sha256"
    ).fetchall()
    if not rows or not hashes:
        return []
    owners = [r["sha256"] for r in rows]
    idxs = np.array([r["idx"] for r in rows])
    values = np.array([db.to_unsigned(r["phash"]) for r in rows], dtype=np.uint64)
    owner_animated = {r["sha256"]: bool(r["animated"]) for r in rows}
    hits: dict[str, list[tuple[int, int, int]]] = {}
    for a_idx, h in enumerate(hashes):
        if not _usable(h):
            continue
        x = np.bitwise_xor(values, np.uint64(h & 0xFFFFFFFFFFFFFFFF))
        dist = np.bitwise_count(x)
        for j in np.nonzero(dist <= max_distance)[0]:
            if owners[j] == exclude or not _usable(int(values[j])):
                continue
            hits.setdefault(owners[j], []).append((a_idx, int(idxs[j]), int(dist[j])))
    out = []
    for sha, matches in hits.items():
        best = min(d for _, _, d in matches)
        if not animated and not owner_animated[sha]:
            kind = "near_duplicate"
        elif not animated:
            kind = "frame_of"
        elif not owner_animated[sha]:
            kind = "has_frame"
        else:
            first = [d for a, b, d in matches if a == 0 and b == 0]
            if first:
                kind, best = "near_duplicate", min(first)
            elif len({a for a, _, _ in matches}) >= max(2, math.ceil(0.3 * len(hashes))):
                kind = "shares_frames"
            else:
                continue
        out.append({"ref": sha, "kind": kind, "distance": best})
    out.sort(key=lambda m: (m["kind"] != "near_duplicate", m["distance"], m["ref"]))
    return out


def hex_hashes(summary: dict) -> list[int]:
    return [int(k["phash"], 16) for k in summary["keyframes"]]


__all__ = ["find", "hex_hashes", "to_hex"]
