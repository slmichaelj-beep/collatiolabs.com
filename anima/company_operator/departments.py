"""company_operator.departments — governed department operator role modules.

Department operators are NOT uncontrolled agents. Each is a role with allowed / approval-required /
forbidden action sets; any action it proposes runs through the same authority + approval + budget +
action ledger as everything else. They report up to the founder briefing.
"""
from __future__ import annotations

from pathlib import Path

from anima.company import storage
from . import authority

DEPARTMENTS = {
    "product": {"allowed": ["draft", "plan"], "approval": ["publish"], "forbidden": ["spend", "bank_transfer"]},
    "engineering": {"allowed": ["draft", "plan", "create_document"], "approval": ["publish"],
                    "forbidden": ["bank_transfer", "sign_contract"]},
    "marketing": {"allowed": ["draft", "plan"], "approval": ["publish", "send_message", "spend"],
                  "forbidden": ["bank_transfer"]},
    "sales": {"allowed": ["draft", "plan"], "approval": ["send_message", "vendor_contact"],
              "forbidden": ["sign_contract", "bank_transfer"]},
    "support": {"allowed": ["draft", "plan"], "approval": ["support_reply", "send_message"],
                "forbidden": ["bank_transfer"]},
    "finance_ops": {"allowed": ["draft", "plan"], "approval": ["spend"],
                    "forbidden": ["bank_transfer", "tax_filing", "payroll"]},
    "legal_coordination": {"allowed": ["draft", "plan"], "approval": [],
                           "forbidden": ["sign_contract", "patent_filing", "tax_filing", "legal_representation"]},
    "operations": {"allowed": ["draft", "plan", "create_document"], "approval": ["vendor_contact"],
                   "forbidden": ["bank_transfer"]},
    "growth": {"allowed": ["draft", "plan"], "approval": ["publish", "spend"], "forbidden": ["bank_transfer"]},
    "strategy": {"allowed": ["draft", "plan"], "approval": [], "forbidden": []},
}


def spin_up(name: str, dept: str, mission: str, *, store: Path | None = None) -> dict:
    if dept not in DEPARTMENTS:
        return {"ok": False, "error": "unknown department %r" % dept}
    spec = DEPARTMENTS[dept]
    rec = {"department_id": "dep_" + dept, "name": dept, "mission": mission,
           "allowed_actions": spec["allowed"], "approval_required_actions": spec["approval"],
           "forbidden_actions": spec["forbidden"], "reports_to": "Vera CEO Operator",
           "active_projects": [], "kpis": [], "risks": [], "created_at": storage.now()}
    deps = storage.load(name, "departments", store, default={"departments": []})["departments"]
    deps = [d for d in deps if d["name"] != dept] + [rec]
    storage.save(name, "departments", {"departments": deps}, store)
    return {"ok": True, "department": rec}


def can_act(name: str, dept: str, action_type: str, *, store: Path | None = None) -> dict:
    """A department's action verdict: forbidden -> no; approval-required -> queue; allowed ->
    still subject to the global authority ladder."""
    spec = DEPARTMENTS.get(dept)
    if spec is None:
        return {"allowed": False, "reason": "unknown department"}
    if action_type in spec["forbidden"]:
        return {"allowed": False, "reason": "%s is forbidden for the %s operator" % (action_type, dept)}
    if action_type in spec["approval"]:
        return {"allowed": False, "needs_approval": True,
                "reason": "%s requires an approval packet for the %s operator" % (action_type, dept)}
    if action_type in spec["allowed"]:
        # still gated by the global authority ladder (draft/plan are L0-safe)
        perm = authority.permits(name, action_type, store=store)
        return {"allowed": perm["permitted"], "reason": perm["reason"]}
    return {"allowed": False, "reason": "%s is not in the %s operator's action set" % (action_type, dept)}
