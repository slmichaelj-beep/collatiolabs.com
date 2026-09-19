# Vera — Voice Architecture (Recording → Speaking)

> Generated reference, 2026-06-06. Part 1 is the architecture map; Part 2 is the
> verbatim source of the whole voice path (iOS client + Anima Python backend).
> This is documentation only — no source files were modified to produce it.

Vera's voice is a **real-time WebRTC phone call** between the iPhone app
(`ios/VeraCall`, Swift) and the Mac (`anima/`, Python), tunneled over Tailscale so
audio never leaves the tailnet. Speech-to-text, the LLM, and text-to-speech all run
**locally on the Mac**.

```
 iPhone (VeraCall)                  Tailscale tunnel              Mac (anima/)
 ─────────────────                  ────────────────              ────────────
 Mic ─ RTCAudioTrack ─┐                                   ┌─ aiortc track.recv()
 (Opus, AEC/NS/AGC)   │   Opus / DTLS-SRTP over WebRTC    │   └ av resample → 16kHz PCM
                      ├──────────────  POST /webrtc_offer ─┤   VAD (RMS>600, 700ms gap)
                      │   (SDP offer→answer, one-shot)     │   faster-whisper small.en → text
 Speaker ◀ RTCAudioTrack ◀                                 │   server._turn()  → reply text
 (.speaker default)   └──────────────  Opus frames ───────┤   Kokoro TTS (af_heart, 24kHz)
                                                          └─ resample 48kHz → SpeakerTrack
 Ringing: APNs VoIP push ◀──────────────────────────────── voip_push.py (JWT/HTTP-2)
          PushKit → CallKit native call screen
```

## 1. Recording path (your voice → text)

- **Capture (iPhone).** `WebRTCClient.addMicTrack()` builds an `RTCAudioTrack`
  (`"vera-mic0"`). Audio session is `.playAndRecord` / `.voiceChat` with Bluetooth
  allowed (`CallController.swift:205`). AEC / noise-suppression / AGC are WebRTC
  framework defaults — not configured in-app (`WebRTCClient.swift:199`). Mute =
  `localAudioTrack.isEnabled = false`.
- **Transport.** Opus over DTLS-SRTP. Signaling is a **single HTTP POST** of the SDP
  offer to `…:8766/webrtc_offer?mode=loop`; the answer comes back in the response
  (`WebRTCClient.swift:139`). `iceServers = []`, `gatherOnce` — no STUN/TURN, no
  trickle ICE; relies entirely on the tailnet (`WebRTCClient.swift:73`).
- **Ingest (Mac).** `call_loop.py` pulls frames via `track.recv()` and resamples
  Opus → **16 kHz mono PCM** with PyAV (`call_loop.py:206`).
- **Endpointing.** Pure **RMS-energy VAD** (no ML): speaking when
  `RMS > ANIMA_VAD_RMS` (default 600); utterance ends after ~700 ms silence; 25 s
  total silence → nudge once, then hang up (`call_loop.py:221`).
- **STT.** `faster-whisper` `small.en`, int8, **chunked** (full utterance → temp WAV
  → `transcribe(vad_filter=True)`), class `WhisperEars` (`mouth.py:600`). Overridable
  via `ANIMA_WHISPER`.

## 2. Speaking path (text → her voice)

- **Brain hook.** Transcript → `server._turn(name, text, voice=False)`
  (`call_loop.py:120`). Inside `_turn`: perception → heart-state → router, with a
  local fast-path (LERF/LIRF) that can answer without the LLM; otherwise it calls
  **`L3-8B-Stheno-v3.2-GGUF` via Ollama** at `localhost:11434` (`mouth.py:470`).
- **TTS.** **Kokoro**, voice **`af_heart`**, synthesized at **24 kHz** as a *full
  utterance* (`mouth.py:563`), resampled to **48 kHz**, pushed into a custom
  `SpeakerTrack` that paces frames back over WebRTC (`call_loop.py:69`, `:127`).
- **Half-duplex gate.** While she speaks, the loop sets `speaker.speaking()` and
  **skips transcription** so she doesn't hear herself (`call_loop.py:218`). That is
  the entire echo strategy on the server side.

## 3. Call setup / ringing

- **Ring.** `voip_push.py` sends an APNs **VoIP push** over HTTP/2, JWT-signed
  (ES256, `.p8` key), topic `<bundle>.voip`, payload `{aps, handle:"Vera", call_uuid}`
  (`voip_push.py:178`).
- **Answer.** PushKit wakes the app → `CallController.reportIncomingCall()` shows the
  native CallKit screen → on answer, CallKit's `didActivate` fires `startWebRTC()` and
  audio begins (`CallController.swift:228`, `:263`). Defaults to loudspeaker.
- **Device registration.** On launch the app registers its VoIP token to the **main
  server** at `…:8765/device` (`DeviceRegistration.swift`), persisted to
  `.anima/<name>.device.json` for `voip_push.py`.

## Component / tech reference

| Stage | Tech | Where |
|---|---|---|
| iOS WebRTC | `stasel/WebRTC` 137.0.0 | `Package.resolved` |
| Mac WebRTC | `aiortc` + PyAV | `call_server.py:27`, `call_loop.py:206` |
| Signaling | one-shot `POST /webrtc_offer` (port 8766) | `call_server.py:34` |
| VAD | RMS energy, env-tunable | `call_loop.py:221` |
| STT | faster-whisper `small.en` int8 | `mouth.py:600` |
| LLM | L3-8B-Stheno-v3.2 GGUF via Ollama | `mouth.py:470` |
| TTS | Kokoro, `af_heart`, 24→48 kHz | `mouth.py:563`, `call_loop.py:69` |
| Ring | APNs VoIP push, CallKit/PushKit | `voip_push.py`, `CallController.swift` |
| Transport security | DTLS-SRTP inside Tailscale (HTTP, not HTTPS) | `Settings.swift:59` |

## Known gaps (issue → meaning → action)

- **No barge-in.** Transcription is muted while she talks, so you can't interrupt —
  she finishes the full reply before listening resumes. *Action:* run VAD during
  playback and flush the `SpeakerTrack` queue on sustained user energy.
- **Serial + chunked latency.** Nothing starts until 700 ms of silence, then
  Whisper → LLM → *whole-reply* Kokoro run before any audio plays. The chat path
  already streams TTS per sentence (`server.py:/tts`); the call path doesn't.
  *Action:* stream TTS sentence-by-sentence into the call loop; consider `base.en`.
- **`/webrtc_offer` doesn't enforce auth.** The app sends `Authorization: Bearer`,
  but `call_server.py` ignores it (Phase-2 TODO). Anyone on the tailnet reaching
  port 8766 can open a call. *Action:* gate `_offer()` on `ANIMA_TOKEN`.
- **Tailscale-only by design.** No STUN/TURN means no connectivity off the tailnet —
  intentional (private-by-default), just a hard dependency.

---

# Part 2 — Source code (verbatim)

Server files are full; `mouth.py` is excerpted to the two voice-I/O classes
(`KokoroVoice` TTS + `WhisperEars` STT) — its imports live at the top of the file.
Client files are full.


---

# SERVER — anima/ (Python)


## anima/call_server.py

```python
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

```


## anima/call_loop.py

