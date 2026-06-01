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
        Path(path).write_text(json.dumps({"rows": self.rows}))

    @classmethod
    def load(cls, path):
        p = Path(path)
        if not p.exists():
            return cls()
        return cls(json.loads(p.read_text()).get("rows", []))
