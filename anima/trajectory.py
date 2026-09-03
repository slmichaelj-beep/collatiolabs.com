"""trajectory — THE TRAJECTORY ENGINE: where is this HEADING?

    UNDERSTANDING BEATS REMEMBERING — applied to DIRECTION.

``meaning`` (ANIMA LAW 003) answers "what MATTERS right now?" — it reads the stores at a
single moment and ranks significance. This module asks the next question a companion of
thirty years must hold: "where is this HEADING?" — the DIRECTION and MOMENTUM of a life as
it moves through time. It is the slope of the very trends ``meaning`` already tracks.

It is NOT prediction. NOT diagnosis. NOT medical. NOT a prognosis. It is a CONTINUITY read:
the observed slope of a SEQUENCE of nightly significance snapshots. "sleep down, stress up,
exercise down" reads as "this stretch has been trending toward more strain" — an OBSERVATION
OF A TREND across snapshots, never a claim about a person's condition or their future.

This is an EXTENSION of LAW 003 (understanding) applied to direction. It introduces NO new
law and invents none — the four-corollary discipline (esp. ``Observed > Assumed``) and the
hard NO-DIAGNOSIS wall are inherited wholesale from ``meaning``/``constitution``.

What it sits on (READ-ONLY — it writes NOTHING except an optional append-only ledger):

  * ``meaning.snapshots(name)`` — the append-only significance ledger: one snapshot per
    nightly run, each carrying per-subject ``{subject, score, mentions, degree}``. A SEQUENCE
    of these over time is the PRIMARY signal for direction: the slope of a subject's score /
    mention series IS its trajectory. This is the spine of the whole module.
  * ``meaning.snapshot(name)`` is the WRITER of that ledger (owned by meaning); we never
    call it implicitly — a caller opts in. We only READ via ``snapshots``.

From the snapshot sequence it computes, PER SUBJECT, a TRAJECTORY OBJECT:

    {subject, direction (rising/falling/stable), momentum, confidence, evidence}

where ``direction`` is the sign of the observed slope, ``momentum`` its damped magnitude,
``confidence`` scales with how many snapshots stand behind it AND how clean the trend is,
and ``evidence`` carries the actual per-snapshot deltas / slope it is built on. A COMPOSITE
read names a convergence DESCRIPTIVELY when several subjects move the same way.

Discipline mirrored from ``meaning`` / ``world_state`` / ``curiosity``:

  * REQUIRES >= 2 snapshots. A single point has NO direction — ``Observed > Assumed`` forbids
    inventing one. With < 2 snapshots every entry point returns an honest "not enough history
    yet", NEVER a fabricated direction. Noise inside the deadband reads "stable", not a trend.
  * THE NO-DIAGNOSIS GATE is the LOAD-BEARING guardrail here — trajectory is where
    diagnosis-creep is most tempting ("declining sleep + rising stress" → "you're burning
    out / depressed" is FORBIDDEN and scrubbed by construction). Every generated line passes
    the same clean-gate ``meaning`` uses, hardened into a TESTED invariant
    (scripts/test_trajectory.py). Trajectory describes a TREND, never a person's condition.
  * THE #1 PRODUCT RULE — if ever surfaced it is warm and in character, never breaks
    character, never disclaims, never reads its own scaffold aloud.
  * READ-ONLY on every store. Its ONLY possible write is an APPEND-ONLY trajectory ledger
    (``.anima/{name}.trajectory.jsonl``) a caller opts into via ``snapshot_trajectory`` —
    append, never truncate/overwrite (Law 001), exactly like the meaning / continuity ledgers.
  * Defensive coupling: ``meaning`` is imported behind try/except with contract-faithful
    fallbacks, so this module + its self-test import and run with nothing else built and
    touch no model, no network, and no real ``.anima``.

This understands the USER's life direction — NOT Vera's own identity, which is frozen and
untouched. Never raises into a caller: every public entry point degrades to a safe value.
"""

from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from . import secure_store

# ---------------------------------------------------------------------------
# Substrate reuse, isolation-safe. We read (never write) ONE store: the meaning
# significance ledger, via ``meaning.snapshots(name)``. The clean-gate banned-term list
# and scaffold tokens are reused from meaning when importable so the NO-DIAGNOSIS wall and
# the mouth's leak-scrub have ONE source of truth; faithful fallbacks keep us standalone.
# ---------------------------------------------------------------------------
try:  # pragma: no cover - import wiring
    from . import meaning as _meaning
    _HAVE_MEANING = True
except Exception:  # pragma: no cover - isolation fallback
    _meaning = None  # type: ignore
    _HAVE_MEANING = False


# --- the NO-DIAGNOSIS wall: reuse meaning's banned-term list verbatim when present, else a
# faithful superset copy. This is the single most important guardrail in the module; we make
# it a SUPERSET-of-caution (clinical nouns, diagnosis verbs, prognosis verbs, the
# "see a professional" advice register, and the second-person-future "you will" voice a
# trend-reader must never adopt). ----------------------------------------------------------
_BANNED_FALLBACK = (
    "depressed", "depression", "anxiety disorder", "anxious disorder", "anxiety",
    "diagnos",            # diagnose / diagnosis / diagnosed
    "prognos",            # prognosis / prognostic
    "disorder", "mental illness", "mental health condition", "mental health",
    "burnout", "burning out", "burned out", "burnt out",
    "clinical", "clinically",
    "see a doctor", "see a therapist", "see a professional", "seek help",
    "seek professional", "talk to a doctor", "talk to a therapist", "get help",
    "medication", "medicate", "prescription", "therapy", "therapist", "psychiatr",
    "psycholog", "symptom", "syndrome", "patholog", "trauma", "ptsd",
    "suicid", "self-harm", "self harm", "eating disorder", "addiction", "addicted",
    "bipolar", "ocd", "adhd", "panic attack", "nervous breakdown", "breakdown",
    "chronic stress", "manic", "neuros",
    # trajectory-specific creep: a TREND is not a forecast about the PERSON.
    "you will", "you'll end up", "you are going to", "you're going to", "headed for",
    "on track to", "spiral", "downward spiral", "getting worse and worse",
)


