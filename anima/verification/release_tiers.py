"""verification.release_tiers — the four-rung Diamond ladder. Diamond is not one bar but FOUR, each
STRICTER than the last, and each with its OWN release claims + required evidence:

    local_internal        Local / Internal Diamond             Lamar on this Mac; local-first; NO push
    private_alpha         Private Alpha Diamond                 selected human testers
    external_notification Full External / Notification Diamond  public; Apple APNs push REQUIRED
    enterprise            Enterprise Diamond                    + governance / admin / audit evidence

DOCTRINE — a lower tier is a SMALLER SURFACE, never a LOWER STANDARD. A rung relaxes a requirement vs a
higher rung ONLY via an explicit, surfaced waiver of a feature required at a higher rung:

  external — gap is an external dependency outside the rung's surface (acknowledge_flow needs Apple
             APNs). DOUBLE-LOCKED: waived below its rung ONLY when the live flake classifier independently
             calls it a genuine external partial THIS run. APNs is required at External Notification, so
             Local/Internal AND Private Alpha waive it — but NEITHER may then CLAIM notifications.
  scope    — an upsell capability not in a lower rung's product (enterprise_readiness). Never waives a
             product-red regression.

Neither kind waives a product-red; an off-list product_partial blocks every rung. Beyond the universal
CORE gate set + the global proof-floor (build identity green, 0 P0/UNKNOWN, 0 stale required certs, 0
unclassified flakes, repeatability proven), each rung requires its own EVIDENCE (cumulative down the
ladder): Local/Internal needs the Lamar-path Rover green; Private Alpha adds onboarding / capability
truth / support-export / clear security labels; External Notification adds the live APNs round-trip;
Enterprise adds governance — threat model, incident response, admin controls, audit export, etc.
Enterprise Diamond cannot be green on product behaviour alone.
"""
from __future__ import annotations

from pathlib import Path

from .gates import GREEN, AMBER, RED, BLOCKED, UNKNOWN, STALE

ROOT = Path(__file__).resolve().parent.parent.parent
DOCS = ROOT / "docs"
REPORTS = ROOT / "reports"

TIERS = ["local_internal", "private_alpha", "external_notification", "enterprise"]
TIER_LABEL = {
    "local_internal":        "Local / Internal Diamond",
    "private_alpha":         "Private Alpha Diamond",
    "external_notification": "Full External / Notification Diamond",
    "enterprise":            "Enterprise Diamond",
}
TIER_SURFACE = {
    "local_internal":        "Lamar on this Mac; local-first chat/memory/source/security/host/verification; no remote push",
    "private_alpha":         "selected human testers; onboarding + capability-honest surfaces + clear security labels",
    "external_notification": "public users; Apple APNs push send + acknowledge round-trip in scope",
    "enterprise":            "enterprise buyer; admin/RBAC/audit/governance evidence in scope",
}
TIER_RANK = {t: i for i, t in enumerate(TIERS)}

# what each rung CLAIMS (and explicitly does NOT) — so a green low rung can never imply a high-rung feature.
RELEASE_CLAIMS = {
    "local_internal": {
        "claims": ["local chat + follow-ups", "memory recall + forget", "source add + cited recall",
                   "security & quarantine inspect", "host health", "verification dashboard",
                   "living map", "observation dashboard"],
        "not_claimed": ["remote push notifications", "external user accounts", "multi-tenant admin", "audiobook / long-form media intake (deferred -> future Media/Audiobook Intake tier)"],
    },
    "private_alpha": {
        "claims": ["everything Local/Internal claims", "tester onboarding", "capability-honest surfaces",
                   "support / export package", "clear security-event labels", "tester feedback path"],
        "not_claimed": ["remote push notifications", "enterprise admin / governance", "audiobook / long-form media intake (deferred -> future Media/Audiobook Intake tier)"],
    },
    "external_notification": {
        "claims": ["everything Private Alpha claims", "push notifications (APNs send + acknowledge)",
                   "notification permission + retry/debounce", "notification privacy + audit trail"],
        "not_claimed": ["enterprise admin / governance", "audiobook / long-form media intake (deferred -> future Media/Audiobook Intake tier)"],
    },
    "enterprise": {
        "claims": ["everything External Notification claims", "admin controls", "RBAC/ABAC",
                   "audit log export", "governance evidence package", "incident response",
                   "threat model", "vulnerability management"],
        "not_claimed": ["audiobook / long-form media intake (deferred -> future Media/Audiobook Intake tier; enterprise media intake is not claimed)"],
    },
}