```python
"""
call_loop — milestone 2: the live voice conversation loop for Vera's call.

Replaces call_server's echo. Over one WebRTC connection she:
  1. greets you (Kokoro TTS streamed out),
  2. listens to your mic (incoming track -> 16 kHz -> energy VAD -> end-of-utterance),
  3. transcribes it (WhisperEars),
  4. replies in her REAL voice (active brain + mouth.system_prompt -> Kokoro TTS out),
  5. handles "goodbye" (hang up) and a silence timeout (one nudge, then hang up).

Everything is local — Ollama/cloud brain, Whisper STT, Kokoro TTS; nothing leaves the
Mac. The audio is genuinely real-time, so the VAD threshold / end-of-utterance gap /
echo-suppression are env-tunable and will want tuning BY EAR:
    ANIMA_VAD_RMS (default 600)   ANIMA_UTT_GAP_MS (default 700)
"""
from __future__ import annotations

import asyncio
import fractions
import os
import sys
import tempfile
import time
import wave

import av
import numpy as np
from aiortc import MediaStreamTrack

OUT_SR = 48000
FRAME_MS = 20
OUT_SAMPLES = OUT_SR * FRAME_MS // 1000          # 960 samples / 20 ms @ 48 kHz
_VAD_RMS = float(os.environ.get("ANIMA_VAD_RMS", "600"))
_UTT_GAP_FRAMES = max(3, int(os.environ.get("ANIMA_UTT_GAP_MS", "700")) // FRAME_MS)
_SILENCE_TIMEOUT = float(os.environ.get("ANIMA_CALL_SILENCE", "25"))   # seconds before she gives up

# On a live call a long pause is worse than slightly plainer phrasing, so cap the break-character
# backstop at ONE re-roll here (the sentence-strip still guarantees a clean ship). Set before
# mouth is imported in this process so it picks up the lower default. Text chat keeps its 2.
os.environ.setdefault("ANIMA_BACKSTOP_TRIES", "1")


def _log(msg: str) -> None:
    print("[call] " + str(msg), file=sys.stderr, flush=True)


# --- heavy singletons (loaded once, on first use) ---------------------------
_voice = None
_ears = None


def _kokoro():
    global _voice
    if _voice is None:
        from .mouth import KokoroVoice
        _voice = KokoroVoice()
    return _voice


def _whisper():
    global _ears
    if _ears is None:
        from .mouth import WhisperEars
        _ears = WhisperEars()
    return _ears


# --- TTS: text -> 48 kHz mono int16 (blocking; call in an executor) ----------
def _tts_samples(text: str) -> np.ndarray:
    import soundfile as sf
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        p = f.name
    try:
        _kokoro().speak(text, {}, p)
        data, sr = sf.read(p, dtype="int16")
    finally:
        try:
            os.unlink(p)
        except OSError:
            pass
    if getattr(data, "ndim", 1) > 1:
        data = data[:, 0]
    data = np.asarray(data, dtype=np.int16)
    if sr != OUT_SR and len(data):                     # linear resample to the WebRTC rate
        n = int(len(data) * OUT_SR / sr)
        x = np.linspace(0, len(data), num=n, endpoint=False)
        data = np.interp(x, np.arange(len(data)), data.astype(np.float32)).astype(np.int16)
    return data


# --- STT: 16 kHz mono int16 -> text (blocking; call in an executor) ----------
def _stt(pcm16k: np.ndarray) -> str:
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
        p = f.name
    try:
        with wave.open(p, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(16000)
            w.writeframes(pcm16k.astype(np.int16).tobytes())
        return (_whisper().listen(p) or "").strip()
    except Exception:
        return ""
    finally:
        try:
            os.unlink(p)
        except OSError:
            pass


# --- her reply, in her real voice -------------------------------------------
def _reply_to(name: str, user_text: str, history: list) -> str:
    """Her reply via the FULL honest turn — the SAME path as the text chat: capability
    grounding (route) + the HONESTY RAIL + her portrait memory + the heart. This is the
    whole point: without it the call bypasses the rail and she CONFABULATES personal facts
    ("when was I born?" -> she invents an answer). With it she says she doesn't know
    instead of making things up. History is carried by the turn's own session memory."""
    from . import server
    try:
        out = server._turn(name, user_text, voice=False)
        return (out.get("reply") or "").strip()
    except Exception:
        return "Sorry — my words got slow there. Say that again?"


# --- outgoing track: she speaks by pushing samples into this ----------------
class SpeakerTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self) -> None:
        super().__init__()
        self._q: asyncio.Queue = asyncio.Queue()
        self._buf = np.zeros(0, dtype=np.int16)
        self._pts = 0
        self._t0 = None

    def push(self, samples_i16: np.ndarray) -> None:
        self._q.put_nowait(np.asarray(samples_i16, dtype=np.int16))

    def speaking(self) -> bool:
        return self._q.qsize() > 0 or len(self._buf) > 0

    async def recv(self):
        if self._t0 is None:
            self._t0 = time.monotonic()
        while len(self._buf) < OUT_SAMPLES:
            try:
                self._buf = np.concatenate([self._buf, self._q.get_nowait()])
            except asyncio.QueueEmpty:
                self._buf = np.concatenate(
                    [self._buf, np.zeros(OUT_SAMPLES - len(self._buf), dtype=np.int16)])
                break
        out, self._buf = self._buf[:OUT_SAMPLES], self._buf[OUT_SAMPLES:]
        frame = av.AudioFrame.from_ndarray(out.reshape(1, -1), format="s16", layout="mono")
        frame.sample_rate = OUT_SR
        frame.pts = self._pts
        frame.time_base = fractions.Fraction(1, OUT_SR)
        self._pts += OUT_SAMPLES
        target = self._t0 + self._pts / OUT_SR        # pace to real time
        now = time.monotonic()
        if target > now:
            await asyncio.sleep(target - now)
        return frame


# --- the conversation session ----------------------------------------------
class CallSession:
    def __init__(self, pc, name: str = "Vera") -> None:
        self.pc = pc
        self.name = name
        self.speaker = SpeakerTrack()
        # addTrack is deferred to attach() (inside the on("track") handler) so it reuses the
        # incoming audio transceiver exactly like the working echo — adding it here, before
        # setRemoteDescription, can leave her voice on an m-line the browser never receives.
        from . import server          # the call runs in a SEPARATE process; load her recent
        try:                          # conversation from disk so she walks into the call knowing
            server._HISTORY.clear()   # what you've actually told her (your birthday) instead of
            server._load_history(name)  # confabulating it. The portrait memory comes via _turn.
        except Exception:
            pass
        self.history: list = []
        self._last_voice = time.monotonic()
        self._done = asyncio.Event()

    def attach(self, track) -> None:
        self.pc.addTrack(self.speaker)              # reuse the incoming transceiver to send her voice
        _log("call connected — speaker added, starting greeter + listener")
        asyncio.ensure_future(self._greet())
        asyncio.ensure_future(self._listen(track))

    async def _say(self, text: str) -> None:
        _log("speaking: %r" % text[:70])
        loop = asyncio.get_running_loop()
        samples = await loop.run_in_executor(None, _tts_samples, text)
        for i in range(0, len(samples), OUT_SAMPLES):
            self.speaker.push(samples[i:i + OUT_SAMPLES])
        _log("  pushed %d samples (%.1fs of audio)" % (len(samples), len(samples) / OUT_SR))
        self._last_voice = time.monotonic()

    async def _greet(self) -> None:
        await asyncio.sleep(0.3)
        _log("greeting (first TTS loads Kokoro, ~7s)…")
        await self._say("Hey — I'm here. What's on your mind?")

    async def _listen(self, track) -> None:
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
        speech: list = []
        in_speech = False
        gap = 0
        loop = asyncio.get_running_loop()
        _log("listening for your voice (VAD rms>%d, end-gap %d frames)…" % (_VAD_RMS, _UTT_GAP_FRAMES))
        try:
            while not self._done.is_set():
                frame = await track.recv()
                got = resampler.resample(frame)
                for rf in (got if isinstance(got, list) else [got]):
                    pcm = rf.to_ndarray().reshape(-1).astype(np.int16)
                    if self.speaker.speaking():        # don't transcribe her own voice
                        in_speech, speech, gap = False, [], 0
                        continue
                    rms = float(np.sqrt(np.mean((pcm.astype(np.float32)) ** 2))) if len(pcm) else 0.0
                    if rms > _VAD_RMS:
                        in_speech = True
                        gap = 0
                        speech.append(pcm)
                        self._last_voice = time.monotonic()
                    elif in_speech:
                        gap += 1
                        speech.append(pcm)
                        if gap >= _UTT_GAP_FRAMES:      # end of an utterance
                            utt = np.concatenate(speech)
                            _log("utterance ended (%.1fs) — transcribing" % (len(utt) / 16000))
                            speech, in_speech, gap = [], False, 0
                            await self._handle(np.frombuffer(utt.tobytes(), dtype=np.int16), loop)
                if (not self.speaker.speaking()
                        and time.monotonic() - self._last_voice > _SILENCE_TIMEOUT):
                    await self._say("Still there? ... Alright, I'll let you go. Talk soon.")
                    await asyncio.sleep(2.0)
                    break
        except Exception:
            pass
        await self._hangup()

    async def _handle(self, pcm16k: np.ndarray, loop) -> None:
        text = await loop.run_in_executor(None, _stt, pcm16k)
        _log("you said: %r" % text)
        if not text:
            return
        low = text.lower()
        if any(w in low for w in ("goodbye", "good bye", "bye", "talk later", "good night", "see you")):
            await self._say("Night. I'm here whenever you want me.")
            await asyncio.sleep(2.0)
            await self._hangup()
            return
        reply = await loop.run_in_executor(None, _reply_to, self.name, text, list(self.history))
        _log("she replies: %r" % reply[:70])
        self.history.append((text, reply))
        await self._say(reply)

    async def _hangup(self) -> None:
        self._done.set()
        try:
            await self.pc.close()
        except Exception:
            pass

```