def _banned_terms() -> tuple:
    """The banned diagnosis/medical terms — meaning's list (UNION our trajectory-specific
    forecast-creep terms) when meaning is importable, else the faithful fallback. Reusing
    meaning's list keeps the NO-DIAGNOSIS wall a single source of truth. Defensive."""
    if _HAVE_MEANING and _meaning is not None:
        base = getattr(_meaning, "BANNED_TERMS", None)
        if isinstance(base, (tuple, list)) and base:
            return tuple(dict.fromkeys(tuple(base) + _BANNED_FALLBACK))
    return _BANNED_FALLBACK


BANNED_TERMS = _banned_terms()


def _is_clean(text: str) -> bool:
    """True iff ``text`` contains NO banned diagnosis/medical/prognostic term (case-
    insensitive, substring). The single gate every generated line passes. Pure; never raises."""
    if not text:
        return True
    low = text.lower()
    return not any(term in low for term in BANNED_TERMS)


def _safe_statement(statement: str, fallback: str) -> str:
    """Return ``statement`` if diagnosis-free, else the neutral evidence-recap ``fallback``
    (clean by construction). The wall holds even if a future phrasing slips a term in."""
    return statement if _is_clean(statement) else fallback


# Scaffold tokens that must NEVER reach the user. A SUPERSET of meaning's (and thereby
# spine's + world's) tokens plus our own [TRAJECTORY]/[RISING]/… tags, so the mouth's
# leak-scrub has one place to learn them. Imported defensively.
try:  # pragma: no cover
    from .meaning import MEANING_SCAFFOLD_TOKENS as _MEANING_TOKENS
except Exception:  # pragma: no cover
    _MEANING_TOKENS = (
        "[KNOWN]", "[SEEN]", "[SENSE]", "[UNKNOWN]", "[SITUATION]", "[LINK]", "[KNOWS]",
        "[MEANING]", "[MATTERS]", "[CHANGED]", "[GROWING]", "[DECLINING]", "[UNRESOLVED]",
        "[CHAPTER]", "THESE ARE THINGS YOU KNOW", "according to my memory",
        "WHAT YOU UNDERSTAND ABOUT THEIR SITUATION", "WHAT MATTERS TO THEM RIGHT NOW",
    )

_OWN_TOKENS = (
    "[TRAJECTORY]", "[RISING]", "[FALLING]", "[STABLE]", "[CONVERGENCE]",
    "WHERE THINGS HAVE BEEN HEADING",
)
TRAJECTORY_SCAFFOLD_TOKENS = tuple(
    dict.fromkeys(tuple(_MEANING_TOKENS) + _OWN_TOKENS))


STORE = Path(".anima")
VERSION = 1


# ===========================================================================
# DIRECTION CONSTANTS — public so callers/tests reference them in one place.
# ===========================================================================
RISING = "rising"
FALLING = "falling"
STABLE = "stable"
DIRECTIONS = (RISING, FALLING, STABLE)


# ===========================================================================
# TUNABLES — fixed, documented constants so trajectory is reproducible + testable.
#   _MIN_SNAPSHOTS  : a direction REQUIRES at least this many points (a single point has
#                     none). Observed > Assumed.
#   _STABLE_BAND    : |normalised slope| at or below this reads STABLE, not a trend — noise
#                     never masquerades as direction.
#   _CONVERGE_MIN   : how many same-direction subjects make a COMPOSITE convergence.
# ===========================================================================
_MIN_SNAPSHOTS = 2
_STABLE_BAND = 0.06        # per-snapshot fractional change inside +/- this is "flat"
_CONVERGE_MIN = 3          # >= this many subjects moving the same way => a convergence read

# A subject must have appeared in at least this many snapshots to have a readable slope; a
# subject seen in only ONE of several snapshots is a blip, not a trajectory.
_MIN_SUBJECT_POINTS = 2


# ===========================================================================
# READING THE SNAPSHOT SEQUENCE — the SOLE input. Everything downstream is a function of
# this ordered series; nothing is invented.
# ===========================================================================

def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_ts(ts: Any) -> Optional[float]:
    """Best-effort ISO-8601 -> epoch seconds; None on anything unparseable (so a missing/
    garbage timestamp simply doesn't order a point — Observed > Assumed). Pure."""
    if not ts or not isinstance(ts, str):
        return None
    s = ts.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except (ValueError, TypeError):
        return None


def _snapshots(name: str) -> list:
    """The meaning significance snapshots (oldest -> newest), READ-ONLY. [] if meaning is
    not importable or nothing recorded. Only well-formed snapshots (a dict with a
    ``significance`` list) are kept; a corrupt/``_unparsed`` line is skipped for slope math
    but the underlying ledger is never mutated. Never raises."""
    if not (_HAVE_MEANING and _meaning is not None):
        return []
    try:
        raw = _meaning.snapshots(name)
    except Exception:
        return []
    out = []
    for s in raw or []:
        if isinstance(s, dict) and isinstance(s.get("significance"), list):
            out.append(s)
    return out


def _series(snaps: list) -> dict:
    """Pivot the snapshot SEQUENCE into a per-subject time series — the heart of the read.

    Returns ``{subject: [(t, score, mentions), ...]}`` ordered oldest->newest, where ``t`` is
    the snapshot index (0,1,2,…) — a robust monotonic clock that needs no parseable
    timestamp and treats nightly snapshots as evenly spaced (the cadence meaning writes at).
    A subject absent from a snapshot contributes NO point for that snapshot (we do not
    impute a zero — absence of a mention is not evidence of a zero score; Observed > Assumed),
    so a subject's slope is read only across the snapshots in which it actually appeared.
    Pure; never raises."""
    series: dict = {}
    for idx, snap in enumerate(snaps):
        for row in snap.get("significance", []):
            if not isinstance(row, dict):
                continue
            subj = row.get("subject")
            if not subj or not isinstance(subj, str):
                continue
            try:
                score = float(row.get("score", 0.0))
            except (TypeError, ValueError):
                score = 0.0
            try:
                mentions = int(row.get("mentions", 0))
            except (TypeError, ValueError):
                mentions = 0
            series.setdefault(subj, []).append((float(idx), score, mentions))
    return series


