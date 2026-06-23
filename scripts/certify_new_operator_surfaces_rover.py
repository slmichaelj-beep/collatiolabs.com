#!/usr/bin/env python3
"""certify_new_operator_surfaces_rover — real-browser proof of every operator surface, with the
governance banner + trace chip rendered. Writes reports/new_operator_surfaces_rover.{json,md}.
"""
from __future__ import annotations

import json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

oks, fails = [], []
rows = []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)

# (route, title fragment, body fragment, governance-banner expected?)
SURFACES = [
    ("/learning", "Learning Integrity", "Active Memories", False),
    ("/founder", "Where do we stand", "Founder decisions needed", True),
    ("/chairman", "Where should my capital", "Ventures", True),
    ("/observation", "Observation", "evidence", False),
    ("/commercial", "first sale", "asset inventory", True),
    ("/sales", "selling going", "Revenue truth", True),
    ("/board/revenue", "revenue actually stands", "closed revenue", True),
    ("/opportunities", "opportunities i can see", "highest-leverage next move", True),
    ("/collatio", "collatio labs", "entity status", True),
    ("/teams", "teams i can build", "work orders", True),
    ("/workforce", "where the work is", "service catalog", True),
    ("/self", "what i am", "frozen systems", True),
    ("/revenue", "make money now", "revenue truth board", True),
    ("/revenue/swarm", "revenue experiments", "portfolio truth", True),
    ("/compounding", "compound it", "portfolio allocations", True),
    ("/revenue/intelligence", "learned from trying to make money", "revenue graph", True),
    ("/distribution", "where buyers come from", "buyer database", True),
    ("/trust/moat", "trust moat", "proof library", True),
    ("/resources", "what i need to grow", "bottlenecks", True),
    ("/empire", "hosts, work routing, capital", "capital decisions", True),
    ("/revenue/cash", "16,000 net profit by 2026-06-28", "remaining gap", True),
    ("/marketplaces/fiverr", "fiverr as a governed service channel", "policy (enforced)", True),
    ("/pipeline", "upwork bid pipeline", "recent triage", True),
]


def main() -> int:
    t0 = time.perf_counter()
    print("NEW OPERATOR SURFACES ROVER — browser-proven, governance-visible, trace-linked")
    print("=" * 92)
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        ck("playwright available", False); print("  (%r)" % e); return 1

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        for route, tfrag, bfrag, gov in SURFACES:
            errs = []
            pg = b.new_page()
            pg.on("console", lambda m, E=errs: E.append(m.text) if m.type == "error" else None)
            pg.on("pageerror", lambda e, E=errs: E.append(str(e)))
            rec = {"route": route, "ok": False}
            try:
                pg.goto("http://127.0.0.1:8765" + route, wait_until="domcontentloaded", timeout=25000)
                title = pg.title()
                try:
                    pg.wait_for_function(
                        "f => document.body.innerText.toLowerCase().includes(f.toLowerCase())",
                        arg=bfrag, timeout=12000)
                    rendered = True
                except Exception:
                    rendered = False
                body = pg.inner_text("body")
                served = (tfrag.lower() in (title + " " + body).lower()) and "404" not in title
                ck("%s served + titled (%r)" % (route, title), served)
                ck("%s rendered its data (not blank/loading)" % route, rendered)
                ck("%s console/page clean (errs=%d)" % (route, len(errs)), not errs)
                if gov:
                    gov_ok = "Governance:" in body and ("human-only" in body.lower())
                    ck("%s shows the governance banner (authority/external/legal/kill)" % route, gov_ok)
                    ck("%s shows the trace/observed chip" % route, "Observed" in body)
                rec.update({"ok": served and rendered and not errs, "title": title,
                            "rendered": rendered, "console_errors": len(errs), "governance": gov})
            except Exception as e:
                ck("%s reachable (%r)" % (route, e), False)
                rec["error"] = repr(e)
            finally:
                rows.append(rec); pg.close()
        b.close()

    # reports
    rp = ROOT / "reports"; rp.mkdir(exist_ok=True)
    payload = {"report": "new_operator_surfaces_rover", "surfaces": rows,
               "passed": sum(1 for r in rows if r.get("ok")), "total": len(rows)}
    (rp / "new_operator_surfaces_rover.json").write_text(json.dumps(payload, indent=1))
    md = ["# New operator surfaces — real-browser rover", ""]
    md += ["- %s: %s (console errors: %s)" % (r["route"], "OK" if r.get("ok") else "FAIL",
                                              r.get("console_errors", "?")) for r in rows]
    (rp / "new_operator_surfaces_rover.md").write_text("\n".join(md) + "\n")

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_new_operator_surfaces_rover", "green" if green else "red",
                files_observed=["anima/web/founder.html", "anima/web/chairman.html",
                                "anima/web/observation.html", "anima/web/learning.html"],
                report_paths=["reports/new_operator_surfaces_rover.json"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nNEW-OPERATOR-SURFACES-ROVER CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
