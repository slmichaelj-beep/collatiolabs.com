"""
voip_push — the Mac side that *rings the phone*.

Sends an APNs VoIP push to the iPhone's PushKit token over APNs' HTTP/2 endpoint,
authenticated with a JWT signed by your APNs Auth Key (.p8). When VeraCall (the iOS app)
receives this push it reports an incoming call to CallKit, so iOS shows the native
full-screen swipe-to-answer screen — even if the app was backgrounded or terminated.
After the user swipes to answer, the app opens a WebRTC call to anima/call_server.py.

This file sends NOTHING by default and stores NO secrets. Everything comes from env:
    APNS_KEY_ID    — the 10-char Key ID of your APNs Auth Key
    APNS_TEAM_ID   — your 10-char Apple Developer Team ID
    APNS_BUNDLE_ID — the app's bundle id, e.g. ai.guruu.vera.VeraCall
                     (the VoIP push "topic" is <bundle_id>.voip)
    APNS_KEY_PATH  — path to the AuthKey_XXXXXXXXXX.p8 file
    APNS_ENV       — "sandbox" (default; for development builds run from Xcode)
                     or "production" (TestFlight / App Store builds)

The phone's VoIP token is stored by anima/server.py's /device endpoint
(.anima/<name>.device.json -> {"voip_token": ...}); see ring() / __main__ below, which
will read it from there if you don't pass one explicitly.

Dependencies (HTTP/2 + JWT signing):
    pip install httpx[http2] PyJWT cryptography
(httpx[http2] pulls in the `h2` package; APNs requires HTTP/2.)

CLI (send a test ring):
    # ring whatever token is registered for the default creature ("Vera"):
    python3 -m anima.voip_push --ring
    # or ring an explicit token:
    python3 -m anima.voip_push --token <hex_voip_token> --handle "Vera"
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional


# --- JWT provider token (cached, refreshed before APNs' 1h limit) ------------
_TOKEN_CACHE: dict[str, Any] = {"jwt": None, "iat": 0.0}
_TOKEN_TTL = 50 * 60  # refresh at 50 min; APNs rejects tokens older than 60 min


def _require_env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise SystemExit(
            f"voip_push: ${name} is not set. Required env: APNS_KEY_ID, APNS_TEAM_ID, "
            f"APNS_BUNDLE_ID, APNS_KEY_PATH (see the module docstring / README)."
        )
    return val


def _provider_jwt() -> str:
    """A short-lived ES256 JWT signed with the .p8 key, identifying you to APNs.

    APNs accepts the same provider token for up to 1 hour, so we cache and reuse it
    (re-minting on every push will get you 429 TooManyProviderTokenUpdates)."""
    now = time.time()
    if _TOKEN_CACHE["jwt"] and (now - _TOKEN_CACHE["iat"]) < _TOKEN_TTL:
        return _TOKEN_CACHE["jwt"]

    try:
        import jwt  # PyJWT
    except ImportError as e:  # pragma: no cover - dependency hint
        raise SystemExit("voip_push: PyJWT is required — `pip install PyJWT cryptography`") from e

    key_id = _require_env("APNS_KEY_ID")
    team_id = _require_env("APNS_TEAM_ID")
    key_path = Path(_require_env("APNS_KEY_PATH")).expanduser()
    if not key_path.is_file():
        raise SystemExit(f"voip_push: APNS_KEY_PATH does not exist: {key_path}")

    signing_key = key_path.read_text()
    token = jwt.encode(
        {"iss": team_id, "iat": int(now)},
        signing_key,
        algorithm="ES256",
        headers={"alg": "ES256", "kid": key_id},
    )
    # PyJWT>=2 returns str; older returns bytes. Normalise.
    if isinstance(token, bytes):
        token = token.decode("ascii")
    _TOKEN_CACHE["jwt"] = token
    _TOKEN_CACHE["iat"] = now
    return token


def _apns_host() -> str:
    env = os.environ.get("APNS_ENV", "sandbox").strip().lower()
    # Development builds (run from Xcode, aps-environment=development) -> sandbox.
    # TestFlight/App Store builds (aps-environment=production) -> production.
    return "api.push.apple.com" if env in ("prod", "production") else "api.sandbox.push.apple.com"


def send_voip_push(device_token: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Send one VoIP push to `device_token` carrying `payload` (the app's
    PKPushPayload.dictionaryPayload). Returns {"ok", "status", "apns_id", "reason"}.

    Raises SystemExit if required env / deps are missing. Network and APNs-rejection
    outcomes are returned, not raised, so a caller (e.g. the reminder subsystem) can
    decide what to do.

    The push is sent with apns-push-type: voip and topic <APNS_BUNDLE_ID>.voip, which is
    what PushKit requires; a high priority (10) and no collapse id so each ring is delivered.
    """
    device_token = (device_token or "").strip()
    if not device_token:
        return {"ok": False, "status": 0, "apns_id": None, "reason": "empty device_token"}

    try:
        import httpx
    except ImportError as e:  # pragma: no cover - dependency hint
        raise SystemExit("voip_push: httpx is required — `pip install httpx[http2]`") from e

    bundle_id = _require_env("APNS_BUNDLE_ID")
    topic = f"{bundle_id}.voip"            # VoIP pushes use the .voip topic suffix
    host = _apns_host()
    url = f"https://{host}/3/device/{device_token}"
    apns_id = str(uuid.uuid4()).upper()

    headers = {
        "authorization": f"bearer {_provider_jwt()}",
        "apns-topic": topic,
        "apns-push-type": "voip",
        "apns-priority": "10",
        "apns-expiration": "0",           # deliver now or not at all (a ring is ephemeral)
        "apns-id": apns_id,
    }
    body = json.dumps(payload).encode("utf-8")

    # APNs requires HTTP/2. httpx needs http2=True (and the h2 package, via httpx[http2]).
    try:
        with httpx.Client(http2=True, timeout=10.0) as client:
            resp = client.post(url, headers=headers, content=body)
    except Exception as exc:  # network error, TLS, etc.
        return {"ok": False, "status": 0, "apns_id": apns_id, "reason": f"network: {exc}"}

    reason = ""
    if resp.status_code != 200:
        try:
            reason = (resp.json() or {}).get("reason", "")
        except Exception:
            reason = resp.text[:200]
    return {
        "ok": resp.status_code == 200,
        "status": resp.status_code,
        "apns_id": resp.headers.get("apns-id", apns_id),
        "reason": reason,
    }


