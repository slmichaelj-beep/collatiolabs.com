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
# capability sub-permissions default to the safe subset; UI can widen them
DEFAULT = {"imessage": False, "mail": False, "web": False,
           "imessage_read": False, "mail_read": False, "allowlist": []}


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


def load(name) -> dict:
    raw = load_json(_path(name)) if _path(name).exists() else {}
    out = dict(DEFAULT)
    if isinstance(raw, dict):
        for k in ("imessage", "mail", "web", "imessage_read", "mail_read"):
            out[k] = bool(raw.get(k, False))
        al = raw.get("allowlist", [])
        if isinstance(al, list):
            out["allowlist"] = sorted({_norm_host(h) for h in al if isinstance(h, str)} - {""})[:100]
    return out


def save(name, caps) -> dict:
    out = dict(DEFAULT)
    for k in ("imessage", "mail", "web", "imessage_read", "mail_read"):
        out[k] = bool(caps.get(k, False))
    al = caps.get("allowlist", [])
    if isinstance(al, list):
        out["allowlist"] = sorted({_norm_host(h) for h in al if isinstance(h, str)} - {""})[:100]
    STORE.mkdir(exist_ok=True)
    save_json(_path(name), out)
    return out


def enabled(name, key) -> bool:
    return bool(load(name).get(key, False))
