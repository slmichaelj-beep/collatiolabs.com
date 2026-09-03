#!/usr/bin/env python3
"""certify_chairman_dashboard — the chairman sees portfolio truth, live."""
from __future__ import annotations

import json, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("CHAIRMAN DASHBOARD — portfolio state, capital, ventures, evidence")
    print("=" * 92)
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/foundry/portfolio.json", timeout=10) as r:
            p = json.loads(r.read())
        ck("1. LIVE /foundry/portfolio.json serves portfolio state",
           p.get("ok") is True and "total_budget" in p and "active_count" in p)
        ck("2. budget rollup present (total/allocated/unallocated)",
           "allocated_budget" in p and "unallocated_budget" in p)
        page = (ROOT / "anima" / "web" / "chairman.html").read_text()
        ck("3. /chairman page exists + wired to the portfolio + flags zombie ventures",
           "Chairman" in page and "/foundry/portfolio.json" in page and "zombie" in page.lower())
        src = (ROOT / "anima" / "server.py").read_text()
        ck("4. /chairman + /foundry/portfolio.json routes wired",
           '"/chairman"' in src and "/foundry/portfolio.json" in src)
    except Exception as e:
        ck("1. live chairman surface reachable (server down: %r)" % e, False)
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_chairman_dashboard", "green" if green else "red",
                files_observed=["anima/web/chairman.html"], duration_sec=time.perf_counter() - t0,
                failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nCHAIRMAN-DASHBOARD CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
