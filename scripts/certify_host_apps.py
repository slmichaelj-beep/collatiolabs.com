#!/usr/bin/env python3
"""
certify_host_apps — the Calendar / Reminders / Notes connector live path (read + confirm-gated write).

Proves the capability-truth contract for the host apps the founder asked Vera to help with, the
"mirror the Messages safety model" way: every power is OFF by default, an OFF power is provably
SILENT (the host backend is never touched), and no write EVER reaches the Mac without a second
human confirmation. Concretely, through the SAME anima.route.route() the server calls on every turn:

  A. OFF BY DEFAULT — a fresh creature's caps have all six host flags False (calendar/reminders/
     notes × read/write). The Settings toggles render from exactly this ledger.
  B. OFF IS SILENT — with the flags OFF, a read ("what are my reminders?") returns the honest
     "it's off" message and NEVER calls anima.host_access (a tripwire raises on any backend call);
     a write ("remind me to …") returns the honest off-message, sets NO pending draft, and likewise
     never touches the backend. Nothing is read, drafted, or written.
  C. THE LEDGER IS DURABLE + ISOLATED — caps.save({reminders_read:True}) then caps.load() returns
     reminders_read True and EVERY OTHER host flag still False (turning on "read reminders" never
     silently enables note-writing). With it ON, the read now reaches the real backend.
  D. WRITE IS CONFIRM-GATED — with the write flag ON, a write request PREPARES a draft (a pending
     draft is stored) and executes NOTHING; an explicit "yes" executes the create EXACTLY once; a
     clear "no" cancels and writes nothing. This is the host-app twin of the message draft→confirm→send.
  E. NOTES READ IS TITLES-ONLY — the notes-list read path calls host_access.list_notes (titles), and
     a note-BODY read ("read my note about X") is refused while notes_read is OFF (no read_note call).

Hermetic + offline: every store (incl. caps) is redirected to a temp dir (gate0_prime_experience.
_temp_store), and anima.host_access is tripwired so NO osascript/EventKit ever runs — zero real reads,
zero real writes, no Mac side effects. The real .anima is fingerprinted before/after and asserted
byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store
_footprint = _g0pe._footprint

_HOST_FLAGS = ("calendar_read", "calendar", "reminders_read", "reminders", "notes_read", "notes")
_BACKEND_FNS = ("list_events", "list_reminders", "list_notes", "read_note",
                "create_reminder", "create_event", "create_note", "append_to_note",
                "complete_reminder")


def _install_tripwire(host_access, log: list):
    """Replace every host_access entrypoint with a recorder that returns a benign FAKE (never the
    real osascript/EventKit). Returns the saved originals so the caller can restore them."""
    saved = {fn: getattr(host_access, fn) for fn in _BACKEND_FNS}

    def _mk(fn):
        def f(*a, **k):
            log.append(fn)
            return {"ok": True, "reminders": [], "notes": [], "events": [], "items": [],
                    "title": (a[0] if a else k.get("title", "?")), "note": "ok",
                    "body": "", "reason": "ok"}
        return f
    for fn in _BACKEND_FNS:
        setattr(host_access, fn, _mk(fn))
    return saved


def main() -> int:
    from anima import route, caps, host_access
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("HOST APPS — Calendar / Reminders / Notes connector (read + confirm-gated write)")
    print("=" * 78)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    log = []
    saved = _install_tripwire(host_access, log)
    try:
        with _temp_store():
            N = "HostAppsCert"
            route._pending_clear(N)

            # ---- A. OFF BY DEFAULT -------------------------------------------------------
            c = caps.load(N)
            ck("A1: a fresh creature has ALL SIX host flags OFF by default",
               all(c.get(k) is False for k in _HOST_FLAGS))

            # ---- B. OFF IS SILENT (read + write) -----------------------------------------
            log.clear()
            r = route.route(N, "what are my reminders?")
            note = (r or {}).get("note", "")
            ck("B1: OFF reminders READ -> honest off-message (off + settings)",
               "NOT CONNECTED" in note and "off" in note.lower() and "settings" in note.lower())
            ck("B2: OFF reminders READ never touched the host backend", not log)

            log.clear()
            r = route.route(N, "what notes do I have?")
            ck("B3: OFF notes READ -> off-message, backend untouched",
               "NOT CONNECTED" in (r or {}).get("note", "") and not log)

            log.clear()
            r = route.route(N, "what's on my calendar today?")
            ck("B4: OFF calendar READ -> off-message, backend untouched",
               "NOT CONNECTED" in (r or {}).get("note", "") and not log)

            log.clear()
            r = route.route(N, "remind me to call the dentist tomorrow at 3pm")
            note = (r or {}).get("note", "")
            ck("B5: OFF reminder WRITE -> off-message, NO draft prepared",
               "add to your reminders" in note.lower() and route._pending_get(N) is None)
            ck("B6: OFF reminder WRITE never touched the backend (drafted nothing)", not log)

            log.clear()
            r = route.route(N, "make a note that I parked on level 3")
            ck("B7: OFF note WRITE -> off-message, no draft, backend untouched",
               "add to your notes" in (r or {}).get("note", "").lower()
               and route._pending_get(N) is None and not log)

            log.clear()
            r = route.route(N, "add lunch with Sam to my calendar tomorrow at noon")
            ck("B8: OFF event WRITE -> off-message, no draft, backend untouched",
               "add to your calendar" in (r or {}).get("note", "").lower()
               and route._pending_get(N) is None and not log)

            # ---- C. LEDGER IS DURABLE + ISOLATED -----------------------------------------
            caps.save(N, {"reminders_read": True})
            c2 = caps.load(N)
            ck("C1: caps.save({reminders_read}) is DURABLE on reload", c2.get("reminders_read") is True)
            ck("C2: turning on ONE read leaves every other host flag OFF (no silent widening)",
               all(c2.get(k) is False for k in _HOST_FLAGS if k != "reminders_read"))
            log.clear()
            r = route.route(N, "what are my reminders?")
            ck("C3: with reminders_read ON, the READ reaches the REAL backend (list_reminders)",
               "list_reminders" in log)

            # notes body read stays refused while notes_read is OFF (read flags are independent)
            log.clear()
            r = route.route(N, "read my note about groceries")
            ck("C4: notes_read still OFF -> a note-BODY read is refused (no read_note call)",
               "NOT CONNECTED" in (r or {}).get("note", "") and "read_note" not in log)

            # ---- D. WRITE IS CONFIRM-GATED -----------------------------------------------
            caps.save(N, {"reminders_read": True, "reminders": True, "notes": True, "calendar": True})
            route._pending_clear(N)
            log.clear()
            r = route.route(N, "remind me to water the plants tomorrow at 9am")
            ck("D1: write ON -> a DRAFT is prepared (nothing executed yet)",
               "DRAFT" in (r or {}).get("note", "") and route._pending_get(N) is not None and not log)
            r2 = route.route(N, "yes do it")
            ck("D2: explicit 'yes' EXECUTES the create exactly once, then clears the draft",
               log == ["create_reminder"] and route._pending_get(N) is None)

            log.clear()
            route.route(N, "add a coffee chat to my calendar tomorrow at 2pm")
            ck("D3: a fresh write re-arms a pending draft", route._pending_get(N) is not None)
            rd = route.route(N, "no, cancel that")
            ck("D4: a clear 'no' CANCELS and writes nothing",
               not log and route._pending_get(N) is None
               and "CANCEL" in (rd or {}).get("note", "").upper())

            # ---- E. NOTES READ IS TITLES-ONLY --------------------------------------------
            caps.save(N, {"notes_read": True})
            log.clear()
            r = route.route(N, "what notes do I have?")
            ck("E1: notes LIST read uses the titles-only path (list_notes), never a body read",
               "list_notes" in log and "read_note" not in log)
    finally:
        for fn, orig in saved.items():
            setattr(host_access, fn, orig)

    # ---- HERMETICITY: the real .anima was never read or written ----------------------
    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nHOST-APPS CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
