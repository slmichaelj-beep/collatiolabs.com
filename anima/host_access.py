"""
host_access — Vera reads AND writes the host Mac's Calendar, Reminders, and Notes.

This is the on-device bridge to the three personal apps the user asked Vera to help
with. It follows the same laws as the rest of anima:

  * local-first & private: everything here is on-device (osascript / EventKit). NONE
    of it is ever an outbound network call. The CONTENTS of calendars, reminders and
    notes are personal, so — exactly like the Portrait memory and the inbox — they are
    PAUSED whenever a cloud brain is active (see route.py's privacy guard). They never
    enter a cloud stream.
  * honest degradation: every function returns a typed dict with an `ok` flag. On a
    macOS TCC permission denial it returns, never crashes and never fakes success:
        {"ok": False, "reason": "no_access",
         "message": "I don't have access to your Reminders yet — you can grant it in "
                    "System Settings > Privacy & Security > Reminders"}
    Other failures return {"ok": False, "reason": "error"/"not_found"/..., "message": ...}.
  * write = confirm-gated: the functions here that MUTATE (create_event, create_reminder,
    complete_reminder, create_note, append_to_note) are the *executors*. They are only
    ever called AFTER an explicit user confirmation — route.py prepares a draft, narrates
    it, and runs the executor only when the user confirms on the next turn. Nothing here
    writes on its own; calling an executor directly is the deliberate, post-confirm act
    (mirroring applemac's imessage_send / mail_send).

Calendar reads reuse anima.context_gather (already a robust ~17-calendar reader) — this
module does NOT duplicate that logic.

Implementation strategy (matches what the machine actually has):
  * EventKit via PyObjC is PREFERRED for Calendar + Reminders *if* it imports AND access
    is authorized — but it is optional. When EventKit isn't importable (the Guruu venv
    ships Foundation/objc but not EventKit) or isn't authorized, we fall back to
    AppleScript (osascript), which is reliable on macOS for all three apps.
  * Notes has no EventKit API → AppleScript only.

────────────────────────────────────────────────────────────────────────────────────
ONE-TIME PERMISSION GRANTS (macOS TCC) — do these once, then Vera can read+write:

  1. Calendars  — System Settings > Privacy & Security > Calendars  → enable the host
                   process (your Terminal, or the Python that runs the server).
  2. Reminders  — System Settings > Privacy & Security > Reminders   → enable it there.
  3. Notes      — Notes has no dedicated pane. The FIRST time Vera scripts Notes, macOS
                   shows an "… wants to control Notes" prompt → click OK. After that it
                   lives under System Settings > Privacy & Security > Automation, where
                   the host process must have "Notes" checked. (Calendar/Reminders via
                   the AppleScript fallback appear under Automation too; the EventKit path
                   uses the Calendars/Reminders panes above instead.)

  macOS attributes the grant to the PROCESS that asks. If you run the server from
  Terminal, grant Terminal. If you bundle it, grant the bundle. After a grant you may
  need to restart the server process once for the new permission to take effect.

  Run `python3 -m anima.host_access --selftest` to see, per app, whether access is live
  (it reads read-only and DRY-RUNS every write — it creates nothing).
────────────────────────────────────────────────────────────────────────────────────

CLI:
    python3 -m anima.host_access --selftest          # safe: reads + dry-runs writes
    python3 -m anima.host_access --calendar 7         # list events in the next 7 days
    python3 -m anima.host_access --reminders          # list reminders
    python3 -m anima.host_access --notes              # list note titles
"""

from __future__ import annotations

import subprocess
import time
from typing import Optional

from . import context_gather

# ── EventKit is optional. Probe ONCE at import; never let a missing module crash. ──
# We only treat EventKit as usable if it imports. Whether it's *authorized* is decided
# per call (a denied/undetermined status falls back to AppleScript, which surfaces the
# same honest no_access if it too is blocked).
try:                                            # pragma: no cover - host-dependent
    import EventKit  # type: ignore
    _HAVE_EVENTKIT = True
except Exception:
    EventKit = None                             # type: ignore
    _HAVE_EVENTKIT = False


# ── shared helpers ──────────────────────────────────────────────────────────────────

# AppleScript field/record separators we choose ourselves, so a title/body containing
# commas or quotes can never break the row format we parse back (same trick as
# context_gather's calendar reader).
_RS = "\x1e"          # between records
_US = "\x1f"          # between fields within a record

