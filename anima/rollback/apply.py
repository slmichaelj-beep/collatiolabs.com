"""rollback.apply — perform a rollback on any reversible surface, record it, ledger it.

Each kind delegates to the surface that owns the undo (teaching.rollback for teaching/auto-learn
drafts; truth.supersession for memory; registry transitions for packs; host.profile for the
profile override; claim_registry rebuild for tier classification), then writes the canonical
rollback record (.anima/<name>.rollbacks.jsonl) and emits a Truth Ledger event.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from . import schema


def _store(store: Path | None) -> Path:
    return store or Path(os.environ.get("ANIMA_STORE", ".anima"))


def _log(name: str, rec: dict, store: Path | None) -> None:
    p = _store(store) / f"{name}.rollbacks.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _truth(name: str, kind: str, target_id: str, reason: str, supersede: str | None,
           store: Path | None) -> str | None:
    try:
        from anima.truth import ledger as tl, schema as ts
        ev = ts.make("rollback:%s" % kind, "ROLLED BACK %s %s (%s)" % (kind, target_id, reason),
                     "correction", provenance_kind="system_cert", provenance_refs=[target_id],
                     supersedes=[supersede] if supersede else [], scope="system",
                     confidence=1.0, actor="user", active_status="retracted")
        tl.emit(name, ev, store=store)
        return ev["event_id"]
    except Exception:
        return None


def rollback(name: str, target_kind: str, target_id: str, *, reason: str = "user requested",
             actor: str = "user", store: Path | None = None,
             target_event: str | None = None, **kw) -> dict:
    """Dispatch a rollback by kind. Returns {ok, record|error}."""
    if target_kind not in schema.TARGET_KINDS:
        return {"ok": False, "error": "unknown target_kind %r" % target_kind}

    prev, new, undone = None, None, ""

    if target_kind in ("teaching_record", "auto_learn_conversion"):
        from anima.teaching import rollback as trb, queue as tq
        rec = tq.get(name, target_id, store)
        prev = rec.get("approval_state") if rec else None
        out = trb.rollback(name, target_id, reason=reason, by=actor, store=store)
        if not out["ok"]:
            return out
        new, undone = "rolled_back", out["rollback"]["undone"]
        target_event = target_event or out["rollback"].get("target_event")

    elif target_kind in ("memory_correction", "forget_retraction"):
        from anima.truth import query as tq, supersession as sup
        ev = tq.by_id(name, target_id, store)
        if ev is None:
            return {"ok": False, "error": "no such truth event"}
        prev = ev.get("active_status")
        sup.retract(name, [target_id], ev.get("subject", "?"),
                    reason="rollback: " + reason, actor=actor, store=store)
        new, undone = "retracted", "memory event %s retracted" % target_id

    elif target_kind == "knowledge_pack":
        from anima.knowledge_packs import registry as kr
        pack = kr.get(name, target_id, store)
        if pack is None:
            return {"ok": False, "error": "no such pack"}
        prev = pack.get("lifecycle_status")
        try:
            kr.transition(name, target_id, "disabled", by=actor, store=store)
            new, undone = "disabled", "pack disabled (no longer retrievable)"
        except ValueError as e:
            return {"ok": False, "error": str(e)}

    elif target_kind == "runtime_profile_override":
        from anima.host import profile as hp
        c = hp.current()
        prev = c.get("selected_profile")
        c2 = hp.build_contract(override_profile=c.get("recommended_profile"),
                               override_by="rollback:%s" % actor)
        new, undone = c2["selected_profile"], "profile restored to recommended (%s)" % new if False else \
            ("profile restored to recommended (%s)" % c2["selected_profile"])
        new = c2["selected_profile"]

    elif target_kind == "release_tier_classification":
        from anima.verification import claim_registry as crg
        prev = (crg.load().get("features") or {}).get(target_id, {}).get("status")
        reg = crg.build()
        new = (reg.get("features") or {}).get(target_id, {}).get("status")
        undone = "claim registry rebuilt from ground truth"

    ev_id = _truth(name, target_kind, target_id, reason, target_event, store)
    rec = schema.make(target_kind, target_id=target_id, previous_state=prev, new_state=new,
                      reason=reason, actor=actor, target_event=target_event,
                      truth_ledger_event=ev_id)
    rec["undone"] = undone
    _log(name, rec, store)
    return {"ok": True, "record": rec}


def history(name: str, store: Path | None = None) -> list[dict]:
    p = _store(store) / f"{name}.rollbacks.jsonl"
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]
