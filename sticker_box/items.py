"""Stored items: commit from staging, show, edit, remove. Every check runs before anything is
written, and all failures are returned together."""

import json
import os
import sqlite3

from . import analysis, clock, db, dupes, paths, refs, rules, stage, vocab
from .errors import BoxError
from .phash import to_hex

LIMITS = {"license": 200, "source": 1000, "text": 4000, "description": 4000, "note": 2000}
FIELD_LIMIT = 2000
CORE = ("license", "source", "text", "description", "note")
INVERSE = {"frame_of": "has_frame", "has_frame": "frame_of", "crop_of": "contains", "contains": "crop_of"}


def field_problems(policy: dict, values: dict) -> list[dict]:
    problems = []
    spec_all = policy["fields"]
    for name in values:
        if name not in spec_all:
            problems.append({"problem": "unknown_field", "field": name, "message": f"no field {name!r}; fields: {', '.join(spec_all)}"})
    for name, spec in spec_all.items():
        value = values.get(name)
        if value is None or (value == "" and not spec["allow_empty"]):
            if spec["required"]:
                hint = " (use 'unknown' when it cannot be found out)" if name == "license" else "; the box's README says what it holds"
                problems.append({"problem": "missing_field", "field": name, "message": f"{name} is required{hint}"})
            continue
        if len(value) > LIMITS.get(name, FIELD_LIMIT):
            problems.append({"problem": "too_long", "field": name, "message": f"{name} is limited to {LIMITS.get(name, FIELD_LIMIT)} characters"})
    return problems


def _relations(box, sha: str) -> list[dict]:
    out = []
    for r in box.conn.execute("SELECT * FROM relation WHERE a = ? OR b = ?", (sha, sha)):
        mine = r["a"] == sha
        other = r["b"] if mine else r["a"]
        kind = r["kind"] if mine else INVERSE.get(r["kind"], r["kind"])
        out.append({"ref": other, "kind": kind, "method": r["method"], "score": r["score"],
                    "transform": json.loads(r["transform"]) if r["transform"] and mine else None})
    return out


def is_expired(row: sqlite3.Row) -> bool:
    return bool(row["expires_at"]) and clock.parse(row["expires_at"]) <= clock.now()


def item_dict(box, sha: str) -> dict:
    row = box.conn.execute("SELECT * FROM item WHERE sha256 = ?", (sha,)).fetchone()
    if row is None:
        raise BoxError("not_found", f"no stored item {sha}", ref=sha)
    tags = box.conn.execute(
        "SELECT t.category, t.value FROM item_tag it JOIN tag t ON t.id = it.tag_id WHERE it.sha256 = ? ORDER BY t.category, t.value", (sha,)
    ).fetchall()
    fields = {r["name"]: r["value"] for r in box.conn.execute("SELECT name, value FROM item_field WHERE sha256 = ? ORDER BY name", (sha,))}
    keyframes = box.conn.execute("SELECT COUNT(*) AS n FROM keyframe WHERE sha256 = ?", (sha,)).fetchone()["n"]
    return {
        "ref": sha,
        "file": paths.safe_stored_str(box, row),
        "format": row["format"], "width": row["width"], "height": row["height"],
        "animated": bool(row["animated"]), "frames": row["frames"], "duration_ms": row["duration_ms"], "fps": row["fps"],
        "codec": row["codec"], "audio": bool(row["audio"]), "bytes": row["bytes"],
        "phash": to_hex(db.to_unsigned(row["phash"])), "keyframes": keyframes,
        "added_at": row["added_at"], "updated_at": row["updated_at"], "expires_at": row["expires_at"], "expired": is_expired(row),
        "license": row["license"], "source": row["source"], "text": row["text"], "description": row["description"], "note": row["note"],
        "fields": fields,
        "tags": [f"{t['category']}={t['value']}" for t in tags],
        "relations": _relations(box, sha),
    }


def _matches(box, policy: dict, sidecar: dict, exclude: str | None = None) -> list[dict]:
    matches = dupes.find(box.conn, dupes.hex_hashes(sidecar), sidecar["media"]["animated"], policy["duplicates"]["phash_max_distance"], exclude)
    seen = {m["ref"] for m in matches}
    for m in sidecar.get("sift_matches") or []:
        if m["ref"] not in seen and box.conn.execute("SELECT 1 FROM item WHERE sha256 = ?", (m["ref"],)).fetchone():
            matches.append(m)
    return matches




def _fresh_analysis(box, policy: dict, src, sha: str) -> dict:
    """Metadata, keyframes, features and SIFT matches recomputed from the staged file itself at
    commit, so nothing stored comes from a sidecar someone could have edited. Only the OCR hint,
    the original name, licence and source are taken from staging."""
    from . import features

    result = analysis.analyze(src, policy["analysis"])
    out = {
        "media": result.info.to_dict(),
        "phash": f"{result.phash:016x}",
        "keyframes": [{"idx": i, "frame_no": k.frame_no, "t_ms": k.t_ms, "phash": f"{k.phash:016x}"} for i, k in enumerate(result.keyframes)],
        "sift_sets": [],
        "sift_matches": [],
    }
    sift = policy["duplicates"]["sift"]
    if sift:
        out["sift_sets"] = features.compute(result, policy)
        out["sift_matches"], _ = features.match(box.conn, out["sift_sets"], (result.info.width, result.info.height), sift, exclude=sha)
    return out