## anima/mouth.py — KokoroVoice (TTS) + WhisperEars (STT), lines 563–642

```python
class KokoroVoice:
    """Kokoro TTS, loaded lazily. Synthesises a WAV; returns its path."""

    name = "kokoro"

    def __init__(self, voice="af_heart"):
        self.voice = voice
        self._pipe = None

    def available(self) -> bool:
        try:
            import kokoro  # noqa: F401
            return True
        except Exception:
            return False

    def speak(self, text: str, hints: dict, out_path: str) -> Optional[str]:
        try:
            import numpy as np
            import soundfile as sf
            from kokoro import KPipeline
            if self._pipe is None:
                self._pipe = KPipeline(lang_code="a")
            speed = hints.get("rate", 1.0)
            # Kokoro yields (graphemes, phonemes, audio); audio is a float tensor
            chunks = [np.asarray(audio, dtype="float32")
                      for _, _, audio in self._pipe(text, voice=self.voice, speed=speed)]
            if not chunks:
                return None
            sf.write(out_path, np.concatenate(chunks), 24000)
            return out_path
        except Exception as e:
            import sys
            print(f"[anima voice] Kokoro could not speak: {e}", file=sys.stderr)
            return None


class WhisperEars:
    """faster-whisper STT, loaded lazily. Transcribes audio -> text."""

    name = "faster-whisper"

    def __init__(self, model=None):
        # large-v3-turbo runs float32 on CPU here (CTranslate2 has no Metal), so it's
        # 2-6s per utterance — the biggest lag after you stop talking. A small English
        # model with int8 is ~4-6x faster with little accuracy loss on clear speech.
        # Override: ANIMA_WHISPER=large-v3-turbo (accuracy) or =base.en (max speed).
        self.model_name = model or os.environ.get("ANIMA_WHISPER", "small.en")
        self.compute_type = os.environ.get("ANIMA_WHISPER_COMPUTE", "int8")
        self._model = None

    def available(self) -> bool:
        try:
            import faster_whisper  # noqa: F401
            return True
        except Exception:
            return False

    def _load(self):
        if self._model is None:
            from faster_whisper import WhisperModel
            self._model = WhisperModel(self.model_name, compute_type=self.compute_type)
        return self._model

    def warm(self):
        """Load the STT model now (at startup) so the first utterance isn't slow."""
        try:
            self._load()
        except Exception:
            pass

    def listen(self, audio_path: str) -> str:
        m = self._load()
        segments, _ = m.transcribe(audio_path, vad_filter=True)
        return " ".join(s.text for s in segments).strip()


# --- the mouth --------------------------------------------------------------

@dataclass

```


## anima/voip_push.py

```python
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

```


---

# CLIENT — ios/VeraCall/ (Swift)


## ios/VeraCall/VeraCall/Sources/VeraCallApp.swift

```swift
//
//  VeraCallApp.swift
//  VeraCall
//
//  App entry point. Wires the SwiftUI scene to the AppDelegate, which owns the
//  long-lived singletons (CallKit provider, PushKit registry, the WebRTC client).
//  Those have to live at app scope, not view scope, because iOS may launch the app
//  straight into the background to deliver a VoIP push with no UI on screen at all.
//

import SwiftUI

@main
struct VeraCallApp: App {
    // UIApplicationDelegateAdaptor keeps the delegate alive for the whole process,
    // including background launches triggered by an incoming VoIP push.
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(appDelegate.callController)
                .environmentObject(appDelegate.settings)
        }
    }
}

```


## ios/VeraCall/VeraCall/Sources/RootView.swift

```swift
//
//  RootView.swift
//  VeraCall
//
//  Top-level UI. When there's an active call we show the in-call screen; otherwise the
//  home screen with a "Call Vera" test button (so you can verify audio without waiting
//  for a push) and a gear into Settings.
//

import SwiftUI

struct RootView: View {
    @EnvironmentObject private var call: CallController
    @State private var showSettings = false

    var body: some View {
        ZStack {
            if call.hasActiveCall {
                InCallView()
            } else {
                HomeView(showSettings: $showSettings)
            }
        }
        .sheet(isPresented: $showSettings) {
            SettingsView()
        }
        .preferredColorScheme(.dark)
    }
}

struct HomeView: View {
    @EnvironmentObject private var call: CallController
    @EnvironmentObject private var settings: VeraSettings
    @Binding var showSettings: Bool

    var body: some View {
        VStack(spacing: 28) {
            Spacer()

            Image(systemName: "waveform.circle.fill")
                .resizable()
                .scaledToFit()
                .frame(width: 96, height: 96)
                .foregroundStyle(.tint)

            Text("Vera")
                .font(.largeTitle.weight(.semibold))

            Text(settings.isConfigured
                 ? "Ready · \(settings.host):\(settings.port)"
                 : "Set the Mac address in Settings")
                .font(.callout)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            Spacer()

            Button {
                call.startOutgoingCall()
            } label: {
                Label("Call Vera", systemImage: "phone.fill")
                    .font(.title3.weight(.semibold))
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
            }
            .buttonStyle(.borderedProminent)
            .tint(.green)
            .disabled(!settings.isConfigured)
            .padding(.horizontal, 32)

            Button {
                showSettings = true
            } label: {
                Label("Settings", systemImage: "gearshape")
                    .font(.body)
            }
            .padding(.bottom, 24)
        }
        .padding()
    }
}

#Preview {
    HomeView(showSettings: .constant(false))
        .environmentObject(CallController())
        .environmentObject(VeraSettings())
}

```


## ios/VeraCall/VeraCall/Sources/CallController.swift

