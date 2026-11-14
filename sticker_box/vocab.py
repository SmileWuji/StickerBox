"""The tag vocabulary: finding tags by value or alias, suggesting near matches, deciding per mode
whether an unknown tag may be created, and the verbs that change the vocabulary."""

import difflib
import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field

from . import clock
from .errors import BoxError

MAX_VALUE = 64
MAX_DEFINITION = 500
MAX_TAGS_PER_CHANGE = 64
MAX_ALIASES = 32
_STRIP = re.compile(r"[\s\W_]+", re.UNICODE)


def norm(text: str) -> str:
    return _STRIP.sub("", unicodedata.normalize("NFKC", text).casefold())


def _bigrams(text: str) -> set[str]:
    return {text[i:i + 2] for i in range(len(text) - 1)} or {text}


def similarity(a: str, b: str) -> float:
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.85 + 0.1 * min(len(a), len(b)) / max(len(a), len(b))
    ba, bb = _bigrams(a), _bigrams(b)
    dice = 2 * len(ba & bb) / (len(ba) + len(bb))
    return max(dice, difflib.SequenceMatcher(None, a, b).ratio() * 0.9)


def check_value(value: str) -> str:
    value = value.strip()
    if not value:
        raise BoxError("invalid_tag", "a tag value may not be empty")
    if len(value) > MAX_VALUE or "\n" in value or "|" in value:
        raise BoxError("invalid_tag", f"tag {value!r} must be one line of at most {MAX_VALUE} characters without '|'")
    return value


def parse(text: str, policy: dict) -> tuple[str, str]:
    """'category=value', or a bare value when the policy has a default category."""
    if "=" in text:
        category, value = text.split("=", 1)
        category = category.strip()
    else:
        category, value = policy["vocabulary"]["default_category"], text
        if category is None:
            raise BoxError("invalid_tag", f"{text!r} has no category; write category=value (categories: {', '.join(policy['categories'])})")
    return category, check_value(value)


def tag_row(conn: sqlite3.Connection, category: str, value: str) -> sqlite3.Row | None:
    row = conn.execute("SELECT * FROM tag WHERE category = ? AND value = ?", (category, value)).fetchone()
    if row:
        return row
    return conn.execute(
        "SELECT t.* FROM tag_alias a JOIN tag t ON t.id = a.tag_id WHERE a.category = ? AND a.alias = ?", (category, value)
    ).fetchone()


def tag_by_norm(conn: sqlite3.Connection, category: str, value: str) -> sqlite3.Row | None:
    target = norm(value)
    if not target:
        return None
    for row in conn.execute("SELECT * FROM tag WHERE category = ? AND retired_at IS NULL", (category,)):
        if norm(row["value"]) == target:
            return row
    for row in conn.execute("SELECT t.*, a.alias FROM tag_alias a JOIN tag t ON t.id = a.tag_id WHERE a.category = ?", (category,)):
        if norm(row["alias"]) == target:
            return row
    return None


def suggest(conn: sqlite3.Connection, category: str, value: str, limit: int = 5) -> list[str]:
    scored: dict[str, float] = {}
    rows = conn.execute(
        """SELECT t.value AS value, t.value AS name FROM tag t WHERE t.category = ? AND t.retired_at IS NULL
           UNION ALL
           SELECT t.value, a.alias FROM tag_alias a JOIN tag t ON t.id = a.tag_id WHERE a.category = ? AND t.retired_at IS NULL""",
        (category, category),
    )
    for row in rows:
        score = similarity(value, row["name"])
        if score >= 0.3:
            scored[row["value"]] = max(scored.get(row["value"], 0.0), score)
    best = sorted(scored.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]
    return [f"{category}={v}" for v, _ in best]


@dataclass
class Plan:
    """Tags an item will carry, the ones to create first, and what went wrong."""
    tag_ids: list[int] = field(default_factory=list)
    create: list[dict] = field(default_factory=list)
    labels: list[str] = field(default_factory=list)
    problems: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    attempted: set[str] = field(default_factory=set)


