"""Staging: the upload step. A staged file sits in temporary/ as <sha256>.<ext> next to a
<sha256>.json sidecar holding its analysis; the database knows nothing about it until `commit`."""

import json
import os
import shutil
import uuid
from pathlib import Path

from . import analysis, clock, dupes, media, rules
from .errors import BoxError

SIDECAR_VERSION = 1


def sidecar_path(box, sha: str) -> Path:
    return box.temporary / f"{sha}.json"


def load_sidecar(box, sha: str) -> dict:
    path = sidecar_path(box, sha)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BoxError("not_found", f"{sha} is not staged (it may have been cleaned); stage the file again", ref=sha) from None


def write_sidecar(box, data: dict) -> None:
    path = sidecar_path(box, data["sha256"])
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def staged_file(box, sidecar: dict) -> Path:
    return box.temporary / sidecar["file"]


def requirements(policy: dict) -> dict:
    return {
        "fields": [name for name, spec in policy["fields"].items() if spec["required"]],
        "categories": [name for name, spec in policy["categories"].items() if spec["required"]],
        "vocabulary": policy["vocabulary"]["mode"],
    }


def duplicate_report(box, matches: list[dict]) -> list[dict]:
    out = []
    for m in matches:
        row = box.conn.execute("SELECT file FROM item WHERE sha256 = ?", (m["ref"],)).fetchone()
        out.append({**m, "file": str(box.root / row["file"]) if row else None})
    return out


def analyse_into_sidecar(box, policy: dict, sha: str, file_name: str, extra: dict) -> dict:
    path = box.temporary / file_name
    params = policy["analysis"]
    result = analysis.analyze(path, params, with_ocr=params["ocr_hint"])
    summary = result.summary()
    if sha != summary["sha256"]:
        raise BoxError("changed", "the staged file changed while it was being analysed; stage it again")
    sidecar = {
        "version": SIDECAR_VERSION,
        "sha256": sha,
        "file": file_name,
        "staged_at": clock.stamp(),
        "analysis_params": params,
        **{k: v for k, v in summary.items() if k != "sha256"},
        **extra,
    }
    if policy["duplicates"]["sift"]:
        from . import features

        features.stage(box, policy, result, sidecar)
    write_sidecar(box, sidecar)
    return sidecar


def report(box, policy: dict, sidecar: dict, status: str) -> dict:
    matches = dupes.find(box.conn, dupes.hex_hashes(sidecar), sidecar["media"]["animated"], policy["duplicates"]["phash_max_distance"])
    if sidecar.get("sift_matches"):
        seen = {m["ref"] for m in matches}
        matches += [m for m in sidecar["sift_matches"] if m["ref"] not in seen]
    sha = sidecar["sha256"]
    return {
        "status": status,
        "ref": sha,
        "name": sidecar.get("name"),
        "file": str(staged_file(box, sidecar)),
        "media": sidecar["media"],
        "keyframes": len(sidecar["keyframes"]),
        "ocr_hint": sidecar.get("ocr_hint"),
        "license": sidecar.get("license"),
        "source": sidecar.get("source"),
        "origin": sidecar.get("origin"),
        "file_problems": rules.check_file(policy["files"], sidecar["media"]),
        "duplicates": duplicate_report(box, matches),
        "requires": requirements(policy),
        "next": f"sticker-box commit {sha[:12]} --tag category=value ...",
    }


MAX_TEMPORARY_BYTES = int(os.environ.get("STICKER_BOX_MAX_TEMPORARY_MB", "1024")) * 1024 * 1024


def _temporary_room(box, adding: int) -> None:
    used = sum(p.stat().st_size for p in box.temporary.iterdir() if p.is_file())
    if used + adding > MAX_TEMPORARY_BYTES:
        from .errors import EXIT_LIMIT

        raise BoxError("temporary_full", f"temporary/ holds {used} bytes and the limit is {MAX_TEMPORARY_BYTES}; run `sticker-box clean`",
                       exit_code=EXIT_LIMIT, used=used, limit=MAX_TEMPORARY_BYTES)


