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

Host apps (Calendar / Reminders / Notes — anima.host_access)
------------------------------------------------------------
The same two shapes extend to the Mac's own apps:

  * READS ("what's on my calendar", "any reminders", "read my note about X") fetch
    REAL data from host_access and return it as a ground-truth note the mouth narrates
    — exactly like the weather/inbox read path. Their CONTENTS are personal, so the
    cloud privacy guard pauses them while a cloud brain is active.
  * WRITES (remind me to…, add … to my calendar, make a note that…, mark … done) are
    CONFIRM-GATED. A write request does NOT execute; it prepares a draft, narrates it,
    and asks the user to confirm. Only the NEXT turn — an explicit "yes / do it /
    confirm" — runs the host_access executor. This mirrors the message/mail
    draft→confirm→send gate: nothing mutates the Mac without a second human action.
    The pending draft is held per-creature in this module (one at a time) and expires.
"""

from __future__ import annotations

import re
import time

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

# --- host apps: Calendar / Reminders / Notes (read cues) ---------------------------
# Broad on purpose, same as above: a false positive truthfully fetches and finds
# nothing; a false negative is the fabrication we are eliminating.
_READ_CAL = [re.compile(p, re.I) for p in [
    r"\bwhat'?s\b.{0,20}\b(?:on|in)\b.{0,12}\b(?:my\b.{0,8})?(?:calendar|schedule|agenda)\b",
    r"\b(?:check|see|show|look at|read|pull up)\b.{0,16}\b(?:my\b.{0,8})?(?:calendar|schedule|agenda)\b",
    r"\bwhat\b.{0,24}\b(?:do i have|have i got|is)\b.{0,20}\b(?:today|tomorrow|this week|scheduled|planned)\b",
    r"\bwhat'?s\b.{0,16}\b(?:happening|going on|coming up)\b.{0,16}\b(?:today|tomorrow|this week)\b",
    r"\b(?:any|got any|do i have)\b.{0,16}\b(?:events|meetings|appointments)\b",
    r"\bmy (?:\w+\s+){0,2}(?:events|meetings|appointments|schedule)\b",
]]
_READ_REM = [re.compile(p, re.I) for p in [
    r"\b(?:any|got any|do i have|check|see|show|read|list)\b.{0,20}\b(?:reminders?|to-?dos?|tasks?)\b",
    r"\bwhat'?s\b.{0,16}\b(?:on\b.{0,8})?(?:my\b.{0,8})?(?:reminders?|to-?do(?:\s?list)?|task list)\b",
    r"\bwhat\b.{0,20}\b(?:do i (?:need|have) to do)\b",
    r"\bmy (?:\w+\s+){0,2}(?:reminders?|to-?dos?|tasks?)\b",
]]
# Notes READ: only the specific "read/open my note about/titled X" — generic "make a note"
# is a WRITE handled below. We capture the note's subject/title for an exact lookup.
_READ_NOTE = [re.compile(p, re.I) for p in [
    r"\b(?:read|open|show|pull up|find|get)\b.{0,12}\bmy?\s*note\b\s*(?:about|on|titled|called|named|for|:)\s+(?P<q>.+)$",
    r"\bwhat(?:'?s| is| does it say)\b.{0,16}\bmy?\s*note\b\s*(?:about|on|titled|called|named|for|:)\s+(?P<q>.+)$",
]]
_LIST_NOTES = [re.compile(p, re.I) for p in [
    r"\b(?:list|show|what are)\b.{0,16}\bmy\s+notes\b",
    r"\bwhat notes\b.{0,16}\bdo i have\b",
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
    # --- CONFIRM-GATE (host writes): if a host-app write draft is pending for this
    # creature, a clear yes/no here is the second human action. "Yes" EXECUTES the
    # stored draft; "no"/anything-else cancels it. This is the host-app mirror of the
    # message/mail draft→confirm→send gate, kept entirely in code so the guarantee
    # holds with any mouth: nothing mutates the Mac without this explicit confirm. ---
    if _pending_get(name) is not None:
        if _is_confirm(text):
            return {"note": _host_execute(name)}
        if _is_decline(text):
            _pending_clear(name)
            return {"note": ("[capability — the user CANCELLED the pending change to their "
                             "Mac; nothing was written. In one warm sentence acknowledge you "
                             "didn't do it. Invent nothing.]")}
        # Neither a clear yes nor no: let the pending draft stand (it expires on its own)
        # and fall through so an unrelated turn is handled normally.
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
    # --- READ: host apps (Calendar / Reminders / Notes — REAL data, mouth narrates) ---
    # Two guards, in order: (1) the cloud privacy guard pauses them (their contents are
    # personal, same as the inbox); (2) each is OFF until its read switch is on — the
    # host-app mirror of the Messages/Mail read gate, so nothing is read by default.
    if any(r.search(text) for r in _READ_CAL):
        if cloud_on:
            return {"note": _cloud_paused("calendar")}
        if not caps.enabled(name, "calendar_read"):
            return {"note": _off("your calendar", "Calendar — read")}
        return {"note": _host_read("calendar", text)}
    if any(r.search(text) for r in _READ_REM):
        if cloud_on:
            return {"note": _cloud_paused("reminders")}
        if not caps.enabled(name, "reminders_read"):
            return {"note": _off("your reminders", "Reminders — read")}
        return {"note": _host_read("reminders", text)}
    nq = _note_query(text)
    if nq is not None:
        if cloud_on:
            return {"note": _cloud_paused("notes")}
        if not caps.enabled(name, "notes_read"):
            return {"note": _off("your notes", "Notes — read")}
        return {"note": _host_read("note", text, nq)}
    if any(r.search(text) for r in _LIST_NOTES):
        if cloud_on:
            return {"note": _cloud_paused("notes")}
        if not caps.enabled(name, "notes_read"):
            return {"note": _off("your notes", "Notes — read")}
        return {"note": _host_read("notes", text)}
    # --- WRITE: host apps (prepare a CONFIRM-GATED draft; executes NOTHING now) ---
    # The write switch (default-OFF) gates DRAFTING; the draft→confirm gate above is then
    # the second, non-bypassable human action — exactly the Messages send model: a power
    # that's OFF can't even draft, and a power that's ON still never writes without a 'yes'.
    w = _parse_host_write(text)
    if w is not None:
        _wcap = _WRITE_CAP.get(w["action"], "")
        if _wcap and not caps.enabled(name, _wcap):
            return {"note": _off_write(_HOST_WHAT.get(w["action"], "your Mac"),
                                       _HOST_TOGGLE.get(w["action"], "host-app writing"))}
        return {"note": _host_prepare(name, w)}
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


def _off_write(what: str, toggle: str) -> str:
    """The write-side mirror of _off: the host-app WRITE switch is off, so we don't even draft."""
    return (f"[capability — NOT CONNECTED: you cannot add to {what}; the '{toggle}' setting "
            f"is off. In ONE honest, friendly sentence tell the user you're not set up to do "
            f"that yet and they can switch it on in settings. Don't over-apologize. Create, "
            f"write, and draft NOTHING — and do NOT ask them to confirm anything.]")


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


