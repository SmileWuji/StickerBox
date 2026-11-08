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


def cmd_analyze(args) -> dict:
    from . import analysis

    params = policy.DEFAULTS["analysis"]
    results = []
    for name in args.paths:
        path = Path(name)
        if not path.is_file():
            raise BoxError("not_found", f"{name} is not a file")
        results.append({"path": str(path), **analysis.analyze(path, params, with_ocr=args.ocr).summary()})
    return {"files": results}


def cmd_frames(args) -> dict:
    from . import analysis, contact, refs
    from . import stage as stage_mod

    path = Path(args.ref)
    if not path.is_file():
        if not refs.looks_like_ref(args.ref):
            raise BoxError("not_found", f"{args.ref} is neither a file nor a reference")
        box = open_box(args)
        kind, sha = refs.resolve(box, args.ref)
        if kind == "item":
            path = box.root / box.conn.execute("SELECT file FROM item WHERE sha256 = ?", (sha,)).fetchone()["file"]
        else:
            path = stage_mod.staged_file(box, stage_mod.load_sidecar(box, sha))
    result = analysis.analyze(path, policy.DEFAULTS["analysis"])
    if args.out:
        out = Path(args.out)
    else:
        out = open_box(args).temporary / f"frames-{result.sha256}.jpg"
    contact.write(contact.sheet(result.sheet_frames()), out)
    return {"sheet": str(out.resolve()), "keyframes": len(result.keyframes), "animated": result.info.animated,
            "duration_ms": result.info.duration_ms}


def _values(args) -> dict:
    values = {name: getattr(args, name, None) for name in ("license", "source", "text", "description", "note")}
    for item in getattr(args, "field", None) or []:
        if "=" not in item:
            raise BoxError("usage", f"--field takes name=value, got {item!r}")
        name, value = item.split("=", 1)
        values[name.strip()] = value
    return values


def cmd_stage(args) -> dict:
    from . import limits
    from . import stage as stage_mod

    box = open_box(args)
    if args.from_box:
        from . import transfer

        if len(args.paths) != 1:
            raise BoxError("usage", "stage --from takes exactly one reference")
        return transfer.stage_from(box, Path(args.from_box), args.paths[0], args.license, args.source, args.auto_cleanup)
    results, failed = [], 0
    for name in args.paths:
        try:
            path = Path(name)
            if path.is_file():
                removed = limits.make_room(box, box.policy(), path.stat().st_size, 1, args.auto_cleanup)
            else:
                removed = []
            result = stage_mod.stage_file(box, path, args.license, args.source)
            if removed:
                result["removed"] = removed
            results.append(result)
        except BoxError as err:
            if err.code == "limit_exceeded":
                raise
            failed += 1
            results.append({"status": "error", "name": name, **err.to_dict()})
    out = {"results": results}
    if failed:
        out["_exit"] = 1
    return out


def cmd_staged(args) -> dict:
    from . import stage as stage_mod

    return {"staged": stage_mod.listing(open_box(args))}


def cmd_commit(args) -> dict:
    from . import items

    return items.commit(open_box(args), args.ref, args.tag or [], [tuple(d) for d in args.define or []], _values(args), args.auto_cleanup)


def cmd_show(args) -> dict:
    from . import items, refs
    from . import stage as stage_mod

    box = open_box(args)
    kind, sha = refs.resolve(box, args.ref)
    if kind == "item":
        return items.item_dict(box, sha)
    policy_ = box.policy()
    sidecar = stage_mod.ensure_fresh(box, policy_, sha)
    return stage_mod.report(box, policy_, sidecar, "staged")


def cmd_edit(args) -> dict:
    from . import items

    return items.edit(open_box(args), args.ref, args.add_tag or [], args.remove_tag or [], [tuple(d) for d in args.define or []],
                      _values(args), args.clear or [])


def cmd_remove(args) -> dict:
    from . import items

    box = open_box(args)
    return {"results": [items.remove(box, ref) for ref in args.refs]}


def cmd_clean(args) -> dict:
    from . import limits

    return limits.clean(open_box(args), everything=args.all)