# Substrings that mark a macOS TCC permission denial in an osascript stderr line, so we
# can answer "no_access" honestly instead of a generic error. (-1743 = not authorized.)
_DENIED_MARKERS = ("not authorized", "-1743", "1743", "not allowed", "permission",
                   "doesn't have permission", "is not allowed", "access")


def _no_access(app: str, pane: str) -> dict:
    """The single, honest 'I can't get in yet' result — identical shape for every app."""
    return {"ok": False, "reason": "no_access",
            "message": (f"I don't have access to your {app} yet — you can grant it in "
                        f"System Settings > Privacy & Security > {pane}")}


def _looks_denied(err: str) -> bool:
    low = (err or "").lower()
    return any(m in low for m in _DENIED_MARKERS)


def esc(s: str) -> str:
    """Escape a string for use inside an AppleScript double-quoted literal."""
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


def _osa(script: str, timeout: float = 25.0):
    """Run an AppleScript; return (ok, output_or_error). Never raises.

    Mirrors applemac._osa / context_gather._run_osa so behaviour and the way
    Automation/TCC denials surface stay consistent across the codebase.
    """
    try:
        p = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=timeout)
        return (p.returncode == 0,
                (p.stdout if p.returncode == 0 else p.stderr).strip())
    except FileNotFoundError:
        return (False, "osascript not found (not a Mac?)")
    except subprocess.TimeoutExpired:
        return (False, "timed out")
    except Exception as e:
        return (False, str(e))


def _rows(out: str):
    """Split an osascript blob emitted with our RS/US separators into a list of field-lists."""
    return [r.split(_US) for r in (out or "").split(_RS) if r.strip()]


# ══════════════════════════════════════════════════════════════════════════════════
# CALENDAR
# ══════════════════════════════════════════════════════════════════════════════════

def list_events(within_days: int = 1) -> dict:
    """Read upcoming Calendar.app events. Reuses anima.context_gather (no duplication).

    `within_days` is a forward window from now (1 = today). context_gather currently
    scans *today*; for a wider window we ask it per-day and merge, so we never re-implement
    its robust, locale-independent, ~17-calendar parsing.

    Returns:
        {"ok": True, "events": [{"title","when","start","all_day"}...], "note": str}
      or, on a calendar that can't be read (Automation/Calendars denied, timeout, skipped):
        {"ok": False, "reason": "no_access"|"unavailable", "message": str}
    """
    try:
        within_days = max(1, int(within_days))
    except (TypeError, ValueError):
        within_days = 1

    cal = context_gather.calendar_today()       # today's events, robustly parsed
    if not cal.ok:
        # context_gather already crafts an honest note; map a permission flavour to no_access.
        note = cal.note or "calendar unavailable"
        if _looks_denied(note):
            return _no_access("Calendar", "Calendars")
        return {"ok": False, "reason": "unavailable", "message": note}

    events = [{"title": e.title, "when": e.when_phrase(),
               "start": e.start, "all_day": e.all_day} for e in cal.events]

    # Extend beyond today by scanning each additional day with the same proven reader.
    if within_days > 1:
        events += _events_future_days(within_days - 1)
        events.sort(key=lambda e: (e["start"] is None, e["start"] or 0.0))

    note = "ok" if events else f"nothing scheduled in the next {within_days} day(s)"
    return {"ok": True, "events": events, "note": note}


# AppleScript for a single future day [offset days from today). Same isoOf/separator
# discipline as context_gather; kept tiny because the heavy lifting (today) is reused.
_CAL_DAY_SCRIPT = r'''
on twoDigit(n)
    set n to n as integer
    if n < 10 then return "0" & n
    return n as text
end twoDigit
on isoOf(d)
    return (year of d as text) & "-" & my twoDigit(month of d as integer) & "-" & my twoDigit(day of d) & "T" & my twoDigit(hours of d) & ":" & my twoDigit(minutes of d) & ":" & my twoDigit(seconds of d)
end isoOf
set RS to (ASCII character 30)
set US to (ASCII character 31)
set dayStart to (current date)
set hours of dayStart to 0
set minutes of dayStart to 0
set seconds of dayStart to 0
set dayStart to dayStart + (__OFFSET__ * days)
set dayEnd to dayStart + (1 * days)
set outList to {}
tell application "Calendar"
    repeat with c in calendars
        try
            set evs to (every event of c whose start date ≥ dayStart and start date < dayEnd)
        on error
            set evs to {}
        end try
        repeat with e in evs
            set ad to "0"
            try
                if (allday event of e) then set ad to "1"
            end try
            set end of outList to ((summary of e) as text) & US & my isoOf(start date of e) & US & ad
        end repeat
    end repeat
end tell
set AppleScript's text item delimiters to RS
set outText to outList as text
set AppleScript's text item delimiters to ""
return outText
'''


