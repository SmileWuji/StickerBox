"""Staging: the upload step. A staged file sits in temporary/ as <sha256>.<ext> next to a
<sha256>.json sidecar holding its analysis; the database knows nothing about it until `commit`."""

import json
import os
import uuid
from pathlib import Path

from . import analysis, clock, dupes, media, paths, rules
from .errors import BoxError

SIDECAR_VERSION = 1
SIDECAR_LIMIT = 2_000_000


def sidecar_path(box, sha: str) -> Path:
    return box.temporary / f"{paths.check_sha(sha)}.json"


def _corrupt(sha: str, why: str) -> BoxError:
    return BoxError("corrupt_staging", f"the staging data for {sha[:12]} is not the tool's ({why}); remove it with `sticker-box remove {sha[:12]}` and stage the file again", ref=sha)


def load_sidecar(box, sha: str) -> dict:
    """The sidecar, checked: its sha256 and file name must be the ones derived from `sha`, so a
    planted sidecar cannot name a path outside temporary/."""
    path = sidecar_path(box, sha)
    try:
        if path.is_symlink() or path.stat().st_size > SIDECAR_LIMIT:
            raise _corrupt(sha, "unsafe file")
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise BoxError("not_found", f"{sha} is not staged (it may have been cleaned); stage the file again", ref=sha) from None
    except (ValueError, UnicodeDecodeError):
        raise _corrupt(sha, "not JSON") from None
    if not isinstance(data, dict) or data.get("sha256") != sha:
        raise _corrupt(sha, "wrong sha256")
    if data.get("file") not in {paths.staged_name(sha, ext) for ext in paths.EXTS}:
        raise _corrupt(sha, "wrong file name")
    m = data.get("media")
    needed = {"format": str, "width": int, "height": int, "animated": bool, "frames": int, "bytes": int}
    if not isinstance(m, dict) or any(not isinstance(m.get(k), t) for k, t in needed.items()) \
            or not isinstance(data.get("keyframes"), list) or not data["keyframes"]:
        raise _corrupt(sha, "no analysis")
    try:
        [int(k["phash"], 16) for k in data["keyframes"]]
        int(data["phash"], 16)
    except (KeyError, TypeError, ValueError):
        raise _corrupt(sha, "bad hashes") from None
    return data


def write_sidecar(box, data: dict) -> None:
    path = sidecar_path(box, data["sha256"])
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def staged_file(box, sidecar: dict) -> Path:
    sha = paths.check_sha(sidecar["sha256"])
    ext = str(sidecar["file"]).rsplit(".", 1)[-1]
    path = box.temporary / paths.staged_name(sha, ext)
    if path.is_symlink():
        raise _corrupt(sha, "the staged file is a symbolic link")
    return path


def remove_extras(box, sha: str) -> None:
    """Every regular file temporary/ holds for `sha`; anything else planted there is left alone."""
    paths.check_sha(sha)
    for extra in box.temporary.glob(f"{sha}.*"):
        if extra.is_symlink() or extra.is_file():
            extra.unlink(missing_ok=True)


def requirements(policy: dict) -> dict:
    return {
        "fields": [name for name, spec in policy["fields"].items() if spec["required"]],
        "categories": [name for name, spec in policy["categories"].items() if spec["required"]],
        "vocabulary": policy["vocabulary"]["mode"],
    }


def duplicate_report(box, matches: list[dict], new_ref: str | None = None, new_media: dict | None = None, staged: bool = True) -> list[dict]:
    out = []
    for m in matches:
        row = box.conn.execute("SELECT sha256, file FROM item WHERE sha256 = ?", (m["ref"],)).fetchone()
        entry = {**m, "file": paths.safe_stored_str(box, row) if row else None}
        if new_ref and new_media:
            entry["suggested"] = dupes.suggest(box, new_ref, new_media, m, staged)
        out.append(entry)
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
        "duplicates": duplicate_report(box, matches, sha, sidecar["media"], staged=True),
        "requires": requirements(policy),
        "next": f"sticker-box commit {sha[:12]} --tag category=value ...",
    }


MAX_TEMPORARY_BYTES = int(os.environ.get("STICKER_BOX_MAX_TEMPORARY_MB", "1024")) * 1024 * 1024


def _size(path: Path) -> int:
    try:
        return path.lstat().st_size
    except FileNotFoundError:
        return 0


