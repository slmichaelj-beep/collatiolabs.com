"""archetypal_patterns.policy — the anti-overreach guarantees + the pattern->improvement bridge.

The whole layer is safe only if it CANNOT cross from system-pattern into user-diagnosis. These guards
are what certify_archetype_no_user_diagnosis verifies.
"""
from __future__ import annotations

from . import schema, detector


def is_system_pattern(p: dict) -> bool:
    """A pattern is acceptable ONLY if it is scoped to the SYSTEM, is not about the user, and is not a
    diagnosis. Anything else is a violation of the anti-overreach law."""
    try:
        return (p.get("scope") == "system" and p.get("is_about_user") is False
                and p.get("is_diagnosis") is False and p.get("archetype") in schema.ARCHETYPE_IDS)
    except Exception:
        return False


def all_system(patterns) -> bool:
    return bool(patterns) and all(is_system_pattern(p) for p in patterns)


def meets_evidence_threshold(p: dict) -> bool:
    """A pattern may only be presented as a HYPOTHESIS (vs 'watching') with repeated evidence +
    provenance — never inferred from one event."""
    return (p.get("status") == "hypothesis"
            and int(p.get("evidence_count", 0)) >= schema.EVIDENCE_THRESHOLD
            and bool(p.get("evidence")))


def to_improvement(p: dict) -> dict:
    """Map a SYSTEM archetype hypothesis to an improvement SUGGESTION for the Improvement Engine — a
    product action, never a claim about the user. Returns {} for a non-promoted/non-system pattern."""
    if not (is_system_pattern(p) and meets_evidence_threshold(p)):
        return {}
    return {
        "improvement_id": "archetype:%s" % p["archetype"],
        "title": "%s pattern — %s" % (p["label"], p["system_question"]),
        "recommendation": p.get("recommended_action"),
        "expected_benefit": "address a recurring SYSTEM pattern surfaced by the archetypal registry",
        "evidence": p.get("evidence"),
        "source_archetype": p["archetype"],
        "is_about_user": False,
        "disclaimer": p.get("disclaimer"),
    }


# A frozen list of forbidden output shapes — the registry must never produce any of these. The cert
# scans the live registry output to prove NONE appear.
FORBIDDEN_USER_CLAIMS = (
    "you are a", "you're a", "the user is", "you have a", "you exhibit", "diagnos",
    "your shadow", "your persona", "your archetype", "you are the",
)


def scan_for_user_diagnosis(patterns) -> list:
    """Return any patterns whose visible text crosses into labelling/diagnosing the USER. Empty == safe.
    The detector has no path that produces these, so this should always return []."""
    bad = []
    for p in patterns:
        blob = " ".join(str(p.get(k, "")) for k in ("hypothesis", "meaning", "system_question",
                                                     "recommended_action", "label")).lower()
        if (not is_system_pattern(p)) or any(s in blob for s in FORBIDDEN_USER_CLAIMS):
            bad.append(p.get("archetype"))
    return bad


def safe_registry(name: str = "Vera") -> dict:
    """The registry, with the anti-overreach guarantee enforced: if ANY pattern would cross into user
    diagnosis, it is dropped (fail safe). In practice the detector never produces such a pattern."""
    reg = detector.registry(name)
    reg["patterns"] = [p for p in reg.get("patterns", []) if is_system_pattern(p)
                       and not scan_for_user_diagnosis([p])]
    reg["no_user_diagnosis"] = (scan_for_user_diagnosis(detector.detect(name)) == [])
    return reg
