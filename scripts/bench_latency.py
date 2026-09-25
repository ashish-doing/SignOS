"""Latency benchmark. Keep a hand in view. Excludes sensor/USB/driver latency and display."""
from __future__ import annotations

import argparse
import csv
import importlib.metadata as md
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.perception import run_perception

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results"


def pct(a):
    a = np.asarray(a, float)
    if a.size == 0:
        return None
    return {"n": int(a.size), "p50": round(float(np.percentile(a, 50)), 3),
            "p95": round(float(np.percentile(a, 95)), 3), "max": round(float(a.max()), 3)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--isl", default=None)
    ap.add_argument("--task-model", default=None)
    a = ap.parse_args()
    RES.mkdir(exist_ok=True)
    csv_path = RES / "timing_local.csv"
    argv = ["--no-window", "--seconds", str(a.seconds), "--camera", str(a.camera),
            "--timing-csv", str(csv_path), "--bus", str(RES / "bench_bus.jsonl")]
    if a.isl:
        argv += ["--isl", a.isl]
    if a.task_model:
        argv += ["--task-model", a.task_model]
    print(f"benchmarking {a.seconds}s - keep your hand in view")
    if run_perception.main(argv) != 0:
        raise SystemExit("run failed")
    rows = list(csv.DictReader(open(csv_path)))
    col = lambda k, m=None: np.array([float(r[k]) for r in rows if m is None or m(r)])
    hp = lambda r: int(r["hands"]) > 0
    em = lambda r: int(r["n_emitted"]) > 0
    t = col("t_s")
    out = {"tag": "MEASURED-LOCAL", "when": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "python": sys.version.split()[0], "platform": platform.platform(),
           "mediapipe": md.version("mediapipe"), "isl_model": a.isl, "seconds": a.seconds,
           "frames": len(rows), "pipeline_fps": round((len(rows) - 1) / (t[-1] - t[0]), 2),
           "hand_present_frac": round(float(np.mean([hp(r) for r in rows])), 3),
           "definition": "camera_to_landmark: frame returned by OpenCV -> landmarks ready. "
                         "landmark_to_intent: landmarks ready -> intent(s) written+fsynced. "
                         "Excludes sensor exposure, USB, driver, display.",
           "camera_to_landmark_ms": pct(col("camera_to_landmark_ms")),
           "camera_to_landmark_ms_hand_present": pct(col("camera_to_landmark_ms", hp)),
           "landmark_to_intent_ms": pct(col("landmark_to_intent_ms")),
           "landmark_to_intent_ms_emitting_frames": pct(col("landmark_to_intent_ms", em)),
           "total_ms": pct(col("total_ms"))}
    (RES / "latency_local.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()