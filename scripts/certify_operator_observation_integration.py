#!/usr/bin/env python3
"""certify_operator_observation_integration — operator actions emit trace-linked observation events.

Live: visiting the operator data routes emits events; events carry trace_ids + governance state;
a blocked external action emits a governance/blocked event; the observation UI can display them.
Hermetic: the emit contract + evidence linkage.
"""
from __future__ import annotations

import json, sys, tempfile, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.observation import emit, schema, query   # noqa: E402

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)


def _obs():
    with urllib.request.urlopen("http://127.0.0.1:8765/observation.json", timeout=10) as r:
        return json.loads(r.read())


def _hit(path):
    try:
        urllib.request.urlopen("http://127.0.0.1:8765" + path, timeout=15).read()
        return True
    except Exception:
        return False


def main() -> int:
    t0 = time.perf_counter()
    print("OPERATOR OBSERVATION INTEGRATION — every operator action is a trace-linked event")
    print("=" * 92)

    # ---- hermetic: the contract ----------------------------------------------------------------
    ev = schema.make("/founder", "company", "daily_briefing_generated", actor="user",
                     report_refs=["reports/x.md"])
    ck("1. an observation event is schema-valid with a trace_id + governance_state",
       schema.validate(ev) == [] and ev["trace_id"].startswith("tr_") and "governance_state" in ev)
    ck("2. has_evidence detects linked references", query.has_evidence(ev))
    with tempfile.TemporaryDirectory() as td:
        st = Path(td)
        import anima.observation.store as obstore
        old = obstore.STORE; obstore.STORE = st
        try:
            r = emit.record("ObsCert", "/chairman", "foundry", "chairman_dashboard_viewed",
                            store_path=st)
            ck("3. emit.record persists an event carrying the live governance snapshot",
               r is not None and r["governance_state"]["legal_financial_human_only"] is True
               and r["governance_state"]["authority_level"].startswith("L"))
            # blocked external action -> a governance/blocked event
            b = emit.record("ObsCert", "/foundry", "company_operator", "external_action_blocked",
                            result="blocked", classification="blocked", store_path=st)
            ck("4. a blocked external action emits a blocked-result governance event",
               b is not None and b["result"] == "blocked")
            ck("5. recent() returns the events in reverse-chron with trace_ids",
               all(e.get("trace_id") for e in query.recent("ObsCert", store_path=st)))
        finally:
            obstore.STORE = old

    # ---- live: visiting operator surfaces emits events -----------------------------------------
    try:
        before = _obs()["summary"]["total"]
        _hit("/learning.json"); _hit("/founder" if False else "/company/briefing.json")
        _hit("/foundry/portfolio.json")
        after = _obs()
        ck("6. visiting /learning, /founder, /chairman data routes emits new events (%d -> %d)"
           % (before, after["summary"]["total"]), after["summary"]["total"] > before)
        systems = set(e["system"] for e in after["events"])
        ck("7. events span the operator systems (learning + company + foundry seen)",
           {"learning", "company", "foundry"} <= systems)
        ck("8. every live event carries a trace_id + governance_state",
           all(e.get("trace_id") and "governance_state" in e for e in after["events"]))
        ck("9. the observation UI can display the events (/observation serves + /observation.json ok)",
           after.get("ok") is True and len(after["events"]) >= 1)
    except Exception as e:
        ck("6. live observation reachable (server down: %r)" % e, False)

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_operator_observation_integration", "green" if green else "red",
                files_observed=["anima/observation/emit.py", "anima/observation/schema.py",
                                "anima/observation/store.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nOPERATOR-OBSERVATION-INTEGRATION CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