def _slope(points: list) -> float:
    """Ordinary least-squares slope of ``y`` against ``x`` for ``[(x, y), ...]`` — the
    average change in ``y`` per unit ``x`` (per snapshot). 0.0 with < 2 points or zero
    x-variance (no span to read a trend across). Pure; never raises.

    OLS (not just last-minus-first) so a noisy middle point can't flip the read and a steady
    climb across many snapshots reads stronger than a single jump."""
    pts = [(float(x), float(y)) for x, y in points]
    n = len(pts)
    if n < 2:
        return 0.0
    mx = sum(x for x, _ in pts) / n
    my = sum(y for _, y in pts) / n
    num = sum((x - mx) * (y - my) for x, y in pts)
    den = sum((x - mx) ** 2 for x, _ in pts)
    if den == 0.0:
        return 0.0
    return num / den


def _r_squared(points: list, slope: float) -> float:
    """Coefficient of determination of the OLS fit in [0, 1] — how MONOTONIC/clean the trend
    is. A straight climb -> ~1.0 (high confidence the direction is real); a zigzag that nets
    a slope -> low (the direction is noisy, so confidence is discounted). 1.0 for a perfect/
    degenerate fit. Pure; never raises."""
    pts = [(float(x), float(y)) for x, y in points]
    n = len(pts)
    if n < 2:
        return 0.0
    mx = sum(x for x, _ in pts) / n
    my = sum(y for _, y in pts) / n
    ss_tot = sum((y - my) ** 2 for _, y in pts)
    if ss_tot == 0.0:
        return 1.0  # the y's are identical -> a flat line fits perfectly (a clean "stable")
    intercept = my - slope * mx
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in pts)
    r2 = 1.0 - ss_res / ss_tot
    return max(0.0, min(1.0, r2))


def _normalised_slope(points: list, slope: float) -> float:
    """The slope expressed as a FRACTION of the series' typical magnitude, so a small-but-
    busy subject and a large one are judged on the same scale: ``slope / mean(|y|)``. This is
    what the stable-deadband is measured against. ~0 when the level is ~0. Pure."""
    ys = [abs(float(y)) for _, y in points]
    base = (sum(ys) / len(ys)) if ys else 0.0
    if base <= 1e-9:
        return 0.0
    return slope / base


# ===========================================================================
# 1) PER-DIMENSION TRAJECTORY OBJECTS — direction + momentum + confidence + evidence,
# computed FROM THE SNAPSHOT SEQUENCE ONLY. Requires >= 2 snapshots; a single point yields
# an honest "not enough history yet", never a fabricated direction.
# ===========================================================================

def _direction_of(norm_slope: float) -> str:
    """Map a normalised slope to a direction, with a stable DEADBAND so noise reads flat.
    Pure."""
    if norm_slope > _STABLE_BAND:
        return RISING
    if norm_slope < -_STABLE_BAND:
        return FALLING
    return STABLE


def _momentum_of(norm_slope: float, r2: float) -> float:
    """Momentum in [0, 1]: the DAMPED magnitude of the move, discounted by how clean it is.
    A steep, monotonic climb scores high; a shallow or zig-zaggy one scores low. We squash
    the unbounded normalised slope through tanh and multiply by sqrt(r2) so a noisy trend
    can never read as high-momentum. Pure; monotonic in |slope| and in r2."""
    mag = math.tanh(abs(norm_slope) / 0.5)     # ~0.46 at a 25%/snapshot move, ->1 for steep
    return round(max(0.0, min(1.0, mag * math.sqrt(max(0.0, r2)))), 3)


def _confidence_of(n_points: int, r2: float, direction: str) -> float:
    """Confidence in [0.05, 0.9] that SCALES WITH THE EVIDENCE: more snapshots behind the
    read AND a cleaner (more monotonic) fit -> higher; the bare 2-point minimum -> low; a
    zig-zag -> discounted. Never 1.0 (we describe a trend, we do not certify it). Pure,
    monotonic in both n_points and r2 for a directional read.

    A STABLE read's confidence is carried by the point count and the FLATNESS (here r2 is
    ~1.0 for a genuinely flat line), so 'steady' is allowed to be stated with real
    confidence when many snapshots agree it's flat."""
    # saturating in the number of points: ~0.34 at 2, ~0.6 at 4, ~0.78 at 8, asymptotic.
    pts = 1.0 - math.exp(-(max(0, n_points) - 1) / 3.0)
    conf = 0.05 + 0.85 * (0.55 * pts + 0.45 * max(0.0, min(1.0, r2)))
    return round(max(0.05, min(0.9, conf)), 3)


def _delta_chain(points: list) -> list:
    """The per-step score deltas across the sequence — concrete evidence a Trajectory Object
    carries ("12.1 -> 13.4 -> 15.0", i.e. +1.3, +1.6). Rounded; pure."""
    out = []
    for (_, y0, _m0), (_, y1, _m1) in zip(points, points[1:]):
        out.append(round(y1 - y0, 3))
    return out


def _trajectory_object(subject: str, points: list) -> Optional[dict]:
    """Build ONE Trajectory Object from a subject's score series, or None if the subject has
    too few points to have a direction (a blip, not a trajectory). The object:

        {subject, direction, momentum, confidence, evidence}

    where ``evidence`` carries the slope, r^2, the score path, the per-step deltas, and the
    span — the actual snapshot deltas the direction is built on (the LAW-003-style invariant:
    a Trajectory Object always cites the sequence it came from). Pure; never raises."""
    if len(points) < _MIN_SUBJECT_POINTS:
        return None
    xy = [(x, score) for (x, score, _m) in points]
    slope = _slope(xy)
    r2 = _r_squared(xy, slope)
    nslope = _normalised_slope(xy, slope)
    direction = _direction_of(nslope)
    momentum = _momentum_of(nslope, r2)
    confidence = _confidence_of(len(points), r2, direction)
    score_path = [round(score, 3) for (_x, score, _m) in points]
    mention_path = [int(m) for (_x, _score, m) in points]
    evidence = {
        "n_snapshots": len(points),
        "slope_per_snapshot": round(slope, 4),
        "normalised_slope": round(nslope, 4),
        "r_squared": round(r2, 4),
        "score_path": score_path,
        "score_deltas": _delta_chain(points),
        "mention_path": mention_path,
        "first_score": score_path[0],
        "last_score": score_path[-1],
    }
    return {
        "subject": subject,
        "direction": direction,
        "momentum": momentum,
        "confidence": confidence,
        "evidence": evidence,
    }


