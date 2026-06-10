"""revenue.revops — Collatio Labs LLC revenue-operations rails (governed, no raw secrets).

Tracks the real-world launch readiness (payment path, business bank, sender email, calendar, buyer
list, outreach approval, CRM) as non-sensitive records; runs the account registry so accounts are
tracked WITHOUT raw credentials (a value that looks like a card/routing number/password/API key is
rejected); enforces the operator boundary (what Vera may draft vs what needs approval vs what it can
never store); and produces the bank/Stripe/email setup packets + the launch checklist. Vera prepares
and operates; Lamar owns credentials, opens accounts, and approves external actions.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from anima.company import storage
from . import milestone as _m

# launch-readiness keys feeding /revenue/cash
READINESS_KEYS = ("payment_path", "business_bank", "sender_email", "calendar", "buyer_list",
                  "outreach_approval", "offer_approval", "crm")
STATUS = ("missing", "pending", "active", "approved", "rejected")
CATEGORIES = ("bank", "payments", "email", "phone", "crm", "calendar", "website", "domain",
              "support", "marketing", "accounting", "password_manager")
ACCESS_LEVELS = ("none", "metadata_only", "draft_only", "approved_action_only", "read_only", "limited_operator")

# things Vera may never store raw — detected and rejected
_SECRET_PATTERNS = [
    re.compile(r"\b\d{13,19}\b"),                      # card / long account numbers
    re.compile(r"\b\d{9}\b"),                          # routing number
    re.compile(r"\bsk_(live|test)_[A-Za-z0-9]+"),      # Stripe secret key
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),              # SSN
    re.compile(r"(?i)\b(password|passwd|pwd|2fa|otp|seed|recovery code|api[_ ]?secret)\b\s*[:=]"),
]

# operator boundary (directive §1 / §7)
MAY_DRAFT = ("draft_email", "draft_landing_page", "draft_offer_page", "draft_proposal", "draft_invoice",
             "prepare_stripe_invoice_details", "track_invoice_status", "track_pipeline", "track_delivery",
             "track_net_profit", "prepare_support_reply", "prepare_followup", "prepare_bank_checklist",
             "prepare_resource_request", "prepare_professional_review")
NEEDS_APPROVAL = ("send_outreach", "publish_page", "contact_buyer", "send_proposal", "send_invoice",
                  "spend_money", "subscribe_tool", "hire_vendor", "open_account", "customer_commitment",
                  "book_meeting_auto", "use_customer_data_externally")
NEVER = ("store_bank_number", "store_card_number", "store_password", "store_api_secret",
         "store_2fa_seed", "store_recovery_code", "store_ssn", "store_gov_id")


# ---- readiness ----
def _read(name, store): return storage.load(name, "revops_readiness", store, default={"flags": {}})


def set_readiness(name: str, key: str, status: str, *, pointer: str = "", approval_ref: str = "",
                  store: Path | None = None) -> dict:
    """Set a readiness flag with a NON-SENSITIVE pointer. Refused if the pointer looks like a raw
    secret. outreach_approval / offer_approval require an approval ref."""
    if key not in READINESS_KEYS:
        return {"ok": False, "error": "unknown readiness key %r" % key}
    if status not in STATUS:
        return {"ok": False, "error": "bad status %r" % status}
    if _looks_secret(pointer):
        return {"ok": False, "error": "that looks like a raw secret — store only a safe pointer"}
    if key in ("outreach_approval", "offer_approval") and status == "approved" and not (approval_ref or "").strip():
        return {"ok": False, "error": "%s=approved needs an approval ref" % key}
    r = _read(name, store)
    r["flags"][key] = {"status": status, "pointer": pointer or None, "approval_ref": approval_ref or None,
                       "at": storage.now()}
    storage.save(name, "revops_readiness", r, store)
    storage.emit_truth(name, "revops_readiness", key, "READINESS %s = %s" % (key, status),
                       actor="user", store=store)
    return {"ok": True, "flags": r["flags"]}


def readiness(name: str, store: Path | None = None) -> dict:
    flags = _read(name, store)["flags"]
    # payment_path is also authoritatively known to the milestone tracker
    pay = _m.payment_path_status(name, store)
    payment_status = "active" if pay["exists"] else flags.get("payment_path", {}).get("status", "missing")
    out = {k: flags.get(k, {}).get("status", "missing") for k in READINESS_KEYS}
    out["payment_path"] = payment_status
    cleared = (out["offer_approval"] == "approved" and out["payment_path"] == "active"
               and out["sender_email"] == "active" and out["buyer_list"] in ("active", "approved")
               and out["outreach_approval"] == "approved")
    blockers = []
    if out["payment_path"] != "active":
        blockers.append("payment path not active (Lamar must set up / confirm — human-only)")
    if out["business_bank"] != "active":
        blockers.append("business bank not active (payout destination) — PARTIALLY BLOCKED")
    if out["sender_email"] != "active":
        blockers.append("sender email not set")
    if out["buyer_list"] not in ("active", "approved"):
        blockers.append("approved buyer list not provided")
    if out["offer_approval"] != "approved":
        blockers.append("offer/pricing not approved")
    if out["outreach_approval"] != "approved":
        blockers.append("first outreach batch not approved")
    return {"ok": True, "flags": out, "cleared_to_launch": cleared, "blockers": blockers,
            "honesty": "all credential/account/send actions are human-only; Vera tracks readiness "
                       "via non-sensitive pointers, never raw secrets."}


# ---- account registry (no raw secrets) ----
def register_account(name: str, *, service_name: str, category: str, purpose: str = "",
                     vera_access_level: str = "metadata_only", credentials_location: str = "password_manager",
                     two_factor_enabled: str = "unknown", kyc_required: bool = True,
                     risk_level: str = "low", raw_value_check: str = "", store: Path | None = None) -> dict:
    """Register a Collatio account as a governed record. raw_value_check is scanned and the call is
    REFUSED if it contains anything secret-looking — Vera never stores raw credentials."""
    if category not in CATEGORIES:
        return {"ok": False, "error": "unknown category %r" % category}
    if _looks_secret(credentials_location) or _looks_secret(raw_value_check) or _looks_secret(purpose):
        return {"ok": False, "error": "raw credential detected — only safe pointers are stored"}
    if vera_access_level not in ACCESS_LEVELS:
        vera_access_level = "metadata_only"
    rec = {"account_id": "acct_" + uuid.uuid4().hex[:10], "entity_id": "collatio_labs_llc",
           "service_name": service_name, "category": category, "purpose": purpose,
           "status": "needed", "owner": "Collatio Labs LLC", "human_admin": "Lamar",
           "vera_access_level": vera_access_level, "credentials_location": "password_manager_ref_only",
           "raw_credentials_stored": False, "two_factor_enabled": two_factor_enabled,
           "recovery_documented": "unknown", "kyc_required": bool(kyc_required), "approval_ref": None,
           "risk_level": "regulated" if category in ("bank", "payments") else risk_level, "notes": []}
    storage.save(name, "revops_account_%s" % rec["account_id"], rec, store)
    _idx(name, rec["account_id"], store)
    return {"ok": True, "account": rec}


def accounts(name: str, store: Path | None = None) -> list:
    idx = storage.load(name, "revops_account_index", store, default={"ids": []})["ids"]
    return [a for a in (storage.load(name, "revops_account_%s" % i, store, default=None) for i in idx) if a]


# ---- operator boundary ----
def can(name: str, action: str, *, approval_ref: str = "") -> dict:
    if action in NEVER:
        return {"allowed": False, "reason": "Vera never does this (raw secret / account action)"}
    if action in NEEDS_APPROVAL:
        if not (approval_ref or "").strip():
            return {"allowed": False, "reason": "requires Lamar approval", "approval_required": True}
        return {"allowed": True, "via": "approval"}
    if action in MAY_DRAFT:
        return {"allowed": True, "via": "draft/prepare scope"}
    return {"allowed": False, "reason": "unknown action — default deny"}


def operator_boundary() -> dict:
    return {"may_draft": list(MAY_DRAFT), "needs_approval": list(NEEDS_APPROVAL), "never": list(NEVER)}


# ---- setup packets + launch checklist ----
def bank_setup_packet() -> dict:
    return {"packet": "business_bank_setup", "compare_on": ["monthly fees", "ACH/wire support",
            "debit card", "online banking", "accounting integrations", "Stripe compatibility",
            "minimum balance", "initial deposit", "support", "security/2FA"],
            "checklist": ["confirm EIN", "locate LLC formation docs", "locate operating agreement",
                          "confirm business address", "choose bank", "apply as Collatio Labs LLC",
                          "complete KYC personally", "enable 2FA", "store credentials in password manager",
                          "create account registry record", "tell Vera 'business checking is active'",
                          "connect Stripe/PayPal payouts"],
            "vera_does": ["prepare comparison + documents checklist", "track status + missing items"],
            "vera_never": ["ask for or store the bank login / account number"]}


def stripe_setup_checklist() -> dict:
    return {"packet": "stripe_setup", "lamar_steps": ["create/log into Stripe", "set business type LLC",
            "enter Collatio Labs LLC legal details", "complete identity/business verification",
            "add payout bank when available", "enable invoicing/payment links", "enable 2FA",
            "store credentials securely", "confirm to Vera 'Stripe invoicing active'"],
            "vera_records": {"provider": "Stripe", "status": "pending", "business_entity": "Collatio Labs LLC",
                             "credentials": "password_manager_ref_only"},
            "vera_can_then": ["prepare invoice drafts (client/service/amount/scope/due/terms)"]}


def email_setup_checklist() -> dict:
    return {"packet": "business_email_setup", "recommended": ["Google Workspace", "Proton", "Fastmail"],
            "minimum": ["one professional sender", "SPF/DKIM/DMARC if possible", "signature", "calendar link"],
            "sender_rule": "messages come from Lamar or clearly from Collatio Labs; never imply Vera is human",
            "best_initial_sender": "lamar@collatiolabs.com"}


def launch_checklist(name: str, store: Path | None = None) -> dict:
    r = readiness(name, store)
    questions = [
        "Do you have the Collatio Labs LLC EIN?",
        "Do you have the LLC formation documents?",
        "Open the business bank account now?",
        "Use Stripe invoicing as the first payment processor?",
        "What business email should sales use?",
        "What calendar link should buyers use?",
        "Approve the AI Revenue + Workflow Audit offer?",
        "Approve the $2,500 / $5,000 / $10,000 pricing ladder?",
        "Can you provide 10–25 warm buyer names?",
        "Approve Vera preparing Batch 1 outreach for final review?",
    ]
    return {"ok": True, "readiness": r["flags"], "cleared_to_launch": r["cleared_to_launch"],
            "blockers": r["blockers"], "questions_for_lamar": questions,
            "minimal_unlock": ["confirm payment path active", "confirm sender email",
                               "approve offer + pricing", "provide 10–25 warm names",
                               "approve Batch 1 outreach"]}


def account_request(name: str, *, needed: str, why_needed: str, milestone_impact: str,
                    minimum_option: str, recommended_option: str, cost: str = "",
                    risk_if_missing: str = "", store: Path | None = None) -> dict:
    if not (milestone_impact or "").strip():
        return {"ok": False, "error": "an account request must state milestone impact"}
    if not (minimum_option and recommended_option):
        return {"ok": False, "error": "needs minimum + recommended options"}
    rec = {"request_id": "areq_" + uuid.uuid4().hex[:10], "needed": needed, "why_needed": why_needed,
           "milestone_impact": milestone_impact, "minimum_option": minimum_option,
           "recommended_option": recommended_option, "cost": cost, "risk_if_missing": risk_if_missing,
           "approval_required": True, "status": "ready_for_lamar"}
    storage.save(name, "revops_request_%s" % rec["request_id"], rec, store)
    return {"ok": True, "request": rec}


# ---- helpers ----
def _looks_secret(s: str) -> bool:
    s = str(s or "")
    return any(p.search(s) for p in _SECRET_PATTERNS)


def _idx(name, aid, store):
    idx = storage.load(name, "revops_account_index", store, default={"ids": []}); idx["ids"].append(aid)
    storage.save(name, "revops_account_index", idx, store)
