#!/usr/bin/env python3
"""certify_release_tiers — the four-rung Diamond ladder obeys no-wallpaper law: a lower tier is a
SMALLER SURFACE, never a LOWER STANDARD; the per-tier waiver can NEVER launder a product gap; a tier
that CLAIMS a feature must prove it; and a tier cannot be green with hidden required gates or evidence.

Rungs: local_internal < private_alpha < external_notification < enterprise.

  1.  LADDER COMPLETE        — four rungs, strict rank order, each with required_gates + claims + evidence
                              + decision (§1.7 schema).
  2.  LOCAL DOES NOT REQUIRE APNs — acknowledge_flow honest-external + all else green/evidenced -> Local/
                              Internal earns Diamond with APNs WAIVED, and APNs is shown as a visible
                              non-blocking item; Local does NOT claim notifications.
  3.  EXTERNAL REQUIRES APNs (RED) — same input: External Notification is RED/not-eligible because it
                              CLAIMS notifications but APNs is not complete.
  4.  APNs PROVEN UNLOCKS    — acknowledge_flow COMPLETE + all evidence -> External + Enterprise unlock.
  5.  PRODUCT GAP NEVER WAIVED (keystone) — acknowledge_flow as a product_partial -> NO tier eligible.
  6.  RED NEVER WAIVED       — a product-red feature blocks every rung.
  7.  MISSING EVIDENCE BLOCKS — a missing required evidence artifact (lamar_path_rover) defers the rung
                              (not green) and is named in missing_evidence.
  8.  ENTERPRISE REQUIRES GOVERNANCE — a missing governance artifact (threat_model) blocks ONLY Enterprise;
                              External (which doesn't require it) can still pass.
  9.  NON-BLOCKING PARTIAL VISIBLE — Local's waived APNs is surfaced in non_blocking_items and Local's
                              not_claimed lists notifications (green Local never implies notifications).
 10.  NO GREEN WITH FLOOR OPEN — P0 / UNKNOWN / stale / unclassified / repeatability-missing each block
                              every rung.
 11.  DOWNWARD-CLOSED        — eligibility is monotonic down the ladder.
 12.  WAIVER DOUBLE-LOCK     — waiver_for needs the live class (external) / not-red (scope); never at/above.
 13.  SERVED (if up)         — /verification.json carries the 4 rungs + highest_diamond_tier; the legacy
                              global Diamond == the Enterprise rung.

Hermetic for the logic teeth (pure over synthetic bundles). Exit 0 == CERTIFIED.
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
        "evidence_room", "program_reality", "feature_certs", "flake_classification"]


def bundle(*, ack="PARTIAL", ack_class="intentional_external_partial", core_red=None, stale=None,
           rep=("ok", 3), unknown=0, core_status=None, evidence=None, unclassified=None):
    """Synthetic gates.compute()-shaped bundle. evidence=dict(id->bool) overrides evidence presence."""
    from anima.verification import release_tiers as rt
    per = [{"feature": "acknowledge_flow", "status": ack, "class": ack_class},
           {"feature": "enterprise_readiness", "status": "COMPLETE", "class": "ok"},
           {"feature": "capability_truth", "status": "COMPLETE", "class": "ok"}]
    red = [p["feature"] for p in per if p["class"] == "product_red"]
    prod = [p["feature"] for p in per if p["class"] == "product_partial"]
    if core_red:
        per.append({"feature": core_red + "_feat", "status": "STUB", "class": "product_red"})
        red = red + [core_red + "_feat"]
    honest = (["acknowledge_flow"] if ack != "COMPLETE"
              and ack_class in ("intentional_external_partial", "env_dependency_partial") else [])
    gst = dict(core_status or {})
    gates = [{"gate_id": c, "status": gst.get(c, "green"), "name": c} for c in CORE]
    rep_obj = {"repeatable": rep[0] == "ok", "runs": rep[1]} if rep is not None else None
    all_ev = {eid: True for eid in rt.EVIDENCE}
    if evidence:
        all_ev.update(evidence)
    return {
        "gates": gates,
        "floor": {"p0_open": len(red), "unknown_count": unknown},
        "build_identity": {"status": "green", "running_commit": "abc1234"},
        "flake_classification": {"per_feature": per, "honest_partials": honest,
                                 "unclassified": list(unclassified or []),
                                 "product_partials": prod, "product_red": red, "harness_flakes": []},
        "freshness": {"stale_required": list(stale or [])},
        "repeatability": rep_obj,
        "evidence_status": all_ev,
    }


def main() -> int:
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("RELEASE TIERS — a lower tier is a smaller surface, never a lower standard (no-wallpaper)")
    print("=" * 92)

    from anima.verification import release_tiers as tiers

    def rungs(b):
        r = tiers.decide_tiers(b)
        return {x["tier_id"]: x for x in r["tiers"]}, r

    # ---- 1 ladder complete + §1.7 schema --------------------------------------------------------
    by, r = rungs(bundle())
    order = [x["tier_id"] for x in r["tiers"]]
    schema_ok = all(all(k in x for k in ("required_gates", "release_claims", "not_claimed", "evidence",
                                         "decision", "blocking_items", "non_blocking_items", "status"))
                    for x in r["tiers"])
    ck("1. four rungs in strict rank order, each carrying the full §1.7 schema",
       order == ["local_internal", "private_alpha", "external_notification", "enterprise"]
       and [x["rank"] for x in r["tiers"]] == [0, 1, 2, 3] and schema_ok)

    # ---- 2 local does NOT require APNs (waived, visible) ----------------------------------------
    by, _ = rungs(bundle())
    li = by["local_internal"]
    ck("2. Local/Internal earns Diamond with APNs WAIVED (acknowledge_flow honest-external, all else green)",
       li["diamond_eligible"] is True and "acknowledge_flow" in li["waived_external"])

    # ---- 3 external REQUIRES APNs -> RED ---------------------------------------------------------
    en = by["external_notification"]
    apns_blocks = any("APNs" in b or "acknowledge_flow" in b for b in en["blocking_items"])
    ck("3. External Notification is RED/not-eligible because it CLAIMS notifications but APNs is incomplete",
       en["diamond_eligible"] is False and en["color"] == "RED" and apns_blocks)

    # ---- 4 APNs proven unlocks notification + enterprise ----------------------------------------
    by2, r2 = rungs(bundle(ack="COMPLETE"))
    ck("4. APNs proven (acknowledge_flow COMPLETE) + all evidence -> External + Enterprise unlock",
       by2["external_notification"]["diamond_eligible"] and by2["enterprise"]["diamond_eligible"]
       and r2["highest_diamond_tier"] == "enterprise")

    # ---- 5 product gap NEVER waived (keystone) --------------------------------------------------
    by3, _ = rungs(bundle(ack_class="product_partial"))
    ck("5. KEYSTONE: acknowledge_flow as a PRODUCT partial (not external) -> NO tier eligible, not even Local",
       not any(x["diamond_eligible"] for x in by3.values()))

    # ---- 6 red never waived ---------------------------------------------------------------------
    by4, _ = rungs(bundle(ack="COMPLETE", core_red="x"))
    ck("6. a product-RED feature blocks EVERY rung", not any(x["diamond_eligible"] for x in by4.values()))

    # ---- 7 missing evidence blocks (deferred) ---------------------------------------------------
    by5, _ = rungs(bundle(evidence={"lamar_path_rover": False}))
    li5 = by5["local_internal"]
    ck("7. a missing required evidence artifact defers the rung (not green) and is NAMED",
       li5["diamond_eligible"] is False and li5["decision"] == "deferred"
       and any("Lamar-path" in m for m in li5["missing_evidence"]))

    # ---- 8 enterprise requires governance (isolated) --------------------------------------------
    by6, _ = rungs(bundle(ack="COMPLETE", evidence={"threat_model": False}))
    ck("8. a missing GOVERNANCE artifact (threat_model) blocks ONLY Enterprise; External still passes",
       by6["external_notification"]["diamond_eligible"] is True
       and by6["enterprise"]["diamond_eligible"] is False
       and any("Threat model" in m for m in by6["enterprise"]["missing_evidence"]))

    # ---- 9 non-blocking partial visible + local never implies notifications ---------------------
    li_nb = any("acknowledge_flow" in s for s in li["non_blocking_items"])
    li_noclaim = any("notification" in c.lower() for c in li["not_claimed"])
    ck("9. Local's waived APNs is a VISIBLE non-blocking item; Local does NOT claim notifications",
       li_nb and li_noclaim)

    # ---- 10 no green with the floor open --------------------------------------------------------
    floor_blocks = all(
        not any(x["diamond_eligible"] for x in rungs(b)[0].values()) for b in (
            bundle(ack="COMPLETE", unknown=1),
            bundle(ack="COMPLETE", core_red="p0"),                      # p0
            bundle(ack="COMPLETE", stale=["live_path_results.json"]),
            bundle(ack="COMPLETE", unclassified=["mystery_feature"]),
            bundle(ack="COMPLETE", rep=None),
            bundle(ack="COMPLETE", rep=("no", 1)),
        ))
    ck("10. P0 / UNKNOWN / stale / repeatability-missing each block EVERY rung", floor_blocks)

    # ---- 11 downward-closed ---------------------------------------------------------------------
    def monotone(b):
        rs = sorted(tiers.decide_tiers(b)["tiers"], key=lambda z: z["rank"])
        seen_false = False
        for x in rs:
            if not x["diamond_eligible"]:
                seen_false = True
            elif seen_false:
                return False
        return True
    ck("11. eligibility is downward-closed for every state",
       all(monotone(b) for b in (bundle(), bundle(ack="COMPLETE"), bundle(ack="COMPLETE", evidence={"threat_model": False}),
                                 bundle(ack_class="product_partial"), bundle(evidence={"lamar_path_rover": False}))))

    # ---- 12 waiver double-lock ------------------------------------------------------------------
    W = tiers.waiver_for
    ext_locked = (W("acknowledge_flow", "local_internal", honest_external=set(), status="PARTIAL") is None
                  and W("acknowledge_flow", "local_internal", honest_external={"acknowledge_flow"}, status="PARTIAL") == "external"
                  and W("acknowledge_flow", "external_notification", honest_external={"acknowledge_flow"}, status="PARTIAL") is None
                  and W("acknowledge_flow", "local_internal", honest_external={"acknowledge_flow"}, status="REGRESSED") is None)
    scope_locked = (W("enterprise_readiness", "local_internal", honest_external=set(), status="DEFERRED") == "scope"
                    and W("enterprise_readiness", "enterprise", honest_external=set(), status="DEFERRED") is None
                    and W("enterprise_readiness", "local_internal", honest_external=set(), status="STUB") is None)
    ck("12. waiver_for double-locks both kinds (external needs live class; scope never waives red; neither at/above rung)",
       ext_locked and scope_locked
       and W("unmapped", "local_internal", honest_external={"unmapped"}, status="PARTIAL") is None)

    # ---- 13 served leg (only if the server is up) -----------------------------------------------
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/verification.json", timeout=8) as resp:
            payload = json.loads(resp.read())
        up = True
    except Exception:
        up = False
    if up:
        rt = payload.get("release_tiers", [])
        top = payload.get("top", {})
        names = [x.get("tier_id") for x in rt]
        served_ok = (names == ["local_internal", "private_alpha", "external_notification", "enterprise"]
                     and all(x.get("required_gates") and "release_claims" in x for x in rt)
                     and "highest_diamond_tier" in top)
        ent = next((x for x in rt if x.get("tier_id") == "enterprise"), {})
        invariant = (bool(top.get("diamond_eligible")) == bool(ent.get("diamond_eligible")))
        ck("13. GET /verification.json carries the 4 rungs + schema + highest tier; global Diamond == Enterprise rung",
           served_ok and invariant)
    else:
        print("  --   13. (skipped — server not up; logic teeth above are server-independent)")

    _, r = rungs(bundle())
    print("\n  rungs: %d · highest(synthetic real state): %s" % (len(r["tiers"]), r["highest_diamond_tier"]))
    print("RELEASE-TIERS CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