# --- convenience: ring the phone, reading the stored token if none is given --
def _stored_voip_token(name: str) -> Optional[str]:
    """Read the VoIP token that anima/server.py's /device endpoint persisted under
    .anima/<name>.device.json. We import the server's own loader so encryption-at-rest
    (ANIMA_KEY) is honoured exactly the same way server.py wrote it."""
    try:
        from . import server  # reuse the server's STORE path + decrypting load_json
        rec = server.load_json(server._device_path(name), default={}) or {}
        return (rec.get("voip_token") or "").strip() or None
    except Exception:
        # Fallback: best-effort plaintext read if the server module isn't importable here.
        try:
            home = Path(os.environ.get("ANIMA_HOME", Path.home() / ".anima"))
            rec = json.loads((home / f"{name}.device.json").read_text())
            return (rec.get("voip_token") or "").strip() or None
        except Exception:
            return None


def ring(name: str = "Vera",
         device_token: Optional[str] = None,
         handle: str = "Vera",
         call_uuid: Optional[str] = None,
         alert: str = "Vera is calling") -> dict[str, Any]:
    """Ring the phone for creature `name`. If `device_token` is None, use the token the
    phone registered via /device. The payload shape matches what VeraCall's
    AppDelegate.pushRegistry(...didReceiveIncomingPush...) expects.

    Payload shape (documented for the iOS side too):
        {
          "aps": {"alert": <str>, "sound": "default"},   # optional, cosmetic
          "handle": <caller label shown on the call screen>,
          "call_uuid": <uuid str, optional — keeps Mac & phone on one id>
        }
    """
    token = device_token or _stored_voip_token(name)
    if not token:
        return {"ok": False, "status": 0, "apns_id": None,
                "reason": f"no VoIP token for {name!r}; register the phone via /device first"}

    payload = {
        "aps": {"alert": alert, "sound": "default"},
        "handle": handle,
        "call_uuid": (call_uuid or str(uuid.uuid4())).upper(),
    }
    return send_voip_push(token, payload)


def _main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="anima.voip_push",
                                 description="Ring the iPhone via an APNs VoIP push.")
    ap.add_argument("--name", default=os.environ.get("ANIMA_NAME", "Vera"),
                    help="creature name whose registered phone token to ring (default Vera)")
    ap.add_argument("--token", default=None,
                    help="explicit hex VoIP token (else read from .anima/<name>.device.json)")
    ap.add_argument("--handle", default="Vera", help="caller label shown on the call screen")
    ap.add_argument("--call-uuid", default=None, help="optional call UUID to agree on")
    ap.add_argument("--alert", default="Vera is calling", help="alert text (cosmetic)")
    ap.add_argument("--ring", action="store_true",
                    help="send the push (without this, just prints what it would do)")
    args = ap.parse_args(argv)

    if not args.ring:
        host = _apns_host()
        tok = args.token or _stored_voip_token(args.name)
        print("voip_push dry run (pass --ring to actually send):", file=sys.stderr)
        print(f"  APNs host : {host}", file=sys.stderr)
        print(f"  bundle    : {os.environ.get('APNS_BUNDLE_ID', '<APNS_BUNDLE_ID unset>')}.voip",
              file=sys.stderr)
        print(f"  token     : {(tok[:12] + '…') if tok else '<none registered>'}", file=sys.stderr)
        return 0

    result = ring(name=args.name, device_token=args.token,
                  handle=args.handle, call_uuid=args.call_uuid, alert=args.alert)
    print(json.dumps(result))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(_main())
