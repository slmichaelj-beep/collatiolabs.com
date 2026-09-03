"""root_cause — the auditable map from a detected pattern to its remediation.

Phase 5 of the Vera moonshot (the Pattern Observatory) turns observation into
engineering work orders:

    pattern  ->  evidence  ->  root cause  ->  recommended fix  ->  required cert

`patterns.py` does the *detecting* (which repeated shape is this, and on which
turns/features is the evidence?).  This module does the *remediation lookup*: given
a stable ``pattern_id``, it returns the canonical, certifiable work order —

    { "root_cause", "recommended_fix", "cert_required", "expected_improvement" }

so a detected pattern carries a concrete, checkable next-build rather than a vague
description.  The map is deliberately small, hand-curated, and seeded from the cases
the Program Reality Audit already proved (live_path_results.json):

  * source_use            — retrieved but not used (the reference-recall seam regression guard)
  * conversation_repair   — memory known but the correction is lost (the live P0 WALLPAPER)
  * capability_truth      — a capability claims LIVE but the runtime probe refuses
  * uki_commit            — intake planned but never committed (the URL/PDF needs_dependency gap)
  * llm_vs_deterministic  — the LLM ran when a deterministic seam (host/reference/lerf) existed
  * completeness          — the final gate stripped the reply below the completeness bar
  * host_resource_spike   — host CPU/mem/disk spiked during a turn (often intake)
  * retrieval_depth_cost  — deeper retrieval cost more without buying more quality

Design rules:
  * Pure data + tiny pure functions.  No I/O, no model, no network, no store writes.
  * ``remediation_for`` NEVER raises and ALWAYS returns the four keys (an unknown
    pattern_id yields an honest, generic placeholder, never a crash).
  * Every entry is the SINGLE source of truth for that pattern's fix; ``patterns.py``
    stamps a detected Pattern from here so the report and the detector cannot drift.

This is the layer where the system proposes its own next-best build.
"""

from __future__ import annotations

from typing import Any, Dict

# ---------------------------------------------------------------------------
# Severity ranking — P0 (ship-blocking) < P1 (important) < P2 (cleanup).
# Kept here so patterns.py and the CLI sort by the SAME order.
# ---------------------------------------------------------------------------
SEVERITY_RANK: Dict[str, int] = {"P0": 0, "P1": 1, "P2": 2}


def severity_rank(sev: Any) -> int:
    """Sortable rank for a severity string; unknown severities sort last."""
    return SEVERITY_RANK.get(str(sev), 99)


