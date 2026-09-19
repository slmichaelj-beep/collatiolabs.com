#!/usr/bin/env python3
"""certify_verification_detail_tabs — the Verification Dashboard detail tabs carry ROW-LEVEL EVIDENCE,
not summary-only verdicts. KEYSTONE: a tab that reads green MUST have at least one contributing-feature
row backed by real cert evidence — a green tab can never be evidence-empty. Rows are read from the real
live-path audit (reports/live_path_results.json) + per-tab enrichment from real reports.

Covers the 8 directive tabs: performance, host_reality, ai_security, consent_privacy, recovery,
rover_journeys, renegade, observation_bundle. (The thin per-tab certs certify_*_detail_tab.py delegate
to verify_tab() here so each tab has its own named cert as the directive lists.)

  1. ALL 8 TABS PRESENT      — detail.all_details() returns every required tab with a label.
  2. KEYSTONE — NO GREEN WITHOUT ROWS — every green/amber tab has >=1 row AND has_row_evidence; a green
                             tab with zero evidence rows is a hard fail.
  3. ROWS ARE REAL           — each row maps to a real feature in reports/live_path_results.json with the
                             same status (rows are not invented).
  4. ENRICHMENT FROM REPORTS — performance carries measured latency + findings; ai_security the security
                             truth summary; rover the founder_lamar journey — all from real report files.
  5. UI WIRED                — verification.html renders detailRows() for all 8 tabs.
  6. SERVED (if up)          — /verification.json carries `detail` with the 8 tabs, each with rows.

Exit 0 == CERTIFIED.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
REPORTS = ROOT / "reports"
TABS = ["performance", "host_reality", "ai_security", "consent_privacy", "recovery",
        "rover_journeys", "renegade", "observation_bundle"]


def verify_tab(tab: str) -> int:
    """Single-tab gate (used by the thin per-tab certs). 0 == that tab has real row-level evidence."""
    from anima.verification import detail
    dt = detail.tab_detail(tab)
    ok = bool(dt.get("rows")) and dt.get("has_row_evidence") is True
    print(("  ok   " if ok else "  XX   ") + "%s: %d rows · rolled=%s · row-evidence=%s"
          % (tab, dt.get("row_count", 0), dt.get("rolled_status"), dt.get("has_row_evidence")))
    return 0 if ok else 1


def main() -> int:
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("VERIFICATION DETAIL TABS — every tab carries row-level evidence (no summary-only green)")
    print("=" * 92)

    from anima.verification import detail
    d = detail.all_details()

    ck("1. all 8 detail tabs present, each labelled", set(TABS) <= set(d.keys())
       and all(d[t].get("label") for t in TABS))

    # ---- 2 KEYSTONE: a green/amber tab must have row-level evidence ------------------------------
    smap = {"COMPLETE": "green"}
    keystone_ok, bad = True, []
    for t in TABS:
        dt = d[t]
        rolled = dt.get("rolled_status")
        if rolled in ("green", "amber"):
            if not (dt.get("rows") and dt.get("has_row_evidence")):
                keystone_ok = False
                bad.append(t)
    ck("2. KEYSTONE: every green/amber tab has >=1 evidence row (no summary-only green)%s"
       % (" — offenders: " + ", ".join(bad) if bad else ""), keystone_ok)

    # ---- 3 rows are real (map to live_path_results.json) ----------------------------------------
    try:
        lp = json.loads((REPORTS / "live_path_results.json").read_text())
        items = lp if isinstance(lp, list) else lp.get("features", lp.get("results", []))
        by = {x.get("feature"): (x.get("status") or "") for x in items}
    except Exception:
        by = {}
    real = True
    for t in TABS:
        for r in d[t]["rows"]:
            if r["feature"] not in by or by[r["feature"]] != r["status"]:
                real = False
    ck("3. every row maps to a real live-path feature with the same status (rows not invented)",
       real and bool(by))

    # ---- 4 enrichment from real reports ---------------------------------------------------------
    perf = d["performance"]["enrichment"]
    sec = d["ai_security"]["enrichment"]
    rov = d["rover_journeys"]["enrichment"]
    ck("4. enrichment is real: performance measured-latency+findings, ai_security truth-summary, rover founder_lamar",
       bool(perf.get("measured_latency_ms")) and "findings" in perf
       and isinstance(sec.get("truth_summary"), dict)
       and isinstance(rov.get("founder_lamar"), dict))

    # ---- 5 UI wired -----------------------------------------------------------------------------
    html = (ROOT / "anima" / "web" / "verification.html").read_text()
    ui_ok = "function detailRows(" in html and all(("detailRows('" + t + "')") in html for t in TABS)
    ck("5. verification.html renders detailRows() for all 8 detail tabs", ui_ok)

    # ---- 6 served leg ---------------------------------------------------------------------------
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/verification.json", timeout=8) as r:
            served = json.loads(r.read()).get("detail", {})
        up = True
    except Exception:
        up = False
    if up:
        ck("6. GET /verification.json carries `detail` with the 8 tabs, each with rows",
           set(TABS) <= set(served.keys()) and all(served[t].get("rows") for t in TABS))
    else:
        print("  --   6. (skipped — server not up; logic teeth above are server-independent)")

    total_rows = sum(d[t]["row_count"] for t in TABS)
    print("\n  tabs: %d · total evidence rows: %d" % (len(TABS), total_rows))
    print("VERIFICATION-DETAIL-TABS CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
