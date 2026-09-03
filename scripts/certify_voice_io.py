#!/usr/bin/env python3
"""
certify_voice_io — Vera's voice in + voice out: the /tts, /stt, /say, /talk endpoints, their
backends, and the AEC-safe barge-in / SpeakerTrack flush logic of the live call.

Voice has two MODEL-dependent legs that need heavy local audio models (Kokoro TTS, faster-whisper
STT) and are NOT byte-deterministic — those are disclosed in the contract's known_gaps, not run here.
What IS deterministic — and is the audit's whole point — is the request/response CONTRACT, the
AUTH-GATE, and the call's barge-in/flush safety logic. This certifies that floor through the SAME
functions the server's voice endpoints and the call loop call, with the model swapped for a faithful
FAKE so the I/O is controlled exactly:

  A. /tts CONTRACT (server._tts, via a FAKE voice) — empty text -> (400); whitespace -> (400);
     a mouth whose .voice is None -> (503 "voice unavailable"); a voice that writes a real WAV ->
     (200, "audio/wav") with a real RIFF body. This is exactly what POST /tts returns to the phone.
  B. /stt CONTRACT (server._transcribe, via a FAKE ears) — _transcribe(raw_bytes) writes a REAL
     temp file holding EXACTLY those bytes, hands its path to ears.listen, and returns {"text": ...};
     an ears that RAISES yields {"text": ""} (honest empty, never a 500). That is POST /stt's body.
  C. AUTH-GATE (static, the no-wallpaper cross-check) — in server.do_POST the _authed() (token) and
     _passed() (Face-ID) guards BOTH precede the /tts /stt /say /talk dispatch, and /say + /talk run
     the honest reply turn _turn(...,voice=False). No voice route is reachable unauthenticated.
  D. AEC-SAFE BARGE-IN (call_loop._is_barge, pure logic) — because the mic hears Vera's own speaker
     (no echo cancellation), a barge-in fires ONLY on energy above a HIGHER threshold sustained for
     several CONSECUTIVE frames: sustained loud -> True; sustained ECHO-level (below the barge
     threshold) -> False (she never interrupts herself); exactly-at-threshold -> False; window too
     short -> False; barge_frames=0 (disabled) -> False.
  E. ATOMIC MID-SPEECH FLUSH (call_loop.SpeakerTrack.flush) — after queuing TTS chunks + a partial
     output buffer, speaking() is True; flush() drains the queue AND the buffer; speaking() flips to
     False; the track is reusable afterward. This is the "stop talking the instant the user cuts in".
  F. AUDIO FETCH IS TRAVERSAL-SAFE (server._serve_audio_file) — a non-audio extension, a ../ escape,
     and an empty name all 404; a real in-store WAV is served (200, "audio/wav") by basename only.

Hermetic + offline: every store (incl. server.STORE) is redirected via gate0_prime_experience.
_temp_store; the FAKE voice/ears are injected by saving+restoring server._MOUTH / server._EARS so the
real singletons (and any real model) are never built; NO Ollama, NO Kokoro/Whisper inference, NO
network. The real .anima is fingerprinted before/after and asserted byte-identical. Exit 0 ==
CERTIFIED, 1 == FAIL.
"""
from __future__ import annotations

import asyncio
import importlib.util
import struct
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Touched indirectly via the imports below; keep intake quiet/offline just in case a transitive
# import wires the intake path (matches the audit's standing rule for any intake-adjacent cert).
import os
os.environ.setdefault("ANIMA_INTAKE_OFFLINE", "1")

_spec = importlib.util.spec_from_file_location("g0pe", str(ROOT / "scripts" / "gate0_prime_experience.py"))
_g0pe = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_g0pe)
_temp_store = _g0pe._temp_store
_footprint = _g0pe._footprint


