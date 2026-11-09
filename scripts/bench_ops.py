"""Operations benchmark (design: 261109-OPS-BENCHMARK-DESIGN.md). Fills boxes to fixed sizes
with seeded synthetic rows written straight into SQLite (placeholder files in persistent/),
then times the commands an agent calls. All data is synthetic, so results can be published.

    python3 scripts/bench_ops.py --where /tmp --sizes 1000,3000,10000,30000 --gallery-sizes 1000,3000,10000
    python3 scripts/bench_ops.py --where testdata/private/bench-tmp --sizes 1000,3000 --gallery-sizes 1000

Writes a JSON report (--out) and prints one line per box size."""

import argparse
import contextlib
import io
import json
import os
import platform
import random
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

import numpy as np  # noqa: E402

import factory  # noqa: E402
from sticker_box import db  # noqa: E402
from sticker_box.cli import main  # noqa: E402

HANZI = ("的一是不了人我在有他这中大来上个国到说们为子和你地出道也时年得就那要下以生会自着去之过家学对可她里后小么心多天而能好都"
         "然没日于起还发成事只作当想看文无开手十用主行方又如前所本见经头面公同三已老从动两长知民样现分将外但身些与高意进把法此实回")
CATEGORIES = {"telegram-sticker": {"emotion": 120, "visual": 200, "character": 80, "series": 30, "pack": 20},
              "gallery": {"tag": 400}}
REPEAT = 7


def word(rng: random.Random, lo: int, hi: int) -> str:
    return "".join(rng.choice(HANZI) for _ in range(rng.randint(lo, hi)))


def zipf(rng: random.Random, values: list):
    return values[min(len(values) - 1, int(rng.paretovariate(1.1)) - 1)]


def fill(root: Path, preset: str, n: int, seed: int) -> dict:
    rng, nrng = random.Random(seed), np.random.default_rng(seed)
    conn = sqlite3.connect(root / "box.sqlite3")
    stamp = "2026-11-09T00:00:00Z"
    vocab, tid = {}, 0
    for category, count in CATEGORIES[preset].items():
        seen, vocab[category] = set(), []
        while len(vocab[category]) < count:
            value = word(rng, 2, 4)
            if value in seen:
                continue
            seen.add(value)
            tid += 1
            vocab[category].append((tid, value))
            conn.execute("INSERT INTO tag (id, category, value, definition, created_at) VALUES (?, ?, ?, ?, ?)",
                         (tid, category, value, word(rng, 6, 14), stamp))
    (root / "persistent" / "202611").mkdir(parents=True, exist_ok=True)
    items, keyframes, item_tags, features, shas, texts = [], [], [], [], [], []
    for i in range(n):
        sha = f"{rng.getrandbits(256):064x}"
        shas.append(sha)
        rel = f"persistent/202611/20261109-{sha}.webp"
        (root / rel).write_bytes(b"0")
        animated = rng.random() < 0.3
        frames = rng.randint(2, 12) if animated else 1
        added = f"2026-11-09T{(i // 3600) % 24:02d}:{(i // 60) % 60:02d}:{i % 60:02d}Z"
        text = "" if rng.random() < 0.5 else word(rng, 4, 12)
        texts.append(text)
        items.append((sha, rel, "webp", 512, 512, int(animated), frames, 1000 if animated else None, 15.0 if animated else None,
                      None, 0, rng.randint(20_000, 250_000), db.to_signed(rng.getrandbits(64)), added, added, None,
                      "unknown", None, text, word(rng, 8, 20), word(rng, 8, 20)))
        keyframes += [(sha, k, k * 2, k * 66, db.to_signed(rng.getrandbits(64))) for k in range(frames)]
        chosen = set()
        if preset == "gallery":
            chosen |= {zipf(rng, vocab["tag"])[0] for _ in range(rng.randint(1, 5))}
            features.append((sha, 0, "sift-v1", 300, nrng.random((300, 2), dtype=np.float32).tobytes(),
                             nrng.integers(0, 256, (300, 128), dtype=np.uint8).tobytes()))
        else:
            for category, lo, hi in (("emotion", 1, 2), ("visual", 1, 3), ("character", 0, 1), ("series", 0, 1), ("pack", 1, 1)):
                chosen |= {zipf(rng, vocab[category])[0] for _ in range(rng.randint(lo, hi))}
        item_tags += [(sha, t) for t in chosen]
    conn.executemany(f"INSERT INTO item VALUES ({','.join('?' * 21)})", items)
    conn.executemany("INSERT INTO keyframe VALUES (?, ?, ?, ?, ?)", keyframes)
    conn.executemany("INSERT INTO item_tag VALUES (?, ?)", item_tags)
    conn.executemany("INSERT INTO feature VALUES (?, ?, ?, ?, ?, ?)", features)
    conn.executemany("INSERT OR IGNORE INTO relation VALUES (?, ?, ?, ?, ?, ?, ?)",
                     [(shas[i], shas[rng.randrange(i)], "near_duplicate", "phash", 3.0, None, stamp) for i in range(1, n) if rng.random() < 0.02])
    conn.commit()
    conn.close()
    first = {c: v[0][1] for c, v in vocab.items()}
    return {"shas": shas, "popular": first, "text_word": next(t for t in texts if t)[:2]}


