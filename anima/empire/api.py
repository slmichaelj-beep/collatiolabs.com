"""empire.api — assemble the /empire dashboard payload (read-only)."""
from __future__ import annotations

from pathlib import Path

from anima.company import storage
from . import registry as _r


def dashboard(name: str, store: Path | None = None) -> dict:
    hosts = _r.hosts(name, store)
    caps = storage.load(name, "emp_capital_index", store, default={"ids": []})["ids"]
    return {
        "ok": True,
        "hosts": [{"name": h["name"], "role": h["role"], "security": h["security_status"],
                   "data_scope": h["data_access_scope"], "status": h["status"]} for h in hosts],
        "certified_hosts": sum(1 for h in hosts if h["security_status"] == "certified"),
        "capital_decisions": len(caps),
        "next_move": ("register + certify hosts before routing sensitive work" if not hosts else
                      "route paid work to certified hosts; allocate capital to evidence-backed winners"),
        "honesty": "no uncertified host gets sensitive data; cloud routing of private data needs "
                   "approval; no capital spend without approval; reserve protected; paid work outranks "
                   "speculation but security/legal emergencies outrank revenue.",
    }