# ════════════════════════════════════════════════════════════════════════════════════
# HOST APPS — Calendar / Reminders / Notes (read + confirm-gated write)
# These wrap anima.host_access. READS inject real data; WRITES are draft→confirm→execute.
# ════════════════════════════════════════════════════════════════════════════════════

def _note_query(text: str):
    """If the turn is a 'read my note about X' request, return X (the title/subject), else None."""
    for r in _READ_NOTE:
        m = r.search(text)
        if m:
            return (m.group("q") or "").strip(" ?.\"'")
    return None


# --- WRITE intent parsing. Anchored at the START of the turn (an imperative), like the
# send parser, so a mid-sentence noun ("I made a note of that yesterday") can't fabricate
# a write. Each parser returns a dict with an 'action' the executor dispatches on. The
# confirm card (the SECOND turn) is always the final safety net. ----------------------
_REMIND = [re.compile(p, re.I) for p in [
    _LEAD + r"remind me\s+(?:to\s+)?(?P<body>.+?)(?:\s+(?P<when>(?:at|on|by|tomorrow|today|tonight|next|in)\b.*))?$",
    _LEAD + r"(?:add|set|make|create)\s+(?:a\s+)?reminder\s+(?:to\s+|that\s+|for\s+)?(?P<body>.+?)(?:\s+(?P<when>(?:at|on|by|tomorrow|today|tonight|next|in)\b.*))?$",
    _LEAD + r"(?:add|put)\s+(?P<body>.+?)\s+(?:to|on)\s+my\s+(?:reminders?|to-?do(?:\s?list)?|task list)\b.*$",
]]
_ADD_EVENT = [re.compile(p, re.I) for p in [
    _LEAD + r"(?:add|put|schedule|create|set up|book)\s+(?P<body>.+?)\s+(?:to|on|in)\s+my\s+calendar(?:\s+(?P<when>(?:at|on|for|tomorrow|today|tonight|next|this)\b.*))?$",
    _LEAD + r"(?:schedule|book|set up)\s+(?:a\s+|an\s+)?(?P<body>.+?)(?:\s+(?P<when>(?:at|on|for|tomorrow|today|tonight|next|this)\b.*))?$",
    _LEAD + r"(?:add|create|put)\s+(?:an?\s+)?(?:event|appointment|meeting)\s+(?:called\s+|named\s+|for\s+|:\s*)?(?P<body>.+?)(?:\s+(?P<when>(?:at|on|tomorrow|today|tonight|next|this)\b.*))?$",
]]
# Notes WRITE: "make a note that/about/saying X", "add X to my note(s)" → append vs create.
_APPEND_NOTE = [re.compile(p, re.I) for p in [
    _LEAD + r"(?:add|append|jot)\s+(?P<text>.+?)\s+to\s+(?:my\s+)?note\s+(?:about|on|titled|called|named|:)\s+(?P<title>.+)$",
]]
_MAKE_NOTE = [re.compile(p, re.I) for p in [
    _LEAD + r"(?:make|create|add|write|take|start|jot)\s+(?:me\s+)?(?:a\s+|an\s+)?(?:new\s+)?note\s+(?:that says|saying|that|about|titled|called|named|:|-)\s*(?P<body>.+)$",
    _LEAD + r"note\s+(?:that|down)\s+(?P<body>.+)$",
]]
_COMPLETE = [re.compile(p, re.I) for p in [
    _LEAD + r"(?:mark|check off|check|tick off|tick)\s+(?:the\s+|my\s+)?(?:reminder\s+)?(?:to\s+)?(?P<title>.+?)\s+(?:as\s+)?(?:done|complete|completed|finished|off)\b.*$",
    _LEAD + r"(?:complete|finish|cross off|close out)\s+(?:the\s+|my\s+)?(?:reminder\s+)?(?:to\s+)?(?P<title>.+)$",
    _LEAD + r"i\s+(?:did|finished|completed|already did)\s+(?P<title>.+)$",
]]


