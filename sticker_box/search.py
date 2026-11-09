"""Search over tags (values, aliases, narrower tags), on-image text, descriptions, notes and
fields. Each term scores an item by its best match; an item's score is the sum over terms, so
items matching more terms rank first, then newer ones. `LIKE` handles short Chinese terms that a
trigram index could not."""

from . import clock, paths, vocab
from .errors import BoxError

TAG_EXACT, TAG_ALIAS, TAG_PART, TAG_CHILD, TAG_DEFINITION = 10, 8, 5, 4, 3
TEXT, NOTE, DESCRIPTION, FIELD = 6, 4, 2, 1
SNIPPET = 160
MAX_TERMS = 16
MAX_TERM = 64


def terms_of(query: str) -> list[str]:
    return [t for t in query.replace("|", " ").split() if t]


def _like(term: str) -> str:
    return "%" + term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _tag_scores(conn, term: str) -> dict[int, tuple[int, str]]:
    tags = conn.execute("SELECT id, category, value, parent_id FROM tag").fetchall()
    aliases = conn.execute("SELECT tag_id, alias FROM tag_alias").fetchall()
    only_category = None
    if "=" in term:
        only_category, term = term.split("=", 1)
    t = vocab.norm(term)
    if not t:
        return {}
    scores: dict[int, tuple[int, str]] = {}

    def give(tag_id: int, score: int, why: str):
        if score > scores.get(tag_id, (0, ""))[0]:
            scores[tag_id] = (score, why)

    names = {r["id"]: f"{r['category']}={r['value']}" for r in tags}
    for r in tags:
        if only_category and r["category"] != only_category:
            continue
        v = vocab.norm(r["value"])
        if v == t:
            give(r["id"], TAG_EXACT, names[r["id"]])
        elif not only_category and v and (t in v or (len(v) >= 2 and v in t)):
            give(r["id"], TAG_PART, names[r["id"]])
    category_of = {r["id"]: r["category"] for r in tags}
    for a in aliases:
        if only_category and category_of.get(a["tag_id"]) != only_category:
            continue
        if vocab.norm(a["alias"]) == t:
            give(a["tag_id"], TAG_ALIAS, f"{names[a['tag_id']]} (alias {a['alias']})")
    children: dict[int, list[int]] = {}
    for r in tags:
        if r["parent_id"]:
            children.setdefault(r["parent_id"], []).append(r["id"])
    if not only_category:
        for r in conn.execute("SELECT id, definition FROM tag WHERE definition IS NOT NULL"):
            if t in vocab.norm(r["definition"]):
                give(r["id"], TAG_DEFINITION, f"{names[r['id']]} (definition)")
    roots = [tid for tid, (score, _) in scores.items() if score >= TAG_ALIAS]
    while roots:
        parent = roots.pop()
        for child in children.get(parent, []):
            if child not in scores:
                give(child, TAG_CHILD, f"{names[child]} (under {names[parent]})")
                roots.append(child)
    return scores


def _term_hits(conn, term: str) -> dict[str, tuple[int, str]]:
    hits: dict[str, tuple[int, str]] = {}

    def give(sha: str, score: int, why: str):
        if score > hits.get(sha, (0, ""))[0]:
            hits[sha] = (score, why)

    tag_scores = _tag_scores(conn, term)
    if tag_scores:
        ids = list(tag_scores)
        for chunk in range(0, len(ids), 500):
            part = ids[chunk:chunk + 500]
            for r in conn.execute(f"SELECT sha256, tag_id FROM item_tag WHERE tag_id IN ({','.join('?' * len(part))})", part):
                score, why = tag_scores[r["tag_id"]]
                give(r["sha256"], score, f"tag {why}")
    if "=" in term:
        return hits
    pattern = _like(term)
    for column, score in (("text", TEXT), ("note", NOTE), ("description", DESCRIPTION), ("source", FIELD)):
        for r in conn.execute(f"SELECT sha256 FROM item WHERE {column} LIKE ? ESCAPE '\\'", (pattern,)):
            give(r["sha256"], score, column)
    for r in conn.execute("SELECT DISTINCT sha256 FROM item_field WHERE value LIKE ? ESCAPE '\\'", (pattern,)):
        give(r["sha256"], FIELD, "field")
    return hits


