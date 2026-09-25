import numpy as np

from src.perception.features import F_DIM, PER_HAND, build_features
from src.perception.isl_runtime import IslConfirmer


def _seq(n=45, fps=30, seed=0):
    rng = np.random.default_rng(seed)
    return rng.random((n, 2, 21, 3)).astype(np.float32), np.ones((n, 2), bool), np.arange(n) / fps


def test_shapes():
    lm, pr, ts = _seq()
    assert build_features(lm, pr, ts).shape[1] == F_DIM
    assert build_features(lm, pr, ts, n=30).shape == (30, F_DIM)


def test_absent_slot_is_zero():
    lm, pr, ts = _seq()
    pr[:, 0] = False
    assert np.all(build_features(lm, pr, ts, n=30)[:, :PER_HAND] == 0)


def test_translation_invariant():
    lm, pr, ts = _seq()
    a = build_features(lm, pr, ts, n=30)
    lm2 = lm.copy()
    lm2[..., :2] += 0.2
    assert np.allclose(a, build_features(lm2, pr, ts, n=30), atol=1e-3)


def test_irregular_fps_resamples_to_fixed_grid():
    ts = np.cumsum(np.random.default_rng(1).uniform(0.025, 0.04, 50))
    lm, pr, _ = _seq(50)
    assert build_features(lm, pr, ts, n=30).shape == (30, F_DIM)


def _p(sign, v=0.95):
    return {"NONE": 1 - v, "TRANSITION": 0.0, sign: v}


def test_confirmer_needs_k_then_fires_once_then_rearms():
    c = IslConfirmer(["NONE", "TRANSITION", "COPY"])
    out = [c.update(_p("COPY"), t * 0.1) for t in range(3)]
    assert out[0][0] == "TRANSITION" and out[2][0] == "ISL_COPY"
    assert all(c.update(_p("COPY"), 0.3 + t * 0.1) is None for t in range(1, 8))  # held sign: no repeat
    c.update({"NONE": 0.99, "TRANSITION": 0.0, "COPY": 0.01}, 1.0)               # release re-arms
    outs = [c.update(_p("COPY"), 1.1 + t * 0.1) for t in range(3)]
    assert outs[-1][0] == "TRANSITION"                                            # cooldown (1.5s) not over
    outs = [c.update(_p("COPY"), 2.0 + t * 0.1) for t in range(3)]
    assert outs[0][0] == "ISL_COPY" and outs[1] is None and outs[2] is None  # fires once, then re-arm needed


def test_confirmer_blocked_resets():
    c = IslConfirmer(["NONE", "TRANSITION", "COPY"])
    c.update(_p("COPY"), 0.0)
    c.update(_p("COPY"), 0.1)
    assert c.update(_p("COPY"), 0.2, blocked=True) is None
    assert c.update(_p("COPY"), 0.3)[0] == "TRANSITION"  # streak restarted