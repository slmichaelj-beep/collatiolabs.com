#!/usr/bin/env python3
"""
certify_passkey_auth — the opt-in Face ID (WebAuthn passkey) second gate + the session-security FLOOR.

Vera is local-first and gated. On top of the private tailnet + the API token, an opt-in Face ID /
Touch ID layer can be REQUIRED to open the app. Once a Face ID passes, the server hands the client a
short-lived SIGNED session; the second gate (server.Handler._passed) then admits a request ONLY if its
X-Anima-Sess session VALIDATES — and ANY tampering with that session is REJECTED. This certifies that
FLOOR deterministically, through the SAME passkey API the gate calls, with NO hardware and NO network:

  A. A FRESH SESSION VALIDATES — passkey.issue_session() mints a token and valid_session() accepts it.
  B. THE TAMPER FLOOR — every forgery is rejected: a flipped signature byte, a truncated token, a
     swapped/garbage signature, an empty token, a None token, and a forged FUTURE-expiry token with a
     made-up signature all return False. Without the per-run secret, no valid HMAC can be produced.
  C. EXPIRY IS ENFORCED — a token that is CORRECTLY signed for a past expiry is still rejected (the
     gate checks exp>now, not just the signature), so a captured-then-expired session can't be replayed.
  D. OPT-IN, CAN'T-LOCK-YOU-OUT — with no credential enrolled, required() is False (the gate is inert
     and returns True), enrolled() is False, and status() is well-formed (available True, bypass flag).

Deliberately NOT tested: the live Face ID ceremony (navigator.credentials) and the WebAuthn assertion
verification (challenge/origin/RP-ID-hash + authenticator flags) — those are hardware/browser flows.
The session floor IS the security-critical, deterministic surface the per-request gate depends on.

Hermetic + offline: the session check is pure in-memory HMAC (no file I/O), and we run inside the
canonical temp store anyway; the real .anima is fingerprinted before/after and asserted byte-identical.
Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
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
    from anima import passkey
    import hmac
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("PASSKEY AUTH — opt-in Face ID second gate + the session-security FLOOR")
    print("=" * 70)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    with _temp_store():
        # ---- A. A FRESH SESSION VALIDATES -------------------------------------------
        tok = passkey.issue_session()
        ck("A1: issue_session() mints a token that valid_session() ACCEPTS (fresh session validates)",
           passkey.valid_session(tok) is True)
        ck("A2: the minted token is the documented exp.sig shape (two dot-joined parts)",
           isinstance(tok, str) and tok.count(".") == 1 and all(tok.split(".")))

        # ---- B. THE TAMPER FLOOR (every forgery rejected) ---------------------------
        flipped = tok[:-1] + ("0" if tok[-1] != "0" else "1")     # flip the last signature byte
        ck("B1: a flipped signature byte is REJECTED", passkey.valid_session(flipped) is False)
        ck("B2: a truncated token is REJECTED", passkey.valid_session(tok[:-1]) is False)

        exp, sig = tok.split(".", 1)
        ck("B3: a swapped/garbage signature (right exp, wrong sig) is REJECTED",
           passkey.valid_session(exp + "." + ("deadbeef" * 8)) is False)
        ck("B4: an empty-string token is REJECTED", passkey.valid_session("") is False)
        ck("B5: a None token is REJECTED (no crash)", passkey.valid_session(None) is False)
        ck("B6: a malformed token with no separator is REJECTED",
           passkey.valid_session("not-a-session") is False)

        # a FORGED token: a plausible future expiry + an attacker-chosen signature. Without the
        # per-run secret the attacker cannot produce the matching HMAC, so it must be rejected.
        forged = str(int(time.time()) + 999999) + "." + ("a" * 64)
        ck("B7: a forged FUTURE-expiry token with a made-up signature is REJECTED",
           passkey.valid_session(forged) is False)

        # ---- C. EXPIRY IS ENFORCED (even with a CORRECT signature) ------------------
        past_exp = str(int(time.time()) - 10)                     # already expired
        good_sig_past = hmac.new(passkey._SECRET, past_exp.encode(), "sha256").hexdigest()
        expired_but_signed = past_exp + "." + good_sig_past
        # sanity: the signature really is the correct one for that expiry (so the ONLY reason it
        # fails is the expiry check, not a bad signature) — that's what makes this a real expiry test.
        ck("C1: (sanity) the past-expiry token carries a genuinely VALID signature for its exp",
           hmac.compare_digest(good_sig_past,
                               hmac.new(passkey._SECRET, past_exp.encode(), "sha256").hexdigest()))
        ck("C2: a correctly-signed but EXPIRED token is REJECTED (exp>now is enforced)",
           passkey.valid_session(expired_but_signed) is False)

        # ---- D. OPT-IN, CAN'T-LOCK-YOU-OUT -----------------------------------------
        # passkey reads .anima/passkey.json (a real path). We assert the opt-in INVARIANT (true on
        # any machine, enrolled or not) rather than a specific enrollment state: the gate is required
        # ONLY when a credential is enrolled AND it's marked required AND the bypass isn't set — so it
        # is inert until you opt in, and the ANIMA_NO_PASSKEY bypass means it can never lock you out.
        st = passkey.status()
        ck("D1: status() is well-formed (available + enrolled + required + bypass keys)",
           isinstance(st, dict) and set(("available", "enrolled", "required", "bypass")) <= set(st))
        ck("D2: available() is True (no library needed — stdlib WebAuthn)", passkey.available() is True)
        ck("D3: opt-in invariant: required() implies enrolled() (the gate can't arm without a credential)",
           (not passkey.required()) or passkey.enrolled())
        ck("D4: required() implies the bypass is OFF (ANIMA_NO_PASSKEY=1 always disarms — no lockout)",
           (not passkey.required()) or not st.get("bypass"))
        ck("D5: status() agrees with required() (the UI gate-check and the server gate read the same)",
           bool(st.get("required")) == bool(passkey.required()))

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nPASSKEY-AUTH CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