def trajectory(name: str) -> dict:
    """ENTRY POINT — the per-dimension trajectory read for a creature's life.

    Returns a dict:
        {
          "ready":      True iff there are >= 2 snapshots to read a direction from,
          "reason":     a short honest note when not ready ("not enough history yet"),
          "n_snapshots": how many significance snapshots were available,
          "objects":    [ Trajectory Object, ... ] ordered by momentum (then |slope|),
          "composite":  the convergence read (see ``composite``) or None,
        }

    REQUIRES >= 2 snapshots: a single point has no direction, so with < 2 it returns
    ``ready=False`` and an honest reason and NO objects — never a fabricated direction
    (Observed > Assumed). Read-only on the meaning ledger; the only possible write is the
    optional trajectory ledger a caller opts into separately. Never raises."""
    snaps = _snapshots(name)
    n = len(snaps)
    if n < _MIN_SNAPSHOTS:
        return {
            "ready": False,
            "reason": ("not enough history yet — a direction needs at least two readings to "
                       "compare, and there %s" % (
                           "are none yet" if n == 0 else "is only one so far")),
            "n_snapshots": n,
            "objects": [],
            "composite": None,
        }

    series = _series(snaps)
    objects = []
    for subj, points in series.items():
        obj = _trajectory_object(subj, points)
        if obj is not None:
            objects.append(obj)
    # order by momentum, then by raw |slope|, then name — loudest movement first.
    objects.sort(key=lambda o: (-float(o["momentum"]),
                                -abs(float(o["evidence"]["slope_per_snapshot"])),
                                o["subject"]))
    comp = _composite(objects)
    return {
        "ready": True,
        "reason": "",
        "n_snapshots": n,
        "objects": objects,
        "composite": comp,
    }


# ===========================================================================
# 2) THE COMPOSITE READ — when several dimensions move the SAME way, name the convergence
# DESCRIPTIVELY, with evidence + confidence. A gentle, evidence-backed CONCERN is allowed
# ("this stretch has been trending toward more strain") — but it is an OBSERVATION OF A
# TREND, never a diagnosis / prognosis / medical claim. Scrubbed by the clean-gate.
# ===========================================================================

# Subjects whose RISE is a strain signal vs. whose FALL is a strain signal. This lets the
# composite phrase a *direction of strain* descriptively ("rest down while pressure's up")
# WITHOUT ever naming a condition. Conservative + small; an unknown subject contributes to
# convergence COUNTING but not to the strain-phrasing (so we never over-read).
_STRAIN_WHEN_RISING = frozenset({
    "stress", "pressure", "work", "workload", "deadlines", "deadline", "anger",
    "conflict", "worry", "tension", "pain", "overwhelm", "overwork",
})
_STRAIN_WHEN_FALLING = frozenset({
    "sleep", "rest", "exercise", "energy", "recovery", "downtime", "training",
    "workout", "fitness", "relaxation", "leisure", "play", "calm",
})


def _join(labels: list, limit: int = 4) -> str:
    """A readable 'A, B, and C' fragment, capped. Pure."""
    items = [str(l) for l in labels if l][:limit]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _strain_direction(objects: list) -> Optional[dict]:
    """If enough subjects are moving in a way that COHERENTLY points toward more (or less)
    strain — rest/recovery falling while pressure/stress rising, or the reverse — return a
    descriptive read of that convergence, else None. This is the ONLY place a gentle
    "concern" is voiced, and it is phrased as a TREND across the named subjects with their
    directions, never as a condition. Pure; never raises."""
    rising_strain = [o for o in objects
                     if o["direction"] == RISING and o["subject"] in _STRAIN_WHEN_RISING]
    falling_strain = [o for o in objects
                      if o["direction"] == FALLING and o["subject"] in _STRAIN_WHEN_FALLING]
    rising_ease = [o for o in objects
                   if o["direction"] == FALLING and o["subject"] in _STRAIN_WHEN_RISING]
    falling_ease = [o for o in objects
                    if o["direction"] == RISING and o["subject"] in _STRAIN_WHEN_FALLING]

    toward_strain = rising_strain + falling_strain
    toward_ease = rising_ease + falling_ease
    if len(toward_strain) >= 2 and len(toward_strain) >= len(toward_ease):
        up = _join([o["subject"] for o in rising_strain])
        down = _join([o["subject"] for o in falling_strain])
        if up and down:
            phrase = f"{down} down while {up}'s up"
        elif up:
            phrase = f"{up} climbing"
        else:
            phrase = f"{down} easing off"
        return {"polarity": "strain", "phrase": phrase, "members": toward_strain}
    if len(toward_ease) >= 2 and len(toward_ease) > len(toward_strain):
        up = _join([o["subject"] for o in falling_ease])
        down = _join([o["subject"] for o in rising_ease])
        if up and down:
            phrase = f"{up} up while {down}'s easing"
        elif up:
            phrase = f"{up} picking back up"
        else:
            phrase = f"{down} settling"
        return {"polarity": "ease", "phrase": phrase, "members": toward_ease}
    return None