def plan(conn: sqlite3.Connection, policy: dict, tags: list[str], defines: list[tuple[str, str]], language: str) -> Plan:
    from . import script_check

    result = Plan()
    if len(tags) + len(defines) > MAX_TAGS_PER_CHANGE:
        result.problems.append({"problem": "too_many_tags", "message": f"at most {MAX_TAGS_PER_CHANGE} tags per command"})
        return result
    mode = policy["vocabulary"]["mode"]
    categories = policy["categories"]
    definitions: dict[tuple[str, str], str] = {}
    requested: list[tuple[str, str]] = []
    for text, definition in defines:
        try:
            key = parse(text, policy)
        except BoxError as err:
            result.problems.append({"problem": "invalid_tag", "message": err.message})
            continue
        if len(definition) > MAX_DEFINITION:
            result.problems.append({"problem": "invalid_definition", "tag": f"{key[0]}={key[1]}", "message": f"definitions are at most {MAX_DEFINITION} characters"})
        definitions[key] = definition.strip()
        requested.append(key)
    for text in tags:
        try:
            requested.append(parse(text, policy))
        except BoxError as err:
            result.problems.append({"problem": "invalid_tag", "message": err.message})
    seen: set[tuple[str, str]] = set()
    for category, value in requested:
        label = f"{category}={value}"
        if (category, value) in seen:
            continue
        seen.add((category, value))
        result.attempted.add(category)
        if category not in categories:
            result.problems.append({"problem": "unknown_category", "tag": label, "message": f"no category {category!r}", "categories": list(categories)})
            continue
        row = tag_row(conn, category, value)
        via_alias = row is not None and row["value"] != value
        if row is None:
            close = tag_by_norm(conn, category, value)
            if close is not None:
                row = close
                result.warnings.append(f"{label}: used the existing tag {category}={close['value']}, which differs only in case, width or punctuation")
        if row is not None:
            if via_alias:
                result.warnings.append(f"{label} is an alias; used {category}={row['value']}")
            if row["retired_at"]:
                result.problems.append({"problem": "retired_tag", "tag": label, "message": f"{label} is retired", "suggestions": suggest(conn, category, value)})
                continue
            if row["id"] not in result.tag_ids:
                result.tag_ids.append(row["id"])
                result.labels.append(f"{category}={row['value']}")
            if (category, value) in definitions and definitions[(category, value)] and not row["definition"]:
                result.warnings.append(f"{label} already exists; its definition was left unchanged (use `tag define`)")
            continue
        definition = definitions.get((category, value), "")
        if mode == "locked":
            result.problems.append({
                "problem": "unknown_tag", "tag": label, "suggestions": suggest(conn, category, value),
                "message": f"{label} is not in the locked vocabulary; use a suggestion, or create it with `sticker-box tag new {category} {value} --means ...`",
            })
            continue
        if mode == "open" and not definition:
            result.problems.append({
                "problem": "unknown_tag", "tag": label, "suggestions": suggest(conn, category, value),
                "message": f"{label} is new; reuse a suggestion if one fits, or define it with --define {label} \"<definition>\"",
            })
            continue
        result.create.append({"category": category, "value": value, "definition": definition or None})
        result.labels.append(label)
        warning = None if categories[category].get("names") else script_check.mismatch(value, language)
        if warning:
            result.warnings.append(f"{label}: {warning}")
    return result


def cardinality(policy: dict, labels: list[str], attempted: set[str] = frozenset()) -> list[dict]:
    problems = []
    counts: dict[str, int] = {}
    for label in labels:
        counts[label.split("=", 1)[0]] = counts.get(label.split("=", 1)[0], 0) + 1
    for name, spec in policy["categories"].items():
        n = counts.get(name, 0)
        if spec["required"] and n == 0 and name not in attempted:
            problems.append({"problem": "missing_category", "category": name, "message": f"at least one {name} tag is required"})
        if not spec["multiple"] and n > 1:
            problems.append({"problem": "too_many_values", "category": name, "message": f"{name} takes one value, got {n}"})
    return problems


