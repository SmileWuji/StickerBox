import argparse
import json
from pathlib import Path

from . import db, policy, presets
from .box import NOTES_LIMIT, Box, locate
from .errors import BoxError


_opened: list[Box] = []


def open_box(args: argparse.Namespace) -> Box:
    box = Box.open(locate(getattr(args, "box", None)))
    _opened.append(box)
    return box


def close_all() -> None:
    while _opened:
        _opened.pop().close()


def _pretty(value) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _read_json(text: str | None, file: str | None):
    if file:
        text = Path(file).read_text(encoding="utf-8")
    if text is None:
        raise BoxError("usage", "give the parameters as JSON, or --file")
    try:
        return json.loads(text)
    except json.JSONDecodeError as err:
        raise BoxError("invalid_json", f"not valid JSON: {err}") from None


def cmd_init(args) -> dict:
    box = Box.create(Path(args.dir), args.preset, args.language, args.description)
    _opened.append(box)
    return {"box": str(box.root), "preset": args.preset, "language": args.language, "readme": str(box.readme)}


def cmd_info(args) -> dict:
    box = open_box(args)
    conn = box.conn
    rules = box.policy()
    items = conn.execute("SELECT COUNT(*) AS n, COALESCE(SUM(bytes), 0) AS b FROM item").fetchone()
    tags = conn.execute("SELECT COUNT(*) AS n FROM tag WHERE retired_at IS NULL").fetchone()["n"]
    staged = len(list(box.temporary.glob("*.json")))
    return {
        "box": str(box.root),
        "preset": box.meta("preset"),
        "language": box.language,
        "description": box.meta("description"),
        "created_at": box.meta("created_at"),
        "schema_version": int(box.meta("schema_version")),
        "items": items["n"],
        "bytes": items["b"],
        "staged": staged,
        "tags": tags,
        "vocabulary": rules["vocabulary"]["mode"],
        "limits": rules["limits"],
        "retention": rules["retention"],
        "rules": policy.describe(rules),
    }


def cmd_policy_show(args) -> dict:
    box = open_box(args)
    rules = box.policy()
    if args.rule:
        if args.rule not in policy.RULES:
            raise BoxError("invalid_policy", f"unknown rule {args.rule!r}; rules: {', '.join(policy.RULES)}")
        result = {"rule": args.rule, "params": rules[args.rule]}
    else:
        result = {"policy": rules}
    result["_text"] = _pretty({k: v for k, v in result.items() if k != "_text"})
    return result


def cmd_policy_set(args) -> dict:
    box = open_box(args)
    params = _read_json(args.params, args.file)
    with db.transaction(box.conn):
        new = policy.set_rule(box.conn, args.rule, params)
    box.write_readme()
    return {"rule": args.rule, "params": new, "rules": policy.describe(box.policy())}


def cmd_manual(args) -> dict:
    box = open_box(args)
    box.write_readme()
    return {"readme": str(box.readme)}


def cmd_notes_show(args) -> dict:
    box = open_box(args)
    notes = box.meta("agent_notes", "")
    return {"notes": notes, "_text": notes or "(no notes)"}


def cmd_notes_set(args) -> dict:
    box = open_box(args)
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
    elif args.text is not None:
        text = args.text
    else:
        raise BoxError("usage", "give the notes as text, or --file")
    if len(text) > NOTES_LIMIT:
        raise BoxError("too_long", f"notes are limited to {NOTES_LIMIT} characters", length=len(text))
    with db.transaction(box.conn):
        db.set_meta(box.conn, "agent_notes", text)
    box.write_readme()
    return {"notes": text}


def register(sub: argparse._SubParsersAction, common: argparse.ArgumentParser) -> None:
    def add(name: str, handler, help_text: str, parent=sub):
        p = parent.add_parser(name, parents=[common], help=help_text, description=help_text)
        p.set_defaults(handler=handler)
        return p

    p = add("init", cmd_init, "create a box")
    p.add_argument("dir")
    p.add_argument("--preset", required=True, choices=sorted(presets.PRESETS))
    p.add_argument("--language", required=True, help="language of tags and descriptions, e.g. zh-Hans, ja, en")
    p.add_argument("--description", help="what the box is for (defaults to the preset's)")

    add("info", cmd_info, "show the box, its usage and its rules")
    add("manual", cmd_manual, "regenerate README.md")

    group = sub.add_parser("policy", help="show or change the policy", parents=[common])
    gsub = group.add_subparsers(dest="action", metavar="<action>", required=True, parser_class=sub._parser_class)
    p = add("show", cmd_policy_show, "print the policy, or one rule", gsub)
    p.add_argument("rule", nargs="?")
    p = add("set", cmd_policy_set, "replace one rule (logged)", gsub)
    p.add_argument("rule", choices=policy.RULES)
    p.add_argument("params", nargs="?", help="the rule's parameters as JSON")
    p.add_argument("--file", help="read the JSON from a file")

    group = sub.add_parser("notes", help="the README's 'To agents' notes", parents=[common])
    gsub = group.add_subparsers(dest="action", metavar="<action>", required=True, parser_class=sub._parser_class)
    add("show", cmd_notes_show, "print the notes", gsub)
    p = add("set", cmd_notes_set, "replace the notes ('' clears them)", gsub)
    p.add_argument("text", nargs="?")
    p.add_argument("--file", help="read the notes from a file")
