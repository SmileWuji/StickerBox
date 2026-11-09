"""Every path the tool reads, moves or deletes inside a box is derived here from a 64-hex sha256
and a known extension, never taken from a sidecar, a database row or a symlink. Anyone who can
write into temporary/ or box.sqlite3 could otherwise point the tool at any file on the system."""

import re
from pathlib import Path

from .errors import BoxError

SHA = re.compile(r"[0-9a-f]{64}")
EXTS = ("webp", "png", "jpg", "gif", "webm")
STORED = re.compile(r"persistent/(\d{6})/(\d{8})-([0-9a-f]{64})\.(webp|png|jpg|gif|webm)")


def check_sha(sha: str) -> str:
    if not isinstance(sha, str) or not SHA.fullmatch(sha):
        raise BoxError("invalid_ref", "not a full sha256")
    return sha


def staged_name(sha: str, ext: str) -> str:
    check_sha(sha)
    if ext not in EXTS:
        raise BoxError("corrupt_staging", f"unknown extension {ext!r}")
    return f"{sha}.{ext}"


def stored_rel(row) -> str | None:
    """The row's stored path if it is one the tool writes for that sha256, else None."""
    file, sha = row["file"], row["sha256"]
    m = STORED.fullmatch(file or "")
    return file if m and m.group(3) == sha else None


def stored_path(box, row) -> Path:
    rel = stored_rel(row)
    if rel is None:
        raise BoxError("corrupt_index", f"item {row['sha256'][:12]} has a file path the tool never writes ({row['file']!r}); run `sticker-box check`")
    path = box.root / rel
    if (box.persistent / rel.split("/")[1]).is_symlink() or path.is_symlink():
        raise BoxError("corrupt_index", f"item {row['sha256'][:12]} is stored through a symbolic link; run `sticker-box check`")
    return path


def safe_stored_str(box, row) -> str | None:
    try:
        return str(stored_path(box, row))
    except BoxError:
        return None
