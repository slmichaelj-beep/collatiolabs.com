#!/usr/bin/env python3
"""
certify_wisdom_theory — the Wisdom/Theory engine (Phase D): observations -> grounded THEORIES ->
refinement over time -> long-horizon LESSONS, freeze-safe and grounded (no fabrication).

Where reality.py runs the short belief->prediction->outcome loop, theory.py runs the LONG loop:
generalise many resolved outcomes into theories ("X tends to lead to Y"), refine each as new outcomes
arrive, and crystallise the strongly-supported ones into durable lessons. This certifies that
contract, hermetically + offline:

  A. HONEST EMPTY — no observations -> no theories (induce never fabricates).
  B. INDUCE (grounded) — a corroborated pattern becomes a theory whose confidence is the corroboration
     posterior (3-of-4 -> ~0.67, never a jumped 1.0) and whose support carries the literal
     observations it generalises.
  C. REFINE (over time) — more corroboration raises confidence and firms the theory to 'supported'.
  D. LESSON — a supported theory crystallises into a long-horizon lesson (a condition->action
     heuristic) that carries its failure envelope (where the pattern broke).
  E. FREEZE — a claim about VERA HERSELF is refused at observe() and never folded into a theory; a
     user/world claim is allowed (the control). Theories model the user + world, never Vera's self.
  F. BRIDGE — from_reality() is wired to the certified reality-learning ledger (best-effort, never
     crashes / never invents).

Hermetic: theory.STORE + lerf store redirected to a temp dir; real .anima fingerprinted before/after
and asserted byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
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
    from anima import theory
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("WISDOM / THEORY — observations -> theories -> refinement -> lessons (grounded, freeze-safe)")
    print("=" * 92)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # ---- E (pure): the freeze boundary -----------------------------------------------------
    fp = theory.freeze_proof()
    ck("E1: a claim about Vera herself is refused; a user/world claim passes (control)",
       fp.get("ok") and all(c["refused"] for c in fp["checks"]) and fp.get("control_passes"))

    with _temp_store() as tp:
        saved = getattr(theory, "STORE", None)
        theory.STORE = tp                                  # redirect the observation ledger to temp
        try:
            N = "WisdomCert"
            # ---- A. HONEST EMPTY -----------------------------------------------------------
            ck("A1: no observations -> no theories (induce never fabricates)",
               theory.theories(N) == [] and theory.induce(N) == [])

            # ---- B. INDUCE (grounded) ------------------------------------------------------
            for _ in range(3):
                theory.observe(N, "shipping daily tends to keep momentum",
                               confirmed=True, evidence="shipped daily and momentum held")
            theory.observe(N, "shipping daily tends to keep momentum",
                           confirmed=False, evidence="skipped a few days and momentum dipped")
            ind = theory.induce(N)
            ck("B1: a corroborated pattern becomes a theory grounded in its observations",
               len(ind) >= 1 and bool(ind[0].get("support"))
               and any("held:" in s for s in ind[0]["support"]))
            ck("B2: confidence is the corroboration posterior (3 of 4 -> ~0.67, never a jumped 1.0)",
               0.5 < ind[0].get("confidence", 0) < 0.8 and ind[0].get("held") == 3
               and ind[0].get("observed") == 4)
            tid = ind[0]["id"]

            # ---- C. REFINE (over time) -----------------------------------------------------
            for _ in range(4):
                theory.refine(N, "shipping daily tends to keep momentum",
                              confirmed=True, evidence="shipped daily again, momentum held")
            t = [x for x in theory.theories(N) if x["id"] == tid][0]
            ck("C1: more corroboration raises confidence and firms it to 'supported'",
               t["confidence"] > ind[0]["confidence"] and t["status"] == "supported")

            # ---- D. LESSON -----------------------------------------------------------------
            ls = theory.lessons(N)
            lset = theory.lesson_set(N)
            ck("D1: a supported theory crystallises into a long-horizon lesson with a failure envelope",
               len(ls) >= 1 and len(lset) >= 1 and lset[0]["condition"] and lset[0]["action"]
               and lset[0]["fails_when"])

            # ---- E. FREEZE (in the store) --------------------------------------------------
            ck("E2: observe() refuses a Vera-self claim (reason='freeze', nothing written)",
               theory.observe(N, "Vera is getting wiser over time", confirmed=True).get("reason")
               == "freeze")
            ck("E3: no theory about Vera exists",
               not any("vera" in x["statement"].lower() for x in theory.theories(N)))

            # ---- F. BRIDGE -----------------------------------------------------------------
            ck("F1: from_reality() bridges the reality-learning ledger (best-effort, never crashes)",
               isinstance(theory.from_reality(N), int))
        finally:
            if saved is not None:
                theory.STORE = saved

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nWISDOM-THEORY CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
