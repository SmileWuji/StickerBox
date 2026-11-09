"""Local features (SIFT) for crops, zooms, rotations and pictures inside screenshots, which pHash
cannot see. Matching runs in two stages (design notes §8): a vote over every stored descriptor,
streamed in batches so memory stays bounded, shortlists a few candidates; each candidate is then
verified pairwise with Lowe's ratio test and a RANSAC homography, which also says how the two
pictures relate. The ratio test is kept out of the vote: with two stored copies of a picture,
best and second-best would tie and every match would be thrown away."""

import math
import os
import time
import uuid
from pathlib import Path

import cv2
import numpy as np

EXTRACTOR = "sift-v1"
SIFT_SIDE = 1024
MIN_KEYPOINTS = 30
VOTE_DISTANCE = 300.0
BATCH_DESCRIPTORS = 60_000
QUERY_CHUNK = 256
SHORTLIST = 3
SAME = 0.85
ROTATION_DEG = 8.0
MIN_SPREAD = 0.04
SCALE_RANGE = (0.05, 20.0)
MAX_KEYPOINTS = 2000
MAX_SETS = 16
MAX_NPZ_BYTES = 8 * 1024 * 1024
SIFT_SECONDS = float(os.environ.get("STICKER_BOX_SIFT_SECONDS", "60"))


def extract(rgb: np.ndarray, orig_size: tuple[int, int], keypoints: int) -> tuple[np.ndarray, np.ndarray] | None:
    """(n×2 float32 keypoints in original pixel coordinates, n×128 uint8 descriptors), or None
    when the image has too few keypoints to match reliably (flat art)."""
    h, w = rgb.shape[:2]
    scale = min(1.0, SIFT_SIDE / max(h, w))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    if scale < 1.0:
        gray = cv2.resize(gray, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_AREA)
    sift = cv2.SIFT_create(nfeatures=keypoints)
    kps, desc = sift.detectAndCompute(gray, None)
    if desc is None or len(kps) < MIN_KEYPOINTS:
        return None
    gh, gw = gray.shape[:2]
    fx, fy = orig_size[0] / gw, orig_size[1] / gh
    pts = np.array([(k.pt[0] * fx, k.pt[1] * fy) for k in kps], dtype=np.float32)
    return pts, np.clip(np.rint(desc), 0, 255).astype(np.uint8)


def pick_frames(count: int, limit: int) -> list[int]:
    if count <= limit:
        return list(range(count))
    return sorted({round(i * (count - 1) / (limit - 1)) for i in range(limit)})


def compute(result, policy: dict) -> list[tuple[int, np.ndarray, np.ndarray]]:
    keypoints = policy["duplicates"]["sift"]["keypoints"]
    size = (result.info.width, result.info.height)
    out = []
    for idx in pick_frames(len(result.keyframes), policy["analysis"]["sift_keyframes"]):
        got = extract(result.keyframes[idx].rgb, size, keypoints)
        if got is not None:
            out.append((idx, got[0], got[1]))
    return out


def npz_path(box, sha: str) -> Path:
    return box.temporary / f"{sha}.features.npz"


def save(path: Path, sets: list) -> None:
    arrays = {}
    for i, (idx, kp, desc) in enumerate(sets):
        arrays[f"idx{i}"] = np.array([idx])
        arrays[f"kp{i}"] = kp
        arrays[f"desc{i}"] = desc
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp.npz")
    np.savez(tmp, n=np.array([len(sets)]), **arrays)
    tmp.replace(path)


def _valid_set(kp, desc) -> bool:
    return (isinstance(kp, np.ndarray) and isinstance(desc, np.ndarray) and kp.dtype == np.float32 and desc.dtype == np.uint8
            and kp.ndim == 2 and kp.shape[1] == 2 and desc.shape == (kp.shape[0], 128)
            and 1 <= kp.shape[0] <= MAX_KEYPOINTS and bool(np.isfinite(kp).all()))


