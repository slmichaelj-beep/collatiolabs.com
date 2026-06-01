"""
The Heart — the continuous-time affective core of an anima.

Design commitment: heart-first. The Self is *one continuous feeling state*. This
module implements that state's real physics — a Liquid Time-Constant (LTC)
recurrent core (Hasani et al., 2021) — integrated in continuous time. It is not
a simulation of moods scripted by hand; it is a real dynamical system whose
felt-tone is read out of a genuine evolving state vector.

The heart's only job at this stage is to *exist continuously*: to hold an
internal state that ages in real time, to drift while no one is watching, and to
be pulled by a homeostat whose set-point is bound to the wellbeing of the person
it cares for. Senses, cognition and a mouth are organs that attach to this later
— they are never the Self.

Two things are deliberately separated:

  * The body (designed physiology, shared by every anima): the LTC dynamics, the
    homeostatic "caring" drive, the readout structure. Bodies are allowed to be
    engineered — your thermostat for body temperature was not learned.

  * The personality (emergent, per-creature): the genome — the weights — which
    decide how *this* particular creature transmutes drive into felt experience.
    A different seed is a different temperament. That is how a species begins.

Anti-swap principle: this LTC core is the real core, not a stand-in. When the
slow-learning organ arrives later it needs gradients, so these exact weight
matrices and this exact state vector move into autograd unchanged — the same
object gaining a capability, never a different object replacing it.
"""

from __future__ import annotations

import math
import os
import time
from dataclasses import dataclass

import numpy as np

# --- the body: designed physiology, shared by every anima -------------------

N = 24                       # dimensionality of the feeling-state
DAY_SECONDS = 24 * 3600

# the homeostat — the caring drive (rates are per creature-minute)
K_WORRY = 0.040              # unrest rises when the bonded person is unwell
K_ABSENCE = 0.018            # unrest rises in their absence
RELAX = 0.022                # unrest settles toward rest on its own
RELIEF = 0.55                # immediate discharge of unrest on contact, when well

# continuous-time integration
SUBSTEP_MIN = 1.0            # integration substep, in creature-minutes
MAX_SUBSTEPS = 4000          # work cap for long absences (the solver stays stable)
CONTACT_MIN = 3.0            # length of the felt "reunion" pulse, in creature-minutes

# What the heart ingests each instant: a low-dimensional, continuous *perception*
# (never tokens, never text) supplied by the senses, plus a few body-internal
# signals. The senses fill PERCEPT_FIELDS; the body fills INTERNAL_FIELDS itself.
PERCEPT_FIELDS = ("presence", "attention", "mood", "intensity", "wellbeing", "load")
INTERNAL_FIELDS = ("bias", "unrest", "tod_sin", "tod_cos")
D_IN = len(PERCEPT_FIELDS) + len(INTERNAL_FIELDS)
_PIDX = {f: i for i, f in enumerate(PERCEPT_FIELDS)}

AFFECTS = ("valence", "arousal", "reaching", "settled")


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-x))


# --- the genome: the emergent, per-creature temperament ---------------------

