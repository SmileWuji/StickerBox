"""Which writing systems a piece of text uses, to warn when a tag is not in the box's language.
A warning only: kanji-only Japanese is indistinguishable from Chinese by script."""

EXPECTED = {
    "zh": {"han"},
    "ja": {"han", "kana"},
    "ko": {"hangul", "han"},
}


def script_of(ch: str) -> str | None:
    o = ord(ch)
    if 0x3040 <= o <= 0x30FF or 0x31F0 <= o <= 0x31FF or 0xFF66 <= o <= 0xFF9D:
        return "kana"
    if 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or 0x20000 <= o <= 0x2FA1F or 0xF900 <= o <= 0xFAFF:
        return "han"
    if 0xAC00 <= o <= 0xD7AF or 0x1100 <= o <= 0x11FF or 0x3130 <= o <= 0x318F:
        return "hangul"
    if ch.isalpha():
        if o < 0x250 or 0x1E00 <= o <= 0x1EFF:
            return "latin"
        if 0x0400 <= o <= 0x04FF:
            return "cyrillic"
        return "other"
    return None


def scripts_in(text: str) -> set[str]:
    return {s for s in (script_of(ch) for ch in text) if s}


def expected(language: str) -> set[str]:
    base = language.split("-", 1)[0].lower()
    if base in EXPECTED:
        return EXPECTED[base]
    if base in ("ru", "uk", "bg", "sr"):
        return {"cyrillic"}
    return {"latin"}


def mismatch(text: str, language: str) -> str | None:
    stray = scripts_in(text) - expected(language)
    if not stray:
        return None
    return (f"written in {', '.join(sorted(stray))} script, but the box language is {language}; keep tags in one "
            "language unless the phrase only exists in its original language")
