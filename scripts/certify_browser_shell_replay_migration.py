#!/usr/bin/env python3
"""certify_browser_shell_replay_migration — W04 multi-shell pairing/replay coverage.

Proves the supported browser-shell migration contract:
  * an already-authenticated browser can mint one more transient one-time pairing code;
  * minting is behind auth and the optional Face-ID/passkey layer;
  * the minted code pairs exactly one additional browser and rejects replay;
  * same-host POSTs work for desktop localhost, LAN browser, HTTPS tunnel, and same-origin
    installed/webview shells;
  * cross-host/cross-site replay is still refused before auth/body parsing;
  * all web shells continue to strip legacy ?k= and avoid localStorage auth secrets.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _Headers(dict):
    def get(self, key, default=""):
        return dict.get(self, key, default)


def _req(path="/say", headers=None, command="POST", token="shell-cert-token"):
    from anima import server
    h = server.Handler.__new__(server.Handler)
    h.token = token
    h.path = path
    h.command = command
    h.headers = _Headers(headers or {})
    h.pairing_codes = set()
    h.client_address = ("127.0.0.1", 43110)
    return h


def _capture_send(h):
    def send(code, ctype, body, headers=None):
        h.sent = {
            "code": code,
            "ctype": ctype,
            "body": body,
            "headers": headers or [],
        }
        return h.sent
    h._send = send
    return h


def main() -> int:
    from anima import passkey, server

    fails: list[str] = []

    def ck(label: str, cond: bool):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("BROWSER SHELL REPLAY / MIGRATION — W04 multi-shell cert")
    print("=" * 86)
    t0 = time.perf_counter()
    token = "shell-cert-token"

    # A. Authenticated mint route: one more one-time code for another shell/device.
    mint = _capture_send(_req(
        "/auth/pairing-code",
        {
            "Host": "127.0.0.1:8765",
            "Origin": "http://127.0.0.1:8765",
            "X-Anima-Key": token,
        },
        token=token,
    ))
    server.Handler.do_POST(mint)
    body = json.loads(mint.sent["body"].decode())
    code = body.get("pairing_code", "")
    ck("A1: authenticated /auth/pairing-code mints a transient code",
       mint.sent["code"] == 200 and body.get("ok") is True and code in mint.pairing_codes
       and isinstance(code, str) and len(code) >= 10)

    pair = _req("/auth/pair", {"X-Anima-Pairing-Code": code}, token=token)
    pair.pairing_codes = mint.pairing_codes
    ck("A2: minted code pairs exactly one additional browser",
       pair._pairing_authed() is True and code not in pair.pairing_codes)
    replay = _req("/auth/pair", {"X-Anima-Pairing-Code": code}, token=token)
    replay.pairing_codes = pair.pairing_codes
    ck("A3: replaying that minted code is rejected", replay._pairing_authed() is False)

    no_auth = _capture_send(_req(
        "/auth/pairing-code",
        {"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"},
        token=token,
    ))
    server.Handler.do_POST(no_auth)
    ck("A4: pairing-code minting is unavailable without auth", no_auth.sent["code"] == 401)

    saved_required = passkey.required
    saved_valid = passkey.valid_session
    try:
        passkey.required = lambda: True
        passkey.valid_session = lambda _s: False
        face_locked = _capture_send(_req(
            "/auth/pairing-code",
            {
                "Host": "127.0.0.1:8765",
                "Origin": "http://127.0.0.1:8765",
                "X-Anima-Key": token,
            },
            token=token,
        ))
        server.Handler.do_POST(face_locked)
        ck("A5: pairing-code minting honors the Face-ID/passkey layer when required",
           face_locked.sent["code"] == 401 and b"need_face_id" in face_locked.sent["body"])
    finally:
        passkey.required = saved_required
        passkey.valid_session = saved_valid

    # B. Same-host shells and hostile replay/cross-site cases.
    allowed = [
        ("desktop-localhost", {"Host": "localhost:8765", "Origin": "http://localhost:8765"}),
        ("desktop-loopback", {"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"}),
        ("lan-browser", {"Host": "192.168.1.24:8765", "Origin": "http://192.168.1.24:8765"}),
        ("https-tunnel", {"Host": "vera.example.test", "Origin": "https://vera.example.test"}),
        ("https-tunnel-default-port", {"Host": "vera.example.test:443",
                                       "Origin": "https://vera.example.test"}),
        ("installed-same-origin-webview", {"Host": "localhost:8765",
                                           "Origin": "http://localhost:8765",
                                           "Sec-Fetch-Site": "same-origin"}),
    ]
    for label, headers in allowed:
        ck("B allow: %s same-host POST accepted" % label,
           _req("/say", headers, token=token)._post_origin_ok() is True)

    denied = [
        ("lan-cookie-replay-from-loopback-origin",
         {"Host": "192.168.1.24:8765", "Origin": "http://127.0.0.1:8765"}),
        ("tunnel-cookie-replay-from-lan-origin",
         {"Host": "vera.example.test", "Origin": "http://192.168.1.24:8765"}),
        ("cross-site-fetch-metadata",
         {"Host": "localhost:8765", "Origin": "http://localhost:8765",
          "Sec-Fetch-Site": "cross-site"}),
        ("opaque-installed-origin",
         {"Host": "localhost:8765", "Origin": "null"}),
        ("custom-scheme-installed-origin",
         {"Host": "localhost:8765", "Origin": "tauri://localhost"}),
    ]
    for label, headers in denied:
        ck("B deny: %s refused" % label,
           _req("/say", headers, token=token)._post_origin_ok() is False)

    ck("B note: custom-scheme installed shells must proxy through a same-origin localhost webview",
       _req("/say", {"Host": "localhost:8765", "Origin": "tauri://localhost"},
            token=token)._post_origin_ok() is False)

    # C. Static web-shell migration contract.
    html_files = sorted((ROOT / "anima" / "web").glob("*.html"))
    combined = "\n".join(p.read_text(encoding="utf-8") for p in html_files)
    forbidden = [
        "localStorage.getItem('anima_token')",
        'localStorage.getItem("anima_token")',
        "localStorage.setItem('anima_token'",
        'localStorage.setItem("anima_token"',
        "localStorage.getItem('anima_sess')",
        'localStorage.getItem("anima_sess")',
        "localStorage.setItem('anima_sess'",
        'localStorage.setItem("anima_sess"',
    ]
    token_pages = [p for p in html_files if "searchParams.get('k')" in p.read_text(encoding="utf-8")]
    ck("C1: all ?k-aware shells strip k and pair into cookies",
       token_pages and all(("history.replaceState" in p.read_text(encoding="utf-8")
                            and "/auth/pair" in p.read_text(encoding="utf-8"))
                           for p in token_pages))
    ck("C2: no shell reads or stores auth/session secrets in localStorage",
       all(s not in combined for s in forbidden))
    idx = (ROOT / "anima" / "web" / "index.html").read_text(encoding="utf-8")
    ck("C3: main shell includes the pairing-code UX for first or migrated browsers",
       all(s in idx for s in ("pairGate", "pairCode", "X-Anima-Pairing-Code", "submitPairCode")))

    # D. Static route wiring.
    src = (ROOT / "anima" / "server.py").read_text()
    pair_route = src.find('path == "/auth/pairing-code"')
    logout_route = src.find('path == "/auth/logout"')
    ck("D1: /auth/pairing-code is wired after auth and before generic logout/session routes",
       pair_route != -1 and logout_route != -1 and pair_route < logout_route)
    ck("D2: /auth/pairing-code stores only transient in-memory codes",
       "_new_pairing_code()" in src and "self.pairing_codes.add(code)" in src
       and "pairing_code" in src and "save_json" not in src[pair_route:pair_route + 600])

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_browser_shell_replay_migration", "green" if green else "red",
                files_observed=[
                    "anima/server.py",
                    "anima/web/index.html",
                    "anima/web/*.html",
                ],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)

    print("\nBROWSER-SHELL-REPLAY-MIGRATION CERT: "
          + ("CERTIFIED" if green else f"FAIL ({len(fails)})"))
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
