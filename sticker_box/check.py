"""Audit: every stored item against the current policy, and the directory against the index.
Reports; never changes anything."""

from . import analysis, features, paths, refs, rules, stage, vocab
from .errors import BoxError
from .items import CORE, field_problems


def check(box, deep: bool = False) -> dict:
    conn = box.conn
    policy = box.policy()
    problems = []
    rows = conn.execute("SELECT * FROM item ORDER BY added_at").fetchall()
    for row in rows:
        sha = row["sha256"]

        def add(problem: dict):
            problems.append({"ref": sha, **problem})

        try:
            path = paths.stored_path(box, row)
        except BoxError as err:
            add({"problem": "bad_path", "message": err.message})
            path = None
        if path is None:
            pass
        elif not path.is_file():
            add({"problem": "missing_file", "message": f"{row['file']} is gone"})
        elif deep and analysis.sha256_file(path) != sha:
            add({"problem": "changed_file", "message": f"{row['file']} no longer matches its sha256"})
        info = {k: row[k] for k in ("format", "width", "height", "frames", "duration_ms", "fps", "codec", "bytes")}
        info.update(animated=bool(row["animated"]), audio=bool(row["audio"]))
        for p in rules.check_file(policy["files"], info):
            add(p)
        values = {name: row[name] for name in CORE if row[name] is not None}
        values.update({r["name"]: r["value"] for r in conn.execute("SELECT name, value FROM item_field WHERE sha256 = ?", (sha,))})
        for p in field_problems(policy, values):
            add(p)
        tags = conn.execute("SELECT t.category, t.value, t.retired_at FROM item_tag it JOIN tag t ON t.id = it.tag_id WHERE it.sha256 = ?", (sha,)).fetchall()
        labels = [f"{t['category']}={t['value']}" for t in tags]
        for t in tags:
            if t["category"] not in policy["categories"]:
                add({"problem": "unknown_category", "tag": f"{t['category']}={t['value']}", "message": f"category {t['category']!r} is no longer in the policy"})
            if t["retired_at"]:
                add({"problem": "retired_tag", "tag": f"{t['category']}={t['value']}", "message": "carries a retired tag"})
        for p in vocab.cardinality(policy, labels):
            add(p)
    known = {r["file"] for r in rows if paths.stored_rel(r)}
    orphans = sorted(str(p.relative_to(box.root)) for p in box.persistent.rglob("*") if p.is_file() and str(p.relative_to(box.root)) not in known)
    stale, featureless = [], []
    if policy["duplicates"]["sift"]:
        stale = [r["sha256"] for r in conn.execute(
            "SELECT DISTINCT sha256 FROM feature WHERE extractor != ?", (features.EXTRACTOR,))]
        stale += [r["sha256"] for r in conn.execute(
            "SELECT DISTINCT sha256 FROM feature WHERE extractor = ? AND (n < 1 OR length(desc) != n * 128 OR length(kp) != n * 8)",
            (features.EXTRACTOR,)) if r["sha256"] not in stale]
        featureless = [r["sha256"] for r in conn.execute(
            "SELECT sha256 FROM item WHERE sha256 NOT IN (SELECT sha256 FROM feature WHERE extractor = ?)", (features.EXTRACTOR,))]
    staged_broken = []
    for sha in refs.staged_shas(box):
        try:
            sidecar = stage.load_sidecar(box, sha)
            if not stage.staged_file(box, sidecar).is_file():
                staged_broken.append(sha)
        except Exception:
            staged_broken.append(sha)
    by_kind: dict[str, int] = {}
    for p in problems:
        by_kind[p["problem"]] = by_kind.get(p["problem"], 0) + 1
    return {
        "items": len(rows),
        "ok": not problems and not orphans and not stale,
        "problem_counts": by_kind,
        "problems": problems,
        "orphan_files": orphans,
        "stale_features": stale,
        "items_without_features": len(featureless),
        "broken_staged": staged_broken,
        "hint": "orphan files and broken staged files are safe to delete; `reindex` refreshes stale features; fix item problems with `edit`" if (problems or orphans or stale or staged_broken) else None,
    }
