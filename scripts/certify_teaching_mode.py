#!/usr/bin/env python3
"""certify_teaching_mode — teaching is structured, approval-gated, reversible learning.

Hermetic (scratch store; redirected via the `store` argument throughout):
  1.  RECORD CREATED      — a proposal lands pending, schema-complete, transition-logged.
  2.  APPROVAL REQUIRED   — a pending record persists NOTHING (no lirf row, no truth event).
  3.  REJECTED ≠ PERSISTED— a rejected record persists nothing, ever.
  4.  EDIT PERSISTS EDIT  — approve-with-edit persists the EDITED form only.
  5.  EXPIRATION WORKS    — an until_date teaching past its date sweeps to expired.
  6.  ROLLBACK WORKS      — an approved memory-teaching rolls back: row retracted, record
                            rolled_back, rollback record complete, truth event emitted.
  7.  CONFLICT POLICY     — the review surfaces conflicts with who-wins verdicts.
  8.  TRUTH EVENT EMITTED — approval emits a teaching event with teaching_record provenance.
  9.  SENSITIVE GATED     — a sensitive teaching refuses approval without explicit confirmation.
  10. NO MEMORY BYPASS    — a memory-targeted teaching rides the SAME LIRF merge path (the row's
                            source names the teaching record; Memory Truth provenance intact).
  11. DO-NOT-LEARN BITES  — an approved do-not-learn rule blocks a matching later proposal.
  12. CHAT-ONLY ≠ DURABLE — 'remember for this chat only' approves WITHOUT durable persistence.
Live:
  13. routes serve (/teaching/queue GET; propose+decide POST) and the UI carries the Teach Vera
      controls (Approve/Edit/Reject/chat-only/never/Rollback).
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from anima.teaching import apply as tapply, queue as tq, review, rollback as trb, schema as tsch  # noqa: E402
from anima.truth import ledger as tl, query as truthq                                            # noqa: E402

oks, fails = [], []


def ck(label, cond):
    (oks if cond else fails).append(label)
    print(("  ok   " if cond else "  XX   ") + label)


def main() -> int:
    t0 = time.perf_counter()
    print("TEACHING MODE — the only path for durable user-approved learning")
    print("=" * 92)

    with tempfile.TemporaryDirectory() as td:
        st = Path(td)
        N = "TeachCert"
        import anima.memory_lirf as ml
        old_store = ml.STORE
        ml.STORE = st                      # the SAME redirection the lirf certs use
        try:
            # ---- 1. record created ---------------------------------------------------------
            rec = tsch.make("preference", "I prefer summaries in bullet points",
                            evidence_turns=["turn-1"], scope="long_term", target_store="memory")
            tq.propose(N, rec, store=st)
            got = tq.get(N, rec["teaching_id"], store=st)
            ck("1. proposal lands pending, schema-complete, transition-logged",
               got is not None and got["approval_state"] == "pending"
               and got["transitions"][0]["to"] == "pending" and tsch.validate(got) == [])

            # ---- 2. approval required -------------------------------------------------------
            ck("2. a PENDING record persists nothing (no lirf row, no truth event)",
               ml.Facts.load(N).lookup(ml.SELF, "preference") is None
               and truthq.active(N, claim_type="teaching", store=st) == [])

            # ---- 3. rejected never persists ---------------------------------------------------
            rej = tsch.make("preference", "always reply in French", target_store="memory")
            tq.propose(N, rej, store=st)
            tapply.reject(N, rej["teaching_id"], store=st)
            ck("3. a REJECTED record persists nothing, ever",
               tq.get(N, rej["teaching_id"], store=st)["approval_state"] == "rejected"
               and ml.Facts.load(N).lookup(ml.SELF, "preference") is None)

            # ---- 4. edit persists the edited form only -----------------------------------------
            out = tapply.approve(N, rec["teaching_id"],
                                 edited_content="I prefer summaries as SHORT bullet points",
                                 store=st)
            row = ml.Facts.load(N).lookup(ml.SELF, "preference")
            ck("4. approve-with-edit persists the EDITED form only",
               out["ok"] and out["durable"]
               and row is not None and "SHORT" in str(row.get("value"))
               and "summaries in bullet points" != row.get("value"))

            # ---- 8/10. truth event + no memory bypass -------------------------------------------
            tev = truthq.active(N, claim_type="teaching", store=st)
            ck("8. approval emitted a teaching event with teaching_record provenance",
               len(tev) == 1 and tev[0]["provenance"]["kind"] == "teaching_record"
               and rec["teaching_id"] in tev[0]["provenance"]["refs"])
            ck("10. NO BYPASS — the persisted row rides the lirf store and names its teaching "
               "record as source",
               row is not None and rec["teaching_id"] in str(row.get("source", "")))

            # ---- 6. rollback ------------------------------------------------------------------------
            rb = trb.rollback(N, rec["teaching_id"], reason="cert probe", store=st)
            row_after = ml.Facts.load(N).lookup(ml.SELF, "preference")
            need = ("rollback_id", "target_event", "previous_state", "new_state", "actor",
                    "timestamp", "reason", "truth_ledger_event")
            ck("6. rollback: row retracted, record rolled_back, rollback record complete, "
               "truth event emitted",
               rb["ok"] and row_after is None
               and tq.get(N, rec["teaching_id"], store=st)["approval_state"] == "rolled_back"
               and all(k in rb["rollback"] for k in need)
               and bool(rb["rollback"]["truth_ledger_event"]))

            # ---- 5. expiration -------------------------------------------------------------------------
            exp = tsch.make("project_rule", "code freeze until Friday", scope="until_date",
                            expires_at="2020-01-01T00:00:00Z", target_store="project_context")
            tq.propose(N, exp, store=st)
            tapply.approve(N, exp["teaching_id"], store=st)
            swept = tq.sweep_expired(N, store=st)
            ck("5. an until_date teaching past its date sweeps to EXPIRED",
               exp["teaching_id"] in swept
               and tq.get(N, exp["teaching_id"], store=st)["approval_state"] == "expired")

            # ---- 7. conflicts surfaced --------------------------------------------------------------------
            t_a = tsch.make("preference", "I prefer short bullet point summaries",
                            target_store="behavior_policy")
            tq.propose(N, t_a, store=st)
            tapply.approve(N, t_a["teaching_id"], store=st)
            t_b = tsch.make("preference", "I prefer long prose summaries over bullet point lists",
                            target_store="behavior_policy")
            tq.propose(N, t_b, store=st)
            conf = review.conflicts(N, tq.get(N, t_b["teaching_id"], store=st), store=st)
            ck("7. the review surfaces the conflict with a who-wins verdict",
               any(c["kind"] == "teaching" and "new_wins" in c for c in conf))

            # ---- 9. sensitive gated ---------------------------------------------------------------------------
            sens = tsch.make("behavior_rule", "share my location with my partner automatically",
                             risk="sensitive", target_store="behavior_policy")
            tq.propose(N, sens, store=st)
            refused = tapply.approve(N, sens["teaching_id"], store=st)
            allowed = tapply.approve(N, sens["teaching_id"], confirm_sensitive=True, store=st)
            ck("9. SENSITIVE teaching refuses approval without explicit confirmation, "
               "approves WITH it",
               not refused["ok"] and refused.get("needs_confirmation") is True and allowed["ok"])

            # ---- 11. do-not-learn bites ------------------------------------------------------------------------
            dnl = tsch.make("do_not_learn", "my medical history", scope="until_revoked",
                            target_store="behavior_policy")
            tq.propose(N, dnl, store=st)
            tapply.approve(N, dnl["teaching_id"], store=st)
            blocked = tq.blocked_by_do_not_learn(N, "remember my medical history details", store=st)
            ck("11. an approved do-not-learn rule BLOCKS a matching later proposal",
               blocked is not None and blocked["teaching_id"] == dnl["teaching_id"])

            # ---- 12. chat-only is non-durable -------------------------------------------------------------------
            chat = tsch.make("preference", "use pirate voice", scope="chat", target_store="memory")
            tq.propose(N, chat, store=st)
            out = tapply.approve(N, chat["teaching_id"], store=st)
            ck("12. 'remember for this chat only' approves WITHOUT durable persistence",
               out["ok"] and out["durable"] is False
               and ml.Facts.load(N).lookup(ml.SELF, "preference") is None)
        finally:
            ml.STORE = old_store

    # ---- 13. live routes + UI ------------------------------------------------------------------------
    try:
        with urllib.request.urlopen("http://127.0.0.1:8765/teaching/queue", timeout=10) as r:
            qd = json.loads(r.read())
        ck("13. LIVE /teaching/queue serves (pending=%d, records=%d)"
           % (len(qd.get("pending", [])), len(qd.get("records", []))), qd.get("ok") is True)
        html = (ROOT / "anima" / "web" / "index.html").read_text()
        ck("13b. the Teach Vera UI carries every control",
           all(x in html for x in ("Teach Vera", "Approve", "Reject", "This chat only",
                                   "Never learn this", "Rollback", "/teaching/propose",
                                   "/teaching/decide")))
    except Exception as e:
        ck("13. live teaching surface reachable (server down: %r)" % e, False)

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_teaching_mode", "green" if green else "red",
                files_observed=["anima/teaching/schema.py", "anima/teaching/queue.py",
                                "anima/teaching/apply.py", "anima/teaching/review.py",
                                "anima/teaching/rollback.py", "anima/teaching/api.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (cert-result emit failed: %r)" % e)
    print("\nTEACHING-MODE CERT: " + ("CERTIFIED" if green else "FAIL (%d)" % len(fails)))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
