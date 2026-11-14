"""64-bit DCT perceptual hash, ported from GuidedStickerBootCamp. Stored hashes are compared
across a whole box, so the resize, transform, median rule and bit packing are frozen; the known
vector in tests/test_phash.py pins them. cv2.dct is the orthonormal DCT-II, identical to the
scipy `dct(..., norm="ortho")` pair BootCamp used."""

import numpy as np

from .opencv import cv2


def bits64(rgb: np.ndarray) -> np.ndarray:
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    small = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
    c = cv2.dct(small)[:8, :8]
    return (c > np.median(c)).flatten()


def to_int(bits: np.ndarray) -> int:
    return int.from_bytes(np.packbits(bits).tobytes(), "big")


def phash(rgb: np.ndarray) -> int:
    return to_int(bits64(rgb))


def to_hex(value: int) -> str:
    return f"{value:016x}"


def distance(a: int, b: int) -> int:
    return ((a ^ b) & 0xFFFFFFFFFFFFFFFF).bit_count()


def distances(query: int, values: np.ndarray) -> np.ndarray:
    """Hamming distance from one hash to an array of unsigned 64-bit hashes."""
    x = np.bitwise_xor(values.astype(np.uint64), np.uint64(query & 0xFFFFFFFFFFFFFFFF))
    return np.bitwise_count(x).astype(np.int32)


def norm_hamming(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(a != b))
