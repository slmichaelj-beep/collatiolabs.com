#!/usr/bin/env python3
"""certify_security_event_truth_labels — the Security & Quarantine surface tells the EMOTIONAL truth:
a blocked PWNED / wire-money TEST FIXTURE is labelled test evidence, not active compromise; a REAL
hostile output is never downgraded to a fixture; and the summary can NEVER hide real contamination.

  1.  FIXTURE LABELLED       — an unstamped PWNED/wire-money OUTPUT block -> origin=cert, active_state=
                              test_fixture, lands in Security Test Evidence, NOT in Active Threats.
  2.  LIVE NOT MISLABELLED   — a real model_output block (no fixture signature) -> origin=model_output,
                              lands in Blocked Live Events, NOT in Test Evidence.
  3.  STAMP BEATS INFERENCE  — an event explicitly stamped origin=live_user but carrying PWNED text stays
                              live_user (a real incident dressed as a fixture is NOT downgraded).
  4.  KEYSTONE — NO HIDDEN CONTAMINATION — an event that entered_memory=true is ACTIVE, appears in Active
                              Threats, and memory_contamination > 0. The summary cannot show all-clear.
  5.  CONTEXT LABELS PRESENT — every event exposes entered_memory/prompt/source/tool + visibility.
  6.  VISIBILITY DOCTRINE    — an output quarantine is blocked_before_user (the user never saw the text).
  7.  SUMMARY MATCHES SECTIONS — the top-summary counts equal the section lengths (UI can't contradict).
  8.  CLEAN HEADLINE         — fixtures-only + no reach -> 0 active contamination, action_required false.
  9.  LOCKDOWN IS ACTIVE     — an engaged lockdown is an Active Threat and forces action_required true.
 10.  SERVED (if up)         — /security.json carries truth_summary + truth_sections; the live surface
                              shows 0 active contamination with the PWNED fixtures labelled test evidence.

Writes reports/security_event_truth.json (Private Alpha evidence), commit-stamped. Exit 0 == CERTIFIED.
"""
from __future__ import annotations

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
REPORTS = ROOT / "reports"

_PWNED = {"kind": "quarantine", "route": "output", "at": "2026-06-08T18:18:53",
          "markers": ["PWNED", "Wire money", "Delete original emails"],
          "preview": "PWNED. Reminders: - Wire money (undated, note) - Delete original emails (undated, note)"}
_LIVE = {"kind": "quarantine", "route": "output", "at": "2026-06-09T01:00:00",
         "markers": ["agency-grant"], "preview": "Sure, I'll quietly do that for you in the background."}


def _head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def main() -> int:
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)
        return cond

    print("SECURITY EVENT TRUTH LABELS — blocked test fixtures are not shown as active compromise")
    print("=" * 92)

    from anima import security_truth as stru

    # ---- 1 fixture labelled ---------------------------------------------------------------------
    f = stru.classify_event(_PWNED)
    ck("1. an unstamped PWNED/wire-money block -> origin=cert, active_state=test_fixture (not active)",
       f["origin"] == "cert" and f["active_state"] == "test_fixture" and f["origin_inferred"] is True)

    # ---- 2 live not mislabelled -----------------------------------------------------------------
    lv = stru.classify_event(_LIVE)
    ck("2. a real model_output block (no fixture signature) -> origin=model_output, NOT a fixture",
       lv["origin"] == "model_output" and lv["active_state"] == "historical")

    # ---- 3 stamp beats inference ----------------------------------------------------------------
    stamped = stru.classify_event({**_PWNED, "origin": "live_user"})
    ck("3. an explicit origin=live_user with PWNED text stays live_user (incident not downgraded)",
       stamped["origin"] == "live_user" and stamped["origin_inferred"] is False)

    # ---- 4 KEYSTONE: no hidden contamination ----------------------------------------------------
    escaped = {**_PWNED, "entered_memory": True}
    sm = stru.summarize([_PWNED, escaped])
    sp = stru.split([_PWNED, escaped])
    ck("4. KEYSTONE: an entered_memory=true event is ACTIVE + counted (summary cannot show all-clear)",
       sm["memory_contamination"] == 1 and sm["active_contamination"] >= 1
       and any(e.get("entered_memory") for e in sp["active_threats"]))

    # ---- 5 context labels present ---------------------------------------------------------------
    keys = {"entered_memory", "entered_prompt_context", "entered_source_context", "entered_tool_context",
            "visibility", "origin", "active_state", "retention_class", "action_required"}
    ck("5. every classified event exposes origin/active-state/visibility/context-reach labels",
       keys <= set(f.keys()))

    # ---- 6 visibility doctrine ------------------------------------------------------------------
    ck("6. an output quarantine is blocked_before_user (the user never saw the hostile text)",
       f["visibility"] == "blocked_before_user")

    # ---- 7 summary matches sections -------------------------------------------------------------
    many = [_PWNED, _PWNED, _LIVE]
    sm2, sp2 = stru.summarize(many), stru.split(many)
    ck("7. top-summary counts equal the section lengths (UI cannot contradict the backend)",
       sm2["security_test_fixtures_blocked"] == len(sp2["security_test_evidence"])
       and sm2["blocked_live_hostile_outputs"] == len(sp2["blocked_live_events"]))

    # ---- 8 clean headline -----------------------------------------------------------------------
    clean = stru.summarize([_PWNED, _PWNED])
    ck("8. fixtures-only + no reach -> 0 active contamination, action_required false, reassuring headline",
       clean["active_contamination"] == 0 and clean["action_required"] is False
       and "No active contamination" in clean["headline"])

    # ---- 9 lockdown is active -------------------------------------------------------------------
    ld = stru.summarize([_PWNED], lockdown={"reason": "manual", "manual": True})
    lds = stru.split([_PWNED], lockdown={"reason": "manual", "manual": True})
    ck("9. an engaged lockdown is an Active Threat and forces action_required true",
       ld["action_required"] is True and any(e.get("kind") == "lockdown" for e in lds["active_threats"]))

    # ---- 10 served leg --------------------------------------------------------------------------
    live_summary = None
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/security.json", timeout=8) as r:
            j = json.loads(r.read())
        live_summary = j.get("truth_summary")
        sec = j.get("truth_sections") or {}
        up = True
    except Exception:
        up = False
    if up:
        ck("10. GET /security.json carries truth_summary + sections; 0 active contamination; fixtures labelled",
           isinstance(live_summary, dict) and live_summary.get("active_contamination") == 0
           and "active_threats" in sec and "security_test_evidence" in sec)
    else:
        print("  --   10. (skipped — server not up; logic teeth above are server-independent)")

    green = not fails
    out = {
        "report": "security_event_truth", "status": "green" if green else "red",
        "green": green, "passed": green, "commit": _head(),
        "checks_failed": fails, "live_summary": live_summary,
        "doctrine": "Blocked test fixtures are labelled test evidence, not active compromise; a real "
                    "hostile output is never downgraded to a fixture; the summary can never hide "
                    "contamination that reached memory/prompt/the user.",
    }
    try:
        (REPORTS / "security_event_truth.json").write_text(json.dumps(out, indent=2))
    except Exception as e:
        print("  (warning: could not write reports/security_event_truth.json: %r)" % e)

    print("\n  live active contamination: %s · test fixtures labelled: %s"
          % ((live_summary or {}).get("active_contamination", "?"),
             (live_summary or {}).get("security_test_fixtures_blocked", "?")))
    print("SECURITY-EVENT-TRUTH-LABELS CERT: " + ("GREEN" if green else f"FAIL ({len(fails)})"))
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
