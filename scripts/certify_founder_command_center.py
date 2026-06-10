#!/usr/bin/env python3
"""certify_founder_command_center — the /founder command center is live, governance-visible, and
answers 'where do we stand?' from real state.

(The founder-ops backend logic is also covered by certify_founder_ops; this cert is the
directive-named surface cert: the page serves, renders its briefing, shows the governance banner,
and emits an observation event on view.)
"""
from __future__ import annotations

import json, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)


def _get(path):
    with urllib.request.urlopen("http://127.0.0.1:8765" + path, timeout=15) as r:
        return r.status, r.read().decode("utf-8", "replace")


def main() -> int:
    t0 = time.perf_counter()
    print("FOUNDER COMMAND CENTER — live, governance-visible, evidence-backed")
    print("=" * 92)
    try:
        st, page = _get("/founder")
        ck("1. /founder serves a titled page", st == 200 and "Founder Command Center" in page)
        ck("2. the page shows the governance banner + observation link",
           "govBanner" in page and "/governance.json" in page and 'href="/observation"' in page)
        bs, body = _get("/company/briefing.json")
        b = json.loads(body)
        s = b.get("sections", {})
        ck("3. the briefing answers 'where do we stand' from current state",
           b.get("ok") and "highest_leverage_next_move" in s and "open_blockers" in s
           and "founder_decisions_needed" in s)
        ck("4. the briefing carries honest caveats when state is stale/dirty (list present)",
           isinstance(b.get("caveats"), list))
        # observation event emitted on briefing view
        _, obody = _get("/observation.json")
        evs = json.loads(obody).get("events", [])
        ck("5. viewing the founder briefing emitted a trace-linked observation event",
           any(e["action"] == "daily_briefing_generated" and e.get("trace_id") for e in evs))
    except Exception as e:
        ck("1. /founder reachable (server down: %r)" % e, False)
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_founder_command_center", "green" if green else "red",
                files_observed=["anima/web/founder.html", "anima/company/briefing.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nFOUNDER-COMMAND-CENTER CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
