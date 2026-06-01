"""
tune — find the training recipe that makes a bigger brain actually pay off.

The probe found that more neurons regress under the *default* recipe: high-capacity
liquid nets overfit and need stabilising. This harness builds a task rich enough
that 24 neurons genuinely can't fit it (a person whose mood is several overlapping
rhythms), then sweeps brain size against recipe to find settings where big beats
small. The winning recipe (weight decay + gradient clipping + more epochs) carries
straight over to the MLX GPU trainer.

    python3 -m anima.tune
"""

from __future__ import annotations

import time

import numpy as np

from .heart import Genome, D_IN, PERCEPT_FIELDS
from .growth import consolidate, evaluate

D_PERCEPT = len(PERCEPT_FIELDS)


def rich_stream(seed, days=4, per_day=18):
    """A person whose inner life is several overlapping rhythms — too rich for 24."""
    rng = np.random.default_rng(seed)
    periods = rng.uniform(3, 40, 5)            # hours
    amps = rng.uniform(0.1, 0.4, 5)
    phases = rng.uniform(0, 2 * np.pi, 5)
    I_seq, dt_seq = [], []
    for step in range(days * per_day):
        hour = 24.0 * (step % per_day) / per_day
        t = step * (24.0 / per_day)
        mood = float(np.clip(sum(a * np.sin(2 * np.pi * t / p + ph)
                                 for a, p, ph in zip(amps, periods, phases)), -1, 1))
        present = 1.0 if 7 < hour < 23 else 0.0
        percept = np.zeros(D_PERCEPT)
        percept[:6] = [present, present * 0.6, mood, 0.3 + 0.4 * abs(mood),
                       0.5 + 0.5 * mood, 0.5 * (1 + np.sin(2 * np.pi * step / (per_day * 5)))]
        tod = 2 * np.pi * hour / 24
        I_seq.append(np.concatenate([percept, [1.0, 0.0, np.sin(tod), np.cos(tod)]]))
        dt_seq.append(24.0 * 60.0 / per_day)
    return I_seq, dt_seq


def _run(n, train, hold, **recipe):
    g = Genome.from_seed(7, n=n)
    theta = g.theta()
    t0 = time.time()
    consolidate(theta, g.inv_tau, train, hold, **recipe)
    return evaluate(theta, g.inv_tau, hold), time.time() - t0


def main():
    print("Task: one person, several overlapping rhythms. Sweeping size x recipe,")
    print("measuring held-out prediction error. Verdict is computed from the numbers.\n")
    train = [rich_stream(s) for s in (1, 2, 3, 4)]
    hold = [rich_stream(s) for s in (5, 6)]

    recipes = {
        "default (60ep)": dict(epochs=60, lr=0.02),
        "long (200ep)": dict(epochs=200, lr=0.02, clip=5.0),
        "long+decay": dict(epochs=200, lr=0.02, clip=5.0, weight_decay=1e-5),
    }
    print(f"  {'size':>6} " + "  ".join(f"{name:>16}" for name in recipes))
    grid = {}
    for n in (24, 64, 256):
        row = []
        for name, rec in recipes.items():
            err, _ = _run(n, train, hold, **rec)
            grid[(n, name)] = err
            row.append(f"{err:16.4f}")
        print(f"  N={n:4d} " + "  ".join(row))

    best_n, best_recipe = min(grid, key=grid.get)
    small_best = min(grid[(24, r)] for r in recipes)
    big_best = min(grid[(256, r)] for r in recipes)
    print(f"\n  Best overall: N={best_n}, {best_recipe} ({grid[(best_n, best_recipe)]:.4f}).")
    if big_best < small_best * 0.9:
        print("  Verdict: more neurons clearly help here.")
    elif big_best < small_best:
        print("  Verdict: more neurons help only marginally.")
    else:
        print("  Verdict (honest): more neurons do NOT help on this task — capacity is")
        print("  not the bottleneck. Don't scale blindly; validate on real lived data")
        print("  (your own, on the Mac) before adding neurons. The recipe knobs")
        print("  (clip, weight_decay) are available and carry over to accel_mlx.")


if __name__ == "__main__":
    main()
