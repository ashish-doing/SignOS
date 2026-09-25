"""Batch 1 runner: open webcam, print live FPS, emit throttled NONE to the intent bus."""
from __future__ import annotations

import argparse
import time

from src.perception.capture import Camera, CameraError, FpsMeter
from src.perception.intent_bus import DEFAULT_BUS_PATH, IntentBusWriter


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--seconds", type=float, default=10.0, help="0 = run until Ctrl+C")
    ap.add_argument("--idle-hz", type=float, default=5.0, help="NONE emit rate")
    ap.add_argument("--bus", default=str(DEFAULT_BUS_PATH))
    args = ap.parse_args(argv)

    meter = FpsMeter()
    idle_period = 1.0 / args.idle_hz
    start = last_emit = last_print = time.perf_counter()
    frames = emitted = 0
    try:
        with Camera(args.camera) as cam, IntentBusWriter(args.bus) as bus:
            print(f"camera {args.camera} open | bus -> {bus.path}")
            while True:
                cam.read()
                now = time.perf_counter()
                fps = meter.tick(now)
                frames += 1
                if now - last_emit >= idle_period:
                    bus.emit("gesture", "NONE", 0.0, source_fps=round(fps, 2))
                    emitted += 1
                    last_emit = now
                if now - last_print >= 1.0:
                    print(f"fps={fps:5.1f}  frames={frames}  NONE emitted={emitted}")
                    last_print = now
                if args.seconds and now - start >= args.seconds:
                    break
    except CameraError as e:
        print(f"[camera error] {e}")
        return 1
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())