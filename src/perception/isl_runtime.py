"""ISL inference (ONNX Runtime) + temporal confirmation before anything reaches the bus."""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path

import numpy as np

from src.perception.features import build_features, hands_to_slots

BACKGROUND = ("NONE", "TRANSITION")


class IslClassifier:
    def __init__(self, onnx_path, meta_path=None, providers=None):
        import onnxruntime as ort
        onnx_path = Path(onnx_path)
        meta_path = Path(meta_path) if meta_path else onnx_path.with_name("isl_meta.json")
        m = json.loads(meta_path.read_text(encoding="utf-8"))
        self.classes, self.T, self.hz, self.aspect = m["classes"], int(m["T"]), float(m["hz"]), float(m["aspect"])
        self.mean, self.std = np.array(m["mean"], np.float32), np.array(m["std"], np.float32)
        self.sess = ort.InferenceSession(str(onnx_path), providers=providers or ["CPUExecutionProvider"])
        self._in = self.sess.get_inputs()[0].name
        self._buf = deque()

    def push(self, t: float, hands) -> None:
        lm, pres = hands_to_slots(hands)
        self._buf.append((t, lm, pres))
        while self._buf and t - self._buf[0][0] > 2.0:
            self._buf.popleft()

    def predict(self):
        if len(self._buf) < 2:
            return None
        ts = np.array([b[0] for b in self._buf], np.float64)
        if ts[-1] - ts[0] < (self.T - 1) / self.hz:
            return None
        lm = np.stack([b[1] for b in self._buf])
        pr = np.stack([b[2] for b in self._buf])
        f = build_features(lm, pr, ts, self.hz, self.T, self.aspect)
        x = ((f - self.mean) / self.std)[None].astype(np.float32)
        logits = self.sess.run(None, {self._in: x})[0][0]
        e = np.exp(logits - logits.max())
        return dict(zip(self.classes, map(float, e / e.sum())))


class IslConfirmer:
    """Fire ISL_<NAME> only after k consecutive top-1 predictions >= thr, then cooldown + re-arm."""

    def __init__(self, classes, thr=0.85, k=3, cooldown_s=1.5, cand_p=0.5):
        self.signs = {c for c in classes if c not in BACKGROUND}
        self.thr, self.k, self.cooldown_s, self.cand_p = thr, k, cooldown_s, cand_p
        self._top, self._streak, self._ok_at, self._armed = None, 0, 0.0, True

    def update(self, probs: dict, now: float, blocked: bool = False):
        if blocked:
            self._top, self._streak = None, 0
            return None
        top = max(probs, key=probs.get)
        p = probs[top]
        if top not in self.signs or p < self.cand_p:
            self._top, self._streak, self._armed = None, 0, True
            return None
        self._streak = self._streak + 1 if top == self._top else 1
        self._top = top
        if not self._armed:
            return None
        if p >= self.thr and self._streak >= self.k and now >= self._ok_at:
            self._ok_at, self._armed, self._streak = now + self.cooldown_s, False, 0
            return ("ISL_" + top, p)
        return ("TRANSITION", p)