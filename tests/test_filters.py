import numpy as np

from src.perception.filters import OneEuro


def test_first_sample_passthrough():
    assert OneEuro()(0.7, 0.0) == 0.7


def test_static_input_stays_put():
    f = OneEuro()
    ys = [f(0.4, i / 30) for i in range(60)]
    assert abs(ys[-1] - 0.4) < 1e-6


def test_reduces_jitter():
    rng = np.random.default_rng(0)
    xs = 0.5 + rng.normal(0, 0.01, 300)
    f = OneEuro()
    ys = [f(x, i / 30) for i, x in enumerate(xs)]
    assert np.std(ys[30:]) < 0.7 * np.std(xs[30:])


def test_tracks_fast_motion():
    f = OneEuro()
    y = 0.0
    for i in range(31):
        y = f(i / 30, i / 30)
    assert abs(y - 1.0) < 0.15