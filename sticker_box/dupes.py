"""Near-duplicates by perceptual hash, over every stored item's keyframes (a still has one).
Classifies each match by what is matched against what, so a still cut from an animation is linked
to it rather than called a duplicate."""

import math
import sqlite3

import numpy as np

from . import db

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


SAME_PICTURE = {"near_duplicate", "duplicate"}


def _remove(box, ref: str) -> str:
    import shlex

    return f"sticker-box remove {ref[:12]} --box {shlex.quote(str(box.root))}"


def suggest(box, new_ref: str, new_media: dict, match: dict, staged: bool) -> list[dict]:
    """Ready-to-run commands for a reported match, likelier choice first. The tool never runs
    them; whoever added the image decides."""
    row = box.conn.execute("SELECT width, height, bytes, animated FROM item WHERE sha256 = ?", (match["ref"],)).fetchone()
    if row is None:
        return []
    drop_new = {"command": _remove(box, new_ref),
                "effect": "drop this new image, keep the stored one" if staged else "remove the image just added, keep the older one"}
    drop_old = {"command": _remove(box, match["ref"]),
                "effect": ("remove the stored image; commit this one first to keep it instead" if staged
                           else "remove the older image, keep the one just added")}
    if match["kind"] not in SAME_PICTURE:
        drop_new["effect"] += f" (only if it shows the same thing: this is `{match['kind']}`, not an identical picture)"
        return [drop_new]
    new_quality = (new_media["width"] * new_media["height"], bool(new_media["animated"]), new_media["bytes"])
    old_quality = (row["width"] * row["height"], bool(row["animated"]), row["bytes"])
    return [drop_old, drop_new] if new_quality > old_quality else [drop_new, drop_old]


def _edge_summary(kind: str, method: str, score, transform: str | None) -> str:
    if method == "sift" and transform:
        import json

        from . import features

        return features.summary(kind, json.loads(transform)) + f" ({int(score)} matching points)"
    return f"{kind.replace('_', ' ')} (pHash distance {int(score)})" if score is not None else kind


def clusters(box, kinds: set[str] | None = None) -> list[dict]:
    """Groups of items linked by relations, each with a suggested keeper: the largest, then the oldest."""
    conn = box.conn
    rels = [r for r in conn.execute("SELECT a, b, kind, method, score, transform FROM relation") if not kinds or r["kind"] in kinds]
    parent: dict[str, str] = {}

    def root(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for r in rels:
        parent[root(r["a"])] = root(r["b"])
    groups: dict[str, list[str]] = {}
    for x in list(parent):
        groups.setdefault(root(x), []).append(x)
    out = []
    for members in groups.values():
        if len(members) < 2:
            continue
        rows = [conn.execute("SELECT sha256, file, width, height, bytes, added_at, animated FROM item WHERE sha256 = ?", (m,)).fetchone() for m in members]
        rows = [r for r in rows if r is not None]
        keeper = max(rows, key=lambda r: (r["width"] * r["height"], r["animated"], [-ord(c) for c in r["added_at"]]))
        member_set = {r["sha256"] for r in rows}
        from . import paths

        out.append({
            "keeper": keeper["sha256"],
            "members": [{"ref": r["sha256"], "file": paths.safe_stored_str(box, r), "size": f"{r['width']}x{r['height']}",
                         "bytes": r["bytes"], "added_at": r["added_at"], "animated": bool(r["animated"])} for r in rows],
            "links": [{"a": r["a"], "b": r["b"], "kind": r["kind"], "how": _edge_summary(r["kind"], r["method"], r["score"], r["transform"])}
                      for r in rels if r["a"] in member_set],
            "suggested": [{"command": _remove(box, r["sha256"]), "effect": "keep the suggested keeper, remove this one"}
                          for r in rows if r["sha256"] != keeper["sha256"]],
        })
    out.sort(key=lambda c: -len(c["members"]))
    return out


def reindex(box) -> dict:
    """Rebuild keyframes, features and relations from the stored files, oldest first, so every
    relation points from a newer item to an older one, as at commit. Each item is replaced in its
    own transaction, so a failure or an interruption leaves the rest of the box as it was; failed
    items are reported and keep their old data."""
    import json

    from . import analysis, clock, features, paths
    from .errors import BoxError

    conn = box.conn
    policy = box.policy()
    sift = policy["duplicates"]["sift"]
    rows = conn.execute("SELECT sha256, file, animated, width, height FROM item ORDER BY added_at, sha256").fetchall()
    done: set[str] = set()
    counts = {"items": 0, "relations": 0, "with_features": 0, "incomplete_matching": 0, "failed": []}
    for row in rows:
        sha = row["sha256"]
        try:
            result = analysis.analyze(paths.stored_path(box, row), policy["analysis"])
        except BoxError as err:
            counts["failed"].append({"ref": sha, "error": err.code, "message": err.message})
            continue
        hashes = [k.phash for k in result.keyframes]
        matches = [m for m in find(conn, hashes, bool(row["animated"]), policy["duplicates"]["phash_max_distance"], exclude=sha) if m["ref"] in done]
        sets = features.compute(result, policy) if sift else []
        if sift:
            seen = {m["ref"] for m in matches}
            found, complete = features.match(conn, sets, (row["width"], row["height"]), sift, exclude=sha, only=done)
            matches += [m for m in found if m["ref"] not in seen]
            counts["incomplete_matching"] += not complete
        stamp = clock.stamp()
        with db.transaction(conn):
            if conn.execute("SELECT 1 FROM item WHERE sha256 = ?", (sha,)).fetchone() is None:
                continue
            conn.execute("DELETE FROM keyframe WHERE sha256 = ?", (sha,))
            conn.execute("DELETE FROM feature WHERE sha256 = ?", (sha,))
            conn.execute("DELETE FROM relation WHERE a = ?", (sha,))
            conn.executemany("INSERT INTO keyframe (sha256, idx, frame_no, t_ms, phash) VALUES (?, ?, ?, ?, ?)",
                             [(sha, i, k.frame_no, k.t_ms, db.to_signed(k.phash)) for i, k in enumerate(result.keyframes)])
            conn.execute("UPDATE item SET phash = ? WHERE sha256 = ?", (db.to_signed(result.phash), sha))
            conn.executemany("INSERT INTO feature (sha256, frame, extractor, n, kp, desc) VALUES (?, ?, ?, ?, ?, ?)",
                             [(sha, idx, features.EXTRACTOR, int(kp.shape[0]), kp.astype(np.float32).tobytes(), desc.tobytes()) for idx, kp, desc in sets])
            conn.executemany(
                "INSERT OR REPLACE INTO relation (a, b, kind, method, score, transform, found_at) "
                "SELECT ?, ?, ?, ?, ?, ?, ? WHERE EXISTS (SELECT 1 FROM item WHERE sha256 = ?)",
                [(sha, m["ref"], m["kind"], m.get("method", "phash"), m.get("distance", m.get("inliers")),
                  json.dumps(m["transform"]) if m.get("transform") else None, stamp, m["ref"]) for m in matches],
            )
        done.add(sha)
        counts["items"] += 1
        counts["relations"] += len(matches)
        counts["with_features"] += bool(sets)
    return counts
