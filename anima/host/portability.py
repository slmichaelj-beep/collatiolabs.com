"""host.portability — Vera moves between Macs safely.

A host registry tracks every machine Vera has run on (by host_id). On a new host, reports/certs
from another host are flagged stale, the wrong-host profile cannot claim green, and an .anima
migration requires explicit confirmation. Old-host reports stay visible but never current.
"""
from __future__ import annotations

from pathlib import Path

from anima.company import storage  # reuse the atomic store helper

ROLES = ("primary_daily", "performance_dev", "portable_backup", "unknown")


def _registry(name, store): return storage.load(name, "host_registry", store, default={"hosts": []})["hosts"]
def _save(name, hosts, store): storage.save(name, "host_registry", {"hosts": hosts}, store)


def register_current(name: str, *, role: str = "unknown", store: Path | None = None) -> dict:
    from .profile import current
    from anima.verification.cert_result import host_id
    c = current()
    hid = host_id()
    hosts = _registry(name, store)
    rec = next((h for h in hosts if h["host_id"] == hid), None)
    now = storage.now()
    if rec is None:
        rec = {"host_id": hid, "hostname": c.get("hostname"), "chip": c.get("chip"),
               "memory_gb": c.get("memory_gb"), "profile": c.get("selected_profile"),
               "role": role if role in ROLES else "unknown", "first_seen": now, "last_seen": now}
        hosts.append(rec)
    else:
        rec["last_seen"] = now
        rec["profile"] = c.get("selected_profile")
    _save(name, hosts, store)
    return rec


def is_report_from_this_host(report_host_id: str | None) -> bool:
    from anima.verification.cert_result import host_id
    return bool(report_host_id) and report_host_id == host_id()


def cross_host_warnings(name: str, store: Path | None = None) -> list[str]:
    """Host-specific cert results recorded on a DIFFERENT host than this one — visible, not current."""
    from anima.verification.cert_result import host_id, load_all
    me = host_id()
    out = []
    for cert, rec in (load_all() or {}).items():
        h = (rec or {}).get("host_id")
        if h and h not in ("any", me):
            out.append("%s ran on host %s (this is %s) — not current here" % (cert, h, me))
    return out


def migration_requires_confirmation() -> dict:
    """.anima migration is never automatic."""
    return {"automatic": False,
            "reason": ".anima carries the creature's life — migrating it onto a new host requires "
                      "explicit owner confirmation + a fresh host-specific cert run"}
