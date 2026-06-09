"""verification.tiers — the four-rung release ladder. Diamond is not one bar but FOUR, each STRICTER
than the last:

    local_internal        Local / Internal Diamond             runs on this host; no remote push needed
    private_alpha         Private Alpha Diamond                 testers on device; ring-on-push needed
    external_notification Full External / Notification Diamond  public; APNs delivery required
    enterprise            Enterprise Diamond                    + enterprise-readiness controls

A rung's requirement set differs from its neighbours ONLY by which features are "required at this rung
and above." A feature required at a higher rung is NOT-REQUIRED (waived) below it. There are exactly
two waiver KINDS, both bounded to an explicit per-feature list and both surfaced (never silent):

  external — the feature's only gap is an external dependency outside the rung's surface (e.g.
             acknowledge_flow needs Apple's APNs). DOUBLE-LOCKED: waived below its rung ONLY when the
             LIVE flake classifier independently calls it a genuine external partial THIS run (it is in
             classification.honest_partials). If it ever broke LOCALLY it would drop out of that set and
             the waiver would vanish at every rung.
  scope    — the feature is an upsell capability not in a lower rung's product (e.g. enterprise SSO /
             readiness). Waived below its rung ONLY when it is NOT a product-red regression. A broken
             (STUB/WALLPAPER/REGRESSED) feature is NEVER scoped away — it blocks every rung.

NEITHER kind can ever waive a product-red, and a product_partial that is not on the waiver list blocks
every rung. So the ladder can never turn a real defect into a green. Every rung also still requires the
FULL core gate set green + the global proof-floor (build identity green, 0 P0, 0 UNKNOWN, 0 stale
required certs, 0 unclassified flakes, repeatability proven). A lower tier is a SMALLER SURFACE, never a
LOWER STANDARD.
"""
from __future__ import annotations

from .gates import GREEN, AMBER, RED, BLOCKED, UNKNOWN, STALE

# the ladder, weakest surface -> strictest. order is meaningful: rung N requires >= everything rung N-1
# requires, plus more surface.
TIERS = ["local_internal", "private_alpha", "external_notification", "enterprise"]
TIER_LABEL = {
    "local_internal":        "Local / Internal Diamond",
    "private_alpha":         "Private Alpha Diamond",
    "external_notification": "Full External / Notification Diamond",
    "enterprise":            "Enterprise Diamond",
}
TIER_SURFACE = {
    "local_internal":        "runs on this host; no remote push round-trip in scope",
    "private_alpha":         "testers on real devices; the ring-on-push experience is in scope",
    "external_notification": "public users; Apple APNs push delivery is in scope",
    "enterprise":            "external surface + enterprise-readiness controls",
}
TIER_RANK = {t: i for i, t in enumerate(TIERS)}

# feature -> (lowest tier at which it is REQUIRED, waiver kind). Below that rung the feature is
# not-required-for-this-tier (waived); at/above it the feature must be fully proven green or the rung's
# Diamond is blocked. This map is the ENTIRE, auditable surface of per-tier relaxation.
REQUIRED_AT = {
    # the phone-push -> tap -> POST /acknowledge round-trip needs Apple's APNs/PushKit stack, which
    # cannot be exercised on this host. Not in the Local/Internal surface; required from Private Alpha up.
    "acknowledge_flow":     ("private_alpha", "external"),
    # enterprise-readiness controls are an enterprise-only upsell surface; not part of the consumer
    # rungs' product. Required at Enterprise. (Currently COMPLETE, so it is green everywhere anyway.)
    "enterprise_readiness": ("enterprise", "scope"),
}

_PARTIALISH = {"PARTIAL", "DEFERRED", "DISABLED"}
_PRODUCT_RED = {"STUB", "WALLPAPER", "UNKNOWN", "REGRESSED"}
# gates whose status is RE-DERIVED per tier (they roll up ALL features, so a per-tier waiver changes
# them); every other gate keeps its single real status for every tier.
_RECOMPUTED = {"program_reality", "feature_certs", "flake_classification"}