# ---------------------------------------------------------------------------
# THE CANONICAL REMEDIATION MAP.  pattern_id -> work order.
#
# Each value carries the four engineering fields.  ``default_severity`` is the
# severity this pattern takes when the detector has no stronger signal (a
# detector may override, e.g. a single source-not-used regression is still P1).
# ---------------------------------------------------------------------------
REMEDIATIONS: Dict[str, Dict[str, Any]] = {

    # --- source retrieved but not used -------------------------------------
    # The canonical worked example.  This was just FIXED via the reference-recall
    # seam, so on current traces it should be RARE; we keep the remediation so a
    # regression resurfaces with a ready-made, certifiable work order.
    "source_use": {
        "title": "Source retrieved but not used",
        "default_severity": "P1",
        "root_cause": (
            "A source/reference was retrieved and labeled for the turn, but the shipped "
            "answer did not route through it (route != reference:recall / quality.source_used "
            "false). The reference-recall seam that grounds the reply in the stored source was "
            "bypassed, so the user got a model answer while a labeled source sat unused."
        ),
        "recommended_fix": (
            "Re-assert the reference-recall seam: when relevant_sources() returns a labeled "
            "match, recall() FROM that source must own the turn (backend reference:recall) "
            "before the LLM path is eligible. Guard it so a retrieved-but-unused source is "
            "impossible, not merely unlikely."
        ),
        "cert_required": [
            "scripts/certify_no_stubs.py --gate",
            "python3 -m anima.source_aware --selftest",
        ],
        "expected_improvement": {
            "source_grounding": "retrieved source is USED, not bypassed",
            "metric": "source_used_rate",
            "from": "regressed (<1.0 on source-eligible turns)",
            "to": 1.0,
        },
    },

    # --- memory known but hedged / correction lost -------------------------
    # The live P0 WALLPAPER from live_path_results.json (conversation_repair).
    "conversation_repair": {
        "title": "Correction lost — memory known but not superseded",
        "default_severity": "P0",
        "root_cause": (
            "memory_lirf.extract() dog_name anchor (lines 361-364) requires a 'my dog ... <Name>' "
            "shape, so a natural correction like 'his name is Atlas' extracts NOTHING; and "
            "_RETRACT_CUE (line 534) lacks 'scratch that' / 'not X, Y'. On the contract's killer "
            "phrasing — 'scratch that — not Rex, his name is Atlas' — the bad value 'Rex' stays the "
            "ACTIVE fact and the corrected 'Atlas' is LOST. There is no supersede-the-last-turn "
            "primitive; only a full re-statement supersedes."
        ),
        "recommended_fix": (
            "Add a deterministic conversation-repair seam: a supersede-the-last-turn primitive. "
            "Extend _RETRACT_CUE with 'scratch that' / 'not X, Y' / 'I said Y', and on a retract "
            "cue rebind the most-recent same-slot fact to the corrected value (old -> history, "
            "new -> active) even when no fresh 'my dog ... <Name>' anchor is present."
        ),
        "cert_required": [
            "conversation_repair killer test",
            "certify_repair.py",
        ],
        "expected_improvement": {
            "behavior": "correction supersedes the prior fact within the same turn",
            "killer_phrase": "scratch that — not Rex, his name is Atlas",
            "from": "LINGERS->Rex (correction lost)",
            "to": "SUPERSEDED->Atlas (correction wins)",
        },
    },

    # --- capability enabled but unavailable --------------------------------
    "capability_truth": {
        "title": "Capability claims LIVE but the runtime probe refuses",
        "default_severity": "P1",
        "root_cause": (
            "The settings/capability ledger advertises a capability as LIVE/enabled, but the "
            "runtime probe for that capability refuses or errors (the settings ledger and the "
            "runtime ledger disagree). The surface promises something the runtime will not do."
        ),
        "recommended_fix": (
            "Make the settings ledger == the runtime ledger: gate every capability at the "
            "runtime so an advertised-LIVE capability that the probe refuses is impossible. "
            "Either wire the runtime to honor the cap, or label the surface OFF/'soon' to match "
            "the probe (honest UI)."
        ),
        "cert_required": [
            "capability_truth live-path check",
            "scripts/certify_no_stubs.py --gate",
        ],
        "expected_improvement": {
            "invariant": "advertised capability == runtime capability",
            "from": "ledger says LIVE, probe refuses",
            "to": "ledger and probe agree",
        },
    },

    # --- UKI planned but not committed -------------------------------------
    "uki_commit": {
        "title": "Knowledge planned but never committed (URL/PDF gap)",
        "default_severity": "P1",
        "root_cause": (
            "An intake source produced a plan but was never committed durably (committed=false / "
            "parse_status needs_dependency). URL / PDF / YouTube / image inputs honestly stop at "
            "needs_dependency: the parser dependency is absent, so the source never reaches a "
            "store and cannot be retrieved later."
        ),
        "recommended_fix": (
            "Land the missing intake parser dependency for the affected type so plan -> approve -> "
            "commit -> durable -> retrieve closes end-to-end, OR keep the honest needs_dependency "
            "stop and surface it as a tracked gap (not a silent drop)."
        ),
        "cert_required": [
            "scripts/intake_cert.py",
            "scripts/certify_no_stubs.py --gate",
        ],
        "expected_improvement": {
            "behavior": "planned source commits durably and is retrievable after restart",
            "from": "committed=false (needs_dependency)",
            "to": "committed=true, retrievable",
        },
    },

    # --- LLM used when a deterministic route exists ------------------------
    "llm_vs_deterministic": {
        "title": "LLM used when a deterministic route existed",
        "default_severity": "P2",
        "root_cause": (
            "route=llm on a turn whose shape matched a deterministic seam (host / reference / "
            "lerf): memory, LERF objects, or an Argus capability were consulted and returned "
            "material on a simple turn, yet the reply still went through the language model — "
            "wasted tokens and latency for an answer a cheaper path could have shipped."
        ),
        "recommended_fix": (
            "Route this shape to the deterministic seam before the LLM is eligible "
            "(LERF-first / reference-recall / host-answer), and reduce retrieval depth on the "
            "shapes where the model adds no quality."
        ),
        "cert_required": [
            "scripts/certify_live_paths.py --gate",
            "scripts/whole_mri_tune.py --selftest",
        ],
        "expected_improvement": {
            "metric": "llm_route_share_on_deterministic_shapes",
            "direction": "down",
            "secondary": "lower latency_ms and tokens_out on these turns",
        },
    },

    # --- response stripped into incompleteness -----------------------------
    "completeness": {
        "title": "Response stripped below the completeness bar",
        "default_severity": "P1",
        "root_cause": (
            "The final gate stripped/altered the candidate reply, or completeness checking marked "
            "the shipped response as too thin (response_complete false). The gate held the line "
            "late, but upstream generation produced something it had to repair, and the user got "
            "a partial reply."
        ),
        "recommended_fix": (
            "Strengthen completeness upstream of the final gate so the reply reaches the gate "
            "already sentence-terminal and above the completeness bar; keep the gate as the last "
            "guard, not the place where the answer is first made whole."
        ),
        "cert_required": [
            "response_completeness live-path check",
            "scripts/certify_whole_mri.py --gate",
        ],
        "expected_improvement": {
            "metric": "response_complete_rate",
            "to": 1.0,
            "secondary": "final gate strips text on 0 turns",
        },
    },

    # --- host resource spike during intake ---------------------------------
    "host_resource_spike": {
        "title": "Host resource spike during a turn",
        "default_severity": "P2",
        "root_cause": (
            "CPU / memory / disk / network on the Mac moved a lot while this turn ran (host-heavy "
            "shape), frequently coinciding with intake/parse work. The turn may be slowed by other "
            "processes, or may itself be the load."
        ),
        "recommended_fix": (
            "Investigate host contention for this turn shape: bound the concurrent host load "
            "(throttle intake/parse during a live turn), and cache redundant host snapshots."
        ),
        "cert_required": [
            "scripts/certify_whole_mri.py --gate",
            "anima.host_window probe",
        ],
        "expected_improvement": {
            "metric": "host_load_p75",
            "direction": "down",
        },
    },

    # --- retrieval depth increases cost without quality --------------------
    "retrieval_depth_cost": {
        "title": "Retrieval depth raised cost without raising quality",
        "default_severity": "P2",
        "root_cause": (
            "A turn paid a top-quartile resource cost (tokens + memory/LERF reads + Argus calls) "
            "without a matching quality gain — deeper/extra retrieval bought cost, not a better "
            "answer."
        ),
        "recommended_fix": (
            "Cap retrieval depth on this shape and reuse a single snapshot/object set; spend the "
            "extra reads only where they measurably move quality."
        ),
        "cert_required": [
            "scripts/whole_mri_tune.py --selftest",
            "scripts/certify_whole_mri.py --gate",
        ],
        "expected_improvement": {
            "metric": "resource_cost_per_quality_point",
            "direction": "down",
        },
    },
}


