#!/usr/bin/env python3
"""certify_market_vision_engine — the full opportunity-intelligence loop, every gate.

Sources (blocked/needs_review/forbidden refused) → cited signals (uncited refused) → mining
(uncited competitor/privacy/pricing refused; single complaint low-confidence) → product gaps
(>=2 evidence classes) → thesis (assumptions/risks/evidence; build downgraded w/o validation) →
scoring (low-conf cap; legal-risk ceiling) → ethical model (data-sale refused) → validation
(success/kill/budget/approval) → portfolio (killed can't advance) → routers (blocked asset not
routed; venture needs approval+budget+validation) → briefing (activity != revenue).
"""
from __future__ import annotations

import sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from anima.market_vision import (source_registry as src, signals as sig, mining, product_gap as pg,  # noqa: E402
                                 asset_monetization as mon, thesis as th, scoring, business_model as bm,
                                 validation as val, portfolio as pf, routers, briefing, api)
from anima.commercial import assets as _assets, ip_license as _ip  # noqa: E402

oks, fails = [], []
def ck(l, c): (oks if c else fails).append(l); print(("  ok   " if c else "  XX   ") + l)


def main() -> int:
    t0 = time.perf_counter()
    print("MARKET VISION ENGINE — sources→signals→gaps→thesis→score→model→validate→route→brief")
    print("=" * 92)
    with tempfile.TemporaryDirectory() as td:
        st = Path(td); N = "MVCert"
        import anima.company.storage as cs
        old = cs.STORE; cs.STORE = st
        try:
            # --- sources ---
            src.seed(N, store=st)
            inv = src.inventory(N, store=st)
            ck("1. approved sources seeded; lawful classes only", inv["approved"])
            approved_id = next(s["source_id"] for s in inv["sources"] if s["status"] == "approved")
            ck("2. an approved source can be scanned", src.can_scan(N, approved_id, store=st)["allowed"])
            blocked = src.add_source(N, "Scrape-a-competitor-login", "web", legal_policy="blocked", store=st)["source"]
            ck("3. a blocked source CANNOT be scanned", not src.can_scan(N, blocked["source_id"], store=st)["allowed"])
            review = src.add_source(N, "Unknown forum", "forum", legal_policy="needs_review", store=st)["source"]
            ck("4. a needs_review source cannot back an active signal",
               not src.can_scan(N, review["source_id"], store=st)["allowed"])
            ck("5. a forbidden behavior is refused regardless of source",
               not src.can_scan(N, approved_id, behavior="illegal_scraping", store=st)["allowed"])

            # --- signals ---
            bad = sig.extract(N, approved_id, signal_type="pricing", text_summary="too pricey", store=st)
            ck("6. a citation-required source with no evidence ref is refused", not bad["ok"])
            s1 = sig.extract(N, approved_id, signal_type="pricing", text_summary="too pricey",
                             evidence_excerpt_ref="review#1", severity="high", frequency_hint="repeated", store=st)["signal"]
            s2 = sig.extract(N, approved_id, signal_type="complaint", text_summary="hate the tracking",
                             evidence_excerpt_ref="review#2", frequency_hint="repeated", store=st)["signal"]
            s3 = sig.extract(N, approved_id, signal_type="privacy", text_summary="don't trust data use",
                             evidence_excerpt_ref="review#3", frequency_hint="clustered", store=st)["signal"]
            bs = sig.extract(N, blocked["source_id"], signal_type="trend", text_summary="x",
                             evidence_excerpt_ref="y", store=st)
            ck("7. a blocked source produces no signal", not bs["ok"])

            # --- mining ---
            single = mining.cluster_complaints(N, theme="solo", signal_ids=[s1["signal_id"]], store=st)
            ck("8. a single-signal cluster is low-confidence", single["confidence"] == "low")
            ck("8b. a cluster never infers willingness-to-pay",
               "not inferable" in single["willingness_to_pay"])
            cl = mining.cluster_complaints(N, theme="pricing pain", industry="smb",
                                           signal_ids=[s1["signal_id"], s2["signal_id"], s3["signal_id"]], store=st)
            ck("9. multiple signals raise cluster confidence", cl["confidence"] in ("medium", "high"))
            nocite_comp = mining.analyze_competitor(N, competitor_name="BloatCo", market="smb",
                                                    weaknesses=["expensive"], evidence_signal_ids=[], store=st)
            ck("10. an uncited competitor claim is refused", not nocite_comp["ok"])
            comp = mining.analyze_competitor(N, competitor_name="BloatCo", market="smb",
                                             weaknesses=["expensive", "invasive"],
                                             evidence_signal_ids=[s1["signal_id"], s2["signal_id"]], store=st)["competitor"]
            ck("11. a cited competitor weakness record is produced", comp["evidence_refs"])
            nocite_priv = mining.detect_privacy_gap(N, market="smb", incumbent="BloatCo",
                                                    observed_practice="tracking", user_concern_signal_ids=[],
                                                    claims_data_sale=True, store=st)
            ck("12. a privacy gap with no cited concern is refused", not nocite_priv["ok"])
            priv = mining.detect_privacy_gap(N, market="smb", incumbent="BloatCo",
                                             observed_practice="opaque tracking",
                                             user_concern_signal_ids=[s2["signal_id"], s3["signal_id"]], store=st)["privacy_gap"]
            ck("13. a privacy gap distinguishes concern vs data-sale claim", priv["claim_type"] == "concern_only")
            nomonet = mining.scan_pricing(N, market="smb", incumbent_pricing_refs=["price#1"],
                                          pricing_pain_signal_ids=[s1["signal_id"]], est_cost_to_serve=2.0,
                                          paid_layer_options=[], store=st)
            ck("14. a pricing scan with no monetization layer is refused (no race-to-zero)", not nomonet["ok"])
            pscan = mining.scan_pricing(N, market="smb", incumbent_pricing_refs=["price#1"],
                                        pricing_pain_signal_ids=[s1["signal_id"]], est_cost_to_serve=2.0,
                                        paid_layer_options=["pro tier"], store=st)["pricing_gap"]
            ck("15. a valid pricing-arbitrage gap is produced", pscan["pricing_gap_id"])

            # --- product gap ---
            onec = pg.detect(N, gap_name="x", market="smb", customer_segment="solo",
                             proposed_solution="y", pain_cluster_refs=[cl["cluster_id"]], store=st)
            ck("16. a product gap with <2 evidence classes is refused", not onec["ok"])
            gap = pg.detect(N, gap_name="Privacy-first SMB workflow tool", market="smb",
                            customer_segment="solo operators", proposed_solution="local-first lite tool",
                            pain_cluster_refs=[cl["cluster_id"]], competitor_refs=[comp["competitor_id"]],
                            privacy_gap_refs=[priv["privacy_gap_id"]], why_now="privacy backlash",
                            why_lamar_can_win="local-first expertise", store=st)["gap"]
            ck("17. a product gap from >=3 evidence classes is high-confidence", gap["confidence"] == "high")

            # --- thesis ---
            noev = th.generate(N, title="t", one_line_thesis="o", customer="c", pain="p",
                               product_gap=gap["gap_id"], proposed_product="pp", business_model="bm",
                               evidence_refs=[], assumptions=["a"], risks=["r"], store=st)
            ck("18. a thesis with no evidence is refused", not noev["ok"])
            norisk = th.generate(N, title="t", one_line_thesis="o", customer="c", pain="p",
                                 product_gap=gap["gap_id"], proposed_product="pp", business_model="bm",
                                 evidence_refs=[gap["gap_id"]], assumptions=["a"], risks=[], store=st)
            ck("19. a thesis with no risks is refused", not norisk["ok"])
            t = th.generate(N, title="Privacy-first SMB lite tool", one_line_thesis="local-first alt to BloatCo",
                            customer="solo operators", pain="bloat + tracking", product_gap=gap["gap_id"],
                            proposed_product="local-first lite tool", business_model="free_core_paid_pro",
                            evidence_refs=gap["evidence_refs"], assumptions=["solos want local-first"],
                            risks=["distribution is hard"], privacy_first_angle="local-first, no tracking",
                            recommended_next_step="build_mvp", store=st)["thesis"]
            ck("20. a build recommendation is downgraded to validate without a validation plan",
               t["recommended_next_step"] == "validate" and t["build_downgraded_pending_validation"])

            # --- scoring ---
            full = {d: 3 for d in scoring.DIMENSIONS}
            legal_risky = scoring.score(N, t["opportunity_id"], scores=full,
                                        risks={"legal_regulatory_risk": 3}, confidence="high", store=st)["score"]
            ck("21. high market score cannot override high legal risk", legal_risky["recommendation"] == "research")
            lowconf = scoring.score(N, t["opportunity_id"], scores=full, risks={}, confidence="low", store=st)["score"]
            ck("22. low confidence CAPS the total score", lowconf["total_score"] <= lowconf["confidence_cap"])
            good = scoring.score(N, t["opportunity_id"], scores=full, risks={"build_difficulty": 1},
                                 confidence="high", store=st)["score"]
            ck("23. a strong, high-confidence opportunity scores high + gets a recommendation",
               good["total_score"] >= 70 and good["recommendation"])

            # --- business model ---
            datasale = bm.generate(N, t["opportunity_id"], family="sell_user_data", free_layer="f",
                                   paid_layers=["p"], store=st)
            ck("24. a data-sale business model is refused", not datasale["ok"])
            model = bm.generate(N, t["opportunity_id"], family="free_core_paid_pro", free_layer="local lite",
                                paid_layers=["pro: teams + sync"], data_policy="local_first", store=st)["model"]
            ck("25. an ethical model has a paid layer + no data sale", model["no_data_sale"] and model["paid_layers"])
            impossible = bm.model_free_core(N, t["opportunity_id"], what_is_free="all", what_is_paid="none",
                                            why_upgrade="?", cost_per_free_user=1.0, conversion_assumption=0.0, store=st)
            ck("26. an economically impossible free tier is refused", not impossible["ok"])

            # --- validation ---
            nokill = val.recommend(N, t["opportunity_id"], hypothesis="solos will sign up", method="landing_page_smoke_test",
                                   budget=200, duration="2w", success_criteria=["50 signups"], kill_criteria=[], store=st)
            ck("27. a validation experiment with no kill criteria is refused", not nokill["ok"])
            exp = val.recommend(N, t["opportunity_id"], hypothesis="solos will sign up",
                                method="landing_page_smoke_test", budget=200, duration="2 weeks",
                                success_criteria=["50 signups @ <$4 CAC"], kill_criteria=["<10 signups"],
                                expected_learning="real demand", store=st)["experiment"]
            ck("28. a valid experiment requires approval before spend/outreach",
               exp["required_approval"] and "approval" in exp["approval_note"].lower())

            # --- portfolio ---
            pf.set_status(N, t["opportunity_id"], "validate", store=st)
            pf.set_status(N, t["opportunity_id"], "killed", reason="failed validation", store=st)
            readvance = pf.set_status(N, t["opportunity_id"], "build_mvp", store=st)
            ck("29. a killed opportunity cannot be advanced", not readvance["ok"])
            port = pf.portfolio(N, store=st)
            ck("30. the killed opportunity is shown in the kill list (not hidden)", port["kill_list"])

            # --- routers ---
            _assets.seed(N, store=st)
            assets = _assets.inventory(N, store=st)["assets"]
            blocked_asset = assets[0]["asset_id"]   # unknown ownership => blocked
            r_blocked = routers.route_to_commercial(N, t["opportunity_id"], blocked_asset, store=st)
            ck("31. an IP-blocked asset is NOT routed to commercialization", not r_blocked["ok"])
            clear_asset = assets[1]["asset_id"]
            _ip.set_status(N, clear_asset, ip_status="owned", license_status="clear",
                           security_status="safe_to_demo", store=st)
            r_ok = routers.route_to_commercial(N, t["opportunity_id"], clear_asset, store=st)
            ck("32. an IP-clear asset-fit opportunity routes to commercialization", r_ok["ok"])
            v_noappr = routers.route_to_venture(N, t["opportunity_id"], approval_ref="", budget=500, store=st)
            ck("33. a venture route without approval is refused", not v_noappr["ok"])
            v_ok = routers.route_to_venture(N, t["opportunity_id"], approval_ref="lamar", budget=500, store=st)
            ck("34. a venture route is a PROPOSAL only — no venture launched", v_ok["ok"] and not v_ok["route"]["launched"])

            # --- monetization + briefing + dashboard ---
            m = mon.map_asset(N, clear_asset, buyer="solo ops", pain="manual work", store=st)
            ck("35. a cleared asset receives monetization paths", m["ok"] and m["monetization"]["best_path"])
            mblocked = mon.map_asset(N, blocked_asset, store=st)
            ck("36. a blocked asset is excluded from monetization", not mblocked["ok"])
            br = briefing.build(N, store=st)
            ck("37. the briefing separates activity from revenue (no fake revenue)",
               "not revenue" in br["honesty"].lower())
            ck("38. the briefing names a highest-leverage next move", br["highest_leverage_next_move"])
            dash = api.dashboard(N, store=st)
            ck("39. the dashboard payload assembles sources/signals/portfolio/briefing",
               dash["ok"] and dash["sources"]["total"] and "briefing" in dash)
            ck("40. every signal carries a source ref (traceable)",
               all(s.get("source_id") for s in sig.list_signals(N, store=st)))
        finally:
            cs.STORE = old
    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_market_vision_engine", "green" if green else "red",
                files_observed=["anima/market_vision/source_registry.py", "anima/market_vision/signals.py",
                                "anima/market_vision/mining.py", "anima/market_vision/product_gap.py",
                                "anima/market_vision/thesis.py", "anima/market_vision/scoring.py",
                                "anima/market_vision/business_model.py", "anima/market_vision/validation.py",
                                "anima/market_vision/portfolio.py", "anima/market_vision/routers.py",
                                "anima/market_vision/briefing.py"],
                report_paths=["reports/market_vision_engine.json"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)
    print("\nMARKET-VISION-ENGINE CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
