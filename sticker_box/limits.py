"""Limits, expiry and cleanup. Nothing is removed implicitly: a write over a limit fails with exit
code 3 unless the caller passed --auto-cleanup, and `clean` is the only other path that deletes."""

import time

from . import clock, db
from .errors import EXIT_LIMIT, BoxError


def usage(conn) -> tuple[int, int]:
    row = conn.execute("SELECT COUNT(*) AS n, COALESCE(SUM(bytes), 0) AS b FROM item").fetchone()
    return row["n"], row["b"]


def _fits(lim: dict, count: int, size: int) -> bool:
    return (not lim["max_items"] or count <= lim["max_items"]) and (not lim["max_bytes"] or size <= lim["max_bytes"])


def plan_room(box, policy: dict, add_bytes: int, add_items: int, auto: bool) -> list[str]:
    """Items to remove so the write fits, or [] when it already does. Raises when it does not fit
    and auto is off, or when even removing everything would not make room."""
    lim = policy["limits"]
    if not lim["max_bytes"] and not lim["max_items"]:
        return []
    count, size = usage(box.conn)
    if _fits(lim, count + add_items, size + add_bytes):
        return []
    state = {"items": count, "bytes": size, "max_items": lim["max_items"], "max_bytes": lim["max_bytes"], "adding_bytes": add_bytes}
    if not auto:
        raise BoxError(
            "limit_exceeded",
            "this write would put the box over its limit; run `sticker-box clean` to remove expired items, "
            "or retry with --auto-cleanup to remove expired items and then the oldest ones",
            exit_code=EXIT_LIMIT, **state,
        )
    now = clock.stamp()
    rows = box.conn.execute(
        "SELECT sha256, bytes, expires_at IS NOT NULL AND expires_at <= ? AS expired FROM item ORDER BY expired DESC, COALESCE(expires_at, added_at), added_at",
        (now,),
    ).fetchall()
    chosen = []
    for row in rows:
        if _fits(lim, count + add_items, size + add_bytes):
            break
        chosen.append(row["sha256"])
        count -= 1
        size -= row["bytes"]
    if not _fits(lim, count + add_items, size + add_bytes):
        raise BoxError("limit_exceeded", "the file alone is larger than the box's limit", exit_code=EXIT_LIMIT, **state)
    return chosen


def remove_items(box, shas: list[str], reason: str) -> list[dict]:
    removed = []
    for sha in shas:
        row = box.conn.execute("SELECT file, added_at, expires_at FROM item WHERE sha256 = ?", (sha,)).fetchone()
        if row is None:
            continue
        with db.transaction(box.conn):
            box.conn.execute("DELETE FROM item WHERE sha256 = ?", (sha,))
        (box.root / row["file"]).unlink(missing_ok=True)
        removed.append({"ref": sha, "reason": reason, "added_at": row["added_at"], "expires_at": row["expires_at"]})
    return removed


def expired(box) -> list[str]:
    return [r["sha256"] for r in box.conn.execute(
        "SELECT sha256 FROM item WHERE expires_at IS NOT NULL AND expires_at <= ? ORDER BY expires_at", (clock.stamp(),))]


def clean(box, everything: bool = False) -> dict:
    policy = box.policy()
    grace = policy["retention"]["staged_grace_minutes"] * 60
    cutoff = time.time() - grace
    files = []
    for path in sorted(box.temporary.iterdir()):
        if not path.is_file():
            continue
        if everything or path.stat().st_mtime <= cutoff:
            path.unlink(missing_ok=True)
            files.append(path.name)
    removed = remove_items(box, expired(box), "expired")
    if removed:
        box.write_readme()
    staged = sorted({name.split(".", 1)[0] for name in files if name.endswith(".json")})
    return {"staged_removed": staged, "temporary_files_removed": len(files), "expired_removed": removed}
