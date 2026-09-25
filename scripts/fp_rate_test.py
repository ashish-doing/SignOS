"""False-positive rate: use your hands NORMALLY (typing/mousing) in view of the camera, no intentional gestures."""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import cv2

from src.perception.capture import Camera
from src.perception.gestures import GestureConfig, GestureEngine
from src.perception.landmarks import HandTracker

ROOT = Path(__file__).resolve().parents[1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=120)
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--hand", default="right")
    ap.add_argument("--task-model", default=None)
    a = ap.parse_args()
    engine, tracker = GestureEngine(GestureConfig(hand=a.hand)), HandTracker(task_model=a.task_model)
    counts, prev, frames, hand_frames = Counter(), None, 0, 0
    print("Type / use the mouse naturally with your hands IN VIEW. NO intentional gestures. Ctrl+C stops early.")
    t_start = time.perf_counter()
    try:
        with Camera(a.camera) as cam:
            while time.perf_counter() - t_start < a.seconds:
                frame = cv2.flip(cam.read(), 1)
                t = time.perf_counter()
                hands = tracker.process(frame, t - t_start)
                frames += 1
                hand_frames += bool(hands)
                h, w = frame.shape[:2]
                for e in engine.update(hands, t, w / h):
                    if e.intent in ("NONE", "TRANSITION"):
                        prev = None
                    elif e.intent != prev:  # a continuous run of one intent = one event
                        counts[e.intent] += 1
                        prev = e.intent
    except KeyboardInterrupt:
        pass
    finally:
        tracker.close()
    minutes = (time.perf_counter() - t_start) / 60
    frac = hand_frames / max(frames, 1)
    total = sum(counts.values())
    out = {"tag": "MEASURED-LOCAL", "when": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "minutes": round(minutes, 2), "frames": frames, "hand_present_frac": round(frac, 3),
           "valid": frac >= 0.5, "events_total": total, "events_per_min": round(total / minutes, 3),
           "upper95_per_min_if_zero": round(3 / minutes, 3) if total == 0 else None,
           "by_intent": dict(counts), "note": "hand-present fraction < 0.5 makes this number meaningless"}
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / "fp_rate.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))
    if not out["valid"]:
        print("WARNING: hands were in view <50% of the time. Rerun with hands visible.")


if __name__ == "__main__":
    main()