def create_tags(conn: sqlite3.Connection, specs: list[dict], how: str) -> list[int]:
    ids = []
    for spec in specs:
        cur = conn.execute(
            "INSERT INTO tag (category, value, definition, created_at) VALUES (?, ?, ?, ?)",
            (spec["category"], spec["value"], spec["definition"], clock.stamp()),
        )
        ids.append(cur.lastrowid)
        log(conn, "create", {"category": spec["category"], "value": spec["value"], "definition": spec["definition"], "via": how})
    return ids


def log(conn: sqlite3.Connection, action: str, details: dict) -> None:
    conn.execute("INSERT INTO vocab_log (at, action, details) VALUES (?, ?, ?)", (clock.stamp(), action, json.dumps(details, ensure_ascii=False)))


def _category(policy: dict, category: str) -> str:
    if category not in policy["categories"]:
        raise BoxError("unknown_category", f"no category {category!r}", categories=list(policy["categories"]))
    return category


def _require(conn: sqlite3.Connection, category: str, value: str) -> sqlite3.Row:
    row = conn.execute("SELECT * FROM tag WHERE category = ? AND value = ?", (category, value)).fetchone()
    if row is None:
        alias = tag_row(conn, category, value)
        hint = f"; {value!r} is an alias of {alias['value']!r}" if alias else ""
        raise BoxError("unknown_tag", f"no tag {category}={value}{hint}", suggestions=suggest(conn, category, value))
    return row


def _free(conn: sqlite3.Connection, category: str, value: str, own_id: int | None = None) -> None:
    taken = tag_row(conn, category, value)
    if taken is not None and taken["id"] != own_id:
        raise BoxError("exists", f"{category}={value} is already a tag or an alias of {category}={taken['value']}")
    close = tag_by_norm(conn, category, value)
    if close is not None and close["id"] != own_id:
        raise BoxError("exists", f"{category}={value} differs from {category}={close['value']} only in case, width or punctuation; use that tag or add an alias")


def _with_counts(conn: sqlite3.Connection, where: str, params: tuple) -> list[dict]:
    rows = conn.execute(
        f"""SELECT t.*, p.value AS parent,
                  (SELECT COUNT(*) FROM item_tag it WHERE it.tag_id = t.id) AS uses,
                  (SELECT GROUP_CONCAT(alias, '|') FROM tag_alias a WHERE a.tag_id = t.id) AS aliases
           FROM tag t LEFT JOIN tag p ON p.id = t.parent_id {where} ORDER BY t.category, uses DESC, t.value""",
        params,
    ).fetchall()
    return [{
        "tag": f"{r['category']}={r['value']}", "category": r["category"], "value": r["value"], "definition": r["definition"],
        "aliases": r["aliases"].split("|") if r["aliases"] else [], "parent": r["parent"], "uses": r["uses"],
        "lang": r["lang"], "retired": bool(r["retired_at"]),
    } for r in rows]


def list_tags(conn: sqlite3.Connection, category: str | None, retired: bool) -> list[dict]:
    clauses, params = [], []
    if category:
        clauses.append("t.category = ?")
        params.append(category)
    if not retired:
        clauses.append("t.retired_at IS NULL")
    return _with_counts(conn, ("WHERE " + " AND ".join(clauses)) if clauses else "", tuple(params))


def new(conn, policy, language, category, value, definition, parent=None, aliases=(), lang=None) -> dict:
    category = _category(policy, category)
    value = check_value(value)
    if not definition or not definition.strip():
        raise BoxError("missing_definition", "a new tag needs a definition (--means)")
    if len(definition) > MAX_DEFINITION:
        raise BoxError("invalid_definition", f"definitions are at most {MAX_DEFINITION} characters")
    _free(conn, category, value)
    parent_id = _require(conn, category, parent)["id"] if parent else None
    cur = conn.execute(
        "INSERT INTO tag (category, value, definition, parent_id, lang, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (category, value, definition.strip(), parent_id, lang, clock.stamp()),
    )
    for alias in aliases:
        add_alias(conn, category, value, alias)
    log(conn, "create", {"category": category, "value": value, "definition": definition.strip(), "parent": parent, "via": "tag new"})
    from . import script_check

    warning = None if lang or policy["categories"][category].get("names") else script_check.mismatch(value, language)
    return {"tag": f"{category}={value}", "id": cur.lastrowid, "warnings": [warning] if warning else []}


