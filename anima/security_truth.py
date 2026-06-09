"""security_truth — label every security event with its ORIGIN, ACTIVE STATE, VISIBILITY, and whether it
ever touched memory / prompt / source / tool context. The /security surface was technically correct but
emotionally wrong: it showed blocked PWNED / wire-money TEST FIXTURES as if they were active compromise.

THE DOCTRINE makes most labels deterministic, not guessed: a `quarantine` event is, by construction, the
immune system CATCHING hostile text and HOLDING it as redacted evidence — never obeyed, never trusted.
So for a quarantine on the OUTPUT route (the answer gate dropped a hostile reply), the truth is fixed:
visibility = blocked_before_user; entered_memory / prompt / source / tool = false; it is NOT active.

What is NOT fixed is ORIGIN — cert/rover/renegade test fixture vs a real model_output/live_user turn. New
events can be stamped at creation (incident.set_origin_context); historical, unstamped events are inferred
from a known-fixture signature match and labelled origin_inferred=True (never confidently mislabelled as a
fixture — an unstamped output with no fixture match is a real model_output, shown under Blocked Live Events).
"""
from __future__ import annotations

# the verbatim injection fixtures the cert/rover/renegade suites feed through the real gate. An unstamped
# OUTPUT quarantine whose evidence matches one of these is inferred to be a security TEST FIXTURE.
FIXTURE_SIGNATURES = [
    "pwned", "wire money", "delete original emails", "delete the original emails",
    "malicious system override", "the system override", "ignore previous instructions",
    "ignore all previous instructions", "reply only with", "this override",
]
ORIGINS = {"cert", "rover", "renegade", "live_user", "source", "model_output", "fallback", "manual_test"}
_TEST_ORIGINS = {"cert", "rover", "renegade", "manual_test"}


def classify_event(ev: dict) -> dict:
    """Return ev enriched with the truth labels. Pure; never raises on a malformed event."""
    ev = dict(ev or {})
    kind = ev.get("kind") or ""
    route = ev.get("route") or ("output" if kind == "quarantine" else "")
    markers = [str(m).lower() for m in (ev.get("markers") or [])]
    blob = (str(ev.get("preview") or "") + " " + str(ev.get("detail") or "") + " " + " ".join(markers)).lower()
    is_fixture_text = any(sig in blob for sig in FIXTURE_SIGNATURES)

    # ORIGIN — an explicit stamp wins; else infer (and flag the inference)
    origin = ev.get("origin")
    inferred = False
    if origin not in ORIGINS:
        inferred = True
        if is_fixture_text:
            origin = "cert"                              # matches a known injection fixture
        elif route == "source":
            origin = "source"
        elif route == "output":
            origin = "model_output"                      # a real reply the gate dropped (NOT a fixture)
        else:
            origin = "live_user"

    # VISIBILITY — doctrine: a quarantine is held as evidence, the user never sees the hostile text
    visibility = ev.get("visibility")
    if visibility not in ("blocked_before_user", "shown_to_user", "redacted", "not_user_visible"):
        if kind == "quarantine":
            visibility = "blocked_before_user" if route == "output" else "not_user_visible"
        else:
            visibility = "not_user_visible"

    # CONTEXT REACH — doctrine: hostile text NEVER becomes memory/prompt/source/tool. Only an explicit
    # stamp (a real escape we caught downstream) can set these true; default false.
    entered_memory = bool(ev.get("entered_memory", False))
    entered_prompt = bool(ev.get("entered_prompt_context", False))
    entered_source = bool(ev.get("entered_source_context", False))
    entered_tool = bool(ev.get("entered_tool_context", False))

    # ACTIVE STATE — nothing is "active" unless explicitly flagged or it reached the user/memory/context
    active_state = ev.get("active_state")
    reached = entered_memory or entered_prompt or entered_source or entered_tool or visibility == "shown_to_user"
    if active_state not in ("active", "resolved", "historical", "test_fixture", "evidence_only"):
        if reached:
            active_state = "active"
        elif origin in _TEST_ORIGINS:
            active_state = "test_fixture"
        elif kind == "quarantine":
            active_state = "historical"                  # blocked, over — evidence on file
        else:
            active_state = "evidence_only"

    retention = ev.get("retention_class")
    if retention not in ("test_evidence", "live_incident", "audit_evidence", "security_regression"):
        retention = ("test_evidence" if origin in _TEST_ORIGINS else
                     ("live_incident" if (route == "output" and origin in ("model_output", "live_user")) else
                      "audit_evidence"))

    action_required = bool(ev.get("action_required", False)) or active_state == "active"

    ev.update({
        "origin": origin, "origin_inferred": inferred, "route": route, "visibility": visibility,
        "active_state": active_state, "entered_memory": entered_memory,
        "entered_prompt_context": entered_prompt, "entered_source_context": entered_source,
        "entered_tool_context": entered_tool, "retention_class": retention,
        "action_required": action_required,
        "scenario_id": ev.get("scenario_id"), "run_id": ev.get("run_id"),
        "cert_name": ev.get("cert_name"), "trace_id": ev.get("trace_id"),
        "safe_to_prune": ev.get("safe_to_prune", origin in _TEST_ORIGINS and not reached),
    })
    return ev


