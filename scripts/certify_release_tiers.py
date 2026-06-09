#!/usr/bin/env python3
"""certify_release_tiers — the four-rung Diamond ladder obeys no-wallpaper law: a lower tier is a
SMALLER SURFACE, never a LOWER STANDARD, and the per-tier waiver can NEVER launder a product gap.

The ladder (local_internal < private_alpha < external_notification < enterprise) differs ONLY by the
'external_not_required_for_this_tier' waiver. This cert proves the waiver is double-locked and the
strictness is real:

  1. LADDER COMPLETE        — all four rungs, in strict rank order, with labels + surfaces.
  2. WAIVER UNLOCKS LOCAL ONLY — with acknowledge_flow an honest external partial + all else green,
                              ONLY Local/Internal earns Diamond; Private-Alpha-and-up stay blocked
                              (APNs required there). This is the user's "allow Local/Internal only."
  3. FULL LADDER ON PROOF   — once APNs is proven (acknowledge_flow COMPLETE), the whole ladder unlocks
                              through Enterprise.
  4. PRODUCT GAP NEVER WAIVED (keystone) — reclassify acknowledge_flow as a product_partial (NOT in
                              honest_partials) and NO tier is eligible, not even Local/Internal. The
                              waiver cannot hide a broken LOCAL handler.
  5. RED NEVER WAIVED       — a product_red feature blocks every rung.
  6. CORE GATE GATES ALL TIERS — a red core gate (ai_security) blocks every rung, Local/Internal first.
  7. NO STALE GREEN ANY TIER — a stale required cert blocks every rung.
  8. NO SINGLE-RUN DIAMOND ANY TIER — repeatability not proven blocks every rung.
  9. ENTERPRISE STRICTEST   — APNs proven but enterprise_readiness amber: lower three rungs green,
                              Enterprise NOT eligible (its extra requirement bites).
 10. DOWNWARD-CLOSED        — eligibility is monotonic down the ladder (no eligible rung above an
                              ineligible one).
 11. WAIVER DOUBLE-LOCK     — waivable_for() needs BOTH the static map AND live honest-external classt.
 12. SERVED (if up)         — /verification.json carries the 4 rungs + highest_diamond_tier, and the
                              legacy global Diamond == the Enterprise rung.

Hermetic for the logic teeth (pure function over synthetic bundles). Exit 0 == CERTIFIED.
"""
from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CORE = ["build_identity", "ai_security", "consent_privacy", "performance", "host_reality", "recovery",
        "consistency", "memory_truth", "live_user_reality", "repeatability", "scenario_coverage",
        "rover_journeys", "renegade", "observation_bundle", "cert_freshness", "ui_truth_consistency",
        "evidence_room", "open_blockers"]


def bundle(*, ack="PARTIAL", ack_class="intentional_external_partial", ent="COMPLETE",
           core_red=None, stale=None, rep=("ok", 3), unknown=0, core_status=None):
    """Build a synthetic gates.compute()-shaped bundle to exercise the tier logic."""
    per = [{"feature": "acknowledge_flow", "status": ack, "class": ack_class},
           {"feature": "enterprise_readiness", "status": ent,
            "class": "ok" if ent == "COMPLETE" else ("product_red" if ent in
                     ("STUB", "WALLPAPER", "UNKNOWN", "REGRESSED") else "product_partial")}]
    red = [p["feature"] for p in per if p["class"] == "product_red"]
    prod = [p["feature"] for p in per if p["class"] == "product_partial"]
    if core_red:
        per.append({"feature": core_red + "_feat", "status": "STUB", "class": "product_red"})
        red = red + [core_red + "_feat"]
    honest = (["acknowledge_flow"] if ack != "COMPLETE"
              and ack_class in ("intentional_external_partial", "env_dependency_partial") else [])
    gate_status = dict(core_status or {})
    gates = [{"gate_id": c, "status": gate_status.get(c, "green")} for c in CORE]
    gates += [{"gate_id": g, "status": "green"} for g in
              ("program_reality", "feature_certs", "flake_classification")]
    rep_obj = None
    if rep is not None:
        rep_obj = {"repeatable": rep[0] == "ok", "runs": rep[1]}
    return {
        "gates": gates,
        "floor": {"p0_open": len(red), "unknown_count": unknown},
        "build_identity": {"status": "green", "running_commit": "abc1234"},
        "flake_classification": {"per_feature": per, "honest_partials": honest, "unclassified": [],
                                 "product_partials": prod, "product_red": red, "harness_flakes": []},
        "freshness": {"stale_required": list(stale or [])},
        "repeatability": rep_obj,
    }


