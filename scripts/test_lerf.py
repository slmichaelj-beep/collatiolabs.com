#!/usr/bin/env python3
"""
test_lerf — the LERF selftest battery.

Two layers, both DETERMINISTIC, OFFLINE, and FULLY HERMETIC (synthetic creatures, temp
stores; the real .anima is asserted byte-unchanged):

  1. The engine's own battery — `anima.lerf._selftest()` — schema, retrieval, verify,
     concepts, procedures, the compression proof, persistence, and the hermetic byte-check.
  2. A build-layer battery here — seed the 10 REAL hand-built skills from scripts/build_lerf
     into a TEMP store and prove the cohort is well-formed, all ACTIVE, individually
     retrievable on a realistic task, and that the retrieval-beats-prompt-stuffing
     compression holds across the whole cohort (not just one cherry-picked skill).

    python3 scripts/test_lerf.py             # run both batteries
    python3 scripts/test_lerf.py --selftest  # (same; accepted for parity with sibling scripts)

Exit 0 iff everything is green. Mirrors the hermetic discipline of anima/memory_lirf.py
_selftest and scripts/conservation.py: every store the load path may write is redirected to
one throwaway temp dir for the duration, and restored after.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from anima import lerf                                  # noqa: E402
import build_lerf                                       # noqa: E402  (sibling script)


_fails = []


def ok(label, cond):
    print(("  ok   " if cond else "  FAIL ") + label)
    if not cond:
        _fails.append(label)


def _footprint(root: Path) -> tuple:
    if not root.is_dir():
        return (None, 0)
    files = sorted(q for q in root.rglob("*")
                   if q.is_file() and "backups" not in q.relative_to(root).parts)
    h = hashlib.sha256()
    for q in files:
        h.update(str(q.relative_to(root)).encode())
        try:
            h.update(q.read_bytes())
        except OSError:
            h.update(b"<unreadable>")
    return (h.hexdigest(), len(files))


def _redirect_targets():
    """(module, attr) pairs for every store the LERF load path may write — resolved by name
    so a missing engine is simply skipped. Mirrors conservation.py._resolve_store_targets."""
    pairs = []
    for modpath, attr in (("anima.lerf", "STORE"),
                          ("anima.constitution", "STORE"),
                          ("anima.reliability", "DEFAULT_STORE")):
        try:
            mod = __import__(modpath, fromlist=["_"])
        except Exception:
            continue
        if hasattr(mod, attr):
            pairs.append((mod, attr))
    return pairs


def _build_layer_battery(creature: str) -> None:
    """Exercise the 10 hand-built seed skills (the build_lerf cohort) in the current
    (already-redirected) temp store."""
    seeded = build_lerf.seed(creature)
    ok("build: seeds exactly 10 skills", len(seeded) == 10)

    stored = lerf.all_skills(name=creature, include_nonactive=True)
    ok("build: all 10 persisted + reload from disk", len(stored) == 10)
    ok("build: every seeded skill is ACTIVE (hand-verified bar)",
       all(s["state"] == lerf.ACTIVE for s in stored))
    ok("build: every skill has real steps (>=3)", all(len(s["steps"]) >= 3 for s in stored))
    ok("build: every skill names its failure modes (>=1)",
       all(len(s.get("failure_modes", [])) >= 1 for s in stored))
    ok("build: every skill has inputs and outputs",
       all(s.get("inputs") and s.get("outputs") for s in stored))
    ok("build: ids are stable + unique (re-seed is idempotent)",
       len({s["id"] for s in stored}) == 10)

    # re-seeding must NOT duplicate (idempotent on id)
    build_lerf.seed(creature)
    ok("build: re-seeding is idempotent (still 10, no dupes)",
       len(lerf.all_skills(name=creature, include_nonactive=True)) == 10)

    # each skill is individually retrievable on a realistic task phrased in user language.
    tasks = {
        "skill_med_appt": "summarize the note from my doctor visit",
        "skill_reminders": "pull the reminders out of this note",
        "skill_errands": "help me plan my errands and the best route around town",
        "skill_legal_doc": "go through this lease contract and tell me my obligations",
        "skill_followup_email": "draft a follow up email to the recruiter",
        "skill_triage_inbox": "triage my inbox and tell me what to handle first",
        "skill_action_items": "extract the action items from this meeting transcript",
        "skill_compare_options": "compare these two phones and help me decide",
        "skill_explain_simply": "explain this concept simply for a beginner",
        "skill_prep_meeting": "help me prep for my meeting tomorrow",
    }
    by_id = {s["id"]: s for s in stored}
    for sid, task in tasks.items():
        top = lerf.retrieve_skills(task, limit=1, name=creature)
        want = by_id[sid]["name"]
        ok(f"retrieve: '{task[:38]}...' -> {want}",
           bool(top) and top[0]["id"] == sid)

    # the compression win holds across a realistic doctor-note task on the real cohort.
    transcript = (
        "Doctor: your blood pressure is 142 over 90, stage 1 hypertension. Starting "
        "lisinopril 10mg once daily in the morning. Cut sodium under 2g a day, walk 30 "
        "minutes most days, get a metabolic and lipid panel before the follow up on July "
        "17th. Call us if you get a persistent dry cough, it can be a side effect. "
    ) * 10  # a realistic multi-page visit transcript
    cr = lerf.compression_report(
        "Summarize this doctor note and turn it into reminders",
        transcript, examples=[transcript, transcript], name=creature)
    ok("PROOF: cohort task retrieves summarize_medical_appointment",
       cr["retrieved_skill"] == "summarize_medical_appointment")
    ok(f"PROOF: retrieved context COMPACT (got {cr['retrieved_tokens']} tok)",
       cr["retrieved_tokens"] <= 900)
    ok(f"PROOF: stuffed baseline LARGE (got {cr['stuffed_tokens']} tok)",
       cr["stuffed_tokens"] >= 1500)
    ok(f"PROOF: retrieval beats stuffing >=5x (got {cr['ratio']}x)", cr["ratio"] >= 5.0)


def main() -> int:
    # ---- layer 1: the engine's own hermetic battery (self-contained) ----
    print("=== anima.lerf engine battery ===")
    rc_engine = lerf._selftest()
    if rc_engine != 0:
        _fails.append("anima.lerf._selftest()")

    # ---- layer 2: build-layer battery, FULLY HERMETIC ----
    print("\n=== build_lerf cohort battery (hermetic temp store) ===")
    real = lerf.STORE if lerf.STORE.is_absolute() else (Path.cwd() / lerf.STORE)
    fp_before = _footprint(real)

    targets = _redirect_targets()
    saved = [(m, a, getattr(m, a, None)) for (m, a) in targets]
    td = tempfile.mkdtemp(prefix="lerf-test-")
    for (m, a) in targets:
        if getattr(m, a, None) is not None:
            setattr(m, a, Path(td))
    try:
        _build_layer_battery("lerf_test_synth")
    finally:
        for (m, a, old) in saved:
            if old is not None:
                setattr(m, a, old)
        import shutil
        shutil.rmtree(td, ignore_errors=True)

    fp_after = _footprint(real)
    ok("HERMETIC: real .anima byte-UNCHANGED across the build-layer battery",
       fp_before == fp_after)
    ok("HERMETIC: no synthetic creature file leaked into real .anima",
       (not real.is_dir()) or not any(p.name.startswith("lerf_test_synth")
                                      for p in real.glob("lerf_test_synth*")))

    print()
    if _fails:
        print(f"{len(_fails)} FAILED: " + ", ".join(_fails))
        return 1
    print("ALL LERF TESTS PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
