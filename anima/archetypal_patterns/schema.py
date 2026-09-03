"""archetypal_patterns.schema — the SYSTEM-facing archetype vocabulary (pure data; no I/O).

Each archetype names a recurring shape in VERA'S OWN behaviour/UI, with the real telemetry source that
evidences it. These are hypotheses about the SYSTEM, never labels for the user.
"""
from __future__ import annotations

# The allowed pattern language (Jung, applied to the product, not the person).
ARCHETYPES = {
    "shadow": {
        "label": "Shadow",
        "meaning": "Rejected / unsafe material that must be SEEN as evidence but never ABSORBED into "
                   "trusted context, memory, or identity.",
        "system_question": "Is hostile/injected material being held as evidence and kept out of trust?",
        "source": "incident.quarantines (the Context Immune catches)",
        "healthy_when": "caught + held as evidence, never absorbed",
        "recommended_action": "review quarantined items on /security; confirm none re-entered context",
    },
    "trickster": {
        "label": "Trickster",
        "meaning": "Confusing loops, misdirection, contradictory UI, or unsafe cleverness — the system "
                   "fooling the user (or itself) instead of being plainly honest.",
        "system_question": "Are repeated confusing/contradictory product behaviours recurring?",
        "source": "reports/patterns.json (the Pattern Observatory — repeated issues)",
        "healthy_when": "no repeating confusion patterns; issues become improvements",
        "recommended_action": "open Patterns & Improvements; promote the recurring issue to a fix",
    },
    "persona": {
        "label": "Persona",
        "meaning": "The interface / role mask. It may shape tone, but it must NEVER hide the truth or "
                   "let Vera disclaim what she is.",
        "system_question": "Is the character mask holding without hiding truth (no #1-rule breaks shipped)?",
        "source": "incident events (quarantine route=output) + the never-break-character gate",
        "healthy_when": "character held; no self-disclaiming output ships",
        "recommended_action": "review any output-gate blocks on /security",
    },
    "self": {
        "label": "Self",
        "meaning": "The coherent operating identity and integration target — the stable centre the other "
                   "patterns orbit.",
        "system_question": "Is identity stable + observed (no unapproved mutation)?",
        "source": "identity_sandbox + self-narrative provenance",
        "healthy_when": "identity stable, observed, freeze-respected",
        "recommended_action": "review Identity Health (when built); none needed while stable",
    },
    "mentor": {
        "label": "Mentor",
        "meaning": "Guidance WITHOUT control — Vera offers options, tradeoffs, and a recommendation, but "
                   "the user calls the shot. Suggest-only, never execute.",
        "system_question": "Is agency staying suggest-only (proposals awaiting approval, never silent power)?",
        "source": "agency_suggestions + the approval queue",
        "healthy_when": "suggestions made + awaiting approval; nothing executed silently",
        "recommended_action": "review the Approval Queue; approve/reject suggestions",
    },
    "threshold": {
        "label": "Threshold / Rite",
        "meaning": "A state transition that REQUIRES consent, proof, and a rollback path — a doorway you "
                   "cross deliberately, not by accident.",
        "system_question": "Are state transitions (consent, lockdown, identity change) gated by consent + proof + rollback?",
        "source": "consent decisions + lockdown/restore + held sensitive memories",
        "healthy_when": "every transition has consent + an audit trail + a reversal",
        "recommended_action": "review Consent & Boundaries + the Security lockdown control",
    },
}

ARCHETYPE_IDS = tuple(ARCHETYPES.keys())

# A pattern is only PROMOTED to a hypothesis once it has at least this many evidence occurrences.
EVIDENCE_THRESHOLD = 3

STATUSES = ("watching", "hypothesis", "acted_on")   # never 'diagnosed' — there is no diagnosis here


def pattern_object_example() -> dict:
    """The documented archetypal-pattern shape (system hypothesis, not a user claim)."""
    return {
        "pattern_id": "shadow", "archetype": "shadow", "label": "Shadow",
        "scope": "system",  # ALWAYS 'system' — never 'user'
        "is_diagnosis": False, "is_about_user": False,
        "hypothesis": "Hostile material is being caught + held as evidence (healthy shadow handling).",
        "evidence": [], "evidence_count": 0, "confidence": 0.0,
        "status": "watching|hypothesis|acted_on",
        "recommended_action": "...", "required_cert": [],
        "disclaimer": "A hypothesis about SYSTEM behaviour, not a diagnosis of any person.",
    }
