"""Checks of a file's metadata against the `files` rule; one problem per broken constraint."""


def _kb(n: int) -> str:
    return f"{n / 1024:.0f} KB"


def _against(info: dict, c: dict, scope: str) -> list[dict]:
    out = []
    w, h = info["width"], info["height"]

    def add(constraint: str, message: str):
        out.append({"problem": "file_rule", "rule": f"{scope}.{constraint}", "message": message})

    if c.get("animated") is False and info["animated"]:
        add("animated", "the file is animated, but only static images are accepted")
    if c.get("animated") is True and not info["animated"]:
        add("animated", "the file is static, but only animated images are accepted")
    if "one_side" in c and c["one_side"] not in (w, h):
        add("one_side", f"the image is {w}x{h}; one side must be exactly {c['one_side']} px")
    if "max_side" in c and max(w, h) > c["max_side"]:
        add("max_side", f"the image is {w}x{h}; no side may exceed {c['max_side']} px")
    if "min_side" in c and min(w, h) < c["min_side"]:
        add("min_side", f"the image is {w}x{h}; no side may be under {c['min_side']} px")
    if "max_bytes" in c and info["bytes"] > c["max_bytes"]:
        add("max_bytes", f"the file is {_kb(info['bytes'])}; at most {_kb(c['max_bytes'])} is accepted")
    if "max_duration_ms" in c and (info["duration_ms"] or 0) > c["max_duration_ms"]:
        add("max_duration_ms", f"the animation lasts {info['duration_ms'] / 1000:.2f} s; at most {c['max_duration_ms'] / 1000:g} s is accepted")
    if "max_fps" in c and (info["fps"] or 0) > c["max_fps"] + 0.01:
        add("max_fps", f"the animation runs at {info['fps']:g} fps; at most {c['max_fps']:g} fps is accepted")
    if "codecs" in c and info["format"] == "webm" and (info["codec"] or "unknown") not in c["codecs"]:
        add("codecs", f"the video codec is {info['codec'] or 'unknown'}; it must be {' or '.join(c['codecs'])}")
    if c.get("audio") is False and info["audio"]:
        add("audio", "the file has an audio track; remove it")
    return out


def check_file(files_rule: dict, info: dict) -> list[dict]:
    problems = []
    formats = files_rule["formats"]
    fmt = info["format"]
    if formats is not None and fmt not in formats:
        problems.append({"problem": "file_rule", "rule": "formats", "message": f"{fmt.upper()} is not accepted; accepted: {', '.join(f.upper() for f in formats)}"})
    elif formats is not None:
        problems += _against(info, formats[fmt], fmt)
    problems += _against(info, files_rule["all"], "all")
    return problems