```swift
//
//  CallController.swift
//  VeraCall
//
//  The bridge between iOS CallKit and Vera's WebRTC audio. It owns:
//    - the CXProvider (the native incoming-call UI + system call state)
//    - the CXCallController (so the app can request actions, e.g. end the call)
//    - the WebRTCClient (the actual audio peer to the Mac)
//
//  Flow for an *incoming* call (the normal case — the Mac rings the phone):
//    VoIP push arrives -> AppDelegate -> reportIncomingCall(...) here ->
//    CXProvider shows the full-screen swipe-to-answer screen -> user swipes ->
//    provider(_:perform: CXAnswerCallAction) -> we start the WebRTC connection.
//
//  Flow for an *outgoing* call (the in-app "Call Vera" button, for testing without push):
//    startOutgoingCall() -> CXStartCallAction -> on success we connect WebRTC.
//
//  CallKit requires the audio session to be configured but NOT activated by us before
//  answering; the provider calls provider(_:didActivate:) when it's our turn to start
//  audio. We start/route WebRTC audio there. See Apple's CallKit audio guidance.
//

import Foundation
import Combine
import CallKit
import AVFoundation
import WebRTC
import os.log

@MainActor
final class CallController: NSObject, ObservableObject {

    // What the in-call UI binds to.
    @Published private(set) var hasActiveCall = false
    @Published private(set) var connectionState: WebRTCState = .idle
    @Published var isMuted = false
    @Published var isSpeaker = true   // default to loudspeaker for a hands-free companion call

    /// Display name shown on the native call screen and in-app.
    let calleeName = "Vera"

    private let log = Logger(subsystem: "ai.guruu.vera.VeraCall", category: "call")
    // CXProvider is documented as safe to message from any thread; PushKit may invoke
    // reportIncomingCall(...) (which touches `provider`) from its own queue, so mark it
    // nonisolated to allow that without hopping actors — required to report the call
    // synchronously before the PushKit completion handler fires (iOS 13+ contract).
    private nonisolated let provider: CXProvider
    private let callController = CXCallController()
    private let webRTC = WebRTCClient()

    /// The settings are injected so the controller knows where the Mac is. Set by AppDelegate.
    weak var settings: VeraSettings?

    /// One call at a time; we track its UUID so CallKit actions map to it.
    private var currentCallID: UUID?

    override init() {
        self.provider = CXProvider(configuration: CallController.providerConfiguration())
        super.init()
        provider.setDelegate(self, queue: nil)
        webRTC.delegate = self
    }

    /// CXProviderConfiguration: how the system renders Vera's calls. Audio-only (video
    /// disabled), one call, generic handle type (we ring "Vera", not a phone number).
    static func providerConfiguration() -> CXProviderConfiguration {
        let config = CXProviderConfiguration()
        config.supportsVideo = false
        config.maximumCallGroups = 1
        config.maximumCallsPerCallGroup = 1
        config.supportedHandleTypes = [.generic]
        config.includesCallsInRecents = true
        // Drop a VeraCallIcon (40x40 template PNG) in the asset catalog to brand the
        // in-call screen; harmless if absent.
        if let icon = UIImage(named: "VeraCallIcon") {
            config.iconTemplateImageData = icon.pngData()
        }
        return config
    }

    // MARK: - Incoming (the Mac rings the phone via VoIP push)

    /// Report an incoming call to CallKit so iOS shows the native swipe-to-answer UI.
    /// Called from the PushKit handler. MUST be called synchronously inside
    /// pushRegistry(_:didReceiveIncomingPushWith:for:completion:) for a .voIP push,
    /// or iOS (13+) will terminate the app for not reporting a call.
    ///
    /// - Parameters:
    ///   - callID: a UUID for this call. If the push payload carries a "call_uuid",
    ///             pass it so the Mac and phone agree on the identifier.
    ///   - handle: what to show as the caller (defaults to "Vera").
    ///   - completion: invoked after CallKit has been told; forward this to PushKit.
    nonisolated func reportIncomingCall(callID: UUID,
                                        handle: String,
                                        completion: @escaping () -> Void) {
        let update = CXCallUpdate()
        update.remoteHandle = CXHandle(type: .generic, value: handle)
        update.localizedCallerName = handle
        update.hasVideo = false
        update.supportsHolding = false
        update.supportsGrouping = false
        update.supportsUngrouping = false
        update.supportsDTMF = false

        provider.reportNewIncomingCall(with: callID, update: update) { [weak self] error in
            if let error = error {
                // Reporting failed (e.g. Do Not Disturb policy rejected it). We still must
                // call completion so PushKit doesn't think we hung.
                self?.log.error("reportNewIncomingCall failed: \(error.localizedDescription)")
            } else {
                Task { @MainActor in self?.currentCallID = callID }
            }
            completion()
        }
    }

    // MARK: - Outgoing (in-app test button — no push required)

    /// Place a call to Vera from inside the app. Routes through CallKit so the audio
    /// session and call state are managed identically to an answered incoming call.
    func startOutgoingCall() {
        guard settings?.isConfigured == true else {
            connectionState = .failed("Set the Mac host in Settings first")
            return
        }
        let callID = UUID()
        let handle = CXHandle(type: .generic, value: calleeName)
        let startAction = CXStartCallAction(call: callID, handle: handle)
        startAction.isVideo = false
        let transaction = CXTransaction(action: startAction)
        callController.request(transaction) { [weak self] error in
            Task { @MainActor in
                guard let self = self else { return }
                if let error = error {
                    self.connectionState = .failed("start call: \(error.localizedDescription)")
                } else {
                    self.currentCallID = callID
                    self.provider.reportOutgoingCall(with: callID, startedConnectingAt: nil)
                }
            }
        }
    }

    // MARK: - End

    /// End the active call (the in-call hang-up button). Routes through CallKit so the
    /// system UI clears too. The actual WebRTC teardown happens in the End action handler.
    func endCall() {
        guard let callID = currentCallID else {
            // Nothing registered with CallKit; just make sure WebRTC is down.
            teardownWebRTC()
            return
        }
        let endAction = CXEndCallAction(call: callID)
        let transaction = CXTransaction(action: endAction)
        callController.request(transaction) { [weak self] error in
            if let error = error {
                self?.log.error("end call request: \(error.localizedDescription)")
                Task { @MainActor in self?.teardownWebRTC() }
            }
        }
    }

    func toggleMute() {
        isMuted.toggle()
        webRTC.setMuted(isMuted)
        // Reflect to CallKit so the system mute state stays in sync.
        if let callID = currentCallID {
            let action = CXSetMutedCallAction(call: callID, muted: isMuted)
            callController.request(CXTransaction(action: action)) { _ in }
        }
    }

    func toggleSpeaker() {
        isSpeaker.toggle()
        webRTC.setSpeaker(isSpeaker)
    }

    // MARK: - WebRTC plumbing

    /// Start the audio connection to the Mac. Called once CallKit hands us the activated
    /// audio session (provider(_:didActivate:)).
    private func startWebRTC() {
        guard let settings = settings, let url = settings.offerURL else {
            connectionState = .failed("Bad Mac URL — check Settings")
            return
        }
        let token = settings.authToken.isEmpty ? nil : settings.authToken
        webRTC.setSpeaker(isSpeaker)
        webRTC.setMuted(isMuted)
        webRTC.connect(offerURL: url, bearerToken: token)
    }

    private func teardownWebRTC() {
        webRTC.close()
        hasActiveCall = false
        currentCallID = nil
        isMuted = false
        connectionState = .idle
    }

    /// CallKit-managed audio session. We do NOT activate it ourselves; CallKit does and
    /// then calls provider(_:didActivate:). We only declare the category/mode here so the
    /// session is correctly configured for VoIP (voiceChat) before activation.
    private func configureAudioSession() {
        let session = RTCAudioSession.sharedInstance()
        session.lockForConfiguration()
        do {
            try session.setCategory(.playAndRecord,
                                    mode: .voiceChat,
                                    options: [.allowBluetoothHFP, .allowBluetoothA2DP])
        } catch {
            log.error("audio session config: \(error.localizedDescription)")
        }
        session.unlockForConfiguration()
    }
}

// MARK: - CXProviderDelegate

extension CallController: CXProviderDelegate {

    nonisolated func providerDidReset(_ provider: CXProvider) {
        // The provider was reset (e.g. the system tore down all calls). Drop everything.
        Task { @MainActor in self.teardownWebRTC() }
    }

    nonisolated func provider(_ provider: CXProvider, perform action: CXAnswerCallAction) {
        // User swiped to answer. Configure (but don't activate) the audio session, mark the
        // call active, and let the system activate audio -> didActivate starts WebRTC.
        Task { @MainActor in
            self.configureAudioSession()
            self.hasActiveCall = true
            self.connectionState = .connecting
        }
        action.fulfill()
    }

    nonisolated func provider(_ provider: CXProvider, perform action: CXStartCallAction) {
        // Outgoing call accepted by the system. Same audio prep as answering.
        Task { @MainActor in
            self.configureAudioSession()
            self.hasActiveCall = true
            self.connectionState = .connecting
        }
        action.fulfill()
    }

    nonisolated func provider(_ provider: CXProvider, perform action: CXEndCallAction) {
        Task { @MainActor in self.teardownWebRTC() }
        action.fulfill()
    }

    nonisolated func provider(_ provider: CXProvider, perform action: CXSetMutedCallAction) {
        Task { @MainActor in
            self.isMuted = action.isMuted
            self.webRTC.setMuted(action.isMuted)
        }
        action.fulfill()
    }

    // CallKit hands us the activated audio session here — THIS is where we start audio.
    nonisolated func provider(_ provider: CXProvider, didActivate audioSession: AVAudioSession) {
        let rtcSession = RTCAudioSession.sharedInstance()
        rtcSession.audioSessionDidActivate(audioSession)
        rtcSession.isAudioEnabled = true
        Task { @MainActor in self.startWebRTC() }
    }

    nonisolated func provider(_ provider: CXProvider, didDeactivate audioSession: AVAudioSession) {
        let rtcSession = RTCAudioSession.sharedInstance()
        rtcSession.audioSessionDidDeactivate(audioSession)
        rtcSession.isAudioEnabled = false
    }
}

// MARK: - WebRTCClientDelegate

extension CallController: WebRTCClientDelegate {
    nonisolated func webRTCClient(_ client: WebRTCClient, didChange state: WebRTCState) {
        Task { @MainActor in
            self.connectionState = state
            switch state {
            case .failed, .closed:
                // If the media dies, end the CallKit call too so the UI doesn't get stuck.
                if self.hasActiveCall { self.endCall() }
            default:
                break
            }
        }
    }
}

```


