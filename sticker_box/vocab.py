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
        if row is None:
            close = tag_by_norm(conn, category, value)
            if close is not None and (mode == "free" or (category, value) not in definitions):
                row = close
                result.warnings.append(f"{label}: used the existing tag {category}={close['value']}")
        if row is not None:
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
        warning = script_check.mismatch(value, language)
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
            problems.append({"problem": "missing_category", "category": name, "message": f"at least one {name} tag is required" + (f" ({spec['description']})" if spec["description"] else "")})
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
