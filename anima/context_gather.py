"""
context_gather — local, key-free fact gathering for a proactive briefing.

The proactive subsystem (a morning briefing, eventually a two-way call) needs a
small, honest *fact sheet* about the day: the weather, what's on the calendar,
maybe an unread-message count. This module gathers exactly that — and NOTHING
ELSE leaves the Mac. Two sources only:

  * weather — Open-Meteo's free forecast endpoint (no API key). lat/lon in,
    temperature (°F) + a plain-language condition out.
  * calendar — Calendar.app via AppleScript (osascript), parsed ROBUSTLY into a
    list of {title, start, all_day} dicts. If Calendar isn't scriptable, has no
    events, or the script errors, it degrades to an EMPTY list plus an honest
    `note` — it never fabricates events.

Design rules, in keeping with the rest of anima:
  * local-first: weather is the one outbound call (a public, keyless forecast);
    the calendar read is entirely on-device. Nothing about the person goes out.
  * honest degradation: every gatherer returns a typed result with an `ok` flag
    and a human `note`, so a caller (and the briefing) can say "I couldn't see
    your calendar" instead of inventing a day.
  * no new deps: stdlib urllib + osascript, same as applemac.py.

This is the *input* layer. Turning these facts into Vera's voice is proactive.py's
job — and it goes through her real brain, never a detached prompt.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

from . import egress, privacy_receipts

# Calendar.app scanned via AppleScript is O(events) PER calendar, and the `whose
# start date ≥ …` predicate is slow — a machine with many subscribed calendars
# (Birthdays, Holidays, CalDAV/Gmail accounts, Siri Suggestions) can take 30-70s
# for today alone. So the default timeout is generous, and tunable; past it the
# reader degrades to "could not read" rather than blocking forever. Set
# ANIMA_CAL_TIMEOUT=0 to skip the calendar entirely (weather-only briefing).
_CAL_TIMEOUT = float(os.environ.get("ANIMA_CAL_TIMEOUT", "45"))

# --- weather (Open-Meteo, no key) -------------------------------------------

# WMO weather-interpretation codes -> short plain-language conditions.
# (Open-Meteo returns a numeric `weather_code`; this is the documented mapping,
# collapsed to the granularity a spoken briefing actually needs.)
_WMO = {
    0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "freezing fog",
    51: "light drizzle", 53: "drizzle", 55: "heavy drizzle",
    56: "freezing drizzle", 57: "freezing drizzle",
    61: "light rain", 63: "rain", 65: "heavy rain",
    66: "freezing rain", 67: "freezing rain",
    71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains",
    80: "light showers", 81: "showers", 82: "violent showers",
    85: "snow showers", 86: "heavy snow showers",
    95: "thunderstorms", 96: "thunderstorms with hail", 99: "severe thunderstorms",
}


@dataclass
class Weather:
    ok: bool
    temp_f: Optional[float] = None          # current temperature, °F
    high_f: Optional[float] = None          # today's forecast high, °F
    low_f: Optional[float] = None           # today's forecast low, °F
    condition: str = ""                     # plain-language, e.g. "partly cloudy"
    note: str = ""                          # human-readable status / failure reason

    def phrase(self) -> str:
        """A one-line spoken-friendly weather summary, or an honest blank."""
        if not self.ok:
            return ""
        bits = []
        if self.condition:
            bits.append(self.condition)
        if self.temp_f is not None:
            bits.append(f"{round(self.temp_f)}°F now")
        if self.high_f is not None and self.low_f is not None:
            bits.append(f"high {round(self.high_f)}, low {round(self.low_f)}")
        return ", ".join(bits)


def weather(lat: float, lon: float, timeout: float = 8.0, *,
            name: str | None = None, turn_id: str = "",
            precision: str | None = None) -> Weather:
    """Current conditions + today's high/low for a coordinate, via Open-Meteo.

    No API key. Returns Weather(ok=False, note=...) on any failure — the caller
    decides how to speak about a missing forecast; we never guess one.
    """
    if egress.zero_enabled():
        try:
            privacy_receipts.record_egress(
                name, kind="weather_lookup", target="https://api.open-meteo.com",
                decision="blocked", turn_id=turn_id, reason="zero-egress")
        except Exception:
            pass
        return Weather(ok=False, note="zero-egress mode is on; blocked weather lookup")
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return Weather(ok=False, note="no/!invalid coordinates for weather")
    loc = privacy_receipts.prepare_location_for_egress(
        lat, lon, name=name, precision=precision)
    if not loc.get("ok"):
        try:
            privacy_receipts.record_egress(
                name, kind="weather_lookup", target="https://api.open-meteo.com",
                decision="blocked", turn_id=turn_id,
                reason="location sharing is off",
                metadata={"provider": "open-meteo", "location_precision": "off"})
        except Exception:
            pass
        return Weather(ok=False, note="location sharing is off; blocked weather lookup")
    lat = float(loc["lat"])
    lon = float(loc["lon"])
    loc_meta = {
        "provider": "open-meteo",
        "location_precision": loc.get("precision", "coarse"),
        "location_label": loc.get("label", ""),
    }
    params = urllib.parse.urlencode({
        "latitude": f"{lat:.4f}",
        "longitude": f"{lon:.4f}",
        "current": "temperature_2m,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min",
        "temperature_unit": "fahrenheit",
        "timezone": "auto",
        "forecast_days": 1,
    })
    url = "https://api.open-meteo.com/v1/forecast?" + params
    try:
        try:
            privacy_receipts.record_egress(
                name, kind="weather_lookup", target=url, decision="attempt",
                turn_id=turn_id, metadata=loc_meta)
        except Exception:
            pass
        with urllib.request.urlopen(url, timeout=timeout) as r:
            data = json.loads(r.read())
    except Exception as e:                       # network down, rate-limited, etc.
        try:
            privacy_receipts.record_egress(
                name, kind="weather_lookup", target=url, decision="failed",
                turn_id=turn_id, reason=e.__class__.__name__,
                metadata=loc_meta)
        except Exception:
            pass
        return Weather(ok=False, note=f"weather lookup failed: {e}")
    cur = data.get("current") or {}
    daily = data.get("daily") or {}
    code = cur.get("weather_code")
    cond = _WMO.get(int(code), "") if isinstance(code, (int, float)) else ""

    def _first(seq):
        return seq[0] if isinstance(seq, list) and seq else None

    try:
        privacy_receipts.record_egress(
            name, kind="weather_lookup", target=url, decision="completed",
            turn_id=turn_id, metadata=loc_meta)
    except Exception:
        pass
    return Weather(
        ok=True,
        temp_f=cur.get("temperature_2m"),
        high_f=_first(daily.get("temperature_2m_max")),
        low_f=_first(daily.get("temperature_2m_min")),
        condition=cond,
        note="ok",
    )


# --- calendar (Calendar.app via AppleScript) --------------------------------

@dataclass
class CalEvent:
    title: str
    start: Optional[float] = None           # epoch seconds, if parseable
    start_text: str = ""                    # the raw date string AppleScript gave
    all_day: bool = False

    def when_phrase(self) -> str:
        """A spoken-friendly time, e.g. '9:30 AM' or 'all day' or the raw text."""
        if self.all_day:
            return "all day"
        if self.start is not None:
            return time.strftime("%-I:%M %p", time.localtime(self.start))
        return self.start_text or ""


@dataclass
class Calendar:
    ok: bool
    events: list = field(default_factory=list)   # list[CalEvent], chronological
    note: str = ""

    def phrases(self) -> list:
        """Each event as 'TITLE at TIME' / 'TITLE (all day)', for the fact sheet."""
        out = []
        for e in self.events:
            w = e.when_phrase()
            out.append(f"{e.title} ({w})" if w else e.title)
        return out


# We ask AppleScript to emit ONE line per event with unambiguous field separators
# we choose ourselves (a record-separator + unit-separator), instead of trying to
# re-parse Calendar's locale-dependent prose. This is the robustness the proposal's
# simulated parser lacked: titles with commas/quotes can't break the row format.
_RS = "\x1e"          # between events
_US = "\x1f"          # between fields within an event

# AppleScript: today's events (across all calendars), each as
#   summary <US> startISO <US> alldayFlag
# joined by <RS>. `date string`/`time string` are locale-bound, so instead we build
# an ISO-ish stamp from the date's own components — locale-independent and parseable.
_CAL_SCRIPT = r'''
on twoDigit(n)
    set n to n as integer
    if n < 10 then return "0" & n
    return n as text
end twoDigit

on isoOf(d)
    set y to year of d
    set mo to (month of d as integer)
    set dy to day of d
    set hh to hours of d
    set mm to minutes of d
    set ss to seconds of d
    return (y as text) & "-" & my twoDigit(mo) & "-" & my twoDigit(dy) & "T" & my twoDigit(hh) & ":" & my twoDigit(mm) & ":" & my twoDigit(ss)
end isoOf

set RS to (ASCII character 30)
set US to (ASCII character 31)
set startOfDay to current date
set hours of startOfDay to 0
set minutes of startOfDay to 0
set seconds of startOfDay to 0
set endOfDay to startOfDay + (1 * days)
set outList to {}
tell application "Calendar"
    repeat with c in calendars
        try
            set evs to (every event of c whose start date ≥ startOfDay and start date < endOfDay)
        on error
            set evs to {}
        end try
        repeat with e in evs
            set theTitle to (summary of e) as text
            set theStart to my isoOf(start date of e)
            set ad to "0"
            try
                if (allday event of e) then set ad to "1"
            end try
            set end of outList to theTitle & US & theStart & US & ad
        end repeat
    end repeat
end tell
set AppleScript's text item delimiters to RS
set outText to outList as text
set AppleScript's text item delimiters to ""
return outText
'''

# Accept the locale-independent stamp the script emits (and tolerate a trailing
# fractional/zone the OS might append, though we don't ask for one).
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})")


def _parse_iso_local(s: str) -> Optional[float]:
    """Parse the 'YYYY-MM-DDTHH:MM:SS' the script emits as LOCAL time -> epoch.
    Returns None if it doesn't match, so a malformed stamp degrades to start_text."""
    m = _ISO.match((s or "").strip())
    if not m:
        return None
    try:
        y, mo, d, hh, mm, ss = (int(x) for x in m.groups())
        # mktime interprets the struct as local time, matching Calendar's wall clock.
        return time.mktime((y, mo, d, hh, mm, ss, 0, 0, -1))
    except (ValueError, OverflowError):
        return None


