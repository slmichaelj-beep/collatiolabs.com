#!/usr/bin/env python3
"""certify_agency_suggest_only — Wave 2 Alpha: Vera SUGGESTS, never EXECUTES.

The load-bearing safety proof for controlled activation. Behavioral, hermetic (.anima redirected):

  1. SCHEMA        — a suggestion carries the full intent schema; born requires_approval=True,
                     execution_allowed=False, status=proposed; risk fail-safes to "high".
  2. LOGGED        — submitting writes the intent to the append-only intent ledger AND queues it.
  3. NO EXECUTION  — execution_allowed is False at EVERY stage (proposed / approved / rejected); the
                     is_executable() gate returns False for everything the loop produces.
  4. APPROVAL-GATED— nothing is approved without an explicit approve(); a fresh queue auto-approves
                     nothing (items sit 'proposed').
  5. APPROVE != EXECUTE — approve() records the decision + audits it, but does NOT flip
                     execution_allowed (execution is Wave 2B, a separate certified gate).
  6. REJECT        — reject() records 'rejected', audited, and the item can never execute.
  7. AUDITED       — submission/approval/rejection each write a security event to the SOC trail.
  8. DURABLE       — the queue + decisions persist across a reload.

Exit 0 == CERTIFIED; 1 == FAIL.
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


def main() -> int:
    from anima import agency_suggest as A, agency_approval_queue as Q
    from anima import agency_intent_ledger as L, incident
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("AGENCY SUGGEST-ONLY — Vera proposes; the founder disposes; nothing executes")
    print("=" * 92)

    with _temp_store():
        name = "AgencyCert"

        # ---- 1. SCHEMA ---------------------------------------------------------------------
        s = A.make_suggestion("Draft a reply to the doctor's office about the appointment",
                              "You said you'd respond today and the note is in your sources.",
                              evidence=["source:doc_note_42"], risk="low", action_type="draft")
        need = {"intent_id", "suggestion", "reason", "evidence", "risk", "requires_approval",
                "action_type", "execution_allowed", "status"}
        ck("1. a suggestion carries the full intent schema",
           need.issubset(set(s.keys())))
        ck("1. born requires_approval=True, execution_allowed=False, status=proposed",
           s["requires_approval"] is True and s["execution_allowed"] is False and s["status"] == "proposed")
        bad = A.make_suggestion("x", "y", risk="ULTRA", action_type="nuke")
        ck("1. fail-safe: unknown risk -> 'high', unknown action_type -> 'draft'",
           bad["risk"] == "high" and bad["action_type"] == "draft")

        # ---- 2. LOGGED ---------------------------------------------------------------------
        Q.submit(name, s)
        ck("2. submitting logs the intent to the append-only intent ledger",
           any(e.get("intent_id") == s["intent_id"] for e in L.entries(name, 50)))
        ck("2. submitting queues it as pending",
           any(p.get("intent_id") == s["intent_id"] for p in Q.pending(name)))

        # ---- 3. NO EXECUTION (proposed) ----------------------------------------------------
        ck("3. a proposed suggestion is NOT executable (execution_allowed False)",
           A.is_executable(Q.get(name, s["intent_id"])) is False)

        # ---- 4. APPROVAL-GATED -------------------------------------------------------------
        ck("4. a fresh queue auto-approves NOTHING (item still 'proposed')",
           Q.get(name, s["intent_id"])["status"] == "proposed")

        # ---- 5. APPROVE != EXECUTE ---------------------------------------------------------
        appr = Q.approve(name, s["intent_id"], by="founder")
        ck("5. approve() records the decision (status approved, decided_by founder)",
           appr["status"] == "approved" and appr.get("decided_by") == "founder")
        ck("5. approve() does NOT flip execution_allowed (suggest-only; execution is Wave 2B)",
           appr["execution_allowed"] is False and A.is_executable(appr) is False)

        # ---- 6. REJECT ---------------------------------------------------------------------
        s2 = A.make_suggestion("Organize the medical sources into a folder", "You have 6 related docs.",
                               risk="low", action_type="organize")
        Q.submit(name, s2)
        rej = Q.reject(name, s2["intent_id"], by="founder")
        ck("6. reject() records 'rejected' and the item can never execute",
           rej["status"] == "rejected" and A.is_executable(rej) is False)
        ck("6. a rejected suggestion is no longer pending",
           not any(p.get("intent_id") == s2["intent_id"] for p in Q.pending(name)))

        # ---- 7. AUDITED --------------------------------------------------------------------
        kinds = [e.get("kind") for e in incident.recent_events(50)]
        ck("7. submission + approval + rejection each wrote a security event (SOC trail)",
           "agency_suggestion" in kinds and "agency_approve" in kinds and "agency_reject" in kinds)

        # ---- 8. DURABLE --------------------------------------------------------------------
        import importlib
        importlib.reload(Q)            # drop any in-memory state; force a fresh read from disk
        again = Q.get(name, s["intent_id"])
        ck("8. the queue + decisions persist across a reload (approved item still approved)",
           again is not None and again["status"] == "approved" and again["execution_allowed"] is False)

    print("\nAGENCY-SUGGEST-ONLY CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
