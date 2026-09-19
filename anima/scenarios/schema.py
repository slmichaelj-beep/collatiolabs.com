"""scenarios.schema — the finite user-space model: the axes + the machine-readable Scenario object.

Section 4 of the Total Reality directive: every scenario is a point in a finite product of equivalence
classes. Infinite phrasings collapse to finite BEHAVIOUR CLASSES; we test representative variations per
class, not every English sentence. Pure data; no I/O.
"""
from __future__ import annotations

# ---- 4.3 user intents (behaviour classes — the finite reduction of infinite phrasing) --------
USER_INTENTS = (
    "ask", "tell", "correct", "clarify", "interrupt", "retry", "add_knowledge", "upload", "paste_url",
    "ask_from_source", "inspect_source", "delete_source", "forget_memory", "approve_memory",
    "reject_memory", "edit_memory", "export_self", "import_data", "ask_what_vera_knows",
    "ask_why_vera_answered", "ask_what_source_used", "ask_what_vera_inferred", "ask_what_vera_can_do",
    "ask_what_is_incomplete", "ask_what_is_real", "approve_suggestion", "reject_suggestion",
    "edit_suggestion", "simulate_change", "view_pattern", "promote_improvement", "lockdown", "restore",
    "change_setting", "review_incident", "run_audit", "view_performance", "view_host_state",
    "view_trust_ledger", "view_living_map", "replay_turn", "run_rover", "run_renegade",
)

# ---- 4.4 input types ------------------------------------------------------------------------
INPUT_TYPES = (
    "plain_text", "voice_transcribed", "pdf", "scanned_pdf", "image", "photo", "audio", "aax",
    "transcript", "url", "webpage", "email_like", "calendar_like", "health_note", "therapy_note",
    "relationship_note", "finance_note", "legal_note", "code_log", "csv", "json", "markdown",
    "large_file", "empty_file", "duplicate_file", "corrupt_file", "unsupported_file", "malformed_url",
    "host_telemetry", "no_input", "ambiguous_input",
)

# ---- 4.5 data classes -----------------------------------------------------------------------
DATA_CLASSES = (
    "public", "internal", "personal", "sensitive_personal", "health_adjacent", "financial_adjacent",
    "legal_adjacent", "location", "communications", "credential_secret", "enterprise_confidential",
    "regulated", "host_telemetry", "hostile_instruction", "unknown_classification",
)

# ---- 4.6 permission states ------------------------------------------------------------------
PERMISSION_STATES = (
    "granted", "denied", "ask_each_time", "revoked", "not_configured", "expired", "locked_down",
    "admin_only", "external_dependency_blocked",
)

# ---- 4.7 consent states ---------------------------------------------------------------------
CONSENT_STATES = (
    "not_required", "required_not_requested", "requested_pending", "granted", "denied",
    "ask_each_time", "revoked", "expired", "sensitive_go_slow", "confirm_each_step",
)

# ---- 4.8 memory/source states ---------------------------------------------------------------
MEMORY_SOURCE_STATES = (
    "not_captured", "captured_not_stored", "stored_not_indexed", "indexed_not_retrieved",
    "retrieved_not_used", "used_not_shipped", "shipped_not_verified", "quarantined", "deleted",
    "forgotten", "stale", "duplicate", "conflicting", "low_confidence", "source_unavailable",
    "source_hostile", "source_clean", "source_sensitive", "indexed",
)

# ---- 4.9 host states ------------------------------------------------------------------------
HOST_STATES = (
    "green", "yellow", "red", "critical", "high_swap", "low_disk", "high_cpu", "high_io",
    "gpu_pressure", "model_loaded", "model_not_loaded", "model_cold", "model_warm", "network_unavailable",
)

