import numpy as np
import pytest

from src.perception.gestures import GestureEngine, HandObs
from src.perception.intent_bus import make_intent, validate_intent

FPS = 30


def make_hand(pose, cx=0.5, cy=0.6, score=0.95, label="right"):
    P = {5: (-.04, -.11), 9: (0, -.12), 13: (.035, -.11), 17: (.07, -.09)}
    lm = np.zeros((21, 3), np.float32)
    lm[1], lm[2], lm[3] = (-.03, -.03, 0), (-.05, -.06, 0), (-.07, -.09, 0)
    ext = {"point": (1, 0, 0, 0), "scroll": (1, 1, 0, 0), "palm": (1, 1, 1, 1),
           "fist": (0, 0, 0, 0), "pinch": (1, 1, 1, 1)}[pose]
    for e, m in zip(ext, (5, 9, 13, 17)):
        mx, my = P[m]
        lm[m] = (mx, my, 0)
        for j, d in enumerate((-.045, -.075, -.10) if e else (-.04, -.01, 0.0)):
            lm[m + 1 + j] = (mx, my + d, 0)
    if pose == "palm":
        lm[4] = (-.09, -.12, 0)
    elif pose == "pinch":
        lm[6], lm[7], lm[8] = (-.04, -.15, 0), (-.05, -.165, 0), (-.06, -.17, 0)
        lm[4] = (-.062, -.17, 0)
    else:
        lm[4] = (-.02, -.06, 0)
    lm[:, 0] += cx
    lm[:, 1] += cy
    return HandObs(lm, label, score)


class Seq:
    def __init__(self):
        self.t, self.f = 0.0, []

    def add(self, pose, dur, x=(.5, .5), y=(.6, .6), score=.95):
        n = max(int(round(dur * FPS)), 1)
        for i in range(n):
            a = i / max(n - 1, 1)
            hand = None if pose is None else make_hand(
                pose, cx=x[0] + (x[1] - x[0]) * a, cy=y[0] + (y[1] - y[0]) * a, score=score)
            self.f.append((self.t, hand))
            self.t += 1 / FPS
        return self


def run(frames):
    eng, out = GestureEngine(), []
    for t, h in frames:
        for e in eng.update([h] if h is not None else [], t):
            out.append((t, e))
    return out


def names(out):
    return [e.intent for _, e in out]


def test_idle_no_hand_is_none():
    assert set(names(run(Seq().add(None, 1.0).f))) == {"NONE"}


def test_point_needs_temporal_stability():
    pts = [(t, e) for t, e in run(Seq().add("point", 0.6).f) if e.intent == "POINT"]
    assert len(pts) > 5 and pts[0][0] >= 0.1
    assert pts[0][1].pointer == pytest.approx((0.46, 0.49), abs=0.01)


def test_transition_while_forming():
    assert "TRANSITION" in names(run(Seq().add("point", 0.3).f))


def test_low_score_hand_ignored():
    assert "POINT" not in names(run(Seq().add("point", 0.6, score=0.3).f))


def test_single_pinch_frame_never_clicks():
    assert "PINCH" not in names(run(Seq().add("point", .5).add("pinch", 1 / FPS).add("point", .5).f))


def test_click_fires_exactly_once():
    n = names(run(Seq().add("point", .5).add("pinch", .2).add("point", .6).f))
    assert n.count("PINCH") == 1 and "PINCH_HOLD_MOVE" not in n


def test_two_clicks_after_cooldown():
    s = Seq().add("point", .5).add("pinch", .2).add("point", .6).add("pinch", .2).add("point", .5)
    assert names(run(s.f)).count("PINCH") == 2


def test_drag_streams_and_no_click():
    s = Seq().add("point", .5, x=(.4, .4)).add("pinch", 1.0, x=(.4, .6)).add("point", .5, x=(.6, .6))
    n = names(run(s.f))
    assert n.count("PINCH_HOLD_MOVE") > 8 and "PINCH" not in n


def test_hold_still_once_no_click():
    n = names(run(Seq().add("point", .5).add("pinch", 1.0).add("point", .5).f))
    assert n.count("PINCH_HOLD_STILL") == 1 and "PINCH" not in n


def test_scroll_axis_locks_vertical_and_horizontal():
    v = names(run(Seq().add("scroll", .3).add("scroll", .6, y=(.4, .7)).f))
    assert v.count("SCROLL_V") > 5 and "SCROLL_H" not in v
    h = names(run(Seq().add("scroll", .3).add("scroll", .6, x=(.3, .6)).f))
    assert h.count("SCROLL_H") > 5 and "SCROLL_V" not in h


def test_swipe_right_once_return_stroke_suppressed():
    s = Seq().add("palm", .3, x=(.3, .3)).add("palm", .25, x=(.3, .7)).add("palm", .25, x=(.7, .3))
    n = names(run(s.f))
    assert n.count("SWIPE_RIGHT") == 1 and "SWIPE_LEFT" not in n


def test_swipe_left():
    s = Seq().add("palm", .3, x=(.7, .7)).add("palm", .25, x=(.7, .3))
    assert names(run(s.f)).count("SWIPE_LEFT") == 1


def test_slow_drift_is_not_a_swipe():
    s = Seq().add("palm", .3, x=(.3, .3)).add("palm", 3.0, x=(.3, .5))
    n = names(run(s.f))
    assert "SWIPE_LEFT" not in n and "SWIPE_RIGHT" not in n


def test_palm_hold_once():
    assert names(run(Seq().add("palm", 1.5).f)).count("PALM_HOLD") == 1


def test_clutch_toggle_blocks_gestures():
    s = (Seq().add("fist", 1.2).add("point", .5).add("pinch", .2).add("point", .5)
         .add("fist", 1.5).add("point", .5))
    ev = [(t, e.intent) for t, e in run(s.f)]
    on = [t for t, i in ev if i == "CLUTCH_ON"]
    off = [t for t, i in ev if i == "CLUTCH_OFF"]
    assert len(on) == 1 and len(off) == 1 and on[0] < off[0]
    assert not {"POINT", "PINCH"} & {i for t, i in ev if on[0] < t < off[0]}
    assert "POINT" in [i for t, i in ev if t > off[0]]


def test_hand_loss_resets_and_no_ghost_click():
    s = Seq().add("point", .5, x=(.4, .4)).add("pinch", .8, x=(.4, .6)).add(None, .6)
    n = names(run(s.f))
    assert "PINCH" not in n and n[-1] == "NONE"


def test_events_satisfy_bus_contract():
    s = (Seq().add("point", .5).add("pinch", .2).add("point", .5).add("pinch", .8, x=(.4, .6))
         .add("point", .4).add("scroll", .6, y=(.4, .7)).add("palm", .3).add("palm", .25, x=(.3, .7))
         .add("fist", 1.2))
    for _, e in run(s.f):
        ptr = None if e.pointer is None else {"x": e.pointer[0], "y": e.pointer[1]}
        validate_intent(make_intent("gesture", e.intent, e.confidence, pointer=ptr,
                                    hand=e.hand, raw_duration_ms=e.raw_duration_ms))