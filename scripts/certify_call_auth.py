#!/usr/bin/env python3
"""certify_call_auth — the WebRTC call server's ANIMA_TOKEN wall (anima/call_server.py).

A loop-mode /webrtc_offer opens a LIVE voice channel to Vera's brain, so it must be gated exactly
like the main server's /loc and /device endpoints (anima/server.py::_authed). This cert proves the
wall three ways, mirroring scripts/certify_proactive_location.py's auth-gate assertions:

  A. THE LOGIC — call_server._authed() is open ONLY when no ANIMA_TOKEN is configured (dev); with a
     token set it REFUSES an offer that presents no / wrong credentials, and ACCEPTS the correct
     token via ?k=, X-Anima-Key, or Authorization: Bearer (constant-time compare).
  B. THE WALL IS LIVE — calling the real _offer handler with a token configured + no credentials
     returns HTTP 401 BEFORE it reads the SDP body or builds a peer connection (so an unauthenticated
     loop-mode call never reaches CallSession / Vera's brain).
  C. THE WIRING — the _offer source gates on _authed() -> 401 ahead of the CallSession construction,
     the phase-2 TODO is gone, and the docstring SECURITY note reflects the closed gate.

Hermetic: no socket, no real peer connection (the 401 path returns before any aiortc work). Exit 0
== CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

TOKEN = "cert-secret-7f3a9c"


class _Req:
    """A minimal stand-in for aiohttp's web.Request: just the surface _offer touches on the 401
    path — .query, .headers, and an async .json()."""
    def __init__(self, query=None, headers=None):
        self.query = query or {}
        self.headers = headers or {}

    async def json(self):
        return {"sdp": "v=0\r\n", "type": "offer"}


def main() -> int:
    from anima import call_server as cs
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("CALL-SERVER AUTH — ANIMA_TOKEN wall on /webrtc_offer")
    print("=" * 84)

    saved = os.environ.get("ANIMA_TOKEN")
    try:
        # ---- A. the _authed() logic ----------------------------------------------------------
        os.environ.pop("ANIMA_TOKEN", None)
        ck("A1: no ANIMA_TOKEN -> open (dev posture, matches main server auth-off)",
           cs._authed(_Req()) is True)

        os.environ["ANIMA_TOKEN"] = TOKEN
        ck("A2: token set + NO credentials -> refused", cs._authed(_Req()) is False)
        ck("A3: token set + wrong ?k= -> refused", cs._authed(_Req(query={"k": "nope"})) is False)
        ck("A4: token set + correct ?k= -> allowed", cs._authed(_Req(query={"k": TOKEN})) is True)
        ck("A5: token set + correct X-Anima-Key -> allowed",
           cs._authed(_Req(headers={"X-Anima-Key": TOKEN})) is True)
        ck("A6: token set + correct Authorization: Bearer -> allowed",
           cs._authed(_Req(headers={"Authorization": "Bearer " + TOKEN})) is True)
        ck("A7: token set + wrong Bearer -> refused",
           cs._authed(_Req(headers={"Authorization": "Bearer wrong"})) is False)

        # ---- B. the wall is live on the real handler -----------------------------------------
        # token configured, unauthenticated loop-mode offer -> 401, and it returns BEFORE reading
        # the body or constructing a peer connection (so it never reaches Vera's brain).
        os.environ["ANIMA_TOKEN"] = TOKEN
        resp = asyncio.run(cs._offer(_Req(query={"mode": "loop"})))
        ck("B1: unauthenticated loop-mode offer -> HTTP 401 (the wall, not a soft pass)",
           getattr(resp, "status", None) == 401)
        ck("B2: nothing leaked past the wall — no peer connection was created",
           len(cs._pcs) == 0)
        # an echo offer is likewise refused while a token is configured (open only in dev)
        resp_echo = asyncio.run(cs._offer(_Req(query={"mode": "echo"})))
        ck("B3: unauthenticated echo offer -> 401 too while a token is set (open only in dev)",
           getattr(resp_echo, "status", None) == 401 and len(cs._pcs) == 0)
    finally:
        if saved is None:
            os.environ.pop("ANIMA_TOKEN", None)
        else:
            os.environ["ANIMA_TOKEN"] = saved

    # ---- C. the wiring (static, mirrors certify_proactive_location's source assertions) -------
    src = (ROOT / "anima" / "call_server.py").read_text(encoding="utf-8")
    off = src.find("async def _offer")
    gate = src.find("if not _authed(request):", off)
    four01 = src.find("status=401", gate) if gate != -1 else -1
    sess = src.find("CallSession", off)
    ck("C1: _offer gates on _authed() and returns 401 on failure",
       gate != -1 and four01 != -1 and (four01 - gate) < 160)
    ck("C2: the 401 gate PRECEDES the CallSession (loop-brain) construction",
       gate != -1 and (sess == -1 or gate < sess))
    ck("C3: the phase-2 TODO is removed", "TODO(phase2)" not in src and "TODO(phase" not in src)
    ck("C4: the docstring SECURITY note reflects the CLOSED gate (no 'currently OPEN')",
       "currently OPEN" not in src and "gated behind the server's ANIMA_TOKEN" in src)

    print("\nCALL-AUTH CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