def _run_osa(script: str, timeout: float = 25.0):
    """Run an AppleScript; return (ok, output_or_error). Never raises.
    Mirrors applemac._osa so behaviour (and Automation-permission failures) match."""
    try:
        p = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=timeout)
        return (p.returncode == 0, (p.stdout if p.returncode == 0 else p.stderr).strip())
    except FileNotFoundError:
        return (False, "osascript not found (not a Mac?)")
    except subprocess.TimeoutExpired:
        return (False, "Calendar timed out")
    except Exception as e:
        return (False, str(e))


def calendar_today(timeout: Optional[float] = None) -> Calendar:
    """Today's Calendar.app events, robustly parsed, sorted chronologically.

    Honest failure modes (all return ok per whether the SCRIPT ran, with events
    possibly empty and a clear note):
      * ANIMA_CAL_TIMEOUT=0 -> skipped on purpose -> ok=False, note says so.
      * Calendar not scriptable / Automation permission denied -> ok=False, note.
      * Calendar too slow (many calendars) and timed out -> ok=False, note suggests
        raising ANIMA_CAL_TIMEOUT.
      * Script ran, no events today -> ok=True, events=[], note="no events today".
      * A row that won't parse is kept with start=None (start_text preserved),
        never dropped silently and never invented.
    """
    timeout = _CAL_TIMEOUT if timeout is None else timeout
    if timeout <= 0:
        return Calendar(ok=False, events=[],
                        note="calendar skipped (ANIMA_CAL_TIMEOUT=0)")
    ok, out = _run_osa(_CAL_SCRIPT, timeout=timeout)
    if not ok:
        hint = out
        low = (out or "").lower()
        if "not authorized" in low or "1743" in low or "permission" in low:
            hint = ("Calendar access not granted — allow your terminal/Python under "
                    "System Settings > Privacy & Security > Automation (and Calendars).")
        elif "timed out" in low:
            hint = (f"Calendar too slow to scan within {timeout:.0f}s (many calendars?) — "
                    f"raise it with ANIMA_CAL_TIMEOUT, or set =0 to skip the calendar.")
        return Calendar(ok=False, events=[], note=f"calendar unavailable: {hint}")
    rows = [r for r in (out or "").split(_RS) if r.strip()]
    events = []
    for row in rows:
        parts = row.split(_US)
        title = (parts[0] if len(parts) > 0 else "").strip() or "(untitled)"
        start_text = parts[1].strip() if len(parts) > 1 else ""
        all_day = (len(parts) > 2 and parts[2].strip() == "1")
        events.append(CalEvent(title=title, start=_parse_iso_local(start_text),
                               start_text=start_text, all_day=all_day))
    # chronological: timed events by start, all-day/unparsed sink to the end stably
    events.sort(key=lambda e: (e.start is None, e.start or 0.0))
    note = "ok" if events else "no events today"
    return Calendar(ok=True, events=events, note=note)