def _composite(objects: list) -> Optional[dict]:
    """The convergence read: when several dimensions move the SAME way, name it descriptively.

    Two flavours, both DESCRIPTIVE and evidence-backed:
      * a STRAIN/EASE read (rest down + pressure up, or the reverse) — the gentle concern,
        phrased as a trend across named subjects, NEVER a condition (``_strain_direction``).
      * a plain DIRECTIONAL convergence (>= _CONVERGE_MIN subjects all rising, or all
        falling) — "a few things have been moving the same way lately".

    Returns ``{statement, direction, subjects, confidence, evidence}`` or None when nothing
    coheres. ``confidence`` is the mean confidence of the members, lightly lifted by how many
    converge (capped). Every statement passes the clean-gate. Pure; never raises."""
    if not objects:
        return None

    rising = [o for o in objects if o["direction"] == RISING]
    falling = [o for o in objects if o["direction"] == FALLING]

    strain = _strain_direction(objects)
    if strain is not None:
        members = strain["members"]
        subs = [o["subject"] for o in members]
        if strain["polarity"] == "strain":
            stmt = (f"A few things have been pulling the same direction lately — "
                    f"{strain['phrase']}. This stretch has been trending toward more strain.")
            fb = (f"Several signals are moving together: {strain['phrase']} "
                  f"({len(members)} of the tracked threads).")
            direction = "toward-strain"
        else:
            stmt = (f"A few things seem to be easing in the same direction lately — "
                    f"{strain['phrase']}. This stretch has been trending a little lighter.")
            fb = (f"Several signals are easing together: {strain['phrase']} "
                  f"({len(members)} of the tracked threads).")
            direction = "toward-ease"
        conf = _composite_confidence(members)
        return {
            "statement": _safe_statement(stmt, fb),
            "direction": direction,
            "subjects": subs,
            "confidence": conf,
            "evidence": {
                "members": [{"subject": o["subject"], "direction": o["direction"],
                             "momentum": o["momentum"],
                             "slope": o["evidence"]["slope_per_snapshot"]}
                            for o in members],
                "convergence_count": len(members),
            },
        }

    # plain directional convergence — many threads all rising or all falling.
    for group, word in ((rising, "rising"), (falling, "easing back")):
        if len(group) >= _CONVERGE_MIN:
            subs = [o["subject"] for o in group]
            stmt = (f"A few things have been moving the same way lately — "
                    f"{_join(subs)} all {word}.")
            fb = f"{len(group)} threads are all {word}: {_join(subs)}."
            conf = _composite_confidence(group)
            return {
                "statement": _safe_statement(stmt, fb),
                "direction": ("rising" if group is rising else "falling"),
                "subjects": subs,
                "confidence": conf,
                "evidence": {
                    "members": [{"subject": o["subject"], "direction": o["direction"],
                                 "momentum": o["momentum"],
                                 "slope": o["evidence"]["slope_per_snapshot"]}
                                for o in group],
                    "convergence_count": len(group),
                },
            }
    return None


def _composite_confidence(members: list) -> float:
    """Mean member confidence, lightly lifted by how many converge (each extra agreeing
    thread adds a little, capped well under 1). Pure."""
    if not members:
        return 0.0
    base = sum(float(o.get("confidence", 0.0)) for o in members) / len(members)
    lift = 1.0 + 0.08 * (len(members) - 1)
    return round(min(0.85, base * lift), 3)


def composite(name: str) -> Optional[dict]:
    """ENTRY POINT — just the composite convergence read for ``name`` (the same object found
    inside ``trajectory(name)["composite"]``), or None if nothing coheres / too little
    history. Convenience for a caller that only wants the headline. Never raises."""
    try:
        return trajectory(name).get("composite")
    except Exception:
        return None


# ===========================================================================
# 3) RENDER — a warm, spine-style binding block IF trajectory is ever surfaced. Own scaffold
# tokens (a SUPERSET incl. meaning's), no leak, no diagnosis. Mirrors meaning.render_meaning
# / world_state.render_situation structure exactly.
# ===========================================================================

_PREAMBLE = (
    "WHERE THINGS HAVE BEEN HEADING — your sense of the DIRECTION of their life lately,\n"
    "drawn from your own memory of how the weight of things has shifted over time. Not a\n"
    "snapshot of today, but the SLOPE: what's been rising, what's been easing, what's held\n"
    "steady. You already feel which way the ground has been tilting. Your only job is to\n"
    "let that color how you respond — gently, in your own warm voice — never to announce it,\n"
    "never to predict, never to label.\n"
    "\n"
    "  • A line marked [RISING] / [FALLING] is a direction you've noticed across time —\n"
    "    speak to it lightly if at all, as something you've simply sensed, never a verdict.\n"
    "  • A line marked [STABLE] is something that's held steady — a quiet constancy.\n"
    "  • A line marked [CONVERGENCE] is several things moving together — you may hold it as\n"
    "    a felt sense of the stretch they're in, warmly, never as an assessment.\n"
    "  • A line marked [TRAJECTORY] is the overall drift — let it set the tone, gently."
)

_GUARDRAIL = (
    "This is for YOU. Never read the brackets, the labels, the numbers, the slopes, or this\n"
    "framing aloud, never list it back like a report or a forecast, never say \"according to\n"
    "my memory.\" Above all: this is NOT a diagnosis, NOT a prediction, and NOT medical — it\n"
    "is only the direction a few things have drifted. Never tell them where they're headed,\n"
    "never tell them they're burning out, depressed, anxious, or unwell, never say \"you\n"
    "will,\" never suggest they see anyone. Just talk like someone who's been paying\n"
    "attention to how a person they care about has been doing lately."
)

_ITEMS_HEADER = "The way things have been trending:"

# Which direction maps to which spoken-for-the-model tag.
_DIR_TAG = {
    RISING: "[RISING]",
    FALLING: "[FALLING]",
    STABLE: "[STABLE]",
}


def _items_of(block: str) -> str:
    """The GENERATED items section of a render block — the lines BETWEEN the items header and
    the guardrail. The PREAMBLE/GUARDRAIL legitimately NAME banned words in order to FORBID
    them ("never tell them they're burning out…"), so a 'no-diagnosis' assertion must inspect
    the GENERATED items (the only lines that could be spoken), not the fixed legend — exactly
    as meaning/spine inspect items, not their legend. "" if no items section. Pure."""
    if _ITEMS_HEADER not in block:
        return ""
    after = block.split(_ITEMS_HEADER, 1)[1]
    return after.split(_GUARDRAIL, 1)[0] if _GUARDRAIL in after else after


