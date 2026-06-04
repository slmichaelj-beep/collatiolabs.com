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
BOOL_KEYS = ("imessage", "mail", "web", "imessage_read", "mail_read", "identity_agency")

# Enum (multi-value) settings, persisted alongside the booleans. Each maps a key to
# (allowed_values, default); load()/save() read this map so a new enum stays in lockstep
# the way BOOL_KEYS does for flags. Unlike a flag, an enum has a *safe default value*
# (not just False) and any value off the allowed list collapses to that default.
#
# curiosity — the Curiosity Budget. Controls how OFTEN Vera surfaces a contextual
# question (FREQUENCY only — never the content of any question, which the Curiosity
# Engine owns). "minimal" rarely asks, "balanced" is the default cadence, "deep" asks
# more freely. It is a dial on volume, not a gate on what she may learn.
ENUM_KEYS = {
    "curiosity": (("minimal", "balanced", "deep"), "balanced"),
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