## ios/VeraCall/VeraCall/Sources/WebRTCClient.swift

```swift
//
//  WebRTCClient.swift
//  VeraCall
//
//  The audio-only WebRTC peer. This is the Swift twin of the JS in call_server.py's
//  GET /calltest page. The handshake is intentionally minimal (no trickle ICE, no
//  data channel): create an offer, POST it to the Mac, apply the returned answer.
//
//  Exact handshake (must match anima/call_server.py::_offer):
//    1. getUserMedia(audio) -> add a local mic audio track
//    2. createOffer / setLocalDescription
//    3. POST {"sdp": localSDP, "type": "offer"}  to  http://<mac>:8766/webrtc_offer?mode=loop
//    4. response is {"sdp": answerSDP, "type": "answer"}
//    5. setRemoteDescription(answer)
//    6. her audio arrives on the remote track -> play it
//
//  No STUN/TURN servers are configured: the phone and Mac are on the same Tailscale
//  tunnel, so host candidates over the tunnel resolve directly. (aiortc on the Mac
//  likewise opens a direct peer connection.)
//
//  Requires the WebRTC binary framework. Add via Swift Package Manager:
//      https://github.com/stasel/WebRTC  (product name: WebRTC)
//  See README "Adding the WebRTC framework". The import below is `import WebRTC`.
//

import Foundation
import WebRTC
import os.log

/// High-level connection state surfaced to the UI and CallKit.
enum WebRTCState: Equatable {
    case idle
    case connecting
    case connected
    case failed(String)
    case closed
}

protocol WebRTCClientDelegate: AnyObject {
    func webRTCClient(_ client: WebRTCClient, didChange state: WebRTCState)
}

final class WebRTCClient: NSObject {

    // One process-wide factory. RTCInitializeSSL() must be called once before use and
    // RTCCleanupSSL() at teardown; we do that in AppDelegate's lifecycle.
    static let factory: RTCPeerConnectionFactory = {
        let encoder = RTCDefaultVideoEncoderFactory()
        let decoder = RTCDefaultVideoDecoderFactory()
        return RTCPeerConnectionFactory(encoderFactory: encoder, decoderFactory: decoder)
    }()

    weak var delegate: WebRTCClientDelegate?

    private let log = Logger(subsystem: "ai.guruu.vera.VeraCall", category: "webrtc")
    private var peerConnection: RTCPeerConnection?
    private var localAudioTrack: RTCAudioTrack?
    private var remoteAudioTrack: RTCAudioTrack?
    private let audioQueue = DispatchQueue(label: "ai.guruu.vera.audio")

    private(set) var state: WebRTCState = .idle {
        didSet { delegate?.webRTCClient(self, didChange: state) }
    }

    // MARK: - Connect

    /// Opens the peer connection, builds the local offer, POSTs it to the Mac, applies
    /// the answer. `offerURL` already carries the ?mode= query. `bearerToken` is the
    /// Mac's ANIMA_TOKEN (sent as Authorization: Bearer ...), or nil/empty to omit.
    func connect(offerURL: URL, bearerToken: String?) {
        state = .connecting

        let config = RTCConfiguration()
        // No ICE servers on purpose — direct over the tailnet tunnel. If you ever move
        // off Tailscale you'd add a STUN server here, e.g.:
        //   config.iceServers = [RTCIceServer(urlStrings: ["stun:stun.l.google.com:19302"])]
        config.iceServers = []
        config.sdpSemantics = .unifiedPlan
        // Gather all candidates, then send the offer once (the Mac has no trickle path).
        config.continualGatheringPolicy = .gatherOnce

        let constraints = RTCMediaConstraints(mandatoryConstraints: nil,
                                              optionalConstraints: nil)
        guard let pc = WebRTCClient.factory.peerConnection(with: config,
                                                           constraints: constraints,
                                                           delegate: self) else {
            state = .failed("Could not create RTCPeerConnection")
            return
        }
        self.peerConnection = pc

        addMicTrack(to: pc)

        let offerConstraints = RTCMediaConstraints(
            mandatoryConstraints: [
                kRTCMediaConstraintsOfferToReceiveAudio: kRTCMediaConstraintsValueTrue,
                kRTCMediaConstraintsOfferToReceiveVideo: kRTCMediaConstraintsValueFalse
            ],
            optionalConstraints: nil)

        pc.offer(for: offerConstraints) { [weak self] sdp, error in
            guard let self = self else { return }
            if let error = error {
                self.state = .failed("createOffer: \(error.localizedDescription)")
                return
            }
            guard let sdp = sdp else {
                self.state = .failed("createOffer returned no SDP")
                return
            }
            pc.setLocalDescription(sdp) { [weak self] error in
                guard let self = self else { return }
                if let error = error {
                    self.state = .failed("setLocalDescription: \(error.localizedDescription)")
                    return
                }
                // gatherOnce: wait until ICE gathering completes so the POSTed SDP carries
                // the host candidates. We poll the local description in the ICE state
                // callback; once complete we send whatever local description we have.
                self.maybeSendOffer(pc: pc, offerURL: offerURL, bearerToken: bearerToken)
            }
        }
    }

    private var offerSent = false

    /// Sends the offer once ICE gathering is complete (or immediately if already complete).
    private func maybeSendOffer(pc: RTCPeerConnection, offerURL: URL, bearerToken: String?) {
        // Capture the params; the actual POST fires from the ICE-gathering-complete callback
        // (or here, if gathering finished synchronously, which can happen with no ICE servers).
        self.pendingOffer = (pc, offerURL, bearerToken)
        if pc.iceGatheringState == .complete {
            sendPendingOffer()
        }
    }

    private var pendingOffer: (pc: RTCPeerConnection, url: URL, token: String?)?

    private func sendPendingOffer() {
        guard !offerSent, let pending = pendingOffer,
              let localSDP = pending.pc.localDescription else { return }
        offerSent = true

        var request = URLRequest(url: pending.url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if let token = pending.token, !token.isEmpty {
            request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        }
        request.timeoutInterval = 20

        // call_server expects exactly {"sdp": ..., "type": "offer"} and replies the same.
        let body: [String: String] = ["sdp": localSDP.sdp, "type": sdpTypeString(localSDP.type)]
        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: body, options: [])
        } catch {
            state = .failed("encode offer: \(error.localizedDescription)")
            return
        }

        log.info("POSTing offer to \(pending.url.absoluteString, privacy: .public)")
        URLSession.shared.dataTask(with: request) { [weak self] data, response, error in
            guard let self = self else { return }
            if let error = error {
                self.state = .failed("offer POST failed: \(error.localizedDescription)")
                return
            }
            guard let http = response as? HTTPURLResponse else {
                self.state = .failed("offer POST: no HTTP response")
                return
            }
            guard (200..<300).contains(http.statusCode) else {
                self.state = .failed("offer POST: HTTP \(http.statusCode)")
                return
            }
            guard let data = data,
                  let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let answerSDP = json["sdp"] as? String,
                  let typeStr = json["type"] as? String else {
                self.state = .failed("offer POST: malformed answer JSON")
                return
            }
            let answer = RTCSessionDescription(type: self.sdpType(from: typeStr), sdp: answerSDP)
            pending.pc.setRemoteDescription(answer) { [weak self] error in
                guard let self = self else { return }
                if let error = error {
                    self.state = .failed("setRemoteDescription: \(error.localizedDescription)")
                    return
                }
                self.log.info("remote answer applied; waiting for media")
                // state -> .connected is driven by the RTCPeerConnectionDelegate connection
                // state callback below, mirroring call_server's connectionstatechange.
            }
        }.resume()
    }

    // MARK: - Mic / speaker

    private func addMicTrack(to pc: RTCPeerConnection) {
        let constraints = RTCMediaConstraints(mandatoryConstraints: nil, optionalConstraints: nil)
        let audioSource = WebRTCClient.factory.audioSource(with: constraints)
        let track = WebRTCClient.factory.audioTrack(with: audioSource, trackId: "vera-mic0")
        pc.add(track, streamIds: ["vera-stream0"])
        self.localAudioTrack = track
    }

    /// Mute/unmute the outgoing mic. The track stays in the connection; we just gate it.
    func setMuted(_ muted: Bool) {
        localAudioTrack?.isEnabled = !muted
    }

    /// Route her audio to the loudspeaker (true) or earpiece (false).
    func setSpeaker(_ loud: Bool) {
        audioQueue.async {
            let session = RTCAudioSession.sharedInstance()
            session.lockForConfiguration()
            defer { session.unlockForConfiguration() }
            do {
                if loud {
                    try session.overrideOutputAudioPort(.speaker)
                } else {
                    try session.overrideOutputAudioPort(.none)
                }
            } catch {
                self.log.error("speaker override failed: \(error.localizedDescription)")
            }
        }
    }

    // MARK: - Teardown

    func close() {
        peerConnection?.close()
        peerConnection = nil
        localAudioTrack = nil
        remoteAudioTrack = nil
        pendingOffer = nil
        offerSent = false
        state = .closed
    }

    // MARK: - SDP type helpers

    private func sdpTypeString(_ type: RTCSdpType) -> String {
        switch type {
        case .offer: return "offer"
        case .prAnswer: return "pranswer"
        case .answer: return "answer"
        case .rollback: return "rollback"
        @unknown default: return "offer"
        }
    }

    private func sdpType(from string: String) -> RTCSdpType {
        switch string.lowercased() {
        case "offer": return .offer
        case "pranswer": return .prAnswer
        case "answer": return .answer
        case "rollback": return .rollback
        default: return .answer
        }
    }
}

// MARK: - RTCPeerConnectionDelegate

extension WebRTCClient: RTCPeerConnectionDelegate {

    func peerConnection(_ pc: RTCPeerConnection, didChange newState: RTCIceGatheringState) {
        log.debug("ICE gathering: \(newState.rawValue)")
        if newState == .complete {
            // gatherOnce finished — now the local SDP has all host candidates; send it.
            sendPendingOffer()
        }
    }

    func peerConnection(_ pc: RTCPeerConnection, didChange newState: RTCPeerConnectionState) {
        log.info("connection state: \(newState.rawValue)")
        switch newState {
        case .connected:
            state = .connected
        case .failed:
            state = .failed("peer connection failed")
        case .closed:
            state = .closed
        case .disconnected:
            // Brief blips can self-heal over the tunnel; surface but don't hard-close.
            state = .failed("disconnected")
        default:
            break
        }
    }

    func peerConnection(_ pc: RTCPeerConnection, didAdd rtpReceiver: RTCRtpReceiver,
                        streams: [RTCMediaStream]) {
        if let track = rtpReceiver.track as? RTCAudioTrack {
            self.remoteAudioTrack = track
            track.isEnabled = true   // play her voice
            log.info("remote audio track added")
        }
    }

    // The remaining delegate methods are required by the protocol but unused for a
    // minimal audio call (no renegotiation, no data channel, no trickle ICE out).
    func peerConnectionShouldNegotiate(_ pc: RTCPeerConnection) {}
    func peerConnection(_ pc: RTCPeerConnection, didChange stateChanged: RTCSignalingState) {}
    func peerConnection(_ pc: RTCPeerConnection, didAdd stream: RTCMediaStream) {}
    func peerConnection(_ pc: RTCPeerConnection, didRemove stream: RTCMediaStream) {}
    func peerConnection(_ pc: RTCPeerConnection, didChange newState: RTCIceConnectionState) {}
    func peerConnection(_ pc: RTCPeerConnection, didGenerate candidate: RTCIceCandidate) {
        // No trickle: candidates are folded into the offer via gatherOnce, so nothing to send.
    }
    func peerConnection(_ pc: RTCPeerConnection, didRemove candidates: [RTCIceCandidate]) {}
    func peerConnection(_ pc: RTCPeerConnection, didOpen dataChannel: RTCDataChannel) {}
}

```