# feature -> (lowest tier at which it is REQUIRED, waiver kind). Below that rung the feature is
# not-required-for-this-tier (waived); at/above it it must be fully proven green or the rung blocks.
REQUIRED_AT = {
    # the phone-push -> tap -> POST /acknowledge round-trip needs Apple's APNs/PushKit stack; required
    # at the notification tier. Local/Internal + Private Alpha waive it (and do NOT claim notifications).
    "acknowledge_flow":     ("external_notification", "external"),
    # enterprise-readiness controls are an enterprise-only surface; required at Enterprise.
    "enterprise_readiness": ("enterprise", "scope"),
    # audiobook / long-form-audio intake is DEFERRED by product decision (2026-06-09): not part of the
    # current Local/Internal release and not claimed by ANY current rung (incl. Enterprise — enterprise
    # media intake is not claimed). It becomes required only at the FUTURE "media_intake" tier
    # ("Media/Audiobook Intake"), which is not yet on the ladder — so every current rung waives it as
    # scope, surfaced never silent. A product-red still blocks (waiver_for never waives red).
    "audiobook_intake":     ("media_intake", "scope"),
}

# future tiers referenced by REQUIRED_AT but not yet on the 4-rung ladder: every CURRENT rung ranks
# below them, so the feature is waived (surfaced) everywhere until the tier is added to TIERS.
FUTURE_TIERS = {"media_intake": "Media/Audiobook Intake"}

# the universal CORE gate set — required green for EVERY rung (a lower tier is a smaller surface, not a
# lower standard). These are the gate_ids gates.compute() emits.
CORE_GATES = [
    "build_identity", "program_reality", "feature_certs", "live_user_reality", "scenario_coverage",
    "rover_journeys", "observation_bundle", "renegade", "performance", "host_reality", "ai_security",
    "consent_privacy", "recovery", "ui_truth_consistency", "evidence_room", "cert_freshness",
    "repeatability", "flake_classification",
]

