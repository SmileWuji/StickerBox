import copy
import json
import re
import sqlite3

from . import clock
from .errors import BoxError

RULES = ("fields", "categories", "files", "vocabulary", "duplicates", "limits", "retention", "analysis")
CORE_FIELDS = ("license", "source", "text", "description", "note")
FORMATS = ("webp", "png", "jpeg", "gif", "webm")
MODES = ("free", "open", "locked")
FIELD_NAME = re.compile(r"[a-z][a-z0-9_]{0,31}")
CATEGORY_NAME = re.compile(r"[\w\-]{1,32}")
CODEC = re.compile(r"[a-z0-9]{1,16}")

DEFAULTS = {
    "fields": {},
    "categories": {},
    "files": {"formats": None, "all": {}},
    "vocabulary": {"mode": "free", "default_category": None},
    "duplicates": {"phash_max_distance": 6, "sift": None},
    "limits": {"max_bytes": None, "max_items": None},
    "retention": {"expire_after_minutes": None, "staged_grace_minutes": 60},
    "analysis": {"ocr_hint": False, "keyframe_drop_thr": 0.10, "max_keyframes": 64, "sift_keyframes": 4},
}
SIFT_DEFAULTS = {"keypoints": 300, "min_inliers": 12, "ratio": 0.75}


def _fail(rule: str, message: str):
    raise BoxError("invalid_policy", f"{rule}: {message}", rule=rule)


def _keys(rule: str, obj, allowed, where: str = "") -> dict:
    if not isinstance(obj, dict):
        _fail(rule, f"{where or 'params'} must be an object")
    unknown = sorted(set(obj) - set(allowed))
    if unknown:
        _fail(rule, f"unknown key(s) {', '.join(unknown)} in {where or 'params'}; allowed: {', '.join(sorted(allowed))}")
    return obj


MAX_INT = 2 ** 53


def _int(rule, value, name, lo=0, hi=MAX_INT, nullable=False):
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < lo or (hi is not None and value > hi):
        _fail(rule, f"{name} must be an integer from {lo}" + (f" to {hi}" if hi is not None else "") + (" or null" if nullable else ""))
    return value


def _num(rule, value, name, lo, hi):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not lo <= value <= hi:
        _fail(rule, f"{name} must be a number from {lo} to {hi}")
    return float(value)


def _bool(rule, value, name):
    if not isinstance(value, bool):
        _fail(rule, f"{name} must be true or false")
    return value


def _text(rule, value, name, limit=500):
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 or ord(c) == 127 for c in value):
        _fail(rule, f"{name} must be one line of at most {limit} characters")
    return value


def _fields(p: dict) -> dict:
    out = {}
    for name, spec in p.items():
        if not FIELD_NAME.fullmatch(name):
            _fail("fields", f"field name {name!r} must match {FIELD_NAME.pattern}")
        spec = _keys("fields", spec or {}, {"required", "allow_empty", "description"}, name)
        out[name] = {
            "required": _bool("fields", spec.get("required", False), f"{name}.required"),
            "allow_empty": _bool("fields", spec.get("allow_empty", False), f"{name}.allow_empty"),
            "description": _text("fields", spec.get("description", ""), f"{name}.description"),
        }
    for name in CORE_FIELDS:
        out.setdefault(name, {"required": False, "allow_empty": False, "description": ""})
    if not out["license"]["required"] or out["license"]["allow_empty"]:
        _fail("fields", "license is always required and never empty (use the value 'unknown' when it is not known)")
    return out


def _categories(p: dict) -> dict:
    out = {}
    for name, spec in p.items():
        if not CATEGORY_NAME.fullmatch(name):
            _fail("categories", f"category name {name!r} must be 1 to 32 letters, digits, '_' or '-'")
        spec = _keys("categories", spec or {}, {"description", "multiple", "required"}, name)
        out[name] = {
            "description": _text("categories", spec.get("description", ""), f"{name}.description"),
            "multiple": _bool("categories", spec.get("multiple", True), f"{name}.multiple"),
            "required": _bool("categories", spec.get("required", False), f"{name}.required"),
        }
    return out


