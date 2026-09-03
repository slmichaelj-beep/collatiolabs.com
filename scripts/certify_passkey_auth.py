#!/usr/bin/env python3
"""
certify_passkey_auth — the opt-in Face ID (WebAuthn passkey) second gate + the session-security FLOOR.

Vera is local-first and gated. On top of the private tailnet + the API token, an opt-in Face ID /
Touch ID layer can be REQUIRED to open the app. Once a Face ID passes, the server hands the browser a
short-lived SIGNED session in an HttpOnly/SameSite cookie; API clients may still send that session in
X-Anima-Sess. The second gate (server.Handler._passed) admits a request ONLY if that session VALIDATES
— and ANY tampering with that session is REJECTED. This certifies that FLOOR deterministically, through
the SAME passkey API the gate calls, with NO hardware and NO network:

  A. A FRESH SESSION VALIDATES — passkey.issue_session() mints a token and valid_session() accepts it.
  B. THE TAMPER FLOOR — every forgery is rejected: a flipped signature byte, a truncated token, a
     swapped/garbage signature, an empty token, a None token, and a forged FUTURE-expiry token with a
     made-up signature all return False. Without the per-run secret, no valid HMAC can be produced.
  C. EXPIRY IS ENFORCED — a token that is CORRECTLY signed for a past expiry is still rejected (the
     gate checks exp>now, not just the signature), so a captured-then-expired session can't be replayed.
  D. OPT-IN, CAN'T-LOCK-YOU-OUT — with no credential enrolled, required() is False (the gate is inert
     and returns True), enrolled() is False, and status() is well-formed (available True, bypass flag).

This cert does not need actual Face ID hardware: it builds a deterministic synthetic WebAuthn
credential, registers it through passkey.register_finish(), and authenticates through
passkey.auth_finish() with a real cryptographic signature over authenticatorData || SHA256(clientDataJSON).
The live navigator.credentials browser ceremony remains hardware/manual, but the server verifier is
covered deterministically here.

Hermetic + offline: the session check is pure in-memory HMAC (no file I/O), and we run inside the
canonical temp store anyway; the real .anima is fingerprinted before/after and asserted byte-identical.
Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import base64
import hashlib
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


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _cbor_head(major: int, n: int) -> bytes:
    if n < 24:
        return bytes([(major << 5) | n])
    if n < 256:
        return bytes([(major << 5) | 24, n])
    if n < 65536:
        return bytes([(major << 5) | 25]) + n.to_bytes(2, "big")
    return bytes([(major << 5) | 26]) + n.to_bytes(4, "big")


def _cbor(v) -> bytes:
    if isinstance(v, int):
        if v >= 0:
            return _cbor_head(0, v)
        return _cbor_head(1, -1 - v)
    if isinstance(v, bytes):
        return _cbor_head(2, len(v)) + v
    if isinstance(v, str):
        raw = v.encode("utf-8")
        return _cbor_head(3, len(raw)) + raw
    if isinstance(v, list):
        return _cbor_head(4, len(v)) + b"".join(_cbor(x) for x in v)
    if isinstance(v, dict):
        out = _cbor_head(5, len(v))
        for k, val in v.items():
            out += _cbor(k) + _cbor(val)
        return out
    raise TypeError(type(v).__name__)


def _client_data(kind: str, challenge: str, origin: str) -> bytes:
    return json.dumps(
        {"type": kind, "challenge": challenge, "origin": origin},
        separators=(",", ":"),
    ).encode("utf-8")


def main() -> int:
    from anima import passkey
    from anima.util import save_json
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
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
        ck("D2: available() is True (cryptography-backed WebAuthn verifier is present)",
           passkey.available() is True)
        ck("D3: opt-in invariant: required() implies enrolled() (the gate can't arm without a credential)",
           (not passkey.required()) or passkey.enrolled())
        ck("D4: required() implies the bypass is OFF (ANIMA_NO_PASSKEY=1 always disarms — no lockout)",
           (not passkey.required()) or not st.get("bypass"))
        ck("D5: status() agrees with required() (the UI gate-check and the server gate read the same)",
           bool(st.get("required")) == bool(passkey.required()))

        # ---- E. FULL WEBAUTHN SIGNATURE VERIFICATION ------------------------------
        rp_id = "localhost"
        origin = "https://localhost"
        private_key = ec.generate_private_key(ec.SECP256R1())
        numbers = private_key.public_key().public_numbers()
        cose_key = {
            1: 2,                         # kty EC2
            3: -7,                        # alg ES256
            -1: 1,                        # crv P-256
            -2: numbers.x.to_bytes(32, "big"),
            -3: numbers.y.to_bytes(32, "big"),
        }
        cred_id = b"synthetic-passkey-credential"
        rp_hash = hashlib.sha256(rp_id.encode()).digest()

        reg_opts = json.loads(passkey.register_begin(rp_id))
        reg_client = _client_data("webauthn.create", reg_opts["challenge"], origin)
        reg_auth_data = (
            rp_hash
            + bytes([0x45])                # UP + UV + AT
            + (1).to_bytes(4, "big")
            + (b"\x00" * 16)
            + len(cred_id).to_bytes(2, "big")
            + cred_id
            + _cbor(cose_key)
        )
        reg_cred = {
            "rawId": _b64u(cred_id),
            "response": {
                "clientDataJSON": _b64u(reg_client),
                "attestationObject": _b64u(_cbor({
                    "fmt": "none",
                    "authData": reg_auth_data,
                    "attStmt": {},
                })),
            },
        }
        reg = passkey.register_finish(reg_cred, rp_id, origin)
        stored = passkey._load().get("credential") or {}
        ck("E1: register_finish() stores a credential public key for full assertion verification",
           reg.get("ok") is True and stored.get("public_key_cose") and stored.get("alg") == -7)
        ck("E2: a signature-capable credential arms required() when require=true",
           passkey.required() is True and passkey.status().get("signature_verified") is True)

        def assertion(counter: int, *, flags: int = 0x05, tamper_sig: bool = False,
                      challenge_override: str | None = None) -> dict:
            auth_opts = json.loads(passkey.auth_begin(rp_id))
            challenge = challenge_override or auth_opts["challenge"]
            client = _client_data("webauthn.get", challenge, origin)
            auth_data = rp_hash + bytes([flags]) + int(counter).to_bytes(4, "big")
            sig = private_key.sign(auth_data + hashlib.sha256(client).digest(), ec.ECDSA(hashes.SHA256()))
            if tamper_sig:
                sig = sig[:-1] + bytes([sig[-1] ^ 0x01])
            return {
                "rawId": _b64u(cred_id),
                "response": {
                    "authenticatorData": _b64u(auth_data),
                    "clientDataJSON": _b64u(client),
                    "signature": _b64u(sig),
                },
            }

        good = passkey.auth_finish(assertion(2), rp_id, origin)
        ck("E3: auth_finish() accepts a valid WebAuthn assertion signature and issues a session",
           good.get("ok") is True and passkey.valid_session(good.get("session", "")) is True)
        bad_sig = passkey.auth_finish(assertion(3, tamper_sig=True), rp_id, origin)
        ck("E4: a tampered WebAuthn assertion signature is REJECTED",
           bad_sig.get("ok") is False and "signature" in bad_sig.get("error", ""))
        no_uv = passkey.auth_finish(assertion(3, flags=0x01), rp_id, origin)
        ck("E5: an assertion without user-verified/Face-ID flag is REJECTED",
           no_uv.get("ok") is False and "verified" in no_uv.get("error", ""))
        bad_challenge = passkey.auth_finish(assertion(3, challenge_override="wrong-challenge"), rp_id, origin)
        ck("E6: an assertion signed over the wrong challenge is REJECTED",
           bad_challenge.get("ok") is False and "challenge" in bad_challenge.get("error", ""))
        replay_counter = passkey.auth_finish(assertion(2), rp_id, origin)
        ck("E7: a non-increasing authenticator sign counter is REJECTED when counters are present",
           replay_counter.get("ok") is False and "sign count" in replay_counter.get("error", ""))

        save_json(passkey._path(), {"credential": {"id": _b64u(cred_id)}, "require": True})
        legacy = passkey.status()
        ck("E8: a legacy rawId-only credential is visible as upgrade_required, but does NOT arm required()",
           legacy.get("upgrade_required") is True and legacy.get("required") is False
           and passkey.required() is False)

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nPASSKEY-AUTH CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
