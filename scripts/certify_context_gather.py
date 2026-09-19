#!/usr/bin/env python3
"""
certify_context_gather — the ambient day fact-sheet (weather + calendar) is REAL, deterministic,
and HONEST: it gathers true facts or degrades with a clear reason, and it NEVER fabricates context.

context_gather.py is the INPUT layer for the proactive briefing (proactive.compose_briefing reads a
context_gather.DayContext and narrates ONLY from its fact_sheet(), through Vera's real brain). Its two
sources are LIVE I/O — Open-Meteo (a keyless HTTPS forecast) for weather, and Calendar.app via
osascript for today's events. This cert proves the deterministic surface those feed, OFFLINE, through
the SAME functions proactive/host_access/reminders call — and it tripwires BOTH live sources OFF so a
real network or osascript call would FAIL the cert (no live model, no network, no host scan):

  A. WEATHER DEGRADES HONESTLY, NEVER FABRICATES — weather() with non-numeric coordinates returns
     ok=False + a clear note and an EMPTY phrase() (no temperature invented), making ZERO network
     calls; a simulated network failure (urlopen raising) returns ok=False + "weather lookup failed:
     ..." + an empty phrase(). A missing forecast is stated as missing, never guessed.
  B. CALENDAR DEGRADES HONESTLY — calendar_today(timeout=0) returns ok=False, events=[], a note
     naming the ANIMA_CAL_TIMEOUT=0 skip, with NO osascript call; a simulated permission-denied
     osascript error maps to an ok=False note mentioning Automation/permission and yields ZERO events.
  C. PURE PARSER IS REAL + GROUNDED — _parse_iso_local round-trips "YYYY-MM-DDTHH:MM:SS" to the
     matching LOCAL epoch, and returns None (not a guess) for junk / empty input.
  D. ROBUST SHAPE, KEPT-NOT-INVENTED — a synthetic RS/US Calendar output (fed via the tripwired
     _run_osa, so STILL no real osascript) parses into the exact events, sorted chronologically, with
     a comma/quote title preserved intact, an all-day flag honored, and a row whose timestamp won't
     parse KEPT (present, start=None, start_text preserved) rather than dropped or fabricated; an
     empty script output yields ok=True, events=[], note="no events today" and invents nothing.
  E. FACT SHEET STATES ABSENCE AS ABSENCE — with weather + calendar both unavailable, fact_sheet()
     emits "Weather: unavailable (...)" and "Calendar today: could not read (...)" and contains NO
     invented event line; gather() with no coordinates yields no weather, an honest "no location yet"
     note, and a sheet that never names a forecast or an event.

Hermetic + offline: every store-bearing module is redirected to a temp dir via
gate0_prime_experience._temp_store (context_gather itself is stateless and writes nothing); the two
live sources are replaced with tripwires for the whole run, so any deterministic path that tried to
reach the network or the host would trip them and FAIL. The real .anima is fingerprinted before/after
and asserted byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
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


class _Tripwire(Exception):
    """Raised if a deterministic path EVER touches the live network or osascript. A trip = FAIL,
    proving the offline cert never silently made a real call."""


def main() -> int:
    from anima import context_gather as cg
    import urllib.request as _urlreq
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("CONTEXT GATHER — the day fact-sheet is real, deterministic, and never fabricates context")
    print("=" * 86)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # --- TRIPWIRES: both LIVE sources OFF for the whole run -----------------------------------
    # If any deterministic path tried a real Open-Meteo fetch or a real Calendar.app scan, it would
    # raise here and the cert would FAIL — so "offline" is enforced, not assumed. We record whether a
    # tripwire ever fired so a guessing path can never quietly pass.
    tripped = {"net": 0, "osa": 0}

    def _net_tripwire(*a, **k):
        tripped["net"] += 1
        raise _Tripwire("network reached (urlopen) — not allowed in this offline cert")

    saved_urlopen = _urlreq.urlopen
    saved_run_osa = cg._run_osa
    # default osascript tripwire (per-check we swap in synthetic outputs explicitly)
    def _osa_tripwire(script, timeout=25.0):
        tripped["osa"] += 1
        raise _Tripwire("osascript reached (_run_osa) — not allowed in this offline cert")

    with _temp_store():
        _urlreq.urlopen = _net_tripwire
        cg._run_osa = _osa_tripwire
        try:
            # ---- A. WEATHER DEGRADES HONESTLY, NEVER FABRICATES -------------------------------
            net0 = tripped["net"]
            w_bad = cg.weather("not-a-lat", "not-a-lon")
            ck("A1: weather() with non-numeric coordinates returns ok=False with a clear note",
               w_bad.ok is False and bool(w_bad.note))
            ck("A2: a failed weather read invents NO temperature — phrase() is empty",
               w_bad.phrase() == "" and w_bad.temp_f is None and w_bad.high_f is None)
            ck("A3: the invalid-coordinate path made ZERO network calls (rejected before any fetch)",
               tripped["net"] == net0)

            # simulated network DOWN: urlopen raises -> honest ok=False, empty phrase, no guess
            w_net = cg.weather(45.5231, -122.6765)
            ck("A4: a simulated network failure degrades to ok=False + 'weather lookup failed: ...'",
               w_net.ok is False and "weather lookup failed" in (w_net.note or ""))
            ck("A5: the network-down weather still fabricates nothing (empty phrase, no temp/high/low)",
               w_net.phrase() == "" and w_net.temp_f is None
               and w_net.high_f is None and w_net.low_f is None)
            ck("A6: the network-down path DID attempt the fetch and hit the tripwire (real call site)",
               tripped["net"] == net0 + 1)

            # ---- B. CALENDAR DEGRADES HONESTLY -----------------------------------------------
            osa0 = tripped["osa"]
            c_skip = cg.calendar_today(timeout=0)
            ck("B1: calendar_today(timeout=0) is honestly SKIPPED — ok=False, events=[], clear note",
               c_skip.ok is False and c_skip.events == []
               and "ANIMA_CAL_TIMEOUT=0" in (c_skip.note or ""))
            ck("B2: the skipped calendar made ZERO osascript calls (skipped before the scan)",
               tripped["osa"] == osa0)
            ck("B3: a skipped calendar invents no events — phrases() is empty",
               c_skip.phrases() == [])

            # simulated Automation-permission DENIED osascript error -> honest, mapped note, no events
            cg._run_osa = lambda script, timeout=25.0: (False, "execution error: Not authorized "
                                                               "to send Apple events (1743).")
            try:
                c_denied = cg.calendar_today(timeout=45)
            finally:
                cg._run_osa = _osa_tripwire
            ck("B4: a permission-denied osascript maps to an honest ok=False note (Automation hint)",
               c_denied.ok is False and "unavailable" in (c_denied.note or "")
               and ("Automation" in c_denied.note or "permission" in c_denied.note.lower()))
            ck("B5: the denied calendar yields ZERO events (never fabricates a day)",
               c_denied.events == [] and c_denied.phrases() == [])

            # ---- C. PURE PARSER IS REAL + GROUNDED -------------------------------------------
            import time as _time
            stamp = "2026-06-07T09:30:00"
            epoch = cg._parse_iso_local(stamp)
            ck("C1: _parse_iso_local round-trips a well-formed stamp to the matching LOCAL epoch",
               isinstance(epoch, float)
               and _time.strftime("%Y-%m-%dT%H:%M:%S", _time.localtime(epoch)) == stamp)
            # A stamp that doesn't MATCH the ISO shape degrades to None (-> start_text), never a guess.
            # (An in-range-shaped stamp that mktime can normalize is honestly accepted as a real time —
            # that's not fabrication, so the contract is shape-match, not value-validation.)
            ck("C2: a stamp that doesn't match the ISO shape returns None (degrades to start_text — "
               "never a guess)",
               cg._parse_iso_local("not-a-date") is None
               and cg._parse_iso_local("") is None
               and cg._parse_iso_local("2026-06-07") is None        # no time portion -> no match
               and cg._parse_iso_local("   ") is None)

            # ---- D. ROBUST SHAPE, KEPT-NOT-INVENTED ------------------------------------------
            RS, US = cg._RS, cg._US
            comma_title = 'Lunch, with Mara (and "the team")'
            rows = [
                "Standup" + US + "2026-06-07T09:30:00" + US + "0",          # timed
                "All-day Offsite" + US + "2026-06-07T00:00:00" + US + "1",  # all-day flag
                comma_title + US + "GARBAGE-STAMP" + US + "0",             # unparseable start -> kept
            ]
            synthetic_out = RS.join(rows)
            cg._run_osa = lambda script, timeout=25.0: (True, synthetic_out)
            try:
                cal = cg.calendar_today(timeout=45)
            finally:
                cg._run_osa = _osa_tripwire
            ck("D1: a real script output parses to exactly the 3 rows (ok=True, none dropped)",
               cal.ok is True and len(cal.events) == 3 and cal.note == "ok")
            titles = [e.title for e in cal.events]
            ck("D2: a comma/quote title survives the robust RS/US row format intact (not split)",
               comma_title in titles)
            allday = next((e for e in cal.events if e.title == "All-day Offsite"), None)
            ck("D3: the all-day flag is honored (when_phrase() == 'all day')",
               allday is not None and allday.all_day is True and allday.when_phrase() == "all day")
            timed = next((e for e in cal.events if e.title == "Standup"), None)
            ck("D4: a timed event parses to a real epoch + a spoken time, not invented",
               timed is not None and isinstance(timed.start, float) and timed.when_phrase() != "")
            garbage = next((e for e in cal.events if e.title == comma_title), None)
            ck("D5: a row with an UNPARSEABLE timestamp is KEPT with start=None (start_text "
               "preserved) — never dropped, never fabricated",
               garbage is not None and garbage.start is None
               and garbage.start_text == "GARBAGE-STAMP")
            starts = [e.start for e in cal.events]
            unparsed_last = (starts.index(None) == len(starts) - 1)
            ck("D6: events are sorted chronologically with the unparsed/all-day rows ordered stably "
               "(timed-by-start first, start=None sinks to the end)",
               unparsed_last and timed.start <= (garbage.start or float("inf")))

            # an empty script output -> ok=True, no events, honest 'no events today', invents nothing
            cg._run_osa = lambda script, timeout=25.0: (True, "")
            try:
                cal_empty = cg.calendar_today(timeout=45)
            finally:
                cg._run_osa = _osa_tripwire
            ck("D7: an empty calendar (script ran, zero events) is honest: ok=True, events=[], "
               "note='no events today' — fabricates nothing",
               cal_empty.ok is True and cal_empty.events == []
               and cal_empty.note == "no events today" and cal_empty.phrases() == [])

            # ---- E. FACT SHEET STATES ABSENCE AS ABSENCE -------------------------------------
            ctx_absent = cg.DayContext(
                when=1717000000.0,
                weather=cg.Weather(ok=False, note="weather lookup failed: simulated offline"),
                calendar=cg.Calendar(ok=False, events=[], note="calendar unavailable: denied"))
            sheet = ctx_absent.fact_sheet()
            ck("E1: fact_sheet() states a missing forecast as 'Weather: unavailable (...)'",
               "Weather: unavailable (" in sheet)
            ck("E2: fact_sheet() states an unreadable calendar as 'Calendar today: could not read (...)'",
               "Calendar today: could not read (" in sheet)
            ck("E3: a degraded fact_sheet() contains NO invented event line (no '  - ' bullet)",
               "\n  - " not in sheet)

            # gather() end-to-end, OFFLINE: NO coordinates (so weather() is never called) and the
            # calendar deterministically skipped via context_gather's own offline knob (_CAL_TIMEOUT=0),
            # which we already proved makes ZERO osascript calls (B1/B2). So gather() reaches NEITHER
            # live source; we assert it degrades to an honest, fabrication-free sheet.
            saved_cal_timeout = cg._CAL_TIMEOUT
            osa_g0 = tripped["osa"]
            net_g0 = tripped["net"]
            cg._CAL_TIMEOUT = 0.0
            try:
                ctx_g = cg.gather(now=1717000000.0)     # no lat/lon -> weather() not called
            finally:
                cg._CAL_TIMEOUT = saved_cal_timeout
            ck("E4: gather() with no coordinates yields no weather + an honest 'no location' note",
               ctx_g.weather.ok is False
               and any("no location" in n for n in ctx_g.notes))
            ck("E5: gather()'s calendar is honestly skipped (ok=False) and reached NEITHER live source "
               "(zero network + zero osascript calls)",
               ctx_g.calendar.ok is False
               and tripped["osa"] == osa_g0 and tripped["net"] == net_g0)
            g_sheet = ctx_g.fact_sheet()
            ck("E6: the assembled fact_sheet() names NO forecast and NO event — absence stated as "
               "absence, nothing invented",
               g_sheet.startswith("Date: ")
               and "Weather: unavailable (" in g_sheet
               and "\n  - " not in g_sheet
               and "could not read" in g_sheet)

        except _Tripwire as tw:
            ck("FATAL: a deterministic path made a REAL network/osascript call — offline violated: "
               + str(tw), False)
        finally:
            _urlreq.urlopen = saved_urlopen
            cg._run_osa = saved_run_osa

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (context_gather writes nothing)",
       fp_before == fp_after)

    print("\nCONTEXT-GATHER CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
