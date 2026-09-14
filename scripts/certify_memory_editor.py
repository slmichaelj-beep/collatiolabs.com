#!/usr/bin/env python3
"""
certify_memory_editor — the memory-type editor live path: POST /library/edit edits a stored item,
the change PERSISTS to the durable store and is reflected on reload, and a bad id/action is REFUSED
honestly (no silent no-op, no fabricated success).

The Library rows (.lactions Reprocess/Archive/Delete) call POST /library/edit, which
server._serve_library_edit validates against intake_queue._VALID_EDIT_ACTIONS and dispatches to
intake_queue.edit_item (reroute/archive/reprocess/delete) with an append-only audit. Certified
through that SAME path the UI calls:

  A. RECLASSIFY PERSISTS — edit_item(action='reroute', new_destination, new_rights) returns
     (item, audit) with audit.from != audit.to; a FRESH intake_queue.references() read from disk
     shows the new destination + rights (the edit is durable, not in-memory).
  B. THROUGH THE SERVER HANDLER — server._serve_library_edit(action='archive') returns ok=True and
     a fresh get_record() shows the queue record is now 'archived' (the exact path the UI button hits).
  C. HONEST REFUSAL — _serve_library_edit on an UNKNOWN id returns ok=False with an error (the
     backend KeyError is surfaced, not crashed); an UNKNOWN action returns ok=False (must be one of
     the valid actions); a MISSING id returns ok=False. Nothing is fabricated; nothing else mutates.

Hermetic: every store via _temp_store; the real .anima is fingerprinted before/after and asserted
byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

# The reprocess/archive editor actions advance the durable QUEUE record (set_state), so we create
# the item through the REAL plan->approve flow (which writes both a reference entry and a queue
# record). Force the intake fetch seam offline so the text path never opens a socket.
os.environ.setdefault("ANIMA_INTAKE_OFFLINE", "1")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store
_footprint = _g0pe._footprint


def main() -> int:
    from anima import intake_queue, server
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("MEMORY EDITOR — edit a stored item: persists on reload; bad id/action refused honestly")
    print("=" * 80)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    with _temp_store():
        N = "MemoryEditorCert"
        server._ensure(N, 64)

        # Seed an EDITABLE item through the REAL plan->approve flow (reference_only): this writes
        # both a Reference Library entry AND a durable queue record, so reroute/archive both apply.
        LADDER = ("The blue copper ladder 92817 has exactly twelve rungs and was forged in the "
                  "city of Aldermere by the smith Orin Vale.")
        plan = server._intake_plan(N, {"kind": "text", "text": LADDER})
        SRC = plan.get("source_id")
        appr = server._intake_approve(N, {"source_id": SRC, "control": "reference_only"})
        ck("S0: setup — plan->approve committed a durable reference (the item to edit)",
           bool(SRC) and appr.get("ok") is True and appr.get("committed") is True
           and any(r.get("id") == SRC for r in intake_queue.references(N)))

        # ---- A. RECLASSIFY PERSISTS (reroute destination + rights) ---------------------------
        item, audit = intake_queue.edit_item(
            N, SRC, action="reroute",
            new_destination="Authoritative Sources", new_rights="authoritative",
            reason="reclassify as an authoritative source")
        ck("A1: edit_item(reroute) returns (item, audit) and the audit records the change (from != to)",
           isinstance(item, dict) and isinstance(audit, dict) and audit.get("from") != audit.get("to")
           and (audit.get("to") or {}).get("destination") == "Authoritative Sources")
        fresh = intake_queue.references(N)   # re-read straight from disk
        prov = next((r.get("provenance", {}) for r in fresh if r.get("id") == SRC), {})
        ck("A2: the reclassify PERSISTS on a fresh disk read (destination + rights updated)",
           prov.get("destination") == "Authoritative Sources"
           and prov.get("rights_category") == "authoritative")

        # ---- B. THROUGH THE SERVER HANDLER (the exact UI button path) ------------------------
        out = server._serve_library_edit(N, {"id": SRC, "action": "archive",
                                              "reason": "archive via editor"})
        ck("B1: POST /library/edit (archive) returns ok=True with item + audit",
           out.get("ok") is True and out.get("item") and out.get("audit"))
        rec = intake_queue.get_record(N, SRC)
        ck("B2: a fresh get_record() shows the queue record is now 'archived' (durable transition)",
           (rec or {}).get("state") == "archived")

        # ---- C. HONEST REFUSAL ---------------------------------------------------------------
        bad_id = server._serve_library_edit(N, {"id": "does_not_exist", "action": "archive"})
        ck("C1: an UNKNOWN id is refused honestly (ok=False + error; backend KeyError surfaced, not a crash)",
           bad_id.get("ok") is False and bool(bad_id.get("error")))
        bad_action = server._serve_library_edit(N, {"id": SRC, "action": "frobnicate"})
        ck("C2: an UNKNOWN action is refused (ok=False; must be one of the valid edit actions)",
           bad_action.get("ok") is False and "action must be one of" in (bad_action.get("error") or ""))
        no_id = server._serve_library_edit(N, {"action": "archive"})
        ck("C3: a MISSING id is refused (ok=False, 'id is required')",
           no_id.get("ok") is False and "id is required" in (no_id.get("error") or ""))

        # the honest-refusal calls mutated nothing new: the one real item is still the only one
        ck("C4: the refusals fabricated NOTHING (still exactly one stored reference)",
           len(intake_queue.references(N)) == 1)

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nMEMORY-EDITOR CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
