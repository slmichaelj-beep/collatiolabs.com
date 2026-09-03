"""knowledge_packs.registry — the persisted pack registry + lifecycle enforcement.

.anima/<name>.packs.json holds the registry; pack CONTENT lives in
.anima/<name>.packs/<pack_id>/ (chunks.jsonl after indexing). Lifecycle transitions are
validated against schema.TRANSITIONS — a pack can never skip quarantine or become ready
without evaluation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from anima import secure_store

from . import schema


def default_store() -> Path:
    return Path(os.environ.get("ANIMA_STORE", ".anima"))


def reg_path(name: str, store: Path | None = None) -> Path:
    return (store or default_store()) / f"{name}.packs.json"


def content_dir(name: str, pack_id: str, store: Path | None = None) -> Path:
    return (store or default_store()) / f"{name}.packs" / pack_id


def load(name: str, store: Path | None = None) -> list[dict]:
    data = secure_store.load_json(reg_path(name, store), {}) or {}
    return data.get("packs", []) if isinstance(data, dict) else []


def _save(name: str, packs: list[dict], store: Path | None = None) -> None:
    p = reg_path(name, store)
    secure_store.save_json(p, {"version": 1, "packs": packs})


def add(name: str, pack: dict, store: Path | None = None) -> dict:
    problems = schema.validate(pack)
    if problems:
        raise ValueError("refusing invalid pack: " + "; ".join(problems))
    packs = load(name, store)
    packs.append(pack)
    _save(name, packs, store)
    # a new pack is QUARANTINED immediately — its content is untrusted data
    return transition(name, pack["pack_id"], "quarantined", by="system", store=store)


def get(name: str, pack_id: str, store: Path | None = None) -> dict | None:
    for p in load(name, store):
        if p.get("pack_id") == pack_id:
            return p
    return None


def transition(name: str, pack_id: str, to: str, *, by: str = "user",
               store: Path | None = None, patch: dict | None = None) -> dict:
    packs = load(name, store)
    for p in packs:
        if p.get("pack_id") == pack_id:
            cur = p.get("lifecycle_status")
            if to not in schema.TRANSITIONS.get(cur, ()):
                raise ValueError("illegal lifecycle transition %s -> %s (legal: %s)"
                                 % (cur, to, list(schema.TRANSITIONS.get(cur, ()))))
            p["lifecycle_status"] = to
            if patch:
                p.update(patch)
            p.setdefault("transitions", []).append({"at": schema.now(), "to": to, "by": by})
            _save(name, packs, store)
            return p
    raise KeyError("no such pack %r" % pack_id)


def ready_packs(name: str, store: Path | None = None) -> list[dict]:
    return [p for p in load(name, store) if p.get("lifecycle_status") == "ready"]