def run_cli(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = main(["--json", *argv])
    if code not in (0, 1):
        raise RuntimeError(f"{argv[:3]} exited {code}: {out.getvalue()[:300]}")
    return code, out.getvalue()


def stats(times: list[float]) -> dict:
    s = sorted(times)
    return {"median_ms": round(statistics.median(s) * 1000, 1), "p95_ms": round(s[max(0, int(len(s) * 0.95) - 1)] * 1000, 1),
            "max_ms": round(s[-1] * 1000, 1), "n": len(s)}


def timed(fn, repeat: int = REPEAT) -> dict:
    fn(-1)
    times = []
    for i in range(repeat):
        t0 = time.perf_counter()
        fn(i)
        times.append(time.perf_counter() - t0)
    return stats(times)


def as_process(argv: list[str]) -> dict:
    """Wall time and peak memory of one command run as its own process, as an agent runs it. Peak
    memory is VmHWM, which starts afresh at exec; getrusage's maxrss would carry over the forking
    parent's peak on Linux."""
    code = ("import sys; from sticker_box.cli import main; c = main(sys.argv[1:]); "
            "print(next(l.split()[1] for l in open('/proc/self/status') if l.startswith('VmHWM')), file=sys.stderr)")
    t0 = time.perf_counter()
    done = subprocess.run([sys.executable, "-c", code, "--json", *argv], capture_output=True, text=True)
    wall = time.perf_counter() - t0
    rss_kb = int(done.stderr.strip().splitlines()[-1]) if done.stderr.strip().splitlines()[-1].isdigit() else None
    return {"wall_ms": round(wall * 1000, 1), "peak_rss_mb": round(rss_kb / 1024, 1) if rss_kb else None}


def new_sticker(tmp: Path, seed: int) -> Path:
    return factory.write_webp(tmp / f"s{seed}.webp", factory.picture(seed, (512, 512), alpha=True))


def commit_args(preset: str, popular: dict) -> list[str]:
    if preset == "telegram-sticker":
        return ["--license", "unknown", "--text", "", "--note", "基准", "--tag", f"emotion={popular['emotion']}"]
    return ["--license", "unknown", "--tag", "bench"]


PLANS = {
    "search: items with one tag": "SELECT i.sha256, i.added_at FROM item i WHERE i.sha256 IN (SELECT sha256 FROM item_tag WHERE tag_id = 1)",
    "search: items of matched tags": "SELECT sha256, tag_id FROM item_tag WHERE tag_id IN (1, 2, 3)",
    "search: text LIKE": "SELECT sha256 FROM item WHERE text LIKE '%ab%' ESCAPE '\\'",
    "search: field LIKE": "SELECT DISTINCT sha256 FROM item_field WHERE value LIKE '%ab%' ESCAPE '\\'",
    "write: all keyframe hashes": "SELECT k.sha256, k.idx, k.phash, i.animated FROM keyframe k JOIN item i ON i.sha256 = k.sha256",
    "write: usage for limits": "SELECT COUNT(*) AS n, COALESCE(SUM(bytes), 0) AS b FROM item",
    "show: relations of an item": "SELECT * FROM relation WHERE a = 'x' OR b = 'x'",
    "readme: uses per tag": "SELECT t.id, (SELECT COUNT(*) FROM item_tag it WHERE it.tag_id = t.id) FROM tag t WHERE t.category = 'emotion'",
    "sift: stored descriptors": "SELECT sha256, frame, n, desc FROM feature WHERE extractor = 'sift-v1' ORDER BY rowid",
}


def plans(root: Path) -> dict:
    conn = sqlite3.connect(root / "box.sqlite3")
    out = {name: [r[3] for r in conn.execute("EXPLAIN QUERY PLAN " + sql)] for name, sql in PLANS.items()}
    conn.close()
    return out


def concurrency(root: Path, preset: str, popular: dict, writers: int, per_writer: int, tmp: Path) -> dict:
    files = [[new_sticker(tmp, 900_000 + writers * 100_000 + w * 1000 + i) for i in range(per_writer)] for w in range(writers)]
    script = ("import json, sys, time; from sticker_box.cli import main; import contextlib, io\n"
              "box, extra, paths = sys.argv[1], json.loads(sys.argv[2]), sys.argv[3:]\n"
              "fails, times = 0, []\n"
              "for p in paths:\n"
              "    t0 = time.perf_counter(); out = io.StringIO()\n"
              "    with contextlib.redirect_stdout(out): main(['--json', 'stage', p, '--box', box])\n"
              "    ref = json.loads(out.getvalue())['results'][0]['ref']\n"
              "    with contextlib.redirect_stdout(io.StringIO()): code = main(['--json', 'commit', ref, '--box', box, *extra])\n"
              "    fails += code != 0; times.append(time.perf_counter() - t0)\n"
              "print(json.dumps({'fails': fails, 'times': times}))\n")
    t0 = time.perf_counter()
    procs = [subprocess.Popen([sys.executable, "-c", script, str(root), json.dumps(commit_args(preset, popular)), *map(str, f)],
                              stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True) for f in files]
    results = [json.loads(p.communicate()[0]) for p in procs]
    wall = time.perf_counter() - t0
    times = [t for r in results for t in r["times"]]
    return {"writers": writers, "items": writers * per_writer, "wall_s": round(wall, 1), "failures": sum(r["fails"] for r in results),
            "stage_plus_commit": stats(times)}


def bench_box(where: Path, preset: str, n: int, repeat: int, deep: bool) -> dict:
    root = where / f"{preset}-{n}"
    run_cli("init", str(root), "--preset", preset, "--language", "zh-Hans")
    t0 = time.perf_counter()
    info = fill(root, preset, n, seed=n)
    fill_s = time.perf_counter() - t0
    run_cli("manual", "--box", str(root))
    box = ["--box", str(root)]
    rng = random.Random(7)
    category, value = next(iter(info["popular"].items()))
    ops = {
        "search --tag (one tag)": timed(lambda i: run_cli("search", "--tag", f"{category}={value}", *box), repeat),
        "search: a tag value": timed(lambda i: run_cli("search", value, *box), repeat),
        "search: a word in on-image text": timed(lambda i: run_cli("search", info["text_word"], *box), repeat),
        "search: five words": timed(lambda i: run_cli("search", *[word(rng, 2, 3) for _ in range(5)], *box), repeat),
        "search: no words (newest)": timed(lambda i: run_cli("search", *box), repeat),
        "show": timed(lambda i: run_cli("show", rng.choice(info["shas"]), *box), repeat),
        "tag list": timed(lambda i: run_cli("tag", "list", *box), repeat),
        "info": timed(lambda i: run_cli("info", *box), repeat),
    }
    tmp = where / f"new-{preset}-{n}"
    tmp.mkdir()
    stage_t, commit_t, edit_t, remove_t = [], [], [], []
    for i in range(-1, repeat):
        path = new_sticker(tmp, n * 10 + i + 1)
        t0 = time.perf_counter()
        _, out = run_cli("stage", str(path), *box)
        t1 = time.perf_counter()
        ref = json.loads(out)["results"][0]["ref"]
        run_cli("commit", ref, *box, *commit_args(preset, info["popular"]))
        t2 = time.perf_counter()
        run_cli("edit", ref, *box, "--note", "改")
        t3 = time.perf_counter()
        run_cli("remove", ref, *box)
        t4 = time.perf_counter()
        if i >= 0:
            stage_t.append(t1 - t0), commit_t.append(t2 - t1), edit_t.append(t3 - t2), remove_t.append(t4 - t3)
    ops.update({"stage": stats(stage_t), "commit": stats(commit_t), "edit (note)": stats(edit_t), "remove": stats(remove_t)})
    slow = max(3, repeat // 2)
    ops["vocab review"] = timed(lambda i: run_cli("vocab", "review", *box), slow)
    ops["dupes"] = timed(lambda i: run_cli("dupes", *box), slow)
    ops["check"] = timed(lambda i: run_cli("check", *box), slow)
    ops["clean (nothing to do)"] = timed(lambda i: run_cli("clean", *box), slow)
    tag_cat = "emotion" if preset == "telegram-sticker" else "tag"
    a, b = fill_vocab(root, tag_cat)[:2]
    t0 = time.perf_counter()
    run_cli("tag", "rename", tag_cat, a, a + "改", *box)
    ops["tag rename"] = {"median_ms": round((time.perf_counter() - t0) * 1000, 1), "n": 1}
    t0 = time.perf_counter()
    run_cli("tag", "merge", tag_cat, b, a + "改", *box)
    ops["tag merge"] = {"median_ms": round((time.perf_counter() - t0) * 1000, 1), "n": 1}
    proc_path = new_sticker(tmp, n * 10 + 999)
    _, out = run_cli("stage", str(proc_path), *box)
    staged = json.loads(out)["results"][0]["ref"]
    process = {
        "search --tag": as_process(["search", "--tag", f"{category}={value}", *box]),
        "show": as_process(["show", info["shas"][0], *box]),
        "stage": as_process(["stage", str(new_sticker(tmp, n * 10 + 998)), *box]),
        "commit": as_process(["commit", staged, *box, *commit_args(preset, info["popular"])]),
        "remove": as_process(["remove", staged, *box]),
        "check": as_process(["check", *box]),
    }
    report = {"preset": preset, "items": n, "fill_s": round(fill_s, 1), "db_mb": round((root / "box.sqlite3").stat().st_size / 1e6, 1),
              "ops": ops, "as_process": process, "plans": plans(root)}
    if deep:
        report["concurrency"] = [concurrency(root, preset, info["popular"], w, 6, tmp) for w in (1, 2, 4)]
    shutil.rmtree(root, ignore_errors=True)
    shutil.rmtree(tmp, ignore_errors=True)
    return report


def fill_vocab(root: Path, category: str) -> list[str]:
    conn = sqlite3.connect(root / "box.sqlite3")
    values = [r[0] for r in conn.execute("SELECT value FROM tag WHERE category = ? AND retired_at IS NULL ORDER BY id", (category,))]
    conn.close()
    return values


def startup(where: Path, repeat: int) -> dict:
    root = where / "startup"
    run_cli("init", str(root), "--preset", "gallery", "--language", "en")
    exe = str(Path(sys.executable).parent / "sticker-box")
    out = {}
    for label, argv in (("--version", [exe, "--version"]), ("info on an empty box", [exe, "info", "--box", str(root), "--json"])):
        times = []
        for _ in range(repeat):
            t0 = time.perf_counter()
            subprocess.run(argv, capture_output=True, check=True)
            times.append(time.perf_counter() - t0)
        out[label] = stats(times)
    shutil.rmtree(root, ignore_errors=True)
    return out


def environment(where: Path) -> dict:
    import cv2
    import PIL

    cpu = next((line.split(":", 1)[1].strip() for line in open("/proc/cpuinfo") if line.startswith("model name")), platform.processor())
    mem = next((int(line.split()[1]) // 1024 for line in open("/proc/meminfo") if line.startswith("MemTotal")), None)
    fs = subprocess.run(["df", "-T", str(where)], capture_output=True, text=True).stdout.splitlines()[-1].split()[1]
    return {"cpu": cpu, "cores": os.cpu_count(), "ram_mb": mem, "os": platform.platform(), "python": platform.python_version(),
            "sqlite": sqlite3.sqlite_version, "numpy": np.__version__, "opencv": cv2.__version__, "pillow": PIL.__version__,
            "where": str(where), "filesystem": fs}


def main_bench() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--where", default="/tmp")
    ap.add_argument("--sizes", default="1000,3000,10000,30000")
    ap.add_argument("--gallery-sizes", default="1000,3000,10000")
    ap.add_argument("--repeat", type=int, default=REPEAT)
    ap.add_argument("--concurrency-at", type=int, default=3000, help="sticker box size at which to run the concurrent writers")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    base = Path(args.where)
    base.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="sticker-box-bench-", dir=base))
    report = {"environment": environment(work), "startup": startup(work, args.repeat), "boxes": []}
    out = Path(args.out)
    try:
        for preset, sizes in (("telegram-sticker", args.sizes), ("gallery", args.gallery_sizes)):
            for n in [int(x) for x in sizes.split(",") if x]:
                deep = preset == "telegram-sticker" and n == args.concurrency_at
                report["boxes"].append(bench_box(work, preset, n, args.repeat, deep))
                out.write_text(json.dumps(report, ensure_ascii=False, indent=1))
                ops = report["boxes"][-1]["ops"]
                print(f"{preset} {n}: " + ", ".join(f"{k} {v['median_ms']}" for k, v in ops.items()), flush=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main_bench()
