#!/usr/bin/env python3
"""
certify_web_allowlist — the web-fetch GATES: OFF by default, EMPTY allow-list, SSRF/non-allowlisted
refusal — every refusal short-circuiting BEFORE any network fetch. NO real request is ever made.

The Settings 'Read allow-listed sites' control + #allow textarea feed the 'web' cap + allow-list;
POST /web/fetch -> server._web_fetch cap-gates on 'web' then delegates to webget.fetch, which refuses
(host_allowed False) before opening a socket when the host is not allow-listed. Certified through
those SAME functions, entirely OFFLINE — every assertion is a DEFAULT-STATE refusal that returns
before any connect():

  A. DEFAULT — caps.load(name)['web'] is False and ['allowlist'] is [] (nothing reachable).
  B. ENDPOINT OFF — server._web_fetch refuses ('web access is off in settings') while the cap is off.
  C. EMPTY ALLOW-LIST — webget.host_allowed returns False for a public host, loopback (127.0.0.1),
     link-local (169.254.169.254), and private (10.x); webget.fetch returns the refusal WITHOUT a
     socket (offline-safe). A non-allowlisted PUBLIC host is refused the same way.
  D. SCHEME — a non-http(s) scheme (file://) is refused even against a NON-empty allow-list.
  E. ENDPOINT ON + EMPTY — even with the 'web' cap ON, an empty allow-list still refuses at the
     webget gate (a domain must be added before anything is reachable).

Hermetic + OFFLINE: every store via _temp_store; ANIMA_INTAKE_OFFLINE=1; the cert NEVER calls
webget.fetch with a matching allow-list entry, so no outbound connection is ever attempted. The real
.anima is fingerprinted before/after and asserted byte-identical. Exit 0 == CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

# Belt-and-suspenders offline (this cert never makes a real request; it only exercises refusals).
os.environ.setdefault("ANIMA_INTAKE_OFFLINE", "1")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store
_footprint = _g0pe._footprint


def main() -> int:
    from anima import caps, server, webget
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("WEB ALLOW-LIST — web OFF by default; allow-list EMPTY; SSRF + non-allowlisted refused "
          "BEFORE any fetch (OFFLINE, no real request)")
    print("=" * 80)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    # A tripwire opener: if ANY code path tried to open a real socket through webget, this records it.
    # webget.fetch builds its opener via urllib.request.build_opener(...).open — we wrap build_opener
    # so a fetch that DID NOT short-circuit would be caught. Every assertion below must keep this empty.
    import urllib.request as _ureq
    opened = []
    _orig_build_opener = _ureq.build_opener

    def _spy_build_opener(*a, **k):
        op = _orig_build_opener(*a, **k)
        _orig_open = op.open

        def _open(*oa, **ok):
            opened.append(oa[0] if oa else None)
            raise AssertionError("network fetch attempted — a gate failed to short-circuit")
        op.open = _open
        return op
    _ureq.build_opener = _spy_build_opener
    try:
        with _temp_store():
            N = "WebAllowlistCert"
            server._ensure(N, 64)

            # ---- A. DEFAULT ------------------------------------------------------------------
            c = caps.load(N)
            ck("A1: the 'web' capability is OFF by default", c.get("web") is False)
            ck("A2: the allow-list starts EMPTY (nothing reachable)", c.get("allowlist") == [])

            # ---- B. ENDPOINT OFF -------------------------------------------------------------
            off = json.loads(server._web_fetch(N, {"url": "https://example.com/"}))
            ck("B1: POST /web/fetch refuses while the 'web' cap is off (before any fetch)",
               off.get("ok") is False and "off in settings" in (off.get("error") or ""))

            # ---- C. EMPTY ALLOW-LIST: every host refused, no socket --------------------------
            ck("C1: empty allow-list -> a public host is NOT allowed",
               webget.host_allowed("https://example.com/", []) is False)
            ck("C2: empty allow-list -> a LOOPBACK host (127.0.0.1) is NOT allowed (SSRF refusal)",
               webget.host_allowed("http://127.0.0.1/admin", []) is False)
            ck("C3: empty allow-list -> a LINK-LOCAL host (169.254.169.254) is NOT allowed (SSRF refusal)",
               webget.host_allowed("http://169.254.169.254/latest/meta-data/", []) is False)
            ck("C4: empty allow-list -> a PRIVATE host (10.x) is NOT allowed (SSRF refusal)",
               webget.host_allowed("http://10.0.0.5/", []) is False)
            f_pub = webget.fetch("https://example.com/", [])
            f_loop = webget.fetch("http://127.0.0.1/admin", [])
            ck("C5: webget.fetch refuses a non-allowlisted public host WITHOUT opening a socket",
               f_pub.get("ok") is False and "allow-list" in (f_pub.get("error") or "") and not opened)
            ck("C6: webget.fetch refuses a loopback host WITHOUT opening a socket",
               f_loop.get("ok") is False and "allow-list" in (f_loop.get("error") or "") and not opened)

            # ---- D. SCHEME (refused even with a non-empty allow-list) -------------------------
            ck("D1: a non-http(s) scheme (file://) is refused even against a non-empty allow-list",
               webget.host_allowed("file:///etc/passwd", ["example.com"]) is False)

            # ---- E. ENDPOINT ON + EMPTY ALLOW-LIST still refuses at the webget gate -----------
            caps.save(N, {**c, "web": True})           # turn the cap ON, allow-list still []
            on_empty = json.loads(server._web_fetch(N, {"url": "https://example.com/"}))
            ck("E1: even with 'web' ON, an EMPTY allow-list still refuses at the webget gate "
               "(nothing reachable until a domain is added)",
               on_empty.get("ok") is False and "allow-list" in (on_empty.get("error") or ""))

            ck("Z1: NO real network fetch was ever attempted (every gate short-circuited)", not opened)

            # ---- F. THE UI TOGGLE IS LIVE (go-live) — the user can opt in; the floor above HOLDS ---
            idx = (ROOT / "anima" / "web" / "index.html").read_text(encoding="utf-8")
            web_line = next((ln for ln in idx.splitlines() if 'data-cap="web"' in ln), "")
            ck("F1: the Web toggle is LIVE (data-cap=\"web\" present, NOT disabled, no 'soon' tag on it)",
               bool(web_line) and "disabled" not in web_line and ">soon<" not in web_line
               and "cap soon" not in web_line)
            ck("F2: going live did NOT weaken the floor — A1/A2/B1/E1 above still prove off-by-default, "
               "empty allow-list, and the webget gate refuses until a domain is added",
               c.get("web") is False and c.get("allowlist") == [])
    finally:
        _ureq.build_opener = _orig_build_opener

    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nWEB-ALLOWLIST CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
