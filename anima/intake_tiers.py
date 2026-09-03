"""intake_tiers — Intake Wave 4, item O: HOT / WARM / COLD storage tiers for the knowledge base.

As the Reference Library grows, not every source deserves the same residency. This module tiers
stored references by how live they are:

  * HOT   — recently stored OR recently cited: kept verbatim, instantly retrievable.
  * WARM  — middle-aged, uncited: kept verbatim, a demotion candidate.
  * COLD  — old AND never cited: its text is gzip-compressed into a cold blob.

THE LAW (001 — Compressed > Forgotten): COLD never DELETES. It COMPRESSES, and the bytes round-trip
EXACTLY (restore_cold returns byte-identical chunks). A cold item is still the Mind's — just denser.
This is intelligence-per-GB at the storage layer: keep the live knowledge hot, store the dormant
knowledge compactly, lose nothing. `savings()` reports the real bytes reclaimed by compression.

SAFE BY CONSTRUCTION. The tier layer is ADDITIVE: it maintains its OWN append-only tier ledger and
cold-blob store under intake.STORE; it READS references read-only and never mutates a reference
record or any cognitive store. Tiering is a storage decision, not a learning one — it cannot change
what Vera knows, only how densely a dormant source is held. `now_ts` and `cited_ids` are injected so
the policy is deterministic and testable; an unparseable age stays HOT (never cold by accident).
"""
from __future__ import annotations

import gzip
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from . import secure_store
from . import intake as I
from . import intake_queue as Q

HOT = "hot"
WARM = "warm"
COLD = "cold"
TIERS = (HOT, WARM, COLD)

# Default policy thresholds (days). Tunable per call.
HOT_DAYS = 14
WARM_DAYS = 90


def _now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_ts(s: str) -> Optional[datetime]:
    if not s or not isinstance(s, str):
        return None
    t = s.strip().replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(t)
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _age_days(stored_at: str, now_ts: str) -> Optional[float]:
    a, b = _parse_ts(stored_at), _parse_ts(now_ts)
    if a is None or b is None:
        return None
    return (b - a).total_seconds() / 86400.0


def recommend(item: dict, *, now_ts: str, cited_ids: Iterable[str] = (),
              hot_days: int = HOT_DAYS, warm_days: int = WARM_DAYS) -> str:
    """The tier this reference SHOULD sit in. A cited source is always HOT (live knowledge); else age
    decides. An unknown/unparseable age stays HOT — we never cold-archive something we can't age."""
    if item.get("id") in set(cited_ids or ()):
        return HOT
    age = _age_days(item.get("stored_at", ""), now_ts)
    if age is None:
        return HOT
    if age <= hot_days:
        return HOT
    if age <= warm_days:
        return WARM
    return COLD


def _item_payload(item: dict) -> bytes:
    """The canonical bytes a cold blob holds — the source's chunks (the retrievable knowledge),
    serialised deterministically so the round-trip is byte-exact."""
    return json.dumps(item.get("chunks", []), ensure_ascii=False,
                      sort_keys=True, separators=(",", ":")).encode("utf-8")


def _cold_dir(name: str) -> Path:
    return I.STORE / f"{name}.cold"


def _cold_path(name: str, source_id: str) -> Path:
    safe = "".join(c if (c.isalnum() or c in "._-") else "_" for c in str(source_id))[:128]
    return _cold_dir(name) / f"{safe}.json.gz"


def _ledger_path(name: str) -> Path:
    return I.STORE / f"{name}.tiers.jsonl"


def _append(name: str, event: dict) -> dict:
    p = _ledger_path(name)
    secure_store.append_jsonl(p, event)
    return event


def tier_events(name: str) -> list:
    p = _ledger_path(name)
    if not p.exists():
        return []
    out = []
    for line in secure_store.read_jsonl_lines(p):
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def tier_of(name: str, source_id: str) -> Optional[str]:
    """The CURRENT tier of a source (latest ledger event), or None if never tiered."""
    cur = None
    for ev in tier_events(name):
        if ev.get("source_id") == source_id and ev.get("tier") in TIERS:
            cur = ev["tier"]
    return cur


