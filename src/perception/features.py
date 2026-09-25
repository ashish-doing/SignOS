"""Feature builder shared by recorder, trainer, and runtime (train/serve parity)."""
from __future__ import annotations

import numpy as np

HZ = 30
T_DEFAULT = 30
ASPECT = 4 / 3
FINGERS = ((1, 2, 3, 4), (5, 6, 7, 8), (9, 10, 11, 12), (13, 14, 15, 16), (17, 18, 19, 20))
PER_HAND = 42 + 15 + 42 + 2 + 1      # norm xy, joint angles, norm-xy velocity, wrist velocity, present
F_DIM = 2 * PER_HAND                 # slot 0 = left hand, slot 1 = right hand


def hands_to_slots(hands):
    lm = np.zeros((2, 21, 3), np.float32)
    pres = np.zeros(2, bool)
    for h in sorted(hands, key=lambda h: h.score):  # higher score written last wins
        s = 0 if h.label == "left" else 1
        lm[s], pres[s] = h.lm, True
    return lm, pres


def _hand_feats(lm, pres, hz, aspect):
    n = len(lm)
    p = lm.astype(np.float32).copy()
    p[..., 0] *= aspect
    size = np.maximum(np.linalg.norm(p[:, 9, :2] - p[:, 0, :2], axis=1), 1e-4)
    pos = (p[:, :, :2] - p[:, 0:1, :2]) / size[:, None, None]
    ang = np.zeros((n, 15), np.float32)
    k = 0
    for fing in FINGERS:
        chain = (0, *fing)
        for i in range(1, 4):
            v1 = p[:, chain[i]] - p[:, chain[i - 1]]
            v2 = p[:, chain[i + 1]] - p[:, chain[i]]
            cos = (v1 * v2).sum(1) / np.maximum(np.linalg.norm(v1, axis=1) * np.linalg.norm(v2, axis=1), 1e-6)
            ang[:, k] = np.arccos(np.clip(cos, -1.0, 1.0))
            k += 1
    vel = np.zeros_like(pos)
    vel[1:] = (pos[1:] - pos[:-1]) * hz
    wv = np.zeros((n, 2), np.float32)
    wv[1:] = (p[1:, 0, :2] - p[:-1, 0, :2]) * hz
    ok_prev = np.zeros(n, bool)
    ok_prev[1:] = pres[1:] & pres[:-1]
    vel[~ok_prev] = 0.0
    wv[~ok_prev] = 0.0
    out = np.concatenate([pos.reshape(n, -1), ang, vel.reshape(n, -1), wv,
                          pres[:, None].astype(np.float32)], axis=1)
    out[~pres] = 0.0
    return out


def build_features(lm, present, ts, hz=HZ, n=None, aspect=ASPECT):
    """lm (N,2,21,3), present (N,2), ts (N,) seconds -> (n,F_DIM) on a uniform hz grid
    (zero-order hold). n=None: whole sequence. n=k: last k grid frames ending at ts[-1]."""
    ts = np.asarray(ts, np.float64)
    if n is None:
        grid = ts[0] + np.arange(int((ts[-1] - ts[0]) * hz) + 1) / hz
    else:
        grid = ts[-1] - (n - 1 - np.arange(n)) / hz
    idx = np.clip(np.searchsorted(ts, grid, side="right") - 1, 0, len(ts) - 1)
    lm, present = np.asarray(lm)[idx], np.asarray(present)[idx].astype(bool)
    return np.concatenate([_hand_feats(lm[:, s], present[:, s], hz, aspect) for s in (0, 1)], axis=1)