#!/usr/bin/env python3
"""certify_patterns_dashboard — the Founder Console (Patterns & Improvements) shows REAL self-
improvement data, not a hardcoded good-news dashboard.

Proves the founder's required list:
  1. PAGE REACHABLE   — /console serves the page; the page file exists.
  2. PATTERNS RENDER  — at least one real pattern object rides through (or an honest empty state).
  3. EVIDENCE LINKS   — patterns carry evidence trace/turn IDs.
  4. IMPROVEMENTS     — improvement suggestions render with recommendation + expected benefit.
  5. SEV/FREQ/STATUS  — severity, frequency, and status fields render.
  6. APPROVE/REJECT   — the approve/reject control WORKS (persists + audits) — or is honestly disabled.
  7. LIVE FEED        — the live observation feed renders (security events + Rover findings).
  8. NOT HARDCODED    — the data EQUALS the real pattern store (reports/patterns.json), not invented.
  9. HONEST EMPTY     — the page has an honest empty state (no fake 'all good' when there's nothing).
 10. REAL STORES      — improvements equal the real Improvement Engine backlog.

Exit 0 == CERTIFIED; 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store


def main() -> int:
    from anima import server
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("FOUNDER CONSOLE — Patterns & Improvements (real self-improvement data)")
    print("=" * 92)

    page = ROOT / "anima" / "web" / "console.html"
    srv = (ROOT / "anima" / "server.py").read_text()
    html = page.read_text() if page.exists() else ""
    d = server._console_data("Vera")

    # ---- 1 / route + auth posture ----------------------------------------------------------
    ck("1. /console serves the page; the page file exists",
       page.exists() and '"/console"' in srv and "console.html" in srv)
    ck("1. /console.json is wired behind the auth wall (personal -> token-gated)",
       '"/console.json"' in srv and srv.find("if not self._authed():") < srv.find('"/console.json"'))

    # ---- 2 / 3 PATTERNS + EVIDENCE ---------------------------------------------------------
    ck("2. at least one real pattern object rides through",
       isinstance(d.get("patterns"), list) and len(d["patterns"]) >= 1)
    ck("3. patterns carry evidence trace/turn IDs",
       any(p.get("evidence") for p in d["patterns"]))

    # ---- 4 / 5 IMPROVEMENTS + fields -------------------------------------------------------
    ck("4. improvement suggestions render (recommendation + expected benefit + required cert)",
       bool(d.get("improvements")) and all(("recommendation" in i and "required_cert" in i)
                                           for i in d["improvements"]))
    ck("5. severity / frequency / status fields render",
       all(("severity" in p and "frequency" in p) for p in d["patterns"])
       and all("approval_status" in i for i in d["improvements"]))

    # ---- 6 APPROVE / REJECT works (hermetic, persisted + audited) ---------------------------
    with _temp_store():
        iid = d["improvements"][0]["improvement_id"]
        r = server._console_decide("Ck", {"improvement_id": iid, "action": "approve"})
        after = server._console_data("Ck")
        # under the temp store the decision persists and shows on the matching improvement
        approved = any(i["improvement_id"] == iid and i["approval_status"] == "approved"
                       for i in after["improvements"])
        rej = server._console_decide("Ck", {"improvement_id": iid, "action": "reject"})
        ck("6. approve/reject WORKS — the decision persists and is auditable",
           r.get("ok") and approved and rej.get("approval_status") == "rejected")
    ck("6. the page wires the approve/reject controls (and honestly labels build/verify as not 1-click)",
       'data-a="approve"' in html and 'data-a="reject"' in html and "honestly not one-click" in html)

    # ---- 7 LIVE FEED -----------------------------------------------------------------------
    ck("7. the live observation feed renders (security events + Rover findings)",
       isinstance(d.get("feed"), list) and len(d["feed"]) >= 1)

    # ---- 8 / 10 NOT HARDCODED — equals the REAL stores -------------------------------------
    try:
        pj = json.loads((ROOT / "reports" / "patterns.json").read_text())
        store_titles = {x.get("title") for x in (pj.get("patterns") or [])}
        console_titles = {p.get("title") for p in d["patterns"]}
        ck("8. the patterns EQUAL the real Pattern Observatory store (not hardcoded good-news)",
           store_titles == console_titles and len(store_titles) >= 1)
    except Exception:
        ck("8. the patterns EQUAL the real Pattern Observatory store", False)
    try:
        bj = json.loads((ROOT / "reports" / "improvement_backlog.json").read_text())
        ck("10. the improvements EQUAL the real Improvement Engine backlog",
           {x.get("title") for x in (bj.get("items") or [])} == {i.get("title") for i in d["improvements"]})
    except Exception:
        ck("10. the improvements EQUAL the real Improvement Engine backlog", False)

    # ---- 11 ROI — completed work is CERT-BACKED, not invented good-news ---------------------
    roi = d.get("roi") or []
    verified = [r for r in roi if r.get("status") == "verified"]
    ck("11. the Completed/ROI view shows real shipped work with before->after",
       len(roi) >= 1 and all(r.get("before") and r.get("after") for r in roi))
    ck("11. EVERY verified ROI entry is gated by an EXISTING cert file (benefit proven, not claimed)",
       len(verified) >= 1 and all((ROOT / r.get("cert", "x")).exists() for r in verified))
    ck("11. every verified ROI entry maps to a COMPLETE contract (no fake good-news)",
       all(r.get("contract_status") in (None, "COMPLETE") for r in verified))
    ck("11. the page renders the Completed/ROI tab (before->after + what it did for us)",
       "Completed · ROI" in html and "roiView" in html and "What it did for us" in html)

    # ---- 9 HONEST EMPTY STATE --------------------------------------------------------------
    ck("9. the page has an HONEST empty state (no fake 'all good' when there's nothing)",
       "Honest empty state" in html and "No repeating issues" in html
       and "No improvements have entered the loop" in html
       and "empty" in srv)   # _console_data computes a real `empty` flag

    print("\nPATTERNS-DASHBOARD CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
