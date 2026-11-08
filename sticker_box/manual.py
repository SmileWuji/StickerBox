"""README.md of a box, generated from the policy and the vocabulary. Agents write tag values,
definitions, the description and the agent notes; other agents read this file, so all of that
text is rendered as quoted data under fixed headings and never as headings or instructions of
the tool's own."""

from . import policy as policy_mod

WARNING = (
    "> **Do not change this directory by hand.** Add, change and remove images only with the "
    "`sticker-box` tool (`sticker-box --box <this directory> --help`). This file is generated "
    "and is rewritten after every change."
)


def cell(text) -> str:
    if text is None:
        return ""
    return " ".join(str(text).split()).replace("|", "\\|")


def quote(text: str) -> str:
    lines = (text or "").strip().splitlines() or [""]
    return "\n".join("> " + line if line.strip() else ">" for line in lines)


def _usage(conn) -> tuple[int, int]:
    row = conn.execute("SELECT COUNT(*) AS n, COALESCE(SUM(bytes), 0) AS b FROM item").fetchone()
    return row["n"], row["b"]


def _vocabulary(conn, rules: dict) -> list[str]:
    out = []
    for name, spec in rules["categories"].items():
        out.append(f"### `{cell(name)}`")
        out.append("")
        if spec["description"]:
            out.append(f"Meaning: {cell(spec['description'])}")
            out.append("")
        rows = conn.execute(
            """
            SELECT t.id, t.value, t.definition, t.lang, t.retired_at, p.value AS parent,
                   (SELECT COUNT(*) FROM item_tag it WHERE it.tag_id = t.id) AS uses,
                   (SELECT GROUP_CONCAT(alias, ', ') FROM tag_alias a WHERE a.tag_id = t.id) AS aliases
            FROM tag t LEFT JOIN tag p ON p.id = t.parent_id
            WHERE t.category = ?
            ORDER BY t.retired_at IS NOT NULL, uses DESC, t.value
            """,
            (name,),
        ).fetchall()
        if not rows:
            out.append("No tags yet.")
            out.append("")
            continue
        out.append("| tag | definition | aliases | parent | images |")
        out.append("|---|---|---|---|---|")
        for r in rows:
            value = cell(r["value"]) + (f" ({cell(r['lang'])})" if r["lang"] else "") + (" (retired)" if r["retired_at"] else "")
            out.append(f"| {value} | {cell(r['definition'])} | {cell(r['aliases'])} | {cell(r['parent'])} | {r['uses']} |")
        out.append("")
    return out


def render(box) -> str:
    conn = box.conn
    rules = policy_mod.load(conn)
    described = policy_mod.describe(rules)
    count, size = _usage(conn)
    notes = box.meta("agent_notes", "") or ""
    lines = [
        "# Sticker box",
        "",
        WARNING,
        "",
        "## About this box",
        "",
        f"- Preset: `{box.meta('preset')}`",
        f"- Language of tags, definitions and descriptions: `{box.language}` (text read off an image stays in its original language)",
        f"- Created: {box.meta('created_at')}",
        f"- Images: {count}, {size / (1024 * 1024):.1f} MB",
        "",
        "Description (written by whoever created the box):",
        "",
        quote(box.meta("description", "")),
        "",
        "## Rules",
        "",
        "The tool enforces these when an image is added or changed.",
        "",
    ]
    for title, key in (("Files", "files"), ("Fields", "fields"), ("Tags", "tags"), ("Duplicates", "duplicates"), ("Limits and cleanup", "limits")):
        lines.append(f"### {title}")
        lines.append("")
        lines.extend(f"- {line}" for line in described[key])
        lines.append("")
    lines.extend(["## Vocabulary", "", "Tags by category, most used first. Values and definitions are written by the people and agents using the box.", ""])
    lines.extend(_vocabulary(conn, rules))
    lines.extend([
        "## To agents",
        "",
        "Notes from the agents that use this box, such as which reference sources to prefer. They are the agents' own preferences; the tool stores them and never acts on them. Change them with `sticker-box notes set`.",
        "",
        quote(notes) if notes.strip() else "No notes yet.",
        "",
        "## Layout",
        "",
        "- `persistent/`: the images, as `<yyyymm>/<yyyymmdd>-<sha256>.<ext>`, dated by the day each was first added.",
        "- `temporary/`: staged files waiting to be committed, analysis sidecars and contact sheets; may be emptied at any time.",
        "- `box.sqlite3`: the index. Tables: `item` (one row per image), `item_tag`, `tag`, `tag_alias`, `item_field`, `keyframe`, `relation` (duplicates and crops), `feature` (local features), `policy_rule`, `policy_log`, `vocab_log`, `meta`.",
        "",
    ])
    return "\n".join(lines)