def _parse_host_write(text: str):
    """Detect a host-app WRITE and return a draft spec, else None.

    Returns one of:
        {"action":"create_reminder", "title":str, "when":str|None}
        {"action":"create_event",    "title":str, "when":str|None}
        {"action":"create_note",     "title":str, "body":str}
        {"action":"append_to_note",  "title":str, "text":str}
        {"action":"complete_reminder","title":str}
    Order matters: more specific patterns (append, complete) are tried before the
    broad create patterns, and calendar before the catch-all 'schedule'.
    """
    for r in _APPEND_NOTE:                       # "add X to my note about Y"
        m = r.search(text)
        if m:
            return {"action": "append_to_note",
                    "title": (m.group("title") or "").strip(" .\"'"),
                    "text": (m.group("text") or "").strip()}
    for r in _ADD_EVENT:                         # calendar before the generic reminder/schedule
        m = r.search(text)
        if m and (m.group("body") or "").strip():
            return {"action": "create_event",
                    "title": (m.group("body") or "").strip(" .\"'"),
                    "when": (m.groupdict().get("when") or None)}
    for r in _COMPLETE:                          # "mark … done"
        m = r.search(text)
        if m and (m.group("title") or "").strip():
            return {"action": "complete_reminder",
                    "title": (m.group("title") or "").strip(" .\"'")}
    for r in _REMIND:                            # "remind me to …"
        m = r.search(text)
        if m and (m.group("body") or "").strip():
            return {"action": "create_reminder",
                    "title": (m.group("body") or "").strip(" .\"'"),
                    "when": (m.groupdict().get("when") or None)}
    for r in _MAKE_NOTE:                         # "make a note that …"
        m = r.search(text)
        if m and (m.group("body") or "").strip():
            body = (m.group("body") or "").strip()
            title = body.split("\n", 1)[0][:60].strip()    # first line/clause as the title
            return {"action": "create_note", "title": title, "body": body}
    return None