## ios/VeraCall/VeraCall/Sources/AppDelegate.swift

```swift
//
//  AppDelegate.swift
//  VeraCall
//
//  Owns the app-scoped singletons and the PushKit VoIP registry. iOS can launch this
//  app straight into the background to deliver a VoIP push (even from a terminated
//  state), so registration must happen at launch, unconditionally.
//
//  PushKit contract (iOS 13+): when a .voIP push arrives you MUST report an incoming
//  call to CallKit *synchronously* inside didReceiveIncomingPushWith, and only call the
//  completion handler afterwards. Failing to do so gets your app killed and, after a few
//  offenses, your VoIP pushes throttled. We satisfy this by calling
//  CallController.reportIncomingCall(...) and forwarding its completion.
//

import UIKit
import PushKit
import CallKit
import WebRTC
import os.log

final class AppDelegate: NSObject, UIApplicationDelegate {

    let settings = VeraSettings()
    lazy var callController: CallController = {
        let c = CallController()
        c.settings = settings
        return c
    }()

    private let log = Logger(subsystem: "ai.guruu.vera.VeraCall", category: "app")
    private var voipRegistry: PKPushRegistry?

    func application(_ application: UIApplication,
                     didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil) -> Bool {
        // WebRTC global init, once per process.
        RTCInitializeSSL()
        // Let RTCAudioSession cooperate with CallKit instead of auto-configuring.
        RTCAudioSession.sharedInstance().useManualAudio = true
        RTCAudioSession.sharedInstance().isAudioEnabled = false

        registerForVoIPPushes()
        return true
    }

    func applicationWillTerminate(_ application: UIApplication) {
        RTCCleanupSSL()
    }

    // MARK: - PushKit registration

    private func registerForVoIPPushes() {
        let registry = PKPushRegistry(queue: .main)
        registry.delegate = self
        registry.desiredPushTypes = [.voIP]
        self.voipRegistry = registry
        log.info("registered for VoIP pushes")
    }
}

// MARK: - PKPushRegistryDelegate

extension AppDelegate: PKPushRegistryDelegate {

    /// The VoIP token. This is the token the Mac must send the push TO. Register it with
    /// the Mac by POSTing {"voip_token": "<hex>", "platform": "ios", "bundle_id": "..."}
    /// to anima/server.py's /device endpoint (Bearer ANIMA_TOKEN). See README.
    func pushRegistry(_ registry: PKPushRegistry,
                      didUpdate pushCredentials: PKPushCredentials,
                      for type: PKPushType) {
        guard type == .voIP else { return }
        let token = pushCredentials.token.map { String(format: "%02x", $0) }.joined()
        log.info("VoIP push token: \(token, privacy: .public)")
        // Surface it to the UI (Settings screen shows + copies it) and try to auto-register.
        NotificationCenter.default.post(name: .veraDidUpdateVoIPToken,
                                        object: nil,
                                        userInfo: ["token": token])
        DeviceRegistration.register(voipToken: token, settings: settings)
    }

    func pushRegistry(_ registry: PKPushRegistry,
                      didInvalidatePushTokenFor type: PKPushType) {
        guard type == .voIP else { return }
        log.info("VoIP push token invalidated")
    }

    /// An incoming VoIP push. Report the call to CallKit synchronously, then complete.
    func pushRegistry(_ registry: PKPushRegistry,
                      didReceiveIncomingPushWith payload: PKPushPayload,
                      for type: PKPushType,
                      completion: @escaping () -> Void) {
        guard type == .voIP else { completion(); return }

        // Expected payload shape (documented in voip_push.py and the README):
        // {
        //   "aps": { "alert": "Vera is calling", "sound": "default" },   // optional
        //   "handle": "Vera",                                            // caller label
        //   "call_uuid": "EAB3...-...."                                  // optional, agreed id
        // }
        let dict = payload.dictionaryPayload
        let handle = (dict["handle"] as? String) ?? "Vera"
        let callID: UUID = {
            if let s = dict["call_uuid"] as? String, let u = UUID(uuidString: s) { return u }
            return UUID()
        }()

        log.info("incoming VoIP push -> reporting call \(callID.uuidString, privacy: .public)")
        callController.reportIncomingCall(callID: callID, handle: handle, completion: completion)
    }
}

extension Notification.Name {
    /// Posted when the VoIP token changes, so the Settings screen can display/copy it.
    static let veraDidUpdateVoIPToken = Notification.Name("veraDidUpdateVoIPToken")
}

```