def _events_future_days(extra_days: int):
    """Events for tomorrow .. tomorrow+extra_days-1, reusing context_gather's parsing.
    Degrades to [] silently per day — list_events already proved Calendar is reachable."""
    out = []
    for offset in range(1, extra_days + 1):
        ok, blob = _osa(_CAL_DAY_SCRIPT.replace("__OFFSET__", str(offset)),
                        timeout=context_gather._CAL_TIMEOUT or 45.0)
        if not ok:
            continue
        for parts in _rows(blob):
            title = (parts[0] if parts else "").strip() or "(untitled)"
            start_text = parts[1].strip() if len(parts) > 1 else ""
            all_day = (len(parts) > 2 and parts[2].strip() == "1")
            start = context_gather._parse_iso_local(start_text)
            ev = context_gather.CalEvent(title=title, start=start,
                                         start_text=start_text, all_day=all_day)
            out.append({"title": ev.title, "when": ev.when_phrase(),
                        "start": ev.start, "all_day": ev.all_day})
    return out


# Build an AppleScript `date` from components — locale-independent (no date-string parsing).
def _as_date_expr(epoch: float) -> str:
    t = time.localtime(epoch)
    return (f'(my makeDate({t.tm_year}, {t.tm_mon}, {t.tm_mday}, '
            f'{t.tm_hour}, {t.tm_min}, {t.tm_sec}))')


_MAKE_DATE_HANDLER = r'''
on makeDate(y, mo, d, hh, mm, ss)
    set theDate to (current date)
    set year of theDate to y
    set month of theDate to mo
    set day of theDate to d
    set hours of theDate to hh
    set minutes of theDate to mm
    set seconds of theDate to ss
    return theDate
end makeDate
'''


def create_event(title: str, start, end=None, calendar: Optional[str] = None,
                 notes: Optional[str] = None) -> dict:
    """Create a Calendar.app event. EXECUTOR — only call after explicit user confirm.

    Args:
        title: event summary (required).
        start: epoch seconds (float/int) for the start.
        end:   epoch seconds for the end; defaults to start + 1 hour.
        calendar: target calendar NAME; default = the first writable calendar.
        notes: optional body text.

    Returns {"ok": True, "title", "calendar", "start", "end"} or an honest failure dict.
    """
    if not (title or "").strip():
        return {"ok": False, "reason": "bad_args", "message": "an event needs a title"}
    try:
        start = float(start)
    except (TypeError, ValueError):
        return {"ok": False, "reason": "bad_args", "message": "start must be a time"}
    try:
        end = float(end) if end is not None else start + 3600.0
    except (TypeError, ValueError):
        end = start + 3600.0
    if end <= start:
        end = start + 3600.0

    if _HAVE_EVENTKIT:
        res = _ek_create_event(title, start, end, calendar, notes)
        if res is not None:                     # EventKit handled it (ok or honest denial)
            return res                          # else fall through to AppleScript

    # ── AppleScript fallback ──
    props = (f'summary:"{esc(title)}", start date:{_as_date_expr(start)}, '
             f'end date:{_as_date_expr(end)}')
    if notes:
        props += f', description:"{esc(notes)}"'
    script = (_MAKE_DATE_HANDLER +
              'tell application "Calendar"\n'
              + (f'  set theCal to (first calendar whose name is "{esc(calendar)}")\n'
                 if calendar else
                 '  set theCal to (first calendar whose writable is true)\n')
              + f'  tell theCal to make new event with properties {{{props}}}\n'
                '  return name of theCal\n'
                'end tell')
    ok, out = _osa(script)
    if not ok:
        if _looks_denied(out):
            return _no_access("Calendar", "Calendars")
        return {"ok": False, "reason": "error", "message": out}
    return {"ok": True, "title": title, "calendar": out or calendar or "(default)",
            "start": start, "end": end}