# A stable, honest fallback for an unknown pattern_id — never crash, never fabricate.
_GENERIC = {
    "root_cause": "No canonical root cause is registered for this pattern_id.",
    "recommended_fix": "Investigate the evidence and register a remediation in anima/root_cause.py.",
    "cert_required": [],
    "expected_improvement": {},
}


def remediation_for(pattern_id: str) -> Dict[str, Any]:
    """Return the four-field work order for ``pattern_id``.

    ALWAYS returns a dict carrying exactly the keys
    ``root_cause``, ``recommended_fix``, ``cert_required``, ``expected_improvement``.
    An unknown id yields the honest generic placeholder (never raises).
    """
    entry = REMEDIATIONS.get(pattern_id)
    if not entry:
        return dict(_GENERIC)
    return {
        "root_cause": entry["root_cause"],
        "recommended_fix": entry["recommended_fix"],
        "cert_required": list(entry.get("cert_required", [])),
        "expected_improvement": dict(entry.get("expected_improvement", {})),
    }


def default_severity_for(pattern_id: str) -> str:
    """The severity a pattern takes when the detector has no stronger signal."""
    entry = REMEDIATIONS.get(pattern_id)
    return str(entry.get("default_severity", "P2")) if entry else "P2"


def title_for(pattern_id: str) -> str:
    """The canonical human title for a pattern_id (falls back to the id)."""
    entry = REMEDIATIONS.get(pattern_id)
    return str(entry.get("title", pattern_id)) if entry else str(pattern_id)


__all__ = [
    "REMEDIATIONS",
    "SEVERITY_RANK",
    "severity_rank",
    "remediation_for",
    "default_severity_for",
    "title_for",
]
