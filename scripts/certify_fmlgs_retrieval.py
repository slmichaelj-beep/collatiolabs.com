#!/usr/bin/env python3
"""
certify_fmlgs_retrieval — FMLGS: store -> embed -> retrieve the RIGHT object by SEMANTIC match,
recall >= the keyword baseline, the compute win at scale, all deterministic / offline / read-only.

FMLGS is the embedding + fast-retrieval layer over the LERF knowledge vault. This certifies the
LIVE retrieval path through the SAME public entry point the rest of the system would call —
fmlgs.build_from_vault(name) over a real LERF store (read through lerf's public active-only
listers) — proving store->embed->retrieve actually returns the right item by meaning, with no
model and no network:

  A. BUILD FROM THE REAL VAULT — synthetic objects are STORED into the real LERF store via the
     public store_skill/store_object API, then build_from_vault(name) indexes exactly the
     publicly-listable ACTIVE set (a CANDIDATE object is NOT indexed); embeddings are [N,D] unit-norm.
  B. STORE -> EMBED -> RETRIEVE THE RIGHT OBJECT — a doctor-note query retrieves the medical skill
     as #1, an errand query the errand skill #1, an invoice query the invoice skill #1, a
     failing-test query the debug skill #1 — by SEMANTIC similarity (none of these queries is a
     keyword copy of the object); and a cross-type query reaches a HEURISTIC, not just skills.
  C. THE EMBEDDING IS REAL + DETERMINISTIC — embed_text: same text -> byte-identical vector,
     unit-norm, empty -> zero; semantically near texts score higher than far ones; morphology/typo
     tolerance (summarize ~ summarise) beats an unrelated text; IDF down-weights a ubiquitous gram.
  D. RECALL >= KEYWORD BASELINE — FMLGS recall@5 vs the deterministic keyword baseline (lerf._score)
     is >= 1.0 (it recalls everything the shipping retrieval would have served), and recall@5 vs the
     exact linear cosine is 1.0 at this scale (pass-through is non-degrading).
  E. THE SCALING WIN — on a synthetic N=800 fully-distinct vault the Gaussian hierarchy ACTIVATES
     (levels >= 2), a query scores < 50% of the vault (the compute saving), stays lossless vs exact
     cosine, and returns each unique-phrase object as its own #1.
  F. READ-ONLY — building + querying the index creates NO new store files (FMLGS never writes).

Hermetic + offline (no model, no network): lerf.STORE is redirected by _temp_store, and
constitution.STORE / reliability.DEFAULT_STORE (the guarded-load side stores) are redirected here;
the real .anima is fingerprinted before/after and asserted byte-identical. Exit 0 == CERTIFIED,
1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store
_footprint = _g0pe._footprint


def main() -> int:
    from anima import fmlgs, lerf
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("FMLGS RETRIEVAL — store -> embed -> retrieve the RIGHT object (semantic, recall >= keyword)")
    print("=" * 92)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # ---- C. THE EMBEDDING IS REAL + DETERMINISTIC (pure, store-free — exercise outside the store) ----
    v1 = fmlgs.embed_text("summarize this doctor's note and turn it into reminders")
    v2 = fmlgs.embed_text("summarize this doctor's note and turn it into reminders")
    ck("C1: embed_text is deterministic — same text -> byte-identical vector", np.array_equal(v1, v2))
    ck("C2: embed_text is unit-norm and empty text -> zero vector",
       abs(float(np.linalg.norm(v1)) - 1.0) < 1e-5
       and float(np.linalg.norm(fmlgs.embed_text(""))) == 0.0)
    med = fmlgs.embed_text("summarize the doctor appointment and list the medications")
    note = fmlgs.embed_text("summarize this doctor's note into a medication summary")
    errand = fmlgs.embed_text("plan the most efficient driving route between my errands")
    ck("C3: semantically NEAR texts score higher than FAR ones (real similarity, not noise)",
       float(med @ note) > float(med @ errand))
    a = fmlgs.embed_text("summarize the invoice")
    b = fmlgs.embed_text("summarise the invoices")          # British spelling + plural
    c = fmlgs.embed_text("plan my saturday errands")
    ck("C4: morphology/typo tolerance (summarize~summarise) beats an unrelated text",
       float(a @ b) > float(a @ c))
    idf = fmlgs.compute_idf(["the cat sat", "the dog sat", "the bird flew"])
    ck("C5: IDF down-weights a ubiquitous gram below a rare one",
       idf.get("w:sat", 9.0) < idf.get("w:flew", 0.0))

    with _temp_store() as tp:
        # also redirect the two stores _temp_store doesn't cover (guarded-load side effects on a
        # lerf store_* write) — same discipline as certify_personal_intelligence.py.
        extra = []
        for modname, attr in (("anima.constitution", "STORE"), ("anima.reliability", "DEFAULT_STORE")):
            try:
                m = __import__(modname, fromlist=["_"])
                extra.append((m, attr, getattr(m, attr, None)))
                if getattr(m, attr, None) is not None:
                    setattr(m, attr, tp)
            except Exception:
                pass
        try:
            import secrets
            N = "fmlgs_cert_" + secrets.token_hex(3)
            A = lerf.ACTIVE

            # ---- seed a SYNTHETIC vault into the REAL LERF store via the PUBLIC API --------------
            # Domains are deliberately distinct so each query has a single right answer to find.
            syn = [
                lerf.make_skill("summarize_medical_appointment", "health",
                    inputs=["raw doctor's note"],
                    steps=["Identify the diagnosis", "Extract instructions and dosages",
                           "List follow-ups with dates", "Write a 3-sentence summary"],
                    outputs=["plain summary", "medication list"], state=A,
                    failure_modes=["dropping a dosage"]),
                lerf.make_skill("plan_errands", "logistics",
                    inputs=["list of stops", "start location"],
                    steps=["Cluster stops by area", "Order to minimise backtracking",
                           "Account for opening hours"],
                    outputs=["ordered route"], state=A),
                lerf.make_skill("summarize_invoice", "finance",
                    inputs=["a raw invoice"],
                    steps=["Identify the vendor and invoice number",
                           "Extract every line item with its amount",
                           "Sum the total and note the due date"],
                    outputs=["plain summary", "line-item list", "total and due date"], state=A),
                lerf.make_skill("debug_failing_test", "engineering",
                    inputs=["a failing test and its traceback"],
                    steps=["Read the assertion that failed", "Localise the offending function",
                           "Form a hypothesis", "Reproduce and fix"],
                    outputs=["root cause", "the fix"], state=A),
                lerf.make_skill("draft_birthday_message", "social",
                    inputs=["the person and the relationship"],
                    steps=["Recall a shared specific", "Open warmly", "Close with a wish"],
                    outputs=["a short warm message"], state=A),
                lerf.make_heuristic("ship_when_tests_green", "engineering",
                    condition="the hermetic selftest exits zero and the diff is additive",
                    action="ship the change behind the existing freeze",
                    applies_when=["additive changes"],
                    fails_when=["a change that mutates shared state"], state=A),
                lerf.make_mental_model("supply_and_demand", "economics",
                    entities=["buyers", "sellers", "price"],
                    dynamics=["price rises when demand exceeds supply"], state=A),
                lerf.make_failure_mode("silent_data_loss", "engineering",
                    trigger="a rollup drops items without recording the loss",
                    symptom="totals no longer reconcile",
                    mitigation="record an approved_loss line", state=A),
            ]
            for o in syn:
                if o.get("type") == "skill":
                    lerf.store_skill(o, name=N)
                else:
                    lerf.store_object(o, name=N)
            # a NON-active object must never be indexed (active-only public listing)
            lerf.store_skill(lerf.make_skill("inactive_skill", "misc", ["i"], ["s"], ["o"],
                                             state=lerf.CANDIDATE), name=N)

            def _id_of(nm):
                return next(o["id"] for o in syn if o["name"] == nm)

            # ---- A. BUILD FROM THE REAL VAULT (the public drop-in entry point) -------------------
            index = fmlgs.build_from_vault(name=N)
            ck("A1: build_from_vault indexed exactly the publicly-listable ACTIVE set",
               len(index.objects) == len(syn))
            ck("A2: a non-active (CANDIDATE) object is NOT indexed (active-only retrieval)",
               all(o.get("name") != "inactive_skill" for o in index.objects))
            ck("A3: the embeddings matrix is [N, D] and unit-norm",
               index.X.shape == (len(syn), fmlgs.EMBED_DIM)
               and np.allclose(np.linalg.norm(index.X, axis=1), 1.0, atol=1e-4))

            # ---- B. STORE -> EMBED -> RETRIEVE THE RIGHT OBJECT BY SEMANTIC MATCH ----------------
            top = index.query_ids("summarize this doctor note and turn it into reminders", k=3)
            ck("B1: a doctor-note query retrieves the MEDICAL skill as #1 (semantic, not keyword copy)",
               bool(top) and top[0] == _id_of("summarize_medical_appointment"))
            etop = index.query_ids("plan my errands for saturday", k=3)
            ck("B2: an errand query retrieves the ERRAND skill as #1",
               bool(etop) and etop[0] == _id_of("plan_errands"))
            itop = index.query_ids("summarize this invoice and total the line items", k=3)
            ck("B3: an invoice query retrieves the INVOICE skill as #1",
               bool(itop) and itop[0] == _id_of("summarize_invoice"))
            btop = index.query_ids("why is my unit test failing with a traceback", k=3)
            ck("B4: a failing-test query retrieves the DEBUG skill as #1",
               bool(btop) and btop[0] == _id_of("debug_failing_test"))
            stop = index.query_ids("when should I ship this engineering change", k=3)
            ck("B5: a cross-type query reaches a HEURISTIC across object types (not skills-only)",
               _id_of("ship_when_tests_green") in stop)
            # query() returns (object, score) with a real cosine score in (0, 1]
            hits = index.query("summarize this doctor note and turn it into reminders", k=1)
            ck("B6: query returns (object, score) with a real cosine score in (0,1]",
               len(hits) == 1 and 0.0 < float(hits[0][1]) <= 1.0
               and hits[0][0]["id"] == _id_of("summarize_medical_appointment"))

            # ---- D. RECALL >= THE KEYWORD BASELINE (the 'same intelligence' bar) -----------------
            qset = [
                "summarize this doctor note and turn it into reminders",
                "plan my errands for saturday",
                "summarize this invoice and total the line items",
                "why is my unit test failing with a traceback",
                "draft a birthday message for my sister",
                "when should I ship this engineering change",
                "how do supply and demand set a price",
                "how does silent data loss happen in a rollup",
            ]
            rep = fmlgs.measure(index, qset, k=5, repeats=80)
            ck("D1: FMLGS recall@5 vs the deterministic KEYWORD baseline is >= 1.0 "
               "(got %.3f)" % rep["recall_vs_keyword"], rep["recall_vs_keyword"] >= 1.0 - 1e-9)
            ck("D2: FMLGS recall@5 vs the EXACT linear cosine is 1.0 (pass-through, non-degrading) "
               "(got %.3f)" % rep["recall_vs_linear"], rep["recall_vs_linear"] >= 1.0 - 1e-9)
            ck("D3: at this scale the hierarchy is one flat level + scores every object (honest "
               "pass-through, levels=%d)" % rep["footprint"]["levels"],
               rep["footprint"]["levels"] == 1 and abs(rep["scored_fraction"] - 1.0) < 1e-9)
            ck("D4: the footprint ledger is exact (vectors + centroids + idf == total) and latency "
               "measured for all three paths",
               rep["footprint"]["vectors_bytes"] + rep["footprint"]["centroids_bytes"]
               + rep["footprint"]["idf_bytes"] == rep["footprint"]["total_bytes"]
               and rep["latency_fmlgs_us"] > 0 and rep["latency_linear_us"] > 0
               and rep["latency_keyword_us"] > 0)

            # ---- E. THE SCALING WIN — hierarchy ACTIVATES + scores a FRACTION at large N ----------
            # A synthetic N=800 vault of FULLY-distinct objects (each carries a globally-unique,
            # counter-tagged phrase) so every query has a definite top-1 and there are no ties.
            import random as _random
            rng = _random.Random(7)
            adjs = ["careful", "rapid", "thorough", "gentle", "precise", "robust", "minimal",
                    "deep", "broad", "clean"]
            verbs = ["summarize", "reconcile", "debug", "plan", "draft", "scale", "localise",
                     "extract", "tighten", "order"]
            nouns = ["cardiology appointment", "quarterly invoice", "failing pytest", "grocery route",
                     "birthday sonnet", "risotto recipe", "payroll ledger", "memory leak",
                     "dermatology referral", "airport transfer", "bank statement", "regression suite",
                     "elegy draft", "paella scaling", "neurology note", "refund receipt",
                     "deadlock trace", "memoir chapter", "bakery order", "tagine substitution"]
            big, kctr = [], 0
            while len(big) < 800:
                av, vv, nv = rng.choice(adjs), rng.choice(verbs), rng.choice(nouns)
                kctr += 1
                phrase = f"{vv} the {av} {nv} number {kctr}"     # kctr makes the phrase unique
                big.append(lerf.make_skill(
                    f"skill_{vv}_{nv.split()[0]}_{kctr}", vv,
                    inputs=[f"a {nv}"], steps=[phrase, f"then finalise the {nv} cleanly"],
                    outputs=[f"{nv} done"], state=A))
            big_index = fmlgs.FMLGSIndex.build(big)
            big_qs = [o["steps"][0] for o in big[:12]]
            big_rep = fmlgs.measure(big_index, big_qs, k=5, repeats=40)
            ck("E1: at N=800 the Gaussian hierarchy ACTIVATES (levels>=2, leaves>=2)",
               big_rep["footprint"]["levels"] >= 2 and big_rep["footprint"]["leaves"] >= 2)
            ck("E2: a query scores only a FRACTION of the vault (< 50%%) — the compute win "
               "(scored %.0f / %d)" % (big_rep["mean_scored"], len(big)),
               big_rep["scored_fraction"] < 0.5)
            ck("E3: FMLGS stays LOSSLESS vs the exact cosine search at scale (recall %.3f >= 0.98)"
               % big_rep["recall_vs_linear"], big_rep["recall_vs_linear"] >= 0.98)
            ck("E4: every unique-phrase query returns its OWN object as #1 (right answer at scale)",
               all(big_index.query_ids(o["steps"][0], k=1)[:1] == [o["id"]] for o in big[:12]))

            # ---- F. READ-ONLY — FMLGS never writes the store -------------------------------------
            before = set(p.name for p in tp.glob("*"))
            _ = fmlgs.build_from_vault(name=N)
            _ = index.query_ids("anything at all", k=3)
            after = set(p.name for p in tp.glob("*"))
            ck("F1: building + querying the index creates NO new store files (pure read/index)",
               before == after)
        finally:
            for m, attr, old in extra:
                if old is not None:
                    setattr(m, attr, old)

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nFMLGS-RETRIEVAL CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