def _ek_create_event(title, start, end, calendar, notes):
    """EventKit path for create_event. Returns a result dict, or None to fall back.

    None means "EventKit present but not usable for this op" (e.g. not yet authorized
    and we'd rather let AppleScript try). A no_access dict means EventKit asked and was
    explicitly denied.
    """
    try:                                        # pragma: no cover - host/EventKit dependent
        store = EventKit.EKEventStore.alloc().init()
        status = EventKit.EKEventStore.authorizationStatusForEntityType_(0)  # 0 = .event
        if status == 2:                         # .denied
            return _no_access("Calendar", "Calendars")
        if status != 3:                         # not .authorized → let AppleScript try
            return None
        ev = EventKit.EKEvent.eventWithEventStore_(store)
        ev.setTitle_(title)
        ev.setStartDate_(_ns_date(start))
        ev.setEndDate_(_ns_date(end))
        if notes:
            ev.setNotes_(notes)
        cal_obj = None
        if calendar:
            for c in store.calendarsForEntityType_(0):
                if str(c.title()) == calendar:
                    cal_obj = c
                    break
        ev.setCalendar_(cal_obj or store.defaultCalendarForNewEvents())
        ok, err = store.saveEvent_span_error_(ev, 0, None)
        if not ok:
            return {"ok": False, "reason": "error", "message": str(err)}
        return {"ok": True, "title": title,
                "calendar": str(ev.calendar().title()) if ev.calendar() else "(default)",
                "start": start, "end": end}
    except Exception:
        return None                             # any surprise → AppleScript fallback


def _ns_date(epoch: float):
    import Foundation
    return Foundation.NSDate.dateWithTimeIntervalSince1970_(float(epoch))


# ══════════════════════════════════════════════════════════════════════════════════
# REMINDERS  (the macOS Reminders.app — NOT anima.reminders, which is the call-escalation
#             state machine. These are unrelated; do not conflate.)
# ══════════════════════════════════════════════════════════════════════════════════

# Reminders AppleScript is SLOW: reading ANY per-reminder property (`name`, and worst of
# all `id`) costs ~hundreds of ms each, so a multi-list account blows past a short timeout
# (the same pathology context_gather documents for Calendar). Two mitigations:
#   1. We pull `name of every reminder ... whose completed is false` per list in ONE bulk
#      call (and the matching `due date of every reminder ...`), instead of a per-reminder
#      loop — the bulk form is dramatically faster.
#   2. We do NOT fetch the per-reminder `id` here (it roughly doubles the time). Listing
#      shows name + list + due; complete_reminder resolves by title (or by id via EventKit
#      when that's available), so the id isn't needed on this hot path.
# Due dates come back as a parallel list and are stamped from COMPONENTS (a tiny isoOf),
# never the slow `date string`/`«class isot»` coercion.
_REMINDERS_LIST_SCRIPT = r'''
on twoDigit(n)
    set n to n as integer
    if n < 10 then return "0" & n
    return n as text
end twoDigit
on isoOf(d)
    if d is missing value then return ""
    return (year of d as text) & "-" & my twoDigit(month of d as integer) & "-" & my twoDigit(day of d) & "T" & my twoDigit(hours of d) & ":" & my twoDigit(minutes of d)
end isoOf
set RS to (ASCII character 30)
set US to (ASCII character 31)
set outList to {}
tell application "Reminders"
    set theLists to lists
    if "__LIST__" is not "" then set theLists to {list "__LIST__"}
    repeat with L in theLists
        set ln to (name of L) as text
        try
            set theNames to (name of every reminder of L whose completed is false)
        on error
            set theNames to {}
        end try
        try
            set theDues to (due date of every reminder of L whose completed is false)
        on error
            set theDues to {}
        end try
        repeat with i from 1 to (count of theNames)
            set rn to (item i of theNames) as text
            set du to ""
            try
                set du to my isoOf(item i of theDues)
            end try
            set end of outList to rn & US & ln & US & US & du
        end repeat
    end repeat
end tell
set AppleScript's text item delimiters to RS
set outText to outList as text
set AppleScript's text item delimiters to ""
return outText
'''


def list_reminders(list: Optional[str] = None) -> dict:
    """Read open (not-completed) reminders, optionally from one list by name.

    Returns {"ok": True, "reminders": [{"title","list","id","due"}...], "note": str}
    or an honest no_access/error dict. EventKit-preferred, AppleScript fallback.
    """
    if _HAVE_EVENTKIT:
        res = _ek_list_reminders(list)
        if res is not None:
            return res

    script = _REMINDERS_LIST_SCRIPT.replace("__LIST__", esc(list or ""))
    # Reminders is slow to enumerate; give it the same generous, tunable budget the
    # calendar reader uses rather than failing fast on a large account.
    ok, out = _osa(script, timeout=max(45.0, context_gather._CAL_TIMEOUT))
    if not ok:
        if _looks_denied(out):
            return _no_access("Reminders", "Reminders")
        if "timed out" in (out or "").lower():
            return {"ok": False, "reason": "unavailable",
                    "message": ("Reminders took too long to read (many lists?) — "
                                "raise ANIMA_CAL_TIMEOUT or open a specific list")}
        return {"ok": False, "reason": "error", "message": out}
    items = []
    for parts in _rows(out):
        items.append({"title": (parts[0] if parts else "").strip(),
                      "list": parts[1].strip() if len(parts) > 1 else "",
                      "id": parts[2].strip() if len(parts) > 2 else "",
                      "due": parts[3].strip() if len(parts) > 3 else ""})
    note = "ok" if items else ("no open reminders" + (f" in '{list}'" if list else ""))
    return {"ok": True, "reminders": items, "note": note}


