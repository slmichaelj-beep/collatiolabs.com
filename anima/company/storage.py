"""company.storage — shared atomic JSON store + Truth Ledger link for the company layer.

Every durable company record (canon, decision, doctrine, risk, …) is persisted atomically under
.anima/<name>.company/<kind>.json and, when it becomes durable (approved), emits a Truth Ledger
event so the company claim is traceable like every other claim. Company claims ride the core
ledger as claim_type="system" with a "company:<kind>" subject prefix — zero changes to the core
truth schema, full traceability.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path


STORE = Path(".anima")  # redirectable by hermetic certs (see truth.ledger)


def default_store() -> Path:
    env = os.environ.get("ANIMA_STORE")
    return Path(env) if env else STORE


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def company_dir(name: str, store: Path | None = None) -> Path:
    return (store or default_store()) / f"{name}.company"


def load(name: str, kind: str, store: Path | None = None, default=None):
    p = company_dir(name, store) / f"{kind}.json"
    try:
        return json.loads(p.read_text())
    except Exception:
        return default if default is not None else {}


def save(name: str, kind: str, data, store: Path | None = None) -> None:
    d = company_dir(name, store)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{kind}.json"
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    tmp.replace(p)


def emit_truth(name: str, kind: str, subject: str, claim: str, *, evidence_refs=None,
               provenance_kind: str = "system_cert", provenance_refs=None, actor: str = "system",
               risk: str = "low", active_status: str = "active", supersedes=None,
               store: Path | None = None) -> str | None:
    """Emit a company claim into the core Truth Ledger (claim_type=system, subject
    'company:<kind>:<subject>'). Returns the event id, or None (guarded)."""
    try:
        from anima.truth import ledger as tl, schema as ts
        ev = ts.make("company:%s:%s" % (kind, subject), claim, "system",
                     provenance_kind=provenance_kind, provenance_refs=provenance_refs or [],
                     evidence_refs=evidence_refs or [], scope="system", confidence=1.0,
                     supersedes=supersedes or [], actor=actor, risk=risk,
                     active_status=active_status)
        tl.emit(name, ev, store=store)
        return ev["event_id"]
    except Exception:
        return None