# --- the assembled fact sheet -----------------------------------------------

@dataclass
class DayContext:
    """Everything the briefing composer is allowed to know. Plain, inspectable."""
    when: float                              # epoch the sheet was built
    weather: Weather
    calendar: Calendar
    location_label: str = ""                 # optional human place name, if supplied
    unread_count: Optional[int] = None       # optional; None means 'not checked'
    notes: list = field(default_factory=list)

    def fact_sheet(self) -> str:
        """A compact, honest plaintext brief of the day — the ONLY content handed to
        the brain as ground truth. Absent data is stated as absent, never filled in."""
        lines = []
        lines.append("Date: " + time.strftime("%A, %B %-d, %Y", time.localtime(self.when)))
        if self.location_label:
            lines.append("Location: " + self.location_label)
        wp = self.weather.phrase()
        lines.append("Weather: " + wp if wp else
                     "Weather: unavailable (" + (self.weather.note or "no data") + ")")
        if self.calendar.ok and self.calendar.events:
            lines.append("Calendar today:")
            for p in self.calendar.phrases():
                lines.append("  - " + p)
        elif self.calendar.ok:
            lines.append("Calendar today: nothing scheduled")
        else:
            lines.append("Calendar today: could not read (" + (self.calendar.note or "") + ")")
        if self.unread_count is not None:
            lines.append(f"Unread messages: {self.unread_count}")
        for n in self.notes:
            if n:
                lines.append("Note: " + n)
        return "\n".join(lines)