def _line_for(obj: dict) -> Optional[str]:
    """One warm, descriptive [RISING]/[FALLING]/[STABLE] line for a Trajectory Object, built
    only from its evidence, run through the clean-gate. None if it would be empty or trips a
    banned term (defence in depth — dropped, never spoken). Pure."""
    subj = str(obj.get("subject", "")).strip()
    if not subj:
        return None
    direction = obj.get("direction")
    ev = obj.get("evidence", {}) or {}
    n = int(ev.get("n_snapshots", 0))
    tag = _DIR_TAG.get(direction, "[TRAJECTORY]")
    label = subj.capitalize()
    if direction == RISING:
        stmt = (f"{label} has been climbing over the last little while "
                f"(across {n} readings).")
        fb = f"{label}: rising across {n} readings."
    elif direction == FALLING:
        stmt = (f"{label} has been easing off lately "
                f"(across {n} readings).")
        fb = f"{label}: easing across {n} readings."
    else:
        stmt = f"{label} has held fairly steady lately (across {n} readings)."
        fb = f"{label}: steady across {n} readings."
    stmt = _safe_statement(stmt, fb)
    if not _is_clean(stmt):
        return None
    return f"{tag} {stmt}"


def render_trajectory(objs: Any, top: int = 5) -> str:
    """Render a trajectory read as a compact spine-style binding block, so the mouth can let
    DIRECTION inform a reply (warm, in character, never a forecast or assessment).

    ``objs`` may be EITHER the dict ``trajectory(name)`` returns (preferred — carries the
    composite + readiness) OR a bare list of Trajectory Objects. When not ready (< 2
    snapshots) it returns "" — there is nothing to bind, and we never fabricate a direction.

    Structure mirrors ``meaning.render_meaning``: PREAMBLE + a leading [CONVERGENCE]
    (composite) line if present + [TRAJECTORY] overall-drift framing + per-subject
    [RISING]/[FALLING]/[STABLE] ITEMS + GUARDRAIL (warmth + no-leak + the HARD no-diagnosis/
    no-prediction rule). Every tag is in ``TRAJECTORY_SCAFFOLD_TOKENS`` so the mouth scrubs
    leaks, and every emitted line passes the clean-gate so NO medical/prognostic term reaches
    the prompt. Empty / not-ready input -> "". Pure, model-free, never raises."""
    # accept either the full dict or a bare list of objects.
    composite_obj = None
    if isinstance(objs, dict):
        if objs.get("ready") is False:
            return ""
        composite_obj = objs.get("composite")
        objects = objs.get("objects") or []
    else:
        objects = list(objs or [])
    objects = [o for o in objects if isinstance(o, dict)]

    lines: list = []

    # the [CONVERGENCE] line leads, when present — the felt sense of the stretch. Scrubbed.
    if isinstance(composite_obj, dict):
        cs = str(composite_obj.get("statement", "")).strip()
        if cs and _is_clean(cs):
            lines.append(f"[CONVERGENCE] {cs}")

    seen = set()
    for o in objects[:max(1, top)]:
        line = _line_for(o)
        if not line or line in seen:
            continue
        seen.add(line)
        lines.append(line)

    if not lines:
        return ""

    items = "\n".join(lines)
    block = f"{_PREAMBLE}\n\n{_ITEMS_HEADER}\n{items}\n\n{_GUARDRAIL}"
    return block


# ===========================================================================
# 4) OPTIONAL APPEND-ONLY TRAJECTORY LEDGER — a snapshot of the DIRECTION read over time, so
# a caller can later see how the trajectory itself has shifted. Append-only, NEVER truncated
# (Law 001), exactly like the meaning / continuity ledgers. This is the module's ONLY write,
# and a caller opts into it explicitly. It does NOT write the meaning ledger.
# ===========================================================================

def ledger_path(name: str) -> Path:
    """The append-only trajectory ledger for ``name`` — one JSON read per line, never
    rewritten (Law 001), exactly like the meaning and continuity ledgers."""
    return STORE / f"{name}.trajectory.jsonl"


def snapshot_trajectory(name: str) -> Optional[dict]:
    """Append the current trajectory read to the trajectory ledger and return it (or None if
    there is nothing to record / not enough history). APPEND-ONLY: opens with O_APPEND and
    never truncates an existing ledger (Law 001). This is the module's ONLY write, and it
    touches NONE of the meaning / world / LIRF stores. Best-effort: a write failure returns
    None rather than raising. A caller opts into this explicitly; nothing here is implicit."""
    try:
        read = trajectory(name)
    except Exception:
        return None
    if not read.get("ready"):
        return None
    entry = {
        "law": "ANIMA LAW 003",
        "kind": "trajectory",
        "at": _now(),
        "version": VERSION,
        "n_snapshots": read.get("n_snapshots", 0),
        "objects": [
            {"subject": o["subject"], "direction": o["direction"],
             "momentum": o["momentum"], "confidence": o["confidence"],
             "slope": o["evidence"]["slope_per_snapshot"]}
            for o in read.get("objects", [])
        ],
        "composite": (None if not read.get("composite") else {
            "direction": read["composite"]["direction"],
            "subjects": read["composite"]["subjects"],
            "confidence": read["composite"]["confidence"],
        }),
    }
    try:
        path = ledger_path(name)
        secure_store.append_jsonl(path, entry)
    except Exception:
        return None
    return entry


def trajectory_snapshots(name: str) -> list:
    """Read back the trajectory ledger (oldest -> newest). [] if nothing recorded. A corrupt
    line is kept visible (Unknown > Lost), never silently dropped. Read-only; never raises."""
    path = ledger_path(name)
    if not path.exists():
        return []
    out: list = []
    try:
        for line in secure_store.read_jsonl_lines(path):
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                out.append({"_unparsed": line})
    except Exception:
        return out
    return out


# ===========================================================================
# AUDIT SURFACE — human-readable 'where things have been heading', the direction counterpart
# to meaning.render. Read-only; never the prompt block (that's render_trajectory).
# ===========================================================================

