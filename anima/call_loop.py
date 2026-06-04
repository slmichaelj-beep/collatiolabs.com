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