def archive_cold(name: str, item: dict, *, at: Optional[str] = None) -> dict:
    """Compress a reference's chunks into a cold blob and record the move. Returns the tier event
    with raw_bytes / stored_bytes / saved_bytes. LAW 001: this WRITES the compressed copy; the
    bytes are recoverable byte-exact via restore_cold. Never deletes anything."""
    sid = item.get("id")
    raw = _item_payload(item)
    blob = gzip.compress(raw, compresslevel=9)
    path = _cold_path(name, sid)
    secure_store.save_bytes(path, blob)
    return _append(name, {"source_id": sid, "tier": COLD, "at": at or _now_ts(),
                          "raw_bytes": len(raw), "stored_bytes": len(blob),
                          "saved_bytes": max(0, len(raw) - len(blob)),
                          "blob": str(path.name)})


def restore_cold(name: str, source_id: str) -> Optional[list]:
    """Decompress a cold source's chunks — byte-EXACT round-trip (Compressed > Forgotten). Returns
    the chunk list, or None if there is no cold blob for this source."""
    path = _cold_path(name, source_id)
    if not path.exists():
        return None
    try:
        raw = gzip.decompress(secure_store.load_bytes(path, b"") or b"")
        return json.loads(raw.decode("utf-8"))
    except Exception:
        return None


def plan(name: str = "Vera", *, now_ts: Optional[str] = None, cited_ids: Iterable[str] = (),
         hot_days: int = HOT_DAYS, warm_days: int = WARM_DAYS) -> list:
    """A READ-ONLY tiering plan over the live Reference Library: one row per source with its
    recommended tier, age, citation status, and byte size. Moves nothing."""
    now_ts = now_ts or _now_ts()
    cited = set(cited_ids or ())
    rows = []
    for item in Q.references(name):
        sid = item.get("id")
        tier = recommend(item, now_ts=now_ts, cited_ids=cited, hot_days=hot_days, warm_days=warm_days)
        rows.append({"source_id": sid, "title": item.get("title", ""), "tier": tier,
                     "age_days": _age_days(item.get("stored_at", ""), now_ts),
                     "cited": sid in cited, "bytes": len(_item_payload(item))})
    return rows


def apply(name: str = "Vera", *, now_ts: Optional[str] = None, cited_ids: Iterable[str] = (),
          hot_days: int = HOT_DAYS, warm_days: int = WARM_DAYS) -> dict:
    """Run the plan and ARCHIVE every COLD source (real gzip), recording each move in the tier
    ledger. ADDITIVE + reversible: the reference records are untouched; the cold blobs are the
    compact canonical copy + are restorable byte-exact. Returns a receipt with per-tier counts and
    the real bytes saved by compression."""
    now_ts = now_ts or _now_ts()
    rows = plan(name, now_ts=now_ts, cited_ids=cited_ids, hot_days=hot_days, warm_days=warm_days)
    by_id = {it.get("id"): it for it in Q.references(name)}
    counts = {HOT: 0, WARM: 0, COLD: 0}
    saved = 0
    cold_ids = []
    for row in rows:
        counts[row["tier"]] = counts.get(row["tier"], 0) + 1
        if row["tier"] == COLD:
            ev = archive_cold(name, by_id[row["source_id"]], at=now_ts)
            saved += ev["saved_bytes"]
            cold_ids.append(row["source_id"])
        elif row["tier"] in (HOT, WARM):
            # record the (non-destructive) residency decision too, so the ledger is complete.
            _append(name, {"source_id": row["source_id"], "tier": row["tier"], "at": now_ts})
    return {"ok": True, "name": name, "counts": counts, "cold_ids": cold_ids,
            "bytes_saved": saved, "n": len(rows)}


def savings(name: str = "Vera") -> dict:
    """The storage win: total raw vs stored bytes for every COLD source (latest event per source),
    and the compression ratio. The intelligence-per-GB number at the storage layer."""
    latest = {}
    for ev in tier_events(name):
        if ev.get("tier") == COLD and "raw_bytes" in ev:
            latest[ev.get("source_id")] = ev
    raw = sum(e["raw_bytes"] for e in latest.values())
    stored = sum(e["stored_bytes"] for e in latest.values())
    return {"cold_sources": len(latest), "raw_bytes": raw, "stored_bytes": stored,
            "saved_bytes": max(0, raw - stored),
            "ratio": (raw / stored) if stored else 1.0}


