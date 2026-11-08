import re

from .errors import BoxError

HEX = re.compile(r"^[0-9a-f]{8,64}$")


def looks_like_ref(text: str) -> bool:
    return bool(HEX.match(text.lower()))


def staged_shas(box) -> list[str]:
    return sorted(p.stem for p in box.temporary.glob("*.json") if HEX.match(p.stem) and len(p.stem) == 64)


def resolve(box, ref: str, staged: bool = True, items: bool = True) -> tuple[str, str]:
    """('item' | 'staged', sha256) for a full sha256 or a unique prefix of at least 8 hex digits."""
    ref = ref.strip().lower()
    if not HEX.match(ref):
        raise BoxError("invalid_ref", f"{ref!r} is not a reference: give a sha256 or a prefix of at least 8 hex digits")
    found: list[tuple[str, str]] = []
    if items:
        rows = box.conn.execute("SELECT sha256 FROM item WHERE sha256 >= ? AND sha256 < ? LIMIT 10", (ref, ref + "g")).fetchall()
        found += [("item", r["sha256"]) for r in rows]
    if staged:
        found += [("staged", sha) for sha in staged_shas(box) if sha.startswith(ref) and ("item", sha) not in found]
    if not found:
        where = " and ".join(w for w, on in (("stored items", items), ("staged files", staged)) if on)
        raise BoxError("not_found", f"no {where} match {ref}", ref=ref)
    if len(found) > 1:
        raise BoxError("ambiguous_ref", f"{ref} matches {len(found)} entries; give more digits", matches=[f"{k}:{s}" for k, s in found])
    return found[0]
