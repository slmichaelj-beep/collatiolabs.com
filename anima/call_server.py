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

SECURITY (before this carries real audio): /webrtc_offer is currently OPEN for the
local echo test. Phase 2 gates it behind the server's ANIMA_TOKEN and binds it to
the tailnet, exactly like the /loc and /device endpoints — see TODO below.
"""
from __future__ import annotations

import os

from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaRelay

_pcs: set = set()
_relay = MediaRelay()


async def _offer(request: web.Request) -> web.Response:
    # TODO(phase2): require os.environ["ANIMA_TOKEN"] via an Authorization header before
    # accepting an offer, so only your own devices on the tailnet can open a call.
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    pc = RTCPeerConnection()
    _pcs.add(pc)

    @pc.on("connectionstatechange")
    async def _on_state() -> None:
        if pc.connectionState in ("failed", "closed", "disconnected"):
            await pc.close()
            _pcs.discard(pc)

    @pc.on("track")
    def _on_track(track) -> None:
        if track.kind == "audio":
            pc.addTrack(_relay.subscribe(track))     # echo: send their audio right back

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    return web.json_response({"sdp": pc.localDescription.sdp, "type": pc.localDescription.type})


_TEST_PAGE = """<!doctype html><meta charset=utf8><title>Vera call test</title>
<body style="font-family:system-ui;background:#0e0e10;color:#eee;text-align:center;padding:48px">
<h2>Vera &middot; WebRTC echo test</h2>
<button id=b style="font-size:18px;padding:13px 26px;border-radius:22px;border:none;background:#1f4ed8;color:#fff">Connect</button>
<p id=s style="color:#9a9aa2;margin-top:18px"></p>
<script>
b.onclick=async()=>{
  s.textContent='getting mic…';
  const stream=await navigator.mediaDevices.getUserMedia({audio:true});
  const pc=new RTCPeerConnection();
  stream.getTracks().forEach(t=>pc.addTrack(t,stream));
  pc.ontrack=e=>{const a=new Audio();a.srcObject=e.streams[0];a.play();s.textContent='connected — talk, you should hear yourself';};
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
