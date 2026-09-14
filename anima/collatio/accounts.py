"""collatio.accounts — the Collatio Labs LLC account registry.

Tracks which service accounts belong to the entity. No fake identities, no platform abuse, no raw
passwords (credentials live only as a password-manager ref). 2FA required where available; KYC/
banking require a human; no account is created without approval. Ownership stays with Collatio/Lamar.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage
from .entity import ENTITY_ID

CATEGORIES = ("email", "domain", "banking", "payments", "legal", "support", "marketing", "hosting",
              "analytics", "ops", "social")
STATUS = ("needed", "planned", "approval_required", "created", "active", "suspended", "closed", "blocked")
# categories that legally require a human identity / KYC — never machine-created
_HUMAN_REQUIRED = ("banking", "payments")


def _all(name, store): return storage.load(name, "collatio_accounts", store, default={"accounts": []})["accounts"]
def _save(name, a, store): storage.save(name, "collatio_accounts", {"accounts": a}, store)


def register(name: str, *, service_name: str, category: str, purpose: str = "",
             requires_kyc: bool = False, store: Path | None = None) -> dict:
    if category not in CATEGORIES:
        return {"ok": False, "error": "unknown category %r" % category}
    human = requires_kyc or category in _HUMAN_REQUIRED
    rec = {"account_id": "acc_" + uuid.uuid4().hex[:10], "entity_id": ENTITY_ID,
           "service_name": service_name, "category": category, "purpose": purpose,
           "owner": "Collatio Labs LLC", "admin_contacts": [], "status": "needed",
           "requires_kyc": requires_kyc, "requires_2fa": True,
           "requires_legal_entity": category in ("banking", "payments", "legal"),
           "requires_human_identity": human,
           "credentials_location": "password_manager_ref_only", "recovery_plan": "",
           "approval_event": None, "risk_level": "regulated" if human else "low",
           "truth_refs": [], "action_refs": []}
    a = _all(name, store); a.append(rec); _save(name, a, store)
    return {"ok": True, "account": rec}


def create_account_action(name: str, account_id: str, *, approval_ref: str = "",
                          store: Path | None = None) -> dict:
    """Attempt to mark an account created. REFUSED without approval; KYC/banking refused entirely
    (human-only). Raw credentials are never accepted."""
    a = _all(name, store)
    rec = next((r for r in a if r["account_id"] == account_id), None)
    if rec is None:
        return {"ok": False, "error": "no such account"}
    if rec["requires_human_identity"]:
        return {"ok": False, "error": "KYC/banking account is human-only — Vera cannot create it"}
    if not (approval_ref or "").strip():
        return {"ok": False, "error": "account creation requires approval"}
    rec["status"] = "created"; rec["approval_event"] = approval_ref; _save(name, a, store)
    storage.emit_truth(name, "collatio_account", account_id, "ACCOUNT created (approved): " + rec["service_name"],
                       actor="user", store=store)
    return {"ok": True, "account": rec}


def registry(name: str, store: Path | None = None) -> dict:
    a = _all(name, store)
    return {"ok": True, "accounts": a,
            "human_required": [r["service_name"] for r in a if r["requires_human_identity"]],
            "needed": [r["service_name"] for r in a if r["status"] == "needed"]}
