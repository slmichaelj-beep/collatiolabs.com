#!/usr/bin/env python3
"""
distill_demo — a narrated walkthrough of the LERF DISTILLATION engine (Phase 3).

Shows, end to end and HERMETICALLY (a throwaway temp store; the real .anima is never
touched, and NO cloud call is made — deterministic stub teachers), how a brand-new skill that
is NOT among the ten hand-authored seeds is *manufactured* by distilling teacher models:

    teacher interview  ->  candidate skill (state=candidate, full provenance)
    several teachers/framings  ->  a COMPETITION between candidates  ->  the winner
    the winner  ->  the REAL Wave-2 gate (promote_skill -> verified; activate_skill -> active)
    -> an ACTIVE, retrievable, fully-provenanced skill (who taught it, when, what tests).

It also shows the GROUNDED-FAILURE guarantee (a teacher whose own test cases fail never goes
active) and the SCOPE guard (distilling identity/inner-life is refused outright).

    python3 scripts/distill_demo.py          # narrated, hermetic, $0 (stub teachers)

This narrates the SAME machinery the live path uses; to prove it against a real paid model:
    python3 -m anima.lerf_distill --live --task "summarize an invoice"   # ONE real call
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from anima import lerf                       # noqa: E402
from anima import lerf_distill as distill    # noqa: E402


def _rule(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def main() -> int:
    task = "summarize an invoice and extract what I owe and when"

    # FULLY HERMETIC: redirect every store the distill+gate path may write to one temp dir, and
    # restore after. The real .anima is asserted byte-unchanged at the end. NO cloud is called —
    # the teachers are deterministic stubs, so this costs $0.
    real = lerf.STORE if lerf.STORE.is_absolute() else (Path.cwd() / lerf.STORE)
    fp_before = distill._footprint(real)

    td = tempfile.mkdtemp(prefix="distill-demo-")
    targets = distill._redirect_targets()
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    for (m, a) in targets:
        if getattr(m, a, None) is not None:
            setattr(m, a, Path(td))
    try:
        nm = "demo"

        _rule("LERF DISTILLATION — manufacturing skill #11 (a finance/invoice skill, NOT a seed)")
        print("The ten seed skills are hand-authored. This one is DISTILLED from teachers.\n"
              "Two teachers compete, each under two framings — four interviews in all.\n"
              "Teacher A is a strong practitioner; Teacher B answers thinly (a one-line stub).")

        strong = distill.StubTeacher(provider="anthropic", model="claude-sonnet-4-6")
        thin = distill.StubTeacher(provider="openai", model="gpt-4o-mini", degrade=True)

        trace = distill.distill(task, [strong, thin], distill.DEMO_INVOICE_DOC, name=nm)

        _rule("THE DISTILLATION TRACE")
        print(distill.render_trace(trace))

        _rule("THE NOW-ACTIVE SKILL — inspectable, unlike a weight tensor")
        got = lerf.retrieve_skills("what do I owe on this invoice and when is it due", name=nm)
        if got:
            print(lerf.explain_skill(got[0], name=nm))

        _rule("GROUNDED FAILURE — a teacher whose own tests fail NEVER becomes active")
        print("A teacher offers an invoice skill but with a test case it cannot pass\n"
              "(expects a token absent from the input). The gate refuses it:\n")
        liar = distill.StubTeacher(provider="openai", model="gpt-4o-mini", bad_tests=True)
        bad = distill.distill("summarize a vendor invoice", [liar],
                              distill.DEMO_INVOICE_DOC, name=nm)
        print(f"  outcome : {'ACTIVE' if bad['ok'] else 'NOT ACTIVATED'}")
        print(f"  reason  : {bad['reason']}")
        if bad.get("winner"):
            st = lerf._get(nm, bad["winner"]["skill_id"]).get("state")
            print(f"  on disk : the rejected candidate is state={st!r} (kept for provenance, "
                  f"never retrievable)")

        _rule("SCOPE GUARD — distilling identity / inner life is refused outright")
        print("Distillation is for TASK procedures only. An identity 'task' is refused before\n"
              "any teacher is interviewed (frozen architecture / #1 product rule):\n")
        idt = distill.distill("learn who you really are and how you feel inside", [strong],
                              distill.DEMO_INVOICE_DOC, name=nm)
        print(f"  refused : {idt['ok'] is False}   reason: {idt['reason']}")

    finally:
        for (m, a, old) in saved:
            if old is not None:
                setattr(m, a, old)
        shutil.rmtree(td, ignore_errors=True)

    fp_after = distill._footprint(real)
    _rule("HERMETIC PROOF")
    print(f"  real .anima byte-UNCHANGED across this demo : {fp_before == fp_after}")
    print(f"  cloud calls made                            : 0 (deterministic stub teachers, $0)")
    return 0 if fp_before == fp_after else 1


if __name__ == "__main__":
    raise SystemExit(main())
