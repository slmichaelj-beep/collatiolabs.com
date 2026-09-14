#!/usr/bin/env python3
"""certify_browser_origin_csrf — browser POSTs cannot cross Vera's local trust boundary.

This cert captures the W04 hardening contract:
  * token headers and Bearer auth still work for browser/API clients;
  * legacy `?k=` auth remains GET-only and cannot authorize POST;
  * hostile Origin/Referer/Fetch-Metadata values fail before auth or body parsing;
  * same-host browser POSTs and native clients that omit browser headers still work.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class _Headers(dict):
    def get(self, key, default=""):
        return dict.get(self, key, default)


def _req(path: str, headers: dict | None = None, command: str = "POST", token: str = "cert-token"):
    from anima import server
    h = server.Handler.__new__(server.Handler)
    h.token = token
    h.path = path
    h.command = command
    h.headers = _Headers(headers or {})
    return h


def main() -> int:
    from anima import server

    fails: list[str] = []

    def ck(label: str, cond: bool):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("BROWSER ORIGIN / CSRF — same-host POST boundary")
    print("=" * 76)
    t0 = time.perf_counter()
    token = "csrf-cert-token-not-real"

    # A. Auth contract: headers/Bearer authorize POST; query tokens do not.
    ck("A1: legacy ?k= still works for GET/data routes",
       _req("/version?k=" + token, command="GET", token=token)._authed() is True)
    ck("A2: a correct ?k= alone does NOT authorize POST",
       _req("/say?k=" + token, command="POST", token=token)._authed() is False)
    ck("A3: POST accepts X-Anima-Key header",
       _req("/say", {"X-Anima-Key": token}, token=token)._authed() is True)
    ck("A4: POST accepts Authorization: Bearer header",
       _req("/say", {"Authorization": "Bearer " + token}, token=token)._authed() is True)
    ck("A5: a correct header wins even if a stale query token is present",
       _req("/say?k=stale", {"X-Anima-Key": token}, token=token)._authed() is True)

    # B. Origin/Referer/Fetch-Metadata wall.
    same = {
        "Host": "127.0.0.1:8765",
        "Origin": "http://127.0.0.1:8765",
        "X-Anima-Key": token,
    }
    https_same = {
        "Host": "vera.example.test",
        "Origin": "https://vera.example.test",
        "X-Anima-Key": token,
    }
    ck("B1: same-host browser POST is allowed",
       _req("/say", same, token=token)._post_origin_ok() is True)
    ck("B2: same host behind HTTPS/tunnel is allowed",
       _req("/say", https_same, token=token)._post_origin_ok() is True)
    ck("B3: native/curl-style POST with no browser origin headers is allowed",
       _req("/say", {"X-Anima-Key": token}, token=token)._post_origin_ok() is True)
    ck("B4: hostile Origin is refused",
       _req("/say", {"Host": "127.0.0.1:8765", "Origin": "https://evil.example"},
            token=token)._post_origin_ok() is False)
    ck("B5: opaque/null Origin is refused",
       _req("/say", {"Host": "127.0.0.1:8765", "Origin": "null"},
            token=token)._post_origin_ok() is False)
    ck("B6: hostile Referer is refused when Origin is absent",
       _req("/say", {"Host": "127.0.0.1:8765", "Referer": "https://evil.example/p"},
            token=token)._post_origin_ok() is False)
    ck("B7: Sec-Fetch-Site cross-site is refused even without Origin",
       _req("/say", {"Host": "127.0.0.1:8765", "Sec-Fetch-Site": "cross-site"},
            token=token)._post_origin_ok() is False)

    # C. Static wiring: the guard must be before auth and before any body read.
    src = (ROOT / "anima" / "server.py").read_text()
    post = src.index("def do_POST")
    path_at = src.index("path = urlparse(self.path).path", post)
    origin_at = src.index("if not self._post_origin_ok():", post)
    auth_at = src.index("if not self._authed():", post)
    read_at = src.index("self._read_body()", post)
    ck("C1: do_POST computes path, then rejects unsafe Origin before token auth",
       path_at < origin_at < auth_at)
    ck("C2: unsafe Origin is rejected before any request body is read",
       origin_at < read_at)
    ck("C3: responses carry no-referrer and nosniff security headers",
       'self.send_header("Referrer-Policy", "no-referrer")' in src
       and 'self.send_header("X-Content-Type-Options", "nosniff")' in src)
    ck("C4: POST refusal uses a hard 403 JSON error",
       'b\'{"ok":false,"error":"cross_origin_post_refused"}\'' in src)

    green = not fails
    try:
        from anima.verification import cert_result as cr
        cr.emit("certify_browser_origin_csrf", "green" if green else "red",
                files_observed=["anima/server.py"],
                duration_sec=time.perf_counter() - t0, failures=fails)
    except Exception as e:
        print("  (emit failed: %r)" % e)

    print("\nBROWSER-ORIGIN-CSRF CERT: " + ("CERTIFIED" if green else f"FAIL ({len(fails)})"))
    return 0 if green else 1


if __name__ == "__main__":
    raise SystemExit(main())