CONSTRAINTS = {"animated", "one_side", "max_side", "min_side", "max_bytes", "max_duration_ms", "max_fps", "codecs", "audio"}


def _constraints(spec, where: str) -> dict:
    spec = _keys("files", spec or {}, CONSTRAINTS, where)
    out = {}
    for key, value in spec.items():
        if key in ("animated", "audio"):
            if value is not None:
                out[key] = _bool("files", value, f"{where}.{key}")
        elif key == "codecs":
            if not isinstance(value, list) or not all(isinstance(c, str) and CODEC.fullmatch(c.lower()) for c in value):
                _fail("files", f"{where}.codecs must be a list of codec names such as [\"vp9\"]")
            out[key] = [c.lower() for c in value]
        elif key == "max_fps":
            out[key] = _num("files", value, f"{where}.max_fps", 1, 1000)
        else:
            out[key] = _int("files", value, f"{where}.{key}", 1)
    return out


def _files(p: dict) -> dict:
    formats = p.get("formats")
    if formats is not None:
        _keys("files", formats, FORMATS, "formats")
        formats = {fmt: _constraints(spec, fmt) for fmt, spec in formats.items()}
        if not formats:
            _fail("files", "formats must list at least one format, or be null for any supported format")
    return {"formats": formats, "all": _constraints(p.get("all", {}), "all")}


def _vocabulary(p: dict) -> dict:
    mode = p.get("mode", "free")
    if mode not in MODES:
        _fail("vocabulary", f"mode must be one of {', '.join(MODES)}")
    default = p.get("default_category")
    if default is not None:
        _text("vocabulary", default, "default_category", 32)
    return {"mode": mode, "default_category": default}


def _duplicates(p: dict) -> dict:
    sift = p.get("sift")
    if sift is not None:
        sift = {**SIFT_DEFAULTS, **_keys("duplicates", sift, set(SIFT_DEFAULTS), "sift")}
        _int("duplicates", sift["keypoints"], "sift.keypoints", 50, 2000)
        _int("duplicates", sift["min_inliers"], "sift.min_inliers", 4, 1000)
        sift["ratio"] = _num("duplicates", sift["ratio"], "sift.ratio", 0.5, 0.95)
    return {
        "phash_max_distance": _int("duplicates", p.get("phash_max_distance", 6), "phash_max_distance", 0, 32),
        "sift": sift,
    }


def _limits(p: dict) -> dict:
    return {
        "max_bytes": _int("limits", p.get("max_bytes"), "max_bytes", 1, 2 ** 50, nullable=True),
        "max_items": _int("limits", p.get("max_items"), "max_items", 1, 10 ** 9, nullable=True),
    }


def _retention(p: dict) -> dict:
    return {
        "expire_after_minutes": _int("retention", p.get("expire_after_minutes"), "expire_after_minutes", 1, 100 * 525_600, nullable=True),
        "staged_grace_minutes": _int("retention", p.get("staged_grace_minutes", 60), "staged_grace_minutes", 0, 525_600),
    }


def _analysis(p: dict) -> dict:
    d = DEFAULTS["analysis"]
    return {
        "ocr_hint": _bool("analysis", p.get("ocr_hint", d["ocr_hint"]), "ocr_hint"),
        "keyframe_drop_thr": _num("analysis", p.get("keyframe_drop_thr", d["keyframe_drop_thr"]), "keyframe_drop_thr", 0, 1),
        "max_keyframes": _int("analysis", p.get("max_keyframes", d["max_keyframes"]), "max_keyframes", 1, 256),
        "sift_keyframes": _int("analysis", p.get("sift_keyframes", d["sift_keyframes"]), "sift_keyframes", 1, 16),
    }


