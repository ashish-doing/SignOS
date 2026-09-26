"""Track A runner: camera -> hand landmarks -> gesture engine (+ optional ISL) -> intent bus."""
from __future__ import annotations

import argparse
import csv
import time
from pathlib import Path

import cv2

from src.perception.capture import Camera, CameraError, FpsMeter
from src.perception.gestures import Event, GestureConfig, GestureEngine
from src.perception.intent_bus import DEFAULT_BUS_PATH, IntentBusWriter
from src.perception.landmarks import HandTracker

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_frame_lock = threading.Lock()
_latest_jpeg: bytes | None = None


def _publish_frame(frame) -> None:
    global _latest_jpeg
    ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
    if ok:
        with _frame_lock:
            _latest_jpeg = buf.tobytes()


class _StreamHandler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path != "/frame.mjpg":
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Age", "0")
        self.send_header("Cache-Control", "no-cache, private")
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=FRAME")
        self.end_headers()
        try:
            while True:
                with _frame_lock:
                    jpg = _latest_jpeg
                if jpg is not None:
                    self.wfile.write(b"--FRAME\r\nContent-Type: image/jpeg\r\nContent-Length: "
                                      + str(len(jpg)).encode() + b"\r\n\r\n" + jpg + b"\r\n")
                time.sleep(0.05)
        except (BrokenPipeError, ConnectionResetError):
            pass


def _start_stream_server(port: int) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", port), _StreamHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"camera stream -> http://localhost:{port}/frame.mjpg")

class IdleThrottle:
    """NONE/TRANSITION are rate-limited; any real intent resets it so the next idle passes at once."""

    def __init__(self, hz: float):
        self.period, self.last = 1.0 / hz, {}

    def allow(self, intent: str, now: float) -> bool:
        if intent not in ("NONE", "TRANSITION"):
            self.last.clear()
            return True
        if now - self.last.get(intent, -1e9) >= self.period:
            self.last[intent] = now
            return True
        return False


def _clamp(v) -> float:
    return min(1.0, max(0.0, float(v)))


def send(bus, thr, ev: Event, now: float, fps: float, kind="gesture") -> bool:
    if not thr.allow(ev.intent, now):
        return False
    ptr = None if ev.pointer is None else {"x": _clamp(ev.pointer[0]), "y": _clamp(ev.pointer[1])}
    bus.emit(kind, ev.intent, round(float(ev.confidence), 3), pointer=ptr, hand=ev.hand,
             raw_duration_ms=int(ev.raw_duration_ms), source_fps=round(fps, 2))
    return True


