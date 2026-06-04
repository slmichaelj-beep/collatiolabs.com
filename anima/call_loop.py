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
    from . import cloud
    from .heart import Heart
    from .mouth import OllamaBrain, StubBrain, system_prompt
    from .util import load_json
    brain = None
    try:
        if cloud.is_cloud():
            brain = cloud.build_cloud_brain()
    except Exception:
        brain = None
    if brain is None:
        try:
            brain = OllamaBrain()
        except Exception:
            brain = StubBrain()
    try:
        h = Heart.from_dict(load_json(f".anima/{name}.json"))
        h.advance()
        feeling = h.feeling()
    except Exception:
        feeling = {}
    sysp = system_prompt(name, feeling)                # persona + dials + bridge + narrative
    try:
        return (brain.reply(sysp, user_text, history) or "").strip()
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
        pc.addTrack(self.speaker)
        self.history: list = []
        self._last_voice = time.monotonic()
        self._done = asyncio.Event()

    def attach(self, track) -> None:
        asyncio.ensure_future(self._greet())
        asyncio.ensure_future(self._listen(track))

    async def _say(self, text: str) -> None:
        loop = asyncio.get_running_loop()
        samples = await loop.run_in_executor(None, _tts_samples, text)
        for i in range(0, len(samples), OUT_SAMPLES):
            self.speaker.push(samples[i:i + OUT_SAMPLES])
        self._last_voice = time.monotonic()

    async def _greet(self) -> None:
        await asyncio.sleep(0.3)
        await self._say("Hey — I'm here. What's on your mind?")

    async def _listen(self, track) -> None:
        resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
        speech: list = []
        in_speech = False
        gap = 0
        loop = asyncio.get_running_loop()
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
        if not text:
            return
        low = text.lower()
        if any(w in low for w in ("goodbye", "good bye", "bye", "talk later", "good night", "see you")):
            await self._say("Night. I'm here whenever you want me.")
            await asyncio.sleep(2.0)
            await self._hangup()
            return
        reply = await loop.run_in_executor(None, _reply_to, self.name, text, list(self.history))
        self.history.append((text, reply))
        await self._say(reply)

    async def _hangup(self) -> None:
        self._done.set()
        try:
            await self.pc.close()
        except Exception:
            pass
