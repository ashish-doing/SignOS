"""Record labeled LANDMARK sequences to training/datasets/<label>/. No video unless --save-video.
Nothing here touches the network."""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

from src.perception.capture import Camera
from src.perception.features import hands_to_slots
from src.perception.landmarks import HandTracker
from src.perception.vocab import confirmed_signs

ROOT = Path(__file__).resolve().parents[1]
RECORD_S = 1.25
BACKGROUND = ("NONE", "TRANSITION")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--session", default=datetime.now().strftime("%Y%m%d"))
    ap.add_argument("--auto", action="store_true", help="back-to-back recording (use for NONE/TRANSITION)")
    ap.add_argument("--save-video", action="store_true", help="ALSO save mp4 for your own review")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--task-model", default=None)
    a = ap.parse_args()
    label = a.label.upper()
    if label not in BACKGROUND and label not in confirmed_signs():
        sys.exit(f"'{label}' is not a confirmed sign. Confirm vs ISLRTC, set source + confirmed=true in "
                 f"docs/isl_vocab.json and log it in docs/ATTRIBUTIONS.md first.")
    out_dir = ROOT / "training" / "datasets" / label
    out_dir.mkdir(parents=True, exist_ok=True)
    vid_dir = ROOT / "training" / "video" / label
    if a.save_video:
        vid_dir.mkdir(parents=True, exist_ok=True)
    saved, state, t_state, buf, writer, last_path = 0, "idle", 0.0, [], None, None
    msg = "SPACE = start   u = undo last   q = quit"
    tracker = HandTracker(task_model=a.task_model)
    t_ref = time.perf_counter()
    try:
        with Camera(a.camera) as cam:
            while saved < a.n:
                frame = cv2.flip(cam.read(), 1)
                now = time.perf_counter()
                hands = tracker.process(frame, now - t_ref)
                h, w = frame.shape[:2]
                if state == "countdown" and now - t_state >= (3.0 if not a.auto else 1.0):
                    state, t_state, buf = "rec", now, []
                    if a.save_video:
                        stem = f"{a.session}_{datetime.now().strftime('%H%M%S')}_{saved:03d}"
                        writer = cv2.VideoWriter(str(vid_dir / f"{stem}.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), 30, (w, h))
                if state == "rec":
                    lm, pres = hands_to_slots(hands)
                    buf.append((now, lm, pres))
                    if writer is not None:
                        writer.write(frame)
                    if now - t_state >= RECORD_S:
                        if writer is not None:
                            writer.release()
                            writer = None
                        pres_frac = float(np.mean([b[2].any() for b in buf]))
                        if label not in BACKGROUND and pres_frac < 0.6:
                            msg = f"discarded: hand visible only {pres_frac:.0%} of frames"
                        else:
                            ts = np.array([b[0] for b in buf]) - buf[0][0]
                            last_path = out_dir / f"{a.session}_{datetime.now().strftime('%H%M%S%f')}_{saved:03d}.npz"
                            np.savez_compressed(last_path, lm=np.stack([b[1] for b in buf]),
                                                present=np.stack([b[2] for b in buf]), ts=ts,
                                                aspect=np.float64(w / h), label=np.array(label),
                                                session=np.array(a.session), fps=np.float64(len(buf) / ts[-1]))
                            saved += 1
                            msg = f"saved {saved}/{a.n}"
                        state, t_state = ("countdown", now) if a.auto else ("idle", now)
                for ho in hands:
                    for x, y, _ in ho.lm:
                        cv2.circle(frame, (int(x * w), int(y * h)), 2, (0, 255, 0), -1)
                hud = f"{label}  {saved}/{a.n}  session {a.session}  [{state}]"
                if state == "countdown":
                    hud += f"  starting in {max(0.0, (3.0 if not a.auto else 1.0) - (now - t_state)):.1f}s"
                if state == "rec":
                    cv2.circle(frame, (w - 20, 20), 8, (0, 0, 255), -1)
                cv2.putText(frame, hud, (8, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
                cv2.putText(frame, msg, (8, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 255, 200), 1, cv2.LINE_AA)
                cv2.imshow("gesture studio", frame)
                k = cv2.waitKey(1) & 0xFF
                if k == ord("q"):
                    break
                if k == ord(" ") and state == "idle":
                    state, t_state = "countdown", now
                if k == ord("u") and last_path is not None and last_path.exists():
                    last_path.unlink()
                    last_path, saved, msg = None, max(0, saved - 1), "undid last sample"
                if a.auto and state == "idle" and saved == 0 and k == ord(" "):
                    state, t_state = "countdown", now
    finally:
        tracker.close()
        cv2.destroyAllWindows()
    print(f"{label}: {len(list(out_dir.glob('*.npz')))} samples in {out_dir}")


if __name__ == "__main__":
    main()