"""trust_ledger.schema — the trust taxonomy + invariants (pure data; no I/O).

Every trust-relevant event Vera records maps to a CATEGORY (what kind of trust it touches) and a
PROVENANCE (the real store it came from). The INVARIANTS are the promises the ledger proves over the
real spine — each one is computable and, crucially, FALSIFIABLE (a violation flips it red).
"""
from __future__ import annotations

# ---- categories ------------------------------------------------------------------------------
# Each trust event belongs to exactly one category. The category names the kind of trust at stake.
CATEGORIES = {
    "security": {
        "label": "Security",
        "meaning": "Hostile/injected material was caught, or the system entered/left a safe state.",
    },
    "consent": {
        "label": "Consent",
        "meaning": "A boundary decision: sensitive material held for approval, granted, denied, or revoked.",
    },
    "agency": {
        "label": "Agency",
        "meaning": "A proposed action and the user's decision on it — suggest-only, never silent power.",
    },
    "memory": {
        "label": "Memory",
        "meaning": "A durable-memory write that was gated by consent (held, then approved or forgotten).",
    },
    "improvement": {
        "label": "Improvement",
        "meaning": "A self-improvement proposal the user approved or rejected.",
    },
    "identity": {
        "label": "Identity",
        "meaning": "An identity observation or (frozen) change — never mutated without proof + rollback.",
    },
    "value": {
        "label": "Value Delivered",
        "meaning": "Work the system completed for the user, measured after the fact (the ROI ledger).",
    },
}
CATEGORY_IDS = tuple(CATEGORIES.keys())

# ---- event-kind -> category + provenance -----------------------------------------------------
# The kinds that flow through incident.security_event(), mapped to their trust category and the real
# store that is their source of truth.
KIND_TO_CATEGORY = {
    "quarantine": "security",
    "lockdown": "security",
    "restore": "security",
    "test_probe": "security",
    "output_gate_block": "security",
    "consent_granted": "consent",
    "consent_denied": "consent",
    "consent_revoked": "consent",
    "consent_ask": "consent",
    "sensitive_memory_held": "memory",
    "sensitive_memory_written": "memory",
    "sensitive_memory_discarded": "memory",
    "agency_suggestion": "agency",
    "agency_approve": "agency",
    "agency_reject": "agency",
    "improvement_approve": "improvement",
    "improvement_reject": "improvement",
    "identity_observed": "identity",
    "identity_change": "identity",
}

# the real store each category's events come from (provenance shown in the UI + cert)
CATEGORY_PROVENANCE = {
    "security": ".anima/security_events.jsonl (incident SOC trail)",
    "consent": ".anima/security_events.jsonl (consent decisions) + .anima/{name}.consent.json",
    "agency": ".anima/security_events.jsonl (agency suggest/approve/reject)",
    "memory": ".anima/security_events.jsonl (held/written/discarded) + .anima/{name}.consent_pending.json",
    "improvement": ".anima/security_events.jsonl (improvement decisions) + reports/patterns.json",
    "identity": ".anima/security_events.jsonl + identity_sandbox/",
    "value": "reports/roi_ledger.json (ROI / completed-work ledger)",
}


def category_of(kind: str) -> str:
    """The trust category for an event kind. Unknown kinds fall to 'security' only if they look
    security-ish; otherwise they are surfaced honestly as 'uncategorised' so nothing hides."""
    return KIND_TO_CATEGORY.get(str(kind), "uncategorised")


# ---- the trust invariants --------------------------------------------------------------------
# Each invariant is a promise the ledger PROVES over the real spine. Every one is falsifiable: the
# certs seed a violating event and confirm the invariant flips to holds=False (no wallpaper-green).
INVARIANTS = {
    "append_only": {
        "label": "Append-only integrity",
        "promise": "The trust trail is append-only — event timestamps never go backwards; the log is "
                   "not rewritten under us.",
        "violation": "an event is older than the one before it (the trail was reordered or rewritten)",
    },
    "suggest_only_agency": {
        "label": "Suggest-only agency",
        "promise": "Vera never acts silently — every agency action is a suggestion the user approved or "
                   "rejected; there is no 'executed-without-approval' event, and approvals never exceed "
                   "suggestions.",
        "violation": "an agency action executed without a prior suggestion + approval",
    },
    "consent_before_durable": {
        "label": "No silent sensitive memory",
        "promise": "A sensitive conclusion is never written to durable memory silently — every "
                   "sensitive_memory_written was first held for consent.",
        "violation": "a sensitive memory was written with no preceding 'held' (it skipped the consent gate)",
    },
    "reversible_state": {
        "label": "Reversible state",
        "promise": "Every state transition is reversible — the system is not stuck in lockdown, and "
                   "restore is an audited capability that has been exercised.",
        "violation": "the system is locked with no restore path on record",
    },
}
INVARIANT_IDS = tuple(INVARIANTS.keys())

# the kinds that would, if ever seen, prove a silent (ungated) action — the ledger asserts these are absent
FORBIDDEN_SILENT_KINDS = ("agency_execute", "agency_action", "silent_write", "memory_write_silent")