def load(path: Path) -> list:
    """Feature sets from a staged .npz, checked before use: the file may have been planted or
    damaged, and a wrong shape would otherwise break every later match in the box."""
    from .errors import BoxError

    bad = BoxError("corrupt_staging", f"{path.name} is not a feature file this tool wrote")
    try:
        if path.is_symlink() or path.stat().st_size > MAX_NPZ_BYTES:
            raise bad
        with np.load(path, allow_pickle=False) as data:
            if sum(info.file_size for info in data.zip.infolist()) > MAX_NPZ_BYTES:
                raise bad
            n = int(data["n"][0])
            if not 0 <= n <= MAX_SETS:
                raise bad
            sets = [(int(data[f"idx{i}"][0]), data[f"kp{i}"], data[f"desc{i}"]) for i in range(n)]
    except BoxError:
        raise
    except Exception:
        raise bad from None
    if not all(_valid_set(kp, desc) for _, kp, desc in sets):
        raise bad
    return sets


def _row_ok(r) -> bool:
    n = r["n"]
    return isinstance(n, int) and 1 <= n <= MAX_KEYPOINTS and isinstance(r["desc"], bytes) and len(r["desc"]) == n * 128 \
        and ("kp" not in r.keys() or (isinstance(r["kp"], bytes) and len(r["kp"]) == n * 8))


def _stored_batches(conn, exclude: str | None):
    """Rows of stored features, about BATCH_DESCRIPTORS descriptors at a time, so the distance
    matrix stays near QUERY_CHUNK x BATCH_DESCRIPTORS floats whatever the keypoint setting."""
    batch, count = [], 0
    for r in conn.execute("SELECT sha256, frame, n, desc FROM feature WHERE extractor = ? ORDER BY rowid", (EXTRACTOR,)):
        if r["sha256"] == exclude or not _row_ok(r):
            continue
        batch.append(r)
        count += r["n"]
        if count >= BATCH_DESCRIPTORS:
            yield batch
            batch, count = [], 0
    if batch:
        yield batch


class Timeout(Exception):
    pass


def vote(conn, sets: list, exclude: str | None = None, deadline: float | None = None) -> dict[str, int]:
    votes: dict[str, int] = {}
    queries = [desc.astype(np.float32) for _, _, desc in sets]
    q_norms = [(q * q).sum(1)[:, None] for q in queries]
    for rows in _stored_batches(conn, exclude):
        if deadline is not None and time.monotonic() > deadline:
            raise Timeout(votes)
        descs = [np.frombuffer(r["desc"], np.uint8).reshape(r["n"], 128) for r in rows]
        stack = np.vstack(descs).astype(np.float32)
        owners = np.repeat(np.arange(len(rows)), [d.shape[0] for d in descs])
        s_norms = (stack * stack).sum(1)[None, :]
        for q, qn in zip(queries, q_norms):
            for start in range(0, len(q), QUERY_CHUNK):
                d2 = qn[start:start + QUERY_CHUNK] + s_norms - 2.0 * (q[start:start + QUERY_CHUNK] @ stack.T)
                best = d2.argmin(1)
                ok = d2[np.arange(len(best)), best] <= VOTE_DISTANCE ** 2
                for owner in owners[best[ok]]:
                    sha = rows[owner]["sha256"]
                    votes[sha] = votes.get(sha, 0) + 1
    return votes


def _coverage(H: np.ndarray, src_size: tuple[int, int], dst_size: tuple[int, int]) -> tuple[float, list[float]]:
    """Share of the destination rectangle covered by the source rectangle mapped through H, and
    the mapped source's bounding box in the destination, normalised to 0..1."""
    w, h = src_size
    corners = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32).reshape(-1, 1, 2)
    mapped = cv2.perspectiveTransform(corners, H).reshape(-1, 2)
    dw, dh = dst_size
    x0, y0 = np.clip(mapped.min(0), 0, [dw, dh])
    x1, y1 = np.clip(mapped.max(0), 0, [dw, dh])
    area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    return area / float(dw * dh), [round(float(x0 / dw), 3), round(float(y0 / dh), 3), round(float(x1 / dw), 3), round(float(y1 / dh), 3)]


