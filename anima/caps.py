"""
caps — explicit, default-OFF capability toggles for Vera's outward-facing powers.

Reading your texts/email, sending messages, and reaching the web are all OFF until
you turn them on in settings, and the web allow-list starts EMPTY (nothing reachable
until you add a domain). Stored per-creature in .anima/{name}.caps.json and encrypted
at rest like everything else. This is the on/off switch; the draft→confirm→send gate
(in server.py) is the separate, non-bypassable guard for actually sending anything.
"""

from __future__ import annotations

from pathlib import Path

from .util import load_json, save_json

STORE = Path(".anima")
KEYS = ("imessage", "mail", "web")
# Every boolean capability flag, persisted per-creature and default-OFF. Listed
# once so load()/save() stay in lockstep; "allowlist" is handled separately below.
#
# identity_agency — the held switch for Vera's Identity & Agency organs. OFF until
# the founder turns it on; while OFF the organs stay dormant (organs/__init__.py
# reads this via is_enabled()), honouring the 2026-07-03 observation-window freeze.
#
# grow_intelligence — the "[x] Grow Intelligence" switch for LERF Phase 6 autonomous
# learning (anima/lerf_grow.py). OFF until the founder turns it on; while OFF the
# idle-time learning loop is a provable no-op — ZERO autonomous activity and ZERO
# paid teacher calls. Same default-OFF posture as identity_agency: nothing grows and
# nothing is spent unless the user has EXPLICITLY opted in. It governs ONLY task-skill
# growth; the identity freeze is independent and absolute (a curriculum can never be
# about who Vera is).
BOOL_KEYS = ("imessage", "mail", "web", "imessage_read", "mail_read", "identity_agency",
             "grow_intelligence")

# Enum (multi-value) settings, persisted alongside the booleans. Each maps a key to
# (allowed_values, default); load()/save() read this map so a new enum stays in lockstep
# the way BOOL_KEYS does for flags. Unlike a flag, an enum has a *safe default value*
# (not just False) and any value off the allowed list collapses to that default.
#
# curiosity — the Curiosity Budget. Controls how OFTEN Vera surfaces a contextual
# question (FREQUENCY only — never the content of any question, which the Curiosity
# Engine owns). "minimal" rarely asks, "balanced" is the default cadence, "deep" asks
# more freely. It is a dial on volume, not a gate on what she may learn.
#
# grow_mode — the Autonomous Growth MODE for LERF Phase 6 (anima/lerf_grow.py). Replaces the
# single grow_intelligence throttle with five named intensities: "off" (DEFAULT — provably
# inert, $0, nothing autonomous), "low" (gentle), "medium" (the historical default cadence),
# "high" (aggressive idle learning), "research" (an explicit research burst). The mode picks a
# (cadence_hours, max_per_run, budget_ceiling) profile in lerf_grow; "off" is the safe default
# and any unknown value collapses to it. It governs ONLY task-knowledge growth — the identity
# freeze is independent and absolute (no mode can ever grow who Vera is). The legacy
# grow_intelligence boolean still works (it gates the master ON/OFF); grow_mode refines the
# intensity once ON. Default "off" keeps the whole engine default-OFF.
ENUM_KEYS = {
    "curiosity": (("minimal", "balanced", "deep"), "balanced"),
    "grow_mode": (("off", "low", "medium", "high", "research"), "off"),
}
# capability sub-permissions default to the safe subset; UI can widen them
DEFAULT = {
    **{k: False for k in BOOL_KEYS},
    **{k: default for k, (_allowed, default) in ENUM_KEYS.items()},
    "allowlist": [],
}


def _path(name):
    return STORE / f"{name}.caps.json"


def _norm_host(h: str) -> str:
    """A bare lowercase host: strip scheme, path, port, leading 'www.' and whitespace."""
    h = (h or "").strip().lower()
    if "://" in h:
        h = h.split("://", 1)[1]
    h = h.split("/", 1)[0].split(":", 1)[0]
    if h.startswith("www."):
        h = h[4:]
    return h


def _norm_enum(key: str, value) -> str:
    """Coerce a stored enum value to an allowed one, else the key's safe default.
    A missing key, a non-string, or any value off the allow-list → the default."""
    allowed, default = ENUM_KEYS[key]
    if isinstance(value, str) and value in allowed:
        return value
    return default


def load(name) -> dict:
    raw = load_json(_path(name)) if _path(name).exists() else {}
    out = dict(DEFAULT)
    if isinstance(raw, dict):
        for k in BOOL_KEYS:
            out[k] = bool(raw.get(k, False))
        for k in ENUM_KEYS:
            out[k] = _norm_enum(k, raw.get(k))
        al = raw.get("allowlist", [])
        if isinstance(al, list):
            out["allowlist"] = sorted({_norm_host(h) for h in al if isinstance(h, str)} - {""})[:100]
    return out


def save(name, caps) -> dict:
    out = dict(DEFAULT)
    for k in BOOL_KEYS:
        out[k] = bool(caps.get(k, False))
    for k in ENUM_KEYS:
        out[k] = _norm_enum(k, caps.get(k, out[k]))
    al = caps.get("allowlist", [])
    if isinstance(al, list):
        out["allowlist"] = sorted({_norm_host(h) for h in al if isinstance(h, str)} - {""})[:100]
    STORE.mkdir(exist_ok=True)
    save_json(_path(name), out)
    return out


def enabled(name, key) -> bool:
    return bool(load(name).get(key, False))


def curiosity_budget(name) -> str:
    """How OFTEN Vera surfaces a contextual question: "minimal" | "balanced" | "deep".

    The Curiosity Engine (anima/curiosity.py) calls this to pace itself. Fails SAFE:
    a missing or corrupt store, or any value not on the allow-list, returns the
    default "balanced" — curiosity is never silently switched off or cranked up by
    bad data. (FREQUENCY only; it never touches the *content* of a question.)
    """
    _allowed, default = ENUM_KEYS["curiosity"]
    try:
        value = load(name).get("curiosity", default)
    except Exception:
        return default
    return value if value in _allowed else default


def set_curiosity_budget(name, value) -> str:
    """Persist the Curiosity Budget for `name`. Mirrors how other settings are written:
    read current caps, set this one field, save through the normalising `save()`.
    An invalid value is coerced to the safe default rather than stored. Returns the
    value actually persisted."""
    caps = load(name)
    caps["curiosity"] = _norm_enum("curiosity", value)
    return save(name, caps)["curiosity"]


def grow_mode(name) -> str:
    """The Autonomous Growth MODE for `name`: "off" | "low" | "medium" | "high" | "research".

    anima/lerf_grow.py calls this to pick its (cadence, per-run cap, budget) profile. Fails
    SAFE: a missing/corrupt store, or any value not on the allow-list, returns the default
    "off" — autonomous growth is never silently switched on by bad data. (INTENSITY only; the
    identity freeze and the per-mode budget ceiling are enforced separately in lerf_grow.)"""
    _allowed, default = ENUM_KEYS["grow_mode"]
    try:
        value = load(name).get("grow_mode", default)
    except Exception:
        return default
    return value if value in _allowed else default


def set_grow_mode(name, value) -> str:
    """Persist the Autonomous Growth mode for `name`. Mirrors set_curiosity_budget: read current
    caps, set this one field, save through the normalising `save()`. An invalid value is coerced
    to the safe default ("off") rather than stored. Returns the value actually persisted."""
    caps = load(name)
    caps["grow_mode"] = _norm_enum("grow_mode", value)
    return save(name, caps)["grow_mode"]