def waiver_for(feature: str, tier: str, *, honest_external: set, status: str) -> str | None:
    """Return the waiver KIND ('external'/'scope') if `feature` is waived for `tier`, else None.

    A feature is waived only when it is on the REQUIRED_AT map, this rung is strictly below the rung
    where it becomes required, and the kind's lock is satisfied: 'external' needs the live classifier to
    call it a genuine external partial (feature in honest_external); 'scope' needs it to NOT be a
    product-red regression. Never waives a product-red."""
    spec = REQUIRED_AT.get(feature)
    if spec is None:
        return None
    req_tier, kind = spec
    if TIER_RANK[tier] >= TIER_RANK[req_tier]:
        return None                                       # required at/above this rung — not waivable
    s = (status or "").upper()
    if s in _PRODUCT_RED:
        return None                                       # a regression is never waivable by any kind
    if kind == "external":
        return "external" if feature in honest_external else None
    if kind == "scope":
        return "scope"                                    # scoped-out upsell surface (not product-red)
    return None


def _feat_status(per_feature: list, feature: str) -> str:
    rec = next((o for o in per_feature if o.get("feature") == feature), None)
    if rec is None:
        return BLOCKED
    s = (rec.get("status") or "").upper()
    return {"COMPLETE": GREEN, "PARTIAL": AMBER, "DEFERRED": AMBER, "DISABLED": AMBER,
            "STUB": RED, "WALLPAPER": RED, "UNKNOWN": RED, "REGRESSED": RED}.get(s, BLOCKED)


def _color(statuses: set, p0: int, unknown: int, bi_green: bool, has_running: bool) -> str:
    """Exact mirror of release_decision.decide()'s color logic, over one tier's required statuses."""
    if BLOCKED in statuses or not has_running:
        return BLOCKED
    if RED in statuses or p0 > 0:
        return RED
    if (AMBER in statuses) or (STALE in statuses) or (UNKNOWN in statuses) or unknown > 0 or not bi_green:
        return AMBER
    return GREEN


