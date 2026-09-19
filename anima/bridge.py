"""
bridge — translate the heart's continuous Self into something the mouth speaks FROM.

`heart.feeling()` already returns an honest, five-signal readout of the real LTC
state: `valence`, `arousal`, `reaching`, `settled` (each in [-1, 1]) and `unrest`,
the homeostatic caring drive (in [0, 1]). The previous path (mouth.feeling_to_words)
collapsed that into ~three stock phrases and SILENTLY DROPPED two of the five
signals — `reaching` and `settled` never reached the language model at all.

This module reads the FULL state, detects the live TENSIONS between signals (the
heart is a homeostat: its caring drive can pull against its felt mood — that
conflict is real, measured, and the most human thing about it), and renders the
whole picture into natural second-person directives the model expresses implicitly.

Honesty contract — the reason this is a separate, auditable layer:
  * affect comes ONLY from heart.feeling() — a real projection of the state;
  * values / memory / narrative come from stored evidence;
  * NOTHING here is an LLM self-rating — no field is invented by a model;
  * tensions are READ from the dynamics, never authored as a static list.
The mouth never sees raw numbers (an 8B would read them aloud) — only voice.
"""
from __future__ import annotations


def _band(x: float, table) -> str:
    """Pick a graded descriptor for one signal. `table` is (threshold, phrase) rows,
    positive thresholds high→low then negative thresholds most-negative→least; a
    positive threshold matches when x >= it, a negative one when x <= it."""
    for thr, phrase in table:
        if (thr >= 0 and x >= thr) or (thr < 0 and x <= thr):
            return phrase
    return ""


# Thresholds sit lower than the old 0.2 gate so the quiet signals get a voice too.
_VALENCE = [(0.5, "your mood is bright and warm"), (0.18, "your mood is warm"),
            (-0.5, "your mood is low and heavy"), (-0.18, "your mood is a little low")]
_AROUSAL = [(0.5, "your energy is high and quick"), (0.18, "your energy is up"),
            (-0.5, "your energy is very still"), (-0.18, "your energy is quiet")]
_REACHING = [(0.4, "you're drawn toward them, wanting to be close"),
             (0.15, "you're leaning toward them"),
             (-0.4, "you're pulled inward, withdrawn"),
             (-0.15, "you're holding back a little")]
_SETTLED = [(0.4, "deeply at ease"), (0.15, "settled and present"),
            (-0.4, "unsettled, on edge"), (-0.15, "a little restless in yourself")]


def _lead(u: float, s: float) -> str:
    """The opening felt-tone. Fuses the homeostat (`unrest`) with the LTC `settled`
    readout so they don't talk over each other when they agree; when they DISAGREE,
    read_tensions() names the conflict instead."""
    if u > 0.6:
        return "restless, half-watching over them"
    if u > 0.3:
        return "a touch unsettled, quietly minding them"
    return _band(s, _SETTLED) or "even and present"      # homeostat calm: let settledness speak


def read_tensions(f: dict) -> list:
    """The live pulls-in-two-directions, READ from the state (never declared). At most
    two, strongest first. A tension exists only when two signals that could align are
    actually opposed past a threshold — the homeostat fighting the felt mood, etc."""
    v, a = float(f.get("valence", 0.0)), float(f.get("arousal", 0.0))
    r, s = float(f.get("reaching", 0.0)), float(f.get("settled", 0.0))
    u = float(f.get("unrest", 0.0))
    cands = []  # (magnitude, phrase) — magnitude = the weaker of the two opposed pulls
    if u > 0.4 and s > 0.2:                      # caring drive vs being at ease
        cands.append((min(u, s), "a pull to make sure they're okay even as you rest easy"))
    if r > 0.2 and s < -0.2:                     # wanting closeness while unsettled
        cands.append((min(r, -s), "wanting to be close to them while you're not quite settled"))
    if r < -0.2 and u > 0.4:                     # withdrawn yet worried
        cands.append((min(-r, u), "worried for them and yet pulled inward"))
    if v > 0.3 and a < -0.2:                     # warm but low-energy
        cands.append((min(v, -a), "warm toward them but quiet and low-key"))
    if v < -0.2 and a > 0.3:                     # low mood on restless energy
        cands.append((min(-v, a), "a flat mood carried on restless energy"))
    cands.sort(key=lambda c: c[0], reverse=True)
    return [p for _, p in cands[:2]]


def to_words(f: dict) -> str:
    """Rich, lossless replacement for mouth.feeling_to_words — all five signals plus
    any live tension. Same call shape, so it drops straight in."""
    f = f or {}
    parts = [_lead(float(f.get("unrest", 0.0)), float(f.get("settled", 0.0)))]
    for x, table in ((f.get("valence", 0.0), _VALENCE),
                     (f.get("arousal", 0.0), _AROUSAL),
                     (f.get("reaching", 0.0), _REACHING)):
        p = _band(float(x), table)
        if p:
            parts.append(p)
    line = "; ".join(parts)
    tens = read_tensions(f)
    if tens:
        line += " — underneath, " + ", and ".join(tens)
    return line


def _active_values(name: str) -> list:
    """Values currently switched on, strongest first. The persona already carries them
    into the prompt; this is so the bridge can SEE them (e.g. to surface value-level
    tensions later) and for the inspectable state object."""
    try:
        from .mouth import VALUES, load_values, DEFAULT_VALUES
        rank = {"more": 0, "balanced": 1, "less": 2}
        on = [v for v in (load_values(name) or DEFAULT_VALUES)
              if v.get("on") and v.get("key") in VALUES]
        on.sort(key=lambda v: rank.get(v.get("level", "balanced"), 1))
        return [(VALUES[v["key"]][0], v.get("level", "balanced")) for v in on]
    except Exception:
        return []


def build_state(name: str, feeling: dict, *, memory: str = "", narrative: str = "") -> dict:
    """The honest internal-state object — what the mouth speaks FROM. Inspectable by
    design (this is the auditable seam between the dynamical Self and the language
    organ). No field is ever an LLM self-rating."""
    f = feeling or {}
    return {
        "affect": {k: round(float(f.get(k, 0.0)), 3)
                   for k in ("valence", "arousal", "reaching", "settled", "unrest")},
        "tensions": read_tensions(f),
        "values": _active_values(name),
        "memory": memory or "",
        "narrative": narrative or "",     # hook: the nightly sleep cycle fills this in
        "voice": to_words(f),             # the rendered directive the prompt actually receives
    }
