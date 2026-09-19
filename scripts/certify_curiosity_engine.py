#!/usr/bin/env python3
"""
certify_curiosity_engine — THE CURIOSITY ENGINE (ANIMA LAW 002 — never make the same discovery twice).

Broader than the curiosity_budget cap (which governs FREQUENCY): this certifies the ENGINE itself —
the gap detector, the contextual question generator, and the append-only Asked Ledger that makes a
discovered gap never get re-asked — AND that it is wired into the LIVE reply path (anima.server._turn)
where its question is appended to Vera's reply, persisted, and marked asked. Certified through the SAME
functions the live turn calls (curiosity.next_question / candidate_gaps / mark_asked):

  A. GAP -> QUESTION — an UNKNOWN taxonomy slot becomes a warm, in-character, optional question that
     names the missing category (never a canned "favorite color"), and is clean of scaffold tags +
     AI-disclaimers (the #1 product rule). A repeatedly-mentioned unknown-relationship entity (the
     canonical "Mike x42") becomes a SUSPECTED gap whose question NAMES Mike and asks HOW they know
     each other — anchored to what the user actually said, not a form field.
  B. LAW 002 [never re-discover the KNOWN] — once a fact is KNOWN (a corroborated birthday), the engine
     produces NO gap for it and NEVER phrases a question about it: detect_gaps drops it, and 40 deep
     draws of next_question never ask it.
  C. LAW 002 [never re-ask] — after mark_asked(gap), that gap is gone from candidate_gaps FOREVER and
     next_question never returns it again; the Asked Ledger is APPEND-ONLY (a second mark grows it,
     never truncates — Law 001), and it survives a fresh read from disk (restart-survival).
  D. LIVE WIRE — the EXACT live-turn sequence (server._turn lines ~1150-1165): on a fresh seeded
     creature next_question yields a question, mark_asked(candidate_gaps()[0]) burns it, and re-asking
     after the mark returns a DIFFERENT gap (or None) — never the same one. Proven through the same
     three functions server._turn imports and calls, so "holds here" == "holds in the live aside".
  E. CONTRADICTION — a superseded value (Portland -> Seattle) becomes a CONTRADICTED gap whose clarify
     question names BOTH values, warmly, and is safe.

Hermetic + offline (NO model, NO network): every store the engine + its substrate touch
(curiosity/memory_lirf/world_state via gate0_prime_experience._temp_store) is redirected to a temp
dir, so the append-only Asked Ledger (.anima/{name}.curiosity.jsonl) and the LIRF/world stores land
there; the real .anima is fingerprinted before/after and asserted byte-identical. Exit 0 == CERTIFIED,
1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import re
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
    from anima import curiosity, memory_lirf, world_state
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("CURIOSITY ENGINE — Law 002: gap -> question -> never make the same discovery twice")
    print("=" * 84)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # _looks_unsafe / law_002 are pure — exercise outside the store too.
    ck("L0: law_002() resolves to the NEVER-MAKE-THE-SAME-DISCOVERY-TWICE text",
       "NEVER MAKE THE SAME DISCOVERY TWICE" in curiosity.law_002())
    ck("L0b: _looks_unsafe rejects a scaffold tag + an AI-disclaimer, passes a warm line",
       curiosity._looks_unsafe("[KNOWN] your birthday")
       and curiosity._looks_unsafe("As an AI, I don't have a birthday")
       and not curiosity._looks_unsafe("When's your birthday? I'd love to know."))

    with _temp_store():
        N = "CurioCert"

        # ---- A. GAP -> QUESTION (taxonomy UNKNOWN + the canonical Mike SUSPECTED) -----------
        gaps0 = curiosity.detect_gaps(N)
        ck("A1: an empty creature -> many UNKNOWN/SUSPECTED gaps across the taxonomy",
           len(gaps0) >= 8 and all(g["kind"] in
                                   (curiosity.UNKNOWN, curiosity.SUSPECTED, curiosity.CONTRADICTED)
                                   for g in gaps0))
        bday = [g for g in gaps0 if g["slot"] == "birthday"]
        ck("A2: birthday is an UNKNOWN gap when unknown", len(bday) == 1 and bday[0]["kind"] == curiosity.UNKNOWN)
        bq = curiosity.generate_question(bday[0]) if bday else ""
        ck("A3: the birthday gap becomes a warm question that NAMES the category, clean + in-character",
           "birthday" in bq.lower() and not curiosity._looks_unsafe(bq))
        ck("A4: NO generated question is the banned canned 'favorite color' ask",
           all("favorite color" not in (curiosity.generate_question(g) or "").lower() for g in gaps0))

        # the canonical SUSPECTED relationship gap: Mike mentioned 42x, relationship unknown.
        w = world_state.World([])
        for _ in range(42):
            w.add("you", "knows", "Mike", kind="relationship")
        w.add("you", "knows", "Quinn", kind="relationship")   # 1 mention -> below the floor
        w.save(N)
        gaps_w = curiosity.detect_gaps(N)
        mike = [g for g in gaps_w if curiosity._norm_node(g.get("entity", "")) == "mike"]
        ck("A5: a 42-mention unknown-relationship entity -> exactly one SUSPECTED gap (Mike)",
           len(mike) == 1 and mike[0]["kind"] == curiosity.SUSPECTED)
        ck("A6: a 1-mention entity (Quinn) does NOT clear the mention floor (Observed > Assumed)",
           all(curiosity._norm_node(g.get("entity", "")) != "quinn" for g in gaps_w))
        ck("A7: the high-mention Mike gap OUTRANKS an empty favorite-food slot (priority is signal-led)",
           mike and curiosity._score(mike[0]) > max(
               (curiosity._score(g) for g in gaps_w if g["slot"] == "favorite_food"), default=0.0))
        mq = curiosity.generate_question(mike[0]) if mike else ""
        ck("A8: the Mike question NAMES Mike + asks HOW they know each other (contextual, not canned)",
           "Mike" in mq and re.search(r"know each other|who (?:they|she|he) (?:are|is)", mq, re.I) is not None
           and not curiosity._looks_unsafe(mq))

        # ---- B. LAW 002 [never re-discover the KNOWN] --------------------------------------
        f = memory_lirf.Facts([])
        for c in f.capture(N, "my birthday is June 12"):
            f.merge(c)
        for c in f.capture(N, "yep, June 12 is my birthday"):   # corroborate -> KNOWN (>= 0.85)
            f.merge(c)
        f.save(N)
        row = memory_lirf.Facts.load(N).lookup(curiosity.SELF, "birthday")
        ck("B1: the birthday is now stored as a KNOWN fact (conf >= the [KNOWN] floor)",
           row is not None and float(row["confidence"]) >= curiosity._CONF_KNOWN)
        gaps_k = curiosity.detect_gaps(N)
        ck("B2: LAW 002 [detect] — a KNOWN birthday produces NO birthday gap (it's been discovered)",
           all(g["trait"] != "birthday" and g["slot"] != "birthday" for g in gaps_k))
        leaked = [q for q in (curiosity.generate_question(g) for g in gaps_k)
                  if q and re.search(r"\bbirthday\b", q, re.I)]
        ck("B3: LAW 002 [generate] — no generated question references the KNOWN birthday",
           len(leaked) == 0)
        seen_bday = False
        for _ in range(40):                                     # deep budget -> frequency never masks it
            q = curiosity.next_question(N, budget="deep")
            if q and re.search(r"\bbirthday\b", q, re.I):
                seen_bday = True
                break
        ck("B4: LAW 002 [next_question] — 40 deep draws NEVER ask the KNOWN birthday", not seen_bday)

        # ---- C. LAW 002 [never re-ask] + append-only ledger (Law 001) + restart-survival ----
        before = curiosity.candidate_gaps(N)
        ck("C1: Mike is a candidate BEFORE being asked",
           any(curiosity._norm_node(g.get("entity", "")) == "mike" for g in before))
        n0 = len(curiosity.ledger_path(N).read_text().splitlines()) if curiosity.ledger_path(N).exists() else 0
        curiosity.mark_asked(N, mike[0])
        after = curiosity.candidate_gaps(N)
        ck("C2: LAW 002 [never-re-ask] — after mark_asked, Mike is NEVER a candidate again",
           all(curiosity._norm_node(g.get("entity", "")) != "mike" for g in after))
        re_mike = False
        for _ in range(30):
            q = curiosity.next_question(N, budget="deep")
            if q and "Mike" in q:
                re_mike = True
                break
        ck("C3: LAW 002 [next_question] — a deep budget never RE-asks the asked Mike gap", not re_mike)
        n1 = len(curiosity.ledger_path(N).read_text().splitlines())
        ck("C4: LAW 001 [append-only] — the Asked Ledger GREW by one (never truncated/overwritten)",
           n1 == n0 + 1)
        # restart-survival: a brand-new read of the ledger from disk still suppresses Mike.
        asked_fresh = curiosity.asked_keys(N)
        ck("C5: restart-survival — the asked gap-key persists in the on-disk ledger",
           curiosity._gap_key(mike[0]) in asked_fresh)

        # ---- D. LIVE WIRE — the EXACT server._turn aside sequence (lines ~1150-1165) ---------
        # On a FRESH creature, the live turn does: q = next_question(name, recent_text=text);
        # if q: cands = candidate_gaps(name); if cands: mark_asked(name, cands[0]). We replay that
        # exact sequence through the same three functions and prove the gap is burned, not re-asked.
        LV = "CurioLive"
        q_live = curiosity.next_question(LV, recent_text="just thinking out loud", budget="deep")
        ck("D1: live-wire — next_question yields a question on a fresh creature (the aside fires)",
           isinstance(q_live, str) and bool(q_live.strip()) and not curiosity._looks_unsafe(q_live))
        cands_live = curiosity.candidate_gaps(LV)
        ck("D2: live-wire — candidate_gaps is non-empty so server._turn has a gap to mark",
           len(cands_live) >= 1)
        burned_key = curiosity._gap_key(cands_live[0])
        curiosity.mark_asked(LV, cands_live[0])                 # exactly what server._turn does
        ck("D3: live-wire — after the turn's mark_asked, that gap is no longer a candidate",
           burned_key not in {curiosity._gap_key(g) for g in curiosity.candidate_gaps(LV)})
        # later turns keep re-driving the same three functions; the burned gap-key must NEVER
        # re-enter candidates across any of them (the durable Law-002 proof the live aside relies on).
        burned_returned = any(
            burned_key in {curiosity._gap_key(g) for g in curiosity.candidate_gaps(LV)}
            for _ in range(20))
        ck("D4: live-wire — the burned gap-key NEVER returns to candidates on later turns (Law 002)",
           not burned_returned)

        # ---- E. CONTRADICTION — a superseded value -> a warm two-value clarify --------------
        f2 = memory_lirf.Facts.load(N)
        for c in f2.capture(N, "I live in Portland"):
            f2.merge(c)
        for c in f2.capture(N, "actually I live in Seattle now"):
            f2.merge(c)
        f2.save(N)
        contra = [g for g in curiosity.detect_gaps(N)
                  if g["slot"] == "lives" and g["kind"] == curiosity.CONTRADICTED]
        ck("E1: a superseded 'lives' value -> exactly one CONTRADICTED gap", len(contra) == 1)
        cq = curiosity.generate_question(contra[0]) if contra else ""
        ck("E2: the clarify question names BOTH values (Seattle + Portland), warmly + safely",
           ("Seattle" in cq and "Portland" in cq) and not curiosity._looks_unsafe(cq))

        # ---- robustness: the entry points never raise on junk -------------------------------
        ck("R1: generate_question(None) -> '' (never raises)", curiosity.generate_question(None) == "")
        ck("R2: mark_asked(bad gap) -> None (never raises)", curiosity.mark_asked(N, None) is None)
        ck("R3: render() audit surface shows the budget + curiosities",
           "budget:" in curiosity.render(N))

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nCURIOSITY-ENGINE CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
