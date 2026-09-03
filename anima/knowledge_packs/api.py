"""knowledge_packs.api — the server surface.

GET  /packs                 -> {ok, packs}
POST /packs/add             -> {ok, pack} (lands QUARANTINED)
POST /packs/build           -> index + evaluate (host-profile-bounded)
POST /packs/lifecycle       -> {pack_id, to} guarded transition (promote/disable/remove/…)
POST /packs/retrieve        -> ready-pack retrieval (cited, flagged, ledger-traced)
POST /packs/import          -> Teaching-Mode draft from pack content (never direct persistence)
"""
from __future__ import annotations

from . import builder, registry, retrieval, schema


def serve_list(name: str) -> dict:
    return {"ok": True, "packs": registry.load(name)}


def serve_add(name: str, data: dict) -> dict:
    try:
        pack = schema.make(str(data.get("name") or ""), str(data.get("domain") or ""),
                           owner=str(data.get("owner") or "user"),
                           sources=list(data.get("sources") or []))
        return {"ok": True, "pack": registry.add(name, pack)}
    except ValueError as e:
        return {"ok": False, "error": str(e)}


def serve_build(name: str, data: dict) -> dict:
    pid = str(data.get("pack_id") or "")
    texts = list(data.get("source_texts") or [])
    out = builder.index(name, pid, texts, size_mb=float(data.get("size_mb") or 0))
    if not out.get("ok"):
        return out
    return builder.evaluate(name, pid)


def serve_lifecycle(name: str, data: dict) -> dict:
    pid = str(data.get("pack_id") or "")
    to = str(data.get("to") or "")
    if to == "ready":
        return builder.promote(name, pid)
    try:
        return {"ok": True, "pack": registry.transition(name, pid, to)}
    except (ValueError, KeyError) as e:
        return {"ok": False, "error": str(e)}


def serve_retrieve(name: str, data: dict) -> dict:
    return retrieval.retrieve(name, str(data.get("q") or ""),
                              top_k=int(data.get("top_k") or 4),
                              turn_id=str(data.get("turn_id") or ""))


def serve_import(name: str, data: dict) -> dict:
    return retrieval.import_to_behavior(name, str(data.get("pack_id") or ""),
                                        str(data.get("content") or ""))