## ios/VeraCall/VeraCall/Sources/DeviceRegistration.swift

```swift
//
//  DeviceRegistration.swift
//  VeraCall
//
//  Tells the Mac where to send VoIP pushes, by POSTing the phone's PushKit token to
//  anima/server.py's existing /device endpoint. We do NOT modify server.py; we just
//  speak its protocol.
//
//  IMPORTANT: /device lives on the MAIN anima server (default port 8765), NOT on the
//  call server (8766). It is gated behind ANIMA_TOKEN (sent as Authorization: Bearer).
//  _store_device() accepts: {"token": <apns alert token>, "voip_token": <pushkit token>,
//  "platform": "ios", "bundle_id": "..."} and stores it under .anima/<name>.device.json.
//  Vera's reminder/call subsystem then reads voip_token to ring this phone.
//
//  The main-server port is derived from the call port the user configured: call server
//  default 8766 -> main server default 8765. If your setup differs, change MAIN_PORT.
//

import Foundation
import os.log

enum DeviceRegistration {

    /// The main anima server port. The call server is 8766; the brain/server is 8765.
    /// If you run the main server on a non-default port, set it here.
    static let mainServerPort = 8765

    private static let log = Logger(subsystem: "ai.guruu.vera.VeraCall", category: "register")

    /// POST the VoIP token to the Mac's /device endpoint. Best-effort: failures are logged,
    /// not surfaced, because the user can always copy the token from Settings and register
    /// it by hand (curl) per the README.
    static func register(voipToken: String, settings: VeraSettings) {
        guard settings.isConfigured else { return }

        var c = URLComponents()
        c.scheme = "http"
        c.host = settings.host
        c.port = mainServerPort
        c.path = "/device"
        guard let url = c.url else { return }

        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        if !settings.authToken.isEmpty {
            request.setValue("Bearer \(settings.authToken)", forHTTPHeaderField: "Authorization")
        }
        request.timeoutInterval = 15

        let bundleID = Bundle.main.bundleIdentifier ?? ""
        let body: [String: String] = [
            "voip_token": voipToken,
            "platform": "ios",
            "bundle_id": bundleID
        ]
        guard let data = try? JSONSerialization.data(withJSONObject: body) else { return }
        request.httpBody = data

        URLSession.shared.dataTask(with: request) { _, response, error in
            if let error = error {
                log.error("device registration failed: \(error.localizedDescription)")
                return
            }
            if let http = response as? HTTPURLResponse {
                log.info("device registration -> HTTP \(http.statusCode)")
            }
        }.resume()
    }
}

```


## ios/VeraCall/VeraCall/Sources/Settings.swift

```swift
//
//  Settings.swift
//  VeraCall
//
//  Where the Mac lives + the shared secret, persisted in UserDefaults. The phone
//  reaches the Mac directly over the Tailscale/WireGuard tunnel, so `host` is the
//  Mac's tailnet hostname (e.g. vera-mac.tailnet.ts.net) or its 100.x.y.z tailnet IP
//  — NOT a public address. No STUN/TURN is involved; the tunnel is the transport.
//
//  `port` defaults to 8766 to match anima/call_server.py (env ANIMA_CALL_PORT).
//  `authToken` is the Mac's ANIMA_TOKEN; it is sent as `Authorization: Bearer <token>`
//  on the /webrtc_offer POST. The call_server's _offer() currently does not enforce it
//  (see its phase-2 TODO), but anima/server.py's /device endpoint DOES require it, so we
//  keep one token field for both. Leave blank only if the Mac has ANIMA_TOKEN unset.
//

import Foundation
import Combine

final class VeraSettings: ObservableObject {
    private enum Key {
        static let host = "vera.host"
        static let port = "vera.port"
        static let token = "vera.authToken"
        static let mode = "vera.mode"
    }

    /// Mac's tailnet hostname or 100.x tailnet IP. Placeholder until the user sets theirs.
    @Published var host: String {
        didSet { UserDefaults.standard.set(host, forKey: Key.host) }
    }

    /// Call server port. Matches ANIMA_CALL_PORT (default 8766).
    @Published var port: Int {
        didSet { UserDefaults.standard.set(port, forKey: Key.port) }
    }

    /// Mac's ANIMA_TOKEN. Sent as a Bearer token on the offer POST. May be empty.
    @Published var authToken: String {
        didSet { UserDefaults.standard.set(authToken, forKey: Key.token) }
    }

    /// "loop" = talk to Vera (default), "echo" = bounce your own mic back (audio test).
    @Published var mode: String {
        didSet { UserDefaults.standard.set(mode, forKey: Key.mode) }
    }

    init() {
        let d = UserDefaults.standard
        self.host = d.string(forKey: Key.host) ?? "vera-mac.tailnet.ts.net"
        let p = d.integer(forKey: Key.port)
        self.port = p == 0 ? 8766 : p
        self.authToken = d.string(forKey: Key.token) ?? ""
        self.mode = d.string(forKey: Key.mode) ?? "loop"
    }

    /// The full offer URL, including the ?mode= query the call_server reads.
    /// Mirrors call_server's GET /calltest handshake: POST {sdp,type} -> {sdp,type}.
    var offerURL: URL? {
        var c = URLComponents()
        c.scheme = "http"            // plain HTTP is fine: the tunnel itself is encrypted.
        c.host = host
        c.port = port
        c.path = "/webrtc_offer"
        c.queryItems = [URLQueryItem(name: "mode", value: mode)]
        return c.url
    }

    var isConfigured: Bool {
        !host.trimmingCharacters(in: .whitespaces).isEmpty && port > 0
    }
}

```


## ios/VeraCall/VeraCall/Sources/SettingsView.swift

```swift
//
//  SettingsView.swift
//  VeraCall
//
//  Configure where the Mac lives (tailnet host + call port), the shared ANIMA_TOKEN,
//  and the call mode (loop = talk to Vera, echo = mic loopback test). Also displays the
//  device's VoIP push token so you can register it with the Mac (it auto-registers to
//  /device too, but the token is shown here so you can copy it for a manual curl).
//

import SwiftUI
import UIKit   // UIPasteboard (copy VoIP token)

struct SettingsView: View {
    @EnvironmentObject private var settings: VeraSettings
    @Environment(\.dismiss) private var dismiss

    @State private var portText: String = ""
    @State private var voipToken: String = ""

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField("vera-mac.tailnet.ts.net", text: $settings.host)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .keyboardType(.URL)
                    TextField("8766", text: $portText)
                        .keyboardType(.numberPad)
                        // iOS 16-compatible single-parameter onChange (the two-parameter
                        // (old, new) form is iOS 17+).
                        .onChange(of: portText) { newValue in
                            if let p = Int(newValue.filter(\.isNumber)), p > 0, p < 65536 {
                                settings.port = p
                            }
                        }
                } header: {
                    Text("Mac (over Tailscale)")
                } footer: {
                    Text("The Mac's tailnet hostname or 100.x tailnet IP, and the call "
                       + "server port (ANIMA_CALL_PORT, default 8766). No STUN/TURN — the "
                       + "phone reaches the Mac directly over the tunnel.")
                }

                Section {
                    SecureField("ANIMA_TOKEN (blank if unset)", text: $settings.authToken)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                } header: {
                    Text("Shared secret")
                } footer: {
                    Text("Sent as Authorization: Bearer on the offer POST and on /device "
                       + "registration. Match the Mac's ANIMA_TOKEN. Leave blank only if "
                       + "the Mac runs with no token (local testing).")
                }

                Section {
                    Picker("Mode", selection: $settings.mode) {
                        Text("Talk to Vera").tag("loop")
                        Text("Echo (mic test)").tag("echo")
                    }
                    .pickerStyle(.segmented)
                } header: {
                    Text("Call mode")
                } footer: {
                    Text("\"Echo\" bounces your own mic back so you can confirm two-way "
                       + "audio before involving the conversation loop.")
                }

                Section {
                    if voipToken.isEmpty {
                        Text("Not yet received")
                            .foregroundStyle(.secondary)
                    } else {
                        Text(voipToken)
                            .font(.system(.footnote, design: .monospaced))
                            .textSelection(.enabled)
                        Button {
                            UIPasteboard.general.string = voipToken
                        } label: {
                            Label("Copy token", systemImage: "doc.on.doc")
                        }
                    }
                } header: {
                    Text("VoIP push token")
                } footer: {
                    Text("This device's PushKit token. It auto-registers to the Mac's "
                       + "/device endpoint, or copy it and POST it yourself (see README). "
                       + "This is the token voip_push.py sends the ring TO.")
                }
            }
            .navigationTitle("Settings")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
            .onAppear { portText = String(settings.port) }
            .onReceive(NotificationCenter.default.publisher(for: .veraDidUpdateVoIPToken)) { note in
                if let t = note.userInfo?["token"] as? String { voipToken = t }
            }
        }
    }
}

#Preview {
    SettingsView().environmentObject(VeraSettings())
}

```


