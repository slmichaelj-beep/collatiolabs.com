"""company_operator.accounts — the Account Setup Registry. Governed, never freewheeling.

Vera PLANS and REGISTERS accounts; it never silently creates them. No fake identities, no raw
passwords stored, 2FA + recovery + ownership recorded, and KYC/banking/regulated accounts are
HUMAN-required. Creating any real account is gated by the authority + approval ledgers.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage

CATEGORIES = ("email", "social", "banking", "payments", "legal", "support", "marketing",
              "hosting", "analytics", "ops", "domain", "code", "developer")
STATUS = ("needed", "planned", "approval_required", "created", "active", "suspended", "closed",
          "blocked")
# categories that ALWAYS require a human to complete (KYC / regulated / financial / identity)
HUMAN_REQUIRED_CATS = ("banking", "payments", "legal", "developer")


def _all(name, store): return storage.load(name, "accounts", store, default={"accounts": []})["accounts"]
def _save(name, a, store): storage.save(name, "accounts", {"accounts": a}, store)


def plan_account(name: str, service_name: str, category: str, *, purpose: str = "",
                 requires_kyc: bool = False, requires_bank: bool = False,
                 store: Path | None = None) -> dict:
    cat = category if category in CATEGORIES else "ops"
    human = cat in HUMAN_REQUIRED_CATS or requires_kyc or requires_bank
    rec = {"account_id": "acct_" + uuid.uuid4().hex[:12], "service_name": service_name,
           "category": cat, "purpose": purpose, "owner": "company/founder",
           "admin_contacts": [], "status": "planned",
           "creation_method": "human_required" if human else "vera_can_prepare_after_approval",
           "requires_kyc": bool(requires_kyc), "requires_2fa": True,
           "requires_legal_entity": cat in ("banking", "payments", "legal"),
           "requires_bank": bool(requires_bank), "requires_human_identity": human,
           "credentials_location": "password_manager_ref (never stored in Vera)",
           "recovery_plan": "document recovery email + phone with the owner",
           "risk_level": "regulated" if human else "low",
           "checklist": _checklist(cat, human), "created_at": storage.now()}
    a = _all(name, store); a.append(rec); _save(name, a, store)
    storage.emit_truth(name, "account", rec["account_id"], "ACCOUNT planned: %s (%s)"
                       % (service_name, cat), actor="vera",
                       risk="high" if human else "low", store=store)
    return rec


def _checklist(cat: str, human: bool) -> list:
    base = ["confirm the business identity/brand", "set the recovery email + phone",
            "enable 2FA", "store credentials in the approved password manager (never in Vera)",
            "record owner + admins in the registry"]
    if human:
        base = ["HUMAN must complete this account (KYC/regulated/financial)"] + base
    if cat in ("email", "social", "marketing"):
        base += ["set the posting/response policy + anti-spam policy before any outreach"]
    return base


def store_credentials(name: str, account_id: str, secret: str, *, store: Path | None = None) -> dict:
    """Refuses, always — Vera never stores raw credentials."""
    return {"ok": False,
            "error": "Vera does not store raw credentials. Put them in your password manager and "
                     "record only a reference in the account registry."}


def get(name, account_id, store): return next((x for x in _all(name, store)
                                               if x["account_id"] == account_id), None)


def list_accounts(name, store: Path | None = None) -> list:
    return _all(name, store)
