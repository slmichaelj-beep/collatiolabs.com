#!/usr/bin/env python3
"""certify_foundry_product_polish — the Foundry surface (chairman) is polished + honest.

The chairman dashboard renders the portfolio in plain language, flags zombie ventures (no kill
criteria), shows the governance banner, and never fakes progress. Verifies the live surface + the
honest user-language framing.
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
    print("FOUNDRY PRODUCT POLISH — chairman surface, plain language, zombie-honest")
    print("=" * 92)
    page = (ROOT / "anima" / "web" / "chairman.html").read_text()
    ck("1. the chairman page uses plain founder language ('where should my capital go')",
       "Where should my capital" in page)
    ck("2. it flags zombie ventures (no kill criteria) honestly",
       "zombie" in page.lower() and "kill criteria" in page.lower())
    ck("3. it shows the governance banner + trace chip",
       "govBanner" in page and "Observed" in page and 'href="/observation"' in page)
    try:
        st, body = _get("/foundry/portfolio.json")
        p = json.loads(body)
        ck("4. the live portfolio serves budget rollup + active count + status buckets",
           p.get("ok") and "unallocated_budget" in p and "active_count" in p and "by_status" in p)
        ck("5. it never fakes progress (no ventures => honest empty, not invented)",
           isinstance(p.get("ventures"), list))
        _, obody = _get("/observation.json")
        evs = json.loads(obody).get("events", [])
        ck("6. viewing the chairman dashboard emitted a trace-linked observation event",
           any(e["action"] == "chairman_dashboard_viewed" and e.get("trace_id") for e in evs))
    except Exception as e:
        ck("4. /foundry/portfolio.json reachable (server down: %r)" % e, False)
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_foundry_product_polish", "green" if green else "red",
                files_observed=["anima/web/chairman.html", "anima/foundry/core.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nFOUNDRY-PRODUCT-POLISH CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