## ios/VeraCall/VeraCall/Sources/InCallView.swift

```swift
//
//  InCallView.swift
//  VeraCall
//
//  Minimal in-call surface shown while a call is live: the "Vera" label, the live
//  connection state, a mute toggle, a speaker toggle, and hang up. This is the in-app
//  screen; the native CallKit screen also appears for incoming calls / from the lock
//  screen — both drive the same CallController.
//

import SwiftUI

struct InCallView: View {
    @EnvironmentObject private var call: CallController

    var body: some View {
        VStack(spacing: 0) {
            Spacer()

            PulsingWaveform(active: call.connectionState == .connected)

            Text(call.calleeName)
                .font(.system(size: 36, weight: .semibold))
                .padding(.top, 18)

            Text(stateLabel)
                .font(.callout)
                .foregroundStyle(.secondary)
                .padding(.top, 6)

            Spacer()

            HStack(spacing: 56) {
                CallButton(title: call.isMuted ? "Unmute" : "Mute",
                           systemImage: call.isMuted ? "mic.slash.fill" : "mic.fill",
                           tint: call.isMuted ? .orange : .gray) {
                    call.toggleMute()
                }
                CallButton(title: "Speaker",
                           systemImage: call.isSpeaker ? "speaker.wave.3.fill" : "speaker.fill",
                           tint: call.isSpeaker ? .blue : .gray) {
                    call.toggleSpeaker()
                }
            }
            .padding(.bottom, 44)

            Button {
                call.endCall()
            } label: {
                Image(systemName: "phone.down.fill")
                    .font(.system(size: 30, weight: .bold))
                    .foregroundStyle(.white)
                    .frame(width: 76, height: 76)
                    .background(Circle().fill(.red))
            }
            .padding(.bottom, 48)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Color.black.ignoresSafeArea())
    }

    private var stateLabel: String {
        switch call.connectionState {
        case .idle: return "Starting…"
        case .connecting: return "Connecting…"
        case .connected: return "Connected"
        case .failed(let why): return "Call failed · \(why)"
        case .closed: return "Ended"
        }
    }
}

private struct CallButton: View {
    let title: String
    let systemImage: String
    let tint: Color
    let action: () -> Void

    var body: some View {
        VStack(spacing: 8) {
            Button(action: action) {
                Image(systemName: systemImage)
                    .font(.system(size: 26, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(width: 66, height: 66)
                    .background(Circle().fill(tint.opacity(0.85)))
            }
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }
}

/// The call's pulsing avatar. The `.symbolEffect(.pulse)` animation is iOS 17+, so we gate
/// it on availability and fall back to a static icon on iOS 16.
private struct PulsingWaveform: View {
    let active: Bool

    var body: some View {
        let icon = Image(systemName: "waveform.circle.fill")
            .resizable()
            .scaledToFit()
            .frame(width: 110, height: 110)
            .foregroundStyle(.tint)
        if #available(iOS 17.0, *) {
            icon.symbolEffect(.pulse, isActive: active)
        } else {
            icon
        }
    }
}

#Preview {
    InCallView().environmentObject(CallController())
}

```


## ios/VeraCall/VeraCall/Resources/Info.plist

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!--
  Info.plist — VeraCall

  Key entries for this app:
    * UIBackgroundModes = voip + audio
        - "voip" lets PushKit wake the app to receive an incoming-call push when
          backgrounded or terminated, and report it to CallKit.
        - "audio" keeps the WebRTC audio session alive while the call runs in the
          background (screen locked / app not foreground).
    * NSMicrophoneUsageDescription — required; the app records the mic to send to Vera.
        The system shows this string in the mic permission prompt.

  Bundle identifier is supplied by the Xcode build setting PRODUCT_BUNDLE_IDENTIFIER
  (see project.pbxproj / README) — it MUST match the App ID you create in the Apple
  Developer portal and the APNS_BUNDLE_ID you give voip_push.py.
-->
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>$(DEVELOPMENT_LANGUAGE)</string>
    <key>CFBundleDisplayName</key>
    <string>Vera</string>
    <key>CFBundleExecutable</key>
    <string>$(EXECUTABLE_NAME)</string>
    <key>CFBundleIdentifier</key>
    <string>$(PRODUCT_BUNDLE_IDENTIFIER)</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>$(PRODUCT_NAME)</string>
    <key>CFBundlePackageType</key>
    <string>$(PRODUCT_BUNDLE_PACKAGE_TYPE)</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSRequiresIPhoneOS</key>
    <true/>

    <!-- Microphone permission prompt text (required for getUserMedia/mic capture). -->
    <key>NSMicrophoneUsageDescription</key>
    <string>Vera needs the microphone so you can talk to her on a call.</string>

    <!-- Background execution: VoIP push wake + ongoing call audio. -->
    <key>UIBackgroundModes</key>
    <array>
        <string>voip</string>
        <string>audio</string>
    </array>

    <!-- Standard scene / launch boilerplate. -->
    <key>UIApplicationSupportsIndirectInputEvents</key>
    <true/>
    <key>UILaunchScreen</key>
    <dict>
        <key>UIColorName</key>
        <string></string>
    </dict>
    <key>UISupportedInterfaceOrientations</key>
    <array>
        <string>UIInterfaceOrientationPortrait</string>
    </array>
    <key>UISupportedInterfaceOrientations~ipad</key>
    <array>
        <string>UIInterfaceOrientationPortrait</string>
        <string>UIInterfaceOrientationPortraitUpsideDown</string>
        <string>UIInterfaceOrientationLandscapeLeft</string>
        <string>UIInterfaceOrientationLandscapeRight</string>
    </array>
</dict>
</plist>

```


## ios/VeraCall/VeraCall/Resources/VeraCall.entitlements

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!--
  VeraCall.entitlements

  aps-environment = development
    Enables Apple Push Notification service (which VoIP/PushKit pushes ride on). For a
    TestFlight/App Store build, Xcode rewrites this to "production" automatically when you
    archive with a distribution profile; for development/device runs it stays "development".
    The matching APNs server host for voip_push.py:
        development -> api.sandbox.push.apple.com
        production  -> api.push.apple.com

  NOTE ON SWIPE-TO-ANSWER vs AUTO-ANSWER:
    The native full-screen swipe-to-answer screen comes from CallKit's
    reportNewIncomingCall(...) and needs NO special entitlement — it is the supported path
    and is what this app uses. There is a separate, restricted entitlement
    `com.apple.developer.allow-auto-answer-calls` that would let the call auto-connect with
    no swipe, but Apple grants it only to specific use cases (it requires a request/approval
    and is rarely granted). We deliberately do NOT depend on it. If you were ever granted it,
    you'd add it here; otherwise leave it out and use swipe-to-answer.
-->
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>aps-environment</key>
    <string>development</string>
</dict>
</plist>

```