# --- a tiny, HONEST natural-time helper: parse only the unambiguous phrasings; if a
# time can't be parsed we DON'T guess — the reminder/event is created without a due/
# default-hour and we say so. Returns epoch seconds or None. ----------------------------
_TIME_AT = re.compile(r"\bat\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.I)


def _parse_when(phrase: str):
    """Best-effort epoch from a 'when' phrase. Conservative: None when unsure (no fabrication)."""
    if not phrase:
        return None
    p = phrase.lower()
    base = time.localtime()
    y, mo, d = base.tm_year, base.tm_mon, base.tm_mday
    day_epoch = time.mktime((y, mo, d, 0, 0, 0, 0, 0, -1))
    if "tomorrow" in p:
        day_epoch += 86400
    elif "tonight" in p:
        pass                                     # today, evening (hour set below if given)
    elif "today" in p:
        pass
    elif re.search(r"\bin\s+(\d+)\s+day", p):
        day_epoch += 86400 * int(re.search(r"\bin\s+(\d+)\s+day", p).group(1))
    elif "next week" in p:
        day_epoch += 7 * 86400
    # time-of-day
    hh, mm = None, 0
    m = _TIME_AT.search(p)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2) or 0)
        ap = (m.group(3) or "").lower()
        if ap == "pm" and hh < 12:
            hh += 12
        elif ap == "am" and hh == 12:
            hh = 0
        elif not ap and "tonight" in p and hh < 12:
            hh += 12                             # "tonight at 8" -> 20:00
    elif "tonight" in p:
        hh = 19                                  # a sane, stated default only for 'tonight'
    if hh is None:
        # a bare day with no clock — leave it dateless rather than invent an hour, UNLESS
        # the user clearly named a day (then anchor at 9am so it actually schedules).
        if any(k in p for k in ("tomorrow", "today", "next week")) or re.search(r"\bin\s+\d+\s+day", p):
            hh = 9
        else:
            return None
    lt = time.localtime(day_epoch)
    return time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, hh, mm, 0, 0, 0, -1))


# --- per-creature pending host-write draft (one at a time). Held in-process like the
# server's _DRAFTS; expires after an hour so a forgotten draft can't linger. This is the
# confirm-gate's memory: prepared on turn 1, executed only on an explicit yes on turn 2.
_HOST_PENDING = {}          # name -> {spec, ts}
_PENDING_TTL = 3600.0


def _pending_get(name):
    rec = _HOST_PENDING.get(name)
    if rec and (time.time() - rec["ts"]) <= _PENDING_TTL:
        return rec["spec"]
    if rec:
        _HOST_PENDING.pop(name, None)            # expired
    return None


def _pending_set(name, spec):
    _HOST_PENDING[name] = {"spec": spec, "ts": time.time()}


def _pending_clear(name):
    _HOST_PENDING.pop(name, None)


# Confirm / decline detection — deliberately tight so an ambiguous reply doesn't trigger
# a write. The turn must START with a clearly-affirmative / clearly-negative cue (trailing
# words like "yes do it", "no don't" are fine); a mid-sentence "yes" doesn't count. Decline
# is checked FIRST so "no, go ahead and cancel" can't be misread as a confirm.
_CONFIRM = re.compile(
    r"^\s*(?:yes|yeah|yep|yup|do it|send it|confirm(?:ed)?|go ahead|please do|"
    r"sounds good|that'?s right|correct|ok(?:ay)?|sure|go for it|make it so|"
    r"add it|create it|save it|please)\b", re.I)
