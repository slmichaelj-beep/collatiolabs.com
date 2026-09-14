"""foundry.knowledge_seed — seed the Business + Sales knowledge packs.

These are bounded, cited knowledge packs (built through the real knowledge_packs lifecycle:
added -> quarantined -> indexed -> evaluated -> ready). They are SOURCES, not authority — they
inform and cite; they cannot mutate memory/behavior/rules (the knowledge_packs boundaries already
prove that). Each pack carries a short curated summary + a source attribution; nothing here is a
hallucinated authority claim.
"""
from __future__ import annotations

from pathlib import Path

from anima.knowledge_packs import builder, registry, schema

# (name, domain, [ (chunk_title, chunk_text, source_ref) ... ]) — concise, cited, non-authoritative
BUSINESS_PACKS = [
    ("Capital Allocation", "business/capital", [
        ("Returns on capital", "Allocate capital to its highest risk-adjusted return; compare every "
         "venture against the others and against doing nothing.", "general finance principle")]),
    ("Lean Startup", "business/lean", [
        ("Validated learning", "Find the cheapest experiment that could falsify the riskiest "
         "assumption before building. Build-measure-learn.", "Lean Startup (Ries) — principle")]),
    ("Pricing", "business/pricing", [
        ("Value-based pricing", "Price to the value delivered and the buyer's willingness to pay, "
         "not to cost-plus. Anchor, then justify with proof.", "pricing strategy — principle")]),
    ("Competitive Strategy", "business/strategy", [
        ("Differentiation or cost", "Win by being meaningfully different or structurally lower cost; "
         "stuck-in-the-middle loses. Defensibility comes from a moat.", "Porter — principle")]),
    ("Operations", "business/ops", [
        ("Flow + quality", "Reduce variation and waste; build quality in rather than inspecting it "
         "after. Measure the system, not the people.", "Deming/Toyota — principle")]),
]
SALES_PACKS = [
    ("Consultative Selling", "sales/consultative", [
        ("Diagnose before prescribing", "Run discovery to confirm pain, budget, authority, and "
         "timeline before pitching. Sell the outcome, not features.", "consultative sales — principle")]),
    ("MEDDICC", "sales/meddicc", [
        ("Qualify rigorously", "Metrics, Economic buyer, Decision criteria, Decision process, "
         "Identify pain, Champion, Competition — qualify or disqualify honestly.", "MEDDICC — framework")]),
    ("Objection Handling", "sales/objections", [
        ("Surface the real objection", "Most stated objections (price) hide a real one (risk, "
         "trust, priority). Answer with evidence; disqualify if pain/budget is absent.", "principle")]),
    ("Buyer Psychology", "sales/psychology", [
        ("Cost of inaction", "Buyers move when the cost of the status quo exceeds the cost + risk of "
         "change. Quantify the pain honestly; never manufacture urgency.", "principle")]),
    ("Follow-up Discipline", "sales/followup", [
        ("Respectful persistence", "Most deals are lost to silence, not no. Persist within a touch "
         "cap, always honor opt-out, never harass.", "principle")]),
]


def seed(name: str, *, store: Path | None = None) -> dict:
    """Build every seed pack to 'ready' through the real lifecycle. Idempotent-ish: skips a pack
    whose name already exists. Returns {ready:[...], skipped:[...]}."""
    existing = {p["name"] for p in registry.load(name, store)}
    ready, skipped = [], []
    for pname, domain, chunks in BUSINESS_PACKS + SALES_PACKS:
        if pname in existing:
            skipped.append(pname)
            continue
        pack = schema.make(pname, domain, owner="system")
        registry.add(name, pack, store=store)  # -> quarantined
        pid = pack["pack_id"]
        builder.index(name, pid, [{"title": t, "ref": r, "text": txt} for (t, txt, r) in chunks],
                      store=store)            # -> indexed
        builder.evaluate(name, pid, store=store)  # -> evaluated
        builder.promote(name, pid, store=store)   # -> ready
        ready.append(pname)
    return {"ok": True, "ready": ready, "skipped": skipped,
            "total_packs": len(BUSINESS_PACKS) + len(SALES_PACKS)}
