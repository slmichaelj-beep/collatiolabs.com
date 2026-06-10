"""knowledge_packs.builder — index + evaluate a pack (host-profile-bounded).

index(): chunks the pack's source texts into <pack content dir>/chunks.jsonl (quarantined ->
indexed). evaluate(): runs the quarantine scan over every chunk and records the verdict
(indexed -> evaluated); promote() moves evaluated -> ready. Builds respect the host runtime
contract (allow_pack_build) — a Portable host defers builds, honestly.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import quarantine, registry, schema


def _chunk(text: str, size: int = 900) -> list[str]:
    out, cur = [], []
    n = 0
    for para in (text or "").split("\n\n"):
        cur.append(para)
        n += len(para)
        if n >= size:
            out.append("\n\n".join(cur))
            cur, n = [], 0
    if cur:
        out.append("\n\n".join(cur))
    return [c for c in out if c.strip()]


def index(name: str, pack_id: str, source_texts: list[dict], *, store: Path | None = None,
          size_mb: float = 0.0) -> dict:
    """source_texts: [{title, text, ref}] — chunked + persisted; quarantined -> indexed."""
    try:
        from anima.host import enforcement as henf
        v = henf.allow_heavy_job("pack_build", size_mb)
        if not v["allowed"]:
            return {"ok": False, "deferred": True, "error": v["reason"]}
    except ImportError:
        pass
    pack = registry.get(name, pack_id, store)
    if pack is None:
        return {"ok": False, "error": "no such pack"}
    if pack["lifecycle_status"] not in ("quarantined", "stale", "disabled"):
        return {"ok": False, "error": "pack is %s — only quarantined/stale/disabled can be "
                                      "(re)indexed" % pack["lifecycle_status"]}
    d = registry.content_dir(name, pack_id, store)
    d.mkdir(parents=True, exist_ok=True)
    chunks = []
    for src in source_texts:
        for c in _chunk(str(src.get("text") or "")):
            chunks.append({"text": c, "title": src.get("title") or "untitled",
                           "ref": src.get("ref") or src.get("title") or "untitled"})
    (d / "chunks.jsonl").write_text(
        "\n".join(json.dumps(c, ensure_ascii=False) for c in chunks) + "\n")
    registry.transition(name, pack_id, "indexed", by="builder", store=store,
                        patch={"last_indexed_at": schema.now()})
    return {"ok": True, "chunks": len(chunks)}


def load_chunks(name: str, pack_id: str, store: Path | None = None) -> list[dict]:
    f = registry.content_dir(name, pack_id, store) / "chunks.jsonl"
    if not f.exists():
        return []
    return [json.loads(ln) for ln in f.read_text().splitlines() if ln.strip()]


def evaluate(name: str, pack_id: str, store: Path | None = None) -> dict:
    pack = registry.get(name, pack_id, store)
    if pack is None:
        return {"ok": False, "error": "no such pack"}
    if pack["lifecycle_status"] != "indexed":
        return {"ok": False, "error": "pack is %s — only an indexed pack can be evaluated"
                                      % pack["lifecycle_status"]}
    verdict = quarantine.evaluate_chunks(load_chunks(name, pack_id, store))
    registry.transition(name, pack_id, "evaluated", by="builder", store=store,
                        patch={"prompt_injection_risk": verdict["prompt_injection_risk"],
                               "cert_status": "amber" if verdict["flagged"] else "green",
                               "_evaluation": verdict})
    return {"ok": True, **verdict}


def promote(name: str, pack_id: str, store: Path | None = None) -> dict:
    """evaluated -> ready. Refused for any pack that skipped evaluation (lifecycle-enforced)."""
    try:
        pack = registry.transition(name, pack_id, "ready", by="owner", store=store)
        return {"ok": True, "pack": pack}
    except (ValueError, KeyError) as e:
        return {"ok": False, "error": str(e)}
