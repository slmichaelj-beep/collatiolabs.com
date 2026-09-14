"""
Memory — the lived experience an anima grows from.

Every sensed moment is recorded verbatim as the exact input the heart felt (its
perception plus the body-internal signals at that instant) together with how much
time had passed. This stream is the food: the slow-learning organ replays it to
become person-specific. Nothing here is interpreted into words — it is the raw
felt history, kept so the creature can learn what it could not learn in the
moment.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .util import save_json, load_json


class Memory:
    def __init__(self, rows=None):
        self.rows = rows or []      # each: {"clock": ts, "dt": minutes, "I": [floats]}

    def __len__(self):
        return len(self.rows)

    def record(self, input_vector, dt_min, clock_ts):
        self.rows.append({
            "clock": float(clock_ts),
            "dt": float(dt_min),
            "I": np.asarray(input_vector, dtype=float).tolist(),
        })

    # split the one life-stream into overlapping windows so consolidation has
    # several sequences to learn from, and a held-out tail to be judged on.
    def streams(self, window=24, holdout_frac=0.25):
        if len(self.rows) < 4:
            return [], []
        I = [np.array(r["I"]) for r in self.rows]
        dt = [r["dt"] for r in self.rows]
        chunks = []
        step = max(1, window // 2)
        for s in range(0, max(1, len(I) - 1), step):
            seg_I, seg_dt = I[s:s + window], dt[s:s + window]
            if len(seg_I) >= 4:
                chunks.append((seg_I, seg_dt))
        if not chunks:
            chunks = [(I, dt)]
        cut = max(1, int(len(chunks) * (1 - holdout_frac)))
        return chunks[:cut], chunks[cut:] or chunks[-1:]

    def save(self, path):
        save_json(path, {"rows": self.rows})

    @classmethod
    def load(cls, path):
        d = load_json(path)            # decrypts if needed; tolerates missing/corrupt
        return cls(d.get("rows", [])) if isinstance(d, dict) else cls()


def _chunk(I_seq, dt_seq, window, step):
    out = []
    for s in range(0, max(1, len(I_seq) - 1), step):
        seg_I, seg_dt = I_seq[s:s + window], dt_seq[s:s + window]
        if len(seg_I) >= 4:
            out.append((seg_I, seg_dt))
    return out


class Replay:
    """The long-term memory organ — the cure for catastrophic forgetting.

    A bounded reservoir of past episodes. New experience is folded in, but the
    buffer keeps a *uniform random sample of the creature's entire life* in fixed
    space (Vitter's Algorithm R). When it sleeps, it learns on a mix drawn from
    this whole reservoir, so the newest day is interleaved with a fair slice of
    everything that came before — and the earlier 'you' is never overwritten.

    This is the honest, bounded form of memory. It does not hoard every instant
    forever (no life fits in finite weights); it keeps a faithful cross-section
    and lets the redundant rest fade, the way a person remembers a representative
    past rather than every second of it.
    """

    def __init__(self, capacity=64, episodes=None, seen=0, seed=0):
        self.capacity = capacity
        self.episodes = episodes or []     # each: [I_list(list of lists), dt_list]
        self.seen = seen
        self._rng = np.random.default_rng(seed)

    def __len__(self):
        return len(self.episodes)

    def _add_episode(self, I_seq, dt_seq):
        ep = [[np.asarray(x, float).tolist() for x in I_seq], [float(d) for d in dt_seq]]
        self.seen += 1
        if len(self.episodes) < self.capacity:
            self.episodes.append(ep)
        else:                              # Algorithm R: keep a uniform sample
            j = int(self._rng.integers(self.seen))
            if j < self.capacity:
                self.episodes[j] = ep

    def absorb(self, I_seq, dt_seq, window=24, step=12):
        """Fold one lived stream into the reservoir as one or more episodes."""
        for seg_I, seg_dt in _chunk(list(I_seq), list(dt_seq), window, step):
            self._add_episode(seg_I, seg_dt)

    def _streams(self, eps):
        return [([np.array(x, float) for x in I], list(dt)) for I, dt in eps]

    def train_holdout(self, holdout_frac=0.25):
        eps = list(self.episodes)
        self._rng.shuffle(eps)
        cut = max(1, int(len(eps) * (1 - holdout_frac)))
        return self._streams(eps[:cut]), self._streams(eps[cut:] or eps[-1:])

    def save(self, path):
        save_json(path, {"capacity": self.capacity, "seen": self.seen, "episodes": self.episodes})

    @classmethod
    def load(cls, path, capacity=64):
        d = load_json(path)
        if not isinstance(d, dict):
            return cls(capacity=capacity)
        return cls(capacity=d.get("capacity", capacity),
                   episodes=d.get("episodes", []), seen=d.get("seen", 0))
