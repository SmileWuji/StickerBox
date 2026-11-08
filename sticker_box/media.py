"""Sniffing, metadata and decoding. Stills and animated WEBP/PNG/GIF go through Pillow; WEBM is a
real video container and goes through cv2.VideoCapture, with codec and audio read from the
Matroska track headers so no ffprobe binary is needed. Every frame comes out RGB with alpha
composited onto white, the convention every analysis step relies on."""

import os
import warnings
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .errors import BoxError

MAX_FILE_BYTES = int(os.environ.get("STICKER_BOX_MAX_FILE_MB", "100")) * 1024 * 1024
MAX_PIXELS = 64_000_000
MAX_FRAMES = 3000
WORK_SIDE = 1600

Image.MAX_IMAGE_PIXELS = MAX_PIXELS


@dataclass
class MediaInfo:
    format: str
    width: int
    height: int
    animated: bool
    frames: int
    duration_ms: int | None
    fps: float | None
    codec: str | None
    audio: bool
    bytes: int

    def to_dict(self) -> dict:
        return asdict(self)


def sniff(head: bytes) -> str | None:
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if head[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if head[:4] == b"\x1a\x45\xdf\xa3":
        return "webm" if b"webm" in head[:64] else "matroska"
    return None


EXTENSIONS = {"webp": "webp", "png": "png", "jpeg": "jpg", "gif": "gif", "webm": "webm"}
WEBM_VIDEO = {"V_VP8", "V_VP9", "V_AV1"}


def _read_head(path: Path) -> bytes:
    with open(path, "rb") as fh:
        return fh.read(64)


def detect(path: Path) -> str:
    size = path.stat().st_size
    if size == 0:
        raise BoxError("empty_file", f"{path.name} is empty")
    if size > MAX_FILE_BYTES:
        raise BoxError("file_too_large", f"{path.name} is {size} bytes; the tool reads at most {MAX_FILE_BYTES}", bytes=size)
    fmt = sniff(_read_head(path))
    if fmt == "matroska":
        with open(path, "rb") as fh:
            if matroska_tracks(fh.read(1024 * 1024))["video"] in WEBM_VIDEO:
                fmt = "webm"
    if fmt not in EXTENSIONS:
        raise BoxError("unsupported_format", f"{path.name} is not WEBP, PNG, JPEG, GIF or WEBM", detected=fmt)
    return fmt


def _vint(data: bytes, pos: int, keep_marker: bool) -> tuple[int, int]:
    first = data[pos]
    length, mask = 1, 0x80
    while length <= 8 and not first & mask:
        mask >>= 1
        length += 1
    if length > 8 or pos + length > len(data):
        raise ValueError("bad vint")
    value = first if keep_marker else first & (mask - 1)
    for i in range(1, length):
        value = (value << 8) | data[pos + i]
    unknown = not keep_marker and value == (1 << (7 * length)) - 1
    return (-1 if unknown else value), length


SEGMENT, TRACKS, TRACK_ENTRY, TRACK_TYPE, CODEC_ID, CLUSTER = 0x18538067, 0x1654AE6B, 0xAE, 0x83, 0x86, 0x1F43B675


def _elements(data: bytes, start: int, end: int) -> Iterator[tuple[int, int, int]]:
    pos = start
    while pos < end:
        eid, n = _vint(data, pos, True)
        size, m = _vint(data, pos + n, False)
        body = pos + n + m
        stop = end if size < 0 else min(end, body + size)
        yield eid, body, stop
        pos = stop


def matroska_tracks(data: bytes) -> dict:
    """Codec ids and whether there is an audio track, from the headers of a WEBM file."""
    video, audio = None, []
    try:
        for eid, body, stop in _elements(data, 0, len(data)):
            if eid != SEGMENT:
                continue
            for cid, cbody, cstop in _elements(data, body, stop):
                if cid == CLUSTER:
                    break
                if cid != TRACKS:
                    continue
                for tid, tbody, tstop in _elements(data, cbody, cstop):
                    if tid != TRACK_ENTRY:
                        continue
                    kind, codec = None, None
                    for fid, fbody, fstop in _elements(data, tbody, tstop):
                        if fid == TRACK_TYPE:
                            kind = int.from_bytes(data[fbody:fstop], "big")
                        elif fid == CODEC_ID:
                            codec = data[fbody:fstop].decode("ascii", "replace").rstrip("\x00")
                    if kind == 1 and video is None:
                        video = codec
                    elif kind == 2:
                        audio.append(codec)
                break
    except (ValueError, IndexError):
        pass
    return {"video": video, "audio": audio}


def _codec_name(codec_id: str | None) -> str | None:
    if not codec_id:
        return None
    return {"V_VP9": "vp9", "V_VP8": "vp8", "V_AV1": "av1"}.get(codec_id, codec_id.removeprefix("V_").lower())


def _flatten(frame: Image.Image) -> np.ndarray:
    rgba = np.asarray(frame.convert("RGBA"), dtype=np.float32)
    alpha = rgba[:, :, 3:4] / 255.0
    rgb = rgba[:, :, :3] * alpha + 255.0 * (1.0 - alpha)
    return rgb.round().astype(np.uint8)


def _open_image(path: Path) -> Image.Image:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            im = Image.open(path)
            if im.width * im.height > MAX_PIXELS:
                raise BoxError("image_too_large", f"{path.name} is {im.width}x{im.height}; at most {MAX_PIXELS} pixels")
            return im
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise BoxError("image_too_large", f"{path.name} has too many pixels") from None
    except (OSError, SyntaxError) as err:
        raise BoxError("undecodable", f"cannot decode {path.name}: {err}") from None


def _pillow_info(path: Path, fmt: str, size: int) -> MediaInfo:
    with _open_image(path) as im:
        n = getattr(im, "n_frames", 1) or 1
        animated = bool(getattr(im, "is_animated", False)) and n > 1
        duration = None
        if animated:
            total = 0
            for i in range(min(n, MAX_FRAMES)):
                im.seek(i)
                total += int(im.info.get("duration", 0) or 0)
            duration = total
        fps = round(n * 1000 / duration, 3) if animated and duration else None
        return MediaInfo(fmt, im.width, im.height, animated, n if animated else 1, duration, fps, None, False, size)


def _video_info(path: Path, size: int) -> MediaInfo:
    with open(path, "rb") as fh:
        tracks = matroska_tracks(fh.read(1024 * 1024))
    cap = cv2.VideoCapture(str(path))
    try:
        if not cap.isOpened():
            raise BoxError("undecodable", f"cannot decode {path.name}")
        width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or None
        if width * height > MAX_PIXELS:
            raise BoxError("image_too_large", f"{path.name} is {width}x{height}; at most {MAX_PIXELS} pixels")
        frames, last_ms = 0, 0.0
        while frames < MAX_FRAMES and cap.grab():
            frames += 1
            last_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
    finally:
        cap.release()
    if frames == 0:
        raise BoxError("undecodable", f"{path.name} has no decodable frames")
    if fps:
        duration = int(round(max(last_ms, (frames - 1) * 1000 / fps) + 1000 / fps))
    else:
        duration = int(round(last_ms)) or None
    return MediaInfo("webm", width, height, frames > 1, frames, duration, round(fps, 3) if fps else None,
                     _codec_name(tracks["video"]), bool(tracks["audio"]), size)


def probe(path: Path) -> MediaInfo:
    fmt = detect(path)
    size = path.stat().st_size
    if fmt == "webm":
        return _video_info(path, size)
    return _pillow_info(path, fmt, size)


def _fit(rgb: np.ndarray, side: int) -> np.ndarray:
    h, w = rgb.shape[:2]
    if max(h, w) <= side:
        return rgb
    scale = side / max(h, w)
    return cv2.resize(rgb, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA)


def frames(path: Path, info: MediaInfo, side: int = WORK_SIDE) -> Iterator[tuple[int, int, np.ndarray]]:
    """(frame_no, t_ms, RGB uint8) for every frame, at most MAX_FRAMES, fitted within `side`."""
    if info.format == "webm":
        cap = cv2.VideoCapture(str(path))
        try:
            fps = cap.get(cv2.CAP_PROP_FPS)
            n = 0
            while n < MAX_FRAMES:
                ok, bgr = cap.read()
                if not ok:
                    break
                t_ms = cap.get(cv2.CAP_PROP_POS_MSEC)
                if t_ms == 0 and n > 0 and fps > 0:
                    t_ms = n * 1000 / fps
                yield n, int(round(t_ms)), _fit(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), side)
                n += 1
        finally:
            cap.release()
        return
    with _open_image(path) as im:
        try:
            if not info.animated:
                im.load()
                yield 0, 0, _fit(_flatten(im), side)
                return
            t = 0
            for i in range(min(info.frames, MAX_FRAMES)):
                im.seek(i)
                yield i, t, _fit(_flatten(im), side)
                t += int(im.info.get("duration", 0) or 0)
        except (OSError, SyntaxError, EOFError) as err:
            raise BoxError("undecodable", f"cannot decode {path.name}: {err}") from None