def classify(H: np.ndarray, size_a: tuple[int, int], size_b: tuple[int, int]) -> tuple[str, dict]:
    """How the new picture A relates to the stored picture B, given H mapping A to B."""
    angle = math.degrees(math.atan2(H[1, 0], H[0, 0]))
    det = abs(float(np.linalg.det(H[:2, :2])))
    scale = math.sqrt(det) if det > 0 else 0.0
    cov_b, region_b = _coverage(H, size_a, size_b)
    try:
        cov_a, region_a = _coverage(np.linalg.inv(H), size_b, size_a)
    except np.linalg.LinAlgError:
        cov_a, region_a = 0.0, [0, 0, 0, 0]
    t = {"angle": round(angle, 1), "zoom": round(1 / scale, 2) if scale else None, "coverage_of_b": round(cov_b, 3),
         "coverage_of_a": round(cov_a, 3), "region_in_b": region_b, "region_in_a": region_a}
    if abs(angle) > ROTATION_DEG:
        kind = "rotation"
    elif cov_a >= SAME and cov_b >= SAME:
        kind = "duplicate"
    elif cov_a >= SAME:
        kind = "crop_of"
    elif cov_b >= SAME:
        kind = "contains"
    else:
        kind = "overlap"
    return kind, t


def summary(kind: str, t: dict) -> str:
    if kind == "duplicate":
        return "the same picture" + (f" at {t['zoom']}x scale" if t["zoom"] and abs(t["zoom"] - 1) > 0.1 else "")
    if kind == "crop_of":
        return f"a crop showing {t['coverage_of_b'] * 100:.0f}% of it" + (f", zoomed {t['zoom']}x" if t["zoom"] else "")
    if kind == "contains":
        return f"contains it, filling {t['coverage_of_a'] * 100:.0f}% of the new picture"
    if kind == "rotation":
        return f"the same picture rotated by {t['angle']:.0f} degrees"
    return "partly the same picture"


def _spread(points: np.ndarray, size: tuple[int, int]) -> float:
    span = np.ptp(points, axis=0)
    return float(span[0] * span[1]) / float(size[0] * size[1])


def verify(a_sets: list, b_sets: list, ratio: float, size_a: tuple[int, int], size_b: tuple[int, int]) -> tuple[int, np.ndarray | None]:
    """Best pair of frames by RANSAC inliers of a similarity transform (rotation, uniform scale,
    translation: everything a crop, zoom, rotation or screenshot does). A full homography also
    fits clusters of look-alike strokes such as text, so it is not used. Inliers must also cover
    at least MIN_SPREAD of both pictures, which rules out a shared logo or watermark."""
    matcher = cv2.BFMatcher(cv2.NORM_L2)
    best = (0, None)
    for _, kp_a, desc_a in a_sets:
        for _, kp_b, desc_b in b_sets:
            pairs = matcher.knnMatch(desc_a.astype(np.float32), desc_b.astype(np.float32), k=2)
            good = [m for m, *rest in pairs if rest and m.distance < ratio * rest[0].distance]
            if len(good) < 6:
                continue
            src = np.float32([kp_a[m.queryIdx] for m in good])
            dst = np.float32([kp_b[m.trainIdx] for m in good])
            threshold = max(3.0, 0.01 * max(size_b))
            M, mask = cv2.estimateAffinePartial2D(src, dst, method=cv2.RANSAC, ransacReprojThreshold=threshold, maxIters=4000)
            if M is None or mask is None:
                continue
            keep = mask.ravel().astype(bool)
            inliers = int(keep.sum())
            if inliers < 6 or _spread(src[keep], size_a) < MIN_SPREAD or _spread(dst[keep], size_b) < MIN_SPREAD:
                continue
            H = np.vstack([M, [0.0, 0.0, 1.0]])
            scale = math.sqrt(abs(float(np.linalg.det(H[:2, :2]))))
            if inliers > best[0] and SCALE_RANGE[0] <= scale <= SCALE_RANGE[1]:
                best = (inliers, H)
    return best


