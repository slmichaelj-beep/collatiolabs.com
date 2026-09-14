"""collatio.api — assemble the /collatio dashboard payload (read-only)."""
from __future__ import annotations

from pathlib import Path

from . import entity as _e, authority as _au, filings as _f, accounts as _ac, contracts as _c, ip_assets as _ip


def dashboard(name: str, store: Path | None = None) -> dict:
    p = _e.profile(name, store=store)
    return {
        "ok": True,
        "entity": {"legal_name": p["legal_name"], "status": p["status"],
                   "jurisdiction": p["jurisdiction"], "ein_status": p["ein_status"],
                   "default_operating_authority": p["default_operating_authority"]},
        "authority": _au.policy(name, store),
        "records": _e.records(name, store),
        "filings": _f.calendar(name, store),
        "accounts": _ac.registry(name, store),
        "contracts": _c.contracts(name, store),
        "ip_assets": _ip.assets(name, store),
        "honesty": "unknown entity facts stay unknown; legal/tax/contract/bank/account actions are "
                   "human-only and approval-gated; Vera prepares and queues.",
    }