def define(conn, category, value, definition) -> dict:
    row = _require(conn, category, value)
    if len(definition) > MAX_DEFINITION:
        raise BoxError("invalid_definition", f"definitions are at most {MAX_DEFINITION} characters")
    conn.execute("UPDATE tag SET definition = ? WHERE id = ?", (definition.strip() or None, row["id"]))
    log(conn, "define", {"category": category, "value": value, "old": row["definition"], "new": definition.strip()})
    return {"tag": f"{category}={value}", "definition": definition.strip()}


def add_alias(conn, category, value, alias) -> None:
    row = _require(conn, category, value)
    alias = check_value(alias)
    _free(conn, category, alias)
    if conn.execute("SELECT COUNT(*) AS n FROM tag_alias WHERE tag_id = ?", (row["id"],)).fetchone()["n"] >= MAX_ALIASES:
        raise BoxError("too_many_aliases", f"{category}={value} already has {MAX_ALIASES} aliases")
    conn.execute("INSERT INTO tag_alias (tag_id, category, alias) VALUES (?, ?, ?)", (row["id"], category, alias))
    log(conn, "alias", {"category": category, "value": value, "alias": alias})


def remove_alias(conn, category, value, alias) -> None:
    row = _require(conn, category, value)
    cur = conn.execute("DELETE FROM tag_alias WHERE tag_id = ? AND alias = ?", (row["id"], alias))
    if cur.rowcount == 0:
        raise BoxError("not_found", f"{alias!r} is not an alias of {category}={value}")
    log(conn, "unalias", {"category": category, "value": value, "alias": alias})


def rename(conn, category, old, new_value) -> dict:
    row = _require(conn, category, old)
    new_value = check_value(new_value)
    _free(conn, category, new_value, own_id=row["id"])
    conn.execute("DELETE FROM tag_alias WHERE category = ? AND alias = ?", (category, new_value))
    conn.execute("UPDATE tag SET value = ? WHERE id = ?", (new_value, row["id"]))
    conn.execute("INSERT OR IGNORE INTO tag_alias (tag_id, category, alias) VALUES (?, ?, ?)", (row["id"], category, old))
    log(conn, "rename", {"category": category, "old": old, "new": new_value})
    return {"tag": f"{category}={new_value}", "alias_kept": old}


def merge(conn, category, source, target) -> dict:
    src, dst = _require(conn, category, source), _require(conn, category, target)
    if src["id"] == dst["id"]:
        raise BoxError("invalid", "a tag cannot be merged into itself")
    had = conn.execute("SELECT COUNT(*) AS n FROM item_tag WHERE tag_id = ?", (src["id"],)).fetchone()["n"]
    moved = conn.execute(
        "INSERT OR IGNORE INTO item_tag (sha256, tag_id) SELECT sha256, ? FROM item_tag WHERE tag_id = ?", (dst["id"], src["id"])
    ).rowcount
    conn.execute("UPDATE tag_alias SET tag_id = ? WHERE tag_id = ?", (dst["id"], src["id"]))
    extra = conn.execute("SELECT alias FROM tag_alias WHERE tag_id = ? ORDER BY rowid LIMIT -1 OFFSET ?", (dst["id"], MAX_ALIASES - 1)).fetchall()
    conn.executemany("DELETE FROM tag_alias WHERE tag_id = ? AND alias = ?", [(dst["id"], r["alias"]) for r in extra])
    conn.execute("UPDATE tag SET parent_id = ? WHERE parent_id = ?", (dst["id"], src["id"]))
    conn.execute("DELETE FROM tag WHERE id = ?", (src["id"],))
    conn.execute("INSERT OR IGNORE INTO tag_alias (tag_id, category, alias) VALUES (?, ?, ?)", (dst["id"], category, source))
    if not dst["definition"] and src["definition"]:
        conn.execute("UPDATE tag SET definition = ? WHERE id = ?", (src["definition"], dst["id"]))
    dropped = [r["alias"] for r in extra]
    log(conn, "merge", {"category": category, "from": source, "into": target, "items": moved,
                        **({"aliases_dropped": dropped} if dropped else {})})
    message = f"{had} item(s) lost {category}={source}; {moved} gained {category}={target}, {had - moved} already had it"
    if dropped:
        message += (f". A tag keeps at most {MAX_ALIASES} aliases, so these were dropped: {', '.join(dropped)}; "
                    "re-add any that matter as aliases of another tag")
    return {"tag": f"{category}={target}", "merged": f"{category}={source}", "items_retagged": moved,
            "items_already_tagged": had - moved, "alias_kept": source, "aliases_dropped": dropped, "message": message}


