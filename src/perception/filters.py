"""One Euro filter (Casiez et al. 2012) for pointer smoothing."""
from __future__ import annotations

import math


def _alpha(dt: float, cutoff: float) -> float:
    tau = 1.0 / (2.0 * math.pi * cutoff)
    return 1.0 / (1.0 + tau / dt)


class OneEuro:
    def __init__(self, min_cutoff=1.5, beta=5.0, d_cutoff=1.0):
        self.min_cutoff, self.beta, self.d_cutoff = min_cutoff, beta, d_cutoff
        self.reset()

    def reset(self):
        self._t = self._x = None
        self._dx = 0.0

    def __call__(self, x: float, t: float) -> float:
        if self._t is None:
            self._t, self._x, self._dx = t, x, 0.0
            return x
        dt = max(t - self._t, 1e-3)
        a_d = _alpha(dt, self.d_cutoff)
        self._dx = a_d * ((x - self._x) / dt) + (1 - a_d) * self._dx
        a = _alpha(dt, self.min_cutoff + self.beta * abs(self._dx))
        self._x = a * x + (1 - a) * self._x
        self._t = t
        return self._x


class OneEuro2D:
    def __init__(self, **kw):
        self.fx, self.fy = OneEuro(**kw), OneEuro(**kw)

    def reset(self):
        self.fx.reset()
        self.fy.reset()

    def __call__(self, x: float, y: float, t: float):
        return self.fx(x, t), self.fy(y, t)