def render_overlay(frame, hands, engine, fps, last_ptr, last_intent):
    h, w = frame.shape[:2]
    for ho in hands:
        for x, y, _ in ho.lm:
            cv2.circle(frame, (int(x * w), int(y * h)), 2, (0, 255, 0), -1)
    if last_ptr is not None:
        cv2.circle(frame, (int(last_ptr[0] * w), int(last_ptr[1] * h)), 10, (0, 0, 255), -1)
    d = engine.debug
    lines = [f"fps {fps:4.1f}   last: {last_intent}",
             f"raw {d.get('raw', '-')}  stable {d.get('stable', '-')}  clutched {engine.clutched}",
             f"pinch {d.get('pinch', '-')}  ratios(i,m,r,p) {d.get('ratios', '-')}",
             "hands: " + (", ".join(f"{ho.label} {ho.score:.2f} x={ho.lm[0][0]:.2f}" for ho in hands) or "none")]
    cv2.rectangle(frame, (0, 0), (w, 20 + 18 * len(lines)), (0, 0, 0), -1)
    for i, t in enumerate(lines):
        cv2.putText(frame, t, (8, 20 + 18 * i), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return frame


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--hand", default="right", choices=["left", "right"])
    ap.add_argument("--seconds", type=float, default=0.0, help="0 = until q / Ctrl+C")
    ap.add_argument("--idle-hz", type=float, default=5.0)
    ap.add_argument("--bus", default=str(DEFAULT_BUS_PATH))
    ap.add_argument("--no-window", action="store_true")
    ap.add_argument("--no-stream", action="store_true")
    ap.add_argument("--stream-port", type=int, default=8421)
    ap.add_argument("--task-model", default=None)
    ap.add_argument("--isl", default=None, help="path to models/isl_gru.onnx")
    ap.add_argument("--isl-hz", type=float, default=10.0)
    ap.add_argument("--no-isl-gate", action="store_true", help="allow ISL while a direct gesture is active")
    ap.add_argument("--timing-csv", default=None)
    args = ap.parse_args(argv)

    engine = GestureEngine(GestureConfig(hand=args.hand))
    tracker = HandTracker(task_model=args.task_model)
    isl = confirmer = None
    if args.isl:
        from src.perception.isl_runtime import IslClassifier, IslConfirmer
        isl = IslClassifier(args.isl)
        confirmer = IslConfirmer(isl.classes)
    g_thr, i_thr = IdleThrottle(args.idle_hz), IdleThrottle(args.idle_hz)
    meter, rows = FpsMeter(), []
    last_ptr, last_ptr_t, last_intent, next_isl = None, 0.0, "-", 0.0
    t_start = time.perf_counter()
    try:
        with Camera(args.camera) as cam, IntentBusWriter(args.bus) as bus:
            print(f"camera {args.camera} open | bus -> {bus.path}")
            if not args.no_stream:
                _start_stream_server(args.stream_port)
            while True:
                frame = cv2.flip(cam.read(), 1)
                t0 = time.perf_counter()
                fps = meter.tick(t0)
                h, w = frame.shape[:2]
                hands = tracker.process(frame, t0 - t_start)
                t1 = time.perf_counter()
                emitted = 0
                for ev in engine.update(hands, t0, w / h):
                    if send(bus, g_thr, ev, t0, fps):
                        emitted += 1
                        if ev.intent not in ("NONE", "TRANSITION"):
                            last_intent = ev.intent
                        if ev.pointer is not None:
                            last_ptr, last_ptr_t = ev.pointer, t0
                if isl is not None:
                    isl.push(t0, hands)
                    if t0 >= next_isl:
                        next_isl = t0 + 1.0 / args.isl_hz
                        probs = isl.predict()
                        if probs is not None:
                            blocked = engine.clutched or not hands or (not args.no_isl_gate and engine.busy(t0))
                            res = confirmer.update(probs, t0, blocked)
                            if res:
                                intent, p = res
                                lab = "two" if len(hands) >= 2 else hands[0].label
                                ev = Event(intent, p, None, lab, int(isl.T * 1000 / isl.hz))
                                if send(bus, i_thr, ev, t0, fps, kind="isl"):
                                    emitted += 1
                                    if intent != "TRANSITION":
                                        last_intent = intent
                t2 = time.perf_counter()
                rows.append((t0 - t_start, len(hands), emitted, (t1 - t0) * 1000, (t2 - t1) * 1000, (t2 - t0) * 1000))
                render_overlay(frame, hands, engine, fps, last_ptr if t0 - last_ptr_t < 0.5 else None, last_intent)
                if not args.no_stream:
                    _publish_frame(frame)
                if not args.no_window:
                    cv2.imshow("SignOS Track A (q to quit)", frame)
                    if cv2.waitKey(1) & 0xFF in (27, ord("q")):
                        break
                if args.seconds and t2 - t_start >= args.seconds:
                    break
    except CameraError as e:
        print(f"[camera error] {e}")
        return 1
    except KeyboardInterrupt:
        pass
    finally:
        tracker.close()
        cv2.destroyAllWindows()
        if args.timing_csv and rows:
            p = Path(args.timing_csv)
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w", newline="") as fh:
                wr = csv.writer(fh)
                wr.writerow(["t_s", "hands", "n_emitted", "camera_to_landmark_ms", "landmark_to_intent_ms", "total_ms"])
                wr.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())