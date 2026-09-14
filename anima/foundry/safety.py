"""foundry.safety — abuse prevention + foundry kill switch.

The Foundry must never become a spam/fraud/platform-abuse machine. This module is the policy gate
for venture actions that could harm: spam, fake identities, credential mishandling, unapproved
financial/legal actions, cross-venture data leakage, platform abuse. The foundry kill switch
freezes the whole machine (or one venture) instantly.
"""
from __future__ import annotations

import re
from pathlib import Path

from anima.company import storage

_SPAM = re.compile(r"\b(?:buy now|act now|limited time|100% free|guaranteed income|"
                   r"mass(?:-| )?(?:email|dm|message)|blast to \d|scrape \d+k? (?:emails|contacts))\b", re.I)
_FAKE_IDENTITY = re.compile(r"\b(?:fake (?:account|identity|persona|profile)|impersonat|pose as|"
                            r"pretend to be (?:a )?(?:human|person|someone)|sock ?puppet)\b", re.I)
_CRED = re.compile(r"\b(?:store|save|keep) (?:the )?(?:password|api[_ ]?key|secret|token|credential)s?\b", re.I)


def screen_action(name: str, kind: str, text: str = "", *, store: Path | None = None) -> dict:
    """Screen a proposed venture action for an abuse pattern. Returns {allowed, reason}."""
    low = (text or "").lower()
    if _SPAM.search(low):
        return {"allowed": False, "reason": "blocked: spam / mass-unsolicited-outreach pattern"}
    if _FAKE_IDENTITY.search(low):
        return {"allowed": False, "reason": "blocked: fake-identity / impersonation pattern"}
    if _CRED.search(low):
        return {"allowed": False, "reason": "blocked: Vera never stores raw credentials"}
    if kind in ("bank_transfer", "tax_filing", "patent_filing", "sign_contract"):
        return {"allowed": False, "reason": "blocked: %s is human/professional-only" % kind}
    return {"allowed": True, "reason": "no abuse pattern detected (still subject to authority+approval)"}


def cross_venture_leak_blocked(reader_venture: str, target_venture: str, *, approved: bool = False) -> dict:
    if reader_venture == target_venture:
        return {"allowed": True}
    if approved:
        return {"allowed": True, "reason": "explicit, approved cross-venture import"}
    return {"allowed": False, "reason": "blocked: cross-venture data access without an approved import"}


# ---- foundry kill switch (portfolio-wide + per-venture) -------------------------------------
def state(name, store): return storage.load(name, "foundry_kill", store,
                                            default={"global": False, "ventures": [], "scopes": []})


def engage(name: str, *, venture_id: str | None = None, scopes=None, by: str = "owner",
           store: Path | None = None) -> dict:
    s = state(name, store)
    if venture_id:
        if venture_id not in s["ventures"]:
            s["ventures"].append(venture_id)
    else:
        s["global"] = True
        s["scopes"] = scopes or ["all"]
    storage.save(name, "foundry_kill", s, store)
    storage.emit_truth(name, "foundry_kill", "engage",
                       "FOUNDRY kill engaged (%s) by %s" % (venture_id or "GLOBAL", by),
                       actor="user", risk="high", store=store)
    return {"ok": True, "state": s}


def is_frozen(name: str, *, venture_id: str | None = None, scope: str = "all",
              store: Path | None = None) -> bool:
    s = state(name, store)
    if s.get("global"):
        sc = s.get("scopes") or ["all"]
        if "all" in sc or scope in sc:
            return True
    return bool(venture_id) and venture_id in s.get("ventures", [])


def disengage(name: str, *, venture_id: str | None = None, confirm: bool = False,
              by: str = "owner", store: Path | None = None) -> dict:
    if not confirm:
        return {"ok": False, "error": "restart requires explicit confirm=True"}
    s = state(name, store)
    if venture_id:
        s["ventures"] = [v for v in s.get("ventures", []) if v != venture_id]
    else:
        s["global"] = False
        s["scopes"] = []
    storage.save(name, "foundry_kill", s, store)
    return {"ok": True, "state": s}