def gather(lat: Optional[float] = None, lon: Optional[float] = None,
           location_label: str = "", unread_count: Optional[int] = None,
           now: Optional[float] = None, name: str | None = None) -> DayContext:
    """Build the full day context from local sources. Every piece degrades on its own;
    a missing coordinate simply means no weather, not a failure of the whole sheet."""
    now = time.time() if now is None else now
    if lat is not None and lon is not None:
        w = weather(lat, lon, name=name)
    else:
        w = Weather(ok=False, note="no location provided (POST one from the phone, or pass --lat/--lon)")
    cal = calendar_today()
    notes = []
    if not w.ok and (lat is None or lon is None):
        notes.append("no location yet, so no weather")
    return DayContext(when=now, weather=w, calendar=cal, location_label=location_label,
                      unread_count=unread_count, notes=notes)


# --- tiny CLI: print the raw fact sheet (no LLM) ----------------------------

def _main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        prog="anima.context_gather",
        description="Print the local day fact-sheet (weather + calendar). No LLM, no network except Open-Meteo.")
    ap.add_argument("--lat", type=float, default=None, help="latitude for weather")
    ap.add_argument("--lon", type=float, default=None, help="longitude for weather")
    ap.add_argument("--place", default="", help="optional human place label")
    args = ap.parse_args(argv)
    ctx = gather(lat=args.lat, lon=args.lon, location_label=args.place)
    print(ctx.fact_sheet())


if __name__ == "__main__":
    _main()