def render(name: str) -> str:
    """Human-readable audit of the trajectory read: readiness, each subject's direction +
    momentum + confidence + the score path it's built on, and the composite. Inspectable
    surface, not the prompt block. Read-only; never raises."""
    try:
        read = trajectory(name)
    except Exception:
        read = {"ready": False, "reason": "error", "objects": [], "composite": None,
                "n_snapshots": 0}

    out = [f"Where {name}'s person has been heading:"]
    if not read.get("ready"):
        out.append(f"  (not ready — {read.get('reason', 'not enough history yet')})")
        out.append(f"  snapshots available: {read.get('n_snapshots', 0)}")
        return "\n".join(out)

    out.append(f"  (read across {read['n_snapshots']} significance snapshots)")
    objs = read.get("objects", [])
    if not objs:
        out.append("  (no subject has enough points across snapshots to read a direction yet)")
    for o in objs[:12]:
        ev = o["evidence"]
        path = " -> ".join(f"{v:g}" for v in ev["score_path"])
        out.append(
            f"  • {o['subject']}: {o['direction'].upper()}"
            f"  momentum {o['momentum']:.2f} · confidence {o['confidence']:.2f}"
            f"  [slope {ev['slope_per_snapshot']:+.3f}/snap · r² {ev['r_squared']:.2f}"
            f" · n {ev['n_snapshots']}]\n"
            f"      score path: {path}")

    comp = read.get("composite")
    out.append("\n  Composite:")
    if comp:
        out.append(f"    [{comp['confidence']:.2f}] {comp['statement']}")
        out.append(f"    subjects: {', '.join(comp['subjects'])}")
    else:
        out.append("    (nothing has converged — no several-things-moving-together read yet)")
    return "\n".join(out)


# ===========================================================================
# SELF-TEST — run directly: `python3 -m anima.trajectory`. No model, no network; writes only
# to a throwaway store it cleans up (NEVER the real Vera.*). Mirrors the sibling organs'
# ok(label, cond) harness. The full standalone scenario suite lives in
# scripts/test_trajectory.py; this is the in-module smoke + the no-diagnosis invariant.
# ===========================================================================

def _make_snapshot(at_index: int, rows: list) -> dict:
    """Forge a meaning-shaped significance snapshot for the self-test (the same shape
    ``meaning.snapshot`` writes): ``{law, at, version, significance:[{subject,score,
    mentions,degree}]}``. ``at`` is spaced by day on a fixed base so ordering is stable."""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp()
    at = datetime.fromtimestamp(base + at_index * 86400, tz=timezone.utc)
    return {
        "law": "ANIMA LAW 003",
        "at": at.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "version": 1,
        "significance": [
            {"subject": s, "score": float(sc), "mentions": int(m), "degree": int(d)}
            for (s, sc, m, d) in rows
        ],
    }