def _stored_sets(conn, sha: str) -> list:
    return [(r["frame"], np.frombuffer(r["kp"], np.float32).reshape(r["n"], 2), np.frombuffer(r["desc"], np.uint8).reshape(r["n"], 128))
            for r in conn.execute("SELECT frame, n, kp, desc FROM feature WHERE sha256 = ? AND extractor = ?", (sha, EXTRACTOR))
            if _row_ok(r)]


def match(conn, sets: list, size: tuple[int, int], sift: dict, exclude: str | None = None,
          only: set[str] | None = None) -> tuple[list[dict], bool]:
    """(matches, complete). Stops at SIFT_SECONDS and returns what it has, so a big or costly box
    slows a write down by at most that much; `only` restricts candidates (used by reindex)."""
    if not sets:
        return [], True
    deadline = time.monotonic() + SIFT_SECONDS
    complete = True
    try:
        votes = vote(conn, sets, exclude, deadline)
    except Timeout as partial:
        votes, complete = partial.args[0], False
    if only is not None:
        votes = {k: v for k, v in votes.items() if k in only}
    floor = max(6, sift["min_inliers"] // 2)
    shortlist = [sha for sha, n in sorted(votes.items(), key=lambda kv: -kv[1]) if n >= floor][:SHORTLIST]
    out = []
    for sha in shortlist:
        if time.monotonic() > deadline:
            complete = False
            break
        row = conn.execute("SELECT width, height FROM item WHERE sha256 = ?", (sha,)).fetchone()
        if row is None:
            continue
        inliers, H = verify(sets, _stored_sets(conn, sha), sift["ratio"], size, (row["width"], row["height"]))
        if H is None or inliers < sift["min_inliers"]:
            continue
        kind, t = classify(H, size, (row["width"], row["height"]))
        out.append({"ref": sha, "kind": kind, "method": "sift", "inliers": inliers, "votes": votes[sha],
                    "transform": t, "summary": summary(kind, t)})
    return out, complete


def stage(box, policy: dict, result, sidecar: dict) -> None:
    sets = compute(result, policy)
    save(npz_path(box, result.sha256), sets)
    sidecar["features"] = {"extractor": EXTRACTOR, "frames": [idx for idx, _, _ in sets], "keypoints": [int(kp.shape[0]) for _, kp, _ in sets]}
    sidecar["sift_matches"], complete = match(box.conn, sets, (result.info.width, result.info.height), policy["duplicates"]["sift"])
    if not complete:
        sidecar["sift_note"] = f"local-feature matching stopped after {SIFT_SECONDS:g} s; crops and rotations may be missed"


def store_sets(box, sha: str, sets: list) -> None:
    rows = [(sha, idx, EXTRACTOR, int(kp.shape[0]), kp.astype(np.float32).tobytes(), desc.astype(np.uint8).tobytes())
            for idx, kp, desc in sets if _valid_set(kp.astype(np.float32), desc.astype(np.uint8))]
    box.conn.executemany("INSERT OR REPLACE INTO feature (sha256, frame, extractor, n, kp, desc) VALUES (?, ?, ?, ?, ?, ?)", rows)


def store(box, sha: str, sidecar: dict) -> None:
    path = npz_path(box, sha)
    if not path.is_file() and not path.is_symlink():
        return
    rows = [(sha, idx, EXTRACTOR, int(kp.shape[0]), kp.astype(np.float32).tobytes(), desc.astype(np.uint8).tobytes())
            for idx, kp, desc in load(path)]
    box.conn.executemany("INSERT OR REPLACE INTO feature (sha256, frame, extractor, n, kp, desc) VALUES (?, ?, ?, ?, ?, ?)", rows)

