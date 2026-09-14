"""
MLX acceleration for Apple Silicon (M-series Mac).

Big creatures (hundreds/thousands of neurons) are slow to train on numpy/CPU.
This module runs the identical LTC predictive-learning on the Mac GPU via MLX,
using MLX autodiff instead of the hand-derived gradients — so it is the same
objective, accelerated. The numpy implementation in `growth.py` stays the
verified reference; this drop-in returns weights in the same format.

VALIDATE ON FIRST RUN on the Mac (compare one consolidation against numpy on a
small case); this path cannot be exercised in a non-Apple environment.

    from anima import accel_mlx
    theta = accel_mlx.train(theta, inv_tau, streams)   # same dict in, same dict out
"""

from __future__ import annotations

import numpy as np

try:
    import mlx.core as mx
    HAVE_MLX = True
except Exception:                       # not on Apple Silicon / MLX not installed
    HAVE_MLX = False

from .heart import PERCEPT_FIELDS
D_PERCEPT = len(PERCEPT_FIELDS)


def available() -> bool:
    return HAVE_MLX


def _stream_loss(p, inv_tau, I, dt):
    """Mean prediction loss over one stream (mirrors growth.loss_and_grads)."""
    h = mx.zeros((p["W"].shape[0],))
    total = mx.array(0.0)
    T = I.shape[0]
    for t in range(T):
        f = mx.sigmoid(p["W"] @ h + p["U"] @ I[t] + p["b"])
        pred = p["Pp"] @ h + p["cp"]
        if t < T - 1:
            resid = pred - I[t + 1][:D_PERCEPT]
            total = total + 0.5 * mx.sum(resid * resid)
        den = 1.0 + dt[t] * (inv_tau + f)
        num = h + dt[t] * (f * p["A"])
        h = num / den
    return total / max(T - 1, 1)


def train(theta, inv_tau, streams, epochs=60, lr=0.02, b1=0.9, b2=0.999, eps=1e-8,
          weight_decay=0.0, clip=None):
    """Adam(W) training on the Mac GPU; returns numpy weights in theta's format.

    Mirrors growth.consolidate's recipe (weight_decay, clip) so the tuned big-brain
    settings from anima.tune carry over unchanged.
    """
    if not HAVE_MLX:
        raise RuntimeError("MLX unavailable — use growth.consolidate (numpy) instead.")

    p = {k: mx.array(np.asarray(v, np.float32)) for k, v in theta.items()}
    it = mx.array(np.asarray(inv_tau, np.float32))
    data = [(mx.array(np.asarray(I, np.float32)), mx.array(np.asarray(dt, np.float32)))
            for I, dt in streams]

    def total_loss(params):
        return mx.add(*[_stream_loss(params, it, I, dt) for I, dt in data]) / len(data) \
            if len(data) > 1 else _stream_loss(params, it, *data[0])

    loss_grad = mx.value_and_grad(total_loss)
    m = {k: mx.zeros(v.shape) for k, v in p.items()}
    v = {k: mx.zeros(val.shape) for k, val in p.items()}
    for step in range(1, epochs + 1):
        _, g = loss_grad(p)
        if clip:
            gn = mx.sqrt(sum(mx.sum(gv * gv) for gv in g.values()))
            scale = mx.minimum(mx.array(1.0), clip / (gn + 1e-8))
            g = {k: gv * scale for k, gv in g.items()}
        for k in p:
            m[k] = b1 * m[k] + (1 - b1) * g[k]
            v[k] = b2 * v[k] + (1 - b2) * (g[k] * g[k])
            mh = m[k] / (1 - b1 ** step)
            vh = v[k] / (1 - b2 ** step)
            p[k] = p[k] - lr * (mh / (mx.sqrt(vh) + eps) + weight_decay * p[k])
        mx.eval(p, m, v)

    return {k: np.array(val, dtype=float) for k, val in p.items()}
