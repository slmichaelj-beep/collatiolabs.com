"""passkey — Face ID / Touch ID unlock via WebAuthn, a second layer on top of the token.

NO extra dependencies. It uses the device's platform authenticator (Face ID / Touch ID)
and verifies the assertion server-side: the challenge we issued, the origin, the RP-ID
hash, and the authenticator flags (user-PRESENT + user-VERIFIED, i.e. a real Face ID).
It does NOT verify the assertion's cryptographic signature (that needs a crypto library),
so this is a strong DEVICE-PRESENCE gate — Face ID is required to open the app — layered
on top of the token + private tailnet, which remain the primary network gate.

Can never lock you out:
  * Opt-in: nothing enforced until you enroll AND it's marked required.
  * Bypass: start the server with ANIMA_NO_PASSKEY=1 (printed in the banner).
  * Inert until you enroll a credential.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

from .util import load_json, save_json

_PATH = Path(".anima") / "passkey.json"
_PENDING = {"challenge": ""}                   # one in-flight challenge (single user)
_SECRET = secrets.token_bytes(32)              # session-signing secret, per server run
SESSION_TTL = 12 * 3600


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64u(s: str) -> bytes:
    s = (s or "").replace("-", "+").replace("_", "/")
    return base64.b64decode(s + "=" * ((4 - len(s) % 4) % 4))


def available() -> bool:
    return True                                # no library needed anymore


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
    return {"available": True, "enrolled": enrolled(), "required": required(),
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


# --- WebAuthn (registration / authentication), stdlib-only ------------------
def register_begin(rp_id: str, name: str = "Vera") -> str:
    ch = secrets.token_urlsafe(32)
    _PENDING["challenge"] = ch
    return json.dumps({
        "challenge": ch,
        "rp": {"id": rp_id, "name": name},
        "user": {"id": _b64u(b"anima-user-1"), "name": name, "displayName": name},
        "pubKeyCredParams": [{"type": "public-key", "alg": -7}, {"type": "public-key", "alg": -257}],
        "authenticatorSelection": {"authenticatorAttachment": "platform",
                                   "userVerification": "required", "residentKey": "preferred"},
        "timeout": 60000, "attestation": "none"})


def _check_client_data(cred: dict, kind: str, origin: str):
    cd = json.loads(_unb64u(cred["response"]["clientDataJSON"]))
    if cd.get("type") != kind:
        raise ValueError("wrong ceremony type")
    if cd.get("challenge") != _PENDING["challenge"] or not _PENDING["challenge"]:
        raise ValueError("challenge mismatch")
    if cd.get("origin") != origin:
        raise ValueError("origin mismatch")


def register_finish(cred: dict, rp_id: str, origin: str) -> dict:
    try:
        _check_client_data(cred, "webauthn.create", origin)
        d = _load()
        d["credential"] = {"id": cred["rawId"]}      # store the credential id (base64url)
        d.setdefault("require", True)
        Path(".anima").mkdir(exist_ok=True)
        save_json(_PATH, d)
        _PENDING["challenge"] = ""
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def auth_begin(rp_id: str):
    cred = _load().get("credential")
    if not cred:
        return None
    ch = secrets.token_urlsafe(32)
    _PENDING["challenge"] = ch
    return json.dumps({"challenge": ch, "rpId": rp_id, "timeout": 60000,
                       "userVerification": "required",
                       "allowCredentials": [{"type": "public-key", "id": cred["id"]}]})


def auth_finish(cred: dict, rp_id: str, origin: str) -> dict:
    try:
        saved = _load().get("credential") or {}
        if cred.get("rawId") != saved.get("id"):
            raise ValueError("unknown credential")
        _check_client_data(cred, "webauthn.get", origin)
        ad = _unb64u(cred["response"]["authenticatorData"])
        if ad[:32] != hashlib.sha256(rp_id.encode()).digest():
            raise ValueError("rp-id mismatch")
        flags = ad[32]
        if not (flags & 0x01):
            raise ValueError("user not present")
        if not (flags & 0x04):
            raise ValueError("user not verified (Face ID)")
        _PENDING["challenge"] = ""
        return {"ok": True, "session": issue_session()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def disable() -> dict:
    d = _load()
    d.pop("credential", None)
    d["require"] = False
    save_json(_PATH, d)
    return {"ok": True}
