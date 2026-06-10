"""collatio.authority — the Collatio-specific operating-authority policy.

Default L0 Think-Only. Research / draft / prepare-packet / internal-task need no approval. External
message / publish / account creation / spend / vendor hire / customer commitment require approval.
Contract / legal filing / tax filing / patent filing / regulated claim require professional review.
Fake identity / spam / raw-credential storage / platform abuse are forbidden outright. This is the
gate every Collatio action checks.
"""
from __future__ import annotations

from pathlib import Path

from anima.company import storage

ALLOWED_WITHOUT_APPROVAL = ("research", "draft", "prepare_packet", "create_internal_task",
                            "send_internal_message")
APPROVAL_REQUIRED = ("external_message", "publish_content", "create_account", "spend_money",
                     "hire_vendor", "customer_commitment")
PROFESSIONAL_REVIEW_REQUIRED = ("contract", "legal_filing", "tax_filing", "patent_filing",
                                "regulated_claim", "sign_contract")
FORBIDDEN = ("fake_identity", "spam", "raw_credential_storage", "platform_abuse",
             "erase_audit_history")


def policy(name: str, store: Path | None = None) -> dict:
    return {"authority_policy_id": "collatio_authority", "entity_id": "collatio_labs_llc",
            "default_level": "L0", "allowed_without_approval": list(ALLOWED_WITHOUT_APPROVAL),
            "approval_required": list(APPROVAL_REQUIRED),
            "professional_review_required": list(PROFESSIONAL_REVIEW_REQUIRED),
            "forbidden": list(FORBIDDEN), "kill_switch_ref": "company_operator.kill_switch"}


def can_do(name: str, action: str, *, approval_ref: str | None = None,
           professional_review_ref: str | None = None, store: Path | None = None) -> dict:
    """The Collatio action gate. Returns whether the action may proceed and what it needs."""
    if action in FORBIDDEN:
        return {"allowed": False, "reason": "forbidden action: %s" % action}
    if action in PROFESSIONAL_REVIEW_REQUIRED:
        if not professional_review_ref:
            return {"allowed": False, "reason": "requires professional review",
                    "professional_review_required": True}
        if not approval_ref:
            return {"allowed": False, "reason": "regulated action also requires Lamar approval",
                    "approval_required": True}
        return {"allowed": True, "via": "professional_review + approval"}
    if action in APPROVAL_REQUIRED:
        if not approval_ref:
            return {"allowed": False, "reason": "requires Lamar approval", "approval_required": True}
        return {"allowed": True, "via": "approval"}
    if action in ALLOWED_WITHOUT_APPROVAL:
        return {"allowed": True, "via": "L0 think-only scope"}
    return {"allowed": False, "reason": "unknown action %r — defaults to deny" % action}