VALIDATORS = {
    "fields": _fields,
    "categories": _categories,
    "files": _files,
    "vocabulary": _vocabulary,
    "duplicates": _duplicates,
    "limits": _limits,
    "retention": _retention,
    "analysis": _analysis,
}
TOP_KEYS = {
    "files": {"formats", "all"},
    "vocabulary": {"mode", "default_category"},
    "duplicates": {"phash_max_distance", "sift"},
    "limits": {"max_bytes", "max_items"},
    "retention": {"expire_after_minutes", "staged_grace_minutes"},
    "analysis": set(DEFAULTS["analysis"]),
}


def validate_rule(name: str, params) -> dict:
    if name not in VALIDATORS:
        raise BoxError("invalid_policy", f"unknown rule {name!r}; rules: {', '.join(RULES)}", rule=name)
    if name in TOP_KEYS:
        _keys(name, params, TOP_KEYS[name])
    elif not isinstance(params, dict):
        _fail(name, "params must be an object")
    return VALIDATORS[name](params)


SIFT_BUDGET = 4800


def cross_check(policy: dict) -> None:
    sift = policy["duplicates"]["sift"]
    if sift and sift["keypoints"] * policy["analysis"]["sift_keyframes"] > SIFT_BUDGET:
        _fail("duplicates", f"sift.keypoints x analysis.sift_keyframes is limited to {SIFT_BUDGET} (matching cost grows with both)")
    default = policy["vocabulary"]["default_category"]
    if default is not None and default not in policy["categories"]:
        _fail("vocabulary", f"default_category {default!r} is not a category; categories: {', '.join(policy['categories']) or 'none'}")
    if policy["vocabulary"]["mode"] != "free" and not policy["categories"]:
        _fail("vocabulary", "open and locked vocabularies need at least one category")


def validate(policy: dict) -> dict:
    out = {name: validate_rule(name, policy.get(name, copy.deepcopy(DEFAULTS[name]))) for name in RULES}
    cross_check(out)
    return out


def load(conn: sqlite3.Connection) -> dict:
    stored = {row["name"]: json.loads(row["params"]) for row in conn.execute("SELECT name, params FROM policy_rule")}
    if isinstance(stored.get("duplicates"), dict):
        stored["duplicates"].pop("on_duplicate", None)
    return {name: stored.get(name, copy.deepcopy(DEFAULTS[name])) for name in RULES}


def store_all(conn: sqlite3.Connection, policy: dict) -> None:
    for name in RULES:
        conn.execute(
            "INSERT INTO policy_rule (name, params) VALUES (?, ?) ON CONFLICT (name) DO UPDATE SET params = excluded.params",
            (name, json.dumps(policy[name], ensure_ascii=False)),
        )


def set_rule(conn: sqlite3.Connection, name: str, params) -> dict:
    """Replaces one rule after validating it against the rest of the policy. Caller holds a transaction."""
    current = load(conn)
    new = validate_rule(name, params)
    candidate = {**current, name: new}
    cross_check(candidate)
    old = json.dumps(current[name], ensure_ascii=False, sort_keys=True)
    store_all(conn, {name_: candidate[name_] for name_ in RULES})
    conn.execute(
        "INSERT INTO policy_log (at, name, old, new) VALUES (?, ?, ?, ?)",
        (clock.stamp(), name, old, json.dumps(new, ensure_ascii=False, sort_keys=True)),
    )
    return new


def _kb(n: int) -> str:
    return f"{n // 1024} KB" if n % 1024 == 0 else f"{n} bytes"


def _describe_constraints(c: dict) -> str:
    parts = []
    if c.get("animated") is True:
        parts.append("animated only")
    elif c.get("animated") is False:
        parts.append("static only")
    if "one_side" in c and "max_side" in c and c["one_side"] == c["max_side"]:
        parts.append(f"one side exactly {c['one_side']} px, the other at most {c['max_side']} px")
    else:
        if "one_side" in c:
            parts.append(f"one side exactly {c['one_side']} px")
        if "max_side" in c:
            parts.append(f"no side over {c['max_side']} px")
    if "min_side" in c:
        parts.append(f"no side under {c['min_side']} px")
    if "max_bytes" in c:
        parts.append(f"at most {_kb(c['max_bytes'])}")
    if "max_duration_ms" in c:
        parts.append(f"at most {c['max_duration_ms'] / 1000:g} s long")
    if "max_fps" in c:
        parts.append(f"at most {c['max_fps']:g} fps")
    if "codecs" in c:
        parts.append(f"codec {' or '.join(c['codecs'])}")
    if c.get("audio") is False:
        parts.append("no audio")
    return "; ".join(parts)