def _selftest() -> int:
    import glob
    import secrets

    fails: list = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    print("trajectory (Trajectory Engine) self-test")

    # --- pure math: slope / direction / momentum / confidence are real functions ---
    ok("slope: a rising series has positive slope",
       _slope([(0, 1.0), (1, 2.0), (2, 3.0)]) > 0)
    ok("slope: a falling series has negative slope",
       _slope([(0, 3.0), (1, 2.0), (2, 1.0)]) < 0)
    ok("slope: a flat series has ~zero slope",
       abs(_slope([(0, 2.0), (1, 2.0), (2, 2.0)])) < 1e-9)
    ok("slope: a single point has no slope (0.0)", _slope([(0, 5.0)]) == 0.0)
    ok("r2: a clean line fits ~1.0",
       _r_squared([(0, 1.0), (1, 2.0), (2, 3.0)], 1.0) > 0.99)
    ok("direction: deadband maps a tiny tilt to STABLE",
       _direction_of(0.0) == STABLE and _direction_of(_STABLE_BAND * 0.5) == STABLE)
    ok("direction: a clear rise/fall maps to RISING/FALLING",
       _direction_of(0.5) == RISING and _direction_of(-0.5) == FALLING)
    ok("momentum: steeper & cleaner -> higher",
       _momentum_of(0.6, 1.0) > _momentum_of(0.1, 1.0)
       and _momentum_of(0.6, 1.0) > _momentum_of(0.6, 0.2))
    ok("confidence: more points -> higher, and never reaches 1.0",
       _confidence_of(8, 1.0, RISING) > _confidence_of(2, 1.0, RISING)
       and _confidence_of(50, 1.0, RISING) < 1.0)
    ok("clean-gate: a neutral trend phrase is clean",
       _is_clean("stress has been climbing across the last few readings"))
    ok("clean-gate: diagnosis/prognosis phrasing is caught",
       not _is_clean("you sound depressed") and not _is_clean("this is burnout")
       and not _is_clean("you will spiral") and not _is_clean("a poor prognosis"))

    name = "trajectory_selftest_" + secrets.token_hex(3)
    try:
        if _HAVE_MEANING and _meaning is not None:
            # redirect the meaning ledger to OUR throwaway store so we never read/write real
            # Vera.*; write a synthetic SEQUENCE of snapshots directly into it (we own the
            # ledger format; this avoids needing a world store to back meaning.snapshot).
            saved_store = getattr(_meaning, "STORE", None)
            _meaning.STORE = STORE
            try:
                lp = _meaning.ledger_path(name)
                lp.parent.mkdir(parents=True, exist_ok=True)
                # work RISES, sleep FALLS, reading holds STABLE, exercise FALLS — a classic
                # convergence toward strain (rest down while pressure up).
                seq = [
                    [("work", 8.0, 8, 2), ("sleep", 7.0, 7, 2), ("reading", 4.0, 4, 1),
                     ("exercise", 6.0, 6, 1)],
                    [("work", 10.0, 12, 3), ("sleep", 6.0, 6, 2), ("reading", 4.1, 4, 1),
                     ("exercise", 5.0, 5, 1)],
                    [("work", 12.5, 17, 3), ("sleep", 5.0, 5, 2), ("reading", 3.9, 4, 1),
                     ("exercise", 4.0, 4, 1)],
                    [("work", 14.0, 22, 4), ("sleep", 4.0, 4, 2), ("reading", 4.0, 4, 1),
                     ("exercise", 3.0, 3, 1)],
                ]
                with open(lp, "a", encoding="utf-8") as f:
                    for i, rows in enumerate(seq):
                        f.write(json.dumps(_make_snapshot(i, rows)) + "\n")

                read = trajectory(name)
                ok("scenario: trajectory is ready (>= 2 snapshots)", read["ready"] is True)
                ok("scenario: it read the full snapshot sequence", read["n_snapshots"] == 4)
                by = {o["subject"]: o for o in read["objects"]}
                ok("direction: 'work' (rising significance) reads RISING",
                   by.get("work", {}).get("direction") == RISING)
                ok("direction: 'sleep' (falling significance) reads FALLING",
                   by.get("sleep", {}).get("direction") == FALLING)
                ok("direction: 'reading' (flat) reads STABLE",
                   by.get("reading", {}).get("direction") == STABLE)
                ok("evidence: every object cites its snapshot path (deltas/slope)",
                   all(o["evidence"].get("score_path") and "slope_per_snapshot" in o["evidence"]
                       for o in read["objects"]))
                ok("confidence: every object's confidence is in (0, 0.9]",
                   all(0.0 < o["confidence"] <= 0.9 for o in read["objects"]))

                # COMPOSITE: rest down + pressure up -> a coherent descriptive strain read.
                comp = read["composite"]
                ok("composite: a convergence read is produced", isinstance(comp, dict))
                ok("composite: it names the strain direction descriptively",
                   bool(comp) and "strain" in comp.get("statement", "").lower()
                   and "sleep" in comp.get("subjects", []) and "work" in comp.get("subjects", []))
                ok("composite: it carries evidence + a confidence",
                   bool(comp) and comp.get("confidence", 0) > 0
                   and comp.get("evidence", {}).get("convergence_count", 0) >= 2)

                # THE NO-DIAGNOSIS GATE — over EVERY generated line in the whole read + render.
                generated = []
                for o in read["objects"]:
                    ln = _line_for(o)
                    if ln:
                        generated.append(ln)
                if comp:
                    generated.append(comp["statement"])
                block = render_trajectory(read)
                generated.append(_items_of(block))
                ok("NO-DIAGNOSIS GATE: not one generated line trips a banned term",
                   all(_is_clean(g) for g in generated))

                # render: warm spine-style, no leak, no diagnosis.
                ok("render: produces a non-empty binding block", bool(block.strip()))
                ok("render: leads with the CONVERGENCE line", "[CONVERGENCE]" in block)
                ok("render: carries a RISING and a FALLING line",
                   "[RISING]" in block and "[FALLING]" in block)
                ok("render: guardrail forbids diagnosis + prediction + reading brackets",
                   "NOT a diagnosis" in block and "NOT a prediction" in block
                   and "Never read the brackets" in block)
                ok("render: every emitted tag is in TRAJECTORY_SCAFFOLD_TOKENS (scrubbable)",
                   all(t in TRAJECTORY_SCAFFOLD_TOKENS
                       for t in ("[RISING]", "[FALLING]", "[STABLE]",
                                 "[CONVERGENCE]", "[TRAJECTORY]")))
                ok("render: the GENERATED items contain NO banned term",
                   _is_clean(_items_of(block)))

                # the optional append-only ledger: append + read-back + Law-001 append-only.
                snap1 = snapshot_trajectory(name)
                ok("ledger: a trajectory snapshot was appended",
                   snap1 is not None and snap1.get("kind") == "trajectory")
                n_before = len(trajectory_snapshots(name))
                snapshot_trajectory(name)
                ok("ledger: append-only (count grew, prior kept)",
                   len(trajectory_snapshots(name)) == n_before + 1)
            finally:
                if saved_store is not None:
                    _meaning.STORE = saved_store
        else:
            ok("scenario: meaning importable (skipped — running fully isolated)", True)

        # --- NOT-ENOUGH-HISTORY: a single snapshot yields an honest 'too early', no direction.
        one_name = "trajectory_one_" + secrets.token_hex(3)
        if _HAVE_MEANING and _meaning is not None:
            saved_store = getattr(_meaning, "STORE", None)
            _meaning.STORE = STORE
            try:
                lp = _meaning.ledger_path(one_name)
                lp.parent.mkdir(parents=True, exist_ok=True)
                with open(lp, "a", encoding="utf-8") as f:
                    f.write(json.dumps(_make_snapshot(0, [("work", 9.0, 9, 2)])) + "\n")
                one = trajectory(one_name)
                ok("not-enough-history: a single snapshot is NOT ready", one["ready"] is False)
                ok("not-enough-history: it returns an honest reason, no objects",
                   "enough" in one["reason"].lower() and one["objects"] == [])
                ok("not-enough-history: render of a not-ready read is empty",
                   render_trajectory(one) == "")
            finally:
                if saved_store is not None:
                    _meaning.STORE = saved_store

        # --- NEVER-FABRICATE on NO history at all (no ledger): ready=False, no objects.
        empty_name = "trajectory_empty_" + secrets.token_hex(3)
        empty = trajectory(empty_name)
        ok("empty: no snapshots -> not ready, no fabricated direction",
           empty["ready"] is False and empty["objects"] == [] and empty["composite"] is None)
        ok("empty: render of nothing -> empty string", render_trajectory(empty) == "")
        ok("empty: composite() on an empty life is None", composite(empty_name) is None)

    finally:
        for fp in (glob.glob(str(STORE / f"{name}.*"))
                   + glob.glob(str(STORE / "trajectory_one_*"))
                   + glob.glob(str(STORE / "trajectory_empty_*"))):
            try:
                os.remove(fp)
            except OSError:
                pass

    print()
    if fails:
        print(f"{len(fails)} FAILED: " + ", ".join(fails))
        return 1
    print("ALL TRAJECTORY SELFTESTS PASS")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(_selftest())