def main() -> int:
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("RELEASE TIERS — a lower tier is a smaller surface, never a lower standard (no-wallpaper)")
    print("=" * 92)

    from anima.verification import tiers

    def elig(b):
        r = tiers.decide_tiers(b)
        return {x["tier"]: x["diamond_eligible"] for x in r["tiers"]}, r

    # ---- 1 ladder complete -----------------------------------------------------------------------
    _, r = elig(bundle())
    order = [x["tier"] for x in r["tiers"]]
    ck("1. ladder is the four rungs in strict rank order, each labelled + with a surface",
       order == ["local_internal", "private_alpha", "external_notification", "enterprise"]
       and all(x.get("label") and x.get("surface") for x in r["tiers"])
       and [x["rank"] for x in r["tiers"]] == [0, 1, 2, 3])

    # ---- 2 waiver unlocks LOCAL ONLY (the directive) --------------------------------------------
    e, r = elig(bundle())
    ck("2. acknowledge_flow honest-external + all green -> ONLY Local/Internal Diamond (others blocked)",
       e["local_internal"] is True and e["private_alpha"] is False
       and e["external_notification"] is False and e["enterprise"] is False
       and r["highest_diamond_tier"] == "local_internal")

    # ---- 3 full ladder once APNs proven ---------------------------------------------------------
    e, r = elig(bundle(ack="COMPLETE"))
    ck("3. APNs proven (acknowledge_flow COMPLETE) -> the WHOLE ladder unlocks through Enterprise",
       all(e.values()) and r["highest_diamond_tier"] == "enterprise")

    # ---- 4 product gap NEVER waived (keystone) --------------------------------------------------
    e, _ = elig(bundle(ack_class="product_partial"))
    ck("4. KEYSTONE: acknowledge_flow as a PRODUCT partial (not external) -> NO tier eligible, not even Local",
       not any(e.values()))

    # ---- 5 red never waived ---------------------------------------------------------------------
    e, _ = elig(bundle(ack="COMPLETE", core_red="x"))
    ck("5. a product-RED feature blocks EVERY rung", not any(e.values()))

    # ---- 6 core gate gates all tiers ------------------------------------------------------------
    e, _ = elig(bundle(core_status={"ai_security": "red"}))
    ck("6. a RED core gate (ai_security) blocks EVERY rung — lower tier != lower standard",
       not any(e.values()))

    # ---- 7 no stale green any tier --------------------------------------------------------------
    e, _ = elig(bundle(stale=["live_path_results.json"]))
    ck("7. a STALE required cert blocks EVERY rung (no stale green at any tier)", not any(e.values()))

    # ---- 8 no single-run diamond any tier -------------------------------------------------------
    e_missing, _ = elig(bundle(rep=None))
    e_notrep, _ = elig(bundle(rep=("no", 1)))
    ck("8. repeatability not proven (missing OR not-repeatable) blocks EVERY rung",
       not any(e_missing.values()) and not any(e_notrep.values()))

    # ---- 9 enterprise strictest -----------------------------------------------------------------
    e, _ = elig(bundle(ack="COMPLETE", ent="DEFERRED"))
    ck("9. APNs proven but enterprise_readiness amber -> lower three GREEN, Enterprise NOT eligible",
       e["local_internal"] and e["private_alpha"] and e["external_notification"]
       and e["enterprise"] is False)

    # ---- 10 downward-closed (monotonic) ---------------------------------------------------------
    def monotone(b):
        r = tiers.decide_tiers(b)["tiers"]
        flags = [x["diamond_eligible"] for x in sorted(r, key=lambda z: z["rank"])]
        # once it goes False going UP, it must never go back True
        seen_false = False
        for f in flags:
            if not f:
                seen_false = True
            elif seen_false:
                return False
        return True
    ck("10. eligibility is downward-closed for every state (no eligible rung above an ineligible one)",
       all(monotone(b) for b in (bundle(), bundle(ack="COMPLETE"), bundle(ack="COMPLETE", ent="DEFERRED"),
                                 bundle(ack_class="product_partial"), bundle(stale=["x"]))))

    # ---- 11 waiver double-lock (both kinds) -----------------------------------------------------
    W = tiers.waiver_for
    ext_locked = (W("acknowledge_flow", "local_internal", honest_external=set(), status="PARTIAL") is None
                  and W("acknowledge_flow", "local_internal", honest_external={"acknowledge_flow"}, status="PARTIAL") == "external"
                  and W("acknowledge_flow", "private_alpha", honest_external={"acknowledge_flow"}, status="PARTIAL") is None  # at/above req
                  and W("acknowledge_flow", "local_internal", honest_external={"acknowledge_flow"}, status="REGRESSED") is None)  # red never
    scope_locked = (W("enterprise_readiness", "local_internal", honest_external=set(), status="DEFERRED") == "scope"
                    and W("enterprise_readiness", "enterprise", honest_external=set(), status="DEFERRED") is None  # required here
                    and W("enterprise_readiness", "local_internal", honest_external=set(), status="STUB") is None)  # red never scoped
    unmapped = W("some_other_feature", "local_internal", honest_external={"some_other_feature"}, status="PARTIAL") is None
    ck("11. waiver_for double-locks BOTH kinds: external needs honest-external class; scope never waives a red; neither waives at/above its rung",
       ext_locked and scope_locked and unmapped)

    # ---- 12 served leg (only if the server is up) -----------------------------------------------
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/verification.json", timeout=8) as resp:
            payload = json.loads(resp.read())
        up = True
    except Exception:
        up = False
    if up:
        rt = payload.get("release_tiers", [])
        top = payload.get("top", {})
        names = [x.get("tier") for x in rt]
        served_ok = (names == ["local_internal", "private_alpha", "external_notification", "enterprise"]
                     and "highest_diamond_tier" in top)
        # the legacy global Diamond is exactly the Enterprise rung (it waives nothing)
        ent = next((x for x in rt if x.get("tier") == "enterprise"), {})
        invariant = (bool(top.get("diamond_eligible")) == bool(ent.get("diamond_eligible")))
        ck("12. GET /verification.json carries the 4 rungs + highest_diamond_tier; global Diamond == Enterprise rung",
           served_ok and invariant)
    else:
        print("  --   12. (skipped — server not up; logic teeth above are server-independent)")

    _, r = elig(bundle())
    print("\n  rungs: %s · highest-now(synthetic real state): %s"
          % (len(r["tiers"]), r["highest_diamond_tier"]))
    print("RELEASE-TIERS CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
