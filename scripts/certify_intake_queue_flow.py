#!/usr/bin/env python3
"""
certify_intake_queue_flow — the consent-gated intake flow: PLAN (stage + preview, nothing durable)
-> explicit APPROVE -> durable + retrievable, and NOTHING is stored without the explicit approve.

The "+ -> Paste text" UI calls POST /intake/plan (runIntake), which server._intake_plan stages the
raw and runs the Wave-1 plan (committed=False); the user then approves via POST /intake/approve,
which server._intake_approve commits through intake_queue.commit_on_approval. Certified OFFLINE
(ANIMA_INTAKE_OFFLINE=1) on a TEXT intake — no heavy parser, no socket — through those SAME handlers:

  A. PLAN STAGES, COMMITS NOTHING — _intake_plan(kind=text) returns ok, committed=False, a real
     source_id, parse_status='ok'; the raw is STAGED (server._read_staging finds it) as the
     awaiting-approval artifact; intake_queue.references() has NOTHING for this source yet.
  B. APPROVE COMMITS — _intake_approve(source_id, control='reference_only') returns ok,
     committed=True; the source is now in intake_queue.references() AND its queue record is ST_ACTIVE;
     GET /library shows it 'active'.
  C. DURABLE + RETRIEVABLE — the committed reference, read FRESH from intake_queue.references()
     (a clean disk read, not an in-process cache), contains the unique phrase.
  D. NO APPROVE => NOTHING STORED — a SECOND plan that is never approved commits NOTHING: its
     source_id never appears in references(), and no ST_ACTIVE record exists for it.

Hermetic: every store via _temp_store; the real .anima is fingerprinted before/after and asserted
byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

# OFFLINE + HERMETIC by contract: force the intake fetch seam offline so the TEXT path never opens a
# socket (a URL would degrade to needs_dependency; we exercise pasted TEXT, the proven durable kind).
os.environ.setdefault("ANIMA_INTAKE_OFFLINE", "1")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store
_footprint = _g0pe._footprint

UNIQUE = ("The blue copper ladder 92817 has exactly twelve rungs and was forged in the city of "
          "Aldermere by the smith Orin Vale.")


def main() -> int:
    from anima import intake_queue, server
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("INTAKE QUEUE FLOW — plan (stage, nothing durable) -> explicit approve -> durable; "
          "no approve => nothing stored")
    print("=" * 80)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    with _temp_store():
        N = "IntakeFlowCert"
        server._ensure(N, 64)

        # ---- A. PLAN STAGES, COMMITS NOTHING -------------------------------------------------
        plan = server._intake_plan(N, {"kind": "text", "text": UNIQUE})
        sid = plan.get("source_id")
        ck("A1: POST /intake/plan (text) returns ok, committed=False, a real source_id, parse ok",
           plan.get("ok") is True and plan.get("committed") is False and bool(sid)
           and plan.get("parse_status") == "ok")
        stage_path, found = server._read_staging(N, sid)
        ck("A2: the raw is STAGED awaiting approval (server._read_staging finds the staging file)",
           found is True and stage_path is not None and stage_path.exists())
        ck("A3: NOTHING is durable after the plan (no reference for this source yet)",
           not any(r.get("id") == sid for r in intake_queue.references(N)))

        # ---- B. APPROVE COMMITS --------------------------------------------------------------
        appr = server._intake_approve(N, {"source_id": sid, "control": "reference_only"})
        ck("B1: POST /intake/approve (reference_only) returns ok + committed=True (durable)",
           appr.get("ok") is True and appr.get("committed") is True and bool(appr.get("reference")))
        ck("B2: the source is now in the Reference Library AND its queue record is ST_ACTIVE",
           any(r.get("id") == sid for r in intake_queue.references(N))
           and (intake_queue.get_record(N, sid) or {}).get("state") == intake_queue.ST_ACTIVE)
        lib = server._serve_library(N, f"name={N}")
        ck("B3: GET /library now shows the committed item with status 'active'",
           lib.get("ok") is True
           and any(it.get("id") == sid and it.get("status") == "active"
                   for it in lib.get("items", [])))

        # ---- C. DURABLE + RETRIEVABLE (fresh disk read carries the unique phrase) -------------
        fresh = intake_queue.references(N)
        ref = next((r for r in fresh if r.get("id") == sid), None)
        ck("C1: the committed reference, read FRESH from disk, carries the unique phrase",
           ref is not None
           and any("92817" in (c.get("text") or "") and "Aldermere" in (c.get("text") or "")
                   for c in ref.get("chunks", [])))

        # ---- D. NO APPROVE => NOTHING STORED -------------------------------------------------
        plan2 = server._intake_plan(N, {"kind": "text", "text": "a second note about teal bricks 4451"})
        sid2 = plan2.get("source_id")
        ck("D1: a SECOND plan (never approved) was planned, committed=False",
           plan2.get("ok") is True and plan2.get("committed") is False and bool(sid2) and sid2 != sid)
        ck("D2: the never-approved source committed NOTHING — absent from references() and not ST_ACTIVE",
           not any(r.get("id") == sid2 for r in intake_queue.references(N))
           and (intake_queue.get_record(N, sid2) or {}).get("state") != intake_queue.ST_ACTIVE)

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nINTAKE-QUEUE-FLOW CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
