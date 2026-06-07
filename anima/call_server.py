"""
call_server — the Mac side of Vera's voice call.

MILESTONE 1 (this file): a WebRTC audio ECHO server. The phone (or a browser, for
testing) POSTs an SDP offer to /webrtc_offer; we open a DIRECT peer connection (no
STUN/TURN — the phone reaches the Mac over the private Tailscale/WireGuard tunnel)
and bounce the incoming mic audio straight back. That proves two-way audio works
end-to-end before any iPhone or Apple account exists.

MILESTONE 2 (next): replace the echo with the real conversation loop — VAD on the
incoming track -> whisper-cli/WhisperEars transcription -> her real brain (mouth)
-> Kokoro TTS back out -> the I'm-awake / snooze / silence state machine.

Run:   python3 -m anima.call_server
Test:  open http://localhost:8766/calltest in a browser, allow the mic, hit
       Connect — you should hear your own voice echoed back within a second.

SECURITY: /webrtc_offer is gated behind the server's ANIMA_TOKEN, exactly like the
main server's /loc and /device endpoints (anima/server.py::_authed). A loop-mode
offer opens a live voice channel to Vera's brain, so EVERY offer must present the
token — via an Authorization: Bearer header, an X-Anima-Key header, or a ?k= query
param (constant-time compare). With ANIMA_TOKEN UNSET the server is open for the
local echo / dev test, matching the main server's auth-off dev posture.
"""
from __future__ import annotations

import hmac
import os

from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRelay

_pcs: set = set()
_relay = MediaRelay()


def _authed(request: web.Request) -> bool:
    """Mirror anima/server.py::_authed — open when no ANIMA_TOKEN is configured (dev), else require
    the token, supplied via a ?k= query param, an X-Anima-Key header, or an Authorization: Bearer
    header, compared in constant time. This is the wall that keeps a loop-mode call (a live channel
    to Vera's brain) from being opened by any peer that can merely reach the port."""
    token = os.environ.get("ANIMA_TOKEN", "")
    if not token:
        return True
    given = request.query.get("k", "") or request.headers.get("X-Anima-Key", "")
    if not given:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            given = auth[7:]
    return hmac.compare_digest(given, token)


async def _offer(request: web.Request) -> web.Response:
    # SECURITY (phase 2, done): every offer must clear the ANIMA_TOKEN wall BEFORE we read the body
    # or build a peer connection. A loop-mode offer opens a live voice channel to Vera's brain; echo
    # mode is likewise gated whenever a token is configured — both are open ONLY in dev (no token).
    if not _authed(request):
        return web.json_response({"error": "unauthorized"}, status=401)
    params = await request.json()
    mode = request.query.get("mode", "loop")          # "loop" = talk to Vera; "echo" = audio test
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    pc = RTCPeerConnection()
    _pcs.add(pc)

    session = None
    if mode != "echo":
        from .call_loop import CallSession
        session = CallSession(pc, name=os.environ.get("ANIMA_NAME", "Vera"))

    @pc.on("connectionstatechange")
    async def _on_state() -> None:
        print("[call] connection: " + pc.connectionState, file=__import__("sys").stderr, flush=True)
        if pc.connectionState in ("failed", "closed", "disconnected"):
            await pc.close()
            _pcs.discard(pc)

    @pc.on("track")
    def _on_track(track) -> None:
        if track.kind != "audio":
            return
        if session is not None:
            session.attach(track)                     # the live conversation loop (M2)
        else:
            pc.addTrack(_relay.subscribe(track))      # echo (audio test, ?mode=echo)

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    return web.json_response({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})


_TEST_PAGE = """<!doctype html><meta charset=utf8><title>Vera call test</title>
<body style="font-family:system-ui;background:#0e0e10;color:#eee;text-align:center;padding:48px">
<h2>Talk to Vera</h2>
<button id=b style="font-size:18px;padding:13px 26px;border-radius:22px;border:none;background:#1f4ed8;color:#fff">Connect &amp; talk</button>
<p id=s style="color:#9a9aa2;margin-top:18px"></p>
<script>
b.onclick=async()=>{
  s.textContent='getting mic…';
  const stream=await navigator.mediaDevices.getUserMedia({audio:true});
  const pc=new RTCPeerConnection();
  stream.getTracks().forEach(t=>pc.addTrack(t,stream));
  pc.ontrack=e=>{const a=new Audio();a.srcObject=e.streams[0];a.play();s.textContent='connected — say hi, give her a second to answer';};
  const offer=await pc.createOffer();await pc.setLocalDescription(offer);
  const r=await fetch('/webrtc_offer',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({sdp:pc.localDescription.sdp,type:pc.localDescription.type})});
  await pc.setRemoteDescription(await r.json());
};
</script>"""


async def _calltest(request: web.Request) -> web.Response:
    return web.Response(text=_TEST_PAGE, content_type="text/html")


async def _index(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "vera call_server", "milestone": 1, "test": "/calltest"})


def make_app() -> web.Application:
    app = web.Application()
    app.router.add_post("/webrtc_offer", _offer)
    app.router.add_get("/calltest", _calltest)
    app.router.add_get("/", _index)
    app.on_shutdown.append(_shutdown)
    return app


async def _shutdown(app: web.Application) -> None:
    for pc in list(_pcs):
        await pc.close()
    _pcs.clear()


if __name__ == "__main__":
    port = int(os.environ.get("ANIMA_CALL_PORT", "8766"))
    web.run_app(make_app(), host="0.0.0.0", port=port)