_DECLINE = re.compile(
    r"^\s*(?:no|nope|nah|don'?t|do not|cancel|stop|never\s?mind|nevermind|forget it|"
    r"not now|wait|hold on)\b", re.I)


def _is_confirm(text: str) -> bool:
    t = text or ""
    return bool(_CONFIRM.match(t)) and not _is_decline(t)


def _is_decline(text: str) -> bool:
    return bool(_DECLINE.match(text or ""))


def _host_read(kind: str, text: str, query: str = "") -> str:
    """Fetch REAL host-app data and return a ground-truth note (or honest no_access/empty)."""
    from . import host_access
    if kind == "calendar":
        within = 7 if re.search(r"\b(week|7 day|upcoming|coming up)\b", text, re.I) else \
                 (2 if re.search(r"\btomorrow\b", text, re.I) else 1)
        res = host_access.list_events(within_days=within)
        if not res.get("ok"):
            return _host_unavailable("calendar", res)
        lines = [f"{e['title']} ({e['when']})" if e.get("when") else e["title"]
                 for e in res.get("events", [])]
        return _items("calendar events", lines)
    if kind == "reminders":
        res = host_access.list_reminders()
        if not res.get("ok"):
            return _host_unavailable("reminders", res)
        lines = [r["title"] + (f" — due {r['due']}" if r.get("due") else "")
                 for r in res.get("reminders", [])]
        return _items("reminders", lines)
    if kind == "note":
        res = host_access.read_note(query)
        if not res.get("ok"):
            if res.get("reason") == "no_access":
                return _host_unavailable("notes", res)
            if res.get("reason") == "not_found":
                return (f"[capability — read OK: there is NO note titled '{query}'. Tell the "
                        f"user plainly you couldn't find that note. Invent nothing.]")
            return _host_unavailable("notes", res)
        body = (res.get("body") or "").strip()
        return (f"[capability — read OK. This is the user's ACTUAL note titled "
                f"'{res.get('title')}'. Relay/summarize ONLY this content; add nothing, "
                f"invent nothing:\n{body[:2000]}\nend.]")
    if kind == "notes":
        res = host_access.list_notes()
        if not res.get("ok"):
            return _host_unavailable("notes", res)
        return _items("note titles", [n["title"] for n in res.get("notes", [])])
    return _host_unavailable(kind, {"reason": "error", "message": "unknown read"})


def _host_unavailable(what: str, res: dict) -> str:
    """Honest note for a host read that couldn't run (TCC denial or other failure)."""
    if res.get("reason") == "no_access":
        msg = res.get("message", "")
        return (f"[capability — NO ACCESS to {what}: {msg} In ONE honest, friendly sentence "
                f"tell the user you can't see their {what} yet and exactly where to grant it. "
                f"Don't over-apologize. Invent nothing.]")
    return _failed(f"your {what}", res.get("message") or res.get("reason"))


# Human-readable label + the host_access executor for each write action.
_ACTION_LABEL = {
    "create_reminder": "a new reminder",
    "create_event": "a new calendar event",
    "create_note": "a new note",
    "append_to_note": "an addition to a note",
    "complete_reminder": "marking a reminder done",
}

# Each host-WRITE action → the default-OFF capability that must be ON to even DRAFT it,
# plus the human phrasing for the honest "it's off" reply. Calendar/Reminders/Notes each
# gate independently, so turning on "add a reminder" never silently enables note-writing.
_WRITE_CAP = {
    "create_reminder": "reminders", "complete_reminder": "reminders",
    "create_event": "calendar",
    "create_note": "notes", "append_to_note": "notes",
}
_HOST_WHAT = {
    "create_reminder": "your reminders", "complete_reminder": "your reminders",
    "create_event": "your calendar",
    "create_note": "your notes", "append_to_note": "your notes",
}
_HOST_TOGGLE = {
    "create_reminder": "Reminders — add", "complete_reminder": "Reminders — add",
    "create_event": "Calendar — add",
    "create_note": "Notes — add", "append_to_note": "Notes — add",
}