def _ek_list_reminders(list_name):
    """EventKit read path. Returns a result dict or None to fall back to AppleScript."""
    try:                                        # pragma: no cover - host/EventKit dependent
        store = EventKit.EKEventStore.alloc().init()
        status = EventKit.EKEventStore.authorizationStatusForEntityType_(1)  # 1 = .reminder
        if status == 2:
            return _no_access("Reminders", "Reminders")
        if status != 3:
            return None
        cals = store.calendarsForEntityType_(1)
        if list_name:
            cals = [c for c in cals if str(c.title()) == list_name]
        pred = store.predicateForRemindersInCalendars_(cals)
        # fetchRemindersMatchingPredicate is async; run it synchronously with a tiny wait.
        import threading
        box = {"items": None}
        done = threading.Event()

        def _cb(reminders):
            box["items"] = reminders
            done.set()
        store.fetchRemindersMatchingPredicate_completion_(pred, _cb)
        if not done.wait(timeout=10.0):
            return None                         # async didn't land → AppleScript fallback
        items = []
        for r in (box["items"] or []):
            if r.isCompleted():
                continue
            due = ""
            try:
                comps = r.dueDateComponents()
                if comps is not None:
                    due = "%04d-%02d-%02dT%02d:%02d" % (
                        comps.year(), comps.month(), comps.day(),
                        max(0, comps.hour()), max(0, comps.minute()))
            except Exception:
                due = ""
            items.append({"title": str(r.title() or ""),
                          "list": str(r.calendar().title()) if r.calendar() else "",
                          "id": str(r.calendarItemIdentifier() or ""),
                          "due": due})
        note = "ok" if items else "no open reminders"
        return {"ok": True, "reminders": items, "note": note}
    except Exception:
        return None


def create_reminder(title: str, due=None, list: Optional[str] = None,
                    notes: Optional[str] = None) -> dict:
    """Create a Reminders.app reminder. EXECUTOR — only call after explicit user confirm.

    Args:
        title: the reminder text (required).
        due:   optional epoch seconds for a due date/alarm.
        list:  optional target list name; default = the app's default list.
        notes: optional body.

    Returns {"ok": True, "title", "list", "due"} or an honest failure dict.
    """
    if not (title or "").strip():
        return {"ok": False, "reason": "bad_args", "message": "a reminder needs a title"}
    due_f = None
    if due is not None:
        try:
            due_f = float(due)
        except (TypeError, ValueError):
            due_f = None

    if _HAVE_EVENTKIT:
        res = _ek_create_reminder(title, due_f, list, notes)
        if res is not None:
            return res

    props = f'name:"{esc(title)}"'
    if notes:
        props += f', body:"{esc(notes)}"'
    if due_f is not None:
        props += f', due date:{_as_date_expr(due_f)}'
    target = (f'  set theList to list "{esc(list)}"\n' if list else
              '  set theList to default list\n')
    script = (_MAKE_DATE_HANDLER +
              'tell application "Reminders"\n'
              + target
              + f'  tell theList to make new reminder with properties {{{props}}}\n'
                '  return name of theList\n'
                'end tell')
    ok, out = _osa(script)
    if not ok:
        if _looks_denied(out):
            return _no_access("Reminders", "Reminders")
        return {"ok": False, "reason": "error", "message": out}
    return {"ok": True, "title": title, "list": out or list or "(default)", "due": due_f}