def split(events: list, quarantined_sources: list | None = None, lockdown: dict | None = None) -> dict:
    """Split events into the four user-facing buckets the directive requires."""
    cl = [classify_event(e) for e in (events or [])]
    active_threats = [e for e in cl if e["active_state"] == "active" or e["action_required"]]
    if lockdown:                                          # an engaged lockdown is itself an active threat row
        active_threats = [{"kind": "lockdown", "active_state": "active", "action_required": True,
                           "origin": "manual_test" if lockdown.get("manual") else "live_user",
                           "detail": "Lockdown engaged: %s" % (lockdown.get("reason") or "manual"),
                           **lockdown}] + active_threats
    blocked_live = [e for e in cl if e["route"] == "output"
                    and e["origin"] in ("model_output", "live_user") and e["active_state"] != "active"]
    test_evidence = [e for e in cl if e["origin"] in _TEST_ORIGINS and e["active_state"] != "active"]
    return {
        "active_threats": active_threats,
        "active_quarantined_sources": list(quarantined_sources or []),
        "blocked_live_events": blocked_live,
        "security_test_evidence": test_evidence,
    }


def summarize(events: list, quarantined_sources: list | None = None, lockdown: dict | None = None) -> dict:
    """The top-of-page truth summary. The safety counts are doctrine-true regardless of origin guessing."""
    cl = [classify_event(e) for e in (events or [])]
    s = split(events, quarantined_sources, lockdown)
    user_visible = [e for e in cl if e["visibility"] == "shown_to_user"]
    mem = [e for e in cl if e["entered_memory"]]
    prompt_ctx = [e for e in cl if e["entered_prompt_context"]]
    active_n = len(s["active_threats"])
    action = active_n > 0 or len(user_visible) > 0 or len(mem) > 0 or len(prompt_ctx) > 0 or bool(lockdown)
    clean = (active_n == 0 and not user_visible and not mem and not prompt_ctx
             and not (quarantined_sources or []))
    return {
        "active_contamination": active_n - (1 if lockdown else 0) if active_n else 0,
        "active_quarantined_sources": len(quarantined_sources or []),
        "blocked_live_hostile_outputs": len(s["blocked_live_events"]),
        "security_test_fixtures_blocked": len(s["security_test_evidence"]),
        "user_visible_hostile_outputs": len(user_visible),
        "memory_contamination": len(mem),
        "prompt_context_contamination": len(prompt_ctx),
        "action_required": action,
        "headline": ("No active contamination. Recent hostile strings are security-test evidence or "
                     "blocked historical events — none reached you, your memory, or Vera's context."
                     if clean else "Action required: review active threats below."),
    }
