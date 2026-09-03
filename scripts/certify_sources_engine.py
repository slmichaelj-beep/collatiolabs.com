#!/usr/bin/env python3
"""
certify_sources_engine — the LERF LEARNING-SOURCES ingestion machinery (anima/sources.py) and its
hard, freeze-bounded contract: MANY mouths feed ONE gate, and every grown object is PROVENANCE-
STAMPED with the source that taught it. Phase 6b of LERF: Vera grows KNOWLEDGE from material BEYOND
a teacher model — books, documents, conversations, resolved REALITY outcomes, and captured PERSONAL
EXPERIENCE — but no source gets a private door around the gate, and nothing here can mint Vera an
inner life. Certified through the SAME public Source API lerf_grow.grow_from_source() drives:

  A. REGISTRY — all five new sources + the teacher source are registered under their SOURCE_KINDS
     (exactly six), and the material digest is bounded + whitespace-collapsed (provenance is sane).
  B. REALITY OUTCOMES (model-free, $0) — a CONFIRMED low-surprise resolved loop grows an ACTIVE
     HEURISTIC; a HIGH-surprise loop grows an ACTIVE MENTAL-MODEL revision. Both go through the REAL
     object gate (promote_object -> activate_object), are grounded in the resolved-loop facts
     (category + surprise live verbatim in support[]), source-stamped reality_outcome, and the grown
     heuristic is RETRIEVABLE on a natural query. No teacher, no cloud, no key — $0 by construction.
  C. PERSONAL EXPERIENCE (model-free, $0, FREEZE-GUARDED) — captured USER experiences grow ACTIVE
     user PREFERENCE + HEURISTIC objects (the USER's, never Vera's), gated + source-stamped, and the
     preference is RETRIEVABLE. THE FREEZE (the #1 product rule, the whole point of this source): a
     poisoned capture naming VERA as the value-holder is REFUSED by lerf's freeze-guarded factory and
     never reaches disk — and that refusal is lerf's OWN (make_value raises FreezeViolation directly).
  D. TEXT SOURCE (book) via the $0 StubTeacher — a book excerpt distills, through the SAME Wave-2
     gate, into an ACTIVE retrievable skill that carries BOTH the teacher provenance (who taught +
     test cases) AND the source stamp (source_kind=book). Belt-and-braces freeze: an identity excerpt
     is REFUSED before any teacher work; and with NO teacher a text source does NO work — the
     hermetic path can never reach cloud.
  E. PROVENANCE READBACK — sources.source_provenance() reads which-source-taught-it off a grown
     object's own support[] (auditable, never inferred); a non-source object reads source_kind=None.

HONEST CLASSIFICATION: this is INTERNAL factory machinery (no server endpoint, no UI button — it is
imported by anima/lerf_grow.py, NOT by anima/server.py). The deterministic, $0 ingestion -> real-gate
-> active -> source-stamped contract is PROVEN here end-to-end; the user-facing effect is INDIRECT
(the live mouth later retrieves the ACTIVE objects this engine accumulates), and the text sources'
real-corpus leg uses a live, paid cloud teacher only on lerf_grow's explicit --live path. -> PARTIAL.

Hermetic + offline: every store (incl. lerf.STORE via _temp_store, plus cloud.STORE redirected here
defensively) points at a temp dir; the StubTeacher is the deterministic $0 teacher (never cloud); no
model, no network, no key. The real .anima is fingerprinted before/after and asserted byte-identical.
Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store
_footprint = _g0pe._footprint


def main() -> int:
    from anima import sources, lerf, lerf_distill, cloud
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("SOURCES ENGINE — many mouths, ONE gate; every grown object source-stamped; freeze absolute")
    print("=" * 92)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    with _temp_store() as tp:
        # cloud.STORE is NOT in _temp_store's module set; redirect it ourselves so even a stray
        # key/spend read can only touch the temp dir (mirrors certify_brain_select.py). The sources
        # paths exercised here are $0 + model-free, so no cloud file should ever be written — we
        # assert exactly that at the end (E-cost).
        saved_cloud_store = getattr(cloud, "STORE", None)
        cloud.STORE = tp
        try:
            stub = lerf_distill.StubTeacher(provider="stub-sources-cert", model="src-stub-cert-v1")

            # ---- A. REGISTRY + DIGEST ----------------------------------------------------------
            reg = sources.all_sources()
            ck("A1: all five new sources + the teacher source are registered (exactly six SOURCE_KINDS)",
               set(reg) == set(sources.SOURCE_KINDS) and len(sources.SOURCE_KINDS) == 6
               and all(isinstance(v, sources.Source) for v in reg.values()))
            ck("A2: get_source maps each kind to a Source whose .kind matches; unknown -> None",
               all(sources.get_source(k).kind == k for k in sources.SOURCE_KINDS)
               and sources.get_source("not_a_real_source") is None)
            ck("A3: the material digest is bounded + whitespace-collapsed (provenance is sane)",
               sources._digest("a  b\n c" * 100, 20) == ("a b c" * 100)[:20])

            # ---- B. REALITY OUTCOMES (model-free, $0) ------------------------------------------
            rb = "reality_cert"
            rsrc = sources.RealityOutcomeSource()
            # B-confirmed: a low-surprise CONFIRMED loop -> an ACTIVE heuristic through the real gate.
            rconf = rsrc.ingest(sources.SAMPLE_REALITY_CONFIRMED, name=rb)
            ck("B1: a CONFIRMED resolved loop grew an object that reached ACTIVE through the real gate",
               rconf.get("ok") and len(rconf["grown"]) == 1 and rconf["grown"][0]["ok"])
            gc = rconf["grown"][0]
            sc = lerf._get(rb, gc["object_id"])
            ck("B2: the confirmed lesson is a HEURISTIC in state ACTIVE (gate truly passed)",
               bool(sc) and sc.get("type") == lerf.HEURISTIC and sc.get("state") == lerf.ACTIVE)
            ck("B3: it is grounded in the resolved-loop facts verbatim (category + surprise in support)",
               any("category=sleep_quality" in s for s in sc.get("support", []))
               and any("surprise=" in s for s in sc.get("support", [])))
            ck("B4: provenance stamps WHICH source taught it (source_kind=reality_outcome + a digest)",
               gc["source"].get("source_kind") == sources.SOURCE_REALITY
               and gc["source"].get("source_material"))
            # B-surprise: a high-surprise loop -> an ACTIVE mental-model revision.
            rsurp = rsrc.ingest(sources.SAMPLE_REALITY_SURPRISE, name=rb)
            sm = lerf._get(rb, rsurp["grown"][0]["object_id"]) if rsurp.get("grown") else None
            ck("B5: a HIGH-surprise resolved loop grew an ACTIVE MENTAL_MODEL revision",
               rsurp.get("ok") and rsurp["grown"][0]["ok"]
               and bool(sm) and sm.get("type") == lerf.MENTAL_MODEL and sm.get("state") == lerf.ACTIVE)
            # the grown lesson is actually RETRIEVABLE — the point of growing it.
            gotr = lerf.retrieve_heuristics("sleep_quality", domain="reality:sleep_quality", name=rb)
            ck("B6: the grown reality heuristic is RETRIEVABLE on a real query",
               bool(gotr) and any(h["id"] == gc["object_id"] for h in gotr))
            # a record too thin to learn from grows nothing (honest: no fabricated lesson).
            thin = rsrc.ingest({"kind": "learning"}, name=rb)
            ck("B7: a category-less record grows NOTHING (no fabricated lesson)",
               thin.get("ok") is False and thin.get("grown") == [])

            # ---- C. PERSONAL EXPERIENCE (model-free, $0, FREEZE-GUARDED) -----------------------
            pb = "experience_cert"
            psrc = sources.PersonalExperienceSource()
            pres = psrc.ingest([sources.SAMPLE_EXPERIENCE_PREFERENCE,
                                sources.SAMPLE_EXPERIENCE_LESSON,
                                sources.SAMPLE_EXPERIENCE_SELF], name=pb, person="Lamar")
            ck("C1: captured USER experiences grew exactly 2 ACTIVE patterns (preference + lesson)",
               pres.get("ok") and sum(1 for g in pres["grown"] if g["ok"]) == 2)
            pref = next((g for g in pres["grown"] if g["type"] == lerf.PREFERENCE), None)
            sp = lerf._get(pb, pref["object_id"]) if pref else None
            ck("C2: the user PREFERENCE is ACTIVE, the USER's (not Vera's), + source-stamped experience",
               bool(pref) and pref["ok"]
               and pref["source"].get("source_kind") == sources.SOURCE_EXPERIENCE
               and bool(sp) and sp.get("type") == lerf.PREFERENCE and sp.get("state") == lerf.ACTIVE
               and not lerf.is_self_referential_subject(sp.get("subject", "")))
            gotp = lerf.retrieve_preferences("concise written updates", name=pb)
            ck("C3: the grown user preference is RETRIEVABLE on a real query",
               bool(gotp) and any(p["id"] == pref["object_id"] for p in gotp))
            # THE FREEZE — the #1 product rule. The Vera-self value was REFUSED and NEVER stored.
            ck("C4[FREEZE]: a Vera-self value was REFUSED (counted) and never appears among grown",
               pres.get("refused_self_referential") == 1
               and all("vera" not in (g.get("name") or "").lower() for g in pres["grown"]))
            # prove the freeze is the FACTORY's own, not merely this source's counter.
            raised = False
            try:
                lerf.make_value(target="Vera's own goal of becoming more curious")
            except lerf.FreezeViolation:
                raised = True
            ck("C5[FREEZE]: the guard is lerf's OWN factory (make_value raises FreezeViolation on Vera-self)",
               raised)

            # ---- D. TEXT SOURCE (book) via the $0 StubTeacher ---------------------------------
            tb = "book_cert"
            bres = sources.BookSource().ingest(sources.SAMPLE_BOOK, name=tb, teacher=stub,
                                               topic="read an invoice")
            ck("D1: a book excerpt distilled, through the gate, into an ACTIVE skill (via the $0 stub)",
               bres.get("ok") and len(bres["grown"]) == 1 and bres["grown"][0]["ok"])
            gb = bres["grown"][0]
            sk = lerf._get(tb, gb["object_id"])
            ck("D2: the grown skill is in state ACTIVE (passed the real Wave-2 gate)",
               bool(sk) and sk.get("state") == lerf.ACTIVE)
            ck("D3: it carries BOTH the source stamp (source_kind=book) AND the teacher provenance",
               gb["source"].get("source_kind") == sources.SOURCE_BOOK
               and gb["provenance"].get("taught_by_provider") == "stub-sources-cert"
               and len(gb["provenance"].get("certified_against", [])) >= 2)
            gotk = lerf.retrieve_skills("summarize this invoice and tell me what I owe", name=tb)
            ck("D4: the grown skill is RETRIEVABLE on a natural user task",
               bool(gotk) and any(s["id"] == gb["object_id"] for s in gotk))
            # belt-and-braces freeze: an identity excerpt is refused BEFORE any teacher work.
            idres = sources.BookSource().ingest("a passage about who you really are inside",
                                                name=tb, teacher=stub, topic="who are you really")
            ck("D5[FREEZE]: an identity excerpt is REFUSED before any teacher work (belt-and-braces)",
               idres.get("ok") is False and "freeze" in (idres.get("reason") or "").lower())
            # cost discipline: a text source with NO teacher does NO work (cannot reach cloud).
            notch = sources.DocumentSource().ingest(sources.SAMPLE_DOCUMENT, name=tb, teacher=None)
            ck("D6: NO teacher -> NO work (the hermetic path can never reach cloud)",
               notch.get("ok") is False and "teacher" in (notch.get("reason") or "").lower())

            # ---- E. PROVENANCE READBACK -------------------------------------------------------
            sp_read = sources.source_provenance(gb["object_id"], name=tb)
            ck("E1: source_provenance reads the stamp off the object's own support[] (auditable)",
               sp_read.get("source_kind") == sources.SOURCE_BOOK
               and sp_read.get("object_id") == gb["object_id"]
               and bool(sp_read.get("ingested_at")))
            # a hand-built object that was NEVER source-grown reads source_kind=None (never inferred).
            plain = {"id": "obj_plain", "name": "n", "type": lerf.HEURISTIC, "support": []}
            ck("E2: a non-source object reads source_kind=None (provenance is read, never invented)",
               sources.source_provenance(plain).get("source_kind") is None)

            # ---- E-cost. ZERO cloud spend / NO key touched anywhere ---------------------------
            ck("E3[cost]: NO cloud spend file written ($0 — no paid call on any path here)",
               not (tp / "spend.json").exists())
            ck("E4[cost]: NO brain.json written (never read or touched a provider key)",
               not (tp / "brain.json").exists())
        finally:
            if saved_cloud_store is not None:
                cloud.STORE = saved_cloud_store

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nSOURCES-ENGINE CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