def _draft_describe(spec: dict) -> str:
    """A short, honest plain-text description of exactly what WILL happen on confirm."""
    a = spec["action"]
    if a == "create_reminder":
        w = spec.get("_when_text")
        return f"reminder: \"{spec['title']}\"" + (f" (due {w})" if w else " (no due time)")
    if a == "create_event":
        w = spec.get("_when_text")
        return f"calendar event: \"{spec['title']}\"" + (f" at {w}" if w else " (no time set yet)")
    if a == "create_note":
        return f"note titled \"{spec['title']}\""
    if a == "append_to_note":
        return f"append \"{spec['text']}\" to the note \"{spec['title']}\""
    if a == "complete_reminder":
        return f"mark the reminder \"{spec['title']}\" as done"
    return "a change to your Mac"


def _host_prepare(name: str, spec: dict) -> str:
    """Prepare (DO NOT execute) a host-write draft, store it, and narrate it for confirm."""
    # Resolve a 'when' phrase to an epoch now, so the confirm card shows the real time and
    # the executor doesn't re-parse. Honest: if it couldn't be parsed, there's just no time.
    if spec.get("when"):
        ep = _parse_when(spec["when"])
        spec["_when_epoch"] = ep
        spec["_when_text"] = (time.strftime("%a %b %-d, %-I:%M %p", time.localtime(ep))
                              if ep else None)
    _pending_set(name, spec)
    desc = _draft_describe(spec)
    return (f"[capability — a DRAFT is ready and NOTHING has been written to the Mac yet: "
            f"{desc}. Warmly read this back to the user and ask them to confirm — tell them "
            f"to say 'yes' / 'do it' to go ahead, or 'no' to cancel. Do NOT say it's done; "
            f"it only happens when they confirm.]")


def _host_execute(name: str) -> str:
    """Execute the pending host-write draft (the post-confirm act) and return a truth note."""
    from . import host_access
    spec = _pending_get(name)
    _pending_clear(name)                         # consume it regardless of outcome
    if spec is None:
        return ("[capability — there was no pending change to confirm. Say so plainly; do "
                "nothing. Invent nothing.]")
    a = spec["action"]
    try:
        if a == "create_reminder":
            res = host_access.create_reminder(spec["title"], due=spec.get("_when_epoch"))
        elif a == "create_event":
            start = spec.get("_when_epoch")
            if start is None:
                # No usable time was given — don't invent one; ask instead of guessing.
                return ("[capability — could NOT create the event: no clear date/time was "
                        "given. In one friendly sentence ask the user what day and time they "
                        "want it. Create nothing; invent nothing.]")
            res = host_access.create_event(spec["title"], start=start)
        elif a == "create_note":
            res = host_access.create_note(spec["title"], body=spec.get("body", ""))
        elif a == "append_to_note":
            res = host_access.append_to_note(spec["title"], spec.get("text", ""))
        elif a == "complete_reminder":
            res = host_access.complete_reminder(spec["title"])
        else:
            return "[capability — unknown action; did nothing. Invent nothing.]"
    except Exception as e:                        # never crash a turn on a host hiccup
        return _failed(f"the {_ACTION_LABEL.get(a, 'change')}", str(e))

    if res.get("ok"):
        return (f"[capability — DONE for real: created/updated {_ACTION_LABEL.get(a, 'the item')} "
                f"({_draft_describe(spec)}). Confirm to the user warmly and briefly that it's "
                f"saved. State ONLY what was done; invent no extra detail.]")
    if res.get("reason") == "no_access":
        return (f"[capability — could NOT do it: {res.get('message','')} In ONE honest sentence "
                f"tell the user you don't have access yet and exactly where to grant it. Nothing "
                f"was written. Invent nothing.]")
    if res.get("reason") == "not_found":
        return (f"[capability — could NOT do it: {res.get('message','')} Say so plainly; nothing "
                f"was changed. Invent nothing.]")
    return _failed(f"the {_ACTION_LABEL.get(a, 'change')}", res.get("message") or res.get("reason"))
