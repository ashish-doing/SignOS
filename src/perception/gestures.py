"""Direct-gesture state machine. Pure logic (no cv2/mediapipe) so it is unit-testable."""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import NamedTuple, Optional

import numpy as np

from src.perception.filters import OneEuro2D


@dataclass
class HandObs:
    lm: np.ndarray  # (21,3) normalized camera space, mirrored (selfie) view
    label: str      # "left" | "right" = the user's real hand
    score: float    # tracker handedness score


class Event(NamedTuple):
    intent: str
    confidence: float
    pointer: Optional[tuple]
    hand: str
    raw_duration_ms: int


@dataclass
class GestureConfig:
    # All thresholds are STARTING VALUES, not tuned. Tune with the overlay numbers.
    hand: str = "right"
    min_hand_score: float = 0.6
    lost_ms: float = 200
    cursor_lm: int = 5             # index MCP: stays put while thumb/index close (no click drift)
    ext_ratio: float = 1.10        # finger extended if dist(wrist,tip)/dist(wrist,pip) > this
    curl_ratio: float = 1.00       # curled if < this
    pinch_enter: float = 0.25      # thumb-index distance / hand size
    pinch_exit: float = 0.40
    stable_ms: dict = field(default_factory=lambda: {
        "PINCH": 90, "POINT": 120, "SCROLL2": 120, "PALM": 120, "FIST": 150, "OTHER": 60})
    release_ms: float = 60         # leaving PINCH
    click_max_ms: float = 450
    click_cooldown_ms: float = 250
    drag_dist: float = 0.03        # camera-normalized units
    scroll_lock_dist: float = 0.04
    swipe_dist: float = 0.22
    swipe_window_ms: float = 350
    swipe_axis_ratio: float = 0.5
    swipe_min_palm_ms: float = 120
    swipe_cooldown_ms: float = 900
    palm_hold_ms: float = 800
    palm_hold_move: float = 0.04
    clutch_hold_ms: float = 700
    clutch_cooldown_ms: float = 1000
    filter_min_cutoff: float = 1.5
    filter_beta: float = 5.0


class Feat(NamedTuple):
    pinch: float
    ratios: tuple  # index, middle, ring, pinky
    palm: tuple


def analyze(lm, aspect: float) -> Feat:
    xy = lm[:, :2].astype(np.float64) * (aspect, 1.0)

    def d(a, b):
        return float(np.hypot(*(xy[a] - xy[b])))

    size = max(d(0, 9), 1e-6)
    ratios = tuple(d(0, t) / max(d(0, p), 1e-6) for t, p in ((8, 6), (12, 10), (16, 14), (20, 18)))
    palm = tuple(float(v) for v in lm[[0, 5, 9, 13, 17], :2].mean(axis=0))
    return Feat(d(4, 8) / size, ratios, palm)


