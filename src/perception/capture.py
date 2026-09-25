"""Webcam capture + FPS meter. Frames are never written to disk here."""
from __future__ import annotations

import sys
import time
from collections import deque

import cv2


class CameraError(RuntimeError):
    pass


class FpsMeter:
    def __init__(self, window_s: float = 1.0):
        self.window_s = window_s
        self._ts: deque[float] = deque()

    def tick(self, now: float | None = None) -> float:
        now = time.perf_counter() if now is None else now
        self._ts.append(now)
        while self._ts and self._ts[0] < now - self.window_s:
            self._ts.popleft()
        if len(self._ts) < 2 or self._ts[-1] == self._ts[0]:
            return 0.0
        return (len(self._ts) - 1) / (self._ts[-1] - self._ts[0])


class Camera:
    def __init__(self, index: int = 0, width: int = 640, height: int = 480, fps: int = 30):
        self.index, self.width, self.height, self.fps = index, width, height, fps
        self._cap = None

    def open(self) -> "Camera":
        backends = [cv2.CAP_DSHOW, cv2.CAP_ANY] if sys.platform == "win32" else [cv2.CAP_ANY]
        for backend in backends:
            cap = cv2.VideoCapture(self.index, backend)
            if not cap.isOpened():
                cap.release()
                continue
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            cap.set(cv2.CAP_PROP_FPS, self.fps)
            for _ in range(15):  # warm-up: first frames often fail
                ok, _frame = cap.read()
                if ok:
                    self._cap = cap
                    return self
                time.sleep(0.05)
            cap.release()
        raise CameraError(
            f"could not open camera {self.index} (close Zoom/Teams/Camera app, or try --camera 1)"
        )

    def read(self):
        ok, frame = self._cap.read()
        if not ok:
            raise CameraError("camera read failed")
        return frame

    def release(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.release()