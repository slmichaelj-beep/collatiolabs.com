"""commercial.landing — landing-page DRAFT builder (prepared, never published).

Generates an honest landing-page draft (headline, subhead, value bullets, proof section, CTA) from
the offer + verified proof. The draft is stored and previewable; PUBLISHING is a human action
(external/public content) and is never performed here. Claims are pulled only from verified proof —
unproven benefits are omitted, not asserted.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from anima.company import storage


def draft(name: str, asset_id: str, *, headline: str, subhead: str, value_bullets: list | None = None,
          verified_claims: list | None = None, cta_text: str = "Request a demo",
          store: Path | None = None) -> dict:
    """Build a landing-page draft. verified_claims should come from proof.build's verified_proofs."""
    value_bullets = value_bullets or []
    verified_claims = verified_claims or []
    rec = {
        "landing_id": "ld_" + uuid.uuid4().hex[:10], "asset_id": asset_id,
        "headline": headline, "subhead": subhead,
        "value_bullets": value_bullets,
        "proof_section": verified_claims,           # only verified claims appear publicly
        "cta": {"text": cta_text, "action": "human-handled (no auto form / no auto-send)"},
        "status": "draft",
        "publish_status": "NOT published — publishing is a human action (public content)",
        "honest_note": "only verified claims are shown; unproven benefits are omitted",
        "created_at": storage.now(),
    }
    storage.save(name, "landing_%s" % asset_id, rec, store)
    storage.emit_truth(name, "landing", rec["landing_id"],
                       "LANDING draft prepared (not published): %s" % headline,
                       actor="vera", store=store)
    return rec


def render_html(rec: dict) -> str:
    """Render the draft to a self-contained preview HTML string (for human review, not deploy)."""
    import html as _h
    b = "".join("<li>%s</li>" % _h.escape(str(x)) for x in rec.get("value_bullets", []))
    pf = "".join("<li>%s</li>" % _h.escape(str(p.get("claim", p)))
                 for p in rec.get("proof_section", [])) or "<li><em>no verified proof yet</em></li>"
    return ("<!doctype html><meta charset=utf-8><title>%s</title>"
            "<h1>%s</h1><p>%s</p><ul>%s</ul><h3>Proof</h3><ul>%s</ul>"
            "<button>%s</button><p><small>DRAFT — not published</small></p>"
            % (_h.escape(rec.get("headline", "")), _h.escape(rec.get("headline", "")),
               _h.escape(rec.get("subhead", "")), b, pf,
               _h.escape(rec.get("cta", {}).get("text", "Contact"))))
