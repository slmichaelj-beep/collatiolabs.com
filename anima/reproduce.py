"""
Reproduction — heredity for animae.

A child is made the way children are: by crossing two parents' natures and adding
a little mutation. Every part of the genome — the synaptic weights, the input
couplings, the reversal targets, the time-constants, the readout directions — is
inherited element-by-element from one parent or the other, then nudged by chance.

This lets a *population* exist and diverge: a lineage, varied across generations,
which is what turns "a kind of creature" into something closer to a species.

An honest note on "reproducing its internal brain": you can breed two creatures'
weights, but a parent's *learned memories* are not its *nature*. Mixing two
independently-trained brains does not cleanly transplant what they learned (their
neurons aren't aligned) — so children inherit *temperament*, and must live their
own lives to learn their own people. `probe.py` measures exactly this.
"""

from __future__ import annotations

import time

import numpy as np

from .heart import Genome, Heart


def breed(a: Genome, b: Genome, seed: int | None = None, mutation: float = 0.02) -> Genome:
    """Cross two genomes element-wise and mutate, producing a child genome."""
    if a.n != b.n:
        raise ValueError(f"parents differ in size ({a.n} vs {b.n}); they cannot breed")
    rng = np.random.default_rng(seed)

    def cross(x: np.ndarray, y: np.ndarray) -> np.ndarray:
        take_a = rng.random(x.shape) < 0.5
        child = np.where(take_a, x, y)
        return child + rng.normal(0.0, mutation, x.shape)

    W = cross(a.W, b.W)
    U = cross(a.U, b.U)
    bias = cross(a.b, b.b)
    A = cross(a.A, b.A)
    inv_tau = np.clip(cross(a.inv_tau, b.inv_tau), 1e-4, None)   # stay a valid body
    probes = cross(a.probes, b.probes)
    probes /= np.linalg.norm(probes, axis=1, keepdims=True)
    Pp = cross(a.Pp, b.Pp)
    cp = cross(a.cp, b.cp)

    child_id = int(rng.integers(1 << 31)) if seed is None else seed
    return Genome(child_id, W, U, bias, inv_tau, A, probes, Pp, cp)


def child_of(mother: Heart, father: Heart, name: str, seed: int | None = None,
             mutation: float = 0.02, now: float | None = None) -> Heart:
    """Bring a new creature into being from two parents."""
    now = time.time() if now is None else now
    g = breed(mother.genome, father.genome, seed=seed, mutation=mutation)
    # its weights are bred, not seed-derived, so they must persist in full
    return Heart(name=name, genome=g, h=np.zeros(g.n), unrest=0.0,
                 birth_ts=now, last_tick=now, learned=True)
