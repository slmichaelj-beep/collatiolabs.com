"""commercial.proof — proof / demo builder (prepared, never fabricated).

Assembles the proof package a buyer needs: what's actually demoable today, what evidence exists
(cert reports, screenshots, metrics), and — honestly — what is NOT yet provable. No testimonials,
case studies, or metrics are ever invented; gaps are surfaced as gaps.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage
from . import ip_license

KINDS = ("live_demo", "recorded_demo", "cert_report", "screenshot", "metric", "reference")


def build(name: str, asset_id: str, *, proofs: list | None = None, store: Path | None = None) -> dict:
    """proofs: [{kind, claim, evidence_ref}]. A proof with no evidence_ref is recorded as a GAP,
    never as proof. Demo is blocked if the asset isn't sell-gate clear (e.g. embedded secrets)."""
    proofs = proofs or []
    gate = ip_license.can_sell(name, asset_id, store=store)
    real, gaps = [], []
    for p in proofs:
        kind = p.get("kind")
        ev = (p.get("evidence_ref") or "").strip()
        item = {"kind": kind if kind in KINDS else "unknown", "claim": p.get("claim", ""),
                "evidence_ref": ev}
        (real if ev else gaps).append(item)
    demo_blocked = not gate["allowed"]
    rec = {
        "proof_id": "pf_" + uuid.uuid4().hex[:10], "asset_id": asset_id,
        "verified_proofs": real, "gaps": gaps,
        "demo_allowed": not demo_blocked,
        "demo_blocked_reason": ("; ".join(gate["blockers"]) if demo_blocked else None),
        "honest_note": ("%d verified proof(s); %d gap(s) with no evidence yet — gaps are NOT claimed"
                        % (len(real), len(gaps))),
        "no_fabrication": "no testimonials, case studies, or metrics are invented",
        "created_at": storage.now(),
    }
    storage.save(name, "proof_%s" % asset_id, rec, store)
    storage.emit_truth(name, "proof", rec["proof_id"],
                       "PROOF package: %d verified, %d gaps%s"
                       % (len(real), len(gaps), " (demo blocked)" if demo_blocked else ""),
                       actor="vera", store=store)
    return rec