# evidence artifacts. kind: doc (a file under docs/ exists) | report (a reports/<f>.json exists + passes)
# | gate (a computed gate is green) | feature (a live_path feature is COMPLETE).
EVIDENCE = {
    # Local/Internal: the founder's own path must pass through the REAL browser UI (Increment 2).
    "lamar_path_rover":      {"label": "Lamar-path Rover (real browser)", "kind": "report", "ref": "lamar_path_rover.json"},
    # Private Alpha
    "onboarding":            {"label": "User onboarding",            "kind": "doc",     "ref": ["onboarding.md", "ONBOARDING.md"]},
    "capability_truth":      {"label": "Capability-truth surface",   "kind": "feature", "ref": "capability_truth"},
    "support_export":        {"label": "Support / export package",   "kind": "doc",     "ref": ["support_export.md", "audit_export.md"]},
    "known_limitations":     {"label": "Known limitations",          "kind": "doc",     "ref": ["known_limitations.md", "KNOWN_LIMITATIONS.md"]},
    "security_event_labels": {"label": "Security-event truth labels","kind": "report",  "ref": "security_event_truth.json"},
    "feedback_path":         {"label": "Founder/tester feedback path","kind": "doc",    "ref": ["feedback_path.md"]},
    # External Notification
    "notification_privacy":  {"label": "Notification privacy policy", "kind": "doc",     "ref": ["notification_privacy.md"]},
    "notification_audit":    {"label": "Notification audit trail",    "kind": "doc",     "ref": ["notification_audit.md"]},
    # Enterprise governance (1.6)
    "threat_model":          {"label": "Threat model",               "kind": "doc",     "ref": ["threat_model.md"]},
    "incident_response":     {"label": "Incident response package",  "kind": "doc",     "ref": ["incident_response.md"]},
    "security_architecture": {"label": "Security architecture",      "kind": "doc",     "ref": ["security_architecture.md"]},
    "admin_controls":        {"label": "Admin controls",             "kind": "doc",     "ref": ["admin_controls.md"]},
    "rbac_abac":             {"label": "RBAC / ABAC plan",           "kind": "doc",     "ref": ["rbac_abac.md", "permission_model.md"]},
    "audit_export":          {"label": "Audit log export",           "kind": "doc",     "ref": ["audit_export.md"]},
    "asset_inventory":       {"label": "Asset inventory",            "kind": "doc",     "ref": ["asset_inventory.md"]},
    "data_classification":   {"label": "Data classification",        "kind": "doc",     "ref": ["data_classification.md"]},
    "support_access_policy": {"label": "Support access policy",      "kind": "doc",     "ref": ["support_access_policy.md"]},
    "vulnerability_mgmt":    {"label": "Vulnerability management",   "kind": "doc",     "ref": ["vulnerability_management.md"]},
    "deployment_docs":       {"label": "Deployment documentation",   "kind": "doc",     "ref": ["self-hosting-digitalocean.md", "deployment.md"]},
    "security_questionnaire":{"label": "Security questionnaire",     "kind": "doc",     "ref": ["security_questionnaire.md"]},
    "compliance_controls":   {"label": "Compliance controls",        "kind": "doc",     "ref": ["compliance_controls.md"]},
    "privacy_data_control":  {"label": "Privacy / data-control proof","kind": "gate",   "ref": "consent_privacy"},
    "evidence_room_complete":{"label": "Evidence Room complete",     "kind": "gate",    "ref": "evidence_room"},
}

# evidence each rung adds (CUMULATIVE down the ladder — a rung needs its own + every lower rung's).
TIER_EVIDENCE = {
    "local_internal":        ["lamar_path_rover"],
    "private_alpha":         ["onboarding", "capability_truth", "support_export", "known_limitations",
                              "security_event_labels", "feedback_path"],
    "external_notification": ["notification_privacy", "notification_audit"],
    "enterprise":            ["threat_model", "incident_response", "security_architecture", "admin_controls",
                              "rbac_abac", "audit_export", "asset_inventory", "data_classification",
                              "support_access_policy", "vulnerability_mgmt", "deployment_docs",
                              "security_questionnaire", "compliance_controls", "privacy_data_control",
                              "evidence_room_complete"],
}

_PARTIALISH = {"PARTIAL", "DEFERRED", "DISABLED"}
_PRODUCT_RED = {"STUB", "WALLPAPER", "UNKNOWN", "REGRESSED"}
_RECOMPUTED = {"program_reality", "feature_certs", "flake_classification"}


def waiver_for(feature: str, tier: str, *, honest_external: set, status: str) -> str | None:
    """Return the waiver KIND ('external'/'scope') if `feature` is waived for `tier`, else None. Double-
    locked: 'external' needs the live classifier to call it a genuine external partial; 'scope' needs it
    to NOT be a product-red; neither waives at/above the rung where the feature becomes required."""
    spec = REQUIRED_AT.get(feature)
    if spec is None:
        return None
    req_tier, kind = spec
    # a FUTURE tier (declared in FUTURE_TIERS, not yet in TIERS) outranks every current rung — the
    # feature is not required anywhere on the current ladder, so the waiver applies (still never red).
    if req_tier not in TIER_RANK:
        if req_tier not in FUTURE_TIERS:
            return None                       # unknown tier name: refuse to waive (fail closed)
    elif TIER_RANK[tier] >= TIER_RANK[req_tier]:
        return None
    if (status or "").upper() in _PRODUCT_RED:
        return None
    if kind == "external":
        return "external" if feature in honest_external else None
    if kind == "scope":
        return "scope"
    return None