class GestureEngine:
    def __init__(self, cfg: GestureConfig | None = None):
        self.cfg = cfg or GestureConfig()
        self.filt = OneEuro2D(min_cutoff=self.cfg.filter_min_cutoff, beta=self.cfg.filter_beta)
        self.clutched = False
        self.debug: dict = {}
        self._last_seen = -1e9
        self._click_ok_at = self._swipe_block_until = self._clutch_ok_at = 0.0
        self._reset_all()

    # ---- resets
    def _reset_motion(self):
        self._pinch = None
        self._scroll_axis = self._scroll_anchor = None
        self._hist = deque()
        self._palm_raw_since = None
        self._ph_anchor = None
        self._ph_t0, self._ph_fired = 0.0, False
        self.filt.reset()

    def _reset_all(self):
        self._reset_motion()
        self.stable, self._cand, self._cand_t, self._stable_since = "OTHER", None, 0.0, 0.0
        self._fist_t0, self._fist_fired = None, False

    # ---- helpers
    def _idle(self, lab=None):
        return Event("NONE", 0.0, None, lab or self.cfg.hand, 0)

    def busy(self, now: float) -> bool:
        """True while a direct gesture owns the hand (used to gate ISL)."""
        return self.stable in ("PINCH", "POINT", "SCROLL2") or now < self._swipe_block_until

    def _pick(self, hands):
        ok = [h for h in hands if h.score >= self.cfg.min_hand_score]
        if not ok:
            return None
        pref = [h for h in ok if h.label == self.cfg.hand]
        return max(pref or ok, key=lambda h: h.score)

    def _raw_pose(self, f: Feat) -> str:
        c = self.cfg
        idx, mid, rng, pnk = f.ratios
        ext, cur = c.ext_ratio, c.curl_ratio
        thr = c.pinch_exit if self.stable == "PINCH" else c.pinch_enter
        fist_like = mid < cur and rng < cur and pnk < cur
        if f.pinch < thr and not fist_like:
            return "PINCH"
        if idx > ext and mid > ext and rng > ext and pnk > ext:
            return "PALM"
        if idx > ext and mid > ext and rng < cur and pnk < cur:
            return "SCROLL2"
        if idx > ext and mid < cur and rng < cur and pnk < cur:
            return "POINT"
        if idx < cur and mid < cur and rng < cur and pnk < cur:
            return "FIST"
        return "OTHER"

    def _stabilize(self, raw: str, now: float):
        c = self.cfg
        key = "~PINCH" if (self.stable == "PINCH" and raw != "PINCH") else raw
        if key != self._cand:
            self._cand, self._cand_t = key, now
        need = c.release_ms if key == "~PINCH" else c.stable_ms[raw]
        if (key == "~PINCH" or raw != self.stable) and (now - self._cand_t) * 1000 >= need:
            self.stable, self._stable_since = raw, self._cand_t

    def _clutch(self, stable, now, lab, conf, ev) -> bool:
        c = self.cfg
        if stable != "FIST":
            self._fist_t0 = None
            return False
        if self._fist_t0 is None:
            self._fist_t0, self._fist_fired = now, False
        if (not self._fist_fired and (now - self._fist_t0) * 1000 >= c.clutch_hold_ms
                and now >= self._clutch_ok_at):
            self._fist_fired = True
            self._clutch_ok_at = now + c.clutch_cooldown_ms / 1000
            self.clutched = not self.clutched
            self._reset_motion()
            ev.append(Event("CLUTCH_ON" if self.clutched else "CLUTCH_OFF", conf, None, lab,
                            int((now - self._fist_t0) * 1000)))
            return True
        return False

    def _swipe(self, raw, now, f, lab, conf):
        c = self.cfg
        if raw != "PALM":
            self._palm_raw_since = None
            self._hist.clear()
            return None
        if self._palm_raw_since is None:
            self._palm_raw_since = now
        self._hist.append((now, f.palm[0], f.palm[1]))
        while self._hist and self._hist[0][0] < now - c.swipe_window_ms / 1000:
            self._hist.popleft()
        if now < self._swipe_block_until or (now - self._palm_raw_since) * 1000 < c.swipe_min_palm_ms:
            return None
        t0, x0, y0 = self._hist[0]
        dx, dy = f.palm[0] - x0, f.palm[1] - y0
        if abs(dx) >= c.swipe_dist and abs(dy) <= c.swipe_axis_ratio * abs(dx):
            self._swipe_block_until = now + c.swipe_cooldown_ms / 1000
            self._hist.clear()
            return Event("SWIPE_RIGHT" if dx > 0 else "SWIPE_LEFT", conf, None, lab, int((now - t0) * 1000))
        return None

    def _palm_hold(self, stable, now, f, lab, conf, ev):
        c = self.cfg
        if stable != "PALM":
            self._ph_anchor = None
            return
        p = f.palm
        if self._ph_anchor is None or math.hypot(p[0] - self._ph_anchor[0], p[1] - self._ph_anchor[1]) > c.palm_hold_move:
            self._ph_anchor, self._ph_t0, self._ph_fired = p, now, False
        elif not self._ph_fired and (now - self._ph_t0) * 1000 >= c.palm_hold_ms:
            self._ph_fired = True
            ev.append(Event("PALM_HOLD", conf, None, lab, int((now - self._ph_t0) * 1000)))

    # ---- main
    def update(self, hands, now: float, aspect: float = 4 / 3) -> list:
        c = self.cfg
        h = self._pick(hands)
        if h is None:
            if now - self._last_seen >= c.lost_ms / 1000:
                self._reset_all()
                return [self._idle()]
            return []  # short dropout: hold state, say nothing
        self._last_seen = now
        f = analyze(h.lm, aspect)
        raw = self._raw_pose(f)
        prev = self.stable
        self._stabilize(raw, now)
        stable = self.stable
        # Confidence for direct gestures = tracker hand score (heuristic, NOT a calibrated gesture probability).
        conf, lab = float(h.score), h.label
        dur = int((now - self._stable_since) * 1000)
        self.debug = {"raw": raw, "stable": stable, "pinch": round(f.pinch, 2),
                      "ratios": tuple(round(r, 2) for r in f.ratios), "clutched": self.clutched}
        ev: list = []

        if self._clutch(stable, now, lab, conf, ev) or self.clutched:
            return ev or [self._idle(lab)]

        sw = self._swipe(raw, now, f, lab, conf)
        if sw:
            ev.append(sw)
        self._palm_hold(stable, now, f, lab, conf, ev)

        # pinch release -> click (once)
        if prev == "PINCH" and stable != "PINCH" and self._pinch is not None:
            p, self._pinch = self._pinch, None
            d = int((now - p["t0"]) * 1000)
            if p["state"] == "DOWN" and not p["hold"] and d < c.click_max_ms and now >= self._click_ok_at:
                self._click_ok_at = now + c.click_cooldown_ms / 1000
                ev.append(Event("PINCH", conf, None, lab, d))

        silent = False
        if stable in ("PINCH", "POINT", "SCROLL2"):
            if stable == "SCROLL2" and prev != "SCROLL2":
                self.filt.reset()
            cur = h.lm[c.cursor_lm]
            px, py = self.filt(float(cur[0]), float(cur[1]), now)
            if stable == "PINCH":
                if prev != "PINCH" or self._pinch is None:
                    self._pinch = {"state": "DOWN", "t0": self._stable_since, "anchor": (px, py), "hold": False}
                p = self._pinch
                d = int((now - p["t0"]) * 1000)
                if p["state"] == "DOWN":
                    if math.hypot(px - p["anchor"][0], py - p["anchor"][1]) >= c.drag_dist:
                        p["state"] = "DRAG"
                    elif d >= c.click_max_ms and not p["hold"]:
                        p["hold"] = True
                        ev.append(Event("PINCH_HOLD_STILL", conf, None, lab, d))
                if p["state"] == "DRAG":
                    ev.append(Event("PINCH_HOLD_MOVE", conf, (px, py), lab, d))
                elif p["hold"]:
                    silent = True
                else:
                    ev.append(Event("TRANSITION", 0.0, None, lab, 0))  # click vs drag undecided
            elif stable == "POINT":
                ev.append(Event("POINT", conf, (px, py), lab, dur))
            else:  # SCROLL2
                if prev != "SCROLL2" or self._scroll_anchor is None:
                    self._scroll_anchor, self._scroll_axis = (px, py), None
                if self._scroll_axis is None:
                    dx, dy = px - self._scroll_anchor[0], py - self._scroll_anchor[1]
                    if math.hypot(dx, dy) >= c.scroll_lock_dist:
                        self._scroll_axis = "H" if abs(dx) > abs(dy) else "V"
                if self._scroll_axis:
                    ev.append(Event("SCROLL_" + self._scroll_axis, conf, (px, py), lab, dur))
                else:
                    ev.append(Event("TRANSITION", 0.0, None, lab, 0))

        if not ev and not silent:
            ev.append(Event("TRANSITION" if raw != stable else "NONE", 0.0, None, lab, 0))
        return ev