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
    r"\bdid \w+ (?:text|message|dm)\b",      # "did Mom text me"
    r"\b(?:texted|messaged|dm'?d) me\b",     # received (past tense)
    r"\bmy (?:\w+\s+){0,2}(?:texts|messages|imessages)\b",
]]
_READ_MAIL = [re.compile(p, re.I) for p in [
    r"\b(?:any|new|recent|latest|unread)\b.{0,20}\b(?:email|emails|e-?mail|mail)\b",
    r"\b(?:check|read|see|show|look at)\b.{0,20}\b(?:email|emails|e-?mail|mail|inbox)\b",
    r"\bdo i have\b.{0,30}\b(?:email|emails|mail)\b",
    r"\bwho emailed me\b",
    r"\bdid \w+ (?:email|e-?mail)\b",         # "did Mom email me"
    r"\b(?:emailed|e-?mailed) me\b",
    r"\bmy (?:\w+\s+){0,2}(?:inbox|email|emails|mail)\b",
]]


def route(name: str, text: str):
    """Return {'note': str, 'send': {kind,to,body}|None} for a handled capability turn,
    else None. 'note' is injected as ground truth; 'send' (when present) asks the server
    to create a confirm-gated draft. Nothing here ever sends — only /…/send does that."""
    from . import caps, applemac
    # PRIVACY GUARD: if a cloud brain is active, never pull the user's private inbox
    # into the cloud stream — pause reading and say so plainly.
    cloud_on = False
    try:
        from . import cloud
        cloud_on = cloud.is_cloud()
    except Exception:
        cloud_on = False
    # --- READ: messages / mail (provenance — inject the REAL items) ---
    if any(r.search(text) for r in _READ_MSG):
        if cloud_on:
            return {"note": _cloud_paused("text messages")}
        if not caps.enabled(name, "imessage_read"):
            return {"note": _off("your text messages", "Messages — read recent")}
        res = applemac.imessage_recent(15)
        if not res.get("ok"):
            return {"note": _failed("your text messages", res.get("error"))}
        lines = [f"{'You' if i.get('who') == 'me' else i.get('who', 'unknown')}: {i.get('text','')}"
                 for i in res.get("items", [])]
        return {"note": _items("text messages", lines)}
    if any(r.search(text) for r in _READ_MAIL):
        if cloud_on:
            return {"note": _cloud_paused("email")}
        if not caps.enabled(name, "mail_read"):
            return {"note": _off("your email", "Mail — read recent")}
        res = applemac.mail_recent(10)
        if not res.get("ok"):
            return {"note": _failed("your email", res.get("error"))}
        return {"note": _items("emails", list(res.get("items") or []))}
    # --- SEND: a text (draft → confirm; never auto-sends) ---
    s = _parse_send(text)
    if s is not None:
        if not caps.enabled(name, "imessage"):
            return {"note": ("[capability — sending texts is OFF. In one friendly sentence "
                             "tell the user to enable 'Messages — send' in settings. Draft and "
                             "send nothing.]")}
        if not s["to"] or not s["body"]:
            return {"note": ("[capability — the user wants to send a text but didn't give both a "
                             "recipient and a message. In one friendly sentence ask for whichever "
                             "is missing. Send nothing.]")}
        return {"send": {"kind": "imessage", "to": s["to"], "body": s["body"]},
                "note": (f"[capability — a text DRAFT is ready (to: {s['to']} · message: "
                         f"\"{s['body']}\"). It is NOT sent. Warmly read it back to the user and "
                         f"ask them to confirm — tell them to tap Send or say 'send it'. Do NOT "
                         f"say it has been sent; it only sends when they confirm.]")}
    return None


# Send-intent extraction. Anchored to an imperative at the START of the turn so the
# nouns "message"/"text" mid-sentence ("I got your message", "the latest text from
# work") don't fabricate a draft. Conservative: if we can't cleanly pull a recipient
# and a body we ask rather than guess; the confirm card is the final safety net.
_LEAD = r"^\s*(?:hey[,\s]+)?(?:can you|could you|would you|please|pls|plz)?[,\s]*"
_NOTNAME = r"(?!me\b|my\b|to\b|the\b|that\b|this\b|a\b|an\b|some\b|messages?\b|texts?\b)"
_SEND = [re.compile(p, re.I) for p in [
    _LEAD + r"send (?:a |an )?(?:text|message|imessage|sms)\s+to\s+(?P<to>[\w'%.+-]+(?:\s[\w'%.+-]+){0,2}?)\s+(?:saying|that says|telling (?:them|her|him)(?: that)?|:|-)\s*(?P<body>.+)$",
    _LEAD + r"(?:text|message|imessage|sms)\s+" + _NOTNAME + r"(?P<to>[\w'%.+-]+)\s+(?:saying\s+|that says\s+|:\s*|-\s*)?(?P<body>.+)$",
    _LEAD + r"(?:text|message|imessage|sms)\s+" + _NOTNAME + r"(?P<to>[\w'%.+-]+)\s*(?P<body>)$",   # recipient only -> ask
]]


def _parse_send(text: str):
    """Return {'to','body'} if this is a send request, else None. Either field may be ''."""
    for r in _SEND:
        m = r.search(text)
        if m:
            return {"to": (m.group("to") or "").strip(" ,.:"),
                    "body": (m.group("body") or "").strip()}
    return None


def _cloud_paused(what: str) -> str:
    return (f"[capability — reading {what} is PAUSED because a cloud brain is active, so the "
            f"user's private messages stay on their Mac. In one friendly sentence tell them "
            f"you won't peek at their {what} while on the cloud brain, and they can switch back "
            f"to the Local brain in settings to read. Read or invent nothing.]")


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