def _selftest() -> int:
    """Hermetic: a temp intake.STORE holds the reference library + tier ledger + cold blobs. Proves
    the policy (hot/warm/cold by age + citation), real gzip compression, byte-EXACT restore (nothing
    lost), additive safety (references untouched), and the savings metric. Real .anima byte-unchanged
    is asserted by the gate's cert."""
    import tempfile
    import hashlib
    import shutil

    fails = []

    def ok(label, cond):
        print(("  ok   " if cond else "  FAIL ") + label)
        if not cond:
            fails.append(label)

    def _fp(root: Path):
        if not root.is_dir():
            return (None, 0)
        files = sorted(q for q in root.rglob("*") if q.is_file())
        h = hashlib.sha256()
        for q in files:
            h.update(str(q.relative_to(root)).encode())
            try:
                h.update(q.read_bytes())
            except OSError:
                h.update(b"?")
        return (h.hexdigest(), len(files))

    real = Path(".anima")
    fp_before = _fp(real)
    saved_store = I.STORE
    tmp = Path(tempfile.mkdtemp(prefix="tiers_cert_"))
    try:
        I.STORE = tmp
        name = "TierCert"
        NOW = "2026-06-07T00:00:00Z"

        # three references of different ages; a long repetitive body so gzip clearly wins.
        body = ("Compound interest is interest on principal plus accumulated interest. " * 60)
        Q.add_reference(name, source_id="fresh", title="Fresh note",
                        provenance={"rights_category": "owned"},
                        chunks=[{"text": body}], safety={})
        Q.add_reference(name, source_id="mid", title="Mid note",
                        provenance={}, chunks=[{"text": body}], safety={})
        Q.add_reference(name, source_id="old", title="Old note",
                        provenance={}, chunks=[{"text": body}], safety={})
        # backdate stored_at directly in the reference store (the only thing the cert mutates).
        from .util import load_json, save_json
        disk = load_json(Q._reference_path(name))
        for it in disk["items"]:
            it["stored_at"] = {"fresh": "2026-06-01T00:00:00Z",   # 6 days -> HOT
                               "mid": "2026-04-01T00:00:00Z",      # ~67 days -> WARM
                               "old": "2025-01-01T00:00:00Z"}[it["id"]]  # >1y -> COLD
        save_json(Q._reference_path(name), disk)

        rows = {r["source_id"]: r["tier"] for r in plan(name, now_ts=NOW)}
        ok("policy: a fresh source is HOT", rows["fresh"] == HOT)
        ok("policy: a mid-age uncited source is WARM", rows["mid"] == WARM)
        ok("policy: an old uncited source is COLD", rows["old"] == COLD)

        # citation overrides age: cite the OLD one -> it must stay HOT (live knowledge)
        rows_cited = {r["source_id"]: r["tier"] for r in plan(name, now_ts=NOW, cited_ids=["old"])}
        ok("policy: a CITED old source is kept HOT (citation overrides age)",
           rows_cited["old"] == HOT)

        rec = apply(name, now_ts=NOW)
        ok("apply: tiers the library (1 hot, 1 warm, 1 cold)",
           rec["counts"] == {HOT: 1, WARM: 1, COLD: 1})
        ok("apply: COLD compression actually saved bytes (raw > stored)", rec["bytes_saved"] > 0)
        ok("apply: the cold source's current tier is recorded as COLD", tier_of(name, "old") == COLD)

        # LAW 001 — the cold round-trip is byte-EXACT (nothing lost)
        restored = restore_cold(name, "old")
        original = next(it for it in Q.references(name) if it["id"] == "old")["chunks"]
        ok("LAW 001: restore_cold round-trips the chunks BYTE-EXACT (Compressed > Forgotten)",
           restored is not None
           and json.dumps(restored, sort_keys=True) == json.dumps(original, sort_keys=True))

        sv = savings(name)
        ok("savings: reports a real compression ratio > 1 (intelligence-per-GB at storage)",
           sv["cold_sources"] == 1 and sv["ratio"] > 1.0 and sv["saved_bytes"] > 0)

        # additive safety: the reference records are untouched (still 3, still full text)
        refs = Q.references(name)
        ok("additive safety: references are UNTOUCHED by tiering (still all present, full text)",
           len(refs) == 3 and all(r["chunks"][0]["text"] == body for r in refs))
    finally:
        I.STORE = saved_store
        shutil.rmtree(tmp, ignore_errors=True)

    fp_after = _fp(real)
    ok("real .anima byte-UNCHANGED around the tiers selftest", fp_before == fp_after)

    print("\nINTAKE-TIERS: " + ("ALL PASS" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        raise SystemExit(_selftest())
    print("intake_tiers — hot/warm/cold storage tiers. Use --selftest, or import plan/apply/savings.")