def commit(box, ref: str, tags: list[str], defines: list[tuple[str, str]], values: dict, auto_cleanup: bool = False) -> dict:
    policy = box.policy()
    kind, sha = refs.resolve(box, ref)
    if kind == "item":
        raise BoxError("already_stored", f"{sha} is already stored; use `edit` to change it", ref=sha)
    sidecar = stage.load_sidecar(box, sha)
    src = stage.staged_file(box, sidecar)
    if not src.is_file():
        raise BoxError("not_found", f"the staged file for {sha} is gone (temporary/ was cleaned); stage it again", ref=sha)
    if analysis.sha256_file(src) != sha:
        raise BoxError("changed", f"the staged file for {sha[:12]} no longer matches its sha256; stage the file again", ref=sha)
    fresh = _fresh_analysis(box, policy, src, sha)
    sidecar = {**sidecar, **fresh}
    defaults = {"license": sidecar.get("license"), "source": sidecar.get("source")}
    merged = {**defaults, **{k: v for k, v in values.items() if v is not None}}
    plan = vocab.plan(box.conn, policy, tags, defines, box.language)
    problems = rules.check_file(policy["files"], sidecar["media"])
    problems += field_problems(policy, merged)
    problems += plan.problems
    problems += vocab.cardinality(policy, plan.labels, plan.attempted)
    matches = _matches(box, policy, sidecar)
    if problems:
        raise BoxError("invalid", f"{len(problems)} problem(s); nothing was stored", problems=problems, warnings=plan.warnings)
    from . import limits

    to_remove = limits.plan_room(box, policy, sidecar["media"]["bytes"], 1, auto_cleanup)
    expired_now = set(limits.expired(box))
    matches = [x for x in matches if x["ref"] not in set(to_remove)]
    removed, doomed_files = [], []

    now = clock.now()
    ext = src.name.rsplit(".", 1)[1]
    rel = f"persistent/{now:%Y%m}/{now:%Y%m%d}-{sha}.{ext}"
    dest = box.root / rel
    if (box.persistent / f"{now:%Y%m}").is_symlink():
        raise BoxError("unsafe_box", f"persistent/{now:%Y%m} is a symbolic link; the tool will not write through it")
    dest.parent.mkdir(parents=True, exist_ok=True)
    m = sidecar["media"]
    minutes = policy["retention"]["expire_after_minutes"]
    expires = clock.later(minutes, now) if minutes else None
    custom = {k: v for k, v in merged.items() if k not in CORE}
    conn = box.conn
    moved = False
    try:
        with db.transaction(conn):
            if conn.execute("SELECT 1 FROM item WHERE sha256 = ?", (sha,)).fetchone():
                raise BoxError("already_stored", f"{sha} was stored by another session", ref=sha)
            for old in to_remove:
                gone = conn.execute("SELECT sha256, file, added_at, expires_at FROM item WHERE sha256 = ?", (old,)).fetchone()
                if gone is None:
                    continue
                conn.execute("DELETE FROM item WHERE sha256 = ?", (old,))
                if paths.stored_rel(gone):
                    doomed_files.append(gone)
                removed.append({"ref": old, "reason": "expired" if old in expired_now else "oldest",
                                "added_at": gone["added_at"], "expires_at": gone["expires_at"]})
            created = vocab.create_tags(conn, plan.create, f"commit {sha[:12]}")
            conn.execute(
                """INSERT INTO item (sha256, file, format, width, height, animated, frames, duration_ms, fps, codec, audio, bytes,
                   phash, added_at, updated_at, expires_at, license, source, text, description, note)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (sha, rel, m["format"], m["width"], m["height"], int(m["animated"]), m["frames"], m["duration_ms"], m["fps"],
                 m["codec"], int(m["audio"]), m["bytes"], db.to_signed(int(sidecar["phash"], 16)), clock.stamp(now), clock.stamp(now),
                 expires, merged.get("license"), merged.get("source"), merged.get("text"), merged.get("description"), merged.get("note")),
            )
            conn.executemany("INSERT OR IGNORE INTO item_tag (sha256, tag_id) VALUES (?, ?)", [(sha, t) for t in plan.tag_ids + created])
            conn.executemany("INSERT INTO item_field (sha256, name, value) VALUES (?, ?, ?)", [(sha, k, v) for k, v in custom.items()])
            conn.executemany(
                "INSERT INTO keyframe (sha256, idx, frame_no, t_ms, phash) VALUES (?, ?, ?, ?, ?)",
                [(sha, k["idx"], k["frame_no"], k["t_ms"], db.to_signed(int(k["phash"], 16))) for k in sidecar["keyframes"]],
            )
            if policy["duplicates"]["sift"]:
                from . import features

                features.store_sets(box, sha, sidecar["sift_sets"])
            stamp = clock.stamp(now)
            conn.executemany(
                "INSERT OR REPLACE INTO relation (a, b, kind, method, score, transform, found_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [(sha, x["ref"], x["kind"], x.get("method", "phash"), x.get("distance", x.get("inliers")),
                  json.dumps(x["transform"]) if x.get("transform") else None, stamp) for x in matches],
            )
            try:
                os.replace(src, dest)
            except FileNotFoundError:
                raise BoxError("not_found", f"the staged file for {sha} disappeared (temporary/ was cleaned); stage it again", ref=sha) from None
            moved = True
    except sqlite3.IntegrityError as err:
        if moved:
            os.replace(dest, src)
        raise BoxError("conflict", f"another session changed the box at the same time ({err}); run the command again") from None
    except BaseException:
        if moved:
            os.replace(dest, src)
        raise
    for gone in doomed_files:
        try:
            paths.stored_path(box, gone).unlink(missing_ok=True)
        except BoxError:
            pass
    stage.remove_extras(box, sha)
    box.write_readme()
    return {
        "status": "stored",
        "ref": sha,
        "file": str(dest),
        "tags": plan.labels,
        "created_tags": [f"{c['category']}={c['value']}" for c in plan.create],
        "relations": stage.duplicate_report(box, matches, sha, sidecar["media"], staged=False),
        "expires_at": expires,
        "removed": removed,
        "warnings": plan.warnings,
    }


def _current_tags(box, sha: str) -> dict[int, str]:
    return {
        r["id"]: f"{r['category']}={r['value']}"
        for r in box.conn.execute("SELECT t.id, t.category, t.value FROM item_tag it JOIN tag t ON t.id = it.tag_id WHERE it.sha256 = ?", (sha,))
    }


def edit(box, ref: str, add: list[str], remove: list[str], defines: list[tuple[str, str]], values: dict, clear: list[str]) -> dict:
    policy = box.policy()
    _, sha = refs.resolve(box, ref, staged=False)
    row = box.conn.execute("SELECT * FROM item WHERE sha256 = ?", (sha,)).fetchone()
    current = _current_tags(box, sha)
    plan = vocab.plan(box.conn, policy, add, defines, box.language)
    problems = list(plan.problems)
    drop: list[int] = []
    for text in remove:
        try:
            category, value = vocab.parse(text, policy)
        except BoxError as err:
            problems.append({"problem": "invalid_tag", "message": err.message})
            continue
        tag = vocab.tag_row(box.conn, category, value)
        if tag is None or tag["id"] not in current:
            problems.append({"problem": "not_tagged", "tag": f"{category}={value}", "message": f"the item has no tag {category}={value}"})
        else:
            drop.append(tag["id"])
    final = [label for tid, label in current.items() if tid not in drop]
    final += [label for label in plan.labels if label not in final]
    problems += vocab.cardinality(policy, final, plan.attempted)
    fields = {name: row[name] for name in CORE}
    fields.update({r["name"]: r["value"] for r in box.conn.execute("SELECT name, value FROM item_field WHERE sha256 = ?", (sha,))})
    fields.update({k: v for k, v in values.items() if v is not None})
    for name in clear:
        fields[name] = None
    problems += field_problems(policy, {k: v for k, v in fields.items() if v is not None})
    if problems:
        raise BoxError("invalid", f"{len(problems)} problem(s); nothing was changed", problems=problems, warnings=plan.warnings)
    with db.transaction(box.conn):
        created = vocab.create_tags(box.conn, plan.create, f"edit {sha[:12]}")
        box.conn.executemany("DELETE FROM item_tag WHERE sha256 = ? AND tag_id = ?", [(sha, t) for t in drop])
        box.conn.executemany("INSERT OR IGNORE INTO item_tag (sha256, tag_id) VALUES (?, ?)", [(sha, t) for t in plan.tag_ids + created])
        box.conn.execute(
            "UPDATE item SET license = ?, source = ?, text = ?, description = ?, note = ?, updated_at = ? WHERE sha256 = ?",
            (fields["license"], fields["source"], fields["text"], fields["description"], fields["note"], clock.stamp(), sha),
        )
        for name, value in fields.items():
            if name in CORE:
                continue
            if value is None:
                box.conn.execute("DELETE FROM item_field WHERE sha256 = ? AND name = ?", (sha, name))
            else:
                box.conn.execute("INSERT OR REPLACE INTO item_field (sha256, name, value) VALUES (?, ?, ?)", (sha, name, value))
    box.write_readme()
    return {"status": "edited", **item_dict(box, sha), "warnings": plan.warnings}


def remove(box, ref: str) -> dict:
    kind, sha = refs.resolve(box, ref)
    if kind == "staged":
        stage.remove(box, sha)
        return {"status": "removed", "ref": sha, "was": "staged"}
    from . import limits

    (entry,) = limits.remove_items(box, [sha], "removed")
    box.write_readme()
    return {"status": "removed", "ref": sha, "was": "stored", **({"warning": entry["file_left"]} if "file_left" in entry else {})}
