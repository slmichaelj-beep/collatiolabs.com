"""
applemac — Messages and Mail through AppleScript (osascript), Mac-only.

Sending is executed ONLY by the *_send functions here, and the server calls them ONLY
after a draft has been explicitly confirmed — there is no path that sends without that
second human action. User-supplied text (recipient, subject, body) is escaped for an
AppleScript string literal so a message body can never break out and run script.

Honesty note: iMessage *sending* via AppleScript is reliable; iMessage *reading* is
not (Apple restricts the Messages scripting dictionary), so reading falls back to the
local chat.db and needs Full Disk Access — it returns a clear reason if it can't. Mail
read and send are both via AppleScript. None of this runs or is testable off a Mac.
"""

from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import time
from pathlib import Path

_CONTACTS = {"map": None, "at": 0.0}        # cached phone/email -> name (Full Disk Access)


def _norm_phone(s: str) -> str:
    """Last 10 digits — robust to '+1 (555) 123-4567' vs '5551234567' formatting."""
    d = re.sub(r"\D", "", s or "")
    return d[-10:] if len(d) >= 10 else d


def _contacts_map() -> dict:
    """Map a normalized phone number / email -> the person's name, read from the macOS
    AddressBook (needs Full Disk Access). Cached for 5 min. Returns {} if unavailable."""
    now = time.time()
    if _CONTACTS["map"] is not None and now - _CONTACTS["at"] < 300:
        return _CONTACTS["map"]
    base = Path.home() / "Library" / "Application Support" / "AddressBook"
    dbs = list(base.glob("AddressBook-v22.abcddb")) + list(base.glob("Sources/*/AddressBook-v22.abcddb"))
    m = {}
    for db in dbs:
        try:
            con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
            names = {}
            for pk, fn, ln, org in con.execute(
                    "SELECT Z_PK, ZFIRSTNAME, ZLASTNAME, ZORGANIZATION FROM ZABCDRECORD"):
                nm = " ".join(x for x in (fn, ln) if x) or (org or "")
                if nm:
                    names[pk] = nm.strip()
            for owner, num in con.execute("SELECT ZOWNER, ZFULLNUMBER FROM ZABCDPHONENUMBER"):
                if owner in names and num:
                    m[_norm_phone(num)] = names[owner]
            for owner, addr in con.execute("SELECT ZOWNER, ZADDRESS FROM ZABCDEMAILADDRESS"):
                if owner in names and addr:
                    m[addr.lower().strip()] = names[owner]
            con.close()
        except Exception:
            continue
    _CONTACTS["map"], _CONTACTS["at"] = m, now
    return m


def _name_for(handle: str, contacts: dict) -> str:
    """Resolve a chat.db handle (phone or email) to a contact name, else the handle."""
    if not handle:
        return "unknown"
    if "@" in handle:
        return contacts.get(handle.lower().strip(), handle)
    return contacts.get(_norm_phone(handle), handle)


def _osa(script: str):
    """Run an AppleScript; return (ok, output). Never raises."""
    try:
        p = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=25)
        return (p.returncode == 0, (p.stdout or p.stderr).strip())
    except Exception as e:
        return (False, str(e))


def esc(s: str) -> str:
    """Escape a string for use inside an AppleScript double-quoted literal."""
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


# --- sending (only ever called after a confirmed draft) ---------------------

def imessage_send(to: str, body: str):
    script = (f'tell application "Messages"\n'
              f'  set svc to 1st service whose service type = iMessage\n'
              f'  set buddyTarget to buddy "{esc(to)}" of svc\n'
              f'  send "{esc(body)}" to buddyTarget\n'
              f'end tell')
    return _osa(script)


def mail_send(to: str, subject: str, body: str):
    script = (f'tell application "Mail"\n'
              f'  set msg to make new outgoing message with properties '
              f'{{subject:"{esc(subject)}", content:"{esc(body)}", visible:false}}\n'
              f'  tell msg to make new to recipient at end of to recipients '
              f'with properties {{address:"{esc(to)}"}}\n'
              f'  send msg\n'
              f'end tell')
    return _osa(script)


# --- reading -----------------------------------------------------------------

def mail_recent(limit: int = 10):
    """Most-recent inbox subjects/senders via AppleScript (no bodies, for context)."""
    n = max(1, min(int(limit), 25))
    script = (f'tell application "Mail"\n'
              f'  set out to ""\n'
              f'  set msgs to messages 1 thru (count of messages of inbox) of inbox\n'
              f'  set k to 0\n'
              f'  repeat with m in msgs\n'
              f'    if k ≥ {n} then exit repeat\n'
              f'    set out to out & (sender of m) & " | " & (subject of m) & linefeed\n'
              f'    set k to k + 1\n'
              f'  end repeat\n'
              f'  return out\n'
              f'end tell')
    ok, txt = _osa(script)
    return {"ok": ok, "items": [l for l in txt.splitlines() if l.strip()] if ok else [],
            "error": None if ok else txt}


def imessage_recent(limit: int = 10):
    """Recent messages from the local chat.db (needs Full Disk Access). Read-only."""
    db = Path.home() / "Library" / "Messages" / "chat.db"
    if not db.exists():
        return {"ok": False, "items": [], "error": "chat.db not found"}
    n = max(1, min(int(limit), 50))
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=5)
        rows = con.execute(
            "SELECT h.id, m.text, m.is_from_me FROM message m "
            "LEFT JOIN handle h ON m.handle_id = h.ROWID "
            "WHERE m.text IS NOT NULL ORDER BY m.date DESC LIMIT ?", (n,)).fetchall()
        con.close()
    except Exception as e:
        # the most common cause is missing Full Disk Access for the host process
        return {"ok": False, "items": [], "error": f"{e} (grant Full Disk Access?)"}
    contacts = _contacts_map()       # resolve phone/email -> name (so it's "Mom", not +1555…)
    items = [{"who": "me" if me else _name_for(who, contacts), "text": txt}
             for who, txt, me in rows]
    return {"ok": True, "items": items, "error": None}
