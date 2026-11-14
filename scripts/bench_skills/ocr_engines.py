"""Compares the OCR hint of whichever RapidOCR package is installed against the benchmark's labels:
the human has-text labels, the human transcriptions, and Sonnet's checked transcriptions. Results
live in the git-ignored testdata/private/bench/ocr-engines/, one file per engine.

    python3 scripts/bench_skills/ocr_engines.py run [--name NAME] [--param KEY=VALUE ...]
    python3 scripts/bench_skills/ocr_engines.py score NAME [NAME ...]
"""

import argparse
import importlib.metadata
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from qwen import BENCH, cer, load_reference, norm_text  # noqa: E402
from sticker_box import analysis, ocr, policy  # noqa: E402

OUT = BENCH / "ocr-engines"


def engine_name() -> str:
    for dist in ("rapidocr", "rapidocr-onnxruntime"):
        try:
            return f"{dist}-{importlib.metadata.version(dist)}"
        except importlib.metadata.PackageNotFoundError:
            continue
    raise SystemExit("no RapidOCR package installed")


def stickers() -> dict[str, str]:
    sample = json.loads((BENCH / "sample.json").read_text())
    paths = {row["id"]: row["path"] for row in sample["sample"]}
    for group in ("has_text", "transcribe"):
        for row in sample["human"][group]:
            paths.setdefault(row["id"], row["path"])
    return paths


def run(name: str, params: list[str]) -> None:
    OUT.mkdir(exist_ok=True)
    if params:
        from rapidocr import RapidOCR

        ocr._engine = RapidOCR(params={"Global.log_level": "error", **{k: json.loads(v) for k, v in (p.split("=", 1) for p in params)}})
    timings: list[float] = []
    original = ocr.hint

    def timed(images):
        start = time.perf_counter()
        try:
            return original(images)
        finally:
            timings.append(time.perf_counter() - start)

    ocr.hint = timed
    start = time.perf_counter()
    ocr._get_engine()
    load_s = time.perf_counter() - start
    results = {}
    for key, path in sorted(stickers().items()):
        found = analysis.analyze(Path(path), policy.DEFAULTS["analysis"], with_ocr=True).ocr
        results[key] = {"text": found["text"], "noise": found["noise"], "ms": round(timings[-1] * 1000, 1)}
    (OUT / f"{name}.json").write_text(json.dumps({"engine": name, "load_s": round(load_s, 2), "results": results},
                                                 ensure_ascii=False, indent=0))
    print(f"{name}: {len(results)} stickers, model load {load_s:.2f} s")


def score(name: str, other: dict | None) -> dict:
    data = json.loads((OUT / f"{name}.json").read_text())
    results = data["results"]
    sample = json.loads((BENCH / "sample.json").read_text())
    human = {row["id"]: row for row in sample["human"]["has_text"]}
    reference = {k: v["text"] for k, v in load_reference().items() if v.get("has_text") is not None}
    reference.update({k: v.get("text") or "" for k, v in load_reference().items() if v.get("has_text") is False})
    for row in sample["human"]["transcribe"]:
        reference[row["id"]] = row["text"]

    def found(key):
        r = results[key]
        return bool(r["text"]) and not r["noise"]

    tp = sum(1 for k, h in human.items() if h["has_text"] and found(k))
    fp = sum(1 for k, h in human.items() if not h["has_text"] and found(k))
    fn = sum(1 for k, h in human.items() if h["has_text"] and not found(k))
    tn = len(human) - tp - fp - fn
    marks = [k for k, h in human.items() if h["watermark"]]
    with_text = [k for k, t in reference.items() if norm_text(t) and k in results]
    errors = [cer(results[k]["text"], reference[k]) for k in with_text]
    ms = [r["ms"] for r in results.values()]
    out = {
        "engine": name,
        "model_load_s": data["load_s"],
        "has_text_human_n": len(human),
        "has_text_accuracy": round((tp + tn) / len(human), 3),
        "has_text_precision": round(tp / (tp + fp), 3) if tp + fp else None,
        "has_text_recall": round(tp / (tp + fn), 3) if tp + fn else None,
        "watermark_recall": f"{sum(found(k) for k in marks)}/{len(marks)}",
        "transcribed_n": len(with_text),
        "cer_mean": round(statistics.mean(errors), 3),
        "cer_median": round(statistics.median(errors), 3),
        "exact": round(sum(e == 0 for e in errors) / len(errors), 3),
        "ocr_ms_median": round(statistics.median(ms), 1),
        "ocr_ms_p90": round(sorted(ms)[int(len(ms) * 0.9)], 1),
    }
    if other is not None:
        shared = [k for k in results if k in other]
        same = sum(norm_text(results[k]["text"]) == norm_text(other[k]["text"]) for k in shared)
        out["identical_to_first"] = f"{same}/{len(shared)}"
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--name", default=None)
    r.add_argument("--param", action="append", default=[], help="a RapidOCR 3 setting as KEY=JSON, e.g. Global.use_cls=false")
    s = sub.add_parser("score")
    s.add_argument("names", nargs="+")
    args = ap.parse_args()
    if args.cmd == "run":
        run(args.name or engine_name(), args.param)
        return
    first = None
    for name in args.names:
        print(json.dumps(score(name, first), ensure_ascii=False))
        if first is None:
            first = json.loads((OUT / f"{name}.json").read_text())["results"]


if __name__ == "__main__":
    main()
