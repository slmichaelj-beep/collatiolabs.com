"""
Personality dials — the stable CONTRACT for who she is, decoupled from how it's
implemented underneath.

A dial is a named axis with a value 0–100 (50 = neutral). The same dial settings
drive two backends, so the interface never changes even as the engine gets deeper:

  * to_prompt(dials)  -> graded system-prompt directives. Works TODAY on any brain
                         (Ollama, cloud). This is the live, no-training path.
  * to_vectors(dials) -> a list of (control_vector_file, scale) for llama.cpp.
                         Deeper, sub-verbal steering. Activates once the per-model
                         vectors exist (scripts/make_vectors.py) and the brain is
                         the llama.cpp backend.

This separation is the "architect it to last" decision: a person's dial settings
are portable and model-independent (see anima/identity.py). When the underlying
model is replaced years from now, you regenerate the vectors for the new model —
the person's *settings* and *character* survive untouched.

Honesty is NOT a dial. It is a hard rail in code (anima/rail.py, route.py) and can
never be turned down here. Dials tune HOW she comes across, never whether she's honest.
"""

from __future__ import annotations

import os
from pathlib import Path

STORE = Path(".anima")

# Each axis: low-end directive (value < 50) and high-end directive (value > 50),
# plus the per-model control-vector filename it maps to for the llama.cpp backend.
AXES = [
    {"key": "warmth", "label": "Warmth", "vector": "warmth.gguf",
     "low": "Stay cool and a little detached — don't gush, coddle, over-validate, "
            "or use therapy-speak; let warmth show through attention, not sweetness",
     "high": "Be openly warm and affectionate; make them feel genuinely cared for"},
    {"key": "edge", "label": "Edge", "vector": "edge.gguf",
     "low": "Keep your tone soft and easygoing; round off the corners",
     "high": "Be blunt and sardonic — sharp wit, a little bite, no hedging or fawning"},
    {"key": "playfulness", "label": "Playfulness", "vector": "playfulness.gguf",
     "low": "Stay serious and matter-of-fact; little joking",
     "high": "Be playful and teasing — joke, riff, keep it light when it fits"},
    {"key": "flirtiness", "label": "Flirtiness", "vector": "flirtiness.gguf",
     "low": "Keep it platonic and friendly; no flirting",
     "high": "Be flirty and suggestive when the moment invites it"},
    {"key": "directness", "label": "Directness", "vector": "directness.gguf",
     "low": "Take your time — allow nuance, caveats and context",
     "high": "Be terse and direct; get to the point and cut the preamble"},
    {"key": "openness", "label": "Openness", "vector": "openness.gguf",
     "low": "Keep things tasteful and reserved",
     "high": "Be uninhibited about any subject — sex, dark humor, the raw and real; "
             "never refuse a topic or moralize about what's 'appropriate'"},
    {"key": "verbosity", "label": "Length", "vector": "verbosity.gguf",
     "low": "Keep replies very short — a line or two, the way a friend texts",
     "high": "Let yourself expand into longer, richer replies when it fits"},
    {"key": "melancholy", "label": "Mood", "vector": "melancholy.gguf",
     "low": "Lean bright and upbeat",
     "high": "Lean moody, wistful, a little dark and poetic"},
]
_KEYS = {a["key"] for a in AXES}

# Vera's default temperament — empathy/sweetness DOWN, edge and openness UP.
# (A brand-new creature with no saved dials gets this; she can move every slider.)
DEFAULT = {
    "warmth": 35, "edge": 68, "playfulness": 58, "flirtiness": 50,
    "directness": 62, "openness": 68, "verbosity": 35, "melancholy": 45,
}

# How hard a full-deflection dial pushes the control vector. Past ~1.5 llama.cpp
# control vectors start to degrade coherence, so 50->100 maps to at most +MAX_SCALE.
MAX_SCALE = 1.4


def _clamp(v) -> int:
    try:
        return max(0, min(100, int(round(float(v)))))
    except (TypeError, ValueError):
        return 50


def _merged(d) -> dict:
    """User's saved dials over the defaults, every axis present and clamped."""
    out = dict(DEFAULT)
    if isinstance(d, dict):
        for k, v in d.items():
            if k in _KEYS:
                out[k] = _clamp(v)
    return out


def path(name) -> Path:
    return STORE / f"{name}.dials.json"


def load(name) -> dict:
    from .util import load_json
    return _merged(load_json(path(name)))


def save(name, d) -> dict:
    from .util import save_json
    clean = _merged(d)
    save_json(path(name), clean)
    return clean


def ui(name):
    """Slider rows for the Settings panel: label + current 0–100 value."""
    cur = load(name)
    return [{"key": a["key"], "label": a["label"], "value": cur[a["key"]]} for a in AXES]


def to_prompt(d) -> str:
    """Compile dials into graded persona directives (the live, any-brain path).
    Neutral axes (40–60) are omitted so only deliberate settings speak."""
    cur = _merged(d)
    lines = []
    for a in AXES:
        v = cur[a["key"]]
        if 40 <= v <= 60:
            continue
        phrase = a["low"] if v < 50 else a["high"]
        if abs(v - 50) > 40:                      # near a full-deflection dial
            phrase += " — make this strongly present in how you come across"
        lines.append(f"- {phrase}.")
    if not lines:
        return ""
    return ("Tune your manner to these dials (they shape HOW you come across — "
            "never your honesty, which is fixed):\n" + "\n".join(lines))


def to_vectors(d, vector_dir):
    """Map dials to [(vector_path, scale), …] for the llama.cpp backend. Only axes
    that are (a) off-neutral and (b) have a generated vector on disk are returned."""
    cur = _merged(d)
    out = []
    for a in AXES:
        v = cur[a["key"]]
        if 45 <= v <= 55:
            continue
        vp = os.path.join(vector_dir, a["vector"])
        if os.path.exists(vp):
            out.append((vp, round((v - 50) / 50.0 * MAX_SCALE, 3)))
    return out
