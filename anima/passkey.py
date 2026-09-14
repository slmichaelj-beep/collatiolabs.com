"""passkey — Face ID / Touch ID unlock via WebAuthn, a second layer on top of the token.

Uses the device's platform authenticator (Face ID / Touch ID) and verifies the assertion
server-side: the challenge we issued, the origin, the RP-ID hash, user-PRESENT/user-VERIFIED
flags, and the authenticator's cryptographic signature over authenticatorData || SHA256(clientDataJSON).
Supported public-key algorithms are ES256 and RS256.

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

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
except Exception as _crypto_error:  # pragma: no cover - exercised by status()/available() when absent.
    InvalidSignature = None
    hashes = ec = padding = rsa = None
    _CRYPTO_IMPORT_ERROR = str(_crypto_error)
else:
    _CRYPTO_IMPORT_ERROR = ""

_PENDING = {"challenge": ""}                   # one in-flight challenge (single user)
_SECRET = secrets.token_bytes(32)              # session-signing secret, per server run
SESSION_TTL = 12 * 3600


def _path() -> Path:
    return Path(os.environ.get("ANIMA_STORE", ".anima")) / "passkey.json"


def _b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _unb64u(s: str) -> bytes:
    s = (s or "").replace("-", "+").replace("_", "/")
    return base64.b64decode(s + "=" * ((4 - len(s) % 4) % 4))


def available() -> bool:
    return not _CRYPTO_IMPORT_ERROR


def _load() -> dict:
    try:
        d = load_json(_path())
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def enrolled() -> bool:
    return bool(_load().get("credential"))


def required() -> bool:
    if os.environ.get("ANIMA_NO_PASSKEY") == "1":
        return False
    d = _load()
    cred = d.get("credential") or {}
    return bool(cred.get("public_key_cose") and d.get("require"))


def status() -> dict:
    d = _load()
    cred = d.get("credential") or {}
    return {"available": available(), "enrolled": bool(cred), "required": required(),
            "bypass": os.environ.get("ANIMA_NO_PASSKEY") == "1",
            "signature_verified": bool(cred.get("public_key_cose")),
            "upgrade_required": bool(cred and not cred.get("public_key_cose")),
            "error": _CRYPTO_IMPORT_ERROR or None}


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


# --- Minimal CBOR + WebAuthn helpers ---------------------------------------
def _cbor_len(data: bytes, pos: int, addl: int) -> tuple[int, int]:
    if addl < 24:
        return addl, pos
    if addl == 24:
        return data[pos], pos + 1
    if addl == 25:
        return int.from_bytes(data[pos:pos + 2], "big"), pos + 2
    if addl == 26:
        return int.from_bytes(data[pos:pos + 4], "big"), pos + 4
    if addl == 27:
        return int.from_bytes(data[pos:pos + 8], "big"), pos + 8
    raise ValueError("unsupported indefinite CBOR length")


def _cbor_decode_one(data: bytes, pos: int = 0):
    if pos >= len(data):
        raise ValueError("truncated CBOR")
    initial = data[pos]
    pos += 1
    major, addl = initial >> 5, initial & 0x1F
    n, pos = _cbor_len(data, pos, addl)
    if major == 0:
        return n, pos
    if major == 1:
        return -1 - n, pos
    if major == 2:
        end = pos + n
        if end > len(data):
            raise ValueError("truncated CBOR bytes")
        return data[pos:end], end
    if major == 3:
        end = pos + n
        if end > len(data):
            raise ValueError("truncated CBOR text")
        return data[pos:end].decode("utf-8"), end
    if major == 4:
        arr = []
        for _ in range(n):
            v, pos = _cbor_decode_one(data, pos)
            arr.append(v)
        return arr, pos
    if major == 5:
        m = {}
        for _ in range(n):
            k, pos = _cbor_decode_one(data, pos)
            v, pos = _cbor_decode_one(data, pos)
            m[k] = v
        return m, pos
    if major == 6:
        return _cbor_decode_one(data, pos)
    if major == 7:
        if addl == 20:
            return False, pos
        if addl == 21:
            return True, pos
        if addl in (22, 23):
            return None, pos
    raise ValueError("unsupported CBOR value")


def _cbor_decode(data: bytes):
    obj, pos = _cbor_decode_one(data, 0)
    if pos != len(data):
        raise ValueError("trailing CBOR bytes")
    return obj


def _require_crypto():
    if _CRYPTO_IMPORT_ERROR:
        raise ValueError("cryptography unavailable: " + _CRYPTO_IMPORT_ERROR)


def _client_data(cred: dict, kind: str, origin: str) -> tuple[bytes, dict]:
    raw = _unb64u(cred["response"]["clientDataJSON"])
    cd = json.loads(raw)
    if cd.get("type") != kind:
        raise ValueError("wrong ceremony type")
    if cd.get("challenge") != _PENDING["challenge"] or not _PENDING["challenge"]:
        raise ValueError("challenge mismatch")
    if cd.get("origin") != origin:
        raise ValueError("origin mismatch")
    return raw, cd


def _auth_data_header(ad: bytes, rp_id: str) -> tuple[int, int]:
    if len(ad) < 37:
        raise ValueError("authenticatorData too short")
    if ad[:32] != hashlib.sha256(rp_id.encode()).digest():
        raise ValueError("rp-id mismatch")
    flags = ad[32]
    if not (flags & 0x01):
        raise ValueError("user not present")
    if not (flags & 0x04):
        raise ValueError("user not verified (Face ID)")
    return flags, int.from_bytes(ad[33:37], "big")


def _attested_credential(ad: bytes) -> tuple[str, bytes, dict, int]:
    if len(ad) < 55:
        raise ValueError("attested credential data too short")
    pos = 37 + 16
    cred_len = int.from_bytes(ad[pos:pos + 2], "big")
    pos += 2
    cred_id = ad[pos:pos + cred_len]
    if len(cred_id) != cred_len:
        raise ValueError("credential id truncated")
    pos += cred_len
    cose_start = pos
    cose, pos = _cbor_decode_one(ad, pos)
    cose_bytes = ad[cose_start:pos]
    if not isinstance(cose, dict):
        raise ValueError("credential public key is not a COSE map")
    return _b64u(cred_id), cose_bytes, cose, pos


def _parse_registration(cred: dict, rp_id: str) -> dict:
    att = _cbor_decode(_unb64u(cred["response"]["attestationObject"]))
    if not isinstance(att, dict) or not isinstance(att.get("authData"), (bytes, bytearray)):
        raise ValueError("bad attestation object")
    ad = bytes(att["authData"])
    flags, sign_count = _auth_data_header(ad, rp_id)
    if not (flags & 0x40):
        raise ValueError("missing attested credential data")
    cred_id, cose_bytes, cose, _ = _attested_credential(ad)
    if cred.get("rawId") != cred_id:
        raise ValueError("credential id mismatch")
    alg = cose.get(3)
    if alg not in (-7, -257):
        raise ValueError("unsupported public-key algorithm")
    _public_key_from_cose(cose)
    return {"id": cred_id, "alg": alg, "public_key_cose": _b64u(cose_bytes),
            "sign_count": sign_count, "fmt": str(att.get("fmt") or "")}


def _public_key_from_cose(cose: dict):
    _require_crypto()
    alg = cose.get(3)
    if alg == -7:
        if cose.get(1) != 2 or cose.get(-1) != 1:
            raise ValueError("unsupported ES256 COSE key")
        x, y = cose.get(-2), cose.get(-3)
        if not isinstance(x, bytes) or not isinstance(y, bytes):
            raise ValueError("bad ES256 coordinates")
        return ec.EllipticCurvePublicNumbers(
            int.from_bytes(x, "big"), int.from_bytes(y, "big"), ec.SECP256R1()
        ).public_key()
    if alg == -257:
        if cose.get(1) != 3:
            raise ValueError("unsupported RSA COSE key")
        n, e = cose.get(-1), cose.get(-2)
        if not isinstance(n, bytes) or not isinstance(e, bytes):
            raise ValueError("bad RSA key")
        return rsa.RSAPublicNumbers(int.from_bytes(e, "big"), int.from_bytes(n, "big")).public_key()
    raise ValueError("unsupported public-key algorithm")


def _verify_signature(saved: dict, signature: bytes, signed_data: bytes) -> None:
    cose = _cbor_decode(_unb64u(saved.get("public_key_cose", "")))
    pub = _public_key_from_cose(cose)
    try:
        if saved.get("alg") == -7:
            pub.verify(signature, signed_data, ec.ECDSA(hashes.SHA256()))
        elif saved.get("alg") == -257:
            pub.verify(signature, signed_data, padding.PKCS1v15(), hashes.SHA256())
        else:
            raise ValueError("unsupported public-key algorithm")
    except InvalidSignature:
        raise ValueError("signature mismatch")


# --- WebAuthn (registration / authentication) ------------------------------
def register_begin(rp_id: str, name: str = "Vera") -> str:
    _require_crypto()
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


def register_finish(cred: dict, rp_id: str, origin: str) -> dict:
    try:
        _client_data(cred, "webauthn.create", origin)
        stored = _parse_registration(cred, rp_id)
        d = _load()
        d["credential"] = stored
        d.setdefault("require", True)
        _path().parent.mkdir(exist_ok=True)
        save_json(_path(), d)
        _PENDING["challenge"] = ""
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def auth_begin(rp_id: str):
    _require_crypto()
    cred = _load().get("credential")
    if not cred:
        return None
    if not cred.get("public_key_cose"):
        return json.dumps({"error": "stored passkey must be re-enrolled for signature verification"})
    ch = secrets.token_urlsafe(32)
    _PENDING["challenge"] = ch
    return json.dumps({"challenge": ch, "rpId": rp_id, "timeout": 60000,
                       "userVerification": "required",
                       "allowCredentials": [{"type": "public-key", "id": cred["id"]}]})


def auth_finish(cred: dict, rp_id: str, origin: str) -> dict:
    try:
        _require_crypto()
        saved = _load().get("credential") or {}
        if cred.get("rawId") != saved.get("id"):
            raise ValueError("unknown credential")
        if not saved.get("public_key_cose"):
            raise ValueError("stored passkey must be re-enrolled for signature verification")
        client_data_json, _ = _client_data(cred, "webauthn.get", origin)
        ad = _unb64u(cred["response"]["authenticatorData"])
        _, sign_count = _auth_data_header(ad, rp_id)
        signature = _unb64u(cred["response"]["signature"])
        _verify_signature(saved, signature, ad + hashlib.sha256(client_data_json).digest())
        old_count = int(saved.get("sign_count") or 0)
        if sign_count and old_count and sign_count <= old_count:
            raise ValueError("sign count did not increase")
        if sign_count:
            d = _load()
            d.setdefault("credential", {})["sign_count"] = sign_count
            save_json(_path(), d)
        _PENDING["challenge"] = ""
        return {"ok": True, "session": issue_session()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def disable() -> dict:
    d = _load()
    d.pop("credential", None)
    d["require"] = False
    _path().parent.mkdir(exist_ok=True)
    save_json(_path(), d)
    return {"ok": True}
