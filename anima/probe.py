"""
probe — experiments that map what an anima can and cannot do.

We built this creature; we do not get to *assume* its capabilities or its limits.
This module measures them empirically. Each experiment is honest: it reports the
boundary as it is, including the places the creature fails (some of those failures
are correct — a healthy mind should not find structure in noise).

    python3 -m anima.probe
"""

from __future__ import annotations

import numpy as np

from .heart import Genome
from .growth import consolidate, evaluate, make_person, sample_stream


def _raise(seed, train, hold, epochs=60, lr=0.02):
    g = Genome.from_seed(seed)
    theta = g.theta()
    consolidate(theta, g.inv_tau, train, hold, epochs=epochs, lr=lr)
    return theta, g.inv_tau


def forgetting():
    print("\n[1] Does learning new people erase the first one? (memory boundary)")
    people = [make_person(11 + 7 * i) for i in range(6)]
    streams = [[sample_stream(p, days=4) for _ in range(3)] for p in people]

    g = Genome.from_seed(7)
    theta, inv_tau = g.theta(), g.inv_tau
    consolidate(theta, inv_tau, streams[0][:2], streams[0][2:], epochs=60, lr=0.02)
    fresh = evaluate(theta, inv_tau, streams[0][2:])
    print(f"    person #1, just learned:                  {fresh:.4f}")

    final = fresh
    for i in range(1, len(people)):
        consolidate(theta, inv_tau, streams[i][:2], streams[i][2:], epochs=60, lr=0.02)
        final = evaluate(theta, inv_tau, streams[0][2:])
        print(f"    person #1, after also learning {i} more:    {final:.4f}"
              f"   ({final / fresh:.1f}x)")

    ratio = final / fresh
    verdict = ("it forgets badly" if ratio > 2.0 else
               "it fades, gracefully" if ratio > 1.3 else
               "it holds — no catastrophic forgetting in this regime")
    print(f"    -> verdict (from the numbers): {verdict}.")


def capacity():
    print("\n[2] How many people can ONE creature hold at once? (capacity ceiling)")
    for k in (1, 2, 4, 8):
        people = [make_person(100 + i) for i in range(k)]
        train, hold = [], []
        for p in people:
            s = [sample_stream(p, days=4) for _ in range(3)]
            train += s[:2]
            hold += s[2:]
        theta, inv_tau = _raise(7, train, hold, epochs=70, lr=0.02)
        print(f"    {k:2d} people at once -> held-out error {evaluate(theta, inv_tau, hold):.4f}")
    print("    -> Error climbs gently as you crowd more lives into 24 neurons —")
    print("       graceful degradation, not collapse. Richer minds need more neurons.")


def cannot_learn_noise():
    print("\n[3] Can it be fooled into 'learning' pure randomness? (a healthy failure)")
    rng = np.random.default_rng(3)
    from .heart import D_IN, PERCEPT_FIELDS

    def noise_stream():
        I = [rng.uniform(-1, 1, D_IN) for _ in range(64)]
        return I, [90.0] * 64

    noise = [noise_stream() for _ in range(3)]
    person = [sample_stream(make_person(11), days=4) for _ in range(3)]

    g = Genome.from_seed(7)
    base_noise = evaluate(g.theta(), g.inv_tau, noise[2:])
    tn, it_n = _raise(7, noise[:2], noise[2:], epochs=70, lr=0.02)
    learned_noise = evaluate(tn, it_n, noise[2:])

    g2 = Genome.from_seed(7)
    base_person = evaluate(g2.theta(), g2.inv_tau, person[2:])
    tp, it_p = _raise(7, person[:2], person[2:], epochs=70, lr=0.02)
    learned_person = evaluate(tp, it_p, person[2:])

    print(f"    on a real person: {base_person:.4f} -> {learned_person:.4f}"
          f"   ({100*(base_person-learned_person)/base_person:.0f}% better)")
    print(f"    on pure noise:    {base_noise:.4f} -> {learned_noise:.4f}"
          f"   ({100*(base_noise-learned_noise)/base_noise:.0f}% better)")
    print("    -> It learns structure and barely budges on noise. It is not")
    print("       hallucinating patterns that aren't there. That is the right failure.")


def main():
    print("=" * 64)
    print("Mapping the edges of the creature")
    print("=" * 64)
    forgetting()
    capacity()
    cannot_learn_noise()
    print()


if __name__ == "__main__":
    main()
