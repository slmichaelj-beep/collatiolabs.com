#!/usr/bin/env python3
"""certify_software_commercialization — the commercialization loop is real, honest, and governed.

asset inventory -> first sellable wedge -> offer package -> sales pipeline -> approval queue ->
board revenue briefing. No asset claimed sellable without an audit; no wedge from an un-audited
asset; pricing is a recommendation (binding needs approval); revenue truth keeps activity !=
pipeline != closed revenue; the loop is observed + governance-visible + linked.
"""
from __future__ import annotations

import json, sys, tempfile, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.commercial import assets, wedge, offer, revenue_briefing   # noqa: E402

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("SOFTWARE COMMERCIALIZATION — assets -> wedge -> offer -> pipeline -> revenue (governed)")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "CommCert"
        import anima.company.storage as cs
        old = cs.STORE; cs.STORE = st
        try:
            # 1. inventory seeds honestly (everything needs_audit; nothing auto-sellable)
            s = assets.seed(N, store=st)
            inv = assets.inventory(N, store=st)
            ck("1. asset inventory seeds; every asset starts needs_audit (nothing auto-sellable)",
               s["ok"] and inv["sellable"] == [] and inv["needs_audit"])
            a0 = inv["assets"][0]["asset_id"]
            # 2. no wedge from an un-audited asset
            ck("2. a wedge from a needs_audit asset is REFUSED",
               not wedge.propose(N, a0, narrow_use_case="x", store=st)["ok"])
            # 3. advancing readiness requires findings
            ck("3. advancing to sellable requires recorded audit findings",
               not assets.audit_readiness(N, a0, readiness="sellable", findings="", store=st)["ok"])
            assets.audit_readiness(N, a0, readiness="sellable",
                                   findings="narrow use case demoable; one pilot candidate", store=st)
            # 4. wedge requires a narrow use case
            ck("4. a wedge requires a NARROW use case",
               not wedge.propose(N, a0, narrow_use_case="", store=st)["ok"])
            w = wedge.propose(N, a0, narrow_use_case="one-click invoicing for solo freelancers", store=st)
            ck("5. a wedge from an audited asset is proposed", w["ok"])
            wid = w["wedge"]["wedge_id"]
            # 6. offer only on an approved wedge
            ck("6. an offer cannot be built on an un-approved wedge",
               not offer.build(N, wid, icp="x", value_prop="y", store=st)["ok"])
            wedge.approve(N, wid, store=st)
            o = offer.build(N, wid, icp="solo freelancers", value_prop="save 5h/mo on invoicing",
                            price_recommendation=49, store=st)
            ck("7. an offer builds on the approved wedge; price is a RECOMMENDATION not a commitment",
               o["ok"] and o["offer"]["price_is_commitment"] is False)
            ck("8. offer readiness audits the gaps (ICP/value/proof) honestly",
               offer.audit_readiness(N, o["offer"]["offer_id"], store=st)["ready"] is True)
            # 9. revenue briefing ties the loop together + keeps revenue truth
            rb = revenue_briefing.build(N, store=st)
            ck("9. the board revenue briefing distinguishes activity / pipeline / closed revenue",
               rb["loop"]["revenue_truth"]["closed_revenue"] == 0
               and "forecast" in rb["honesty"].lower())
            ck("10. the briefing names a concrete highest-leverage next move + shows governance",
               bool(rb["highest_leverage_next_move"]) and "governance" in rb)
        finally:
            cs.STORE = old

    # ---- live: the surfaces serve + emit observation + are governance-visible -------------------
    try:
        for r in ("/commercial", "/sales"):
            with urllib.request.urlopen("http://127.0.0.1:8765" + r, timeout=15) as resp:
                body = resp.read().decode()
            ck("L. %s serves a titled page with the governance banner" % r,
               resp.status == 200 and "govBanner" in body and "human-only" in body)
        with urllib.request.urlopen("http://127.0.0.1:8765/sales.json", timeout=15) as resp:
            sj = json.loads(resp.read())
        ck("L2. /sales.json returns the loop with revenue truth (closed != forecast honesty)",
           sj.get("ok") and "revenue_truth" in sj["loop"] and "forecast" in sj["honesty"].lower())
        with urllib.request.urlopen("http://127.0.0.1:8765/observation.json", timeout=10) as resp:
            obs = json.loads(resp.read())
        acts = {e["action"] for e in obs["events"]}
        ck("L3. viewing the surfaces emitted commercialization observation events",
           "software_asset_inventory_viewed" in acts and "revenue_briefing_generated" in acts)
    except Exception as e:
        ck("L. live commercial/sales surfaces reachable (server down: %r)" % e, False)

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_software_commercialization", "green" if green else "red",
                files_observed=["anima/commercial/assets.py", "anima/commercial/wedge.py",
                                "anima/commercial/offer.py", "anima/commercial/revenue_briefing.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nSOFTWARE-COMMERCIALIZATION CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