def _ek_create_reminder(title, due_f, list_name, notes):
    """EventKit write path for a reminder. Returns a result dict or None to fall back."""
    try:                                        # pragma: no cover - host/EventKit dependent
        store = EventKit.EKEventStore.alloc().init()
        status = EventKit.EKEventStore.authorizationStatusForEntityType_(1)
        if status == 2:
            return _no_access("Reminders", "Reminders")
        if status != 3:
            return None
        rem = EventKit.EKReminder.reminderWithEventStore_(store)
        rem.setTitle_(title)
        if notes:
            rem.setNotes_(notes)
        cal_obj = None
        if list_name:
            for c in store.calendarsForEntityType_(1):
                if str(c.title()) == list_name:
                    cal_obj = c
                    break
        rem.setCalendar_(cal_obj or store.defaultCalendarForNewReminders())
        if due_f is not None:
            import Foundation
            cal = Foundation.NSCalendar.currentCalendar()
            units = (Foundation.NSCalendarUnitYear | Foundation.NSCalendarUnitMonth
                     | Foundation.NSCalendarUnitDay | Foundation.NSCalendarUnitHour
                     | Foundation.NSCalendarUnitMinute)
            comps = cal.components_fromDate_(units, _ns_date(due_f))
            rem.setDueDateComponents_(comps)
        ok, err = store.saveReminder_commit_error_(rem, True, None)
        if not ok:
            return {"ok": False, "reason": "error", "message": str(err)}
        return {"ok": True, "title": title,
                "list": str(rem.calendar().title()) if rem.calendar() else "(default)",
                "due": due_f}
    except Exception:
        return None


def complete_reminder(id_or_title: str) -> dict:
    """Mark a reminder complete by its id OR (fallback) by an exact open-reminder title.

    EXECUTOR — only call after explicit user confirm. Returns
    {"ok": True, "completed": title} / {"ok": False, "reason": "not_found", ...} / honest denial.
    """
    key = (id_or_title or "").strip()
    if not key:
        return {"ok": False, "reason": "bad_args", "message": "need a reminder id or title"}

    if _HAVE_EVENTKIT:
        res = _ek_complete_reminder(key)
        if res is not None:
            return res

    # Try by id first, then by exact name among open reminders. Emit a marker we can read.
    script = (
        'tell application "Reminders"\n'
        '  set target to missing value\n'
        '  try\n'
        f'    set target to (first reminder whose id is "{esc(key)}")\n'
        '  end try\n'
        '  if target is missing value then\n'
        '    try\n'
        f'      set target to (first reminder whose completed is false and name is "{esc(key)}")\n'
        '    end try\n'
        '  end if\n'
        '  if target is missing value then return "__NONE__"\n'
        '  set completed of target to true\n'
        '  return (name of target)\n'
        'end tell')
    ok, out = _osa(script)
    if not ok:
        if _looks_denied(out):
            return _no_access("Reminders", "Reminders")
        return {"ok": False, "reason": "error", "message": out}
    if out == "__NONE__":
        return {"ok": False, "reason": "not_found",
                "message": f"I couldn't find an open reminder matching '{key}'"}
    return {"ok": True, "completed": out or key}


def _ek_complete_reminder(key):
    """EventKit completion path. Returns a result dict or None to fall back."""
    try:                                        # pragma: no cover - host/EventKit dependent
        store = EventKit.EKEventStore.alloc().init()
        status = EventKit.EKEventStore.authorizationStatusForEntityType_(1)
        if status == 2:
            return _no_access("Reminders", "Reminders")
        if status != 3:
            return None
        # Resolve by identifier first (cheap, exact).
        item = store.calendarItemWithIdentifier_(key)
        target = item if (item is not None and hasattr(item, "isCompleted")) else None
        if target is None:                      # by title among open reminders
            pred = store.predicateForRemindersInCalendars_(
                store.calendarsForEntityType_(1))
            import threading
            box = {"items": None}
            done = threading.Event()
            store.fetchRemindersMatchingPredicate_completion_(
                pred, lambda rs: (box.__setitem__("items", rs), done.set()))
            if not done.wait(timeout=10.0):
                return None
            for r in (box["items"] or []):
                if not r.isCompleted() and str(r.title() or "") == key:
                    target = r
                    break
        if target is None:
            return {"ok": False, "reason": "not_found",
                    "message": f"I couldn't find an open reminder matching '{key}'"}
        target.setCompleted_(True)
        ok, err = store.saveReminder_commit_error_(target, True, None)
        if not ok:
            return {"ok": False, "reason": "error", "message": str(err)}
        return {"ok": True, "completed": str(target.title() or key)}
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════════
# NOTES  (no EventKit API → AppleScript only)
# ══════════════════════════════════════════════════════════════════════════════════

