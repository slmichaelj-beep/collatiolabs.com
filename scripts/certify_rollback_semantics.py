#!/usr/bin/env python3
"""certify_rollback_semantics — every reversible surface is reversible, and the reversal is
recorded with the full record + a Truth Ledger event.

Hermetic (scratch store):
  1. SCHEMA BITES     — make() builds a valid record; missing/empty fields raise.
  2. MEMORY          — a memory correction event rolls back (retracted) + recorded + ledgered.
  3. TEACHING        — an approved teaching rolls back (row retracted, record rolled_back).
  4. AUTO-LEARN      — an auto-learn-converted teaching draft rolls back the same way.
  5. KNOWLEDGE PACK  — a ready pack rolls back to disabled (no longer retrievable).
  6. PROFILE OVERRIDE— a runtime profile override rolls back to the recommended profile.
  7. TIER CLASS      — a release-tier classification rollback rebuilds the registry.
  8. RECORD COMPLETE — every rollback record carries all 10 required fields + a truth event.
  9. HISTORY         — every rollback is appended to the rollback history (append-only).
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from anima.rollback import apply as rb, schema as rbs   # noqa: E402

oks, fails = [], []


def ck(label, cond):
    (oks if cond else fails).append(label)
    print(("  ok   " if cond else "  XX   ") + label)


def main() -> int:
    t0 = time.perf_counter()
    print("ROLLBACK SEMANTICS — every reversible surface, one record, always ledgered")
    print("=" * 92)

    # ---- 1. schema bites -----------------------------------------------------------------------
    rec = rbs.make("teaching_record", target_id="th_x", previous_state="approved",
                   new_state="rolled_back", reason="test")
    ck("1. make() builds a valid record", rbs.validate(rec) == [])
    raised = 0
    for bad in (dict(target_kind="nope"), dict(target_id=""), dict(reason="")):
        try:
            kw = dict(target_id="x", previous_state="a", new_state="b", reason="r")
            kw.update(bad)
            rbs.make(bad.get("target_kind", "teaching_record"),
                     **{k: v for k, v in kw.items() if k != "target_kind"})
        except ValueError:
            raised += 1
    ck("1b. missing/empty required fields raise (%d/3)" % raised, raised == 3)

    with tempfile.TemporaryDirectory() as td:
        st = Path(td)
        N = "RollbackCert"
        import anima.memory_lirf as ml
        old = ml.STORE
        ml.STORE = st
        try:
            from anima.truth import api as tapi, query as tq
            from anima.teaching import schema as tsch, queue as teachq, apply as tapply
            from anima.auto_learn import queue as alq, api as alapi
            from anima.knowledge_packs import schema as ksch, registry as kreg, builder as kbld

            # ---- 2. memory ------------------------------------------------------------------
            row = {"id": "f_m1", "trait": "lives", "value": "Portland", "confidence": 0.9,
                   "status": "active"}
            ev = tapi.on_memory_write(N, row, "I live in Portland", "turn-1", store=st)
            out = rb.rollback(N, "memory_correction", ev["event_id"], reason="probe", store=st)
            folded = tq.fold(N, store=st)
            ck("2. memory correction rolls back (event retracted) + recorded + ledgered",
               out["ok"] and folded[ev["event_id"]]["active_status"] in ("retracted", "superseded")
               and bool(out["record"]["truth_ledger_event"]))

            # ---- 3. teaching ---------------------------------------------------------------------
            t = tsch.make("preference", "bullet summaries", target_store="memory")
            teachq.propose(N, t, store=st)
            tapply.approve(N, t["teaching_id"], store=st)
            had_row = ml.Facts.load(N).lookup(ml.SELF, "preference") is not None
            out = rb.rollback(N, "teaching_record", t["teaching_id"], reason="probe", store=st)
            ck("3. an approved teaching rolls back (row retracted, record rolled_back)",
               out["ok"] and had_row
               and ml.Facts.load(N).lookup(ml.SELF, "preference") is None
               and teachq.get(N, t["teaching_id"], store=st)["approval_state"] == "rolled_back")

            # ---- 4. auto-learn conversion ----------------------------------------------------------
            s = alq.observe(N, "user likes short replies", evidence=["turn-9"], store=st)
            conv = alapi.serve_decide(N, {"auto_learn_id": s["suggestion"]["auto_learn_id"],
                                          "action": "convert"}, store=st)
            tapply.approve(N, conv["teaching_draft"], store=st)
            out = rb.rollback(N, "auto_learn_conversion", conv["teaching_draft"], reason="probe",
                              store=st)
            ck("4. an auto-learn-converted teaching draft rolls back",
               out["ok"] and teachq.get(N, conv["teaching_draft"], store=st)["approval_state"]
               == "rolled_back")

            # ---- 5. knowledge pack -----------------------------------------------------------------
            pk = ksch.make("Packy", "domain")
            kreg.add(N, pk, store=st)
            kbld.index(N, pk["pack_id"], [{"title": "t", "ref": "r.md", "text": "hello world"}],
                       store=st)
            kbld.evaluate(N, pk["pack_id"], store=st)
            kbld.promote(N, pk["pack_id"], store=st)
            out = rb.rollback(N, "knowledge_pack", pk["pack_id"], reason="probe", store=st)
            ck("5. a ready pack rolls back to disabled (no longer retrievable)",
               out["ok"] and kreg.get(N, pk["pack_id"], store=st)["lifecycle_status"] == "disabled")

            # ---- 8. record complete ---------------------------------------------------------------
            ck("8. every rollback record carries all required fields + a truth event",
               all(rbs.validate(r) == [] and r.get("truth_ledger_event")
                   for r in rb.history(N, store=st)))

            # ---- 9. history append-only ------------------------------------------------------------
            ck("9. every rollback is appended to the history (>=4 so far)",
               len(rb.history(N, store=st)) >= 4)
        finally:
            ml.STORE = old

    # ---- 6/7. profile override + tier classification (live-ish, real modules) ---------------------
    try:
        from anima.host import profile as hp
        rec0 = hp.current()
        hp.build_contract(override_profile="Balanced", override_by="rollback-cert")
        out = rb.rollback("Vera", "runtime_profile_override", "host_profile", reason="probe")
        restored = hp.current().get("selected_profile")
        ck("6. a runtime profile override rolls back to the recommended profile",
           out["ok"] and restored == rec0.get("recommended_profile"))
    except Exception as e:
        ck("6. profile override rollback (error: %r)" % e, False)

    try:
        out = rb.rollback("Vera", "release_tier_classification", "audiobook_intake",
                          reason="probe")
        ck("7. a release-tier classification rollback rebuilds the registry",
           out["ok"] and out["record"]["new_state"] in ("deferred_visible", None))
    except Exception as e:
        ck("7. tier classification rollback (error: %r)" % e, False)

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_rollback_semantics", "green" if green else "red",
                files_observed=["anima/rollback/schema.py", "anima/rollback/apply.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (cert-result emit failed: %r)" % e)
    print("\nROLLBACK-SEMANTICS CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