def _safe(text: str) -> str:
    from .manual import cell

    return cell(text)


def describe(policy: dict) -> dict[str, list[str]]:
    """Plain-language statements of every rule, for README.md and `info`."""
    out: dict[str, list[str]] = {}
    files = policy["files"]
    lines = []
    if files["formats"] is None:
        lines.append("Any supported format (WEBP, PNG, JPEG, GIF, WEBM), at any size.")
    else:
        lines.append("Accepted formats: " + ", ".join(fmt.upper() for fmt in files["formats"]) + ". Convert files before adding them; the box does not convert.")
        for fmt, c in files["formats"].items():
            text = _describe_constraints(c)
            lines.append(f"{fmt.upper()}: {text}." if text else f"{fmt.upper()}: no further limits.")
    if files["all"]:
        lines.append(f"Every file: {_describe_constraints(files['all'])}.")
    out["files"] = lines

    lines = []
    for name, spec in policy["fields"].items():
        state = "required" if spec["required"] else "optional"
        if spec["required"] and spec["allow_empty"]:
            state = "required, may be empty"
        lines.append(f"`{name}` ({state})" + (f": {_safe(spec['description'])}" if spec["description"] else ""))
    out["fields"] = lines

    lines = []
    for name, spec in policy["categories"].items():
        count = "one or more values" if spec["multiple"] else "one value"
        need = "required" if spec["required"] else "optional"
        lines.append(f"`{name}` ({need}, {count})" + (f": {_safe(spec['description'])}" if spec["description"] else ""))
    mode = policy["vocabulary"]["mode"]
    lines.append({
        "free": "Vocabulary is free: any tag may be used and is created on first use.",
        "open": "Vocabulary is open: a new tag may be created while adding an image, and must come with a definition. Reuse existing tags whenever one fits.",
        "locked": "Vocabulary is locked: only existing tags may be used; a new tag needs `sticker-box tag new` with a definition.",
    }[mode])
    if policy["vocabulary"]["default_category"]:
        lines.append(f"A tag given without a category goes into `{policy['vocabulary']['default_category']}`.")
    out["tags"] = lines

    dup = policy["duplicates"]
    lines = [f"Identical files are never stored twice. Images within {dup['phash_max_distance']} bits of perceptual hash count as near-duplicates."]
    if dup["sift"]:
        lines.append(f"Local features (SIFT, {dup['sift']['keypoints']} keypoints) find crops, zooms and rotations of stored images (at least {dup['sift']['min_inliers']} matching points).")
    lines.append("Duplicates and related images are reported, never refused or removed by the tool: each report comes "
                 "with suggested `sticker-box remove` commands, and whoever adds the image decides what to keep.")
    out["duplicates"] = lines

    lim, ret = policy["limits"], policy["retention"]
    lines = []
    if lim["max_bytes"]:
        lines.append(f"At most {lim['max_bytes'] / (1024 * 1024):g} MB of images.")
    if lim["max_items"]:
        lines.append(f"At most {lim['max_items']} images.")
    if ret["expire_after_minutes"]:
        lines.append(f"Images expire {ret['expire_after_minutes']} minutes after they are added and are removed by `sticker-box clean`.")
    lines.append(f"Staged files older than {ret['staged_grace_minutes']} minutes are removed by `sticker-box clean`.")
    if lim["max_bytes"] or lim["max_items"]:
        lines.append("A write that would pass a limit fails; run `sticker-box clean`, or pass `--auto-cleanup` to remove expired and then the oldest images.")
    out["limits"] = lines
    return out
