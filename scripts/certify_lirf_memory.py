#!/usr/bin/env python3
"""
certify_lirf_memory — the durable personal-fact ledger (LIRF): capture WITH provenance, recall
across a restart, and USE in a LIVE deterministic turn (no model), with the honesty wall + the
identity-freeze schema invariant intact.

LIRF is the hard, queryable memory-of-you: every belief the user states is an append-only row with
a stable id, a confidence, the verbatim evidence that set it, and a dated source. This certifies the
end-to-end LIVE user path through the SAME functions server._turn's known-fact seam calls:

  A. CAPTURE IS DURABLE + CARRIES PROVENANCE — memory_lirf.capture("LirfCert","my birthday is
     June 12") writes exactly ONE row whose entity is the user ("you"), whose value carries "June 12",
     which keeps the verbatim evidence snippet, stamps a dated source, enters >= CONF_NEW, and lands
     in .anima/LirfCert.lirf.json on disk (not just memory).
  B. RESTART SURVIVAL + RECALL WITH PROVENANCE — a FRESH Facts.load() (the restart) recalls the row
     via lookup(SELF,"birthday") with the value AND provenance preserved; memory_lirf.fact_note
     surfaces the actual stored value + its provenance for a known-fact question.
  C. USED IN A LIVE DETERMINISTIC TURN (the headline) — we replicate server._turn's known-fact seam,
     model-free: spine.fact_question("when is my birthday?") routes to "birthday"; the loaded row is
     spine.is_known_fact True; spine.answer_from_fact assembles the warm reply; mouth.final_output_gate
     ships it CONTAINING "June 12" and free of any hedge/disclaimer. THIS is the live user-facing effect.
  D. HONESTY WALL (no fabrication) — a never-captured trait (phone) -> lookup None -> spine.answer_from_fact
     refuses (None) and spine.honest_unknown admits + asks, asserting NO value.
  E. INJECTION INTO EVERY TURN (Organ 3) — organs.router.select_facts(name,"when is my birthday?")
     returns the birthday row in its relevant set + a block string carrying the value (the per-turn
     fact-injection path).
  F. ENTITY INVARIANT (identity freeze, schema level) — merging a candidate tagged entity="vera" folds
     onto SELF: a belief about Vera can NEVER enter this store as a user fact.
  G. CORRECTION + HISTORY (provenance never deleted) — a corrected birthday supersedes newest-wins,
     and the displaced value is kept in history[] so the correction is provable.
  H. RETRACTION — THE USER OWNS DELETION (the 2026-06-09 live-drive gap) — a BARE "Forget my
     favorite color." (value NOT restated) must (1) read as RETRACTION INTENT in the spine seam
     (retraction_intent routes it; fact_question REFUSES it, so the canned recall "teal's your
     favorite — I remember." can never ship on a forget-turn), (2) be acknowledged WITHOUT reciting
     the stored value (acknowledge_forget), and (3) actually retract the active row via the SAME
     capture->merge path a restated retraction takes — kept on disk as status='retracted' for audit,
     never silently no-op'd. Restated-value retraction ("Forget that my favorite color is X.") still
     works unweakened, a forget aimed at an EMPTY slot creates nothing, and a recall turn that merely
     contains a retraction-ish cue ("never mind that — what's my favorite color?") retracts NOTHING.

Hermetic + offline (NO model, NO network): memory_lirf/spine/server stores are redirected by
_temp_store; reliability.DEFAULT_STORE is redirected here (its guarded-load/backup side effects).
The real .anima is fingerprinted before/after and asserted byte-identical. Exit 0 == CERTIFIED,
1 == FAIL.
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
    from anima import memory_lirf, spine, mouth
    from anima.memory_lirf import Facts, SELF
    from anima.organs import router
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("LIRF MEMORY — capture WITH provenance -> recall across restart -> USED in a live "
          "deterministic turn")
    print("=" * 98)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    with _temp_store() as tp:
        # reliability uses DEFAULT_STORE (not STORE) and is not in _temp_store's set; redirect it so a
        # guarded-load backup/approved-loss side effect lands in the temp dir, never the real .anima.
        extra = []
        try:
            import anima.reliability as _rel
            extra.append((_rel, "DEFAULT_STORE", getattr(_rel, "DEFAULT_STORE", None)))
            _rel.DEFAULT_STORE = tp
        except Exception:
            pass
        try:
            N = "LirfCert"
            Q = "when is my birthday?"

            # ---- A. CAPTURE IS DURABLE + CARRIES PROVENANCE ----------------------------
            touched = memory_lirf.capture(N, "my birthday is June 12")
            bday = next((r for r in touched if r.get("trait") == "birthday"), None)
            ck("A1: capture writes a birthday row from the user's words",
               bday is not None and "june 12" in str(bday.get("value", "")).lower())
            ck("A2: the row's entity is the USER ('you') — the schema invariant",
               bday is not None and bday.get("entity") == SELF)
            ck("A3: the row keeps the VERBATIM evidence snippet that set it (provenance)",
               bool(bday and bday.get("evidence")) and "june 12" in str(bday.get("evidence", "")).lower())
            ck("A4: the row stamps a dated source + enters at >= CONF_NEW (a stated fact)",
               bool(bday and bday.get("source"))
               and float(bday.get("confidence", 0)) >= memory_lirf.CONF_NEW)
            lirf_path = tp / f"{N}.lirf.json"
            ck("A5: the fact is DURABLE on disk (.anima/LirfCert.lirf.json exists)", lirf_path.is_file())

            # ---- B. RESTART SURVIVAL + RECALL WITH PROVENANCE --------------------------
            # A fresh load() reads ONLY from disk — this is the restart.
            reloaded = Facts.load(N)
            row = reloaded.lookup(SELF, "birthday")
            ck("B1: after a fresh load (restart) the row is recalled by lookup(SELF,'birthday')",
               row is not None and "june 12" in str(row.get("value", "")).lower())
            ck("B2: provenance survived the round-trip (evidence + source still on the row)",
               bool(row and row.get("evidence") and row.get("source")))
            note = memory_lirf.fact_note(N, Q)
            ck("B3: fact_note surfaces the ACTUAL stored value + provenance for the question",
               bool(note) and "june 12" in note.lower() and "provenance" in note.lower())

            # ---- C. USED IN A LIVE DETERMINISTIC TURN (the headline) -------------------
            # This is server._turn's known-fact seam, reproduced model-free:
            #   fact_question -> Facts.lookup -> is_known_fact -> answer_from_fact -> final_output_gate.
            trait = spine.fact_question(Q)
            ck("C1: a clean 'when is my birthday?' routes to the 'birthday' trait (fact_question)",
               trait == "birthday")
            kf_row = Facts.load(N).lookup(SELF, trait) if trait else None
            ck("C2: the recalled row clears the [KNOWN] bar (spine.is_known_fact)",
               kf_row is not None and spine.is_known_fact(kf_row) is True)
            raw = spine.answer_from_fact(Q, kf_row, name=N) if kf_row else None
            shipped = mouth.final_output_gate(raw) if raw else None
            ck("C3: answer_from_fact assembles a model-free reply containing the stored value",
               bool(raw) and "june 12" in raw.lower())
            ck("C4: the reply ships through the shared #1-rule final gate STILL carrying 'June 12'",
               bool(shipped) and "june 12" in shipped.lower())
            low = (shipped or "").lower()
            ck("C5: the shipped reply does NOT hedge or disclaim a fact she holds",
               not any(p in low for p in ("i don't have", "not on record", "i think it",
                                          "if i remember", "i'm not sure", "i don't know")))

            # ---- D. HONESTY WALL (no fabrication) --------------------------------------
            # A trait that was NEVER captured must not be invented. lookup is None; answer_from_fact
            # refuses; honest_unknown admits + asks and asserts no value.
            PHONE_Q = "what is my phone number?"
            no_row = Facts.load(N).lookup(SELF, "phone")
            ck("D1: a never-captured trait (phone) has NO row on record", no_row is None)
            ck("D2: answer_from_fact REFUSES to assert a value it doesn't have (returns None)",
               spine.answer_from_fact(PHONE_Q, no_row, name=N) is None)
            hon = spine.honest_unknown(PHONE_Q, name=N)
            ck("D3: honest_unknown admits + asks (no fabricated number)",
               bool(hon) and "phone" in hon.lower()
               and not any(ch.isdigit() for ch in hon))

            # ---- E. INJECTION INTO EVERY TURN (Organ 3) --------------------------------
            sel_rows, block = router.select_facts(N, Q)
            ck("E1: Organ-3 select_facts injects the birthday row for this question",
               any(r.get("trait") == "birthday" for r in sel_rows))
            ck("E2: the injectable fact-block carries the stored value",
               bool(block) and "june 12" in block.lower())

            # ---- F. ENTITY INVARIANT (identity freeze at the schema level) -------------
            f2 = Facts.load(N)
            vera_row = f2.merge({"trait": "favorite_color", "value": "violet",
                                 "entity": "vera", "evidence": "Vera likes violet"})
            ck("F1: a candidate tagged entity='vera' folds onto the USER ('you') — never enters as Vera",
               vera_row.get("entity") == SELF)
            ck("F2: NO row in the ledger is ever attributed to the creature ('vera'/'assistant')",
               all(r.get("entity") != "vera" and r.get("entity") != "assistant" for r in f2.rows))

            # ---- G. CORRECTION + HISTORY (provenance never deleted) --------------------
            f3 = Facts.load(N)
            f3.merge({"trait": "birthday", "value": "July 4",
                      "evidence": "actually my birthday is July 4", "correction": True})
            f3.save(N)
            after = Facts.load(N).lookup(SELF, "birthday")
            ck("G1: a correction supersedes newest-wins (the active value is now July 4)",
               after is not None and "july 4" in str(after.get("value", "")).lower())
            ck("G2: the displaced value is KEPT in history[] (correction is provable, never deleted)",
               any("june 12" in str(h.get("value", "")).lower() for h in after.get("history", [])))

            # ---- H. RETRACTION — the user owns deletion (2026-06-09 live-drive gap) ----
            FORGET = "Forget my favorite color."
            memory_lirf.capture(N, "my favorite color is teal")
            ck("H1: precondition — favorite_color='teal' is active on record",
               (lambda r: r is not None and "teal" in str(r.get("value", "")).lower())(
                   Facts.load(N).lookup(SELF, "favorite_color")))
            # the seam reads the forget as RETRACTION, never recall
            ck("H2: retraction_intent routes the bare forget to its trait (no value restated)",
               spine.retraction_intent(FORGET) == "favorite_color")
            ck("H3: fact_question REFUSES a forget-turn — the canned recall can NEVER fire on it",
               spine.fact_question(FORGET) is None)
            ack = spine.acknowledge_forget(FORGET, name=N, on_record=True)
            shipped_ack = mouth.final_output_gate(ack) if ack else None
            ck("H4: the shipped ack confirms the forget WITHOUT reciting the stored value",
               bool(shipped_ack) and "teal" not in shipped_ack.lower()
               and "favorite color" in shipped_ack.lower()
               and "i remember" not in shipped_ack.lower())
            # the same turn's normal LIRF capture performs the actual retraction
            memory_lirf.capture(N, FORGET)
            ck("H5: a BARE retraction retracts the active row (the forget is no longer a no-op)",
               Facts.load(N).lookup(SELF, "favorite_color") is None)
            ck("H6: the retracted row is KEPT on disk for audit (status='retracted', not deleted)",
               any(r.get("trait") == "favorite_color" and r.get("status") == "retracted"
                   for r in Facts.load(N).rows))
            # the second live-drive phrasing
            memory_lirf.capture(N, "my favorite color is green")
            memory_lirf.capture(N, "Please forget my favorite color — delete it from your memory.")
            ck("H7: 'Please forget my favorite color — delete it from your memory.' retracts too",
               Facts.load(N).lookup(SELF, "favorite_color") is None)
            # restated-value retraction is UNWEAKENED
            memory_lirf.capture(N, "my favorite color is blue")
            memory_lirf.capture(N, "Forget that my favorite color is blue.")
            ck("H8: restated-value retraction ('forget that my X is Y') still retracts (unweakened)",
               Facts.load(N).lookup(SELF, "favorite_color") is None)
            # a forget aimed at an EMPTY slot creates nothing and claims nothing
            empty_touch = memory_lirf.capture(N, "Forget my anniversary.")
            ack_empty = spine.acknowledge_forget("Forget my anniversary.", name=N, on_record=False)
            ck("H9: a forget for an EMPTY slot writes NOTHING (a forget can never create a row)",
               empty_touch == [] and Facts.load(N).lookup(SELF, "anniversary") is None)
            ck("H10: ...and its ack honestly says there is nothing to forget (no false deletion claim)",
               bool(ack_empty) and "nothing" in ack_empty.lower())
            # a recall turn that merely CONTAINS a retraction-ish cue retracts NOTHING
            memory_lirf.capture(N, "my favorite color is red")
            ck("H11: 'never mind that — what's my favorite color?' carries NO retraction intent",
               spine.retraction_intent("never mind that — what's my favorite color?") is None)
            memory_lirf.capture(N, "never mind that — what's my favorite color?")
            ck("H12: ...and a capture pass over it leaves the row ACTIVE (recall never deletes)",
               (lambda r: r is not None and "red" in str(r.get("value", "")).lower())(
                   Facts.load(N).lookup(SELF, "favorite_color")))
        finally:
            for m, attr, old in extra:
                if old is not None:
                    setattr(m, attr, old)

    fp_after = _footprint(real_anima)
    ck("I1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nLIRF-MEMORY CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
