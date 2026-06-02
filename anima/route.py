"""route — the deterministic capability router (provenance, not vibes).

The lesson of the "Sarah" incident: a swappable local mouth must NEVER describe a
capability because it *believes* the action happened — only because code can
*prove* it happened. So the router runs in real code, before the mouth speaks:

    user turn -> route() -> (maybe call a real capability) -> ground-truth note

If a turn asks for live data (messages, mail...), the router calls the real
endpoint and returns a note containing the ACTUAL result. The mouth then narrates
only what's in that note. If the capability is off or fails, the note says so and
the mouth reports that plainly — it never invents a sender, a quote, or a count.

This lives OUTSIDE the mouth on purpose: drop in any model and the guarantee holds.
It is the same philosophy as the honesty rail — important behaviour lives in code.
"""

from __future__ import annotations

import re

# Intent cues. Deliberately broad: a false positive just makes her truthfully fetch
# (and find nothing); a false negative is the fabrication we are eliminating.
_READ_MSG = [re.compile(p, re.I) for p in [
    r"\bunread\b",
    r"\b(?:any|new|recent|latest)\b.{0,20}\b(?:text|texts|message|messages|imessage|imessages|dm|dms)\b",
    r"\b(?:check|read|see|show|look at|got|get)\b.{0,20}\b(?:text|texts|message|messages|imessage|imessages)\b",
    r"\bdo i have\b.{0,30}\b(?:text|texts|message|messages)\b",
    r"\bwho (?:texted|messaged|dm'?d) me\b",
    r"\bmy (?:\w+\s+){0,2}(?:texts|messages|imessages)\b",
]]
_READ_MAIL = [re.compile(p, re.I) for p in [
    r"\b(?:any|new|recent|latest|unread)\b.{0,20}\b(?:email|emails|e-?mail|mail)\b",
    r"\b(?:check|read|see|show|look at)\b.{0,20}\b(?:email|emails|e-?mail|mail|inbox)\b",
    r"\bdo i have\b.{0,30}\b(?:email|emails|mail)\b",
    r"\bwho emailed me\b",
    r"\bmy (?:\w+\s+){0,2}(?:inbox|email|emails|mail)\b",
]]


def route(name: str, text: str):
    """Return a ground-truth note to inject, or None if not a handled capability ask."""
    from . import caps, applemac
    if any(r.search(text) for r in _READ_MSG):
        if not caps.enabled(name, "imessage_read"):
            return _off("your text messages", "Messages — read recent")
        res = applemac.imessage_recent(15)
        if not res.get("ok"):
            return _failed("your text messages", res.get("error"))
        lines = [f"{'You' if i.get('who') == 'me' else i.get('who', 'unknown')}: {i.get('text','')}"
                 for i in res.get("items", [])]
        return _items("text messages", lines)
    if any(r.search(text) for r in _READ_MAIL):
        if not caps.enabled(name, "mail_read"):
            return _off("your email", "Mail — read recent")
        res = applemac.mail_recent(10)
        if not res.get("ok"):
            return _failed("your email", res.get("error"))
        return _items("emails", list(res.get("items") or []))
    return None


def _off(what: str, toggle: str) -> str:
    return (f"[capability — NOT CONNECTED: you cannot see {what}; the '{toggle}' setting "
            f"is off. In ONE honest, friendly sentence tell the user you're not set up to "
            f"do that yet and they can switch it on in settings. Don't over-apologize. "
            f"Invent nothing — no sender, message, count, or time.]")


def _failed(what: str, error) -> str:
    return (f"[capability — read FAILED ({error}). In ONE honest sentence tell the user you "
            f"couldn't access {what} and why (e.g. Full Disk Access may be needed). Don't "
            f"over-apologize. Invent nothing.]")


def _items(label: str, lines) -> str:
    lines = [ln for ln in (lines or []) if str(ln).strip()]
    if not lines:
        return (f"[capability — read OK: there are NO recent {label}. Tell the user plainly "
                f"there's nothing new. Invent nothing.]")
    body = "\n".join(f"  - {ln}" for ln in lines[:20])
    return (f"[capability — read OK. These are the user's ACTUAL recent {label}. Describe "
            f"ONLY these; add none; invent no sender, time, or wording:\n{body}\nend.]")
