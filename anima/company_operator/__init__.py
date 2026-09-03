"""anima.company_operator — governed AI Founder-Operator.

Governed autonomy, never uncontrolled. The governance core (authority ladder, approval queue,
budget ledger, action ledger, kill switch) gates every external action: nothing fires without the
right authority level + (when required) an approved packet + budget, and the kill switch stops
everything instantly. Default authority is L0 (think-only). v1 wires NO real external
integrations — Vera prepares and queues; humans execute regulated/financial/account actions.
"""
from . import (accounts, action_ledger, approvals, authority, budget, departments,  # noqa: F401
               kill_switch, legal_ip, planning)