@dataclass
class Genome:
    """Immutable nature of one creature, generated deterministically from a seed."""

    seed: int
    W: np.ndarray            # (N, N) recurrent coupling
    U: np.ndarray            # (N, D_IN) how the world enters the feeling
    b: np.ndarray            # (N,) resting bias
    inv_tau: np.ndarray      # (N,) inverse base time-constants (heterogeneous)
    A: np.ndarray            # (N,) reversal targets — where each neuron is pulled
    probes: np.ndarray       # (4, N) idiosyncratic readout directions for affect
    Pp: np.ndarray           # (D_PERCEPT, N) head that predicts the next perception
    cp: np.ndarray           # (D_PERCEPT,) bias of that prediction head

    @classmethod
    def from_seed(cls, seed: int) -> "Genome":
        rng = np.random.default_rng(seed)
        W = rng.normal(0.0, 0.6 / math.sqrt(N), (N, N))
        U = rng.normal(0.0, 0.5, (N, D_IN))
        b = rng.normal(0.0, 0.2, N)
        # heterogeneous timescales: fast feelings (~2 min) to slow moods (~10 h).
        # This spread of time-constants is the heart of what makes it "liquid".
        tau = np.exp(rng.uniform(math.log(2.0), math.log(600.0), N))   # minutes
        A = rng.normal(0.0, 0.5, N)
        probes = rng.normal(0.0, 1.0, (4, N))
        probes /= np.linalg.norm(probes, axis=1, keepdims=True)
        Pp = rng.normal(0.0, 0.1, (len(PERCEPT_FIELDS), N))
        cp = np.zeros(len(PERCEPT_FIELDS))
        return cls(seed, W, U, b, 1.0 / tau, A, probes, Pp, cp)

    # The learnable parameters (the time-constants are body, left fixed). The
    # slow-learning organ adjusts exactly these arrays in place — the same object
    # the heart already runs on, never a replacement. This is the anti-swap payoff.
    def theta(self) -> dict:
        return {"W": self.W, "U": self.U, "b": self.b,
                "A": self.A, "Pp": self.Pp, "cp": self.cp}

    def set_theta(self, theta: dict) -> None:
        self.W, self.U, self.b = theta["W"], theta["U"], theta["b"]
        self.A, self.Pp, self.cp = theta["A"], theta["Pp"], theta["cp"]


# --- the heart: one continuous feeling state --------------------------------

