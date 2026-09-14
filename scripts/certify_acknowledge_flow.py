#!/usr/bin/env python3
"""
certify_acknowledge_flow — POST /acknowledge is the real '👍 Got it' that CANCELS the call.

Vera's reminders are TIERED: a reminder is gentle first (a push with a confirm button); if you tap it
in time the escalation is cancelled; if you DON'T, she escalates and CALLS you out loud. POST
/acknowledge {reminder_id} is that tap. The server handler is a one-liner —
``ok = reminders.acknowledge(str(data.get("reminder_id", "")))`` then ``{"ok": ok}`` — so we certify the
DETERMINISTIC, SAFETY-CRITICAL state machine it drives, through the SAME function the endpoint calls,
and reproduce the endpoint's exact payload:

  A. SCHEDULE PERSISTS A PENDING REMINDER — schedule() mints+persists a reminder in state 'pending'
     (the 👍 push is the STUB _deliver_push, which only logs 'would push'); a fresh _load() sees it.
  B. ACK FLIPS THE STATE (DURABLY) — acknowledge(rid) returns True and moves 'pending'->'acknowledged';
     the change is on disk (a fresh _load() confirms acked_at set + state acknowledged).
  C. THE WHOLE POINT — ACK CANCELS THE CALL — a tick() PAST the deadline does NOT escalate the
     acknowledged reminder, proven against a CONTROL: an UN-acknowledged reminder of the same shape on
     the SAME tick DOES escalate (tick returns its id; _deliver_call STUB logs 'would CALL'). So the ack
     is demonstrably what cancels the call — not that escalation never fires.
  D. HONEST — acknowledge() returns False for: an unknown id, an empty id, an already-acknowledged id,
     and an already-escalated id. A confirmation can only cancel a real, still-pending reminder; it can
     never claim to have cancelled something that wasn't pending.
  E. ENDPOINT PAYLOAD — what POST /acknowledge sends is exactly {"ok": <bool>} (json), computed off
     reminders.acknowledge — True for the pending ack, False for a junk id.
  F. RESTART-SURVIVAL — the acknowledged state lives in reminders.json (atomic + encrypted-at-rest via
     util.save_json), so a fresh _load() ('a restart') still shows it acknowledged — a reboot can't
     resurrect a cancelled call.

Hermetic + offline (no model, no Apple, no HTTP): _temp_store() redirects reminders.STORE, but
reminders._STATE = STORE/'reminders.json' is a FROZEN module-level constant bound at import, so the cert
ALSO redirects reminders._STATE into the temp dir itself (exactly as certify_brain_select redirects
cloud.STORE) — otherwise schedule()/acknowledge() would touch the real .anima/reminders.json. Time is
injected (tiny fractional ack windows + tick(now=...)) so there are no sleeps and the run is fully
deterministic. ANIMA_INTAKE_OFFLINE=1. The real .anima is fingerprinted before/after and asserted
byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

os.environ.setdefault("ANIMA_INTAKE_OFFLINE", "1")   # belt-and-suspenders: nothing here touches intake

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store
_footprint = _g0pe._footprint


def _endpoint_payload(reminder_id: str) -> bytes:
    """Byte-for-byte what POST /acknowledge writes in server.do_POST:
        ok = reminders.acknowledge(str(data.get("reminder_id", "")))
        self._send(200, "application/json", json.dumps({"ok": ok}).encode())
    """
    from anima import reminders
    ok = reminders.acknowledge(str(reminder_id or ""))
    return json.dumps({"ok": ok}).encode()


def main() -> int:
    from anima import reminders
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("ACKNOWLEDGE FLOW — POST /acknowledge is the real '👍 Got it' that cancels the call")
    print("=" * 84)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    with _temp_store() as tp:
        # _temp_store rebinds reminders.STORE, but reminders._STATE = STORE/'reminders.json' is a
        # FROZEN constant bound at import — redirect it ourselves (like certify_brain_select does for
        # cloud.STORE) so NO real .anima/reminders.json is read or written.
        saved_state = getattr(reminders, "_STATE", None)
        reminders._STATE = Path(tp) / "reminders.json"
        try:
            N = "AckCert"

            def by_id():
                return {r.id: r for r in reminders.all_reminders()}

            def loaded(rid):
                """Read the row back FRESH from disk (a 'restart' view) — proves durability, not a
                cached in-memory object."""
                return reminders._load().get(rid)

            # ---- A. SCHEDULE PERSISTS A PENDING REMINDER --------------------------------------
            # tiny fractional window so the deadline is already in the past for tick(now=...) below;
            # the 👍 push here is the STUB _deliver_push (logs 'would push', never fails).
            rid = reminders.schedule("take your meds", ack_window_min=0.001, name=N)
            ck("A1: schedule() mints a reminder id", bool(rid) and isinstance(rid, str))
            ck("A2: the new reminder is persisted in state 'pending' (a fresh disk read sees it)",
               (loaded(rid) is not None) and loaded(rid).state == "pending")

            # ---- B. ACK FLIPS THE STATE (DURABLY) ---------------------------------------------
            ok_ack = reminders.acknowledge(rid)
            ck("B1: acknowledge(rid) returns True for a real pending reminder", ok_ack is True)
            row = by_id().get(rid)
            ck("B2: state is now 'acknowledged' with acked_at set",
               row is not None and row.state == "acknowledged" and row.acked_at is not None)

            # ---- C. THE WHOLE POINT — ACK CANCELS THE CALL (vs an un-acked control) ------------
            # A CONTROL reminder of the same shape, left UN-acknowledged.
            rid_ctrl = reminders.schedule("leave for the dentist", ack_window_min=0.001, name=N)
            # Run escalation well past every deadline. Only the control (still pending) must escalate.
            fired = reminders.tick(now=time.time() + 3600.0, name=N)
            ck("C1: the ACKNOWLEDGED reminder is NOT escalated on a past-deadline tick (call cancelled)",
               rid not in fired)
            ck("C2: CONTROL — an UN-acknowledged reminder of the same shape IS escalated on that tick "
               "(so ack is what cancels, not that escalation never fires)", fired == [rid_ctrl])
            ck("C3: the acknowledged reminder's state is untouched by the tick (still 'acknowledged')",
               by_id().get(rid).state == "acknowledged")
            ck("C4: the escalated control is now 'escalated' with escalated_at set",
               by_id().get(rid_ctrl).state == "escalated"
               and by_id().get(rid_ctrl).escalated_at is not None)

            # ---- D. HONEST — ack only ever cancels a real, still-pending reminder --------------
            ck("D1: acknowledge('') is False (empty id never claims a cancel)",
               reminders.acknowledge("") is False)
            ck("D2: acknowledge(unknown id) is False",
               reminders.acknowledge("nope-not-a-real-id") is False)
            ck("D3: re-acknowledging an already-acknowledged reminder is False (idempotent, honest)",
               reminders.acknowledge(rid) is False)
            ck("D4: acknowledging an already-ESCALATED reminder is False (you can't un-ring the call)",
               reminders.acknowledge(rid_ctrl) is False)

            # ---- E. ENDPOINT PAYLOAD — exactly what POST /acknowledge emits --------------------
            rid_ep = reminders.schedule("call the bank", ack_window_min=5.0, name=N)
            ck("E1: POST /acknowledge payload for a real pending id is {'ok': true}",
               _endpoint_payload(rid_ep) == b'{"ok": true}')
            ck("E2: POST /acknowledge payload for a junk id is {'ok': false}",
               _endpoint_payload("garbage") == b'{"ok": false}')

            # ---- F. RESTART-SURVIVAL — the cancel survives a reload ----------------------------
            # rid_ep was just acknowledged by E1's endpoint call; a FRESH _load() ('a restart') must
            # still see it acknowledged — a reboot cannot resurrect the cancelled call.
            ck("F1: a fresh _load() ('a restart') still shows the endpoint-acked reminder acknowledged",
               loaded(rid_ep) is not None and loaded(rid_ep).state == "acknowledged")
            ck("F2: and the originally-acked reminder is still acknowledged after the reload",
               loaded(rid) is not None and loaded(rid).state == "acknowledged")
        finally:
            if saved_state is not None:
                reminders._STATE = saved_state

    # ---- HERMETICITY ----------------------------------------------------------------------
    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nACKNOWLEDGE-FLOW CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
