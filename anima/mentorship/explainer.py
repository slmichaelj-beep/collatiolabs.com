"""mentorship.explainer — turn a decision (or a real agency suggestion) into a non-coercive tradeoff.

Pure transforms; no I/O. The output is suggest-only (execution_allowed=False, requires_approval=True) and
always carries >= MIN_OPTIONS options with honest pros/cons, a recommendation the USER owns, and a plain
'you decide' framing.
"""
from __future__ import annotations

from . import schema


def _norm_option(o: dict) -> dict:
    """Normalise an option so it always has pros + cons (an option with no honest cons is a red flag the
    cert checks for — every real choice has a downside)."""
    return {
        "label": str(o.get("label") or "Option"),
        "pros": [str(p) for p in (o.get("pros") or [])] or ["(no clear upside stated)"],
        "cons": [str(c) for c in (o.get("cons") or [])] or ["(no clear downside stated)"],
        "effort": str(o.get("effort") or "unknown"),
        "risk": str(o.get("risk") or "unknown"),
    }


def explain_tradeoff(decision: str, options: list, recommend=None, reason: str = "") -> dict:
    """Build a non-coercive tradeoff. `recommend` is an index or label (optional). If fewer than
    MIN_OPTIONS are given, the standing 'keep things as they are' option is added so doing nothing is
    always a real choice."""
    opts = [_norm_option(o) for o in (options or [])]
    if len(opts) < schema.MIN_OPTIONS:
        opts.append(_norm_option(schema.DO_NOTHING))

    rec_label = None
    if isinstance(recommend, int) and 0 <= recommend < len(opts):
        rec_label = opts[recommend]["label"]
    elif isinstance(recommend, str):
        rec_label = next((o["label"] for o in opts if o["label"] == recommend), None)

    recommendation = None
    if rec_label is not None:
        recommendation = {
            "label": rec_label,
            "reason": str(reason or "On balance this looks like the best fit — but it's your call."),
        }

    return {
        "decision": str(decision),
        "options": opts,
        "recommendation": recommendation,        # may be None — a recommendation is optional, never forced
        "decision_owner": schema.DECISION_OWNER,  # always 'user'
        "you_decide": "These are the options as I see them. The choice is yours — tell me which way to go.",
        "requires_approval": True,
        "execution_allowed": False,               # suggest-only, inherited from agency
        "disclaimer": "Guidance, not a directive. You decide; nothing happens until you say so.",
    }


def from_suggestion(sugg: dict) -> dict:
    """Wrap a REAL agency suggestion (anima/agency_suggest schema) into a non-coercive tradeoff: the
    proposed action as one option, the standing 'do nothing' as another, recommending the proposal while
    leaving the decision with the user."""
    proposal = {
        "label": str(sugg.get("suggestion") or "Do the proposed thing"),
        "pros": [str(sugg.get("reason"))] if sugg.get("reason") else ["Addresses what prompted this"],
        "cons": ["Takes an action you'd otherwise not take yet",
                 "Risk level: %s" % (sugg.get("risk") or "unknown")],
        "effort": "some",
        "risk": str(sugg.get("risk") or "unknown"),
    }
    t = explain_tradeoff(
        decision="Whether to: %s" % (sugg.get("suggestion") or "proceed"),
        options=[proposal, schema.DO_NOTHING],
        recommend=0,
        reason=str(sugg.get("reason") or "It fits what you're trying to do — but it's your call."),
    )
    t["source_intent_id"] = sugg.get("intent_id")
    t["action_type"] = sugg.get("action_type")
    return t


def rendered_text(t: dict) -> str:
    """All visible mentorship text (for the no-coercion scan)."""
    parts = [t.get("decision", ""), t.get("you_decide", ""), t.get("disclaimer", "")]
    for o in t.get("options", []):
        parts += [o.get("label", "")] + o.get("pros", []) + o.get("cons", [])
    if t.get("recommendation"):
        parts += [t["recommendation"].get("label", ""), t["recommendation"].get("reason", "")]
    return " \n ".join(str(p) for p in parts)
