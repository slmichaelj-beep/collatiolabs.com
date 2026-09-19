#!/usr/bin/env python3
"""
certify_organ_verifier — ORGAN 4: the critic that checks an answer against its evidence BEFORE
it ships. The last gate between the mouth and the user, and a SAFETY rail: it must FLAG a draft
that contradicts / confabulates / disclaims a held fact, and must PASS a grounded one — all
DETERMINISTICALLY (substring / value-contradiction / heuristic, NO model on the critical path),
and it must NEVER raise into a turn (a crashing gate fails OPEN). This certifies that contract
through the SAME function the server's _turn gate calls (anima.organs.verifier.verify):

  A. CONTRADICTION CAUGHT (the unforgivable companion failure — the WRONG birthday). Evidence
     holds birthday 1990-06-11; the draft says "June 14th" -> override=True (suppress/regenerate),
     issue tagged 'contradiction', confidence < 0.2 — proven from BOTH a canonical Memory dict AND
     a raw LIRF row (shape-agnostic). The SAME date in a different spelling is NOT a contradiction.
  B. CONFABULATION CAUGHT (unsupported personal claim). With NO evidence and nothing in the
     question, an invented birthday / dog name -> override=True, issue 'unsupported_personal_claim'.
  C. IGNORED KNOWN FACT CAUGHT (the symmetric partner — the WRONG value's twin: the MISSING value).
     Evidence holds a KNOWN birthday (Sept 14, active, conf 0.97); the question asks for it; the
     draft disclaims it ("I don't have your birthday") OR silently omits it OR is an incoherent
     disclaimer-that-also-states-it -> override=True, issue 'ignored_known_fact:birthday'.
  D. GROUNDED / HONEST PASSES (no false fire). A correct stored-fact answer, a claim the user gave
     in the question, a claim backed by a real cap_note, a normal non-personal reply, an honest
     disclaimer of a GENUINELY-UNKNOWN trait, and the known value stated across spellings all PASS
     (override=False, ok=True).
  E. GUARDS + ROBUSTNESS. A CONTESTED (needs_reconfirm) and a sub-0.85 ([SENSE]) fact are demoted
     out of KNOWN so hedging them is honest; an off-topic omission is never flagged; a list-valued
     trait is never a contradiction; None/garbage evidence is tolerated (fails OPEN); the
     override-implies-not-ok invariant holds; the module-level verify() matches the organ method.
  F. SELFTEST — anima/organs/verifier.py --selftest passes in-process (the organ's isolation proof).

The verdict proven here is the EXACT one server._turn gates on (and that drives its regenerate-
then-floor enforcement); the optional model pass + the regenerate leg need a live model and are
not exercised (see known_gaps). verify() is pure + stateless, but per the cert discipline the whole
exercise runs inside _temp_store() and the real .anima is fingerprinted before/after and asserted
byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
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


def _mem(subject: str, predicate: str, value, confidence: float = 0.97) -> dict:
    """A canonical-Memory-shaped evidence dict (the bus shape an organ emits onto OBSERVATION)."""
    return {"id": "f_cert", "type": "value", "subject": subject, "predicate": predicate,
            "value": value, "confidence": confidence, "sources": ["organ_verifier_cert"],
            "support": [], "updated": "2026-01-01T00:00:00Z", "lirf": ""}


def _row(trait: str, value, confidence: float = 0.97, entity: str = "you") -> dict:
    """A raw LIRF-row-shaped evidence dict (the memory_lirf.Facts.about()/.lookup() shape)."""
    return {"id": "f_row", "entity": entity, "trait": trait, "value": value,
            "confidence": confidence, "support": 3, "status": "active"}


def main() -> int:
    from anima.organs import verifier as V
    from anima.organs.verifier import verify, Verdict   # the EXACT module-level entry server._turn calls

    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("ORGAN VERIFIER (ORGAN 4) — the critic that checks an answer vs its evidence BEFORE it ships")
    print("=" * 92)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # verify() is a PURE, store-free function; still, per the cert discipline we exercise it inside
    # _temp_store() (every store redirected) and assert the real .anima is byte-identical after.
    with _temp_store():
        # ---- A. CONTRADICTION — the WRONG birthday is caught + override (suppress/regenerate) ----
        ev_bday = [_mem("you", "birthday", "1990-06-11")]
        a = verify("when's my birthday?", "Your birthday is June 14th!", ev_bday)
        ck("A1: a draft that CONTRADICTS the stored birthday is caught (not ok)", a.ok is False)
        ck("A2: the contradiction sets override=True (suppress/regenerate)", a.override is True)
        ck("A3: the issue is tagged 'contradiction'",
           any(str(i).startswith(Verdict.CONTRADICTION) for i in a.issues))
        ck("A4: a contradicted known fact scores very low confidence", a.confidence < 0.2)
        a_row = verify("when's my birthday?", "Your birthday is June 14th!", [_row("birthday", "June 11")])
        ck("A5: the contradiction is caught from a RAW LIRF ROW too (shape-agnostic)",
           a_row.override is True)
        a_same = verify("when's my birthday?", "Your birthday is June 11, 1990.", ev_bday)
        ck("A6: the SAME date in a different spelling is NOT a contradiction (passes)",
           a_same.ok is True and a_same.override is False)

        # ---- B. CONFABULATION — an unsupported HARD personal specific is caught + override -------
        b = verify("do you remember my birthday?", "Of course — your birthday is March 3rd!", [])
        ck("B1: a confabulated personal DATE (not in evidence/question) is caught (not ok)",
           b.ok is False and b.override is True)
        ck("B2: the issue is tagged 'unsupported_personal_claim'",
           any(str(i).startswith(Verdict.UNSUPPORTED_PERSONAL) for i in b.issues))
        b2 = verify("what's my dog's name?", "Your dog's name is Biscuit!", [])
        ck("B3: a confabulated personal NAME is likewise caught (override)", b2.override is True)

        # ---- C. IGNORED KNOWN FACT — the symmetric partner: a held fact asked-for but denied -----
        known_bday = [_mem("you", "birthday", "September 14")]    # active, conf 0.97 -> KNOWN
        c1 = verify("when's my birthday?", "I don't have your birthday saved, sorry!", known_bday)
        ck("C1: DISCLAIMING a KNOWN birthday that was asked for is caught (not ok)", c1.ok is False)
        ck("C2: the ignored-known disclaimer sets override=True", c1.override is True)
        ck("C3: the issue is tagged 'ignored_known_fact:birthday' (the trait the turn routed)",
           any(str(i).startswith(Verdict.IGNORED_KNOWN_FACT + ":birthday") for i in c1.issues))
        ck("C4: a denied known fact scores very low confidence (same tier as a contradiction)",
           c1.confidence < 0.2)
        c_silent = verify("when's my birthday?",
                          "Aww, birthdays! Tell me, how do you like to celebrate?", known_bday)
        ck("C5: a SILENT OMISSION of the known value (warm deflection, no value) is also caught",
           c_silent.override is True)
        c_incoh = verify("when's my birthday?",
                         "I don't have your birthday saved, so I can't tell you the exact date. "
                         "But I do remember that September 14th is a special day for us!", known_bday)
        ck("C6: an INCOHERENT disclaimer that ALSO states the value still overrides (reads as not-knowing)",
           c_incoh.override is True)
        c_row = verify("when's my birthday?", "I don't know your birthday.", [_row("birthday", "September 14")])
        ck("C7: the ignored-known fact is caught from a RAW LIRF ROW too (shape-agnostic)",
           c_row.override is True)

        # ---- D. GROUNDED / HONEST — the good cases PASS untouched (no false fire) ----------------
        d1 = verify("when's my birthday?", "Your birthday is June 11th — I remember!", ev_bday)
        ck("D1: a correct evidence-grounded answer PASSES (ok, no override, no issues)",
           d1.ok is True and d1.override is False and d1.issues == [])
        ck("D2: the grounded answer has high confidence", d1.confidence >= 0.8)
        d_known = verify("when's my birthday?", "Your birthday is September 14th — I remember!", known_bday)
        ck("D3: STATING the known birthday raises no ignored-known issue (no false fire)",
           d_known.override is False
           and not any(str(i).startswith(Verdict.IGNORED_KNOWN_FACT) for i in d_known.issues))
        ck("D4: the known value is satisfied ACROSS spellings (Sept 14 / 9/14 / the 14th)",
           all(verify("when's my birthday?", f"Of course — it's {s}!", known_bday).override is False
               for s in ("Sept 14", "9/14", "the 14th of September", "1990-09-14")))
        d_q = verify("my birthday is June 11 by the way", "Got it — your birthday is June 11!", [])
        ck("D5: a claim the user SUPPLIED in the question is grounded (passes)", d_q.ok is True)
        d_cap = verify("what's on my calendar?", "You have a dentist appointment on June 12.", [],
                       cap_note="[capability — read OK. ACTUAL events: dentist on June 12 at 3pm]")
        ck("D6: a claim backed by a real cap_note (fetched data) is grounded (passes)", d_cap.ok is True)
        d_chat = verify("tell me a joke",
                        "Why did the scarecrow win an award? Because he was outstanding in his field!", [])
        ck("D7: a normal NON-personal reply passes untouched (nothing to verify)",
           d_chat.ok is True and d_chat.override is False and d_chat.issues == [])
        d_unknown = verify("when's my birthday?", "I don't have your birthday yet — when is it?", [])
        ck("D8: an HONEST disclaimer of a GENUINELY-UNKNOWN birthday PASSES (rule inert, no KNOWN row)",
           d_unknown.ok is True and d_unknown.override is False
           and not any(str(i).startswith(Verdict.IGNORED_KNOWN_FACT) for i in d_unknown.issues))

        # ---- E. GUARDS + ROBUSTNESS — the rule never over-fires; never raises into a turn --------
        contested = _row("birthday", "September 14")
        contested["needs_reconfirm"] = True
        e_cont = verify("when's my birthday?",
                        "I'm not totally sure of your birthday anymore — remind me?", [contested])
        ck("E1: a CONTESTED (needs_reconfirm) fact is demoted out of KNOWN -> hedging it is honest",
           e_cont.override is False)
        soft = _row("birthday", "September 14", confidence=0.6)
        e_soft = verify("when's my birthday?", "I don't have your birthday down.", [soft])
        ck("E2: a sub-0.85 ([SENSE]) fact is below the KNOWN bar -> disclaiming it is honest",
           e_soft.override is False)
        e_off = verify("how's the weather where you are?",
                       "I can't really see outside, but I hope it's nice!", known_bday)
        ck("E3: an OFF-TOPIC omission of a known fact is never flagged (the question routes nowhere)",
           e_off.override is False)
        e_list = verify("what do I like?", "You love sushi.", [_row("likes", ["pizza", "ramen"])])
        ck("E4: a LIST-valued trait can never be 'contradicted' (likes are additive)",
           e_list.override is False)
        ck("E5: None evidence is tolerated and fails OPEN (a crashing gate must not break a turn)",
           verify("hi", "hello there", None).ok is True)
        ck("E6: garbage evidence items are dropped, not fatal",
           verify("hi", "hello", [None, 42, "nope", {"no_value": 1}]).ok is True)
        ck("E7: an empty draft is a clean pass", verify("hi", "", ev_bday).ok is True)
        ck("E8: override ALWAYS implies not-ok (the load-bearing invariant)",
           all(v.ok is False for v in (a, a_row, b, b2, c1, c_silent, c_incoh, c_row) if v.override))
        ck("E9: the module-level verify() matches the organ method (the named entry point)",
           V.Verifier().verify("when's my birthday?", "Your birthday is June 14th!", ev_bday).override
           == verify("when's my birthday?", "Your birthday is June 14th!", ev_bday).override is True)
        vd = d1.as_dict()
        ck("E10: Verdict.as_dict exposes exactly the 4 keys (the output contract)",
           set(vd.keys()) == {"ok", "confidence", "issues", "override"})

        # ---- F. SELFTEST — the organ's own isolation proof (in-process) --------------------------
        rc = V._selftest()
        ck("F1: anima/organs/verifier.py --selftest passes in-process", rc == 0)

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nORGAN-VERIFIER CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