def _vocab_write(args, action) -> dict:
    box = open_box(args)
    with db.transaction(box.conn):
        result = action(box)
    box.write_readme()
    return result


def cmd_tag_list(args) -> dict:
    from . import vocab

    return {"tags": vocab.list_tags(open_box(args).conn, args.category, args.retired)}


def cmd_tag_new(args) -> dict:
    from . import vocab

    return _vocab_write(args, lambda box: vocab.new(box.conn, box.policy(), box.language, args.category, args.value, args.means,
                                                    args.parent, args.alias or [], args.lang))


def cmd_tag_define(args) -> dict:
    from . import vocab

    return _vocab_write(args, lambda box: vocab.define(box.conn, args.category, args.value, args.definition))


def cmd_tag_alias(args) -> dict:
    from . import vocab

    def act(box):
        for alias in args.aliases:
            (vocab.remove_alias if args.remove else vocab.add_alias)(box.conn, args.category, args.value, alias)
        return {"tag": f"{args.category}={args.value}", ("removed" if args.remove else "added"): args.aliases}

    return _vocab_write(args, act)


def cmd_tag_rename(args) -> dict:
    from . import vocab

    return _vocab_write(args, lambda box: vocab.rename(box.conn, args.category, args.old, args.new))


def cmd_tag_merge(args) -> dict:
    from . import vocab

    return _vocab_write(args, lambda box: vocab.merge(box.conn, args.category, args.source, args.target))


def cmd_tag_retire(args) -> dict:
    from . import vocab

    return _vocab_write(args, lambda box: vocab.retire(box.conn, args.category, args.value, args.restore))


def cmd_tag_parent(args) -> dict:
    from . import vocab

    return _vocab_write(args, lambda box: vocab.set_parent(box.conn, args.category, args.value, args.parent))


def cmd_vocab_review(args) -> dict:
    from . import vocab

    box = open_box(args)
    return vocab.review(box.conn, box.policy(), args.category, args.threshold)


def _set_mode(args, mode: str) -> dict:
    box = open_box(args)
    with db.transaction(box.conn):
        current = box.policy()["vocabulary"]
        policy.set_rule(box.conn, "vocabulary", {**current, "mode": mode})
    box.write_readme()
    return {"vocabulary": mode, "was": current["mode"]}


def cmd_vocab_lock(args) -> dict:
    return _set_mode(args, "locked")


