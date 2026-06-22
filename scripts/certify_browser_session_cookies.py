#!/usr/bin/env python3
"""certify_browser_session_cookies — browser auth uses pairing cookies, not localStorage secrets.

This cert closes the remaining W04 browser-session contract:
  * a same-origin browser can pair a token into an HttpOnly/SameSite auth cookie;
  * optional one-time pairing codes are consumed on first use and reject replay;
  * the auth cookie is signed, server-registered, expires, rejects tampering, and can be revoked;
  * session inventory, current-session rotation, single-session revoke, and logout-all work;
  * Face-ID/passkey sessions can ride an HttpOnly/SameSite cookie;
  * web shells strip `?k=` and do not persist auth/session secrets in localStorage.
"""
from __future__ import annotations

import sys
import time
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _Headers(dict):
    def get(self, key, default=""):
        return dict.get(self, key, default)


def _req(path="/say", headers=None, command="POST", token="cookie-cert-token"):
    from anima import server
    h = server.Handler.__new__(server.Handler)
    h.token = token
    h.path = path
    h.command = command
    h.headers = _Headers(headers or {})
    return h


def main() -> int:
    from anima import passkey, server

    fails: list[str] = []

    def ck(label: str, cond: bool):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("BROWSER SESSION COOKIES — pairing, HttpOnly/SameSite, no localStorage secrets")
    print("=" * 92)
    t0 = time.perf_counter()
    token = "cookie-cert-token"
    with server._AUTH_SESSIONS_LOCK:
        server._AUTH_SESSIONS.clear()

    # ---- 0. One-time pairing codes -------------------------------------------------
    pair_req = _req(path="/auth/pair", headers={"X-Anima-Pairing-Code": "pair-once"},
                    token=token)
    pair_req.pairing_codes = {"pair-once"}
    ck("P1: a configured one-time pairing code is accepted exactly once",
       pair_req._pairing_authed() is True and "pair-once" not in pair_req.pairing_codes)
    replay_req = _req(path="/auth/pair", headers={"X-Anima-Pairing-Code": "pair-once"},
                      token=token)
    replay_req.pairing_codes = pair_req.pairing_codes
    ck("P2: replaying the same one-time pairing code is rejected",
       replay_req._pairing_authed() is False)
    ck("P3: the existing X-Anima-Key pairing path remains accepted for compatibility",
       _req(path="/auth/pair", headers={"X-Anima-Key": token}, token=token)._pairing_authed() is True)

    # ---- A. Main auth cookie: signed, expiring, HttpOnly/SameSite ------------------
    h = _req(token=token)
    cookie_value = h._issue_auth_cookie()
    ck("A1: auth pairing mints a versioned signed cookie value",
       isinstance(cookie_value, str) and cookie_value.startswith("v1.") and cookie_value.count(".") == 3)
    ck("A2: the freshly minted auth cookie validates", h._valid_auth_cookie(cookie_value) is True)
    ck("A3: _authed accepts the valid auth cookie without exposing ANIMA_TOKEN to JS headers",
       _req(headers={"Cookie": server.AUTH_COOKIE + "=" + cookie_value}, token=token)._authed() is True)
    future = int(time.time()) + server.AUTH_COOKIE_TTL
    unissued = "v1.%d.%s.%s" % (future, "never-issued",
                                h._sign_auth_cookie(future, "never-issued"))
    ck("A4: a correctly signed but never-issued auth cookie is rejected",
       h._valid_auth_cookie(unissued) is False)
    ck("A5: a tampered auth cookie is rejected",
       h._valid_auth_cookie(cookie_value[:-1] + ("0" if cookie_value[-1] != "0" else "1")) is False)
    past = int(time.time()) - 5
    expired = "v1.%d.%s.%s" % (past, "nonce", h._sign_auth_cookie(past, "nonce"))
    ck("A6: an expired but correctly signed auth cookie is rejected",
       h._valid_auth_cookie(expired) is False)
    hdr = h._cookie_header(server.AUTH_COOKIE, cookie_value, server.AUTH_COOKIE_TTL)
    ck("A7: auth cookie header is HttpOnly, SameSite=Strict, path-scoped, and max-age bounded",
       all(part in hdr for part in ("HttpOnly", "SameSite=Strict", "Path=/", "Max-Age=")))
    ck("A8: revoking an issued auth cookie makes it invalid before expiry",
       h._revoke_auth_cookie(cookie_value) is True and h._valid_auth_cookie(cookie_value) is False)

    # ---- A2. Session inventory / rotation / revoke-all -----------------------------
    h1 = _req(headers={"User-Agent": "CookieCert Safari"}, token=token)
    c1 = h1._issue_auth_cookie()
    h2 = _req(headers={"User-Agent": "CookieCert Chrome"}, token=token)
    c2 = h2._issue_auth_cookie()
    inv_req = _req(headers={"Cookie": server.AUTH_COOKIE + "=" + c2}, token=token)
    sessions = inv_req._auth_sessions_public()
    sid2 = next((s["id"] for s in sessions if s.get("current")), "")
    raw_nonce_2 = c2.split(".", 3)[2]
    ck("A9: session inventory lists active sessions and marks the current cookie",
       len(sessions) == 2 and sum(1 for s in sessions if s.get("current")) == 1
       and any("CookieCert Chrome" in s.get("user_agent", "") for s in sessions))
    ck("A10: session inventory exposes hashed ids, not raw cookie nonces",
       sid2 and raw_nonce_2 not in json.dumps(sessions))

    rotate_req = _req(headers={"Cookie": server.AUTH_COOKIE + "=" + c2,
                               "User-Agent": "CookieCert Rotated"}, token=token)
    rotated = rotate_req._rotate_auth_cookie()
    ck("A11: session rotation invalidates the old cookie and issues a valid replacement",
       rotate_req._valid_auth_cookie(c2) is False and rotate_req._valid_auth_cookie(rotated) is True)

    inv_after_rotate = _req(headers={"Cookie": server.AUTH_COOKIE + "=" + rotated}, token=token)
    old_sid = sid2
    rotated_sessions = inv_after_rotate._auth_sessions_public()
    current_sid = next((s["id"] for s in rotated_sessions if s.get("current")), "")
    non_current_sid = next((s["id"] for s in rotated_sessions if not s.get("current")), "")
    ck("A12: single-session revoke by hashed id can revoke a non-current session without killing current",
       inv_after_rotate._revoke_auth_session_id(old_sid) is False
       and inv_after_rotate._revoke_auth_session_id(non_current_sid) is True
       and inv_after_rotate._valid_auth_cookie(c1) is False
       and inv_after_rotate._valid_auth_cookie(rotated) is True)
    ck("A13: single-session revoke can revoke the current session",
       inv_after_rotate._revoke_auth_session_id(current_sid) is True
       and inv_after_rotate._valid_auth_cookie(rotated) is False)

    c3 = h1._issue_auth_cookie()
    c4 = h2._issue_auth_cookie()
    nrev = h1._revoke_all_auth_sessions()
    ck("A14: logout-all revokes every issued auth cookie",
       nrev >= 2 and h1._valid_auth_cookie(c3) is False and h2._valid_auth_cookie(c4) is False)

    # ---- B. Face-ID/passkey cookie path -------------------------------------------
    face_session = passkey.issue_session()
    face_req = _req(headers={"Cookie": server.FACE_COOKIE + "=" + face_session}, token=token)
    saved_required = passkey.required
    try:
        passkey.required = lambda: True
        ck("B1: _passed accepts a valid Face-ID session from the HttpOnly cookie path",
           face_req._passed() is True)
        bad_req = _req(headers={"Cookie": server.FACE_COOKIE + "=" + face_session[:-1] + "x"},
                       token=token)
        ck("B2: _passed rejects a tampered Face-ID cookie session", bad_req._passed() is False)
    finally:
        passkey.required = saved_required
    face_hdr = h._cookie_header(server.FACE_COOKIE, face_session, passkey.SESSION_TTL)
    ck("B3: Face-ID session cookie header is HttpOnly and SameSite=Strict",
       "HttpOnly" in face_hdr and "SameSite=Strict" in face_hdr)

    # ---- C. Static server wiring ---------------------------------------------------
    src = (ROOT / "anima" / "server.py").read_text()
    pair_at = src.find('path == "/auth/pair"')
    auth_routes_at = src.find('path.startswith("/auth/")')
    ck("C1: /auth/pair is wired before generic /auth passkey dispatch",
       pair_at != -1 and auth_routes_at != -1 and pair_at < auth_routes_at)
    ck("C2: /auth/pair sets the signed auth cookie with Set-Cookie",
       "Set-Cookie" in src and "AUTH_COOKIE" in src and "_issue_auth_cookie()" in src)
    ck("C3: /auth/logout revokes auth cookie and clears both browser cookies",
       'path == "/auth/logout"' in src and "_revoke_auth_cookie" in src
       and "_clear_cookie_header(AUTH_COOKIE)" in src and "_clear_cookie_header(FACE_COOKIE)" in src)
    ck("C4: /auth/sessions, /auth/rotate, /auth/logout-all, and /auth/logout-session are wired",
       'u.path == "/auth/sessions"' in src and 'path == "/auth/rotate"' in src
       and 'path == "/auth/logout-all"' in src and 'path == "/auth/logout-session"' in src)
    ck("C5: session inventory/management routes honor the Face-ID/passkey layer when required",
       'if u.path == "/auth/sessions":' in src
       and 'path == "/auth/logout-all":\n                if not self._passed()' in src
       and 'path == "/auth/rotate":\n                if not self._passed()' in src
       and 'path == "/auth/logout-session":\n                if not self._passed()' in src)
    ck("C6: /auth/login/finish sets the Face-ID session cookie; /auth/disable clears it",
       "FACE_COOKIE" in src and 'path == "/auth/login/finish"' in src
       and 'path == "/auth/disable"' in src and "_clear_cookie_header(FACE_COOKIE)" in src)
    ck("C7: _send supports response headers so cookies are emitted through the normal path",
       "def _send(self, code, ctype, body, headers=None)" in src)
    ck("C8: ANIMA_PAIRING_CODE initializes one-time pairing codes at startup",
       "ANIMA_PAIRING_CODE" in src and "pairing_codes" in src)
    ck("C9: authenticated startup auto-generates a transient one-time pairing code when none is supplied",
       "def _new_pairing_code()" in src
       and "generated_pairing_code = _new_pairing_code()" in src
       and "expires after first use or restart" in src
       and "if Handler.token and not pairing_codes" in src)

    # ---- D. Browser shells do not persist auth/session secrets ----------------------
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
        "keep ?k= IN",
    ]
    ck("D1: no web shell reads or stores anima_token/anima_sess in localStorage",
       all(s not in combined for s in forbidden))
    token_pages = [p for p in html_files if "searchParams.get('k')" in p.read_text(encoding="utf-8")]
    ck("D2: every ?k-aware shell strips k from the URL and calls /auth/pair",
       token_pages and all(("history.replaceState" in p.read_text(encoding="utf-8")
                            and "/auth/pair" in p.read_text(encoding="utf-8"))
                           for p in token_pages))
    idx = (ROOT / "anima" / "web" / "index.html").read_text(encoding="utf-8")
    ck("D3: main chat no longer sends Face-ID sessions through X-Anima-Sess from localStorage",
       "X-Anima-Sess" not in idx and "localStorage.removeItem('anima_sess')" in idx)
    ck("D4: main chat offers a first-launch pairing-code gate instead of a ?k= recovery message",
       all(s in idx for s in ("id=\"pairGate\"", "id=\"pairCode\"", "id=\"pairSubmit\"",
                              "X-Anima-Pairing-Code", "showPairGate()", "submitPairCode()"))
       and "vera2026" not in idx and "Open your link with ?k=" not in idx)
    ck("D5: pairing-code UX posts only to /auth/pair and never writes the code to localStorage",
       "fetch('/auth/pair',{method:'POST',headers:{'X-Anima-Pairing-Code':code}})" in idx
       and "localStorage.setItem('pair" not in idx
       and "localStorage.setItem(\"pair" not in idx)

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_browser_session_cookies", "green" if green else "red",
                files_observed=["anima/server.py", "anima/web/index.html", "anima/web/*.html"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)

    print("\nBROWSER-SESSION-COOKIES CERT: " + ("CERTIFIED" if green else f"FAIL ({len(fails)})"))
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
