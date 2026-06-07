#!/usr/bin/env python3
"""
certify_lerf_router — the LERF Runtime Router: the cheapest-sufficient LADDER + the grounded
VERIFICATION gate, AND its wiring into the live server turn.

The router answers one question per task: which escalating faculty do we spend? It walks six rungs
in strict cost order (free < lookup < tokens < local-gen < cloud) and returns the FIRST that
suffices, with a readable {route, why, fallback} — deterministic, no model. The verifier is a real
gate: a render that violates the skill's contract is WITHHELD, never served. This certifies that
contract through the SAME route_task the server calls, plus the REAL server._lerf_eligible (the
function anima/server._turn invokes at the top of every reply to decide a LERF-skill turn):

  A. THE COST LADDER IS ORDERED — COST is strictly free < lookup < tokens < local <= verifier <
     cloud, so "cheapest sufficient" is meaningful; the cheap gates separate a known-fact question
     from a skill task with no store and no model.
  B. RUNG 3 — a task a seeded ACTIVE skill covers routes to `lerf_skill`, names the right skill +
     score, populates {route,why,fallback} (fallback cites verifier->cloud), rules out the two
     cheaper rungs, and does NOT escalate (a local skill is sufficient). The router is deterministic
     (same task -> identical Route).
  C. RUNG 5 PASS — a contract-faithful small-model render (handed in) verifies to
     `small_local_verified` (grounded True) and does NOT spend the cloud.
  D. RUNG 5 FAIL -> RUNG 6 — a fabricated-figure render FAILS the grounded verifier and escalates to
     `cloud` when one is available (grounded False, escalated True).
  E. GROUNDED WITHHOLD — the SAME bad render with NO cloud is `verifier_failed_no_cloud`: the bad
     output is withheld, never served.
  F. HONEST NO-FACULTY + RUNG 2 — a task no skill covers escalates to cloud iff available, else
     reports `no_local_faculty` (no confabulation); a fact-question with no stored value does NOT
     claim `lirf_memory` (it falls through honestly) and records why.
  G. LIVE WIRING — the REAL anima/server._lerf_eligible (what _turn calls) returns the rung-3
     `lerf_skill` Route for a task-shaped turn whose skill is in the shared library, returns None for
     a feeling/companion turn (the companion path owns it), and returns None when a deterministic
     cap_note already owns the turn. This proves route_task STEERS the live reply path — before any
     model is consulted, deterministically.

Hermetic: every store (lerf/lerf_router/memory_lirf/server via _temp_store, plus constitution.STORE
and reliability.DEFAULT_STORE redirected here) points at a temp dir; the real .anima is fingerprinted
before/after and asserted byte-identical. No model, no network. Exit 0 == CERTIFIED, 1 == FAIL.
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


def _seed_active_skills(lerf, lib: str) -> None:
    """Two ACTIVE skills the router can match on — the same shape lerf_router._selftest seeds."""
    lerf.store_skill(lerf.make_skill(
        "summarize_medical_appointment", "health", state=lerf.ACTIVE,
        inputs=["raw doctor's note or appointment transcript"],
        steps=["Identify the diagnosis", "Extract medications with dosage",
               "List follow-ups with dates", "Write a plain-language summary"],
        outputs=["plain summary", "medication list", "follow-up list"],
        failure_modes=["dropping a dosage number"]), name=lib)
    lerf.store_skill(lerf.make_skill(
        "plan_errands", "logistics", state=lerf.ACTIVE,
        inputs=["list of stops", "start location"],
        steps=["Cluster stops by area", "Order to minimise backtracking"],
        outputs=["ordered route"], failure_modes=["ignoring opening hours"]), name=lib)


def main() -> int:
    from anima import lerf, lerf_router, server
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("LERF ROUTER — cheapest-sufficient ladder + grounded verifier + live server wiring")
    print("=" * 84)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # ---- A. THE COST LADDER IS ORDERED (pure, store-free) -----------------------------------
    ck("A1: COST tiers strictly ordered free < lookup < tokens < local <= verifier < cloud",
       lerf_router.COST["deterministic_rule"] < lerf_router.COST["lirf_memory"]
       < lerf_router.COST["lerf_skill"] < lerf_router.COST["small_local"]
       <= lerf_router.COST["verifier"] < lerf_router.COST["cloud"])
    ck("A2: the cheap gate detects a known-fact question",
       lerf_router._asks_known_fact("when's my birthday?") is not None)
    ck("A3: a skill task is NOT mistaken for a known-fact question",
       lerf_router._asks_known_fact("summarize this doctor's note into reminders") is None)

    with _temp_store() as tp:
        # Also redirect the two stores _temp_store doesn't cover (guarded-load side effects), so a
        # constitution/reliability write during a load can never touch the real .anima.
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
            # Route over the SAME shared library the live server routes over.
            lib = server._LERF_SKILL_LIBRARY
            _seed_active_skills(lerf, lib)
            nm = "lerfrouter_cert_" + secrets.token_hex(3)   # a creature name for personal-store rungs

            # ---- B. RUNG 3: a skill task routes to lerf_skill, fully explained --------------
            r = lerf_router.route_task(
                "Summarize this doctor's note and turn it into reminders", name=lib)
            ck("B1: a skill task routes to lerf_skill (rung 3)",
               r.route == "lerf_skill" and r.rung == 3)
            ck("B2: it names the correct matched skill + a score",
               r.skill_name == "summarize_medical_appointment" and r.score is not None
               and "summarize_medical_appointment" in r.why and "@" in r.why)
            d = r.as_dict()
            ck("B3: the {route, why, fallback} contract is fully populated",
               bool(d["route"]) and bool(d["why"]) and bool(d["fallback"]))
            ck("B4: the fallback names the verifier->cloud path",
               "verifier" in r.fallback and "cloud" in r.fallback)
            ck("B5: it ruled out the two cheaper rungs (deterministic_rule + lirf_memory)",
               any(c["rung"] == "deterministic_rule" for c in r.considered)
               and any(c["rung"] == "lirf_memory" for c in r.considered))
            ck("B6: a local skill is sufficient -> it did NOT escalate to cloud", r.escalated is False)
            ck("B7: the router is deterministic (same task -> identical Route)",
               lerf_router.route_task("plan my errands for saturday", name=lib)
               == lerf_router.route_task("plan my errands for saturday", name=lib))

            # ---- C. RUNG 5 PASS: a faithful render verifies locally; cloud NOT spent --------
            good = ("Summary: your blood pressure is stage 1. Medication: lisinopril 10 mg once "
                    "daily in the morning. Follow-up: book labs before the next visit.")
            rv = lerf_router.route_task(
                "Summarize this doctor's note into reminders", name=lib, rendered=good,
                inputs={"note": "stage 1 hypertension; lisinopril 10 mg once daily in the morning; "
                                "get labs before next visit"})
            ck("C1: a contract-faithful render verifies -> small_local_verified (grounded)",
               rv.route == "small_local_verified" and rv.grounded is True and rv.rung == 5)
            ck("C2: a verified local render does NOT escalate to cloud", rv.escalated is False)

            # ---- D. RUNG 5 FAIL -> RUNG 6: a fabricated figure escalates to the cloud -------
            bad = ("Take lisinopril 999 mg twice daily; your reading was 250 over 190; "
                   "follow up on the 47th.")
            rb = lerf_router.route_task(
                "Summarize this doctor's note into reminders", name=lib, rendered=bad,
                inputs={"note": "stage 1 hypertension discussed; no doses or figures given"},
                caps_state={"cloud_on": True, "cloud_model": "claude"})
            ck("D1: a render that FAILS the grounded verifier escalates to cloud",
               rb.route == "cloud" and rb.escalated is True and rb.grounded is False)
            ck("D2: the why cites the verifier failure as the escalation reason",
               "verifier" in rb.why.lower() or "fabricated" in rb.why.lower())

            # ---- E. GROUNDED WITHHOLD: the same bad render with NO cloud is withheld --------
            rb2 = lerf_router.route_task(
                "Summarize this doctor's note into reminders", name=lib, rendered=bad,
                inputs={"note": "stage 1 hypertension discussed; no figures given"}, caps_state={})
            ck("E1: a failed render with no cloud is WITHHELD (never the bad output)",
               rb2.route == "verifier_failed_no_cloud" and rb2.grounded is False)

            # ---- F. HONEST NO-FACULTY + RUNG 2 honesty -------------------------------------
            rno = lerf_router.route_task("compose a symphony in the style of Mahler", name=lib,
                                         caps_state={"cloud_on": True})
            ck("F1: no-skill + cloud -> escalates to cloud (nothing local suffices)",
               rno.route == "cloud" and rno.escalated is True)
            rno2 = lerf_router.route_task("compose a symphony in the style of Mahler", name=lib,
                                          caps_state={})
            ck("F2: no-skill + no cloud -> honestly reports no_local_faculty (no confabulation)",
               rno2.route == "no_local_faculty")
            # rung 2: with no fact on the (synthetic) ledger, a fact-question does NOT claim memory.
            rfact = lerf_router.route_task("when's my birthday?", name=nm, caps_state={})
            ck("F3: a fact-question with no stored value does NOT claim lirf_memory",
               rfact.route != "lirf_memory")
            ck("F4: it recorded WHY memory was ruled out (fact not on ledger)",
               any(c["rung"] == "lirf_memory" and "ledger" in c.get("ruled_out", "")
                   for c in rfact.considered))

            # ---- G. LIVE WIRING: the REAL server._lerf_eligible (what _turn calls) ----------
            # G1: a task-shaped turn whose skill is in the shared library -> the rung-3 lerf_skill
            #     Route is RETURNED into the live path (route_task steers the reply, no model yet).
            elig = server._lerf_eligible(
                nm, "Summarize this doctor's note and turn it into reminders",
                cap_note=None, cloud_on=False)
            ck("G1: server._lerf_eligible accepts a task turn -> the rung-3 lerf_skill Route",
               elig is not None and elig.route == "lerf_skill" and elig.skill_id
               and elig.skill_name == "summarize_medical_appointment")
            # G2: a first-person feeling/companion turn is EXCLUDED before any skill match — the
            #     companion path owns it; a feeling is never answered with a task skill (#1 rule).
            feel = server._lerf_eligible(
                nm, "honestly I'm overwhelmed and exhausted today and I just feel lost",
                cap_note=None, cloud_on=False)
            ck("G2: server._lerf_eligible REJECTS a feeling/companion turn (returns None)",
               feel is None)
            # G3: when a deterministic capability already owns the turn (cap_note present), the
            #     router is never consulted -> None (rung-1 deterministic owns it).
            owned = server._lerf_eligible(
                nm, "Summarize this doctor's note and turn it into reminders",
                cap_note={"note": "a reminder was set"}, cloud_on=False)
            ck("G3: server._lerf_eligible defers when a deterministic cap_note owns the turn (None)",
               owned is None)
            # G4: the live gate's acceptance is deterministic too (same turn -> same decision).
            elig2 = server._lerf_eligible(
                nm, "Summarize this doctor's note and turn it into reminders",
                cap_note=None, cloud_on=False)
            ck("G4: the live gate decision is deterministic (same turn -> same accepted skill)",
               elig2 is not None and elig2.route == "lerf_skill"
               and elig2.skill_id == elig.skill_id)
        finally:
            for m, attr, old in extra:
                if old is not None:
                    setattr(m, attr, old)

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nLERF-ROUTER CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