def cmd_vocab_unlock(args) -> dict:
    return _set_mode(args, "open")


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

    p = add("analyze", cmd_analyze, "analyse files without a box: metadata, keyframes, pHash, optional OCR hint")
    p.add_argument("paths", nargs="+")
    p.add_argument("--ocr", action="store_true", help="also run the RapidOCR hint")

    p = add("frames", cmd_frames, "contact sheet of an image's keyframes, for reading animations in one image")
    p.add_argument("ref", help="a file path, or a staged or stored reference")
    p.add_argument("--out", help="write the sheet here instead of the box's temporary/")

    def value_args(p, with_fields: bool = True):
        p.add_argument("--license", help="licence of the image; 'unknown' when it cannot be found out")
        p.add_argument("--source", help="where the image came from")
        if with_fields:
            p.add_argument("--text", help="all text on the image, verbatim ('' when there is none)")
            p.add_argument("--description", help="what the image shows")
            p.add_argument("--note", help="when to use it")
            p.add_argument("--field", action="append", metavar="NAME=VALUE", help="a field the policy declares")

    p = add("stage", cmd_stage, "copy files into temporary/ and analyse them; nothing is stored yet")
    p.add_argument("paths", nargs="+", help="files (or, with --from, one reference in the other box)")
    p.add_argument("--from", dest="from_box", metavar="BOX", help="stage an item from another box")
    p.add_argument("--auto-cleanup", action="store_true", help="when over a limit, remove expired and then the oldest items")
    value_args(p, with_fields=False)

    add("staged", cmd_staged, "list staged files")

    p = add("commit", cmd_commit, "store a staged file with its tags and fields; every rule is checked first")
    p.add_argument("ref")
    p.add_argument("--tag", action="append", metavar="CATEGORY=VALUE")
    p.add_argument("--define", action="append", nargs=2, metavar=("CATEGORY=VALUE", "DEFINITION"), help="tag it and create the tag with this definition")
    p.add_argument("--auto-cleanup", action="store_true", help="when over a limit, remove expired and then the oldest items")
    value_args(p)

    p = add("show", cmd_show, "show a stored item or a staged file")
    p.add_argument("ref")

    p = add("edit", cmd_edit, "change a stored item's tags and fields")
    p.add_argument("ref")
    p.add_argument("--add-tag", action="append", metavar="CATEGORY=VALUE")
    p.add_argument("--remove-tag", action="append", metavar="CATEGORY=VALUE")
    p.add_argument("--define", action="append", nargs=2, metavar=("CATEGORY=VALUE", "DEFINITION"))
    p.add_argument("--clear", action="append", metavar="FIELD", help="unset an optional field")
    value_args(p)

    p = add("remove", cmd_remove, "delete stored items or staged files")
    p.add_argument("refs", nargs="+")

    p = add("clean", cmd_clean, "remove staged files past the grace period and expired items")
    p.add_argument("--all", action="store_true", help="remove every staged file, however recent")

    group = sub.add_parser("tag", help="list and change tags", parents=[common])
    tsub = group.add_subparsers(dest="action", metavar="<action>", required=True, parser_class=sub._parser_class)
    p = add("list", cmd_tag_list, "list tags with definitions, aliases and counts", tsub)
    p.add_argument("--category")
    p.add_argument("--retired", action="store_true", help="include retired tags")
    p = add("new", cmd_tag_new, "create a tag (the only way in a locked vocabulary)", tsub)
    p.add_argument("category")
    p.add_argument("value")
    p.add_argument("--means", required=True, metavar="DEFINITION")
    p.add_argument("--parent", metavar="VALUE", help="a broader tag in the same category")
    p.add_argument("--alias", action="append", metavar="ALIAS")
    p.add_argument("--lang", help="language tag, only for a phrase kept in its original language")
    p = add("define", cmd_tag_define, "set a tag's definition", tsub)
    p.add_argument("category")
    p.add_argument("value")
    p.add_argument("definition")
    p = add("alias", cmd_tag_alias, "add (or with --remove, drop) aliases of a tag", tsub)
    p.add_argument("category")
    p.add_argument("value")
    p.add_argument("aliases", nargs="+")
    p.add_argument("--remove", action="store_true")
    p = add("rename", cmd_tag_rename, "rename a tag; the old value becomes an alias", tsub)
    p.add_argument("category")
    p.add_argument("old")
    p.add_argument("new")
    p = add("merge", cmd_tag_merge, "move every item from one tag to another; the first becomes an alias", tsub)
    p.add_argument("category")
    p.add_argument("source", metavar="FROM")
    p.add_argument("target", metavar="INTO")
    p = add("retire", cmd_tag_retire, "stop a tag from being used on new items (or --restore it)", tsub)
    p.add_argument("category")
    p.add_argument("value")
    p.add_argument("--restore", action="store_true")
    p = add("parent", cmd_tag_parent, "set a tag's broader tag, or clear it", tsub)
    p.add_argument("category")
    p.add_argument("value")
    p.add_argument("parent", nargs="?")

    group = sub.add_parser("vocab", help="review and lock the vocabulary", parents=[common])
    vsub = group.add_subparsers(dest="action", metavar="<action>", required=True, parser_class=sub._parser_class)
    p = add("review", cmd_vocab_review, "near-twin, undefined and unused tags, for a cleanup pass", vsub)
    p.add_argument("--category")
    p.add_argument("--threshold", type=float, default=0.6, help="similarity from 0 to 1 (default 0.6)")
    add("lock", cmd_vocab_lock, "lock the vocabulary: new tags only through `tag new`", vsub)
    add("unlock", cmd_vocab_unlock, "reopen the vocabulary", vsub)
