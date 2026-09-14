#!/usr/bin/env python3
"""
certify_root_cause — the Unified Root-Cause Command: every FAILED experience -> ONE root cause,
+ the canonical remediation map that turns a pattern into a certifiable work order.

"Make every failed experience traceable to a root cause in ONE command." This certifies that
contract through the SAME functions the user-facing command (`python3 scripts/rootcause.py`) runs
and the SAME remediation map the Pattern Observatory stamps:

  A. ONE COMMAND, ONE VERDICT — rootcause.root_cause(a SEEDED FailingExperience) returns, in a
     single call, a "FAILED: <symptom> -> ROOT CAUSE: <stage> -> FIX: <hint>" verdict, with the
     root cause drawn from relationship.py's taxonomy and the four corroborating legs attached
     (mri + conservation + decision + diagnosis). It derives a root cause from a seeded failure
     record, deterministically and offline (no model).
  B. THE CHAIN DISCRIMINATES — the three DISTINCT seeded failures localize to the THREE CORRECT,
     DISTINCT stages (never one collapsed label): a never-captured fact -> CAPTURE GAP; the same
     felt symptom but the fact on disk + router missing it -> RETRIEVAL/ROUTING TOO STRICT; an
     invented inner life with nothing on disk -> GROUNDING. Same symptom 'forgot a known fact',
     two different root causes — the headline discrimination invariant.
  C. CORROBORATION IS REAL — for the capture-gap verdict the localizer chain shows AVAILABLE=no
     (the fact never reached disk); for the retrieval verdict AVAILABLE=yes + RETRIEVED=no and
     conservation confirms the in-play trait survived capture to disk; for grounding the reply
     INVENTED with nothing on disk. The MRI film recorded the capture/route/generate/verify
     stages. Every verdict's root cause + fix come straight from relationship.TAXONOMY.
  D. THE REMEDIATION MAP (anima/root_cause.py) — remediation_for(pattern_id) ALWAYS returns the
     four engineering keys (root_cause, recommended_fix, cert_required, expected_improvement); a
     SEEDED pattern_id ('conversation_repair', the live P0 WALLPAPER) returns its real, curated
     work order with a non-empty cert list; an UNKNOWN pattern_id returns the honest generic
     placeholder (never a crash, never a fabrication). The map is internally consistent
     (default_severity / title resolve for every seeded entry, and severity_rank sorts P0<P1<P2).
  E. ROBUST + NEVER-RAISE — a malformed/empty FailingExperience still root-causes (no traceback)
     and still yields a FAILED -> ROOT CAUSE -> FIX line; the live-model leg is GATED ON OLLAMA
     and SKIPS LOUD offline (offline is never a failure).

Hermetic + offline (no Ollama, no network): the in-process MRI + decision legs are driven inside
gate0_prime_experience._temp_store() (every store-bearing module redirected to a temp dir), plus
reliability.DEFAULT_STORE redirected here (a store gate0's set doesn't cover); the chain's own
localizer / conservation each additionally open their OWN hermetic temp store. The real .anima is
fingerprinted before/after and asserted byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# rootcause.py + the tools it chains live importable as top-level modules under scripts/.
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store
_footprint = _g0pe._footprint


def main() -> int:
    import rootcause as rc                          # the Unified Root-Cause COMMAND
    import relationship                             # the CORE localizer + the taxonomy
    from anima import root_cause as rcmap           # the canonical remediation MAP
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("ROOT CAUSE — one command: a failed experience -> one root cause (+ remediation map)")
    print("=" * 84)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # ---- D. THE REMEDIATION MAP — pure data + remediation_for; exercise it OUTSIDE any store ----
    KEYS = {"root_cause", "recommended_fix", "cert_required", "expected_improvement"}
    seeded = rcmap.remediation_for("conversation_repair")     # the live P0 WALLPAPER work order
    ck("D1: remediation_for(seeded) returns exactly the four engineering keys",
       set(seeded.keys()) == KEYS)
    ck("D2: a SEEDED pattern carries a real curated root cause + a non-empty cert list",
       bool(seeded["root_cause"].strip()) and isinstance(seeded["cert_required"], list)
       and len(seeded["cert_required"]) >= 1)
    unknown = rcmap.remediation_for("no_such_pattern_zzz_999")
    ck("D3: an UNKNOWN pattern returns the honest generic placeholder (never a crash/fabrication)",
       set(unknown.keys()) == KEYS
       and "No canonical root cause" in unknown["root_cause"]
       and unknown["cert_required"] == [])
    ck("D4: every seeded entry resolves a title + a default severity (map internally consistent)",
       all(rcmap.title_for(pid) and rcmap.default_severity_for(pid) in ("P0", "P1", "P2")
           for pid in rcmap.REMEDIATIONS))
    ck("D5: severity_rank sorts P0 < P1 < P2 and an unknown severity sorts last",
       rcmap.severity_rank("P0") < rcmap.severity_rank("P1") < rcmap.severity_rank("P2")
       and rcmap.severity_rank("???") > rcmap.severity_rank("P2"))

    with _temp_store():
        # gate0's _temp_store redirects every store-bearing module's STORE to ONE temp dir; read
        # that active temp dir back off an already-redirected module (memory_lirf.STORE).
        tp = getattr(__import__("anima.memory_lirf", fromlist=["_"]), "STORE", None)
        # reliability uses DEFAULT_STORE (not STORE), which gate0's set does not cover; redirect it
        # to the same temp dir so a guarded-backup snapshot can never escape to the real .anima.
        extra = []
        for modname, attr in (("anima.reliability", "DEFAULT_STORE"),):
            try:
                m = __import__(modname, fromlist=["_"])
                extra.append((m, attr, getattr(m, attr, None)))
                if tp is not None and getattr(m, attr, None) is not None:
                    setattr(m, attr, tp)
            except Exception:
                pass
        try:
            # ---- A. ONE COMMAND, ONE VERDICT (from a SEEDED failure record) ---------------------
            fx_cap = rc.FailingExperience(
                rc.SYM_FORGOT_KNOWN, "Do you remember my sister?", "sister", "Mara",
                teach=None, recall_query="what's my sister's name?", reply=None)
            v = rc.root_cause(fx_cap)                 # the ONE call that derives the root cause
            ck("A1: root_cause(a seeded failure) yields a single FAILED -> ROOT CAUSE -> FIX verdict",
               isinstance(v, dict) and v.get("verdict", "").startswith("FAILED:")
               and "ROOT CAUSE:" in v["verdict"] and "FIX:" in v["verdict"])
            ck("A2: the verdict carries ALL FOUR corroborating legs (mri+conservation+decision+diagnosis)",
               all(k in v for k in ("mri", "conservation", "decision", "diagnosis")))
            ck("A3: the root cause is drawn from relationship.py's taxonomy (the CORE owns it)",
               v.get("root_cause") in relationship.TAXONOMY
               and v.get("fix_hint") == relationship.TAXONOMY[v["root_cause"]]["fix_hint"])

            # ---- B. THE CHAIN DISCRIMINATES — three seeds -> three correct, distinct stages -----
            bat = rc.run_battery()                    # offline, deterministic — the correctness gate
            ck("B1: every seeded failure localized to its CORRECT root cause",
               bat.get("all_correct") is True and bat.get("total") == 3)
            ck("B2: the three seeds yield THREE DISTINCT root causes (no collapse to one label)",
               len({c["got"] for c in bat["cases"]}) == 3)
            by_root = {rec["root_cause"]: rec for rec in bat["verdicts"]}
            cap = by_root.get(relationship.CAPTURE_GAP)
            retr = by_root.get(relationship.RETRIEVAL_TOO_STRICT)
            grnd = by_root.get(relationship.GROUNDING)
            ck("B3: all three taxonomy stages (CAPTURE GAP / RETRIEVAL / GROUNDING) are represented",
               cap is not None and retr is not None and grnd is not None)
            ck("B4: CONTROL — same symptom 'forgot a known fact' localizes capture vs retrieval "
               "DIFFERENTLY (root on the chain, not the symptom word)",
               cap is not None and retr is not None
               and cap["symptom"] == rc.SYM_FORGOT_KNOWN == retr["symptom"]
               and {cap["root_cause"], retr["root_cause"]}
               == {relationship.CAPTURE_GAP, relationship.RETRIEVAL_TOO_STRICT})

            # ---- C. CORROBORATION IS REAL — the chain booleans + conservation + the MRI film -----
            ck("C1: capture-gap chain shows AVAILABLE=no (the fact never reached disk)",
               cap is not None and cap["diagnosis"]["available"] is False)
            ck("C2: retrieval chain shows AVAILABLE=yes + RETRIEVED=no (on disk, router missed it)",
               retr is not None and retr["diagnosis"]["available"] is True
               and retr["diagnosis"]["retrieved"] is False)
            ck("C3: conservation CORROBORATES the retrieval verdict — in-play trait survived to disk",
               retr is not None and retr["conservation"].get("ran") is True
               and retr["conservation"].get("inplay_stored") is True)
            ck("C4: grounding verdict — the reply INVENTED with nothing on disk behind it",
               grnd is not None and grnd["diagnosis"]["available"] is False
               and grnd["diagnosis"]["invented"] is True)
            ck("C5: the MRI film recorded the capture+route+generate+verify stages",
               cap is not None
               and {"capture", "route", "generate", "verify"} <= set(cap["mri"]["stages"]))

            # ---- E. ROBUST + NEVER-RAISE + the live gate degrades cleanly ------------------------
            try:
                v_bad = rc.root_cause(rc.FailingExperience("", "", "", "", teach=None,
                                                           recall_query="", reply=None))
                crashed = False
            except Exception as exc:
                crashed = True
                print("       (raised:", repr(exc), ")")
            ck("E1: a malformed/empty failing experience root-causes WITHOUT raising",
               not crashed)
            ck("E2: even a malformed failure still yields a FAILED -> ROOT CAUSE -> FIX line",
               not crashed and v_bad["verdict"].startswith("FAILED:")
               and "ROOT CAUSE:" in v_bad["verdict"])
            # E3: the live-model leg EXISTS and is GATED on Ollama (run_live first asks
            # experience._model_available() and returns {available:False,...} offline). We assert
            # the gate WITHOUT driving the model — this cert is strictly offline; the live leg is
            # observational only and never the correctness gate (run_battery above is). We verify
            # it short-circuits when the gate reports unavailable, via a stub that forces offline.
            _saved_gate = rc.experience._model_available
            try:
                rc.experience._model_available = lambda: (False, "(cert: gate forced offline)", "offline")
                live = rc.run_live()                  # MUST short-circuit BEFORE any generation
            finally:
                rc.experience._model_available = _saved_gate
            ck("E3: the live-model leg is GATED on Ollama and SKIPS LOUD when offline "
               "(observational only; never the correctness gate)",
               live.get("available") is False and "why_not" in live)
        finally:
            for m, attr, old in extra:
                if old is not None:
                    setattr(m, attr, old)

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nROOT-CAUSE CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