def decide_tiers(g: dict) -> dict:
    """Compute the per-tier Diamond verdict from one gates.compute() bundle. Pure; never raises."""
    gates = g.get("gates", [])
    floor = g.get("floor", {})
    bi = g.get("build_identity", {})
    cl = g.get("flake_classification") or {}
    fresh = g.get("freshness") or {}
    rep = g.get("repeatability")

    per = cl.get("per_feature", [])
    honest_external = set(cl.get("honest_partials") or [])
    status_of = {o.get("feature"): (o.get("status") or "").upper() for o in per}

    # universal, tier-independent proof-floor
    bi_green = bi.get("status") == GREEN
    has_running = bool(bi.get("running_commit"))
    unknown = floor.get("unknown_count", 0)
    n_unclassified = len(cl.get("unclassified") or [])
    n_harness = len(cl.get("harness_flakes") or [])
    stale_required = list(fresh.get("stale_required") or [])
    rep_present = rep is not None
    rep_ok = bool(rep and rep.get("repeatable"))

    # the gates that hold a single real status for every tier (everything except the 3 recomputed ones)
    static = [x for x in gates if x.get("gate_id") not in _RECOMPUTED]
    static_statuses = [x.get("status") for x in static]
    bad_static = sorted({x.get("gate_id") for x in static if x.get("status") != GREEN})

    red_feats = [o.get("feature") for o in per if (o.get("status") or "").upper() in _PRODUCT_RED]
    partial_feats = [o.get("feature") for o in per if (o.get("status") or "").upper() in _PARTIALISH]
    product_partials = set(cl.get("product_partials") or [])

    rungs = []
    for tier in TIERS:
        waived_kind = {}
        for f in set(partial_feats) | set(REQUIRED_AT):
            k = waiver_for(f, tier, honest_external=honest_external, status=status_of.get(f, "COMPLETE"))
            # a waiver only MATERIALLY relaxes a NON-green feature; a COMPLETE feature is green at every
            # rung and needs no waiver advertised (keeps the surfaced waiver list honest, not noisy).
            if k and status_of.get(f, "COMPLETE") != "COMPLETE":
                waived_kind[f] = k
        waived = sorted(waived_kind)
        waived_set = set(waived)
        waived_external = sorted(f for f, k in waived_kind.items() if k == "external")
        waived_scope = sorted(f for f, k in waived_kind.items() if k == "scope")

        # red features never waive (waiver_for refuses product-red) -> they block every rung
        t_red = list(red_feats)
        t_partials = [f for f in partial_feats if f not in waived_set]
        t_product = [f for f in product_partials if f not in waived_set]   # scoped-out upsell removed
        t_honest = honest_external - waived_set

        # program_reality / feature_certs re-derived under this rung's waivers
        pr_status = RED if t_red else (AMBER if t_partials else GREEN)
        # flake_classification re-derived: unclassified never waivable; product/honest minus waived
        flake_status = (RED if t_product else (UNKNOWN if n_unclassified else
                        (AMBER if (n_harness or t_honest) else GREEN)))

        tier_statuses = set(static_statuses) | {pr_status, flake_status}
        color = _color(tier_statuses, len(t_red), unknown, bi_green, has_running)
        diamond_eligible = (color == GREEN and len(t_red) == 0 and unknown == 0 and bi_green
                            and not stale_required and n_unclassified == 0 and rep_present and rep_ok)

        # human-readable cause when not green
        blocked_by = []
        if not has_running:
            blocked_by.append("no running server")
        if not bi_green:
            blocked_by.append("build identity not green (running==committed==served==certified)")
        if t_red:
            blocked_by.append("product-red feature(s): " + ", ".join(t_red[:4]))
        required_here = [f for f in partial_feats if f not in waived_set]
        if required_here:
            blocked_by.append("required (in this surface) but not green: " + ", ".join(required_here[:4]))
        if bad_static:
            blocked_by.append("core gate(s) not green: " + ", ".join(bad_static[:6]))
        if stale_required:
            blocked_by.append("stale required cert(s): " + ", ".join(stale_required[:4]))
        if n_unclassified:
            blocked_by.append("%d unclassified flake(s)" % n_unclassified)
        if not (rep_present and rep_ok):
            blocked_by.append("repeatability not proven on this commit")

        if diamond_eligible:
            reason = "All %s-surface gates green + proof-floor met." % tier
            if waived_external:
                reason += " External-not-required: " + ", ".join(waived_external) + "."
            if waived_scope:
                reason += " Scope-not-required: " + ", ".join(waived_scope) + "."
        else:
            reason = "Not eligible: " + ("; ".join(blocked_by) or "open gate(s)") + "."

        rungs.append({
            "tier": tier,
            "label": TIER_LABEL[tier],
            "surface": TIER_SURFACE[tier],
            "rank": TIER_RANK[tier],
            "color": color.upper(),
            "diamond_eligible": diamond_eligible,
            "waived": waived,                                # all not-required-for-this-tier features
            "waived_external": waived_external,              # external_not_required_for_this_tier
            "waived_scope": waived_scope,                    # scope_not_required_for_this_tier
            "blocked_by": blocked_by,
            "reason": reason,
        })

    eligible_ranks = [x["rank"] for x in rungs if x["diamond_eligible"]]
    highest = max(eligible_ranks) if eligible_ranks else None
    highest_tier = TIERS[highest] if highest is not None else None
    return {
        "tiers": rungs,
        "highest_diamond_tier": highest_tier,
        "highest_diamond_tier_label": TIER_LABEL.get(highest_tier) if highest_tier else None,
        "doctrine": "A lower tier is a smaller surface, never a lower standard. The only per-tier "
                    "relaxation is waiving a feature required at a higher rung — 'external' (gap is an "
                    "external dependency the live classifier confirms) or 'scope' (an upsell surface not "
                    "in the lower rung's product). Neither waives a product-red; product gaps off the "
                    "waiver list block every rung.",
    }


if __name__ == "__main__":
    import json
    from . import gates as _g
    print(json.dumps(decide_tiers(_g.compute()), indent=2))