def retire(conn, category, value, restore: bool = False) -> dict:
    row = _require(conn, category, value)
    conn.execute("UPDATE tag SET retired_at = ? WHERE id = ?", (None if restore else clock.stamp(), row["id"]))
    log(conn, "restore" if restore else "retire", {"category": category, "value": value})
    return {"tag": f"{category}={value}", "retired": not restore}


def set_parent(conn, category, value, parent: str | None) -> dict:
    row = _require(conn, category, value)
    parent_id = None
    if parent:
        parent_row = _require(conn, category, parent)
        node = parent_row
        while node is not None:
            if node["id"] == row["id"]:
                raise BoxError("cycle", f"{category}={parent} is below {category}={value}; a tag cannot be its own ancestor")
            node = conn.execute("SELECT * FROM tag WHERE id = ?", (node["parent_id"],)).fetchone() if node["parent_id"] else None
        parent_id = parent_row["id"]
    conn.execute("UPDATE tag SET parent_id = ? WHERE id = ?", (parent_id, row["id"]))
    log(conn, "parent", {"category": category, "value": value, "parent": parent})
    return {"tag": f"{category}={value}", "parent": parent}


def _candidate_pairs(group: list[dict]) -> list[tuple[int, int]]:
    """Pairs of tags that share a character or a bigram in their values or aliases; only these
    can score high, so review stays far below quadratic. Very common keys are skipped."""
    index: dict[str, set[int]] = {}
    for i, t in enumerate(group):
        for name in (t["value"], *t["aliases"]):
            n = norm(name)
            for gram in set(n) | _bigrams(n):
                index.setdefault(gram, set()).add(i)
    pairs = set()
    for members in index.values():
        if len(members) > 200:
            continue
        ordered = sorted(members)
        for x, i in enumerate(ordered):
            for j in ordered[x + 1:]:
                pairs.add((i, j))
    return sorted(pairs)


def review(conn, policy, category: str | None = None, threshold: float = 0.6) -> dict:
    """Near-twin tags, undefined tags and unused tags, for a cleanup pass."""
    tags = list_tags(conn, category, retired=False)
    pairs = []
    by_cat: dict[str, list[dict]] = {}
    for t in tags:
        by_cat.setdefault(t["category"], []).append(t)
    for cat, group in by_cat.items():
        for i, j in _candidate_pairs(group):
            a, b = group[i], group[j]
            names_a = [a["value"], *a["aliases"][:MAX_ALIASES]]
            names_b = [b["value"], *b["aliases"][:MAX_ALIASES]]
            score = max(similarity(x, y) for x in names_a for y in names_b)
            if score >= threshold:
                keep, drop = (a, b) if a["uses"] >= b["uses"] else (b, a)
                pairs.append({
                    "category": cat, "score": round(score, 2),
                    "a": {"value": a["value"], "uses": a["uses"], "definition": a["definition"]},
                    "b": {"value": b["value"], "uses": b["uses"], "definition": b["definition"]},
                    "merge_hint": f"sticker-box tag merge {cat} {drop['value']} {keep['value']}",
                })
    pairs.sort(key=lambda p: -p["score"])
    return {
        "mode": policy["vocabulary"]["mode"],
        "tags": len(tags),
        "similar_pairs": pairs,
        "undefined": [t["tag"] for t in tags if not t["definition"]],
        "unused": [t["tag"] for t in tags if t["uses"] == 0],
    }