# Per-note `container` access errors on some notes and per-note loops are slow, so when
# listing ALL notes we group BY FOLDER (each folder knows its own name and notes) and pull
# `name of every note of <folder>` in ONE bulk call per folder — fast AND it gives us the
# folder label reliably without the fragile `container of` lookup. When a single folder is
# requested we read just that one.
_NOTES_LIST_SCRIPT = r'''
set RS to (ASCII character 30)
set US to (ASCII character 31)
set outList to {}
tell application "Notes"
    if "__FOLDER__" is "" then
        set theFolders to folders
    else
        set theFolders to {folder "__FOLDER__"}
    end if
    repeat with f in theFolders
        set fn to (name of f) as text
        try
            set theNames to (name of every note of f)
        on error
            set theNames to {}
        end try
        repeat with nm in theNames
            set end of outList to (nm as text) & US & fn
        end repeat
    end repeat
end tell
set AppleScript's text item delimiters to RS
set outText to outList as text
set AppleScript's text item delimiters to ""
return outText
'''


def list_notes(folder: Optional[str] = None) -> dict:
    """List note titles (optionally within one folder by name).

    Returns {"ok": True, "notes": [{"title","folder"}...], "note": str} or honest denial.
    """
    script = _NOTES_LIST_SCRIPT.replace("__FOLDER__", esc(folder or ""))
    ok, out = _osa(script, timeout=30.0)
    if not ok:
        if _looks_denied(out):
            return _no_access("Notes", "Automation (enable Notes)")
        return {"ok": False, "reason": "error", "message": out}
    items = [{"title": (p[0] if p else "").strip(),
              "folder": p[1].strip() if len(p) > 1 else ""} for p in _rows(out)]
    note = "ok" if items else ("no notes" + (f" in '{folder}'" if folder else ""))
    return {"ok": True, "notes": items, "note": note}


def read_note(title: str) -> dict:
    """Read one note's plain-text body, matched by exact title (first match wins).

    Returns {"ok": True, "title", "folder", "body"} /
            {"ok": False, "reason": "not_found", ...} / honest denial.
    Note bodies are HTML in Notes; we return the app's plaintext rendering.
    """
    if not (title or "").strip():
        return {"ok": False, "reason": "bad_args", "message": "need a note title"}
    # `plaintext` ALWAYS works and already leads with the title line; `container`/folder
    # errors on some notes, so it is computed into `fn` defensively. We emit plaintext
    # FIRST so the body survives even if the folder lookup fails, with the folder appended
    # after the US (empty if unavailable). Then we strip the leading title line for body.
    script = (
        'set US to (ASCII character 31)\n'
        'tell application "Notes"\n'
        f'  set matches to (notes whose name is "{esc(title)}")\n'
        '  if (count of matches) is 0 then return "__NONE__"\n'
        '  set n to item 1 of matches\n'
        '  set pt to (plaintext of n)\n'
        '  set fn to ""\n'
        '  try\n'
        '    set fn to (name of container of n) as text\n'
        '  end try\n'
        '  return pt & US & fn\n'
        'end tell')
    ok, out = _osa(script)
    if not ok:
        if _looks_denied(out):
            return _no_access("Notes", "Automation (enable Notes)")
        return {"ok": False, "reason": "error", "message": out}
    if out == "__NONE__":
        return {"ok": False, "reason": "not_found",
                "message": f"I couldn't find a note titled '{title}'"}
    plain, _, folder = out.partition(_US)
    # Drop the title line (Notes' plaintext leads with the title) to expose the real body.
    body = plain
    first, _nl, rest = plain.partition("\n")
    if first.strip() == (title or "").strip():
        body = rest
    return {"ok": True, "title": title, "folder": folder.strip(), "body": body}


def create_note(title: str, body: str = "", folder: Optional[str] = None) -> dict:
    """Create a note. EXECUTOR — only call after explicit user confirm.

    The first line of a Notes note becomes its title, so we render the body as
    "<title>\\n<body>". Returns {"ok": True, "title", "folder"} or honest denial.
    """
    if not (title or "").strip():
        return {"ok": False, "reason": "bad_args", "message": "a note needs a title"}
    # Notes treats the first line as the title; a <br> keeps the rest as the body.
    safe_title = esc(title)
    safe_body = esc(body or "")
    html = f'{safe_title}<br>{safe_body}' if safe_body else safe_title
    target = (f'  set theFolder to folder "{esc(folder)}"\n'
              f'  tell theFolder to make new note with properties {{body:"{html}"}}\n'
              if folder else
              f'  make new note with properties {{body:"{html}"}}\n')
    script = ('tell application "Notes"\n'
              + target
              + '  return "ok"\n'
                'end tell')
    ok, out = _osa(script)
    if not ok:
        if _looks_denied(out):
            return _no_access("Notes", "Automation (enable Notes)")
        return {"ok": False, "reason": "error", "message": out}
    return {"ok": True, "title": title, "folder": folder or "(default)"}