def _feat_status(per_feature: list, feature: str) -> str:
    rec = next((o for o in per_feature if o.get("feature") == feature), None)
    if rec is None:
        return BLOCKED
    s = (rec.get("status") or "").upper()
    return {"COMPLETE": GREEN, "PARTIAL": AMBER, "DEFERRED": AMBER, "DISABLED": AMBER,
            "STUB": RED, "WALLPAPER": RED, "UNKNOWN": RED, "REGRESSED": RED}.get(s, BLOCKED)


def _head_short() -> str:
    import subprocess
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=str(ROOT),
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def _report_passes(name: str) -> bool:
    """A report-kind evidence artifact exists, records a pass/green, AND (if it stamps the commit it ran
    at) was produced on the CURRENT HEAD — a stale report from an older build never counts as green."""
    import json
    f = REPORTS / name
    if not f.exists():
        return False
    try:
        j = json.loads(f.read_text())
    except Exception:
        return False
    recorded = (j.get("commit") or "")
    head = _head_short()
    if recorded and head and recorded[:12] != head[:12]:
        return False                                  # stale: ran on a different commit than HEAD
    if j.get("green") is True or j.get("passed") is True:
        return True
    return str(j.get("status", "")).lower() in ("green", "pass", "passed", "certified")


def evaluate_evidence(g: dict) -> dict:
    """Resolve every evidence artifact to present/absent from the real filesystem + computed gates.
    Tests may inject g['evidence_status'] = {id: bool} to bypass the filesystem."""
    override = g.get("evidence_status")
    gates_by = {x.get("gate_id"): x for x in g.get("gates", [])}
    per = (g.get("flake_classification") or {}).get("per_feature", [])
    out = {}
    for eid, spec in EVIDENCE.items():
        if isinstance(override, dict) and eid in override:
            present = bool(override[eid])
        else:
            k = spec["kind"]
            if k == "doc":
                present = any((DOCS / r).exists() for r in spec["ref"])
            elif k == "report":
                present = _report_passes(spec["ref"])
            elif k == "gate":
                present = gates_by.get(spec["ref"], {}).get("status") == GREEN
            elif k == "feature":
                present = _feat_status(per, spec["ref"]) == GREEN
            else:
                present = False
        out[eid] = {"present": present, "label": spec["label"], "kind": spec["kind"], "ref": spec["ref"]}
    return out


def _cumulative_evidence(tier: str) -> list:
    ids = []
    for t in TIERS:
        ids += TIER_EVIDENCE.get(t, [])
        if t == tier:
            break
    # de-dupe preserving order
    seen, out = set(), []
    for i in ids:
        if i not in seen:
            seen.add(i); out.append(i)
    return out


def _color(statuses: set, p0: int, unknown: int, bi_green: bool, has_running: bool) -> str:
    if BLOCKED in statuses or not has_running:
        return BLOCKED
    if RED in statuses or p0 > 0:
        return RED
    if (AMBER in statuses) or (STALE in statuses) or (UNKNOWN in statuses) or unknown > 0 or not bi_green:
        return AMBER
    return GREEN


