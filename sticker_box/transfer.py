"""Transfer between boxes: `stage --from <box> <ref>` stages a stored item of another box here.
The file is analysed again under this box's policy; licence and source carry over, the source's
text, description and note become defaults for `commit`, and its tags are shown as hints only,
since vocabularies differ. The destination validates everything at `commit`, as for any file.

The other box may have been made by someone else, so it is opened read-only with a time limit,
its file path must be one the tool writes, the file is copied without following a symlink, and
every value carried over is type- and length-checked."""

from pathlib import Path

from . import paths, refs, stage
from .box import Box
from .errors import BoxError
from .items import FIELD_LIMIT, LIMITS
from .policy import FIELD_NAME


def _text(value, limit: int):
    return value if isinstance(value, str) and len(value) <= limit else None


def stage_from(box, other_path: Path, ref: str, license: str | None, source: str | None, auto_cleanup: bool) -> dict:
    other = Box.open(other_path, readonly=True)
    dropped = []
    try:
        if other.root == box.root:
            raise BoxError("usage", "--from names this same box")
        _, sha = refs.resolve(other, ref, staged=False)
        row = other.conn.execute("SELECT * FROM item WHERE sha256 = ?", (sha,)).fetchone()
        path = paths.stored_path(other, row)
        tags = []
        for r in other.conn.execute(
                "SELECT t.category, t.value FROM item_tag it JOIN tag t ON t.id = it.tag_id WHERE it.sha256 = ? ORDER BY t.category, t.value LIMIT 64", (sha,)):
            if _text(r["category"], 32) and _text(r["value"], 64):
                tags.append(f"{r['category']}={r['value']}")
        fields = {}
        for r in other.conn.execute("SELECT name, value FROM item_field WHERE sha256 = ? LIMIT 64", (sha,)):
            if isinstance(r["name"], str) and FIELD_NAME.fullmatch(r["name"]) and _text(r["value"], FIELD_LIMIT) is not None:
                fields[r["name"]] = r["value"]
        values = {}
        for key in ("text", "description", "note", "license", "source"):
            values[key] = _text(row[key], LIMITS[key])
            if row[key] is not None and values[key] is None:
                dropped.append(key)
        origin = {"box": str(other.root), "ref": sha, "tags": tags, "text": values["text"], "description": values["description"],
                  "note": values["note"], "fields": fields}
        lic = license if license is not None else values["license"]
        src = source if source is not None else values["source"]
    except BoxError:
        raise
    except Exception as err:
        raise BoxError("unsafe_box", f"cannot read {other_path} as a box ({type(err).__name__})") from None
    finally:
        other.close()
    result = stage.stage_file(box, path, lic, src, auto_cleanup, nofollow=True)
    if result["status"] in ("staged", "already_staged"):
        sidecar = stage.load_sidecar(box, result["ref"])
        sidecar["origin"] = origin
        stage.write_sidecar(box, sidecar)
        result["origin"] = origin
    if dropped:
        result["warnings"] = [f"the source's {', '.join(dropped)} had an unexpected type or length and was not carried over"]
    return {"results": [result]}
