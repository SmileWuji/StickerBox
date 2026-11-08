"""Everything the tool learns from a file without a model: identity, metadata, keyframes with
pHashes, and optionally the RapidOCR hint. `stage` stores the summary in a sidecar; `commit`
reuses it while EXTRACTOR matches."""

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from . import keyframes as kf
from . import media, ocr
from .errors import BoxError
from .phash import to_hex

EXTRACTOR = "analysis-v1"


@dataclass
class Analysis:
    sha256: str
    info: media.MediaInfo
    keyframes: list[kf.Keyframe]
    ocr: dict | None = None
    features: list = field(default_factory=list)

    @property
    def phash(self) -> int:
        return self.keyframes[0].phash

    def summary(self) -> dict:
        return {
            "sha256": self.sha256,
            "extractor": EXTRACTOR,
            "media": self.info.to_dict(),
            "phash": to_hex(self.phash),
            "keyframes": [
                {"idx": i, "frame_no": k.frame_no, "t_ms": k.t_ms, "phash": to_hex(k.phash)} for i, k in enumerate(self.keyframes)
            ],
            "ocr_hint": self.ocr,
        }

    def sheet_frames(self) -> list[tuple[int, int, int, object]]:
        return [(i, k.frame_no, k.t_ms, k.rgb) for i, k in enumerate(self.keyframes)]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def analyze(path: Path, params: dict, with_ocr: bool = False) -> Analysis:
    try:
        return _analyze(path, params, with_ocr)
    except BoxError:
        raise
    except MemoryError:
        raise BoxError("image_too_large", f"{path.name} needs more memory than is available to decode") from None
    except Exception as err:
        raise BoxError("undecodable", f"cannot decode {path.name}: {type(err).__name__}") from None


def _analyze(path: Path, params: dict, with_ocr: bool) -> Analysis:
    info = media.probe(path)
    frames = media.frames(path, info)
    if info.animated:
        kept = kf.extract(frames, params.get("keyframe_drop_thr", 0.10), params.get("max_keyframes", 64))
    else:
        kept = kf.extract(frames, 1.0, 1)
    result = Analysis(sha256_file(path), info, kept)
    if with_ocr:
        result.ocr = ocr.hint([kept[i].rgb for i in ocr.pick_frames(len(kept))])
    return result