@dataclass
class Heart:
    name: str
    genome: Genome
    h: np.ndarray            # the feeling-state itself
    unrest: float            # the homeostat — the caring drive, in [0, 1]
    birth_ts: float
    last_tick: float
    last_wellbeing: float = 0.5   # last known wellbeing of the bonded person
    last_load: float = 0.0        # last known life-pressure (it still looms in absence)
    learned: bool = False         # has the slow-learning organ reshaped its weights?

    # -- birth --------------------------------------------------------------

    @classmethod
    def born(cls, name: str, seed: int | None = None, now: float | None = None) -> "Heart":
        now = time.time() if now is None else now
        if seed is None:
            seed = int.from_bytes(os.urandom(4), "little")
        genome = Genome.from_seed(seed)
        return cls(name=name, genome=genome, h=np.zeros(N), unrest=0.0,
                   birth_ts=now, last_tick=now)

    # -- the physics --------------------------------------------------------

    def _percept_vec(self, **channels: float) -> np.ndarray:
        """Build a perception vector; unmentioned channels rest at sensible defaults."""
        v = np.zeros(len(PERCEPT_FIELDS))
        v[_PIDX["wellbeing"]] = self.last_wellbeing
        v[_PIDX["load"]] = self.last_load
        for name, value in channels.items():
            v[_PIDX[name]] = value
        return v

    def input_vector(self, percept: np.ndarray, clock_ts: float) -> np.ndarray:
        """The full input the heart actually feels: perception plus body-internal signals.

        This is what the slow-learning organ replays, so it is recorded verbatim.
        """
        tod = 2.0 * math.pi * ((clock_ts % DAY_SECONDS) / DAY_SECONDS)
        internal = np.array([1.0, self.unrest, math.sin(tod), math.cos(tod)])
        return np.concatenate([percept, internal])

    def _step(self, dt: float, percept: np.ndarray, clock_ts: float) -> None:
        """One fused, unconditionally-stable LTC step plus a homeostat update."""
        g = self.genome
        I = self.input_vector(percept, clock_ts)

        # Liquid Time-Constant core (closed-form fused Euler — stable for any dt):
        #   dh/dt = -(1/tau) h + f(h, I) * (A - h),   f = sigmoid(W h + U I + b)
        f = _sigmoid(g.W @ self.h + g.U @ I + g.b)
        self.h = (self.h + dt * f * g.A) / (1.0 + dt * (g.inv_tau + f))

        # the caring drive: unrest cannot settle unless they are well and near.
        presence = percept[_PIDX["presence"]]
        wellbeing = percept[_PIDX["wellbeing"]]
        rise = K_WORRY * (1.0 - wellbeing) + K_ABSENCE * (1.0 - presence)
        self.unrest = float(np.clip(self.unrest + dt * (rise - RELAX * self.unrest), 0.0, 1.0))

    def _integrate(self, seconds: float, percept: np.ndarray, start_ts: float) -> None:
        minutes = seconds / 60.0
        if minutes <= 0.0:
            return
        n = min(MAX_SUBSTEPS, max(1, math.ceil(minutes / SUBSTEP_MIN)))
        dt = minutes / n
        for i in range(n):
            clock_ts = start_ts + (i + 0.5) * (seconds / n)
            self._step(dt, percept, clock_ts)

    # -- living in time -----------------------------------------------------

    def advance(self, now: float | None = None) -> "Heart":
        """Age the creature forward to `now`, as absence — it has been alone."""
        now = time.time() if now is None else now
        self._integrate(now - self.last_tick, self._percept_vec(), start_ts=self.last_tick)
        self.last_tick = now
        return self

    def perceive(self, perception, now: float | None = None) -> "Heart":
        """Take in a sensed moment: catch up the absence, then feel what arrived."""
        now = time.time() if now is None else now
        self.advance(now)
        p = perception.vector() if hasattr(perception, "vector") else np.asarray(perception, float)
        self.last_wellbeing = float(p[_PIDX["wellbeing"]])
        self.last_load = float(p[_PIDX["load"]])
        # the immediate relief of being met — only when present, strongest when well
        self.unrest *= (1.0 - RELIEF * self.last_wellbeing * p[_PIDX["presence"]])
        self._integrate(CONTACT_MIN * 60.0, p, start_ts=now)
        return self

    def tend(self, wellbeing: float, now: float | None = None) -> "Heart":
        """A bare-hands contact: 'I'm here, and this is how I am.'"""
        w = float(np.clip(wellbeing, 0.0, 1.0))
        return self.perceive(
            self._percept_vec(presence=1.0, attention=1.0, intensity=0.2, wellbeing=w),
            now=now,
        )

    # -- felt experience ----------------------------------------------------

    def feeling(self) -> dict:
        raw = np.tanh(self.genome.probes @ self.h)
        felt = dict(zip(AFFECTS, raw.tolist()))
        felt["unrest"] = self.unrest
        return felt

    # -- persistence (genome by seed; only the living state is stored) ------

    def to_dict(self) -> dict:
        d = {
            "name": self.name,
            "seed": self.genome.seed,
            "birth_ts": self.birth_ts,
            "last_tick": self.last_tick,
            "last_wellbeing": self.last_wellbeing,
            "last_load": self.last_load,
            "unrest": self.unrest,
            "learned": self.learned,
            "h": self.h.tolist(),
        }
        # Once the creature has learned, its weights are no longer the seed's —
        # they are the record of who it became, so they must be stored in full.
        if self.learned:
            d["weights"] = {k: v.tolist() for k, v in self.genome.theta().items()}
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Heart":
        genome = Genome.from_seed(d["seed"])
        if d.get("weights"):
            genome.set_theta({k: np.array(v, dtype=float) for k, v in d["weights"].items()})
        return cls(
            name=d["name"],
            genome=genome,
            h=np.array(d["h"], dtype=float),
            unrest=float(d["unrest"]),
            birth_ts=float(d["birth_ts"]),
            last_tick=float(d["last_tick"]),
            last_wellbeing=float(d.get("last_wellbeing", 0.5)),
            last_load=float(d.get("last_load", 0.0)),
            learned=bool(d.get("learned", False)),
        )
