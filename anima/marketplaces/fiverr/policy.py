"""marketplaces.fiverr.policy — the Fiverr acceptability gate.

Every Fiverr page/data/action is classified before use. Unauthorized scraping, anti-bot bypass, mass
messaging, fake reviews/engagement, off-platform payment circumvention, third-party-ToS-violating
services, and regulated/prohibited services are BLOCKED. An unclear source defaults to
NEEDS_HUMAN_REVIEW (never auto-allowed). Allowed: reading public docs, manual market review, operating
Collatio's OWN account, and fulfilling purchased orders.
"""
from __future__ import annotations

from pathlib import Path

from anima.company import storage

CLASSIFICATIONS = ("ALLOWED_PUBLIC_DOC_RESEARCH", "ALLOWED_MANUAL_MARKET_REVIEW",
                   "ALLOWED_OWN_ACCOUNT_OPERATION", "ALLOWED_ORDER_FULFILLMENT", "NEEDS_HUMAN_REVIEW",
                   "BLOCKED_UNAUTHORIZED_SCRAPING", "BLOCKED_MASS_MESSAGING",
                   "BLOCKED_FAKE_REVIEW_OR_ENGAGEMENT", "BLOCKED_TOS_CIRCUMVENTION",
                   "BLOCKED_THIRD_PARTY_TOS_VIOLATION", "BLOCKED_REGULATED_OR_PROHIBITED_SERVICE")
_ALLOWED = ("ALLOWED_PUBLIC_DOC_RESEARCH", "ALLOWED_MANUAL_MARKET_REVIEW",
            "ALLOWED_OWN_ACCOUNT_OPERATION", "ALLOWED_ORDER_FULFILLMENT")


def classify(name: str, *, action: str, source_policy_status: str = "unknown",
             uses_automation: bool = False, bulk_extraction: bool = False, sends_messages: bool = False,
             mass_messaging: bool = False, fake_review_or_engagement: bool = False,
             off_platform_payment: bool = False, third_party_tos_violation: bool = False,
             regulated_or_prohibited_service: bool = False, requires_login: bool = False,
             store: Path | None = None) -> dict:
    """Return the policy classification for a Fiverr action. Blocks take precedence; unknown sources
    route to human review; otherwise the action verb decides the allowed class."""
    def out(cls, reason, *, allowed, approval=False, blocked=None, limits=None):
        rec = {"classification": cls, "allowed": allowed, "reason": reason,
               "required_approval": approval, "required_limits": limits or [],
               "blocked_reason": blocked, "evidence_refs": []}
        storage.emit_truth(name, "fiverr_policy", action, "POLICY %s -> %s" % (action, cls),
                           actor="vera", store=store)
        return rec

    # --- hard blocks first ---
    if uses_automation and (bulk_extraction or "scrape" in action.lower()):
        return out("BLOCKED_UNAUTHORIZED_SCRAPING", "automated/bulk extraction of Fiverr is not permitted",
                   allowed=False, blocked="unauthorized_scraping")
    if mass_messaging or (sends_messages and "mass" in action.lower()):
        return out("BLOCKED_MASS_MESSAGING", "mass/unsolicited messaging is not permitted",
                   allowed=False, blocked="mass_messaging")
    if fake_review_or_engagement:
        return out("BLOCKED_FAKE_REVIEW_OR_ENGAGEMENT", "fake reviews/engagement are forbidden",
                   allowed=False, blocked="fake_review_or_engagement")
    if off_platform_payment:
        return out("BLOCKED_TOS_CIRCUMVENTION", "off-platform payment circumvention is forbidden",
                   allowed=False, blocked="tos_circumvention")
    if third_party_tos_violation:
        return out("BLOCKED_THIRD_PARTY_TOS_VIOLATION", "service would violate a third party's ToS",
                   allowed=False, blocked="third_party_tos_violation")
    if regulated_or_prohibited_service:
        return out("BLOCKED_REGULATED_OR_PROHIBITED_SERVICE",
                   "regulated/prohibited service — blocked or needs professional qualification",
                   allowed=False, blocked="regulated_or_prohibited")

    # --- unknown source => human review ---
    if source_policy_status == "known_blocked":
        return out("BLOCKED_THIRD_PARTY_TOS_VIOLATION", "source is known-blocked", allowed=False,
                   blocked="known_blocked")
    if source_policy_status == "unknown":
        return out("NEEDS_HUMAN_REVIEW", "source policy unclear — manual/human-approved only",
                   allowed=False, approval=True)

    # --- allowed verbs ---
    a = action.lower()
    if "help" in a or "doc" in a or "policy" in a or "terms" in a:
        return out("ALLOWED_PUBLIC_DOC_RESEARCH", "reading public help/policy docs", allowed=True)
    if "fulfill" in a or "deliver" in a or "order" in a:
        return out("ALLOWED_ORDER_FULFILLMENT", "fulfilling a purchased order via governed workflow",
                   allowed=True)
    if "own_account" in a or "dashboard" in a or "draft" in a or "respond" in a:
        return out("ALLOWED_OWN_ACCOUNT_OPERATION", "operating Collatio's own account (draft/respond)",
                   allowed=True, approval=("respond" in a or "publish" in a))
    if "review" in a or "research" in a or "browse" in a:
        if uses_automation:
            return out("NEEDS_HUMAN_REVIEW", "automated research at scale needs review", allowed=False, approval=True)
        return out("ALLOWED_MANUAL_MARKET_REVIEW", "manual public market review", allowed=True)
    return out("NEEDS_HUMAN_REVIEW", "unrecognized action — defaults to human review", allowed=False, approval=True)


def is_allowed(rec: dict) -> bool:
    return rec.get("allowed") and rec.get("classification") in _ALLOWED
