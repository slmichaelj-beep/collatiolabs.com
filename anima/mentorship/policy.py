"""mentorship.policy — the anti-coercion guarantees. The whole layer is acceptable only if it CANNOT
pressure the user. These guards are what certify_mentorship proves, including under adversarial pressure.
"""
from __future__ import annotations

from . import schema, explainer

FORBIDDEN_COERCION = schema.COERCION_MARKERS


def scan_for_coercion(t: dict) -> list:
    """Return the reasons a tradeoff would coerce. Empty == non-coercive. Checks BOTH structure (too few
    options / decision taken from the user / execution permitted) AND language (pressure phrases)."""
    reasons = []
    opts = t.get("options") or []
    if len(opts) < schema.MIN_OPTIONS:
        reasons.append("fewer than %d options (take-it-or-leave-it)" % schema.MIN_OPTIONS)
    if t.get("decision_owner") != schema.DECISION_OWNER:
        reasons.append("decision_owner is not the user")
    if t.get("execution_allowed") is True:
        reasons.append("execution_allowed is True (not suggest-only)")
    # every option must show a genuine downside — a 'cons'-free option is a stacked deck
    for o in opts:
        if not (o.get("cons") and any(str(c).strip() for c in o["cons"])):
            reasons.append("option '%s' hides its downsides" % o.get("label"))
    blob = explainer.rendered_text(t).lower()
    for m in FORBIDDEN_COERCION:
        if m in blob:
            reasons.append("coercive phrase: '%s'" % m)
    return reasons


def is_non_coercive(t: dict) -> bool:
    """A tradeoff is acceptable ONLY if it offers a real choice, leaves the decision with the user, is
    suggest-only, hides nothing, and uses no pressure language."""
    return scan_for_coercion(t) == []


def safe_tradeoff(t: dict) -> dict:
    """Fail-safe: never surface a coercive tradeoff. If one would coerce, return it flagged + neutralised
    (decision returned to the user, recommendation downgraded to a note) rather than as guidance."""
    if is_non_coercive(t):
        return t
    safe = dict(t)
    safe["decision_owner"] = schema.DECISION_OWNER
    safe["execution_allowed"] = False
    safe["coercion_blocked"] = scan_for_coercion(t)
    safe["recommendation"] = None        # drop a pushed recommendation when anything looked coercive
    return safe


def recommendation_is_optional(t: dict) -> bool:
    """The recommended option must never be the ONLY option — the user can always pick another."""
    rec = t.get("recommendation")
    if not rec:
        return True
    labels = [o.get("label") for o in (t.get("options") or [])]
    return len(labels) >= schema.MIN_OPTIONS and rec.get("label") in labels
