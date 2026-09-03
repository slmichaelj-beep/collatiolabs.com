#!/usr/bin/env python3
"""certify_incident_response — the panic button + the SOC trail, proven behaviorally.

  1. SAFE STATE       — one lockdown() call forces EVERY outward capability OFF (mail/imessage/web/
                        host/calendar/reminders/notes/grow), even ones the user had enabled.
  2. AUDITED          — the lockdown is recorded (status.locked + reason) and written to the security
                        event trail.
  3. REVERSIBLE       — restore() lifts the lockdown and hands the user's STORED settings back, intact
                        (lockdown overrides, never deletes).
  4. IDEMPOTENT       — a second lockdown is safe; restore with nothing active is a no-op (False).
  5. SOC TRAIL        — security events are append-only, timestamped, and queryable (recent_events).

Hermetic (redirects .anima via the gate0 _temp_store). Exit 0 == CERTIFIED; 1 == FAIL.
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

_OUTWARD = ("mail", "imessage", "web", "host_awareness", "calendar", "reminders", "notes",
            "grow_intelligence")


def main() -> int:
    from anima import caps, incident
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("INCIDENT RESPONSE — the panic button + the SOC trail")
    print("=" * 92)

    with _temp_store():
        name = "IncidentCert"
        # the user has several capabilities turned ON
        c = caps.load(name)
        for k in ("mail", "imessage", "web", "host_awareness", "calendar"):
            c[k] = True
        caps.save(name, c)

        ck("0. baseline: the user's enabled caps read True before any incident",
           all(caps.enabled(name, k) for k in ("mail", "imessage", "web", "host_awareness", "calendar")))
        ck("0. starts unlocked", not incident.is_locked())

        # ---- 1. SAFE STATE ------------------------------------------------------------------
        incident.lockdown("certify drill")
        ck("1. lockdown forces EVERY outward capability OFF (even ones the user enabled)",
           incident.is_locked() and all(caps.enabled(name, k) is False for k in _OUTWARD))

        # ---- 2. AUDITED ---------------------------------------------------------------------
        st = incident.status()
        ck("2. the lockdown is recorded (status.locked + reason)",
           st.get("locked") is True and "drill" in str(st.get("lockdown", {}).get("reason", "")))
        ck("2. the lockdown is written to the security event trail",
           any(e.get("kind") == "lockdown" for e in incident.recent_events(10)))

        # ---- 4a. IDEMPOTENT lockdown --------------------------------------------------------
        incident.lockdown("again")
        ck("4. a second lockdown is safe (still locked, still all-off)",
           incident.is_locked() and caps.enabled(name, "mail") is False)

        # ---- 3. REVERSIBLE ------------------------------------------------------------------
        lifted = incident.restore()
        ck("3. restore lifts the lockdown",
           lifted is True and not incident.is_locked())
        ck("3. the user's STORED settings are handed back intact (override, not delete)",
           all(caps.enabled(name, k) for k in ("mail", "imessage", "web", "host_awareness", "calendar")))
        ck("3. the restore is audited",
           any(e.get("kind") == "restore" for e in incident.recent_events(10)))

        # ---- 4b. restore with nothing active is a no-op -------------------------------------
        ck("4. restore with no active lockdown is a safe no-op (returns False)",
           incident.restore() is False)

        # ---- 5. SOC TRAIL -------------------------------------------------------------------
        n0 = len(incident.recent_events(50))
        incident.security_event("test_probe", "a recorded security observation")
        evs = incident.recent_events(50)
        ck("5. the security event trail is append-only + queryable (newest event present, timestamped)",
           len(evs) == n0 + 1 and evs[-1].get("kind") == "test_probe" and bool(evs[-1].get("at")))

    # ---- caps integration is wired in the real module --------------------------------------
    caps_src = (ROOT / "anima" / "caps.py").read_text()
    ck("6. the caps gate itself honors lockdown (incident.is_locked() check inside caps.enabled)",
       "incident" in caps_src and "is_locked()" in caps_src)

    print("\nINCIDENT-RESPONSE CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