def search(box, query: str, tags: list[str] = (), category: str | None = None, animated: bool | None = None,
           license: str | None = None, limit: int = 10) -> dict:
    conn = box.conn
    policy = box.policy()
    terms = terms_of(query)
    if len(terms) > MAX_TERMS or any(len(t) > MAX_TERM for t in terms):
        raise BoxError("usage", f"a query has at most {MAX_TERMS} words of at most {MAX_TERM} characters each")
    if len(tags) > MAX_TERMS:
        raise BoxError("usage", f"at most {MAX_TERMS} --tag filters")
    if limit < 1 or limit > 500:
        raise BoxError("usage", "--limit must be between 1 and 500")
    clauses, params = [], []
    for text in tags:
        cat, value = vocab.parse(text, policy)
        row = vocab.tag_row(conn, cat, value)
        if row is None:
            return {"query": query, "total": 0, "results": [], "warnings": [f"no tag {cat}={value}"],
                    "suggestions": vocab.suggest(conn, cat, value)}
        clauses.append("i.sha256 IN (SELECT sha256 FROM item_tag WHERE tag_id = ?)")
        params.append(row["id"])
    if category:
        clauses.append("i.sha256 IN (SELECT it.sha256 FROM item_tag it JOIN tag t ON t.id = it.tag_id WHERE t.category = ?)")
        params.append(category)
    if animated is not None:
        clauses.append("i.animated = ?")
        params.append(int(animated))
    if license:
        clauses.append("i.license LIKE ? ESCAPE '\\'")
        params.append(_like(license))
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    allowed = {r["sha256"]: r["added_at"] for r in conn.execute(f"SELECT i.sha256, i.added_at FROM item i {where}", params)}
    scores: dict[str, int] = {}
    matched: dict[str, list[str]] = {}
    for term in terms:
        for sha, (score, why) in _term_hits(conn, term).items():
            if sha in allowed:
                scores[sha] = scores.get(sha, 0) + score
                matched.setdefault(sha, []).append(f"{term}: {why}")
    if not terms:
        scores = {sha: 0 for sha in allowed}
    ranked = sorted(scores, key=lambda sha: (scores[sha], allowed[sha], sha), reverse=True)
    now = clock.stamp()
    results = []
    for sha in ranked[:limit]:
        row = conn.execute("SELECT * FROM item WHERE sha256 = ?", (sha,)).fetchone()
        tag_rows = conn.execute(
            "SELECT t.category, t.value FROM item_tag it JOIN tag t ON t.id = it.tag_id WHERE it.sha256 = ? ORDER BY t.category, t.value", (sha,)
        ).fetchall()
        results.append({
            "ref": sha,
            "file": paths.safe_stored_str(box, row),
            "score": scores[sha],
            "matched": matched.get(sha, []),
            "format": row["format"],
            "animated": bool(row["animated"]),
            "tags": [f"{t['category']}={t['value']}" for t in tag_rows],
            "note": row["note"],
            "text": None if row["text"] is None else row["text"][:SNIPPET],
            "description": (row["description"] or "")[:SNIPPET] or None,
            "expired": bool(row["expires_at"]) and row["expires_at"] <= now,
        })
    return {"query": query, "total": len(ranked), "results": results}


def as_text(result: dict) -> str:
    if not result["results"]:
        return "no results" + ("; " + "; ".join(result.get("warnings", [])) if result.get("warnings") else "")
    lines = [f"{result['total']} result(s)"]
    for r in result["results"]:
        lines.append(f"{r['ref'][:12]}  {r['file']}")
        lines.append(f"    tags: {', '.join(r['tags']) or '-'}")
        if r["note"]:
            lines.append(f"    note: {r['note']}")
        if r["expired"]:
            lines.append("    expired")
    return "\n".join(lines)