# ---- 4.10 system states ---------------------------------------------------------------------
SYSTEM_STATES = (
    "normal", "server_unavailable", "model_unavailable", "source_store_unavailable",
    "memory_store_unavailable", "background_job_running", "background_job_failed", "queue_backed_up",
    "lockdown_active", "quarantine_active", "consent_required", "approval_pending", "audit_failing",
    "partial_degraded", "restart_recovery",
)

# ---- 4.11 security states -------------------------------------------------------------------
SECURITY_STATES = (
    "clean", "suspicious", "hostile", "quarantined", "contaminated_output", "source_chip_suppressed",
    "final_gate_blocked", "fallback_safe", "incident_active",
)

# ---- 4.12 expected outcomes -----------------------------------------------------------------
EXPECTED_OUTCOMES = (
    "answer", "answer_with_source", "answer_with_uncertainty", "ask_clarification", "request_consent",
    "request_approval", "draft_only", "block_safely", "refuse_safely", "quarantine",
    "queue_background_job", "show_progress", "delete", "forget", "export", "import", "show_trace",
    "show_source", "show_capability_truth", "defer_host_pressure", "recover", "incident_created",
    "page_loads", "control_acts",
)

# expected routes (the model/path the turn should take)
EXPECTED_ROUTES = (
    "source_answer", "known_fact", "memory_answer", "simple_chat", "lerf", "model", "fallback_safe",
    "blocked", "ui_only", "background_job",
)

# scenario status taxonomy (Vera Method labels + the directive's vocabulary)
STATUSES = ("untested", "pass", "fail", "blocked", "deferred", "not_applicable")

# severity classification (section 15)
SEVERITIES = ("P0", "P1", "P2", "P3")

# the axes, in order, that every scenario is a point on (section 4)
AXES = (
    "surface", "control_id", "user_intent", "input_type", "data_class", "permission_state",
    "consent_state", "memory_source_state", "host_state", "system_state", "security_state",
    "expected_route", "expected_outcome",
)


def scenario(scenario_id, title, surface, **kw) -> dict:
    """Build a machine-readable Scenario object (section 5 shape). Unspecified axes default to the
    common/honest baseline so every scenario is fully classified (no UNKNOWN axis)."""
    s = {
        "scenario_id": scenario_id,
        "title": title,
        "surface": surface,
        "control_id": kw.get("control_id"),
        "user_intent": kw.get("user_intent", "ask"),
        "input_type": kw.get("input_type", "plain_text"),
        "data_class": kw.get("data_class", "personal"),
        "permission_state": kw.get("permission_state", "granted"),
        "consent_state": kw.get("consent_state", "not_required"),
        "memory_source_state": kw.get("memory_source_state", "indexed"),
        "host_state": kw.get("host_state", "green"),
        "system_state": kw.get("system_state", "normal"),
        "security_state": kw.get("security_state", "clean"),
        "expected_route": kw.get("expected_route", "ui_only"),
        "expected_outcome": kw.get("expected_outcome", "page_loads"),
        "must_pass": list(kw.get("must_pass", [])),
        "must_not_happen": list(kw.get("must_not_happen", [])),
        "required_traces": list(kw.get("required_traces", [])),
        "required_ui_surfaces": list(kw.get("required_ui_surfaces", [])),
        "required_certs": list(kw.get("required_certs", [])),
        "level": kw.get("level", 2),                 # coverage level (0..9)
        "family": kw.get("family", "founder_admin"),  # test family (section 17)
        "kind": kw.get("kind", "normal"),             # critical|normal|edge|adversarial|degraded|blocked|deferred
        "status": kw.get("status", "untested"),
    }
    return s


def is_fully_classified(s: dict) -> bool:
    """A scenario is acceptable only if every axis is a known value and it ends in a known outcome —
    the directive's 'unclassified user behavior: 0' bar."""
    try:
        return (s.get("expected_outcome") in EXPECTED_OUTCOMES
                and s.get("user_intent") in USER_INTENTS
                and s.get("status") in STATUSES
                and bool(s.get("surface")) and bool(s.get("scenario_id")))
    except Exception:
        return False
