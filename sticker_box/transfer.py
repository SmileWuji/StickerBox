"""Transfer between boxes: `stage --from <box> <ref>` stages a stored item of another box here.
The file is analysed again under this box's policy; licence and source carry over, the source's
text, description and note become defaults for `commit`, and its tags are shown as hints only,
since vocabularies differ. The destination validates everything at `commit`, as for any file."""

from pathlib import Path

from . import refs, stage
from .box import Box
from .errors import BoxError


def stage_from(box, other_path: Path, ref: str, license: str | None, source: str | None, auto_cleanup: bool) -> dict:
    other = Box.open(other_path)
    try:
        if other.root == box.root:
            raise BoxError("usage", "--from names this same box")
        _, sha = refs.resolve(other, ref, staged=False)
        row = other.conn.execute("SELECT * FROM item WHERE sha256 = ?", (sha,)).fetchone()
        path = (other.root / row["file"]).resolve()
        if other.persistent.resolve() not in path.parents:
            raise BoxError("invalid", f"the stored path of {sha} is outside its box")
        tags = [f"{r['category']}={r['value']}" for r in other.conn.execute(
            "SELECT t.category, t.value FROM item_tag it JOIN tag t ON t.id = it.tag_id WHERE it.sha256 = ? ORDER BY t.category, t.value", (sha,))]
        fields = {r["name"]: r["value"] for r in other.conn.execute("SELECT name, value FROM item_field WHERE sha256 = ?", (sha,))}
        origin = {"box": str(other.root), "ref": sha, "tags": tags, "text": row["text"], "description": row["description"],
                  "note": row["note"], "fields": fields}
        lic = license if license is not None else row["license"]
        src = source if source is not None else row["source"]
    finally:
        other.close()
    result = stage.stage_file(box, path, lic, src, auto_cleanup)
    if result["status"] in ("staged", "already_staged"):
        sidecar = stage.load_sidecar(box, result["ref"])
        sidecar["origin"] = origin
        stage.write_sidecar(box, sidecar)
        result["origin"] = origin
    return {"results": [result]}
