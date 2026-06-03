"""passkey — optional Face ID / Touch ID unlock via WebAuthn, a SECOND layer on top of
the token. Designed so it can NEVER lock you out:

  * Opt-in: nothing is enforced until you enroll a passkey AND it's marked required.
  * Bypass: start the server with ANIMA_NO_PASSKEY=1 to disable enforcement entirely.
  * Inert without the library: enrolling needs `pip install webauthn`; if it's not
    installed you simply can't enroll, and nothing is ever enforced.

After a successful Face ID check the server hands the page a short-lived session token
(localStorage, sent as X-Anima-Sess) which the data routes require while a passkey is
active — the API key alone is no longer enough. The credential is stored under
.anima/passkey.json (encrypted at rest if ANIMA_KEY is set).

NOTE: this is security code that must be tested on the real device/browser; the
py_webauthn API can vary by version. It stays opt-in + bypassable for exactly that
reason.
"""

from __future__ import annotations

import base64
import hmac
import os
import secrets
import time
from pathlib import Path

from .util import load_json, save_json

_PATH = Path(".anima") / "passkey.json"
_PENDING = {"challenge": None}                 # one in-flight challenge (single user)
_SECRET = secrets.token_bytes(32)              # session-signing secret, per server run
SESSION_TTL = 12 * 3600


def available() -> bool:
    try:
        import webauthn  # noqa: F401
        return True
    except Exception:
        return False


def _load() -> dict:
    try:
        d = load_json(_PATH)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def enrolled() -> bool:
    return bool(_load().get("credential"))


def required() -> bool:
    if os.environ.get("ANIMA_NO_PASSKEY") == "1":
        return False
    d = _load()
    return bool(d.get("credential") and d.get("require"))


def status() -> dict:
    return {"available": available(), "enrolled": enrolled(), "required": required(),
            "bypass": os.environ.get("ANIMA_NO_PASSKEY") == "1"}


# --- session token (issued only after a passed Face ID) ---------------------
def issue_session() -> str:
    exp = str(int(time.time() + SESSION_TTL))
    return exp + "." + hmac.new(_SECRET, exp.encode(), "sha256").hexdigest()


def valid_session(token: str) -> bool:
    try:
        exp, sig = (token or "").split(".", 1)
        good = hmac.compare_digest(sig, hmac.new(_SECRET, exp.encode(), "sha256").hexdigest())
        return good and int(exp) > time.time()
    except Exception:
        return False


# --- WebAuthn registration / authentication (lazy import) -------------------
def register_begin(rp_id: str, name: str = "Vera") -> str:
    from webauthn import generate_registration_options, options_to_json
    from webauthn.helpers.structs import (AuthenticatorSelectionCriteria,
                                          ResidentKeyRequirement, UserVerificationRequirement)
    opts = generate_registration_options(
        rp_id=rp_id, rp_name=name, user_name=name, user_id=b"anima-user-1",
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.REQUIRED))
    _PENDING["challenge"] = opts.challenge
    return options_to_json(opts)


def register_finish(credential_json: str, rp_id: str, origin: str) -> dict:
    from webauthn import verify_registration_response
    v = verify_registration_response(credential=credential_json,
                                     expected_challenge=_PENDING["challenge"],
                                     expected_rp_id=rp_id, expected_origin=origin)
    d = _load()
    d["credential"] = {"id": base64.b64encode(v.credential_id).decode(),
                       "pub": base64.b64encode(v.credential_public_key).decode(),
                       "sign_count": v.sign_count}
    d.setdefault("require", True)
    Path(".anima").mkdir(exist_ok=True)
    save_json(_PATH, d)
    _PENDING["challenge"] = None
    return {"ok": True}


def auth_begin(rp_id: str):
    from webauthn import generate_authentication_options, options_to_json
    from webauthn.helpers.structs import PublicKeyCredentialDescriptor, UserVerificationRequirement
    cred = _load().get("credential")
    if not cred:
        return None
    opts = generate_authentication_options(
        rp_id=rp_id,
        allow_credentials=[PublicKeyCredentialDescriptor(id=base64.b64decode(cred["id"]))],
        user_verification=UserVerificationRequirement.REQUIRED)
    _PENDING["challenge"] = opts.challenge
    return options_to_json(opts)


def auth_finish(credential_json: str, rp_id: str, origin: str) -> dict:
    from webauthn import verify_authentication_response
    cred = _load().get("credential") or {}
    v = verify_authentication_response(
        credential=credential_json, expected_challenge=_PENDING["challenge"],
        expected_rp_id=rp_id, expected_origin=origin,
        credential_public_key=base64.b64decode(cred["pub"]),
        credential_current_sign_count=cred.get("sign_count", 0))
    cred["sign_count"] = v.new_sign_count
    d = _load()
    d["credential"] = cred
    save_json(_PATH, d)
    _PENDING["challenge"] = None
    return {"ok": True, "session": issue_session()}


def disable() -> dict:
    d = _load()
    d.pop("credential", None)
    d["require"] = False
    save_json(_PATH, d)
    return {"ok": True}