def append_to_note(title: str, text: str) -> dict:
    """Append text to an existing note (matched by exact title). EXECUTOR — post-confirm only.

    Returns {"ok": True, "title"} / {"ok": False, "reason": "not_found", ...} / honest denial.
    """
    if not (title or "").strip():
        return {"ok": False, "reason": "bad_args", "message": "need a note title"}
    if not (text or ""):
        return {"ok": False, "reason": "bad_args", "message": "nothing to append"}
    script = (
        'tell application "Notes"\n'
        f'  set matches to (notes whose name is "{esc(title)}")\n'
        '  if (count of matches) is 0 then return "__NONE__"\n'
        '  set n to item 1 of matches\n'
        f'  set body of n to (body of n) & "<br>{esc(text)}"\n'
        '  return "ok"\n'
        'end tell')
    ok, out = _osa(script)
    if not ok:
        if _looks_denied(out):
            return _no_access("Notes", "Automation (enable Notes)")
        return {"ok": False, "reason": "error", "message": out}
    if out == "__NONE__":
        return {"ok": False, "reason": "not_found",
                "message": f"I couldn't find a note titled '{title}' to append to"}
    return {"ok": True, "title": title}


# ══════════════════════════════════════════════════════════════════════════════════
# CLI — selftest (read-only reads, DRY-RUN writes) + small read commands
# ══════════════════════════════════════════════════════════════════════════════════

def _print_result(label: str, res: dict):
    if res.get("ok"):
        print(f"  ok   {label}: {res.get('note', '')}".rstrip())
    elif res.get("reason") == "no_access":
        print(f"  ---  {label}: NO ACCESS — {res.get('message', '')}")
    else:
        print(f"  ??   {label}: {res.get('reason', 'error')} — {res.get('message', '')}")


def _selftest():
    """Exercise every reader read-only and DRY-RUN every writer (creates NOTHING)."""
    print("host_access selftest — reads are read-only; writes are DRY-RUN (nothing is created).")
    print(f"EventKit available: {_HAVE_EVENTKIT}  (AppleScript fallback always available)\n")

    print("READS (live, read-only):")
    cal = list_events(within_days=7)
    _print_result("Calendar list_events(7)", cal)
    if cal.get("ok"):
        for e in cal["events"][:5]:
            print(f"         · {e['title']} ({e['when']})")
    rem = list_reminders()
    _print_result("Reminders list_reminders()", rem)
    if rem.get("ok"):
        for r in rem["reminders"][:5]:
            print(f"         · {r['title']}  [{r['list']}]")
    nts = list_notes()
    _print_result("Notes list_notes()", nts)
    if nts.get("ok"):
        for n in nts["notes"][:5]:
            print(f"         · {n['title']}  [{n['folder']}]")

    print("\nWRITES (DRY-RUN — these are what Vera WOULD create on confirm; nothing happens):")
    when = time.time() + 3600
    print(f"  would create_event(title='Vera selftest', "
          f"start={time.strftime('%Y-%m-%d %H:%M', time.localtime(when))}, +1h)")
    print(f"  would create_reminder(title='Vera selftest reminder', due=None)")
    print(f"  would create_note(title='Vera selftest note', body='hello from selftest')")
    print(f"  would append_to_note(title='<an existing note>', text='…')")
    print(f"  would complete_reminder(id_or_title='<an existing reminder>')")
    print("\n(no writes were performed)")
    return 0


def _main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        prog="anima.host_access",
        description="Read/write the Mac's Calendar, Reminders, Notes (on-device). "
                    "--selftest is always safe (reads read-only, dry-runs writes).")
    ap.add_argument("--selftest", action="store_true",
                    help="probe access; read read-only; DRY-RUN every write (creates nothing)")
    ap.add_argument("--calendar", nargs="?", type=int, const=1, metavar="DAYS",
                    help="list events in the next DAYS days (default 1 = today)")
    ap.add_argument("--reminders", nargs="?", const="", metavar="LIST",
                    help="list open reminders (optionally in one LIST)")
    ap.add_argument("--notes", nargs="?", const="", metavar="FOLDER",
                    help="list note titles (optionally in one FOLDER)")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    did = False
    if args.calendar is not None:
        did = True
        import json
        print(json.dumps(list_events(args.calendar), indent=2, default=str))
    if args.reminders is not None:
        did = True
        import json
        print(json.dumps(list_reminders(args.reminders or None), indent=2, default=str))
    if args.notes is not None:
        did = True
        import json
        print(json.dumps(list_notes(args.notes or None), indent=2, default=str))
    if not did:
        ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