def _temporary_room(box, adding: int) -> None:
    used = sum(_size(p) for p in box.temporary.iterdir())
    if used + adding > MAX_TEMPORARY_BYTES:
        from .errors import EXIT_LIMIT

        raise BoxError("temporary_full", f"temporary/ holds {used} bytes and the limit is {MAX_TEMPORARY_BYTES}; run `sticker-box clean`",
                       exit_code=EXIT_LIMIT, used=used, limit=MAX_TEMPORARY_BYTES)


def copy_in(source: Path, dest: Path, box, nofollow: bool = False) -> int:
    """Copies a regular file into the box before anything inspects it, so what is checked is what
    is stored. With nofollow (files taken from another box) the file itself may not be a symlink."""
    import stat

    flags = os.O_RDONLY | os.O_NONBLOCK | (os.O_NOFOLLOW if nofollow else 0)
    try:
        fd = os.open(source, flags)
    except FileNotFoundError:
        raise BoxError("not_found", f"{source} is not a file") from None
    except OSError as err:
        raise BoxError("not_found", f"cannot read {source}: {err.strerror}") from None
    st = os.fstat(fd)
    if not stat.S_ISREG(st.st_mode):
        os.close(fd)
        raise BoxError("not_found", f"{source} is not a regular file")
    os.set_blocking(fd, True)
    with os.fdopen(fd, "rb") as src:
        if st.st_size > media.MAX_FILE_BYTES:
            raise BoxError("file_too_large", f"{source.name} is {st.st_size} bytes; the tool reads at most {media.MAX_FILE_BYTES}", bytes=st.st_size)
        _temporary_room(box, st.st_size)
        copied = 0
        with open(dest, "wb") as out:
            while chunk := src.read(1 << 20):
                copied += len(chunk)
                if copied > media.MAX_FILE_BYTES:
                    raise BoxError("file_too_large", f"{source.name} grew past {media.MAX_FILE_BYTES} bytes while being read")
                out.write(chunk)
    return copied


def stage_file(box, path: Path, license: str | None = None, source: str | None = None, auto_cleanup: bool = False,
               nofollow: bool = False) -> dict:
    """Never deletes stored items. Over a box limit it fails (exit 3) unless auto_cleanup, in
    which case it stages and lists what `commit --auto-cleanup` would remove."""
    from . import limits

    policy = box.policy()
    tmp = box.temporary / f".incoming-{uuid.uuid4().hex}.part"
    try:
        size = copy_in(path, tmp, box, nofollow)
        try:
            fmt = media.detect(tmp)
        except BoxError as err:
            err.message = err.message.replace(tmp.name, path.name)
            raise
        sha = analysis.sha256_file(tmp)
        stored = box.conn.execute("SELECT sha256, file FROM item WHERE sha256 = ?", (sha,)).fetchone()
        if stored:
            return {"status": "already_stored", "ref": sha, "name": path.name, "file": paths.safe_stored_str(box, stored)}
        planned = limits.plan_room(box, policy, size, 1, auto_cleanup)
        file_name = paths.staged_name(sha, media.EXTENSIONS[fmt])
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
        remove_extras(box, sha)
        raise
    return {**report(box, policy, sidecar, "staged"), "commit_would_remove": planned or None}


def ensure_fresh(box, policy: dict, sha: str) -> dict:
    """The sidecar, re-analysed when the extractor or the analysis policy changed since staging."""
    sidecar = load_sidecar(box, sha)
    if not staged_file(box, sidecar).is_file():
        raise BoxError("not_found", f"the staged file for {sha} is gone (temporary/ was cleaned); stage it again", ref=sha)
    stale = sidecar.get("extractor") != analysis.EXTRACTOR or sidecar.get("analysis_params") != policy["analysis"]
    if policy["duplicates"]["sift"] and not stale:
        from . import features

        stale = (sidecar.get("features") or {}).get("extractor") != features.EXTRACTOR
        try:
            features.load(features.npz_path(box, sha))
        except BoxError:
            stale = True
    if stale:
        keep = {k: sidecar.get(k) for k in ("name", "license", "source", "origin")}
        sidecar = analyse_into_sidecar(box, policy, sha, sidecar["file"], keep)
    return sidecar


def remove(box, sha: str) -> None:
    """Removes every staged file of `sha`, whether or not its sidecar is intact."""
    remove_extras(box, sha)


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
