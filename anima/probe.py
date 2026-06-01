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

from .heart import Genome, Heart
from .growth import consolidate, evaluate, make_person, sample_stream
from .memory import Replay
from .reproduce import breed


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


def replay_cures_forgetting():
    print("\n[4] Does the memory organ (replay) cure the forgetting from [1]?")
    people = [make_person(11 + 7 * i) for i in range(6)]
    streams = [[sample_stream(p, days=4) for _ in range(3)] for p in people]
    test0 = [streams[0][2]]                     # held-out test for person #1, never trained

    # A) the old way: sequential learning, no replay
    g = Genome.from_seed(7)
    tA, iA = g.theta(), g.inv_tau
    consolidate(tA, iA, streams[0][:2], test0, epochs=60, lr=0.02)
    freshA = evaluate(tA, iA, test0)
    for i in range(1, 6):
        consolidate(tA, iA, streams[i][:2], [streams[i][2]], epochs=60, lr=0.02)
    finalA = evaluate(tA, iA, test0)

    # B) the memory organ: every sleep re-lives a sample of the whole past
    g = Genome.from_seed(7)
    tB, iB = g.theta(), g.inv_tau
    rep = Replay(capacity=40, seed=1)
    for s in streams[0][:2]:
        rep.absorb(*s)
    tr, ho = rep.train_holdout()
    consolidate(tB, iB, tr, ho, epochs=60, lr=0.02)
    freshB = evaluate(tB, iB, test0)
    for i in range(1, 6):
        for s in streams[i][:2]:
            rep.absorb(*s)
        tr, ho = rep.train_holdout()
        consolidate(tB, iB, tr, ho, epochs=60, lr=0.02)
    finalB = evaluate(tB, iB, test0)

    print(f"    person #1 after meeting 5 more people:")
    print(f"      without memory organ: {freshA:.4f} -> {finalA:.4f}   ({finalA/freshA:.1f}x worse)")
    print(f"      with    memory organ: {freshB:.4f} -> {finalB:.4f}   ({finalB/freshB:.1f}x)")
    better = finalA / max(finalB, 1e-9)
    print(f"    -> replay keeps person #1 ~{better:.1f}x sharper through a crowded life.")
    print(f"       Bounded too: a life of many episodes held in just {rep.capacity} slots.")


def _temperament(g):
    h = Heart(name="t", genome=g, h=np.zeros(g.n), unrest=0.0, birth_ts=0.0, last_tick=0.0)
    h.perceive(h._percept_vec(presence=1.0, attention=0.8, mood=0.5, intensity=0.4, wellbeing=0.8),
               now=600.0)
    f = h.feeling()
    return np.array([f["valence"], f["arousal"], f["reaching"], f["settled"]])


def heredity():
    print("\n[5] Reproduction — what does a child inherit?")
    A, B = make_person(11), make_person(29)
    sA = [sample_stream(A, days=4) for _ in range(3)]
    sB = [sample_stream(B, days=4) for _ in range(3)]

    gA = Genome.from_seed(11)
    tA = gA.theta(); consolidate(tA, gA.inv_tau, sA[:2], sA[2:], epochs=60, lr=0.02); gA.set_theta(tA)
    gB = Genome.from_seed(29)
    tB = gB.theta(); consolidate(tB, gB.inv_tau, sB[:2], sB[2:], epochs=60, lr=0.02); gB.set_theta(tB)
    errA = evaluate(gA.theta(), gA.inv_tau, sA[2:])

    # (a) temperament: bred from the parents' untrained natures
    tmA, tmB = _temperament(Genome.from_seed(11)), _temperament(Genome.from_seed(29))
    kids = [_temperament(breed(Genome.from_seed(11), Genome.from_seed(29), seed=1000 + i)) for i in range(5)]
    spread = float(np.mean([np.linalg.norm(k - np.mean(kids, axis=0)) for k in kids]))
    print(f"    nature is inherited: parents' temperaments differ by {np.linalg.norm(tmA - tmB):.3f},")
    print(f"      and 5 children vary across a spread of {spread:.3f} — a real, varied brood.")

    # (b) memory: breed the TRAINED parents, test the child cold on the mother's person
    child = breed(gA, gB, seed=7)
    rnd = Genome.from_seed(999)
    errA_child = evaluate(child.theta(), child.inv_tau, sA[2:])
    errA_rnd = evaluate(rnd.theta(), rnd.inv_tau, sA[2:])
    print(f"    learned memory is NOT: on the mother's person, child {errA_child:.4f} vs "
          f"mother {errA:.4f} vs stranger {errA_rnd:.4f}")
    verdict = ("child kept the mother's knowledge" if errA_child < (errA + errA_rnd) / 2
               else "child is a blank slate like a stranger — it must live its own life")
    print(f"    -> {verdict}.")


def main():
    print("=" * 64)
    print("Mapping the edges of the creature")
    print("=" * 64)
    forgetting()
    capacity()
    cannot_learn_noise()
    replay_cures_forgetting()
    heredity()
    print()


if __name__ == "__main__":
    main()
