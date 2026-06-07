#!/usr/bin/env python3
"""
certify_lerf_distillation — the LERF DISTILLATION verify/promote gate: a teacher's opaque competence
is decanted into a CERTIFIED, retrievable cognitive object ONLY when it actually passes the real
Wave-2 gate — and a teacher whose own test cases FAIL never becomes active.

The distillation factory turns skill #11, #12, … into structured skills WITHOUT a human writing them:
interview a teacher -> lower the answer into a lerf candidate -> run a transparent COMPETITION ->
push the winner through the REAL gate (lerf.promote_skill schema+unit+adversarial+regression ->
verified; lerf.activate_skill on a MEASURED compression ratio -> active). This certifies that
verify/promote gate DETERMINISTICALLY (the deterministic StubTeacher — NO live teacher, NO cloud, NO
network, NO key) through the SAME functions the engine's distill() and lerf_grow run:

  A. SCOPE FREEZE — _off_scope_reason refuses an identity/inner-life "task" (and passes a plain task
     verb); distill() on an identity task mints NO candidate (the #1 product rule, enforced before any
     teacher is paid).
  B. INTERVIEW -> CANDIDATE — interview(StubTeacher) parses to a structured spec, and
     candidate_from_interview lowers it into a real lerf SKILL in state='candidate' that is NOT yet
     retrievable (candidate != active) and carries its full PROVENANCE (who taught it + the verbatim
     test cases it will be certified against).
  C. THE VERIFY/PROMOTE GATE (the heart) — distill() runs a competition (substantive candidate beats a
     one-line stub) and certifies the winner THROUGH THE REAL GATE: every phase (schema+unit+
     adversarial+regression) ran ok, activation used a MEASURED ratio >= the floor, the result is
     final_state=ACTIVE, and the now-active skill is RETRIEVABLE on a natural user task — with full
     provenance (who-taught + what-tests + the measured activation ratio) on the active object.
  D. GROUNDED REJECTION — a teacher whose own test cases FAIL is NOT activated: distill() returns
     ok=False with an explicit reason, no skill is left active, and the failed candidate is REJECTED on
     disk (provenance kept) and never retrievable. The gate cannot be tricked into certifying a skill
     that does not work.

Hermetic + offline: lerf/memory_lirf/constitution stores via _temp_store, PLUS reliability.DEFAULT_STORE
and cloud.STORE redirected here (the gate's guarded-load + any cloud probe), all to one temp dir; the
real .anima is fingerprinted before/after and asserted byte-identical. NO cloud teacher is ever
constructed (StubTeacher only). Exit 0 == CERTIFIED, 1 == FAIL.
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


def main() -> int:
    from anima import lerf_distill as D, lerf
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("LERF DISTILLATION — interview -> candidate -> the REAL verify/promote gate -> active (or rejected)")
    print("=" * 98)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # ---- A0. SCOPE FREEZE is a pure function — exercise it outside the store too. ----------------
    ck("A0: _off_scope_reason refuses an identity/inner-life task and passes a plain task verb",
       D._off_scope_reason("learn who you really are and how you feel inside") is not None
       and D._off_scope_reason("are you conscious or sentient?") is not None
       and D._off_scope_reason("summarize an invoice and extract what I owe") is None)

    with _temp_store() as tp:
        # _temp_store redirects lerf/memory_lirf/constitution; also redirect the two stores it does
        # NOT cover that the gate's guarded-load / any cloud probe could touch (mirrors
        # certify_personal_intelligence.py), and restore in finally.
        extra = []
        for modname, attr in (("anima.reliability", "DEFAULT_STORE"), ("anima.cloud", "STORE")):
            try:
                m = __import__(modname, fromlist=["_"])
                extra.append((m, attr, getattr(m, attr, None)))
                if getattr(m, attr, None) is not None:
                    setattr(m, attr, tp)
            except Exception:
                pass
        try:
            N = "DistillCert_" + secrets.token_hex(3)
            TASK = "summarize an invoice and extract what I owe and when"

            # ---- A. SCOPE FREEZE end-to-end: an identity task mints NO candidate ------------------
            id_trace = D.distill("learn who you really are and how you feel inside",
                                 [D.StubTeacher()], D.DEMO_INVOICE_DOC, name=N)
            ck("A1: distill() on an identity task is refused — no candidate, off-scope reason",
               id_trace.get("ok") is False and not id_trace.get("candidates")
               and "off-scope" in id_trace.get("reason", ""))

            # ---- B. INTERVIEW -> CANDIDATE (provenance-stamped, not yet retrievable) --------------
            iv = D.interview(D.StubTeacher(), TASK, D.FRAMINGS[0])
            ck("B1: interview(StubTeacher) parses to a structured spec with steps + >=2 test cases",
               iv.get("ok") and iv.get("steps") and len(iv.get("test_cases")) >= 2)
            cand = D.candidate_from_interview(iv, TASK, N)
            ck("B2: candidate_from_interview lowers it into a lerf SKILL in state='candidate'",
               cand and cand.get("state") == lerf.CANDIDATE and cand.get("type") == "skill")
            ck("B3: the candidate is NOT yet retrievable (candidate != active — the gate gates use)",
               all(s.get("id") != cand["id"] for s in lerf.retrieve_skills("invoice", name=N)))
            prov0 = D.provenance(cand["id"], name=N)
            ck("B4: provenance is stamped on the candidate (who-taught + the verbatim test cases)",
               prov0.get("taught_by_provider") == "stub"
               and prov0.get("distilled_for_task") == TASK
               and len(prov0.get("certified_against", [])) >= 2)

            # ---- C. THE VERIFY/PROMOTE GATE (the heart): competition -> real gate -> ACTIVE -------
            strong = D.StubTeacher(provider="strong", model="good-v1")
            weak = D.StubTeacher(provider="weak", model="thin-v1", degrade=True)
            trace = D.distill(TASK, [strong, weak], D.DEMO_INVOICE_DOC, name=N)
            ck("C1: a competition ran (>=2 candidates) and the SUBSTANTIVE one beat the one-line stub",
               len(trace.get("candidates", [])) >= 2
               and trace["winner"]["provider"] == "strong"
               and trace["winner"]["clarity"] > min(c["clarity"] for c in trace["candidates"]))
            cert = trace.get("certification") or {}
            phases = (cert.get("gate") or {}).get("phases", {})
            ck("C2: the REAL gate ran — schema+unit+adversarial+regression ALL ok (not reimplemented)",
               all(phases.get(p, {}).get("ok") for p in
                   ("schema", "unit", "adversarial", "regression")))
            ck("C3: activation used a MEASURED compression ratio >= the floor",
               (cert.get("benchmark") or {}).get("ratio", 0) >= lerf.ACTIVATION_MIN_RATIO)
            ck("C4: the winner is CERTIFIED to ACTIVE (the only retrievable state)",
               trace.get("ok") is True and cert.get("final_state") == lerf.ACTIVE)
            got = lerf.retrieve_skills("summarize this invoice and tell me what I owe", name=N)
            ck("C5: the now-active distilled skill is RETRIEVABLE on a natural user task",
               bool(got) and got[0]["id"] == trace["winner"]["skill_id"]
               and got[0]["domain"] == "finance" and "invoice" in got[0]["name"])
            prov = trace.get("provenance") or {}
            ck("C6: the active skill carries full provenance (who-taught + what-tests + measured ratio)",
               prov.get("taught_by_provider") == "strong"
               and len(prov.get("certified_against", [])) >= 2
               and prov.get("activation") and "activated:ratio=" in (prov.get("activation") or ""))

            # ---- D. GROUNDED REJECTION: failing test cases -> NOT activated, REJECTED, never used --
            bad = D.StubTeacher(provider="liar", model="bad-tests-v1", bad_tests=True)
            bad_trace = D.distill("summarize a different invoice variant", [bad],
                                  D.DEMO_INVOICE_DOC, name=N)
            ck("D1: a teacher whose own test cases FAIL is NOT activated (no fabricated success)",
               bad_trace.get("ok") is False and bad_trace.get("active_skill") is None
               and ("reject" in bad_trace.get("reason", "").lower()
                    or "not activated" in bad_trace.get("reason", "").lower()))
            if bad_trace.get("winner"):
                rid = bad_trace["winner"]["skill_id"]
                ck("D2: the failed candidate is REJECTED on disk (its provenance is kept, not erased)",
                   lerf._get(N, rid)["state"] == lerf.REJECTED)
                ck("D3: the rejected candidate is NEVER retrievable (the gate truly gates use)",
                   all(s.get("id") != rid for s in lerf.retrieve_skills("invoice variant", name=N)))
            else:
                ck("D2: a rejected candidate exists to inspect", False)

            # ---- E. COST DISCIPLINE: the whole cert made ZERO cloud calls ($0, no key touched) ----
            ck("E1: no cloud spend file was written (StubTeacher only — $0, no paid call)",
               not (tp / "spend.json").exists())
            ck("E2: no brain.json was written (the cert never read or touched an API key)",
               not (tp / "brain.json").exists())
        finally:
            for m, attr, old in extra:
                if old is not None:
                    setattr(m, attr, old)

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nLERF-DISTILLATION CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