def stage_file(box, path: Path, license: str | None = None, source: str | None = None, auto_cleanup: bool = False) -> dict:
    """Never deletes stored items. Over a box limit it fails (exit 3) unless auto_cleanup, in
    which case it stages and lists what `commit --auto-cleanup` would remove."""
    from . import limits

    fmt = media.detect(path)
    policy = box.policy()
    size = path.stat().st_size
    _temporary_room(box, size)
    tmp = box.temporary / f".incoming-{uuid.uuid4().hex}.part"
    try:
        shutil.copyfile(path, tmp)
        sha = analysis.sha256_file(tmp)
        stored = box.conn.execute("SELECT file FROM item WHERE sha256 = ?", (sha,)).fetchone()
        if stored:
            return {"status": "already_stored", "ref": sha, "name": path.name, "file": str(box.root / stored["file"])}
        planned = limits.plan_room(box, policy, size, 1, auto_cleanup)
        file_name = f"{sha}.{media.EXTENSIONS[fmt]}"
        existing = sidecar_path(box, sha)
        if existing.is_file() and (box.temporary / file_name).is_file():
            sidecar = load_sidecar(box, sha)
            changed = False
            for key, value in (("license", license), ("source", source)):
                if value is not None and sidecar.get(key) != value:
                    sidecar[key] = value
                    changed = True
            if sidecar.get("extractor") != analysis.EXTRACTOR or sidecar.get("analysis_params") != policy["analysis"]:
                sidecar = analyse_into_sidecar(box, policy, sha, file_name, {k: sidecar.get(k) for k in ("name", "license", "source", "origin")})
            elif changed:
                write_sidecar(box, sidecar)
            return {**report(box, policy, sidecar, "already_staged"), "commit_would_remove": planned or None}
        os.replace(tmp, box.temporary / file_name)
    finally:
        tmp.unlink(missing_ok=True)
    try:
        sidecar = analyse_into_sidecar(box, policy, sha, file_name, {"name": path.name, "license": license, "source": source, "origin": None})
    except BaseException:
        for leftover in box.temporary.glob(f"{sha}.*"):
            leftover.unlink(missing_ok=True)
        raise
    return {**report(box, policy, sidecar, "staged"), "commit_would_remove": planned or None}


def ensure_fresh(box, policy: dict, sha: str) -> dict:
    """The sidecar, re-analysed when the extractor or the analysis policy changed since staging."""
    sidecar = load_sidecar(box, sha)
    if not staged_file(box, sidecar).is_file():
        raise BoxError("not_found", f"the staged file for {sha} is gone (temporary/ was cleaned); stage it again", ref=sha)
    stale = sidecar.get("extractor") != analysis.EXTRACTOR or sidecar.get("analysis_params") != policy["analysis"]
    if policy["duplicates"]["sift"]:
        from . import features

        stale = stale or not features.npz_path(box, sha).is_file() or (sidecar.get("features") or {}).get("extractor") != features.EXTRACTOR
    if stale:
        keep = {k: sidecar.get(k) for k in ("name", "license", "source", "origin")}
        sidecar = analyse_into_sidecar(box, policy, sha, sidecar["file"], keep)
    return sidecar


def remove(box, sha: str) -> None:
    sidecar = load_sidecar(box, sha)
    staged_file(box, sidecar).unlink(missing_ok=True)
    for extra in box.temporary.glob(f"{sha}.*"):
        extra.unlink(missing_ok=True)


def listing(box) -> list[dict]:
    from .refs import staged_shas

    out = []
    for sha in staged_shas(box):
        try:
            sidecar = load_sidecar(box, sha)
        except (BoxError, json.JSONDecodeError):
            continue
        hint = (sidecar.get("ocr_hint") or {}).get("text") or ""
        out.append({
            "ref": sha,
            "name": sidecar.get("name"),
            "format": sidecar["media"]["format"],
            "animated": sidecar["media"]["animated"],
            "staged_at": sidecar.get("staged_at"),
            "ocr_hint": hint[:80],
            "file": str(staged_file(box, sidecar)),
        })
    out.sort(key=lambda r: r["staged_at"] or "")
    return out
