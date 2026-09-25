"""MediaPipe hand landmarks. Legacy mp.solutions if present, else Tasks API with a .task model."""
from __future__ import annotations

import cv2
import numpy as np

from src.perception.gestures import HandObs


class HandTracker:
    def __init__(self, max_hands=2, min_det=0.6, min_track=0.5, task_model=None):
        import mediapipe as mp
        self._mp, self._last_ms = mp, -1
        if task_model is None and not hasattr(mp, "solutions"):
            from pathlib import Path
            _d = Path(__file__).resolve().parents[2] / "models" / "hand_landmarker.task"
            task_model = _d if _d.exists() else None
        if task_model is None and hasattr(mp, "solutions"):
            self._mode = "solutions"
            self._h = mp.solutions.hands.Hands(
                static_image_mode=False, max_num_hands=max_hands, model_complexity=0,
                min_detection_confidence=min_det, min_tracking_confidence=min_track)
        elif task_model is not None:
            from mediapipe.tasks import python as mpt
            from mediapipe.tasks.python import vision
            self._mode = "tasks"
            opts = vision.HandLandmarkerOptions(
                base_options=mpt.BaseOptions(model_asset_path=str(task_model)),
                running_mode=vision.RunningMode.VIDEO, num_hands=max_hands,
                min_hand_detection_confidence=min_det, min_tracking_confidence=min_track)
            self._h = vision.HandLandmarker.create_from_options(opts)
        else:
            raise RuntimeError("mediapipe has no mp.solutions; download hand_landmarker.task and pass --task-model")

    def process(self, frame_bgr, t_s: float) -> list:
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        out = []
        if self._mode == "solutions":
            rgb.flags.writeable = False
            res = self._h.process(rgb)
            if res.multi_hand_landmarks:
                for lms, hd in zip(res.multi_hand_landmarks, res.multi_handedness):
                    c = hd.classification[0]
                    arr = np.array([[p.x, p.y, p.z] for p in lms.landmark], np.float32)
                    out.append(HandObs(arr, c.label.lower(), float(c.score)))
        else:
            ms = max(int(t_s * 1000), self._last_ms + 1)
            self._last_ms = ms
            img = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
            res = self._h.detect_for_video(img, ms)
            for pts, cats in zip(res.hand_landmarks, res.handedness):
                arr = np.array([[p.x, p.y, p.z] for p in pts], np.float32)
                lab = cats[0].category_name.lower()
                out.append(HandObs(arr, {"left": "right", "right": "left"}.get(lab, lab), float(cats[0].score)))
        return out

    def close(self):
        self._h.close()