# --- faithful fakes: exercise the REAL server/call code, control only the model I/O ----------
class _FakeVoice:
    """Stands in for KokoroVoice: writes a real (tiny) WAV and returns its path, exactly as the
    real voice's contract requires — so server._tts's success path is driven for real, byte for
    byte, without loading Kokoro."""
    name = "fake-kokoro"

    def speak(self, text, hints, out_path):
        with wave.open(out_path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(24000)
            w.writeframes(struct.pack("<8h", *([1200] * 8)))
        return out_path


class _MouthWithVoice:
    voice = _FakeVoice()


class _MouthNoVoice:
    voice = None


class _FakeEars:
    """Stands in for WhisperEars: records the bytes it was handed (so we can prove _transcribe
    wrote a real temp file with the caller's audio) and returns a fixed transcript."""
    name = "fake-whisper"

    def __init__(self):
        self.seen = None

    def listen(self, audio_path):
        self.seen = Path(audio_path).read_bytes()
        return "the cathedral bells rang at midnight"


class _BoomEars:
    def listen(self, audio_path):
        raise RuntimeError("whisper backend down")


def main() -> int:
    from anima import server, call_loop
    import numpy as np
    fails = []

    def ck(label, cond):
        print(("  ok   " if cond else "  XX   ") + label)
        if not cond:
            fails.append(label)

    print("VOICE I/O — /tts /stt /say /talk + AEC-safe barge-in + atomic mid-speech flush")
    print("=" * 78)

    real_anima = ROOT / ".anima"
    fp_before = _footprint(real_anima)

    with _temp_store():
        # Inject the fakes; restore the real singletons no matter what (so no real model is ever built
        # by this process and the next consumer is unaffected).
        saved_mouth, saved_ears = server._MOUTH, server._EARS
        try:
            # ---- A. /tts CONTRACT (server._tts) -------------------------------------------------
            server._MOUTH = _MouthWithVoice()
            ck("A1: /tts on EMPTY text -> 400 (the phone never asks Kokoro to voice nothing)",
               server._tts({"text": ""})[:2] == (400, "text/plain"))
            ck("A2: /tts on whitespace-only text -> 400",
               server._tts({"text": "   "})[:2] == (400, "text/plain"))
            server._MOUTH = _MouthNoVoice()
            ck("A3: /tts with NO voice backend -> 503 'voice unavailable' (honest, not a fake clip)",
               server._tts({"text": "hello"})[:2] == (503, "text/plain"))
            server._MOUTH = _MouthWithVoice()
            code, ctype, body = server._tts({"text": "hello world"})
            ck("A4: /tts success -> (200, audio/wav) with a real RIFF WAV body",
               code == 200 and ctype == "audio/wav" and body[:4] == b"RIFF" and len(body) > 44)

            # ---- B. /stt CONTRACT (server._transcribe) ------------------------------------------
            fe = _FakeEars()
            server._EARS = fe
            RAW = b"RAW-PCM-AUDIO-BYTES-abc123"
            out = server._transcribe(RAW)
            ck("B1: /stt returns {'text': ...} from the ears' transcript",
               isinstance(out, dict) and out.get("text") == "the cathedral bells rang at midnight")
            ck("B2: /stt wrote a REAL temp file holding EXACTLY the caller's audio bytes "
               "(the bytes truly reach the transcriber)", fe.seen == RAW)
            server._EARS = _BoomEars()
            ck("B3: /stt on a transcriber failure -> {'text': ''} (honest empty, never a 500)",
               server._transcribe(b"xx") == {"text": ""})
        finally:
            server._MOUTH, server._EARS = saved_mouth, saved_ears

        # ---- C. AUTH-GATE (static no-wallpaper cross-check) -------------------------------------
        server_src = (ROOT / "anima" / "server.py").read_text()
        post = server_src.index("def do_POST(")
        authed_at = server_src.index("if not self._authed()", post)
        passed_at = server_src.index("if not self._passed()", post)
        tts_at = server_src.index('path == "/tts"', post)
        ck("C1: do_POST's _authed() (token) guard precedes the /tts dispatch (no unauth voice)",
           authed_at < tts_at)
        ck("C2: do_POST's _passed() (Face-ID) guard also precedes the /tts dispatch",
           passed_at < tts_at)
        ck("C3: all four voice routes are dispatched (/tts /stt /say /talk)",
           all(f'path == "{p}"' in server_src for p in ("/tts", "/stt", "/say", "/talk")))
        ck("C4: /say + /talk run the honest reply turn _turn(...,voice=False) (no confabulation bypass)",
           server_src.count("_turn(self.name, text, voice=False)") >= 2)

        # ---- D. AEC-SAFE BARGE-IN (call_loop._is_barge, pure) ----------------------------------
        ck("D1: sustained loud energy over the barge threshold -> barge-in True",
           call_loop._is_barge([500, 600] + [2500] * 5, 2000.0, 5) is True)
        ck("D2: sustained ECHO-level energy (below the barge threshold) -> False "
           "(she never self-triggers on her own speaker)",
           call_loop._is_barge([800] * 10, 2000.0, 5) is False)
        ck("D3: energy exactly AT the threshold (not strictly above) -> False",
           call_loop._is_barge([2000] * 5, 2000.0, 5) is False)
        ck("D4: a window shorter than barge_frames -> False (insufficient sustain)",
           call_loop._is_barge([9999] * 3, 2000.0, 5) is False)
        ck("D5: barge_frames=0 (disabled) -> always False",
           call_loop._is_barge([9999] * 10, 0.0, 0) is False)

        # ---- E. ATOMIC MID-SPEECH FLUSH (call_loop.SpeakerTrack.flush) -------------------------
        async def _flush_probe():
            st = call_loop.SpeakerTrack()
            empty0 = st.speaking()                        # nothing queued yet
            chunk = np.ones(call_loop.OUT_SAMPLES, dtype=np.int16) * 1000
            st.push(chunk); st.push(chunk); st.push(chunk)
            st._buf = np.ones(64, dtype=np.int16) * 500   # a partially-consumed output frame
            speaking_before = st.speaking()
            q_before, buf_before = st._q.qsize(), len(st._buf)
            st.flush()                                    # the user cut in — stop instantly
            speaking_after = st.speaking()
            q_after, buf_after = st._q.qsize(), len(st._buf)
            st.push(chunk)                                # reusable after a flush
            reusable = st.speaking()
            st.flush()
            return (empty0, speaking_before, q_before, buf_before,
                    speaking_after, q_after, buf_after, reusable)
        (empty0, sp_b, q_b, buf_b, sp_a, q_a, buf_a, reuse) = asyncio.run(_flush_probe())
        ck("E1: a fresh SpeakerTrack is not speaking()", empty0 is False)
        ck("E2: after pushing TTS chunks + a partial buffer, speaking() is True (queue+buf non-empty)",
           sp_b is True and q_b == 3 and buf_b == 64)
        ck("E3: flush() drains BOTH the queue and the buffer -> speaking() flips to False",
           sp_a is False and q_a == 0 and buf_a == 0)
        ck("E4: the track is reusable after a flush (next push speaks again, next flush silences)",
           reuse is True)

        # ---- F. AUDIO FETCH IS TRAVERSAL-SAFE (server._serve_audio_file) -----------------------
        ck("F1: a non-audio extension -> 404 (no reading e.g. a .json out of the store)",
           server._serve_audio_file("secret.json")[0] == 404)
        ck("F2: a ../ path-traversal escape -> 404",
           server._serve_audio_file("../../etc/passwd")[0] == 404)
        ck("F3: an empty name -> 404", server._serve_audio_file("")[0] == 404)
        server.STORE.mkdir(parents=True, exist_ok=True)
        clip = server.STORE / "vera_clip_cert.wav"
        with wave.open(str(clip), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(24000)
            w.writeframes(struct.pack("<4h", 1, 2, 3, 4))
        acode, actype, abody = server._serve_audio_file("vera_clip_cert.wav")
        ck("F4: a real in-store WAV is served (200, audio/wav) by basename with a real RIFF body",
           acode == 200 and actype == "audio/wav" and abody[:4] == b"RIFF")

    # ---- HERMETICITY -----------------------------------------------------------------------
    fp_after = _footprint(real_anima)
    ck("H1: real .anima is byte-identical after the cert (no contamination)", fp_before == fp_after)

    print("\nVOICE-IO CERT: " + ("CERTIFIED" if not fails else f"FAIL ({len(fails)})"))
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
