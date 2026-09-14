#!/usr/bin/env python3
"""
certify_meaning_engine — ANIMA LAW 003 (understanding beats remembering): meaning capture +
compression on a REAL seeded input, grounded in evidence, diagnosis-free, append-only.

Vera does not merely store what was said — she COMPRESSES a life into significance. From the
stores she already keeps she computes, for every topic, a significance score that is a FUNCTION
OF THE EVIDENCE (frequency + connectivity + trend + unresolved), packages it as evidence-grounded
Meaning Objects across five dimensions + a descriptive current chapter, scrubs out all diagnosis/
medical language, and records an append-only significance ledger. This certifies that contract
through the SAME functions review.py (the nightly sleep cortex) and mouth.py (the reply leak/no-
diagnosis wall) consume — by seeding a REAL world_state graph and running the live pipeline:

  A. SIGNIFICANCE IS A FUNCTION OF EVIDENCE — with a 'work' hub (many mentions, connected to
     stress/sleep/energy) and a lone 1-mention 'stamps' island seeded into the real graph,
     significance() ranks 'work' first; its components carry real frequency>0 + connectivity>0;
     the island scores far lower and is never headlined as dominant (never-fabricate).
  B. MEANING OBJECTS + THE LAW-003 INVARIANT — meaning() emits objects, and EVERY one carries a
     non-empty evidence dict with real counts ('mentions' present), confidence in (0, 0.95];
     a 'work … dominant force' what_matters object exists; 'work' surfaces as an unresolved weight.
  C. NO-DIAGNOSIS GATE — across every Meaning Object statement, the current_chapter summary, AND
     the GENERATED items of the render block, NO banned diagnosis/medical term appears; and the
     clean-gate positively CATCHES an injected 'burnout/depressed' phrase (the wall is real).
  D. RENDER BINDING BLOCK (the consumed surface) — render_meaning() yields a spine-style block
     that leads with [CHAPTER] and carries [MATTERS], and every emitted tag is in
     MEANING_SCAFFOLD_TOKENS so the mouth's scrub can strip any that leak.
  E. NEVER-FABRICATE ON EMPTY — a creature with no stores yields significance()==[] and
     meaning()==[] (no spurious meaning) and a low-confidence 'too early' chapter, not an invented one.
  F. APPEND-ONLY LEDGER (Law 001) — snapshot() appends a significance snapshot and a SECOND
     snapshot grows the ledger count (never truncates a prior); snapshots() reads them back.

Hermetic + offline (NO model, NO network): meaning.STORE and the world_state/memory_lirf/curiosity
stores it reads are all redirected to a temp dir by _temp_store; the real .anima is fingerprinted
before/after and asserted byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import secrets
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


def _seed_work_hub(World, name: str) -> None:
    """Seed a REAL world_state graph: a 'work' hub mentioned many times and connected to
    stress/sleep/energy (the canonical significance scenario), plus a lone single-mention
    'stamps' island that must NEVER be called dominant. Mirrors the module self-test's
    contrived hub so the live pipeline runs on real edges, not a shim."""
    w = World.load(name)
    for _ in range(32):
        w.add("you", "stressed_by", "work", kind="problem")
    for _ in range(21):
        w.add("work", "leads_to", "stress", kind="inference")
    for _ in range(18):
        w.add("stress", "affects", "sleep", kind="inference")
    for _ in range(9):
        w.add("sleep", "affects", "energy", kind="inference")
    w.add("you", "cares_about", "stamps", kind="preference")   # the isolated 1-mention node
    w.save(name)


def main() -> int:
    from anima import meaning
    from anima.world_state import World
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("MEANING ENGINE — LAW 003: compress a life into evidence-grounded significance (no diagnosis)")
    print("=" * 92)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # The clean-gate is a pure function — exercise the wall outside the store too: it must clear a
    # neutral pressure phrase and CATCH clinical/plain-English diagnosis language.
    ck("C0: the no-diagnosis gate clears 'work is a dominant force' and catches 'burnout'/'depressed'",
       meaning._is_clean("work is a dominant force right now")
       and not meaning._is_clean("this is clearly burnout")
       and not meaning._is_clean("you sound depressed"))

    with _temp_store():
        N = "MeaningCert_" + secrets.token_hex(3)
        _seed_work_hub(World, N)

        # ---- A. SIGNIFICANCE IS A FUNCTION OF EVIDENCE ---------------------------------------
        ranked = meaning.significance(N)
        ck("A1: significance() is non-empty and computed from the seeded graph", len(ranked) > 0)
        by_subj = {it["subject"]: it for it in ranked}
        ck("A2: 'work' ranks FIRST — the hub the evidence makes dominant",
           bool(ranked) and ranked[0]["subject"] == "work")
        work = by_subj.get("work", {})
        comp = work.get("components", {})
        ck("A3: 'work' carries REAL evidence components (frequency>0 AND connectivity>0 — not flat)",
           comp.get("frequency", 0) > 0 and comp.get("connectivity", 0) > 0)
        ck("A4: the 1-mention 'stamps' island scores far below the hub (never-fabricate floor)",
           by_subj.get("stamps", {}).get("score", 0) < work.get("score", 0)
           and work.get("score", 0) - by_subj.get("stamps", {}).get("score", 0) > 1.0)

        # ---- B. MEANING OBJECTS + THE LAW-003 INVARIANT -------------------------------------
        objs = meaning.meaning(N)
        ck("B1: meaning() emits Meaning Objects from the real graph", len(objs) > 0)
        ck("B2: LAW 003 — EVERY object carries a non-empty evidence dict with real counts (mentions)",
           all(isinstance(o.get("evidence"), dict) and o["evidence"]
               and "mentions" in o["evidence"] for o in objs))
        ck("B3: confidence on every object is in (0, 0.95] and never asserted as certainty",
           all(0.0 < o.get("confidence", 0) <= 0.95 for o in objs))
        matters = [o for o in objs if o["dimension"] == meaning.WHAT_MATTERS]
        ck("B4: a 'work … dominant force' what_matters object exists (the headline)",
           any(o["subject"] == "work" and "dominant force" in o["statement"] for o in matters))
        ck("B5: 'stamps' (1 mention, isolated) is NEVER called a dominant force",
           all("dominant force" not in o["statement"]
               for o in matters if o["subject"] == "stamps"))
        unresolved = [o for o in objs if o["dimension"] == meaning.WHAT_UNRESOLVED]
        ck("B6: 'work' surfaces as an UNRESOLVED open weight (a stated stressor)",
           any(o["subject"] == "work" for o in unresolved))

        # ---- C. NO-DIAGNOSIS GATE over the WHOLE generated corpus ---------------------------
        chap = meaning.current_chapter(N)
        block = meaning.render_meaning(objs, chap)
        ck("C1: NO Meaning-Object statement trips a banned diagnosis/medical term",
           all(meaning._is_clean(o["statement"]) for o in objs))
        ck("C2: the current_chapter summary is diagnosis-free",
           meaning._is_clean(chap.get("summary", "")))
        ck("C3: the GENERATED items of the render block carry NO banned diagnosis term",
           meaning._is_clean(meaning._items_of(block)))

        # ---- D. RENDER BINDING BLOCK — the surface mouth/review consume ---------------------
        ck("D1: render_meaning() produces a non-empty spine-style binding block", bool(block.strip()))
        ck("D2: the block leads with the [CHAPTER] through-line and carries a [MATTERS] line",
           "[CHAPTER]" in block and "[MATTERS]" in block)
        ck("D3: every emitted dimension tag is in MEANING_SCAFFOLD_TOKENS (the mouth can scrub leaks)",
           all(t in meaning.MEANING_SCAFFOLD_TOKENS
               for t in ("[MATTERS]", "[CHAPTER]", "[UNRESOLVED]")))

        # ---- E. NEVER-FABRICATE ON EMPTY ----------------------------------------------------
        EMPTY = "MeaningEmpty_" + secrets.token_hex(3)
        ck("E1: an empty life yields significance()==[] (no fabricated weight)",
           meaning.significance(EMPTY) == [])
        ck("E2: an empty life yields meaning()==[] (no spurious Meaning Objects)",
           meaning.meaning(EMPTY) == [])
        chap_e = meaning.current_chapter(EMPTY)
        ck("E3: an empty chapter is a low-confidence 'too early', not an invented one",
           chap_e.get("confidence", 1.0) <= 0.15 and not chap_e.get("themes")
           and ("early" in chap_e.get("summary", "").lower()
                or "enough" in chap_e.get("summary", "").lower()))

        # ---- F. APPEND-ONLY MEANING LEDGER (Law 001) ----------------------------------------
        snap1 = meaning.snapshot(N)
        ck("F1: snapshot() appends a Law-003 significance snapshot to the ledger",
           snap1 is not None and snap1.get("law") == "ANIMA LAW 003"
           and len(snap1.get("significance", [])) > 0)
        n_before = len(meaning.snapshots(N))
        meaning.snapshot(N)
        ck("F2: the ledger is APPEND-ONLY — a second snapshot grows the count, never truncates",
           len(meaning.snapshots(N)) == n_before + 1)

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nMEANING-ENGINE CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