def decide_tiers(g: dict) -> dict:
    """Compute the per-tier Diamond verdict + the full §1.7 schema from one gates.compute() bundle.
    Pure over (g + the evidence filesystem); never raises."""
    gates = g.get("gates", [])
    floor = g.get("floor", {})
    bi = g.get("build_identity", {})
    cl = g.get("flake_classification") or {}
    fresh = g.get("freshness") or {}
    rep = g.get("repeatability")

    per = cl.get("per_feature", [])
    honest_external = set(cl.get("honest_partials") or [])
    status_of = {o.get("feature"): (o.get("status") or "").upper() for o in per}
    ev = evaluate_evidence(g)

    bi_green = bi.get("status") == GREEN
    has_running = bool(bi.get("running_commit"))
    unknown = floor.get("unknown_count", 0)
    n_unclassified = len(cl.get("unclassified") or [])
    n_harness = len(cl.get("harness_flakes") or [])
    stale_required = list(fresh.get("stale_required") or [])
    rep_present = rep is not None
    rep_ok = bool(rep and rep.get("repeatable"))

    gates_by = {x.get("gate_id"): x for x in gates}
    static = [x for x in gates if x.get("gate_id") not in _RECOMPUTED]
    static_statuses = [x.get("status") for x in static]
    bad_static = sorted({x.get("gate_id") for x in static if x.get("status") != GREEN})

    red_feats = [o.get("feature") for o in per if (o.get("status") or "").upper() in _PRODUCT_RED]
    partial_feats = [o.get("feature") for o in per if (o.get("status") or "").upper() in _PARTIALISH]
    product_partials = set(cl.get("product_partials") or [])

    rungs = []
    for tier in TIERS:
        # ---- per-tier feature waivers (external/scope), surfaced, never silent ----
        waived_kind = {}
        for f in set(partial_feats) | set(REQUIRED_AT):
            k = waiver_for(f, tier, honest_external=honest_external, status=status_of.get(f, "COMPLETE"))
            if k and status_of.get(f, "COMPLETE") != "COMPLETE":
                waived_kind[f] = k
        waived_set = set(waived_kind)
        waived_external = sorted(f for f, k in waived_kind.items() if k == "external")
        waived_scope = sorted(f for f, k in waived_kind.items() if k == "scope")

        t_red = list(red_feats)
        t_partials = [f for f in partial_feats if f not in waived_set]
        t_product = [f for f in product_partials if f not in waived_set]
        t_honest = honest_external - waived_set

        pr_status = RED if t_red else (AMBER if t_partials else GREEN)
        flake_status = (RED if t_product else (UNKNOWN if n_unclassified else
                        (AMBER if (n_harness or t_honest) else GREEN)))

        # ---- per-tier required evidence (cumulative) ----
        req_ev = _cumulative_evidence(tier)
        missing_ev = [eid for eid in req_ev if not ev[eid]["present"]]

        # ---- APNs requirement state for this tier (feature acknowledge_flow) ----
        apns_required = TIER_RANK[tier] >= TIER_RANK[REQUIRED_AT["acknowledge_flow"][0]]
        apns_status = _feat_status(per, "acknowledge_flow")

        tier_statuses = set(static_statuses) | {pr_status, flake_status}
        if missing_ev:
            tier_statuses.add(AMBER)                       # missing evidence is a work state, not a defect
        # a tier that CLAIMS a required external feature but cannot prove it is RED (the claim is broken),
        # not amber — e.g. External Notification claims push but acknowledge_flow/APNs is not complete.
        apns_claim_broken = apns_required and apns_status != GREEN
        if apns_claim_broken:
            tier_statuses.add(RED)
        color = _color(tier_statuses, len(t_red), unknown, bi_green, has_running)
        diamond_eligible = (color == GREEN and len(t_red) == 0 and unknown == 0 and bi_green
                            and not stale_required and n_unclassified == 0 and rep_present and rep_ok
                            and not missing_ev)

        # ---- the §1.7 schema: required gates (with status), blocking + non-blocking items ----
        required_gates = []
        for gid in CORE_GATES:
            required_gates.append({"id": gid, "label": (gates_by.get(gid, {}) or {}).get("name", gid),
                                   "status": (gates_by.get(gid, {}) or {}).get("status", "unknown")})
        if apns_required:
            required_gates.append({"id": "acknowledge_flow", "label": "APNs acknowledge round-trip",
                                   "status": apns_status})
        for eid in req_ev:
            required_gates.append({"id": eid, "label": EVIDENCE[eid]["label"],
                                   "status": GREEN if ev[eid]["present"] else "missing"})

        blocking_items, non_blocking_items = [], []
        if not has_running:
            blocking_items.append("no running server")
        if not bi_green:
            blocking_items.append("build identity not green (running==committed==served==certified)")
        for f in t_red:
            blocking_items.append("product-red feature: " + f)
        for f in t_partials:
            if f == "acknowledge_flow" and apns_claim_broken:
                continue                                    # reported once, explicitly, below
            blocking_items.append("required feature not green (in this surface): " + f)
        if apns_claim_broken:
            blocking_items.append("APNs / acknowledge_flow not complete — this tier CLAIMS notifications "
                                  "but the push round-trip is not live-path certified (status: %s)" % apns_status)
        for gid in bad_static:
            blocking_items.append("core gate not green: " + gid)
        for eid in missing_ev:
            blocking_items.append("missing evidence: " + EVIDENCE[eid]["label"])
        for r in stale_required:
            blocking_items.append("stale required cert: " + r)
        if n_unclassified:
            blocking_items.append("%d unclassified flake(s)" % n_unclassified)
        if not (rep_present and rep_ok):
            blocking_items.append("repeatability not proven on this commit")
        # non-blocking but VISIBLE: the waived externals/scopes for this tier
        for f in waived_external:
            non_blocking_items.append("external-not-required-for-this-tier: %s (NOT proven, NOT claimed)" % f)
        for f in waived_scope:
            non_blocking_items.append("scope-not-required-for-this-tier: %s" % f)

        allowed_partials = ([{"feature": f, "kind": "external"} for f in waived_external]
                            + [{"feature": f, "kind": "scope"} for f in waived_scope])
        evidence_rows = [{"id": eid, "label": EVIDENCE[eid]["label"], "kind": EVIDENCE[eid]["kind"],
                          "present": ev[eid]["present"]} for eid in req_ev]

        if diamond_eligible:
            decision = "eligible"
            reason = "All %s-surface gates green, evidence complete, proof-floor met." % tier
            if waived_external or waived_scope:
                reason += " Not-required-for-this-tier: " + ", ".join(waived_external + waived_scope) + "."
        elif color == RED:
            decision = "not_eligible"
            reason = "Not eligible (RED): " + ("; ".join(blocking_items[:4]) or "a required gate is red") + "."
        else:
            decision = "deferred"
            reason = "Deferred (AMBER): " + ("; ".join(blocking_items[:4]) or "evidence/external pending") + "."

        rungs.append({
            "tier_id": tier,
            "name": TIER_LABEL[tier],
            "surface": TIER_SURFACE[tier],
            "rank": TIER_RANK[tier],
            "status": color,
            "color": color.upper(),
            "diamond_eligible": diamond_eligible,
            "decision": decision,
            "reason": reason,
            "required_gates": required_gates,
            "passed_gates": [r["id"] for r in required_gates if r["status"] == GREEN],
            "failed_gates": [r["id"] for r in required_gates if r["status"] not in (GREEN,)],
            "allowed_non_blocking_partials": allowed_partials,
            "blocking_items": blocking_items,
            "non_blocking_items": non_blocking_items,
            "release_claims": RELEASE_CLAIMS[tier]["claims"],
            "not_claimed": RELEASE_CLAIMS[tier]["not_claimed"],
            "evidence": evidence_rows,
            "missing_evidence": [EVIDENCE[e]["label"] for e in missing_ev],
            "apns_required": apns_required,
            "apns_status": apns_status,
            # legacy keys kept for the existing UI/cert
            "label": TIER_LABEL[tier],
            "waived": sorted(waived_set),
            "waived_external": waived_external,
            "waived_scope": waived_scope,
            "blocked_by": blocking_items,
        })

    eligible_ranks = [x["rank"] for x in rungs if x["diamond_eligible"]]
    highest = max(eligible_ranks) if eligible_ranks else None
    highest_tier = TIERS[highest] if highest is not None else None
    return {
        "tiers": rungs,
        "highest_diamond_tier": highest_tier,
        "highest_diamond_tier_label": TIER_LABEL.get(highest_tier) if highest_tier else None,
        "evidence_status": {k: v["present"] for k, v in ev.items()},
        "doctrine": "A lower tier is a smaller surface, never a lower standard. Per-tier relaxation is "
                    "limited to surfaced waivers of higher-rung features (external / scope), never a "
                    "product gap; and each rung adds its own cumulative evidence. Enterprise Diamond "
                    "cannot be green on product behaviour alone.",
    }


if __name__ == "__main__":
    import json
    from . import gates as _g
    print(json.dumps(decide_tiers(_g.compute()), indent=2))
