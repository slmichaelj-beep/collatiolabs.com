#!/usr/bin/env python3
"""
certify_mail_send — the email compose -> draft -> confirm -> send live path (NEVER auto-sends).

Proves the "Mail-send: Vera composes; the user taps confirm; never auto-send" contract end-to-end,
through the SAME functions the server runs (anima.route.route for the compose, anima.server._draft +
_confirm_send for the draft/send), with the real senders TRIPWIRED so nothing ever leaves the Mac:

  A. OFF BY DEFAULT — a fresh creature has the 'mail' (send) switch False.
  B. OFF IS REFUSED — with it OFF, route.route(compose) returns the honest off-message and produces
     NO send draft; and server._confirm_send refuses to send even a (forged) matching draft. Nothing
     is sent.
  C. COMPOSE -> DRAFT — with 'mail' ON, route.route composes a {kind:mail, to, subject, body} send
     dict (Vera writes a subject when the user didn't), and composing it sends NOTHING; the server
     turns that into a stored draft whose preview carries the subject.
  D. CONFIRM-GATED SEND — server._confirm_send sends EXACTLY once, via applemac.mail_send, only when
     'mail' is ON AND a matching draft id exists; the draft is then consumed (re-confirming the same
     id refuses — no double-send).
  E. PARSE HYGIENE — a mid-sentence mention ("I got an email from Bob") never fabricates a draft; a
     clear imperative ("email bob saying hi") does.

Hermetic + offline: every store (incl. caps) is redirected to a temp dir (gate0_prime_experience.
_temp_store) and applemac.mail_send / imessage_send are tripwired (record-only, never osascript), so
ZERO email is sent. The real .anima is fingerprinted before/after and asserted byte-identical.
Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
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
    from anima import route, caps, server, applemac
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("MAIL-SEND — compose -> draft -> confirm -> send (NEVER auto-sends)")
    print("=" * 72)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # Tripwire the ONLY functions that actually send: record the call, return a benign ok,
    # NEVER touch osascript/Mail. Restored in finally.
    sent = []
    saved_mail, saved_im = applemac.mail_send, applemac.imessage_send
    applemac.mail_send = lambda to, subject, body: (sent.append(("mail", to, subject, body)) or (True, "ok"))
    applemac.imessage_send = lambda to, body: (sent.append(("imessage", to, body)) or (True, "ok"))
    try:
        with _temp_store():
            N = "MailSendCert"
            server._DRAFTS.clear()

            # ---- A. OFF BY DEFAULT ----------------------------------------------------------
            ck("A1: the 'mail' (send) switch is OFF by default", caps.load(N).get("mail") is False)

            # ---- B. OFF IS REFUSED (compose + send) -----------------------------------------
            r = route.route(N, "email bob@example.com saying the report is ready")
            ck("B1: OFF -> route returns an off-message and produces NO send draft",
               (r or {}).get("send") is None and "off" in (r or {}).get("note", "").lower())
            server._DRAFTS["forged"] = {"kind": "mail", "to": "x@y.com", "subject": "s",
                                        "body": "b", "ts": time.time()}
            res = json.loads(server._confirm_send(N, "/mail/send", {"id": "forged"}))
            ck("B2: OFF -> _confirm_send refuses even a matching draft",
               res.get("ok") is False and "off" in res.get("error", "").lower())
            ck("B3: OFF -> nothing was sent", not sent)
            server._DRAFTS.clear()

            # ---- C. COMPOSE -> DRAFT (mail ON) ----------------------------------------------
            caps.save(N, {"mail": True})
            r = route.route(N, "email bob@example.com about the Q3 report saying it is attached and ready")
            s = (r or {}).get("send")
            ck("C1: ON -> route composes a mail send dict (to / subject / body)",
               bool(s) and s.get("kind") == "mail" and s.get("to") == "bob@example.com"
               and bool(s.get("body")) and bool(s.get("subject")))
            ck("C2: composing the draft SENT nothing (route never sends)", not sent)
            d = json.loads(server._draft("/mail/draft",
                                         {"to": s["to"], "body": s["body"], "subject": s["subject"]}))
            ck("C3: the server stores a draft whose preview carries the subject",
               d.get("ok") and d["draft"]["kind"] == "mail" and bool(d["draft"].get("subject")))
            did = d["draft"]["id"]

            # ---- D. CONFIRM-GATED SEND ------------------------------------------------------
            res = json.loads(server._confirm_send(N, "/mail/send", {"id": did}))
            ck("D1: explicit confirm sends EXACTLY once via applemac.mail_send (to the right address)",
               res.get("sent") is True and len(sent) == 1
               and sent[0][0] == "mail" and sent[0][1] == "bob@example.com")
            ck("D2: the draft is consumed on send", server._DRAFTS.get(did) is None)
            res2 = json.loads(server._confirm_send(N, "/mail/send", {"id": did}))
            ck("D3: re-confirming the consumed draft refuses (no double-send)",
               res2.get("ok") is False and len(sent) == 1)
            server._DRAFTS.clear()

            # ---- E. PARSE HYGIENE -----------------------------------------------------------
            ck("E1: a mid-sentence mention does NOT fabricate a draft",
               route._parse_mail_send("I got an email from Bob yesterday and it was great") is None)
            ck("E2: a clear imperative DOES compose a send",
               (route._parse_mail_send("email bob saying hi") or {}).get("to") == "bob")
            ck("E3: Vera derives a non-blank subject from the body when none is given",
               bool(route._default_subject("can we move the meeting to friday")) and
               route._default_subject("") == "(no subject)")
    finally:
        applemac.mail_send, applemac.imessage_send = saved_mail, saved_im
        try:
            server._DRAFTS.clear()
        except Exception:
            pass

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nMAIL-SEND CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
